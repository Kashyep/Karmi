"""Streaming chat endpoints: SSE streaming, resume, stop, continue and regenerate.

Handlers that touch the synchronous SQLAlchemy session are plain ``def`` so FastAPI runs them
in the threadpool and they never block the event loop. Work that must run on the loop (task
creation, Redis awaits) is bridged back with ``anyio.from_thread``.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.config import Settings, get_settings
from daily_agent.conversations.service import (
    ensure_conversation_for_message,
    list_messages,
    touch_conversation,
)
from daily_agent.db import get_session
from daily_agent.deps import gateway_dependency, limited_principal, own_run
from daily_agent.gateway.router import classify_task
from daily_agent.gateway.service import Gateway
from daily_agent.models import (
    ChatMessage,
    Conversation,
    Run,
    RunStatus,
    chat_message_id_str,
    utcnow,
    uuid_str,
)
from daily_agent.plans import PlanPolicy
from daily_agent.schemas_chat import (
    ChatStreamRequest,
    ErrorCategory,
    FinishReason,
    MessageStatus,
    StopResponse,
)
from daily_agent.security import Principal
from daily_agent.services import (
    BudgetDenied,
    GatewayAdmission,
    GatewayCapacityFull,
    ReservationInFlight,
    admit_gateway_requests,
    estimate_request_cost_micro,
    history_from_messages,
    history_tokens,
    policy_for,
    reserve_budget,
    run_debug_view,
    trim_history,
)
from daily_agent.streaming.registry import RunState, StreamEvent, get_stream_registry
from daily_agent.streaming.runner import start_stream_run
from daily_agent.streaming.sse import SSE_HEADERS, encode_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

IST = timedelta(hours=5, minutes=30)

# Rough chars-per-token used for the input size estimate and the token hold.
_CHARS_PER_TOKEN = 4


def _capacity_full_message(reset_at: datetime) -> str:
    ist = (reset_at.astimezone(UTC) + IST).strftime("%H:%M")
    utc = reset_at.astimezone(UTC).strftime("%H:%M")
    return f"Beta capacity full; resets at {ist} IST ({utc} UTC). Upgrade to Parth or try later."


def _sse(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(events, media_type="text/event-stream", headers=SSE_HEADERS)


def _in_flight_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "STREAM_IN_FLIGHT", "message": "stream generation already in flight"},
    )


def _enforce_input_budget(text: str, policy: PlanPolicy) -> None:
    """Reject a message that cannot fit the plan's input budget, before any reservation."""
    estimated = len(text.encode("utf-8")) // _CHARS_PER_TOKEN
    if estimated > policy.input_tokens:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "INPUT_TOO_LARGE",
                "message": (
                    f"message is too large for this plan ({estimated} estimated input tokens; "
                    f"limit {policy.input_tokens})"
                ),
                "max_input_tokens": policy.input_tokens,
            },
        )


def _continue_key(assistant_message_id: str, previous_run_id: str | None) -> str:
    return f"stream:continue:{assistant_message_id}:{previous_run_id or 'none'}"


def _regen_key(user_message_id: str, variant_index: int) -> str:
    return f"stream:regen:{user_message_id}:{variant_index}"


def _resume_frame(evt: StreamEvent, after_seq: int, catching_up: bool) -> str | None:
    if evt.event == "run.started":
        if after_seq < 0:
            return encode_sse_event(evt.event, evt.data, event_id=evt.seq)
        return None
    if evt.event == "message.delta":
        if evt.seq is not None and evt.seq > after_seq:
            return encode_sse_event(evt.event, evt.data, event_id=evt.seq)
        return None
    if evt.event in ("run.finished", "run.error"):
        return encode_sse_event(evt.event, evt.data, event_id=evt.seq)
    if evt.event == "heartbeat" and not catching_up:
        return encode_sse_event(evt.event, evt.data)
    return None


async def stream_run_events(run_state: RunState, after_seq: int = -1) -> AsyncIterator[str]:
    cursor = 0
    catching_up = after_seq >= 0
    try:
        while True:
            async with run_state.condition:
                while cursor >= len(run_state.events) and not run_state.terminal:
                    catching_up = False
                    await run_state.condition.wait()
                new_events: list[StreamEvent] = list(run_state.events[cursor:])
                cursor = len(run_state.events)
                is_terminal = run_state.terminal

            for evt in new_events:
                frame = _resume_frame(evt, after_seq, catching_up)
                if frame is not None:
                    yield frame

            if is_terminal and cursor >= len(run_state.events):
                break
    except asyncio.CancelledError:
        # Client disconnected: generator cancels, but the background task in StreamRegistry
        # keeps running
        return


async def _redis_resume_events(run_id: str, after_seq: int) -> AsyncIterator[str]:
    """Stream a run owned by another worker by tailing its Redis event mirror."""
    from daily_agent.streaming.redis_state import tail_events

    catching_up = after_seq >= 0
    try:
        async for evt in tail_events(run_id, after_seq):
            frame = _resume_frame(evt, after_seq, catching_up)
            if evt.seq is not None and evt.seq > after_seq:
                catching_up = False
            if frame is not None:
                yield frame
    except asyncio.CancelledError:
        return


async def _redis_run_live(run_id: str) -> bool:
    from daily_agent.streaming.redis_state import run_is_live

    return await run_is_live(run_id)


async def _replay_from_db(
    user_msg: ChatMessage,
    assistant_msg: ChatMessage | None,
    run: Run | None,
    *,
    debug_enabled: bool = False,
) -> AsyncIterator[str]:
    run_id = (run.id if run else None) or user_msg.run_id or "run_unknown"
    assistant_id = assistant_msg.id if assistant_msg else "msg_unknown"
    yield encode_sse_event(
        "run.started",
        {
            "run_id": run_id,
            "conversation_id": user_msg.conversation_id,
            "user_message_id": user_msg.id,
            "assistant_message_id": assistant_id,
            "seq": 0,
        },
        event_id=0,
    )
    text = (run.response_text if run else None) or (assistant_msg.content if assistant_msg else "")
    if text:
        yield encode_sse_event(
            "message.delta",
            {"text": text},
            event_id=1,
        )
    if run and run.status == RunStatus.FAILED:
        yield encode_sse_event(
            "run.error",
            {
                "category": ErrorCategory.INTERNAL.value,
                "retryable": True,
                "assistant_message_id": assistant_id,
            },
        )
    else:
        finish_reason = (
            (run.finish_reason if run else None)
            or (assistant_msg.finish_reason if assistant_msg else None)
            or FinishReason.STOP.value
        )
        outcome = (run.outcome if run else None) or "COMPLETED"
        finished: dict[str, Any] = {
            "finish_reason": finish_reason,
            "outcome": outcome,
            "assistant_message_id": assistant_id,
        }
        if debug_enabled and run is not None:
            finished["debug"] = run_debug_view(run).model_dump()
        yield encode_sse_event("run.finished", finished)


def _replay_response(
    run_id: str,
    user_msg: ChatMessage,
    assistant_msg: ChatMessage | None,
    run: Run | None,
    *,
    debug_enabled: bool,
) -> StreamingResponse:
    """Replay a run: local registry first, then Redis if another worker owns it live."""
    run_state = get_stream_registry().get(run_id)
    if run_state is not None:
        return _sse(stream_run_events(run_state, after_seq=-1))
    if anyio.from_thread.run(_redis_run_live, run_id):
        return _sse(_redis_resume_events(run_id, -1))
    return _sse(_replay_from_db(user_msg, assistant_msg, run, debug_enabled=debug_enabled))


def _assistant_for_run(session: Session, principal: Principal, run_id: str) -> ChatMessage | None:
    return session.scalar(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.run_id == run_id,
            ChatMessage.role == "assistant",
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(ChatMessage.variant_index.desc())
    )


def _assistant_for_user_turn(
    session: Session, principal: Principal, user_msg: ChatMessage
) -> ChatMessage | None:
    return session.scalars(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.parent_message_id == user_msg.id,
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(ChatMessage.variant_index.desc())
    ).first()


def _find_run_by_key(session: Session, principal: Principal, logical_request_id: str) -> Run | None:
    return session.scalar(
        select(Run).where(
            Run.account_id == principal.account_id,
            Run.logical_request_id == logical_request_id,
        )
    )


def _reserve_and_admit(
    session: Session,
    *,
    principal: Principal,
    settings: Settings,
    gateway: Gateway,
    policy: PlanPolicy,
    logical_request_id: str,
    history_tokens_used: int,
    text: str,
) -> tuple[str, GatewayAdmission | None]:
    """Reserve budget and gateway admission; maps refusals to HTTP errors and rolls back."""
    amount = estimate_request_cost_micro(policy, settings)
    token_hold = (
        max(1, len(text.encode("utf-8")) // _CHARS_PER_TOKEN + history_tokens_used)
        + policy.output_tokens
        if gateway.live
        else 0
    )
    admission: GatewayAdmission | None = None
    try:
        reservation = reserve_budget(
            session,
            settings=settings,
            account_id=principal.account_id,
            logical_request_id=logical_request_id,
            stage="execution",
            amount_micro=amount,
            tokens=token_hold,
        )
        if gateway.live:
            admission = admit_gateway_requests(
                session, settings, paid=policy.price_inr > 0, slots=2
            )
    except GatewayCapacityFull as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "BETA_CAPACITY_FULL",
                "message": _capacity_full_message(exc.reset_at),
                "reset_at": exc.reset_at.isoformat(),
            },
        ) from exc
    except BudgetDenied as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "ALLOWANCE_EXHAUSTED",
                "message": str(exc),
                "reset_at": exc.reset_at.isoformat(),
            },
        ) from exc
    except ReservationInFlight as exc:
        session.rollback()
        raise _in_flight_conflict() from exc
    return reservation.id, admission


def _history_for(
    session: Session,
    principal: Principal,
    conversation_id: str,
    *,
    before: str | None,
    text: str,
    policy: PlanPolicy,
) -> tuple[tuple[dict[str, str], ...], int]:
    prior_msgs, _ = list_messages(session, principal, conversation_id, before=before, limit=50)
    trimmed_turns = trim_history(history_from_messages(prior_msgs), text=text, plan=policy)
    payload = tuple({"role": t.role, "content": t.content} for t in trimmed_turns)
    return payload, history_tokens(trimmed_turns)


def _commit_or_duplicate(session: Session) -> None:
    """Commit a new run's rows. A lost unique-key race becomes a 409, not a 500."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise _in_flight_conflict() from exc


def _launch_run(
    session: Session,
    *,
    run_state: RunState,
    policy: PlanPolicy,
    text: str,
    gateway: Gateway,
    settings: Settings,
    reservation_id: str,
    admission: GatewayAdmission | None,
    history: tuple[dict[str, str], ...],
    debug_enabled: bool,
    prior_content: str | None = None,
) -> StreamingResponse:
    session_factory = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    start_kwargs: dict[str, Any] = {
        "run_state": run_state,
        "plan": policy,
        "text": text,
        "task_type": classify_task(text),
        "max_output_tokens": policy.output_tokens,
        "gateway": gateway,
        "settings": settings,
        "session_factory": session_factory,
        "reservation_id": reservation_id,
        "debug_enabled": debug_enabled,
        "prior_content": prior_content,
        "history": history,
    }
    if "admission" in inspect.signature(start_stream_run).parameters:
        start_kwargs["admission"] = admission

    def _register_and_start() -> None:
        # Task creation needs the event loop, so this runs on the loop thread.
        get_stream_registry().register(run_state)
        start_stream_run(**start_kwargs)

    anyio.from_thread.run_sync(_register_and_start)
    return _sse(stream_run_events(run_state, after_seq=-1))


@router.post("/v1/chat/stream")
def chat_stream(
    body: ChatStreamRequest,
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: Gateway = Depends(gateway_dependency),
) -> StreamingResponse:
    # 1. Idempotency check on (conversation_id, client_message_id)
    if body.conversation_id:
        conv = session.scalar(
            select(Conversation).where(
                Conversation.id == body.conversation_id,
                Conversation.account_id == principal.account_id,
                Conversation.user_id == principal.user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="conversation not found",
            )
        existing_user_msg = session.scalars(
            select(ChatMessage)
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .where(
                ChatMessage.conversation_id == body.conversation_id,
                ChatMessage.client_message_id == body.client_message_id,
                ChatMessage.account_id == principal.account_id,
                Conversation.user_id == principal.user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(ChatMessage.created_at.desc())
        ).first()
    else:
        existing_user_msg = session.scalars(
            select(ChatMessage)
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .where(
                ChatMessage.client_message_id == body.client_message_id,
                ChatMessage.account_id == principal.account_id,
                Conversation.user_id == principal.user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(ChatMessage.created_at.desc())
        ).first()

    if existing_user_msg is not None:
        # Replay the existing run
        assistant_msg = _assistant_for_user_turn(session, principal, existing_user_msg)
        run_id = existing_user_msg.run_id or (assistant_msg.run_id if assistant_msg else None)
        if run_id:
            run = session.scalar(
                select(Run).where(
                    Run.id == run_id,
                    Run.account_id == principal.account_id,
                    Run.user_id == principal.user_id,
                )
            )
            return _replay_response(
                run_id,
                existing_user_msg,
                assistant_msg,
                run,
                debug_enabled=principal.tester,
            )

    # 2. The plan's input budget is checked before any row is created, so an oversize
    #    message never leaves a conversation or reservation behind.
    _subscription, policy = policy_for(session, principal.account_id)
    _enforce_input_budget(body.text, policy)

    # 3. Get or create conversation (first message creates it; no empty records)
    conv = ensure_conversation_for_message(
        session, principal, body.conversation_id, body.text, utcnow()
    )

    # 4. Budget reservation & admission pre-stream
    history_payload, history_used = _history_for(
        session, principal, conv.id, before=None, text=body.text, policy=policy
    )
    run_id = uuid_str()
    logical_request_id = f"stream:{conv.id}:{body.client_message_id}"
    reservation_id, admission = _reserve_and_admit(
        session,
        principal=principal,
        settings=settings,
        gateway=gateway,
        policy=policy,
        logical_request_id=logical_request_id,
        history_tokens_used=history_used,
        text=body.text,
    )

    # 5. Create user message, assistant message, and Run in one transaction
    user_msg = ChatMessage(
        id=chat_message_id_str(),
        conversation_id=conv.id,
        account_id=principal.account_id,
        role="user",
        status="complete",
        content=body.text,
        client_message_id=body.client_message_id,
        run_id=run_id,
    )
    assistant_msg = ChatMessage(
        id=chat_message_id_str(),
        conversation_id=conv.id,
        account_id=principal.account_id,
        role="assistant",
        status=MessageStatus.STREAMING.value,
        content="",
        run_id=run_id,
        parent_message_id=user_msg.id,
        variant_index=0,
    )
    run = Run(
        id=run_id,
        account_id=principal.account_id,
        user_id=principal.user_id,
        logical_request_id=logical_request_id,
        status="streaming",
        last_seq=0,
        heartbeat_at=utcnow(),
    )
    conv.last_message_at = utcnow()
    session.add_all([user_msg, assistant_msg, run])
    _commit_or_duplicate(session)

    # 6. Initialize RunState and start the background runner
    run_state = RunState(
        run_id=run_id,
        conversation_id=conv.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
    )
    return _launch_run(
        session,
        run_state=run_state,
        policy=policy,
        text=body.text,
        gateway=gateway,
        settings=settings,
        reservation_id=reservation_id,
        admission=admission,
        history=history_payload,
        debug_enabled=principal.tester,
    )


@router.get("/v1/runs/{run_id}/events")
def run_events(
    run_id: str,
    after_seq: int = Query(-1, alias="after_seq"),
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    own_run(session, principal, run_id)
    logger.info("stream.resumed run_id=%s after_seq=%s", run_id, after_seq)

    run_state = get_stream_registry().get(run_id)
    if run_state is not None and after_seq <= run_state.last_seq:
        return _sse(stream_run_events(run_state, after_seq=after_seq))
    if run_state is None and anyio.from_thread.run(_redis_run_live, run_id):
        return _sse(_redis_resume_events(run_id, after_seq))

    assistant_msg = _assistant_for_run(session, principal, run_id)
    assistant_id = (
        assistant_msg.id
        if assistant_msg
        else (run_state.assistant_message_id if run_state else None)
    )

    async def _resume_unavailable() -> AsyncIterator[str]:
        yield encode_sse_event(
            "run.error",
            {
                "category": ErrorCategory.RESUME_UNAVAILABLE.value,
                "retryable": False,
                "assistant_message_id": assistant_id,
            },
        )

    return _sse(_resume_unavailable())


@router.post("/v1/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
def stop_run(
    run_id: str,
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
) -> StopResponse:
    from daily_agent.streaming.redis_state import request_stop

    run = own_run(session, principal, run_id)
    run_state = get_stream_registry().get(run_id)
    if run_state is not None:
        run_state.stop()
    else:
        if anyio.from_thread.run(request_stop, run_id):
            # The owning worker observes the stop flag and finalizes the run itself.
            logger.info("stream.stop_forwarded run_id=%s", run_id)
            return StopResponse(status="cancelled")
        if run.status == "streaming":
            run.status = "completed"
            run.finish_reason = FinishReason.CANCELLED.value
            run.outcome = "STOPPED"
            msg = session.scalar(
                select(ChatMessage)
                .join(Conversation, ChatMessage.conversation_id == Conversation.id)
                .where(
                    ChatMessage.run_id == run_id,
                    ChatMessage.role == "assistant",
                    ChatMessage.account_id == principal.account_id,
                    Conversation.user_id == principal.user_id,
                    Conversation.deleted_at.is_(None),
                )
            )
            if msg:
                msg.status = MessageStatus.STOPPED.value
                msg.finish_reason = FinishReason.CANCELLED.value
                conversation = session.get(Conversation, msg.conversation_id)
                if conversation is not None:
                    touch_conversation(conversation, utcnow())
            session.commit()
    logger.info("stream.stopped run_id=%s", run_id)
    return StopResponse(status="cancelled")


@router.post("/v1/messages/{assistant_message_id}/continue")
def continue_message(
    assistant_message_id: str,
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: Gateway = Depends(gateway_dependency),
) -> StreamingResponse:
    msg = session.scalar(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.id == assistant_message_id,
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    if msg.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only assistant messages can be continued",
        )
    user_msg = session.scalar(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.id == msg.parent_message_id,
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if user_msg is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="parent user message not found"
        )

    if msg.status == MessageStatus.STREAMING.value:
        # A concurrent continue already claimed this message. Replay its run if it is the
        # continuation this request would have created; otherwise the message is busy.
        inflight = session.scalar(
            select(Run).where(Run.id == msg.run_id, Run.account_id == principal.account_id)
        )
        if (
            inflight is not None
            and inflight.continuation_of_run_id is not None
            and inflight.logical_request_id
            == _continue_key(assistant_message_id, inflight.continuation_of_run_id)
        ):
            return _replay_response(
                inflight.id,
                user_msg,
                msg,
                inflight,
                debug_enabled=principal.tester,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cannot continue streaming message"
        )
    if msg.finish_reason not in (
        FinishReason.LENGTH.value,
        FinishReason.CANCELLED.value,
        FinishReason.INTERRUPTED.value,
        FinishReason.ERROR.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"cannot continue message with finish_reason={msg.finish_reason}",
        )

    _subscription, policy = policy_for(session, principal.account_id)
    _enforce_input_budget(user_msg.content, policy)

    previous_run_id = msg.run_id
    prior_content = msg.content
    conversation_id = msg.conversation_id
    user_text = user_msg.content
    user_message_id = user_msg.id
    history_payload, history_used = _history_for(
        session, principal, conversation_id, before=user_message_id, text=user_text, policy=policy
    )
    new_run_id = uuid_str()
    logical_request_id = _continue_key(assistant_message_id, previous_run_id)
    reservation_id, admission = _reserve_and_admit(
        session,
        principal=principal,
        settings=settings,
        gateway=gateway,
        policy=policy,
        logical_request_id=logical_request_id,
        history_tokens_used=history_used,
        text=user_text,
    )

    # Atomic claim: only one request can move the message from its previous run to a new
    # streaming run. A concurrent loser rolls back its reservation and gets a 409.
    run_match = (
        ChatMessage.run_id.is_(None)
        if previous_run_id is None
        else ChatMessage.run_id == previous_run_id
    )
    claim = session.execute(
        update(ChatMessage)
        .where(
            ChatMessage.id == assistant_message_id,
            run_match,
            ChatMessage.status != MessageStatus.STREAMING.value,
        )
        .values(
            status=MessageStatus.STREAMING.value,
            run_id=new_run_id,
            finish_reason=None,
        )
        .execution_options(synchronize_session=False)
    )
    if not (isinstance(claim, CursorResult) and claim.rowcount == 1):
        session.rollback()
        raise _in_flight_conflict()
    session.add(
        Run(
            id=new_run_id,
            account_id=principal.account_id,
            user_id=principal.user_id,
            logical_request_id=logical_request_id,
            status="streaming",
            continuation_of_run_id=previous_run_id,
            last_seq=0,
            heartbeat_at=utcnow(),
        )
    )
    _commit_or_duplicate(session)

    run_state = RunState(
        run_id=new_run_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
    )
    return _launch_run(
        session,
        run_state=run_state,
        policy=policy,
        text=user_text,
        gateway=gateway,
        settings=settings,
        reservation_id=reservation_id,
        admission=admission,
        history=history_payload,
        debug_enabled=principal.tester,
        prior_content=prior_content,
    )


@router.post("/v1/messages/{assistant_message_id}/regenerate")
def regenerate_message(
    assistant_message_id: str,
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    gateway: Gateway = Depends(gateway_dependency),
) -> StreamingResponse:
    msg = session.scalar(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.id == assistant_message_id,
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    if msg.role != "assistant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only assistant messages can be regenerated",
        )
    if msg.status == MessageStatus.STREAMING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cannot regenerate streaming message"
        )

    user_msg = session.scalar(
        select(ChatMessage)
        .join(Conversation, ChatMessage.conversation_id == Conversation.id)
        .where(
            ChatMessage.id == msg.parent_message_id,
            ChatMessage.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if user_msg is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="parent user message not found"
        )

    max_variant = session.scalar(
        select(func.max(ChatMessage.variant_index)).where(
            ChatMessage.parent_message_id == user_msg.id
        )
    )
    variant_index = (max_variant if max_variant is not None else msg.variant_index) + 1
    logical_request_id = _regen_key(user_msg.id, variant_index)

    # A regenerate for the same variant slot that already has a run (a concurrent or retried
    # request) replays that run instead of reserving budget twice.
    existing = _find_run_by_key(session, principal, logical_request_id)
    if existing is not None:
        sibling = _assistant_for_run(session, principal, existing.id)
        return _replay_response(
            existing.id,
            user_msg,
            sibling,
            existing,
            debug_enabled=principal.tester,
        )

    _subscription, policy = policy_for(session, principal.account_id)
    _enforce_input_budget(user_msg.content, policy)

    user_text = user_msg.content
    user_message_id = user_msg.id
    conversation_id = msg.conversation_id
    previous_run_id = msg.run_id
    history_payload, history_used = _history_for(
        session, principal, conversation_id, before=user_message_id, text=user_text, policy=policy
    )
    new_run_id = uuid_str()
    reservation_id, admission = _reserve_and_admit(
        session,
        principal=principal,
        settings=settings,
        gateway=gateway,
        policy=policy,
        logical_request_id=logical_request_id,
        history_tokens_used=history_used,
        text=user_text,
    )

    sibling_id = chat_message_id_str()
    session.add_all(
        [
            ChatMessage(
                id=sibling_id,
                conversation_id=conversation_id,
                account_id=principal.account_id,
                role="assistant",
                status=MessageStatus.STREAMING.value,
                content="",
                run_id=new_run_id,
                parent_message_id=user_message_id,
                variant_index=variant_index,
            ),
            Run(
                id=new_run_id,
                account_id=principal.account_id,
                user_id=principal.user_id,
                logical_request_id=logical_request_id,
                status="streaming",
                previous_run_id=previous_run_id,
                regenerate_reason="user_request",
                last_seq=0,
                heartbeat_at=utcnow(),
            ),
        ]
    )
    _commit_or_duplicate(session)

    run_state = RunState(
        run_id=new_run_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=sibling_id,
    )
    return _launch_run(
        session,
        run_state=run_state,
        policy=policy,
        text=user_text,
        gateway=gateway,
        settings=settings,
        reservation_id=reservation_id,
        admission=admission,
        history=history_payload,
        debug_enabled=principal.tester,
        prior_content=None,
    )
