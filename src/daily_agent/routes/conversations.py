from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from daily_agent.conversations.service import (
    get_conversation,
    list_conversations,
    list_messages,
    message_counts,
    restore,
    search_conversations,
    soft_delete,
    to_conversation_view,
    to_message_view,
    update_conversation,
)
from daily_agent.db import get_session
from daily_agent.deps import limited_principal
from daily_agent.schemas_chat import (
    ConversationPage,
    ConversationSearchResult,
    ConversationUpdate,
    ConversationView,
    MessagePage,
)
from daily_agent.security import Principal

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


@router.get("", response_model=ConversationPage)
def list_conversations_endpoint(
    archived: bool = Query(default=False),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> ConversationPage:
    try:
        convs, next_cursor = list_conversations(
            session=session,
            principal=principal,
            archived=archived,
            cursor=cursor,
            limit=limit,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid cursor: {err}",
        ) from err
    counts = message_counts(session, [c.id for c in convs])
    items = [to_conversation_view(c, counts.get(c.id, 0)) for c in convs]
    return ConversationPage(items=items, nextCursor=next_cursor)


@router.get("/search", response_model=list[ConversationSearchResult])
def search_conversations_endpoint(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> list[ConversationSearchResult]:
    clean_q = q.strip()
    if not clean_q or len(clean_q) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="query must be between 1 and 200 characters",
        )
    return search_conversations(
        session=session,
        principal=principal,
        q=clean_q,
        limit=limit,
    )


@router.get("/{conversation_id}", response_model=ConversationView)
def get_conversation_endpoint(
    conversation_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> ConversationView:
    conv = get_conversation(session=session, principal=principal, id=conversation_id)
    counts = message_counts(session, [conv.id])
    return to_conversation_view(conv, counts.get(conv.id, 0))


@router.get("/{conversation_id}/messages", response_model=MessagePage)
def list_messages_endpoint(
    conversation_id: str,
    before: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> MessagePage:
    msgs, has_more_before = list_messages(
        session=session,
        principal=principal,
        conversation_id=conversation_id,
        before=before,
        limit=limit,
    )
    items = [to_message_view(m) for m in msgs]
    return MessagePage(items=items, hasMoreBefore=has_more_before)


@router.patch("/{conversation_id}", response_model=ConversationView)
def update_conversation_endpoint(
    conversation_id: str,
    body: ConversationUpdate,
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> ConversationView:
    conv = update_conversation(
        session=session,
        principal=principal,
        id=conversation_id,
        update=body,
    )
    session.commit()
    counts = message_counts(session, [conv.id])
    return to_conversation_view(conv, counts.get(conv.id, 0))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_endpoint(
    conversation_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> Response:
    soft_delete(session=session, principal=principal, id=conversation_id)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/restore", response_model=ConversationView)
def restore_conversation_endpoint(
    conversation_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(limited_principal),
) -> ConversationView:
    conv = restore(session=session, principal=principal, id=conversation_id)
    session.commit()
    counts = message_counts(session, [conv.id])
    return to_conversation_view(conv, counts.get(conv.id, 0))
