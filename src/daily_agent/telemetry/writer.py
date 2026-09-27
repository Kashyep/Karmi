"""Database persistence of telemetry events into sync SQLAlchemy tables (ADR-0003).

All inserts are idempotent by primary key so that replaying spooled batches after an
interruption never duplicates rows or causes uniqueness violations.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

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


def persist_events(
    session: Session,
    events: Sequence[TelemetryEvent],
    *,
    now: datetime,
    attribution_window_seconds: int,
) -> None:
    """Persist a batch of telemetry events in one transaction (caller commits).

    Idempotent by primary key: rows whose PK already exists are skipped without error.
    """
    for event in events:
        if isinstance(event, RunRecord):
            _persist_run(session, event, now=now, attribution_window_seconds=attribution_window_seconds)
        elif isinstance(event, SignalRecord):
            _persist_signal(session, event)
        elif isinstance(event, FeedbackRecord):
            _persist_feedback(session, event)
        elif isinstance(event, OpsEventRecord):
            _persist_ops_event(session, event)


def _persist_run(
    session: Session,
    event: RunRecord,
    *,
    now: datetime,
    attribution_window_seconds: int,
) -> None:
    if session.get(TelemetryRun, event.run_id) is not None:
        return

    session.add(
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
        )
    )

    for d in event.decisions:
        if session.get(TelemetryRouterDecision, d.decision_id) is None:
            session.add(
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
                )
            )

    for a in event.attempts:
        if session.get(TelemetryModelAttempt, a.attempt_id) is None:
            cost_m = (
                a.cost_measurement.value
                if hasattr(a.cost_measurement, "value")
                else str(a.cost_measurement)
            )
            session.add(
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
                )
            )

    for t in event.tool_events:
        if session.get(TelemetryToolEvent, t.event_id) is None:
            session.add(
                TelemetryToolEvent(
                    event_id=t.event_id,
                    run_id=event.run_id,
                    tool_name=t.tool_name,
                    attempt_number=t.attempt_number,
                    schema_valid=t.schema_valid,
                    execution_success=t.execution_success,
                    latency_ms=t.latency_ms,
                    error_class=t.error_class,
                )
            )

    if session.get(TelemetryRunOutcome, event.run_id) is None:
        cost_m_out = (
            event.outcome.cost_measurement.value
            if hasattr(event.outcome.cost_measurement, "value")
            else str(event.outcome.cost_measurement)
        )
        session.add(
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
            )
        )

    # Derived retry attribution
    if event.request_fingerprint is not None:
        cutoff = event.started_at - timedelta(seconds=attribution_window_seconds)
        earlier_stmt = (
            select(TelemetryRun)
            .where(
                TelemetryRun.anonymous_actor_id == event.anonymous_actor_id,
                TelemetryRun.request_fingerprint == event.request_fingerprint,
                TelemetryRun.run_id != event.run_id,
                TelemetryRun.completed_at <= event.started_at,
                TelemetryRun.completed_at >= cutoff,
            )
            .order_by(TelemetryRun.completed_at.desc())
        )
        earlier_runs = list(session.scalars(earlier_stmt).all())
        if earlier_runs:
            earlier_run = earlier_runs[0]
            existing_sig = session.scalar(
                select(TelemetryOutcomeSignal).where(
                    TelemetryOutcomeSignal.run_id == earlier_run.run_id,
                    TelemetryOutcomeSignal.signal_type == SignalType.RETRY.value,
                    TelemetryOutcomeSignal.source == SignalSource.DERIVED.value,
                )
            )
            if existing_sig is None:
                is_late = earlier_run.export_batch_id is not None
                session.add(
                    TelemetryOutcomeSignal(
                        signal_id=str(uuid.uuid4()),
                        run_id=earlier_run.run_id,
                        signal_type=SignalType.RETRY.value,
                        strength=SignalStrength.WEAK.value,
                        confidence=0.6,
                        source=SignalSource.DERIVED.value,
                        observed_at=event.started_at,
                        late=is_late,
                        export_batch_id=None,
                    )
                )


def _persist_signal(session: Session, event: SignalRecord) -> None:
    if session.get(TelemetryOutcomeSignal, event.signal_id) is not None:
        return

    run = session.get(TelemetryRun, event.run_id)
    is_late = run.export_batch_id is not None if run else False

    session.add(
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
        )
    )


def _persist_feedback(session: Session, event: FeedbackRecord) -> None:
    if session.get(TelemetryFeedback, event.feedback_id) is not None:
        return

    run = session.get(TelemetryRun, event.run_id)
    is_late = run.export_batch_id is not None if run else False

    session.add(
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
        )
    )

    # Strong explicit signal from feedback
    sig_type = _FEEDBACK_TO_SIGNAL_MAP.get(event.feedback_type)
    if sig_type is not None:
        sig_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"feedback-signal:{event.feedback_id}"))
        if session.get(TelemetryOutcomeSignal, sig_id) is None:
            session.add(
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
                )
            )


def _persist_ops_event(session: Session, event: OpsEventRecord) -> None:
    if session.get(TelemetryOpsEvent, event.event_id) is not None:
        return

    session.add(
        TelemetryOpsEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            detail=event.detail,
            policy_version=event.policy_version,
            created_at=event.created_at,
        )
    )
