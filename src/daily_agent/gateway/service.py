"""Gateway: route a request to a free model, validate the reply, retry once, else defer.

Policy (all bounded, nothing hidden):
* at most two provider attempts per request, the second always on a different model;
* a failed validation (or an explicit regenerate) escalates one class; a provider error falls
  back within the eligible pool, preferring another provider;
* the circuit breaker / cooldowns live in ``HealthTracker``; this module only reports outcomes;
* a final failure returns ``failed=True`` and the caller defers and releases the reservation.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from daily_agent.gateway.adapters import ChatProvider
from daily_agent.gateway.health import HealthTracker
from daily_agent.gateway.registry import ModelRegistry, RegistryModel
from daily_agent.gateway.router import RouteRequest, eligible_models
from daily_agent.gateway.types import ChatRequest, ModelClass, ProviderError, TaskType
from daily_agent.plans import PlanPolicy
from daily_agent.providers import ProviderCall

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
FREE_MEASUREMENT = "registry-free-model"

SYSTEM_PROMPT = (
    "You are Karmi, a patient study and productivity assistant for students in India. Give "
    "correct, concise answers. Reply in the language the user wrote in (Hindi, English, or a "
    "Hindi-English mix). Show working for maths and keep code runnable. Never claim that a "
    "task, reminder or message was saved, sent or changed; this chat route cannot perform "
    "actions. If required facts are missing, ask one short clarifying question."
)


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
    ) -> None:
        # Only models whose provider is actually configured are routable.
        self.registry = registry.for_providers(frozenset(providers))
        self._providers = providers
        self.health = health
        self.kill_switch = kill_switch

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
    ) -> GatewayResult:
        request = RouteRequest(
            plan=plan,
            task_type=task_type,
            prompt_tokens=max(1, (len(text.encode("utf-8")) + len(SYSTEM_PROMPT)) // 4),
            max_output_tokens=max_output_tokens,
            escalate=escalate,
        )
        pool = eligible_models(self.registry, request, is_available=self._available)
        if not pool:
            return GatewayResult(None, (), None, True, "no_eligible_model")
        messages = (
            {"role": "system", "content": SYSTEM_PROMPT},
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
