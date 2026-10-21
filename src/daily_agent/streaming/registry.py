"""In-process stream registry and run state management."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.models import BudgetReservation, ChatMessage, ReservationStatus, Run
from daily_agent.schemas_chat import ErrorCategory, FinishReason, MessageStatus
from daily_agent.services import release_budget

logger = logging.getLogger(__name__)

@dataclass
class StreamEvent:
    event: str
    data: dict[str, Any]
    seq: int | None = None


@dataclass
class RunState:
    run_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    last_seq: int = 0
    events: list[StreamEvent] = field(default_factory=list)
    terminal: bool = False
    terminated_at: float | None = None
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    partial_text: str = ""
    finish_reason: str | None = None
    created_at: float = field(default_factory=time.time)
    on_finalize: Callable[[], None] | None = None

    async def publish(self, event: str, data: dict[str, Any], seq: int | None = None) -> None:
        async with self.condition:
            if event in ("run.finished", "run.error"):
                if self.terminal:
                    return
                self.terminal = True
                self.terminated_at = time.time()
                self.finish_reason = data.get("finish_reason") or data.get("category")
            evt = StreamEvent(event=event, data=data, seq=seq)
            self.events.append(evt)
            if seq is not None and seq > self.last_seq:
                self.last_seq = seq
            if event == "message.delta" and "text" in data:
                self.partial_text += data["text"]
            self.condition.notify_all()

    def finalize(self) -> None:
        if self.terminal:
            return
        if self.task is not None and not self.task.done():
            self.task.cancel()
        if self.on_finalize is not None:
            try:
                self.on_finalize()
            except Exception:
                logger.exception("Error in run_state on_finalize for run %s", self.run_id)
        if not self.terminal:
            self.terminal = True
            if self.terminated_at is None:
                self.terminated_at = time.time()
            self.finish_reason = FinishReason.ERROR.value
            self.events.append(
                StreamEvent(
                    event="run.error",
                    data={
                        "category": ErrorCategory.INTERNAL.value,
                        "retryable": False,
                        "assistant_message_id": self.assistant_message_id,
                    },
                )
            )
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    async def _notify() -> None:
                        async with self.condition:
                            self.condition.notify_all()
                    loop.create_task(_notify())
            except RuntimeError:
                pass

    def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()

class StreamRegistry:
    def __init__(self, ttl_seconds: float = 600.0, stuck_timeout_seconds: float = 900.0) -> None:
        self._runs: dict[str, RunState] = {}
        self.ttl_seconds = ttl_seconds
        self.stuck_timeout_seconds = stuck_timeout_seconds

    def register(self, run_state: RunState) -> None:
        self.evict_expired()
        self._runs[run_state.run_id] = run_state

    def get(self, run_id: str) -> RunState | None:
        self.evict_expired()
        return self._runs.get(run_id)

    def has(self, run_id: str) -> bool:
        self.evict_expired()
        return run_id in self._runs

    def evict_expired(
        self,
        ttl_seconds: float | None = None,
        stuck_timeout_seconds: float | None = None,
        now: float | None = None,
    ) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        stuck_ttl = stuck_timeout_seconds if stuck_timeout_seconds is not None else self.stuck_timeout_seconds
        current = now if now is not None else time.time()
        to_remove: list[str] = []
        for run_id, state in list(self._runs.items()):
            if state.terminal and state.terminated_at is not None and (current - state.terminated_at) > ttl:
                to_remove.append(run_id)
            elif not state.terminal and (
                (state.task is not None and state.task.done())
                or ((current - state.created_at) > stuck_ttl)
            ):
                state.finalize()
                to_remove.append(run_id)

        for run_id in to_remove:
            self._runs.pop(run_id, None)
        return len(to_remove)

    def clear(self) -> None:
        self._runs.clear()


_REGISTRY: StreamRegistry | None = None


def get_stream_registry() -> StreamRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = StreamRegistry()
    return _REGISTRY


def sweep_interrupted_runs(session: Session) -> int:
    """Sweep runs and messages left in 'streaming' state at process start."""
    runs = session.scalars(select(Run).where(Run.status == "streaming")).all()
    count = len(runs)
    for run in runs:
        run.status = "interrupted"
        run.finish_reason = FinishReason.INTERRUPTED.value
        reservations = session.scalars(
            select(BudgetReservation).where(
                BudgetReservation.account_id == run.account_id,
                BudgetReservation.logical_request_id == run.logical_request_id,
                BudgetReservation.status == ReservationStatus.RESERVED,
            )
        ).all()
        for reservation in reservations:
            release_budget(session, reservation)
    messages = session.scalars(
        select(ChatMessage).where(ChatMessage.status == MessageStatus.STREAMING.value)
    ).all()
    for msg in messages:
        msg.status = MessageStatus.INTERRUPTED.value
        msg.finish_reason = FinishReason.INTERRUPTED.value

    session.commit()
    return count
