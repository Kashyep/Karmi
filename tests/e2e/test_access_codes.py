import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from daily_agent.access_codes import load_access_code_hashes
from daily_agent.config import Settings
from tests.conftest import create_identity


def _digest(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


def _setup(ctx: dict[str, object], tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    settings = ctx["settings"]
    factory = ctx["factory"]
    client = ctx["client"]
    assert isinstance(settings, Settings)
    assert isinstance(factory, sessionmaker)
    assert isinstance(client, TestClient)
    path = tmp_path / "codes.json"
    path.write_text(
        json.dumps(
            {"hashes": {_digest("YANTA-TEST-0001"): "yanta", _digest("PARTH-TEST-0002"): "parth"}}
        )
    )
    settings.access_codes_path = path
    with factory() as session:
        _a, _u, token = create_identity(session, settings, name="Tester")
    return client, {"Authorization": f"Bearer {token}"}


def test_code_upgrades_the_plan_and_never_downgrades(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    client, headers = _setup(test_context, tmp_path)

    up = client.post("/v1/access-code", json={"code": "yanta-test-0001"}, headers=headers)
    assert up.json() == {"plan_id": "yanta", "plan_label": "Yanta", "changed": True}
    assert client.get("/v1/usage", headers=headers).json()["plan_id"] == "yanta"

    top = client.post("/v1/access-code", json={"code": "PARTH TEST 0002"}, headers=headers)
    assert top.json()["plan_id"] == "parth"
    again = client.post("/v1/access-code", json={"code": "YANTA-TEST-0001"}, headers=headers)
    assert again.json() == {"plan_id": "parth", "plan_label": "Parth", "changed": False}


def test_wrong_codes_are_rejected_and_guessing_is_throttled(
    test_context: dict[str, object], tmp_path: Path
) -> None:
    client, headers = _setup(test_context, tmp_path)

    statuses = [
        client.post(
            "/v1/access-code", json={"code": f"WRONG-CODE-{i:04d}"}, headers=headers
        ).status_code
        for i in range(6)
    ]

    assert statuses == [404] * 5 + [429]
    assert client.get("/v1/usage", headers=headers).json()["plan_id"] == "ananta"


def test_packaged_codes_cover_each_paid_tier_once() -> None:
    hashes = load_access_code_hashes()
    assert sorted(hashes.values()) == ["parth", "trika", "yanta"]
