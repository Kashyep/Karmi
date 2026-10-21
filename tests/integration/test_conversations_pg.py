from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from daily_agent.config import Settings
from daily_agent.conversations.service import (
    ensure_conversation_for_message,
    get_conversation,
    list_conversations,
    restore,
    search_conversations,
    soft_delete,
    update_conversation,
)
from daily_agent.models import ChatMessage, Conversation, utcnow
from daily_agent.schemas_chat import ConversationUpdate
from daily_agent.security import Principal
from tests.conftest import create_identity

pytestmark = pytest.mark.integration


def integration_urls() -> tuple[str, str]:
    database_url = os.environ.get("DAILY_AGENT_INTEGRATION_DATABASE_URL", "")
    redis_url = os.environ.get("DAILY_AGENT_INTEGRATION_REDIS_URL", "")
    if not database_url:
        pytest.skip("DAILY_AGENT_INTEGRATION_DATABASE_URL not set; disposable PostgreSQL required.")
    if "127.0.0.1:55432/daily_agent_test" not in database_url:
        pytest.fail("refusing to run outside the declared disposable PostgreSQL database")
    if redis_url != "redis://127.0.0.1:56379/15":
        pytest.fail("refusing to run outside the declared disposable Redis database")
    return database_url, redis_url


def test_alembic_migrations_round_trip_pg() -> None:
    database_url, _redis_url = integration_urls()
    os.environ["DAILY_AGENT_DATABASE_URL"] = database_url

    alembic = Config("alembic.ini")
    script_dir = ScriptDirectory.from_config(alembic)

    # Verify migration metadata and lineage
    rev_runs = script_dir.get_revision("c7a1d2e3f405")
    assert rev_runs is not None
    assert rev_runs.down_revision == "5f708192a3b4"

    rev_conv = script_dir.get_revision("d8b2e3f4a516")
    assert rev_conv is not None
    assert rev_conv.down_revision == "c7a1d2e3f405"

    # Step (a): Upgrade to head against PostgreSQL
    command.upgrade(alembic, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "conversations" in tables
        assert "chat_messages" in tables
        assert "runs" in tables

        # Verify new columns in runs from c7a1d2e3f405
        runs_cols = {c["name"] for c in inspector.get_columns("runs")}
        expected_run_cols = {
            "finish_reason",
            "partial_text",
            "last_seq",
            "heartbeat_at",
            "continuation_of_run_id",
        }
        assert expected_run_cols.issubset(runs_cols)

        # Verify columns in conversations and chat_messages from d8b2e3f4a516
        conv_cols = {c["name"] for c in inspector.get_columns("conversations")}
        expected_conv_cols = {
            "id",
            "account_id",
            "user_id",
            "title",
            "title_source",
            "pinned",
            "archived_at",
            "deleted_at",
            "created_at",
            "updated_at",
            "last_message_at",
        }
        assert expected_conv_cols.issubset(conv_cols)

        msg_cols = {c["name"] for c in inspector.get_columns("chat_messages")}
        expected_msg_cols = {
            "id",
            "conversation_id",
            "account_id",
            "role",
            "status",
            "content",
            "finish_reason",
            "run_id",
            "parent_message_id",
            "variant_index",
            "client_message_id",
            "created_at",
            "updated_at",
        }
        assert expected_msg_cols.issubset(msg_cols)

        # Step (b): Downgrade to c7a1d2e3f405 and verify tables dropped
        command.downgrade(alembic, "c7a1d2e3f405")

        inspector = inspect(engine)
        tables_at_c7 = set(inspector.get_table_names())
        assert "conversations" not in tables_at_c7
        assert "chat_messages" not in tables_at_c7

        # Runs table still has new columns at c7a1d2e3f405
        runs_cols_at_c7 = {c["name"] for c in inspector.get_columns("runs")}
        assert expected_run_cols.issubset(runs_cols_at_c7)

        # Upgrade back to head
        command.upgrade(alembic, "head")

        inspector = inspect(engine)
        tables_back = set(inspector.get_table_names())
        assert "conversations" in tables_back
        assert "chat_messages" in tables_back

        command.check(alembic)
    finally:
        engine.dispose()


def test_conversations_service_pg() -> None:
    database_url, _redis_url = integration_urls()
    os.environ["DAILY_AGENT_DATABASE_URL"] = database_url

    alembic = Config("alembic.ini")
    command.upgrade(alembic, "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        auth_secret="integration-fixture-secret",  # noqa: S106
        webhook_secret="integration-webhook-secret",  # noqa: S106
    )

    try:
        with factory() as session:
            account, user_a, _ = create_identity(session, settings, name="ConvUserA")
            principal_a = Principal(user_id=user_a.id, account_id=account.id, role=user_a.role)

            _, user_b, _ = create_identity(session, settings, name="ConvUserB")
            principal_b = Principal(user_id=user_b.id, account_id=account.id, role=user_b.role)

            # (1) Verify no conversation row exists before first message
            count_before = session.scalar(
                select(func.count(Conversation.id)).where(Conversation.user_id == principal_a.user_id)
            )
            assert count_before == 0

            # (2) Create conversation and first user message in same transaction
            now = utcnow()
            first_query = "What is 100% test coverage for my_project?"
            conv1 = ensure_conversation_for_message(session, principal_a, None, first_query, now)
            msg1 = ChatMessage(
                conversation_id=conv1.id,
                account_id=principal_a.account_id,
                role="user",
                status="complete",
                content=first_query,
                created_at=now,
                updated_at=now,
            )
            session.add(msg1)
            session.commit()

            # Verify conversation properties
            assert conv1.id.startswith("conv_")
            assert conv1.title == first_query[:60]
            assert conv1.title_source == "auto"
            assert conv1.pinned is False
            assert conv1.archived_at is None
            assert conv1.deleted_at is None
            assert conv1.user_id == principal_a.user_id
            assert conv1.account_id == principal_a.account_id

            conv_count = session.scalar(
                select(func.count(Conversation.id)).where(Conversation.user_id == principal_a.user_id)
            )
            assert conv_count == 1
            msg_count = session.scalar(
                select(func.count(ChatMessage.id)).where(ChatMessage.conversation_id == conv1.id)
            )
            assert msg_count == 1

            # (3) Search with ILIKE on title/content and escaping of % and _
            # conv2: contains '1000' (must not match '100%' if % is escaped)
            conv2 = ensure_conversation_for_message(session, principal_a, None, "1000 items to process", now)
            msg2 = ChatMessage(
                conversation_id=conv2.id,
                account_id=principal_a.account_id,
                role="user",
                status="complete",
                content="Processing a batch of 1000 items in sequence",
                created_at=now,
                updated_at=now,
            )
            session.add(msg2)

            # conv3: contains underscore 'python_agent'
            conv3 = ensure_conversation_for_message(session, principal_a, None, "Guide to python_agent", now)
            msg3 = ChatMessage(
                conversation_id=conv3.id,
                account_id=principal_a.account_id,
                role="user",
                status="complete",
                content="Details about the python_agent architecture",
                created_at=now,
                updated_at=now,
            )
            session.add(msg3)

            # conv4: contains hyphen 'python-agent' (must not match 'python_agent' if _ is escaped)
            conv4 = ensure_conversation_for_message(session, principal_a, None, "Guide to python-agent", now)
            msg4 = ChatMessage(
                conversation_id=conv4.id,
                account_id=principal_a.account_id,
                role="user",
                status="complete",
                content="Details about the python-agent architecture",
                created_at=now,
                updated_at=now,
            )
            session.add(msg4)

            # conv5: match solely on message content (title has no match)
            conv5 = ensure_conversation_for_message(session, principal_a, None, "General Architecture", now)
            msg5_user = ChatMessage(
                conversation_id=conv5.id,
                account_id=principal_a.account_id,
                role="user",
                status="complete",
                content="Can you explain the system?",
                created_at=now,
                updated_at=now,
            )
            msg5_assistant = ChatMessage(
                conversation_id=conv5.id,
                account_id=principal_a.account_id,
                role="assistant",
                status="complete",
                content="The system maintains 100% reliable execution guarantees.",
                created_at=now,
                updated_at=now,
            )
            session.add_all([msg5_user, msg5_assistant])
            session.commit()

            # Search '100%': conv1 (title/content) and conv5 (assistant content) match, conv2 does NOT
            results_percent = search_conversations(session, principal_a, "100%")
            matched_ids_percent = [r.conversation.id for r in results_percent]
            assert conv1.id in matched_ids_percent
            assert conv5.id in matched_ids_percent
            assert conv2.id not in matched_ids_percent

            r1 = next(r for r in results_percent if r.conversation.id == conv1.id)
            assert r1.matched == "title"
            assert "100%" in r1.snippet

            r5 = next(r for r in results_percent if r.conversation.id == conv5.id)
            assert r5.matched == "content"
            assert "100%" in r5.snippet

            # Search 'python_agent': conv3 matches, conv4 ('python-agent') does NOT
            results_underscore = search_conversations(session, principal_a, "python_agent")
            matched_ids_underscore = [r.conversation.id for r in results_underscore]
            assert conv3.id in matched_ids_underscore
            assert conv4.id not in matched_ids_underscore

            # Case-insensitivity verification
            results_case = search_conversations(session, principal_a, "PYTHON_AGENT")
            assert any(r.conversation.id == conv3.id for r in results_case)

            # (4) Archive (archived_at)
            update_conversation(session, principal_a, conv1.id, ConversationUpdate(archived=True))
            session.commit()

            c1_archived = get_conversation(session, principal_a, conv1.id)
            assert c1_archived.archived_at is not None

            active_list, _ = list_conversations(session, principal_a, archived=False)
            assert conv1.id not in [c.id for c in active_list]

            archived_list, _ = list_conversations(session, principal_a, archived=True)
            assert conv1.id in [c.id for c in archived_list]

            # Unarchive
            update_conversation(session, principal_a, conv1.id, ConversationUpdate(archived=False))
            session.commit()

            c1_unarchived = get_conversation(session, principal_a, conv1.id)
            assert c1_unarchived.archived_at is None
            active_list_after, _ = list_conversations(session, principal_a, archived=False)
            assert conv1.id in [c.id for c in active_list_after]

            # (5) Soft delete: deleted_at set, hidden from list/search
            soft_delete(session, principal_a, conv1.id)
            session.commit()

            raw_conv = session.scalar(select(Conversation).where(Conversation.id == conv1.id))
            assert raw_conv is not None
            assert raw_conv.deleted_at is not None

            with pytest.raises(HTTPException) as exc_info:
                get_conversation(session, principal_a, conv1.id)
            assert exc_info.value.status_code == 404

            active_del, _ = list_conversations(session, principal_a, archived=False)
            assert conv1.id not in [c.id for c in active_del]

            archived_del, _ = list_conversations(session, principal_a, archived=True)
            assert conv1.id not in [c.id for c in archived_del]

            search_del = search_conversations(session, principal_a, "100%")
            assert conv1.id not in [r.conversation.id for r in search_del]

            # (6) Restore
            restored = restore(session, principal_a, conv1.id)
            session.commit()
            assert restored.deleted_at is None

            c1_restored = get_conversation(session, principal_a, conv1.id)
            assert c1_restored.id == conv1.id
            assert c1_restored.deleted_at is None

            active_restored, _ = list_conversations(session, principal_a, archived=False)
            assert conv1.id in [c.id for c in active_restored]

            search_restored = search_conversations(session, principal_a, "100%")
            assert conv1.id in [r.conversation.id for r in search_restored]

            # (7) Cross-user isolation: User B cannot access User A's conversation
            with pytest.raises(HTTPException) as exc_b:
                get_conversation(session, principal_b, conv1.id)
            assert exc_b.value.status_code == 404

            list_b, _ = list_conversations(session, principal_b)
            assert conv1.id not in [c.id for c in list_b]

            search_b = search_conversations(session, principal_b, "100%")
            assert len(search_b) == 0
    finally:
        engine.dispose()
