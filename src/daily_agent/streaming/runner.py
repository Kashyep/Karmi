"""Background stream generation runner, flush policy, budget settlement and terminal handling."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import SingletonThreadPool

from daily_agent.config import Settings
from daily_agent.conversations.service import touch_conversation
from daily_agent.gateway.service import SYSTEM_PROMPT, Gateway
from daily_agent.gateway.types import (
    CapacityFullError,
    GatewayStreamError,
    ProviderError,
    ProviderUnavailableError,
    QuotaExhaustedError,
    TaskType,
    UnauthorizedError,
    ValidationFailedError,
)
from daily_agent.models import BudgetReservation, ChatMessage, Conversation, Run, RunStatus, utcnow
from daily_agent.plans import PlanPolicy
from daily_agent.schemas_chat import ErrorCategory, FinishReason, MessageStatus
from daily_agent.services import (
    GatewayAdmission,
    measured_cost_micro,
    measured_tokens,
    release_budget,
    return_gateway_requests,
    settle_budget,
)
from daily_agent.streaming.registry import RunState

logger = logging.getLogger(__name__)


def _error_category(exc: Exception) -> tuple[str, bool, int | None]:
    if isinstance(exc, QuotaExhaustedError):
        return ErrorCategory.QUOTA_EXHAUSTED.value, False, None
    if isinstance(exc, CapacityFullError):
        return ErrorCategory.CAPACITY_FULL.value, True, exc.retry_after_s
    if isinstance(exc, ProviderUnavailableError):
        return ErrorCategory.PROVIDER_UNAVAILABLE.value, True, exc.retry_after_s
    if isinstance(exc, ValidationFailedError):
        return ErrorCategory.VALIDATION_FAILED.value, True, None
    if isinstance(exc, UnauthorizedError):
        return ErrorCategory.UNAUTHORIZED.value, False, None
    if isinstance(exc, GatewayStreamError):
        return exc.category, exc.retryable, exc.retry_after_s
    if isinstance(exc, ProviderError):
        if exc.kind in (ProviderError.TIMEOUT, ProviderError.SERVER):
            return ErrorCategory.PROVIDER_UNAVAILABLE.value, True, None
        if exc.kind == ProviderError.RATE_LIMITED:
            retry_s = int(exc.retry_after_seconds) if exc.retry_after_seconds else None
            return ErrorCategory.CAPACITY_FULL.value, True, retry_s
        if exc.kind == ProviderError.AUTH:
            return ErrorCategory.UNAUTHORIZED.value, False, None
    return ErrorCategory.INTERNAL.value, True, None


class StreamRunner:
    def __init__(
        self,
        *,
        run_state: RunState,
        plan: PlanPolicy,
        text: str,
        task_type: TaskType,
        max_output_tokens: int,
        gateway: Gateway,
        settings: Settings,
        session_factory: Callable[[], Session],
        reservation_id: str,
        prior_content: str | None = None,
        admission: GatewayAdmission | None = None,
    ) -> None:
        self.run_state = run_state
        self.plan = plan
        self.text = text
        self.task_type = task_type
        self.max_output_tokens = max_output_tokens
        self.gateway = gateway
        self.settings = settings
        self.session_factory = session_factory
        self.reservation_id = reservation_id
        self.prior_content = prior_content
        self.admission = admission

        self.seq = 0
        self.accumulated_text = ""
        self.last_flush_time = time.monotonic()
        self.last_flushed_len = 0
        self.last_event_time = time.monotonic()
        self.first_delta_recorded = False
        self.start_time = time.monotonic()
        self.provider_invoked = False
        self._budget_settled = False
        self._budget_lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._flushed_terminal = False
        self.final_call: Any = None
        if self.run_state.on_finalize is None:
            self.run_state.on_finalize = self.finalize

    @property
    def budget_settled(self) -> bool:
        return self._budget_settled

    @budget_settled.setter
    def budget_settled(self, value: bool) -> None:
        self._budget_settled = value

    def _is_sqlite_singleton_memory(self) -> bool:
        if hasattr(self, "_sqlite_singleton_memory"):
            return self._sqlite_singleton_memory
        is_singleton = False
        try:
            bind = getattr(self.session_factory, "kw", {}).get("bind") or getattr(
                self.session_factory, "bind", None
            )
            if bind is None:
                with self.session_factory() as session:
                    bind = session.get_bind()
            if (
                bind is not None
                and bind.dialect.name == "sqlite"
                and isinstance(bind.pool, SingletonThreadPool)
            ):
                is_singleton = True
        except Exception:
            pass
        self._sqlite_singleton_memory = is_singleton
        return is_singleton

    async def _run_in_thread(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self._is_sqlite_singleton_memory():
            return fn(*args, **kwargs)
        return await asyncio.to_thread(fn, *args, **kwargs)
    def _flush_db(
        self,
        *,
        text: str,
        run_status: str | None = None,
        run_finish_reason: str | None = None,
        message_status: str | None = None,
        message_finish_reason: str | None = None,
        outcome: str | None = None,
    ) -> None:
        with self._flush_lock:
            with self.session_factory() as session:
                run = session.scalar(select(Run).where(Run.id == self.run_state.run_id))
                if run is not None:
                    run.partial_text = text
                    run.last_seq = self.seq
                    if run_status is not None:
                        run.status = run_status
                    if run_finish_reason is not None:
                        run.finish_reason = run_finish_reason
                    if outcome is not None:
                        run.outcome = outcome
                    if run_status == RunStatus.COMPLETED:
                        run.response_text = text

                msg = session.scalar(select(ChatMessage).where(ChatMessage.id == self.run_state.assistant_message_id))
                if msg is not None:
                    # If continuing, full content includes prior text
                    full_content = (self.prior_content or "") + text
                    msg.content = full_content
                    if message_status is not None:
                        msg.status = message_status
                    if message_finish_reason is not None:
                        msg.finish_reason = message_finish_reason
                if msg is not None and run_status in (RunStatus.COMPLETED, RunStatus.FAILED):
                    self._flushed_terminal = True
                    conversation = session.get(Conversation, msg.conversation_id)
                    if conversation is not None:
                        touch_conversation(conversation, utcnow())
                session.commit()
                self.last_flush_time = time.monotonic()
                self.last_flushed_len = len(text)

    def _settle_or_release_budget(self, *, release: bool = False) -> None:
        with self._budget_lock:
            if self._budget_settled:
                return
            self._budget_settled = True
            with self.session_factory() as session:
                reservation = session.get(BudgetReservation, self.reservation_id)
                if reservation is not None:
                    if release or (self.final_call is None and not self.accumulated_text):
                        release_budget(session, reservation)
                    else:
                        calls = [self.final_call] if self.final_call is not None else []
                        cost = measured_cost_micro(calls) if calls else 0
                        tokens = measured_tokens(calls) if calls else len(self.accumulated_text) // 4
                        settle_budget(
                            session,
                            reservation,
                            attempt_id=f"{self.run_state.run_id}:1",
                            actual_micro=cost,
                            actual_tokens=tokens,
                            calls=calls,
                        )
                if self.admission is not None:
                    used = 1 if (self.provider_invoked or self.final_call is not None) else 0
                    return_gateway_requests(session, self.admission, used=used)
                session.commit()

    def finalize(self) -> None:
        self._settle_or_release_budget(release=not bool(self.accumulated_text))
        if not self._flushed_terminal:
            try:
                self._flush_db(
                    text=self.accumulated_text,
                    run_status=RunStatus.FAILED,
                    run_finish_reason=FinishReason.ERROR.value,
                    message_status=MessageStatus.FAILED.value,
                    message_finish_reason=FinishReason.ERROR.value,
                    outcome="FAILED",
                )
            except Exception:
                logger.exception("Failed to flush DB during runner finalization")

    async def _heartbeat_loop(self) -> None:
        while not self.run_state.terminal:
            await asyncio.sleep(1.0)
            if self.run_state.terminal:
                break
            now = time.monotonic()
            if now - self.last_event_time >= 15.0:
                self.last_event_time = now
                heartbeat_at = datetime.now(UTC).isoformat()
                await self.run_state.publish("heartbeat", {"at": heartbeat_at})

    async def run(self) -> None:
        logger.info("stream.started run_id=%s", self.run_state.run_id)
        # Always emit run.started first (seq=0)
        await self.run_state.publish(
            "run.started",
            {
                "run_id": self.run_state.run_id,
                "conversation_id": self.run_state.conversation_id,
                "user_message_id": self.run_state.user_message_id,
                "assistant_message_id": self.run_state.assistant_message_id,
                "seq": 0,
            },
            seq=0,
        )
        self.last_event_time = time.monotonic()

        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Construct messages if prior assistant content is provided (continue)
        messages: tuple[dict[str, str], ...] | None = None
        if self.prior_content:
            messages = (
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self.text},
                {"role": "assistant", "content": self.prior_content},
            )

        finish_reason: str = FinishReason.STOP.value
        try:
            self.provider_invoked = True
            stream_gen = self.gateway.stream(
                plan=self.plan,
                text=self.text,
                task_type=self.task_type,
                max_output_tokens=self.max_output_tokens,
                messages=messages,
            )
            async for chunk in stream_gen:
                if chunk.text:
                    self.seq += 1
                    self.accumulated_text += chunk.text
                    now = time.monotonic()
                    self.last_event_time = now
                    if not self.first_delta_recorded:
                        self.first_delta_recorded = True
                        first_delta_ms = int((now - self.start_time) * 1000)
                        logger.info("stream.first_delta_ms run_id=%s ms=%d", self.run_state.run_id, first_delta_ms)

                    await self.run_state.publish(
                        "message.delta",
                        {"text": chunk.text},
                        seq=self.seq,
                    )

                    # Flush partial text at most once per 1.0 s or per 1 KB of new text
                    if (now - self.last_flush_time >= 1.0) or (len(self.accumulated_text) - self.last_flushed_len >= 1024):
                        await self._run_in_thread(
                            self._flush_db,
                            text=self.accumulated_text,
                            run_status="streaming",
                            message_status=MessageStatus.STREAMING.value,
                        )

                if chunk.finish_reason is not None:
                    finish_reason = chunk.finish_reason
                if chunk.call is not None:
                    self.final_call = chunk.call

            # Stream finished normally
            await self._run_in_thread(
                self._flush_db,
                text=self.accumulated_text,
                run_status=RunStatus.COMPLETED,
                run_finish_reason=finish_reason,
                message_status=MessageStatus.COMPLETE.value,
                message_finish_reason=finish_reason,
                outcome="COMPLETED",
            )
            await self._run_in_thread(self._settle_or_release_budget, release=False)

            in_tokens = self.final_call.input_tokens if self.final_call else None
            out_tokens = self.final_call.output_tokens if self.final_call else None
            await self.run_state.publish(
                "run.finished",
                {
                    "finish_reason": finish_reason,
                    "outcome": "COMPLETED",
                    "input_tokens": in_tokens,
                    "output_tokens": out_tokens,
                    "assistant_message_id": self.run_state.assistant_message_id,
                },
            )
            logger.info("stream.finished run_id=%s finish_reason=%s", self.run_state.run_id, finish_reason)

        except asyncio.CancelledError:
            # Stop requested: cancels the provider call. Finish_reason=cancelled, message status=stopped, partial kept
            logger.info("stream.stopped run_id=%s", self.run_state.run_id)
            await self._run_in_thread(
                self._flush_db,
                text=self.accumulated_text,
                run_status=RunStatus.COMPLETED,
                run_finish_reason=FinishReason.CANCELLED.value,
                message_status=MessageStatus.STOPPED.value,
                message_finish_reason=FinishReason.CANCELLED.value,
                outcome="STOPPED",
            )
            await self._run_in_thread(self._settle_or_release_budget, release=False)
            if not self.run_state.terminal:
                await self.run_state.publish(
                    "run.finished",
                    {
                        "finish_reason": FinishReason.CANCELLED.value,
                        "outcome": "STOPPED",
                        "assistant_message_id": self.run_state.assistant_message_id,
                    },
                )
            raise

        except Exception as exc:
            category, retryable, retry_after_s = _error_category(exc)
            logger.info("stream.error run_id=%s category=%s", self.run_state.run_id, category)
            # Partial text is kept
            await self._run_in_thread(
                self._flush_db,
                text=self.accumulated_text,
                run_status=RunStatus.FAILED,
                run_finish_reason=FinishReason.ERROR.value,
                message_status=MessageStatus.FAILED.value,
                message_finish_reason=FinishReason.ERROR.value,
                outcome="FAILED",
            )
            await self._run_in_thread(self._settle_or_release_budget, release=not bool(self.accumulated_text))
            if not self.run_state.terminal:
                await self.run_state.publish(
                    "run.error",
                    {
                        "category": category,
                        "retryable": retryable,
                        "retry_after_s": retry_after_s,
                        "assistant_message_id": self.run_state.assistant_message_id,
                    },
                )

        finally:
            heartbeat_task.cancel()


def start_stream_run(
    *,
    run_state: RunState,
    plan: PlanPolicy,
    text: str,
    task_type: TaskType,
    max_output_tokens: int,
    gateway: Gateway,
    settings: Settings,
    session_factory: Callable[[], Session],
    reservation_id: str,
    prior_content: str | None = None,
    admission: GatewayAdmission | None = None,
) -> asyncio.Task[None]:
    runner = StreamRunner(
        run_state=run_state,
        plan=plan,
        text=text,
        task_type=task_type,
        max_output_tokens=max_output_tokens,
        gateway=gateway,
        settings=settings,
        session_factory=session_factory,
        reservation_id=reservation_id,
        prior_content=prior_content,
        admission=admission,
    )
    task = asyncio.create_task(runner.run())
    run_state.task = task
    run_state.on_finalize = runner.finalize
    return task
