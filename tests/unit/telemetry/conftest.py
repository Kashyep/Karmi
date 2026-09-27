"""Fixtures and synthetic telemetry record builders for unit tests."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from daily_agent.db import Base
from daily_agent.routing.models import FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION
from daily_agent.telemetry.events import (
    TELEMETRY_SCHEMA_VERSION,
    AttemptRecord,
    CostMeasurement,
    DecisionRecord,
    FeedbackRecord,
    FeedbackType,
    ImmediateOutcome,
    OpsEventRecord,
    RunRecord,
    RunStatus,
    SignalRecord,
    SignalSource,
    SignalStrength,
    SignalType,
    ToolEventRecord,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[sessionmaker[Session], None, None]:
    db_file = tmp_path / "telemetry_test.db"
    engine: Engine = create_engine(
        f"sqlite+pysqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def make_uuid(prefix: int = 1) -> str:
    return f"{prefix:08x}-0000-0000-0000-000000000000"


def make_hex64(char: str = "a") -> str:
    return char * 64


def build_synthetic_run_record(
    *,
    run_id: str | None = None,
    anonymous_actor_id: str | None = None,
    request_fingerprint: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    status: RunStatus = RunStatus.COMPLETED,
    outcome_str: str | None = "STORE_MEMORY",
    feature_schema_version: str = FEATURE_SCHEMA_VERSION,
) -> RunRecord:
    r_id = run_id or make_uuid(1)
    t0 = started_at or datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC)
    t1 = completed_at or datetime(2026, 9, 27, 10, 0, 1, tzinfo=UTC)
    actor = anonymous_actor_id or make_hex64("1")

    features = {name: 0.5 for name in FEATURE_NAMES_V1}
    dec_id = make_uuid(2)
    att_id = make_uuid(3)
    tool_id = make_uuid(4)

    return RunRecord(
        run_id=r_id,
        request_id=make_uuid(5),
        session_id_hash=make_hex64("2"),
        anonymous_actor_id=actor,
        request_fingerprint=request_fingerprint,
        started_at=t0,
        completed_at=t1,
        task_domain="memory",
        tier="ananta",
        harness_version="harness-v1",
        prompt_version="prompt-v1",
        policy_version="policy-static-v1",
        feature_schema_version=feature_schema_version,
        telemetry_schema_version=TELEMETRY_SCHEMA_VERSION,
        app_version="0.1.0",
        status=status,
        features=features,
        eligible_models=["fake-economy", "typesafe-system-one"],
        eligibility_rejections={},
        live_fallback_reason=None,
        shadow_error=None,
        decisions=[
            DecisionRecord(
                decision_id=dec_id,
                policy_version="policy-static-v1",
                feature_schema_version=feature_schema_version,
                algorithm="static",
                selected_model="fake-economy",
                selected_provider="fake",
                selection_probability=1.0,
                action_probabilities={"fake-economy": 1.0},
                eligible_models=["fake-economy"],
                exploration=False,
                shadow=False,
                agreed_with_live=None,
                created_at=t0,
            )
        ],
        attempts=[
            AttemptRecord(
                attempt_id=att_id,
                decision_id=dec_id,
                provider="fake",
                model="fake-economy",
                operation="generate",
                latency_ms=120,
                input_tokens=100,
                output_tokens=50,
                estimated_cost_micro=10,
                cost_measurement=CostMeasurement.MEASURED,
                success=True,
                error_type=None,
                retry_number=0,
            )
        ],
        tool_events=[
            ToolEventRecord(
                event_id=tool_id,
                tool_name="store_memory",
                attempt_number=1,
                schema_valid=True,
                execution_success=True,
                latency_ms=15,
                error_class=None,
            )
        ],
        outcome=ImmediateOutcome(
            completed=True,
            first_shot_success=True,
            structured_output_valid=True,
            tool_success=True,
            retry_count=0,
            final_latency_ms=135,
            final_cost_micro=10,
            cost_measurement=CostMeasurement.MEASURED,
            outcome=outcome_str,
        ),
    )


def build_synthetic_signal_record(
    *,
    signal_id: str | None = None,
    run_id: str | None = None,
    signal_type: SignalType = SignalType.ACCEPT,
    strength: SignalStrength = SignalStrength.STRONG,
    confidence: float = 1.0,
    source: SignalSource = SignalSource.EXPLICIT_FEEDBACK,
    observed_at: datetime | None = None,
) -> SignalRecord:
    return SignalRecord(
        signal_id=signal_id or str(uuid.uuid4()),
        run_id=run_id or make_uuid(1),
        signal_type=signal_type,
        strength=strength,
        confidence=confidence,
        source=source,
        observed_at=observed_at or datetime(2026, 9, 27, 10, 5, 0, tzinfo=UTC),
    )


def build_synthetic_feedback_record(
    *,
    feedback_id: str | None = None,
    run_id: str | None = None,
    feedback_type: FeedbackType = FeedbackType.ACCEPT,
    correction_distance: float | None = None,
    sanitized_corrected_value: str | None = None,
    created_at: datetime | None = None,
) -> FeedbackRecord:
    return FeedbackRecord(
        feedback_id=feedback_id or str(uuid.uuid4()),
        run_id=run_id or make_uuid(1),
        feedback_type=feedback_type,
        original_value_hash=make_hex64("f"),
        sanitized_corrected_value=sanitized_corrected_value,
        correction_distance=correction_distance,
        created_at=created_at or datetime(2026, 9, 27, 10, 5, 0, tzinfo=UTC),
    )


def build_synthetic_ops_event(
    *,
    event_id: str | None = None,
    event_type: str = "router_reload",
    created_at: datetime | None = None,
) -> OpsEventRecord:
    return OpsEventRecord(
        event_id=event_id or str(uuid.uuid4()),
        event_type=event_type,
        detail="reloaded_ok",
        policy_version="policy-static-v1",
        created_at=created_at or datetime(2026, 9, 27, 10, 0, 0, tzinfo=UTC),
    )
