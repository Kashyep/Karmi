from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from daily_agent.models import ChatMessage, Conversation, utcnow
from tests.conftest import create_identity


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_list_ordering_and_pagination(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserList")  # type: ignore[arg-type]
        base_time = utcnow()

        # conv1: unpinned, older
        conv1 = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Old Unpinned",
            title_source="auto",
            pinned=False,
            updated_at=base_time - timedelta(hours=2),
            created_at=base_time - timedelta(hours=2),
        )
        # conv2: pinned, middle
        conv2 = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Pinned Middle",
            title_source="user",
            pinned=True,
            updated_at=base_time - timedelta(hours=1),
            created_at=base_time - timedelta(hours=1),
        )
        # conv3: unpinned, newest
        conv3 = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Newest Unpinned",
            title_source="auto",
            pinned=False,
            updated_at=base_time,
            created_at=base_time,
        )
        session.add_all([conv1, conv2, conv3])
        session.commit()

    # Page 1: limit 2 -> conv2 (pinned) first, then conv3 (newest unpinned)
    resp = client.get("/v1/conversations?limit=2", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) == 2
    assert items[0]["id"] == conv2.id
    assert items[1]["id"] == conv3.id
    cursor = data["nextCursor"]
    assert cursor is not None

    # Page 2: with cursor -> conv1
    resp2 = client.get(f"/v1/conversations?limit=2&cursor={cursor}", headers=auth(token))
    assert resp2.status_code == 200
    data2 = resp2.json()
    items2 = data2["items"]
    assert len(items2) == 1
    assert items2[0]["id"] == conv1.id
    assert data2["nextCursor"] is None

    # Invalid cursor -> 422
    resp_invalid = client.get("/v1/conversations?cursor=invalid_cursor_xyz", headers=auth(token))
    assert resp_invalid.status_code == 422


def test_archived_filter(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserArchive")  # type: ignore[arg-type]
        now = utcnow()
        active = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Active Chat",
            archived_at=None,
            updated_at=now,
        )
        archived = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Archived Chat",
            archived_at=now,
            updated_at=now,
        )
        session.add_all([active, archived])
        session.commit()

    # archived=false (default) returns only active
    resp_active = client.get("/v1/conversations?archived=false", headers=auth(token))
    assert resp_active.status_code == 200
    ids = [c["id"] for c in resp_active.json()["items"]]
    assert active.id in ids
    assert archived.id not in ids

    # archived=true returns only archived
    resp_archived = client.get("/v1/conversations?archived=true", headers=auth(token))
    assert resp_archived.status_code == 200
    ids_archived = [c["id"] for c in resp_archived.json()["items"]]
    assert archived.id in ids_archived
    assert active.id not in ids_archived


def test_search_validation_and_shadowing(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        _account, _user, token = create_identity(session, settings, name="UserSearch")  # type: ignore[arg-type]

    # Empty query or whitespace-only -> 422
    assert client.get("/v1/conversations/search?q=", headers=auth(token)).status_code == 422
    assert client.get("/v1/conversations/search?q=%20%20%20", headers=auth(token)).status_code == 422
    assert client.get("/v1/conversations/search", headers=auth(token)).status_code == 422

    # Query > 200 characters -> 422
    assert client.get(f"/v1/conversations/search?q={'x' * 201}", headers=auth(token)).status_code == 422

    # Valid search does not get shadowed by /{conversation_id} (returns 200, not 404)
    resp = client.get("/v1/conversations/search?q=testquery", headers=auth(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_search_matching_title_and_content(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserSearchMatch")  # type: ignore[arg-type]
        now = utcnow()

        conv1 = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Quantum Mechanics Research",
            updated_at=now,
        )
        conv2 = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Daily Discussion",
            updated_at=now,
        )
        session.add_all([conv1, conv2])
        session.flush()

        msg = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv2.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="We should investigate astrophysics formulas in the upcoming sprint.",
            created_at=now,
            updated_at=now,
        )
        session.add(msg)
        session.commit()

    # Search matches title
    resp1 = client.get("/v1/conversations/search?q=quantum", headers=auth(token))
    assert resp1.status_code == 200
    results1 = resp1.json()
    assert len(results1) == 1
    assert results1[0]["conversation"]["id"] == conv1.id
    assert results1[0]["matched"] == "title"
    assert results1[0]["snippet"] == "Quantum Mechanics Research"

    # Search matches message content
    resp2 = client.get("/v1/conversations/search?q=astrophysics", headers=auth(token))
    assert resp2.status_code == 200
    results2 = resp2.json()
    assert len(results2) == 1
    assert results2[0]["conversation"]["id"] == conv2.id
    assert results2[0]["matched"] == "content"
    assert "astrophysics" in results2[0]["snippet"].lower()


def test_get_conversation_and_cross_user_404(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account_a, user_a, token_a = create_identity(session, settings, name="UserA")  # type: ignore[arg-type]
        _account_b, _user_b, token_b = create_identity(session, settings, name="UserB")  # type: ignore[arg-type]

        conv_a = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account_a.id,
            user_id=user_a.id,
            title="User A Secret Chat",
        )
        session.add(conv_a)
        session.commit()

    # Owner can get conversation
    resp_owner = client.get(f"/v1/conversations/{conv_a.id}", headers=auth(token_a))
    assert resp_owner.status_code == 200
    assert resp_owner.json()["id"] == conv_a.id
    assert resp_owner.json()["title"] == "User A Secret Chat"

    # Other user receives 404 (never 403)
    resp_other = client.get(f"/v1/conversations/{conv_a.id}", headers=auth(token_b))
    assert resp_other.status_code == 404

    # Nonexistent conversation receives 404
    assert client.get("/v1/conversations/conv_nonexistent", headers=auth(token_a)).status_code == 404


def test_patch_title_and_archived(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserPatch")  # type: ignore[arg-type]
        conv = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Initial Title",
            title_source="auto",
            pinned=False,
        )
        session.add(conv)
        session.commit()

    # PATCH title -> sets title_source='user'
    resp_title = client.patch(
        f"/v1/conversations/{conv.id}",
        headers=auth(token),
        json={"title": "Custom Renamed Title"},
    )
    assert resp_title.status_code == 200
    data = resp_title.json()
    assert data["title"] == "Custom Renamed Title"
    assert data["titleSource"] == "user"

    # PATCH archived: true -> sets archivedAt
    resp_archive = client.patch(
        f"/v1/conversations/{conv.id}",
        headers=auth(token),
        json={"archived": True},
    )
    assert resp_archive.status_code == 200
    assert resp_archive.json()["archivedAt"] is not None

    # PATCH archived: false -> clears archivedAt
    resp_unarchive = client.patch(
        f"/v1/conversations/{conv.id}",
        headers=auth(token),
        json={"archived": False},
    )
    assert resp_unarchive.status_code == 200
    assert resp_unarchive.json()["archivedAt"] is None

    # PATCH pinned: true
    resp_pin = client.patch(
        f"/v1/conversations/{conv.id}",
        headers=auth(token),
        json={"pinned": True},
    )
    assert resp_pin.status_code == 200
    assert resp_pin.json()["pinned"] is True


def test_delete_204_and_restore(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserDelete")  # type: ignore[arg-type]
        _acc2, _usr2, token_other = create_identity(session, settings, name="UserDelOther")  # type: ignore[arg-type]
        conv = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="To Delete",
        )
        session.add(conv)
        session.commit()

    # DELETE -> 204 No Content
    del_resp = client.delete(f"/v1/conversations/{conv.id}", headers=auth(token))
    assert del_resp.status_code == 204
    assert del_resp.content == b""

    # GET soft-deleted conversation -> 404
    assert client.get(f"/v1/conversations/{conv.id}", headers=auth(token)).status_code == 404

    # Second DELETE -> 404 (already deleted)
    assert client.delete(f"/v1/conversations/{conv.id}", headers=auth(token)).status_code == 404

    # Other user cannot restore it -> 404
    assert client.post(f"/v1/conversations/{conv.id}/restore", headers=auth(token_other)).status_code == 404

    # POST restore -> 200 ConversationView
    restore_resp = client.post(f"/v1/conversations/{conv.id}/restore", headers=auth(token))
    assert restore_resp.status_code == 200
    assert restore_resp.json()["id"] == conv.id

    # GET works again after restore
    get_resp = client.get(f"/v1/conversations/{conv.id}", headers=auth(token))
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == conv.id

    # Calling restore again when not soft-deleted -> 404
    assert client.post(f"/v1/conversations/{conv.id}/restore", headers=auth(token)).status_code == 404


def test_messages_before_and_limit(test_context: dict[str, object]) -> None:
    client: TestClient = test_context["client"]  # type: ignore[assignment]
    factory = test_context["factory"]
    settings = test_context["settings"]

    with factory() as session:  # type: ignore[operator]
        account, user, token = create_identity(session, settings, name="UserMsg")  # type: ignore[arg-type]
        _acc_other, _usr_other, token_other = create_identity(session, settings, name="UserMsgOther")  # type: ignore[arg-type]

        conv = Conversation(
            id=f"conv_{uuid4().hex}",
            account_id=account.id,
            user_id=user.id,
            title="Conversation With Messages",
        )
        session.add(conv)
        session.flush()

        base_time = utcnow()
        msg1 = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Message 1 (oldest)",
            created_at=base_time - timedelta(minutes=10),
            updated_at=base_time - timedelta(minutes=10),
        )
        msg2 = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv.id,
            account_id=account.id,
            role="assistant",
            status="complete",
            content="Message 2 (middle)",
            created_at=base_time - timedelta(minutes=5),
            updated_at=base_time - timedelta(minutes=5),
        )
        msg3 = ChatMessage(
            id=f"msg_{uuid4().hex}",
            conversation_id=conv.id,
            account_id=account.id,
            role="user",
            status="complete",
            content="Message 3 (newest)",
            created_at=base_time,
            updated_at=base_time,
        )
        session.add_all([msg1, msg2, msg3])
        session.commit()

    # Query with limit 2: returns newest 2 messages ordered oldest to newest: [msg2, msg3]
    resp = client.get(f"/v1/conversations/{conv.id}/messages?limit=2", headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]
    assert len(items) == 2
    assert items[0]["id"] == msg2.id
    assert items[1]["id"] == msg3.id
    assert data["hasMoreBefore"] is True

    # Query with before=msg2.id: returns messages strictly older than msg2: [msg1]
    resp_before = client.get(
        f"/v1/conversations/{conv.id}/messages?before={msg2.id}&limit=2",
        headers=auth(token),
    )
    assert resp_before.status_code == 200
    data_before = resp_before.json()
    items_before = data_before["items"]
    assert len(items_before) == 1
    assert items_before[0]["id"] == msg1.id
    assert data_before["hasMoreBefore"] is False

    # Invalid before id -> 404
    resp_invalid_before = client.get(
        f"/v1/conversations/{conv.id}/messages?before=msg_nonexistent",
        headers=auth(token),
    )
    assert resp_invalid_before.status_code == 404

    # Other user -> 404
    resp_other = client.get(f"/v1/conversations/{conv.id}/messages", headers=auth(token_other))
    assert resp_other.status_code == 404
