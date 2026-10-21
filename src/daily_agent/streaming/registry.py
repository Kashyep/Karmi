"""In-process stream registry and run state management."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.models import ChatMessage, Run
from daily_agent.schemas_chat import FinishReason, MessageStatus


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

    async def publish(self, event: str, data: dict[str, Any], seq: int | None = None) -> None:
        async with self.condition:
            evt = StreamEvent(event=event, data=data, seq=seq)
            self.events.append(evt)
            if seq is not None and seq > self.last_seq:
                self.last_seq = seq
            if event == "message.delta" and "text" in data:
                self.partial_text += data["text"]
            if event in ("run.finished", "run.error"):
                self.terminal = True
                self.terminated_at = time.time()
                self.finish_reason = data.get("finish_reason") or data.get("category")
            self.condition.notify_all()

    def stop(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()


class StreamRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def register(self, run_state: RunState) -> None:
        self._runs[run_state.run_id] = run_state

    def get(self, run_id: str) -> RunState | None:
        self.evict_expired()
        return self._runs.get(run_id)

    def has(self, run_id: str) -> bool:
        self.evict_expired()
        return run_id in self._runs

    def evict_expired(self, ttl_seconds: float = 600.0, now: float | None = None) -> int:
        current = now if now is not None else time.time()
        to_remove = [
            run_id
            for run_id, state in self._runs.items()
            if state.terminal and state.terminated_at is not None and (current - state.terminated_at) > ttl_seconds
        ]
        for run_id in to_remove:
            del self._runs[run_id]
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

    messages = session.scalars(
        select(ChatMessage).where(ChatMessage.status == MessageStatus.STREAMING.value)
    ).all()
    for msg in messages:
        msg.status = MessageStatus.INTERRUPTED.value
        msg.finish_reason = FinishReason.INTERRUPTED.value

    session.commit()
    return count
