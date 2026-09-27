"""Database persistence of telemetry events into sync SQLAlchemy tables (ADR-0003).

All inserts are idempotent by primary key so that replaying spooled batches after an
interruption never duplicates rows or causes uniqueness violations.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.models import (
    TelemetryFeedback,
    TelemetryModelAttempt,
    TelemetryOpsEvent,
    TelemetryOutcomeSignal,
    TelemetryRouterDecision,
    TelemetryRun,
    TelemetryRunOutcome,
    TelemetryToolEvent,
)
from daily_agent.telemetry.events import (
    FeedbackRecord,
    FeedbackType,
    OpsEventRecord,
    RunRecord,
    SignalRecord,
    SignalSource,
    SignalStrength,
    SignalType,
    TelemetryEvent,
)

_FEEDBACK_TO_SIGNAL_MAP: dict[FeedbackType, SignalType] = {
    FeedbackType.ACCEPT: SignalType.ACCEPT,
    FeedbackType.REJECT: SignalType.REJECT,
    FeedbackType.CORRECTION: SignalType.CORRECTION,
    FeedbackType.PREFERENCE: SignalType.PREFERENCE,
    FeedbackType.CHANGED_INTENT: SignalType.CHANGED_INTENT,
}


def _utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes for DateTime(timezone=True) columns.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class _Batch:
    """Rows added in the current transaction, visible to later events in the batch.

    Autoflush is off while a batch is built, so pending rows are invisible to
    ``Session.get`` and queries; this view keeps in-batch duplicate and retry
    detection equivalent to row-at-a-time flushing.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._pending: dict[tuple[type[object], str], object] = {}

    def get[RowT](self, model: type[RowT], key: str) -> RowT | None:
        pending = self._pending.get((model, key))
        if pending is not None:
            return cast(RowT, pending)
        return self.session.get(model, key)

    def add(self, row: object, key: str) -> None:
        self._pending[(type(row), key)] = row
        self.session.add(row)

    def pending[RowT](self, model: type[RowT]) -> list[RowT]:
        return [cast(RowT, row) for (kind, _), row in self._pending.items() if kind is model]


def _feedback_signal_id(feedback_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"feedback-signal:{feedback_id}"))


def persist_events(
    session: Session,
    events: Sequence[TelemetryEvent],
    *,
    now: datetime,
    attribution_window_seconds: int,
) -> None:
    """Persist a batch of telemetry events in one transaction (caller commits).

    Idempotent by primary key: rows whose PK already exists are skipped without error.
    Inserts are flushed together at commit rather than before each existence check, so
    the database write lock (SQLite: whole database) is held only for the final flush.
    """
    batch = _Batch(session)
    with session.no_autoflush:
        for event in events:
            if isinstance(event, RunRecord):
                _persist_run(
                    batch, event, now=now, attribution_window_seconds=attribution_window_seconds
                )
            elif isinstance(event, SignalRecord):
                _persist_signal(batch, event)
            elif isinstance(event, FeedbackRecord):
                _persist_feedback(batch, event)
            elif isinstance(event, OpsEventRecord):
                _persist_ops_event(batch, event)


def _persist_run(
    batch: _Batch,
    event: RunRecord,
    *,
    now: datetime,
    attribution_window_seconds: int,
) -> None:
    if batch.get(TelemetryRun, event.run_id) is not None:
        return

    batch.add(
        TelemetryRun(
            run_id=event.run_id,
            request_id=event.request_id,
            session_id_hash=event.session_id_hash,
            anonymous_actor_id=event.anonymous_actor_id,
            request_fingerprint=event.request_fingerprint,
            started_at=event.started_at,
            completed_at=event.completed_at,
            task_domain=event.task_domain,
            tier=event.tier,
            harness_version=event.harness_version,
            prompt_version=event.prompt_version,
            policy_version=event.policy_version,
            feature_schema_version=event.feature_schema_version,
            telemetry_schema_version=event.telemetry_schema_version,
            app_version=event.app_version,
            status=event.status.value if hasattr(event.status, "value") else str(event.status),
            features_json=json.dumps(event.features, sort_keys=True, separators=(",", ":")),
            eligible_models_json=json.dumps(
                event.eligible_models, sort_keys=True, separators=(",", ":")
            ),
            eligibility_rejections_json=json.dumps(
                event.eligibility_rejections, sort_keys=True, separators=(",", ":")
            ),
            live_fallback_reason=event.live_fallback_reason,
            shadow_error=event.shadow_error,
            export_batch_id=None,
            created_at=now,
        ),
        event.run_id,
    )

    for d in event.decisions:
        if batch.get(TelemetryRouterDecision, d.decision_id) is None:
            batch.add(
                TelemetryRouterDecision(
                    decision_id=d.decision_id,
                    run_id=event.run_id,
                    policy_version=d.policy_version,
                    feature_schema_version=d.feature_schema_version,
                    algorithm=d.algorithm,
                    selected_model=d.selected_model,
                    selected_provider=d.selected_provider,
                    selection_probability=d.selection_probability,
                    action_probabilities_json=json.dumps(
                        d.action_probabilities, sort_keys=True, separators=(",", ":")
                    ),
                    eligible_models_json=json.dumps(
                        d.eligible_models, sort_keys=True, separators=(",", ":")
                    ),
                    exploration=d.exploration,
                    shadow=d.shadow,
                    agreed_with_live=d.agreed_with_live,
                    created_at=d.created_at,
                ),
                d.decision_id,
            )

    for a in event.attempts:
        if batch.get(TelemetryModelAttempt, a.attempt_id) is None:
            cost_m = (
                a.cost_measurement.value
                if hasattr(a.cost_measurement, "value")
                else str(a.cost_measurement)
            )
            batch.add(
                TelemetryModelAttempt(
                    attempt_id=a.attempt_id,
                    run_id=event.run_id,
                    decision_id=a.decision_id,
                    provider=a.provider,
                    model=a.model,
                    operation=a.operation,
                    latency_ms=a.latency_ms,
                    input_tokens=a.input_tokens,
                    output_tokens=a.output_tokens,
                    estimated_cost_micro=a.estimated_cost_micro,
                    cost_measurement=cost_m,
                    success=a.success,
                    error_type=a.error_type,
                    retry_number=a.retry_number,
                ),
                a.attempt_id,
            )

    for t in event.tool_events:
        if batch.get(TelemetryToolEvent, t.event_id) is None:
            batch.add(
                TelemetryToolEvent(
                    event_id=t.event_id,
                    run_id=event.run_id,
                    tool_name=t.tool_name,
                    attempt_number=t.attempt_number,
                    schema_valid=t.schema_valid,
                    execution_success=t.execution_success,
                    latency_ms=t.latency_ms,
                    error_class=t.error_class,
                ),
                t.event_id,
            )

    if batch.get(TelemetryRunOutcome, event.run_id) is None:
        cost_m_out = (
            event.outcome.cost_measurement.value
            if hasattr(event.outcome.cost_measurement, "value")
            else str(event.outcome.cost_measurement)
        )
        batch.add(
            TelemetryRunOutcome(
                run_id=event.run_id,
                completed=event.outcome.completed,
                first_shot_success=event.outcome.first_shot_success,
                structured_output_valid=event.outcome.structured_output_valid,
                tool_success=event.outcome.tool_success,
                retry_count=event.outcome.retry_count,
                user_retry_signal=False,
                user_abandon_signal=False,
                user_accept_signal=False,
                user_correction_signal=False,
                correction_distance=None,
                final_latency_ms=event.outcome.final_latency_ms,
                final_cost_micro=event.outcome.final_cost_micro,
                cost_measurement=cost_m_out,
                outcome=event.outcome.outcome,
                finalized_at=None,
            ),
            event.run_id,
        )

    if event.request_fingerprint is not None:
        _attribute_retry(batch, event, attribution_window_seconds=attribution_window_seconds)


def _attribute_retry(
    batch: _Batch, event: RunRecord, *, attribution_window_seconds: int
) -> None:
    """Mark the newest earlier run with the same actor and request as retried."""
    started = _utc(event.started_at)
    cutoff = started - timedelta(seconds=attribution_window_seconds)
    candidates = [
        run
        for run in batch.pending(TelemetryRun)
        if run.run_id != event.run_id
        and run.anonymous_actor_id == event.anonymous_actor_id
        and run.request_fingerprint == event.request_fingerprint
        and cutoff <= _utc(run.completed_at) <= started
    ]
    stored = batch.session.scalar(
        select(TelemetryRun)
        .where(
            TelemetryRun.anonymous_actor_id == event.anonymous_actor_id,
            TelemetryRun.request_fingerprint == event.request_fingerprint,
            TelemetryRun.run_id != event.run_id,
            TelemetryRun.completed_at <= event.started_at,
            TelemetryRun.completed_at >= cutoff,
        )
        .order_by(TelemetryRun.completed_at.desc())
        .limit(1)
    )
    if stored is not None:
        candidates.append(stored)
    if not candidates:
        return
    earlier_run = max(candidates, key=lambda run: _utc(run.completed_at))

    def is_derived_retry(signal: TelemetryOutcomeSignal) -> bool:
        return (
            signal.run_id == earlier_run.run_id
            and signal.signal_type == SignalType.RETRY.value
            and signal.source == SignalSource.DERIVED.value
        )

    if any(is_derived_retry(signal) for signal in batch.pending(TelemetryOutcomeSignal)):
        return
    existing_sig = batch.session.scalar(
        select(TelemetryOutcomeSignal).where(
            TelemetryOutcomeSignal.run_id == earlier_run.run_id,
            TelemetryOutcomeSignal.signal_type == SignalType.RETRY.value,
            TelemetryOutcomeSignal.source == SignalSource.DERIVED.value,
        )
    )
    if existing_sig is not None:
        return
    signal_id = str(uuid.uuid4())
    batch.add(
        TelemetryOutcomeSignal(
            signal_id=signal_id,
            run_id=earlier_run.run_id,
            signal_type=SignalType.RETRY.value,
            strength=SignalStrength.WEAK.value,
            confidence=0.6,
            source=SignalSource.DERIVED.value,
            observed_at=event.started_at,
            late=earlier_run.export_batch_id is not None,
            export_batch_id=None,
        ),
        signal_id,
    )


def _persist_signal(batch: _Batch, event: SignalRecord) -> None:
    if batch.get(TelemetryOutcomeSignal, event.signal_id) is not None:
        return

    run = batch.get(TelemetryRun, event.run_id)
    is_late = run.export_batch_id is not None if run else False

    batch.add(
        TelemetryOutcomeSignal(
            signal_id=event.signal_id,
            run_id=event.run_id,
            signal_type=event.signal_type.value
            if hasattr(event.signal_type, "value")
            else str(event.signal_type),
            strength=event.strength.value
            if hasattr(event.strength, "value")
            else str(event.strength),
            confidence=event.confidence,
            source=event.source.value if hasattr(event.source, "value") else str(event.source),
            observed_at=event.observed_at,
            late=is_late,
            export_batch_id=None,
        ),
        event.signal_id,
    )


def _persist_feedback(batch: _Batch, event: FeedbackRecord) -> None:
    if batch.get(TelemetryFeedback, event.feedback_id) is not None:
        return

    run = batch.get(TelemetryRun, event.run_id)
    is_late = run.export_batch_id is not None if run else False

    batch.add(
        TelemetryFeedback(
            feedback_id=event.feedback_id,
            run_id=event.run_id,
            feedback_type=event.feedback_type.value
            if hasattr(event.feedback_type, "value")
            else str(event.feedback_type),
            original_value_hash=event.original_value_hash,
            sanitized_corrected_value=event.sanitized_corrected_value,
            correction_distance=event.correction_distance,
            created_at=event.created_at,
            late=is_late,
            export_batch_id=None,
        ),
        event.feedback_id,
    )

    # Strong explicit signal from feedback
    sig_type = _FEEDBACK_TO_SIGNAL_MAP.get(event.feedback_type)
    if sig_type is not None:
        sig_id = _feedback_signal_id(event.feedback_id)
        if batch.get(TelemetryOutcomeSignal, sig_id) is None:
            batch.add(
                TelemetryOutcomeSignal(
                    signal_id=sig_id,
                    run_id=event.run_id,
                    signal_type=sig_type.value,
                    strength=SignalStrength.STRONG.value,
                    confidence=1.0,
                    source=SignalSource.EXPLICIT_FEEDBACK.value,
                    observed_at=event.created_at,
                    late=is_late,
                    export_batch_id=None,
                ),
                sig_id,
            )


def _persist_ops_event(batch: _Batch, event: OpsEventRecord) -> None:
    if batch.get(TelemetryOpsEvent, event.event_id) is not None:
        return

    batch.add(
        TelemetryOpsEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            detail=event.detail,
            policy_version=event.policy_version,
            created_at=event.created_at,
        ),
        event.event_id,
    )
