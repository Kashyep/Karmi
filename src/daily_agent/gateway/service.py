"""Gateway: route a request to a free model, validate the reply, retry once, else defer.

Policy (all bounded, nothing hidden):
* at most two provider attempts per request, the second always on a different model;
* a failed validation (or an explicit regenerate) escalates one class; a provider error falls
  back within the eligible pool, preferring another provider;
* the circuit breaker / cooldowns live in ``HealthTracker``; this module only reports outcomes;
* a final failure returns ``failed=True`` and the caller defers and releases the reservation.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import threading
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from daily_agent.gateway.adapters import ChatProvider
from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import ModelRegistry, RegistryModel
from daily_agent.gateway.router import RouteRequest, eligible_models
from daily_agent.gateway.types import (
    CapacityFullError,
    ChatRequest,
    ModelClass,
    ProviderError,
    ProviderUnavailableError,
    StreamChunk,
    TaskType,
    UnauthorizedError,
    ValidationFailedError,
)
from daily_agent.plans import PlanPolicy
from daily_agent.providers import ProviderCall

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
FREE_MEASUREMENT = "registry-free-model"

BASE_SYSTEM_PROMPT = (
    "You are Karmi, a patient study and productivity assistant for students in India. Give "
    "correct, concise answers. Reply in the language the user wrote in (Hindi, English, or a "
    "Hindi-English mix). Show working for maths and keep code runnable. Use the earlier "
    'conversation: a short reply such as a place name or "yes" usually answers your previous '
    "question. The current date and time are given below; when the user names another place or "
    "timezone, convert from IST. Use simple Markdown (bold, lists, code blocks) only when it "
    "helps; no tables. Never claim that a task, reminder or message was saved, sent or changed; "
    "this chat route cannot perform actions. If required facts are missing, ask one short "
    "clarifying question."
)


def _home_zone() -> tzinfo:
    # IST has no DST, so the fixed offset is exact when the tz database is missing.
    try:
        return ZoneInfo("Asia/Kolkata")
    except ZoneInfoNotFoundError:  # pragma: no cover - depends on the host tz database
        return timezone(timedelta(hours=5, minutes=30), "IST")


HOME_ZONE = _home_zone()


def build_system_prompt(now: datetime) -> str:
    """Base prompt plus the current IST date/time (``now`` must be timezone-aware)."""
    local = now.astimezone(HOME_ZONE)
    stamp = f"{local:%A}, {local.day} {local:%B %Y, %H:%M}"
    return f"{BASE_SYSTEM_PROMPT}\nCurrent date and time: {stamp} IST (Asia/Kolkata, UTC+05:30)."


# Upper bound for the built prompt: Wednesday + September are the longest names.
SYSTEM_PROMPT_MAX_CHARS = len(build_system_prompt(datetime(2026, 9, 30, 6, 30, tzinfo=UTC)))


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class GatewayResult:
    text: str | None
    calls: tuple[ProviderCall, ...]
    action: str | None  # provider/model that produced ``text`` (or was tried first on failure)
    failed: bool
    reason: str | None = None
    attempts: int = 0


def validate_output(text: str, finish_reason: str | None, task_type: TaskType) -> str | None:
    """Return a rejection reason, or ``None`` when the reply is acceptable."""
    if not text.strip():
        return "empty_reply"
    if finish_reason == "content_filter":
        return "content_filtered"
    if task_type == TaskType.HINDI and not _DEVANAGARI.search(text):
        return "wrong_language"
    return None


def _failed_call(model: RegistryModel, operation: str) -> ProviderCall:
    return ProviderCall(
        provider=model.provider,
        model_id=model.model_id,
        operation=operation,
        input_tokens=None,
        output_tokens=None,
        cost_micro=0,
        measurement=FREE_MEASUREMENT,
        rate_version=f"registry-{model.snapshot_date}",
    )


class Gateway:
    def __init__(
        self,
        *,
        registry: ModelRegistry,
        providers: Mapping[str, ChatProvider],
        health: HealthTracker,
        kill_switch: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        # Only models whose provider is actually configured are routable.
        self.registry = registry.for_providers(frozenset(providers))
        self._providers = providers
        self.health = health
        self.kill_switch = kill_switch
        self._clock = clock or _utc_now

    @property
    def live(self) -> bool:
        return not self.kill_switch and bool(self.registry.models)

    def _available(self, model: RegistryModel) -> bool:
        return self.health.available(model.provider, model.model_id)

    def eligible_actions(self, plan: PlanPolicy) -> list[str]:
        """Every model this plan could reach (used for routing evidence; ignores health)."""
        classes = {ModelClass(name) for name in plan.model_classes}
        return sorted(m.action for m in self.registry.models if m.model_class in classes)

    def generate(
        self,
        *,
        plan: PlanPolicy,
        text: str,
        task_type: TaskType,
        max_output_tokens: int,
        escalate: bool = False,
        history: Sequence[Mapping[str, str]] = (),
    ) -> GatewayResult:
        """Generate a reply to ``text``; ``history`` holds earlier turns, oldest first, already
        trimmed to the plan's input budget by the caller."""
        system_prompt = build_system_prompt(self._clock())
        history_bytes = sum(len(turn["content"].encode("utf-8")) for turn in history)
        request = RouteRequest(
            plan=plan,
            task_type=task_type,
            prompt_tokens=max(
                1, (len(text.encode("utf-8")) + len(system_prompt) + history_bytes) // 4
            ),
            max_output_tokens=max_output_tokens,
            escalate=escalate,
        )
        pool = eligible_models(self.registry, request, is_available=self._available)
        if not pool:
            return GatewayResult(None, (), None, True, "no_eligible_model")
        messages = (
            {"role": "system", "content": system_prompt},
            *({"role": turn["role"], "content": turn["content"]} for turn in history),
            {"role": "user", "content": text},
        )
        calls: list[ProviderCall] = []
        first = pool[0]
        reply, reason = self._attempt(first, messages, task_type, max_output_tokens, calls)
        if reply is not None:
            return GatewayResult(reply, tuple(calls), first.action, False, attempts=1)

        validation_failed = reason is not None and not reason.startswith("provider:")
        retry_pool: list[RegistryModel] = []
        if validation_failed:
            retry_pool = eligible_models(
                self.registry,
                request,
                is_available=self._available,
                exclude={first.action},
                min_rank=first.model_class.rank + 1,
            )
        if not retry_pool:
            retry_pool = eligible_models(
                self.registry, request, is_available=self._available, exclude={first.action}
            )
        retry_pool.sort(key=lambda m: m.provider == first.provider)  # stable: other provider first
        if not retry_pool:
            return GatewayResult(None, tuple(calls), first.action, True, reason, attempts=1)
        second = retry_pool[0]
        reply, reason2 = self._attempt(second, messages, task_type, max_output_tokens, calls)
        if reply is not None:
            return GatewayResult(reply, tuple(calls), second.action, False, attempts=2)
        return GatewayResult(None, tuple(calls), second.action, True, reason2, attempts=2)

    def _attempt(
        self,
        model: RegistryModel,
        messages: tuple[dict[str, str], ...],
        task_type: TaskType,
        max_output_tokens: int,
        calls: list[ProviderCall],
    ) -> tuple[str | None, str | None]:
        provider = self._providers[model.provider]
        self.health.begin_call(model.provider)
        request = ChatRequest(
            model_id=model.model_id,
            messages=messages,
            max_output_tokens=max_output_tokens,
        )
        try:
            result = provider.complete(request, model)
        except ProviderError as exc:
            self.health.record_failure(model.provider, model.model_id, exc)
            calls.append(_failed_call(model, "generate_failed"))
            logger.warning("gateway call failed model=%s kind=%s", model.action, exc.kind)
            return None, f"provider:{exc.kind}"
        self.health.record_success(model.provider)
        rejection = validate_output(result.text, result.finish_reason, task_type)
        if rejection is not None:
            calls.append(replace(result.call, operation="generate_rejected"))
            logger.warning("gateway reply rejected model=%s reason=%s", model.action, rejection)
            return None, rejection
        calls.append(result.call)
        return result.text, None

    async def stream(
        self,
        *,
        plan: PlanPolicy,
        text: str,
        task_type: TaskType,
        max_output_tokens: int,
        messages: tuple[dict[str, str], ...] | None = None,
        history: Sequence[Mapping[str, str]] = (),
    ) -> AsyncIterator[StreamChunk]:
        if not self.live:
            raise ProviderUnavailableError("gateway is disabled or no configured models")
        system_prompt = build_system_prompt(self._clock())
        history_bytes = sum(len(turn["content"].encode("utf-8")) for turn in history)
        request = RouteRequest(
            plan=plan,
            task_type=task_type,
            prompt_tokens=max(
                1, (len(text.encode("utf-8")) + len(system_prompt) + history_bytes) // 4
            ),
            max_output_tokens=max_output_tokens,
        )
        pool = eligible_models(self.registry, request, is_available=self._available)
        if not pool:
            raise ProviderUnavailableError("no eligible model available")
        model = pool[0]
        provider = self._providers[model.provider]
        self.health.begin_call(model.provider)
        if messages is None:
            chat_messages: tuple[dict[str, str], ...] = (
                {"role": "system", "content": system_prompt},
                *({"role": turn["role"], "content": turn["content"]} for turn in history),
                {"role": "user", "content": text},
            )
        else:
            chat_messages = messages
        chat_req = ChatRequest(
            model_id=model.model_id,
            messages=chat_messages,
            max_output_tokens=max_output_tokens,
        )
        try:
            stream_gen = provider.stream(chat_req, model)
        except ProviderError as exc:
            self.health.record_failure(model.provider, model.model_id, exc)
            if exc.kind in (ProviderError.TIMEOUT, ProviderError.SERVER):
                raise ProviderUnavailableError(str(exc)) from exc
            if exc.kind == ProviderError.AUTH:
                raise UnauthorizedError(str(exc)) from exc
            if exc.kind == ProviderError.RATE_LIMITED:
                retry_s = int(exc.retry_after_seconds) if exc.retry_after_seconds else None
                raise CapacityFullError(str(exc), retry_after_s=retry_s) from exc
            raise ProviderUnavailableError(str(exc)) from exc
        except Exception as exc:
            self.health.record_failure(
                model.provider, model.model_id, ProviderError(ProviderError.SERVER, str(exc))
            )
            raise ProviderUnavailableError(str(exc)) from exc

        full_text = ""
        final_finish_reason: str | None = None
        final_call: ProviderCall | None = None

        try:
            async for chunk in _stream_with_timeouts(
                stream_gen, first_timeout=20.0, gap_timeout=30.0
            ):
                if chunk.text:
                    full_text += chunk.text
                    yield chunk
                if chunk.finish_reason is not None:
                    final_finish_reason = chunk.finish_reason
                if chunk.call is not None:
                    final_call = chunk.call
        except TimeoutError as exc:
            self.health.record_failure(
                model.provider, model.model_id, ProviderError(ProviderError.TIMEOUT, "timeout")
            )
            raise ProviderUnavailableError("provider timed out during streaming") from exc
        except ProviderError as exc:
            self.health.record_failure(model.provider, model.model_id, exc)
            if exc.kind in (ProviderError.TIMEOUT, ProviderError.SERVER):
                raise ProviderUnavailableError(str(exc)) from exc
            if exc.kind == ProviderError.AUTH:
                raise UnauthorizedError(str(exc)) from exc
            if exc.kind == ProviderError.RATE_LIMITED:
                retry_s = int(exc.retry_after_seconds) if exc.retry_after_seconds else None
                raise CapacityFullError(str(exc), retry_after_s=retry_s) from exc
            raise ProviderUnavailableError(str(exc)) from exc
        except Exception as exc:
            self.health.record_failure(
                model.provider, model.model_id, ProviderError(ProviderError.SERVER, str(exc))
            )
            raise ProviderUnavailableError(str(exc)) from exc

        self.health.record_success(model.provider)
        rejection = validate_output(full_text, final_finish_reason, task_type)
        if rejection is not None:
            logger.warning("stream output rejected model=%s reason=%s", model.action, rejection)
            raise ValidationFailedError(f"validation failed: {rejection}")

        # Map finish reason
        if final_finish_reason == "length":
            mapped_reason = "length"
        elif final_finish_reason == "content_filter":
            mapped_reason = "content_filter"
        elif final_finish_reason == "error":
            mapped_reason = "error"
        else:
            mapped_reason = "stop"

        if final_call is None:
            final_call = ProviderCall(
                provider=model.provider,
                model_id=model.model_id,
                operation="generate",
                input_tokens=None,
                output_tokens=None,
                cost_micro=0,
                measurement=FREE_MEASUREMENT,
                rate_version=f"registry-{model.snapshot_date}",
            )
        yield StreamChunk(text="", finish_reason=mapped_reason, call=final_call)


async def _stream_with_timeouts(
    stream_obj: Iterator[StreamChunk] | AsyncIterator[StreamChunk],
    first_timeout: float = 20.0,
    gap_timeout: float = 30.0,
) -> AsyncIterator[StreamChunk]:
    if inspect.isasyncgen(stream_obj) or hasattr(stream_obj, "__anext__"):
        first = True
        anext_fn = stream_obj.__anext__
        while True:
            timeout = first_timeout if first else gap_timeout
            try:
                chunk = await asyncio.wait_for(anext_fn(), timeout=timeout)
            except StopAsyncIteration:
                break
            first = False
            yield chunk
    else:
        queue: asyncio.Queue[tuple[StreamChunk | None, Exception | None]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _worker() -> None:
            try:
                for item in stream_obj:
                    loop.call_soon_threadsafe(queue.put_nowait, (item, None))
                loop.call_soon_threadsafe(queue.put_nowait, (None, None))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, (None, exc))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

        first = True
        while True:
            timeout = first_timeout if first else gap_timeout
            item, exc = await asyncio.wait_for(queue.get(), timeout=timeout)
            first = False
            if exc is not None:
                raise exc
            if item is None:
                break
            yield item
