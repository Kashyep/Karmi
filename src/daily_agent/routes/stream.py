"""Streaming chat endpoints: SSE streaming, resume, stop, continue and regenerate."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.config import Settings, get_settings
from daily_agent.conversations.service import ensure_conversation_for_message, touch_conversation
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
    policy_for,
    reserve_budget,
)
from daily_agent.streaming.registry import RunState, StreamEvent, get_stream_registry
from daily_agent.streaming.runner import start_stream_run
from daily_agent.streaming.sse import SSE_HEADERS, encode_sse_event

logger = logging.getLogger(__name__)

router = APIRouter()

IST = timedelta(hours=5, minutes=30)


def _capacity_full_message(reset_at: datetime) -> str:
    ist = (reset_at.astimezone(UTC) + IST).strftime("%H:%M")
    utc = reset_at.astimezone(UTC).strftime("%H:%M")
    return (
        f"Beta capacity full; resets at {ist} IST ({utc} UTC). Upgrade to Parth or try later."
    )


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
                if evt.event == "run.started":
                    if after_seq < 0:
                        yield encode_sse_event(evt.event, evt.data, event_id=evt.seq)
                elif evt.event == "message.delta":
                    if evt.seq is not None and evt.seq > after_seq:
                        yield encode_sse_event(evt.event, evt.data, event_id=evt.seq)
                elif evt.event in ("run.finished", "run.error"):
                    yield encode_sse_event(evt.event, evt.data, event_id=evt.seq)
                elif evt.event == "heartbeat" and not catching_up:
                    yield encode_sse_event(evt.event, evt.data)

            if is_terminal and cursor >= len(run_state.events):
                break
    except asyncio.CancelledError:
        # Client disconnected: generator cancels, but background task in StreamRegistry keeps running
        return


async def _replay_from_db(
    user_msg: ChatMessage,
    assistant_msg: ChatMessage | None,
    run: Run | None,
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
        yield encode_sse_event(
            "run.finished",
            {
                "finish_reason": finish_reason,
                "outcome": outcome,
                "assistant_message_id": assistant_id,
            },
        )


@router.post("/v1/chat/stream")
async def chat_stream(
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
        assistant_msg = session.scalars(
            select(ChatMessage)
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .where(
                ChatMessage.parent_message_id == existing_user_msg.id,
                ChatMessage.account_id == principal.account_id,
                Conversation.user_id == principal.user_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(ChatMessage.variant_index.desc())
        ).first()
        run_id = existing_user_msg.run_id or (assistant_msg.run_id if assistant_msg else None)
        if run_id:
            registry = get_stream_registry()
            run_state = registry.get(run_id)
            if run_state is not None:
                return StreamingResponse(
                    stream_run_events(run_state, after_seq=-1),
                    media_type="text/event-stream",
                    headers=SSE_HEADERS,
                )
            run = session.scalar(
                select(Run).where(
                    Run.id == run_id,
                    Run.account_id == principal.account_id,
                    Run.user_id == principal.user_id,
                )
            )
            return StreamingResponse(
                _replay_from_db(existing_user_msg, assistant_msg, run),
                media_type="text/event-stream",
                headers=SSE_HEADERS,
            )

    # 2. Get or create conversation (first message creates it; no empty records)
    conv = ensure_conversation_for_message(
        session, principal, body.conversation_id, body.text, utcnow()
    )

    # 3. Budget reservation & admission pre-stream
    _subscription, policy = policy_for(session, principal.account_id)
    amount = estimate_request_cost_micro(policy, settings)
    token_hold = (
        max(1, len(body.text.encode("utf-8")) // 4) + policy.output_tokens
        if gateway.live
        else 0
    )
    run_id = uuid_str()
    logical_request_id = f"stream:{conv.id}:{body.client_message_id}"
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
            detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": exc.reset_at.isoformat()},
        ) from exc
    except ReservationInFlight as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "STREAM_IN_FLIGHT", "message": "stream generation already in flight"},
        ) from exc

    # 4. Create user message, assistant message, and Run in one transaction
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
    )
    conv.last_message_at = utcnow()
    session.add_all([user_msg, assistant_msg, run])
    session.commit()

    # 5. Initialize RunState & register in StreamRegistry
    run_state = RunState(
        run_id=run_id,
        conversation_id=conv.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
    )
    registry = get_stream_registry()
    registry.register(run_state)

    # 6. Start background runner
    engine = session.get_bind()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    start_kwargs: dict[str, Any] = {
        "run_state": run_state,
        "plan": policy,
        "text": body.text,
        "task_type": classify_task(body.text),
        "max_output_tokens": policy.output_tokens,
        "gateway": gateway,
        "settings": settings,
        "session_factory": session_factory,
        "reservation_id": reservation.id,
    }
    if "admission" in inspect.signature(start_stream_run).parameters:
        start_kwargs["admission"] = admission
    start_stream_run(**start_kwargs)

    return StreamingResponse(
        stream_run_events(run_state, after_seq=-1),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/v1/runs/{run_id}/events")
async def run_events(
    run_id: str,
    after_seq: int = Query(-1, alias="after_seq"),
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    own_run(session, principal, run_id)
    logger.info("stream.resumed run_id=%s after_seq=%s", run_id, after_seq)

    registry = get_stream_registry()
    run_state = registry.get(run_id)
    if run_state is None or after_seq > run_state.last_seq:
        assistant_msg = session.scalar(
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
        assistant_id = assistant_msg.id if assistant_msg else (run_state.assistant_message_id if run_state else None)

        async def _resume_unavailable() -> AsyncIterator[str]:
            yield encode_sse_event(
                "run.error",
                {
                    "category": ErrorCategory.RESUME_UNAVAILABLE.value,
                    "retryable": False,
                    "assistant_message_id": assistant_id,
                },
            )

        return StreamingResponse(
            _resume_unavailable(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return StreamingResponse(
        stream_run_events(run_state, after_seq=after_seq),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/v1/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_run(
    run_id: str,
    principal: Principal = Depends(limited_principal),
    session: Session = Depends(get_session),
) -> StopResponse:
    run = own_run(session, principal, run_id)
    registry = get_stream_registry()
    run_state = registry.get(run_id)
    if run_state is not None:
        run_state.stop()
    else:
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
async def continue_message(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only assistant messages can be continued")
    if msg.status == MessageStatus.STREAMING.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot continue streaming message")
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parent user message not found")

    _subscription, policy = policy_for(session, principal.account_id)
    amount = estimate_request_cost_micro(policy, settings)
    token_hold = (
        max(1, len(user_msg.content.encode("utf-8")) // 4) + policy.output_tokens
        if gateway.live
        else 0
    )
    new_run_id = uuid_str()
    logical_request_id = f"stream:continue:{new_run_id}"
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
            detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": exc.reset_at.isoformat()},
        ) from exc

    msg.status = MessageStatus.STREAMING.value
    msg.finish_reason = None
    run = Run(
        id=new_run_id,
        account_id=principal.account_id,
        user_id=principal.user_id,
        logical_request_id=logical_request_id,
        status="streaming",
        continuation_of_run_id=msg.run_id,
        last_seq=0,
    )
    msg.run_id = new_run_id
    session.add(run)
    session.commit()

    run_state = RunState(
        run_id=new_run_id,
        conversation_id=msg.conversation_id,
        user_message_id=user_msg.id,
        assistant_message_id=msg.id,
    )
    registry = get_stream_registry()
    registry.register(run_state)

    engine = session.get_bind()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    start_kwargs: dict[str, Any] = {
        "run_state": run_state,
        "plan": policy,
        "text": user_msg.content,
        "task_type": classify_task(user_msg.content),
        "max_output_tokens": policy.output_tokens,
        "gateway": gateway,
        "settings": settings,
        "session_factory": session_factory,
        "reservation_id": reservation.id,
        "prior_content": msg.content,
    }
    if "admission" in inspect.signature(start_stream_run).parameters:
        start_kwargs["admission"] = admission
    start_stream_run(**start_kwargs)

    return StreamingResponse(
        stream_run_events(run_state, after_seq=-1),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/v1/messages/{assistant_message_id}/regenerate")
async def regenerate_message(
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="only assistant messages can be regenerated")
    if msg.status == MessageStatus.STREAMING.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cannot regenerate streaming message")

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="parent user message not found")

    max_variant = session.scalar(
        select(func.max(ChatMessage.variant_index)).where(
            ChatMessage.parent_message_id == user_msg.id
        )
    )
    variant_index = (max_variant if max_variant is not None else msg.variant_index) + 1

    _subscription, policy = policy_for(session, principal.account_id)
    amount = estimate_request_cost_micro(policy, settings)
    token_hold = (
        max(1, len(user_msg.content.encode("utf-8")) // 4) + policy.output_tokens
        if gateway.live
        else 0
    )
    new_run_id = uuid_str()
    logical_request_id = f"stream:regen:{new_run_id}"
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
            detail={"code": "ALLOWANCE_EXHAUSTED", "message": str(exc), "reset_at": exc.reset_at.isoformat()},
        ) from exc

    sibling_msg = ChatMessage(
        id=chat_message_id_str(),
        conversation_id=msg.conversation_id,
        account_id=principal.account_id,
        role="assistant",
        status=MessageStatus.STREAMING.value,
        content="",
        run_id=new_run_id,
        parent_message_id=user_msg.id,
        variant_index=variant_index,
    )
    run = Run(
        id=new_run_id,
        account_id=principal.account_id,
        user_id=principal.user_id,
        logical_request_id=logical_request_id,
        status="streaming",
        previous_run_id=msg.run_id,
        regenerate_reason="user_request",
        last_seq=0,
    )
    session.add_all([sibling_msg, run])
    session.commit()

    run_state = RunState(
        run_id=new_run_id,
        conversation_id=msg.conversation_id,
        user_message_id=user_msg.id,
        assistant_message_id=sibling_msg.id,
    )
    registry = get_stream_registry()
    registry.register(run_state)

    engine = session.get_bind()
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    start_kwargs: dict[str, Any] = {
        "run_state": run_state,
        "plan": policy,
        "text": user_msg.content,
        "task_type": classify_task(user_msg.content),
        "max_output_tokens": policy.output_tokens,
        "gateway": gateway,
        "settings": settings,
        "session_factory": session_factory,
        "reservation_id": reservation.id,
        "prior_content": None,
    }
    if "admission" in inspect.signature(start_stream_run).parameters:
        start_kwargs["admission"] = admission
    start_stream_run(**start_kwargs)

    return StreamingResponse(
        stream_run_events(run_state, after_seq=-1),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
