from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from daily_agent.conversations.service import (
    decode_cursor,
    encode_cursor,
    ensure_conversation_for_message,
    get_conversation,
    list_conversations,
    list_messages,
    message_counts,
    restore,
    search_conversations,
    soft_delete,
    to_conversation_view,
    to_message_view,
    touch_conversation,
    update_conversation,
)
from daily_agent.models import ChatMessage, Conversation, utcnow
from daily_agent.schemas_chat import ConversationUpdate
from daily_agent.security import Principal
from tests.conftest import create_identity


def test_no_conversation_row_before_first_message(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="User1")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)

        # Before calling ensure, zero conversation rows exist
        count_before = session.scalar(
            select(func.count(Conversation.id)).where(Conversation.user_id == principal.user_id)
        )
        assert count_before == 0

        now = utcnow()
        conv = ensure_conversation_for_message(session, principal, None, "Hello world", now)
        session.commit()

        assert conv.id is not None
        assert conv.title == "Hello world"
        assert conv.title_source == "auto"
        assert conv.pinned is False
        assert conv.account_id == principal.account_id
        assert conv.user_id == principal.user_id
        assert conv.last_message_at == now

        count_after = session.scalar(
            select(func.count(Conversation.id)).where(Conversation.user_id == principal.user_id)
        )
        assert count_after == 1


def test_auto_title_truncation_and_stripping(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="User2")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        # Whitespace stripping
        conv1 = ensure_conversation_for_message(
            session, principal, None, "   \n  Stripped greeting   \t ", now
        )
        assert conv1.title == "Stripped greeting"
        assert conv1.title_source == "auto"

        # Truncation to 60 characters
        long_text = "   " + "x" * 95 + "   "
        conv2 = ensure_conversation_for_message(session, principal, None, long_text, now)
        assert conv2.title == "x" * 60
        assert len(conv2.title) == 60
        assert conv2.title_source == "auto"
        session.commit()


def test_user_title_not_overwritten_by_ensure(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="User3")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv = ensure_conversation_for_message(session, principal, None, "Initial question", now)
        session.commit()

        # Set user title via PATCH
        update_conversation(session, principal, conv.id, ConversationUpdate(title="Custom User Title"))
        session.commit()

        # Ensure with conversation_id should never overwrite title
        same_conv = ensure_conversation_for_message(
            session, principal, conv.id, "A subsequent user query", now
        )
        assert same_conv.id == conv.id
        assert same_conv.title == "Custom User Title"
        assert same_conv.title_source == "user"


def test_patch_title_sets_title_source_user(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="User4")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv = ensure_conversation_for_message(session, principal, None, "Original auto title", now)
        assert conv.title_source == "auto"
        session.commit()

        updated = update_conversation(
            session, principal, conv.id, ConversationUpdate(title="Renamed by User")
        )
        assert updated.title == "Renamed by User"
        assert updated.title_source == "user"

        # Updating only pinned keeps title_source as user
        pinned_conv = update_conversation(session, principal, conv.id, ConversationUpdate(pinned=True))
        assert pinned_conv.pinned is True
        assert pinned_conv.title_source == "user"
        session.commit()


def test_soft_delete_hides_and_restore_reveals(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="User5")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv = ensure_conversation_for_message(session, principal, None, "To be deleted", now)
        session.commit()

        # Soft delete
        soft_delete(session, principal, conv.id)
        session.commit()

        # get_conversation raises 404
        with pytest.raises(HTTPException) as exc_info:
            get_conversation(session, principal, conv.id)
        assert exc_info.value.status_code == 404

        # list_conversations does not return deleted conversation
        items, _ = list_conversations(session, principal)
        assert conv.id not in [c.id for c in items]

        # repeat soft_delete raises 404
        with pytest.raises(HTTPException) as exc_info:
            soft_delete(session, principal, conv.id)
        assert exc_info.value.status_code == 404

        # restore reveals it
        restored = restore(session, principal, conv.id)
        assert restored.id == conv.id
        assert restored.deleted_at is None
        session.commit()

        fetched = get_conversation(session, principal, conv.id)
        assert fetched.id == conv.id

        items_after, _ = list_conversations(session, principal)
        assert conv.id in [c.id for c in items_after]

        # restore on already active conversation raises 404
        with pytest.raises(HTTPException) as exc_info:
            restore(session, principal, conv.id)
        assert exc_info.value.status_code == 404


def test_cross_user_access_raises_404(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account_a, user_a, _ = create_identity(session, settings, name="UserA")  # type: ignore[arg-type]
        account_b, user_b, _ = create_identity(session, settings, name="UserB")  # type: ignore[arg-type]
        principal_a = Principal(user_id=user_a.id, account_id=account_a.id, role=user_a.role)
        principal_b = Principal(user_id=user_b.id, account_id=account_b.id, role=user_b.role)
        now = utcnow()

        conv_a = ensure_conversation_for_message(session, principal_a, None, "User A Chat", now)
        session.commit()

        # User B cannot access User A's conversation
        with pytest.raises(HTTPException) as exc_info:
            get_conversation(session, principal_b, conv_a.id)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            update_conversation(session, principal_b, conv_a.id, ConversationUpdate(title="Attack"))
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            soft_delete(session, principal_b, conv_a.id)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            restore(session, principal_b, conv_a.id)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            list_messages(session, principal_b, conv_a.id)
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            ensure_conversation_for_message(session, principal_b, conv_a.id, "Hi", now)
        assert exc_info.value.status_code == 404

        b_list, _ = list_conversations(session, principal_b)
        assert conv_a.id not in [c.id for c in b_list]

        b_search = search_conversations(session, principal_b, "User A Chat")
        assert len(b_search) == 0


def test_search_escaping(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="SearchUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv_normal = ensure_conversation_for_message(session, principal, None, "Normal topic", now)
        conv_percent = ensure_conversation_for_message(
            session, principal, None, "Discount 100% off today", now
        )
        conv_underscore = ensure_conversation_for_message(
            session, principal, None, "Variable snake_case identifier", now
        )
        session.commit()

        # Searching for '%' should only match conversation with '%'
        results_percent = search_conversations(session, principal, "%")
        matching_ids = [r.conversation.id for r in results_percent]
        assert conv_percent.id in matching_ids
        assert conv_normal.id not in matching_ids
        assert conv_underscore.id not in matching_ids

        # Searching for '_' should only match conversation with '_'
        results_underscore = search_conversations(session, principal, "_")
        matching_ids_ = [r.conversation.id for r in results_underscore]
        assert conv_underscore.id in matching_ids_
        assert conv_normal.id not in matching_ids_
        assert conv_percent.id not in matching_ids_


def test_search_title_vs_content_matched_flag(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="SearchFlagUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        # Conv A: Title matches
        conv_a = ensure_conversation_for_message(session, principal, None, "Apple pie recipe", now)
        msg_a = ChatMessage(
            conversation_id=conv_a.id,
            account_id=principal.account_id,
            role="user",
            status="complete",
            content="Baking ingredients and instructions",
            created_at=now,
            updated_at=now,
        )
        session.add(msg_a)

        # Conv B: Only content matches
        conv_b = ensure_conversation_for_message(session, principal, None, "Dessert notes", now)
        msg_b = ChatMessage(
            conversation_id=conv_b.id,
            account_id=principal.account_id,
            role="assistant",
            status="complete",
            content="For dinner we ordered a delicious fresh Apple dessert from the bakery.",
            created_at=now,
            updated_at=now,
        )
        session.add(msg_b)
        session.commit()

        results = search_conversations(session, principal, "apple")
        assert len(results) == 2

        by_id = {r.conversation.id: r for r in results}
        res_a = by_id[conv_a.id]
        res_b = by_id[conv_b.id]

        assert res_a.matched == "title"
        assert res_a.snippet == "Apple pie recipe"

        assert res_b.matched == "content"
        assert "Apple" in res_b.snippet


def test_pagination_cursor_round_trip_and_ordering(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="PageUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        base_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        # Create conversations with distinct pinned and updated_at
        # c1: unpinned, t0
        c1 = Conversation(
            account_id=principal.account_id,
            user_id=principal.user_id,
            title="c1",
            pinned=False,
            created_at=base_time,
            updated_at=base_time,
        )
        # c2: pinned, t0 + 1 hr
        c2 = Conversation(
            account_id=principal.account_id,
            user_id=principal.user_id,
            title="c2",
            pinned=True,
            created_at=base_time + timedelta(hours=1),
            updated_at=base_time + timedelta(hours=1),
        )
        # c3: pinned, t0 + 2 hr
        c3 = Conversation(
            account_id=principal.account_id,
            user_id=principal.user_id,
            title="c3",
            pinned=True,
            created_at=base_time + timedelta(hours=2),
            updated_at=base_time + timedelta(hours=2),
        )
        # c4: unpinned, t0 + 3 hr
        c4 = Conversation(
            account_id=principal.account_id,
            user_id=principal.user_id,
            title="c4",
            pinned=False,
            created_at=base_time + timedelta(hours=3),
            updated_at=base_time + timedelta(hours=3),
        )
        session.add_all([c1, c2, c3, c4])
        session.commit()

        # Cursor round-trip
        cursor_c3 = encode_cursor(c3)
        pinned_dec, updated_dec, id_dec = decode_cursor(cursor_c3)
        assert pinned_dec is True
        assert id_dec == c3.id
        assert updated_dec.isoformat() == c3.updated_at.isoformat()

        # Expected order: pinned DESC, updated_at DESC, id DESC:
        # [c3, c2, c4, c1]
        page1, next1 = list_conversations(session, principal, limit=2)
        assert [c.id for c in page1] == [c3.id, c2.id]
        assert next1 is not None

        page2, next2 = list_conversations(session, principal, cursor=next1, limit=2)
        assert [c.id for c in page2] == [c4.id, c1.id]
        assert next2 is None

        # Archived filter test
        update_conversation(session, principal, c1.id, ConversationUpdate(archived=True))
        session.commit()

        active_page, _ = list_conversations(session, principal, archived=False, limit=10)
        assert c1.id not in [c.id for c in active_page]
        assert {c.id for c in active_page} == {c3.id, c2.id, c4.id}

        archived_page, _ = list_conversations(session, principal, archived=True, limit=10)
        assert [c.id for c in archived_page] == [c1.id]


def test_invalid_cursor_raises_value_error(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="CursorUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)

        for bad in ["not-base64!!!", "e30=", "WzEsIDJd", "WzEsICJiYWQtZGF0ZSIsICJpZCJd"]:
            with pytest.raises(ValueError):
                decode_cursor(bad)

            with pytest.raises(ValueError):
                list_conversations(session, principal, cursor=bad)


def test_list_messages_has_more_before_and_ordering(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="MsgUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv = ensure_conversation_for_message(session, principal, None, "Conversation with msgs", now)
        session.commit()

        # Add 4 messages in chronological order
        msgs: list[ChatMessage] = []
        for i in range(4):
            msg = ChatMessage(
                conversation_id=conv.id,
                account_id=principal.account_id,
                role="user" if i % 2 == 0 else "assistant",
                status="complete",
                content=f"Message {i}",
                created_at=now + timedelta(minutes=i),
                updated_at=now + timedelta(minutes=i),
            )
            session.add(msg)
            msgs.append(msg)
        session.commit()

        # Latest 2 messages: should return [msgs[2], msgs[3]] oldest -> newest with has_more_before=True
        page1, has_more1 = list_messages(session, principal, conv.id, before=None, limit=2)
        assert [m.id for m in page1] == [msgs[2].id, msgs[3].id]
        assert has_more1 is True

        # Paginate before msg[2]: should return [msgs[0], msgs[1]] with has_more_before=False
        page2, has_more2 = list_messages(session, principal, conv.id, before=msgs[2].id, limit=2)
        assert [m.id for m in page2] == [msgs[0].id, msgs[1].id]
        assert has_more2 is False

        # Non-existent before id raises 404
        with pytest.raises(HTTPException) as exc_info:
            list_messages(session, principal, conv.id, before="msg_nonexistent_id", limit=2)
        assert exc_info.value.status_code == 404


def test_touch_conversation_and_message_counts(test_context: dict[str, object]) -> None:
    factory = test_context["factory"]
    settings = test_context["settings"]
    with factory() as session:  # type: ignore[operator]
        account, user, _ = create_identity(session, settings, name="TouchUser")  # type: ignore[arg-type]
        principal = Principal(user_id=user.id, account_id=account.id, role=user.role)
        now = utcnow()

        conv = ensure_conversation_for_message(session, principal, None, "Touch Test", now)
        later = now + timedelta(hours=5)
        touch_conversation(conv, later)
        assert conv.last_message_at == later
        assert conv.updated_at == later

        # Message count grouped query
        msg = ChatMessage(
            conversation_id=conv.id,
            account_id=principal.account_id,
            role="user",
            status="complete",
            content="Hello",
            created_at=now,
            updated_at=now,
        )
        session.add(msg)
        session.commit()

        counts = message_counts(session, [conv.id, "conv_empty"])
        assert counts[conv.id] == 1
        assert counts["conv_empty"] == 0

        # View mappings
        conv_view = to_conversation_view(conv, message_count=counts[conv.id])
        assert conv_view.id == conv.id
        assert conv_view.message_count == 1

        msg_view = to_message_view(msg)
        assert msg_view.id == msg.id
        assert msg_view.content == "Hello"
