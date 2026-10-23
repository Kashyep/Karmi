"""Conversations service layer: persistence, lifecycle, pagination, and search."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from daily_agent.conversations.search import escape_like, make_snippet
from daily_agent.models import ChatMessage, Conversation, utcnow
from daily_agent.schemas_chat import (
    ChatMessageView,
    ConversationSearchResult,
    ConversationUpdate,
    ConversationView,
)
from daily_agent.security import Principal

logger = logging.getLogger(__name__)


def ensure_conversation_for_message(
    session: Session,
    principal: Principal,
    conversation_id: str | None,
    first_user_text: str,
    now: datetime,
) -> Conversation:
    """Ensure a conversation exists for a message.

    If conversation_id is None, creates a new Conversation with auto title
    (first 60 stripped chars), title_source='auto', flushes, and logs conversation.created.
    If conversation_id is provided, loads the user's non-deleted conversation or raises 404.
    Does not commit.
    """
    if conversation_id is None:
        title = first_user_text.strip()[:60]
        conv = Conversation(
            account_id=principal.account_id,
            user_id=principal.user_id,
            title=title,
            title_source="auto",
            pinned=False,
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        session.add(conv)
        session.flush()
        logger.info(
            "conversation.created",
            extra={
                "event": "conversation.created",
                "conversation_id": conv.id,
                "account_id": principal.account_id,
                "user_id": principal.user_id,
            },
        )
        return conv

    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.account_id == principal.account_id,
        Conversation.user_id == principal.user_id,
        Conversation.deleted_at.is_(None),
    )
    found = session.scalar(stmt)
    if found is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return found


def touch_conversation(conversation: Conversation, now: datetime) -> None:
    """Set conversation last_message_at and updated_at to now."""
    conversation.last_message_at = now
    conversation.updated_at = now


def to_conversation_view(conv: Conversation, message_count: int = 0) -> ConversationView:
    """Map Conversation ORM entity and message count to ConversationView schema."""
    return ConversationView(
        id=conv.id,
        title=conv.title,
        titleSource=conv.title_source,
        pinned=conv.pinned,
        archivedAt=conv.archived_at,
        updatedAt=conv.updated_at,
        lastMessageAt=conv.last_message_at,
        messageCount=message_count,
    )


def to_message_view(msg: ChatMessage) -> ChatMessageView:
    """Map ChatMessage ORM entity to ChatMessageView schema."""
    return ChatMessageView(
        id=msg.id,
        conversationId=msg.conversation_id,
        role=msg.role,
        status=msg.status,
        content=msg.content or "",
        finishReason=msg.finish_reason,
        runId=msg.run_id,
        parentMessageId=msg.parent_message_id,
        variantIndex=msg.variant_index,
        clientMessageId=msg.client_message_id,
        createdAt=msg.created_at,
        updatedAt=msg.updated_at,
    )


def encode_cursor(conv: Conversation) -> str:
    """Encode keyset cursor (pinned, updated_at ISO, id) into base64url string."""
    pinned_flag = 1 if conv.pinned else 0
    updated_at_iso = conv.updated_at.isoformat()
    raw = json.dumps([pinned_flag, updated_at_iso, conv.id], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[bool, datetime, str]:
    """Decode base64url keyset cursor into (pinned, updated_at, id).

    Raises ValueError on invalid cursor.
    """
    try:
        padding = 4 - (len(cursor) % 4)
        if padding != 4:
            cursor += "=" * padding
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) != 3:
            raise ValueError("invalid cursor structure")
        pinned_raw, updated_at_raw, id_raw = data
        if pinned_raw not in (0, 1, True, False):
            raise ValueError("invalid pinned in cursor")
        pinned = bool(pinned_raw)
        if not isinstance(updated_at_raw, str) or not isinstance(id_raw, str) or not id_raw:
            raise ValueError("invalid types in cursor")
        updated_at = datetime.fromisoformat(updated_at_raw)
        return pinned, updated_at, id_raw
    except Exception as exc:
        raise ValueError("invalid cursor") from exc


def message_counts(session: Session, conversation_ids: Sequence[str]) -> dict[str, int]:
    """Compute message counts for a collection of conversation IDs in a single grouped query."""
    ids = list(conversation_ids)
    if not ids:
        return {}
    stmt = (
        select(ChatMessage.conversation_id, func.count(ChatMessage.id))
        .where(ChatMessage.conversation_id.in_(ids))
        .group_by(ChatMessage.conversation_id)
    )
    rows = session.execute(stmt).all()
    counts = {cid: 0 for cid in ids}
    for cid, cnt in rows:
        counts[cid] = int(cnt)
    return counts


def list_conversations(
    session: Session,
    principal: Principal,
    archived: bool = False,
    cursor: str | None = None,
    limit: int = 20,
) -> tuple[list[Conversation], str | None]:
    """List conversations ordered by pinned DESC, updated_at DESC, id DESC with keyset pagination."""
    conditions = [
        Conversation.account_id == principal.account_id,
        Conversation.user_id == principal.user_id,
        Conversation.deleted_at.is_(None),
    ]
    if archived:
        conditions.append(Conversation.archived_at.is_not(None))
    else:
        conditions.append(Conversation.archived_at.is_(None))

    if cursor is not None:
        c_pinned, c_updated_at, c_id = decode_cursor(cursor)
        if c_pinned:
            cursor_cond = or_(
                Conversation.pinned.is_(False),
                and_(
                    Conversation.pinned.is_(True),
                    or_(
                        Conversation.updated_at < c_updated_at,
                        and_(
                            Conversation.updated_at == c_updated_at,
                            Conversation.id < c_id,
                        ),
                    ),
                ),
            )
        else:
            cursor_cond = and_(
                Conversation.pinned.is_(False),
                or_(
                    Conversation.updated_at < c_updated_at,
                    and_(
                        Conversation.updated_at == c_updated_at,
                        Conversation.id < c_id,
                    ),
                ),
            )
        conditions.append(cursor_cond)

    stmt = (
        select(Conversation)
        .where(*conditions)
        .order_by(
            Conversation.pinned.desc(),
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .limit(limit + 1)
    )
    items = list(session.scalars(stmt).all())
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        next_cursor = encode_cursor(items[-1])

    return items, next_cursor


def get_conversation(session: Session, principal: Principal, id: str) -> Conversation:
    """Fetch an owned non-deleted conversation by id, raising 404 HTTPException if missing."""
    stmt = select(Conversation).where(
        Conversation.id == id,
        Conversation.account_id == principal.account_id,
        Conversation.user_id == principal.user_id,
        Conversation.deleted_at.is_(None),
    )
    conv = session.scalar(stmt)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


def list_messages(
    session: Session,
    principal: Principal,
    conversation_id: str,
    before: str | None = None,
    limit: int = 50,
) -> tuple[list[ChatMessage], bool]:
    """List messages for a conversation ordered oldest to newest.

    Raises 404 if conversation is missing/deleted/not owned.
    Raises 404 if before message id is not in this conversation.
    Returns (messages, has_more_before).
    """
    conv_stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.account_id == principal.account_id,
        Conversation.user_id == principal.user_id,
        Conversation.deleted_at.is_(None),
    )
    if session.scalar(conv_stmt) is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    conditions = [
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.account_id == principal.account_id,
    ]

    if before is not None:
        before_stmt = select(ChatMessage).where(
            ChatMessage.id == before,
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.account_id == principal.account_id,
        )
        before_msg = session.scalar(before_stmt)
        if before_msg is None:
            raise HTTPException(status_code=404, detail="message not found")
        conditions.append(
            or_(
                ChatMessage.created_at < before_msg.created_at,
                and_(
                    ChatMessage.created_at == before_msg.created_at,
                    ChatMessage.id < before_msg.id,
                ),
            )
        )

    stmt = (
        select(ChatMessage)
        .where(*conditions)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit + 1)
    )
    rows = list(session.scalars(stmt).all())
    has_more_before = len(rows) > limit
    if has_more_before:
        rows = rows[:limit]
    rows.reverse()
    return rows, has_more_before


def update_conversation(
    session: Session,
    principal: Principal,
    id: str,
    update: ConversationUpdate,
) -> Conversation:
    """Update conversation fields.

    Setting title sets title_source='user'.
    archived=True sets archived_at=now, archived=False clears it.
    Does not commit; flushes changes.
    """
    conv = get_conversation(session, principal, id)
    now = utcnow()
    if update.title is not None:
        conv.title = update.title
        conv.title_source = "user"
    if update.pinned is not None:
        conv.pinned = update.pinned
    if update.archived is not None:
        if update.archived:
            if conv.archived_at is None:
                conv.archived_at = now
        else:
            conv.archived_at = None
    conv.updated_at = now
    session.flush()
    return conv


def soft_delete(session: Session, principal: Principal, id: str) -> None:
    """Soft delete conversation setting deleted_at=now.

    Raises 404 if not owned or already deleted.
    """
    conv = get_conversation(session, principal, id)
    now = utcnow()
    conv.deleted_at = now
    conv.updated_at = now
    session.flush()


def restore(session: Session, principal: Principal, id: str) -> Conversation:
    """Restore a soft-deleted conversation owned by caller.

    Clears deleted_at; raises 404 if not owned or not soft-deleted.
    """
    stmt = select(Conversation).where(
        Conversation.id == id,
        Conversation.account_id == principal.account_id,
        Conversation.user_id == principal.user_id,
        Conversation.deleted_at.is_not(None),
    )
    conv = session.scalar(stmt)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    conv.deleted_at = None
    conv.updated_at = utcnow()
    session.flush()
    return conv


def search_conversations(
    session: Session,
    principal: Principal,
    q: str,
    limit: int = 20,
) -> list[ConversationSearchResult]:
    """Search owned non-deleted conversations by title and message content substring.

    Matches case-insensitively with backslash escaping for %, _, and backslash.
    Returns ConversationSearchResult list ordered updated_at DESC.
    """
    term = q.strip()
    if not term:
        return []

    escaped = escape_like(term)
    pattern = f"%{escaped}%"

    msg_subquery = (
        select(ChatMessage.conversation_id)
        .where(
            ChatMessage.account_id == principal.account_id,
            ChatMessage.content.ilike(pattern, escape="\\"),
        )
    )

    conv_stmt = (
        select(Conversation)
        .where(
            Conversation.account_id == principal.account_id,
            Conversation.user_id == principal.user_id,
            Conversation.deleted_at.is_(None),
            or_(
                Conversation.title.ilike(pattern, escape="\\"),
                Conversation.id.in_(msg_subquery),
            ),
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    convs = list(session.scalars(conv_stmt).all())
    if not convs:
        logger.info(
            "conversation.searched",
            extra={
                "event": "conversation.searched",
                "result_count": 0,
                "account_id": principal.account_id,
                "user_id": principal.user_id,
            },
        )
        return []

    counts = message_counts(session, [c.id for c in convs])
    results: list[ConversationSearchResult] = []

    for conv in convs:
        if conv.title and term.lower() in conv.title.lower():
            matched: Literal["title", "content"] = "title"
            snippet = conv.title
        else:
            matched = "content"
            first_msg_stmt = (
                select(ChatMessage)
                .where(
                    ChatMessage.conversation_id == conv.id,
                    ChatMessage.account_id == principal.account_id,
                    ChatMessage.content.ilike(pattern, escape="\\"),
                )
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .limit(1)
            )
            first_msg = session.scalar(first_msg_stmt)
            snippet = make_snippet(first_msg.content, term) if first_msg else conv.title or ""

        conv_view = to_conversation_view(conv, message_count=counts.get(conv.id, 0))
        results.append(
            ConversationSearchResult(
                conversation=conv_view,
                snippet=snippet,
                matched=matched,
            )
        )

    logger.info(
        "conversation.searched",
        extra={
            "event": "conversation.searched",
            "result_count": len(results),
            "account_id": principal.account_id,
            "user_id": principal.user_id,
        },
    )
    return results
