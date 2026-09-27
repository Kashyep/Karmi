"""Export of finalized telemetry runs and late signals to TelemetryBatchV1 artifacts (ADR-0003).

Exports canonical JSON batches to disk, accompanied by a .sha256 checksum file.
Validates the entire export with the privacy sanitizer before writing anything (fail-closed).
Marked rows reference the deterministic batch ID. Export never deletes data.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from daily_agent.models import (
    TelemetryExportBatch,
    TelemetryFeedback,
    TelemetryModelAttempt,
    TelemetryOutcomeSignal,
    TelemetryRouterDecision,
    TelemetryRun,
    TelemetryRunOutcome,
    TelemetryToolEvent,
)
from daily_agent.observability import METRICS
from daily_agent.routing.models import FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION
from daily_agent.telemetry import sanitizer
from daily_agent.telemetry.events import (
    TELEMETRY_SCHEMA_VERSION,
    AttemptRecord,
    CostMeasurement,
    DecisionRecord,
    ExportedRunV1,
    FeedbackRecord,
    FeedbackType,
    FinalOutcomeV1,
    ProducerV1,
    RunStatus,
    SignalRecord,
    SignalSource,
    SignalStrength,
    SignalType,
    TelemetryBatchV1,
    ToolEventRecord,
)


@dataclass(frozen=True)
class ExportResult:
    batch_id: str
    path: Path
    run_count: int
    signal_count: int
    feedback_count: int
    payload_sha256: str

def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt



def export_batch(
    session: Session,
    *,
    out_dir: Path,
    producer_version: str,
    now: datetime,
    limit: int = 1000,
) -> ExportResult | None:
    """Export finalized unexported runs and unexported late signals into a TelemetryBatchV1.

    Returns ExportResult on success, or None if there is nothing to export. Caller commits.
    """
    # 1. Fetch eligible finalized runs
    run_stmt = (
        select(TelemetryRun, TelemetryRunOutcome)
        .join(TelemetryRunOutcome, TelemetryRun.run_id == TelemetryRunOutcome.run_id)
        .where(
            TelemetryRunOutcome.finalized_at.is_not(None),
            TelemetryRun.export_batch_id.is_(None),
        )
        .order_by(TelemetryRun.completed_at.asc(), TelemetryRun.run_id.asc())
        .limit(limit)
    )
    run_pairs = list(session.execute(run_stmt).all())

    # 2. Fetch unexported late signals and feedback
    late_signals_stmt = (
        select(TelemetryOutcomeSignal)
        .where(
            TelemetryOutcomeSignal.late.is_(True),
            TelemetryOutcomeSignal.export_batch_id.is_(None),
        )
        .order_by(TelemetryOutcomeSignal.observed_at.asc(), TelemetryOutcomeSignal.signal_id.asc())
    )
    late_signal_rows = list(session.scalars(late_signals_stmt).all())

    late_feedback_stmt = (
        select(TelemetryFeedback)
        .where(
            TelemetryFeedback.late.is_(True),
            TelemetryFeedback.export_batch_id.is_(None),
        )
        .order_by(TelemetryFeedback.created_at.asc(), TelemetryFeedback.feedback_id.asc())
    )
    late_feedback_rows = list(session.scalars(late_feedback_stmt).all())

    if not run_pairs and not late_signal_rows and not late_feedback_rows:
        return None

    # 3. Deterministic batch_id
    sorted_run_ids = sorted(r.run_id for r, _ in run_pairs)
    sorted_signal_ids = sorted(s.signal_id for s in late_signal_rows)
    sorted_feedback_ids = sorted(f.feedback_id for f in late_feedback_rows)
    preimage = (
        "kashyep-karmi|"
        + ",".join(sorted_run_ids)
        + "|"
        + ",".join(sorted_signal_ids)
        + "|"
        + ",".join(sorted_feedback_ids)
    )
    batch_id = hashlib.sha256(preimage.encode("utf-8")).hexdigest()

    # 4. Assemble ExportedRunV1 records
    exported_runs: list[ExportedRunV1] = []
    for run, outcome in run_pairs:
        # Decisions
        dec_stmt = (
            select(TelemetryRouterDecision)
            .where(TelemetryRouterDecision.run_id == run.run_id)
            .order_by(TelemetryRouterDecision.created_at.asc(), TelemetryRouterDecision.decision_id.asc())
        )
        dec_rows = session.scalars(dec_stmt).all()
        decisions = [
            DecisionRecord(
                decision_id=d.decision_id,
                policy_version=d.policy_version,
                feature_schema_version=d.feature_schema_version,
                algorithm=d.algorithm,
                selected_model=d.selected_model,
                selected_provider=d.selected_provider,
                selection_probability=d.selection_probability,
                action_probabilities=json.loads(d.action_probabilities_json),
                eligible_models=json.loads(d.eligible_models_json),
                exploration=d.exploration,
                shadow=d.shadow,
                agreed_with_live=d.agreed_with_live,
                created_at=_ensure_utc(d.created_at),
            )
            for d in dec_rows
        ]

        # Attempts
        att_stmt = (
            select(TelemetryModelAttempt)
            .where(TelemetryModelAttempt.run_id == run.run_id)
            .order_by(TelemetryModelAttempt.retry_number.asc(), TelemetryModelAttempt.attempt_id.asc())
        )
        att_rows = session.scalars(att_stmt).all()
        attempts = [
            AttemptRecord(
                attempt_id=a.attempt_id,
                decision_id=a.decision_id,
                provider=a.provider,
                model=a.model,
                operation=a.operation,
                latency_ms=a.latency_ms,
                input_tokens=a.input_tokens,
                output_tokens=a.output_tokens,
                estimated_cost_micro=a.estimated_cost_micro,
                cost_measurement=CostMeasurement(a.cost_measurement),
                success=a.success,
                error_type=a.error_type,
                retry_number=a.retry_number,
            )
            for a in att_rows
        ]

        # Tool events
        tool_stmt = (
            select(TelemetryToolEvent)
            .where(TelemetryToolEvent.run_id == run.run_id)
            .order_by(TelemetryToolEvent.attempt_number.asc(), TelemetryToolEvent.event_id.asc())
        )
        tool_rows = session.scalars(tool_stmt).all()
        tool_events = [
            ToolEventRecord(
                event_id=t.event_id,
                tool_name=t.tool_name,
                attempt_number=t.attempt_number,
                schema_valid=t.schema_valid,
                execution_success=t.execution_success,
                latency_ms=t.latency_ms,
                error_class=t.error_class,
            )
            for t in tool_rows
        ]

        # Final outcome
        assert outcome.finalized_at is not None
        outcome_v1 = FinalOutcomeV1(
            completed=outcome.completed,
            first_shot_success=outcome.first_shot_success,
            structured_output_valid=outcome.structured_output_valid,
            tool_success=outcome.tool_success,
            retry_count=outcome.retry_count,
            user_retry_signal=outcome.user_retry_signal,
            user_abandon_signal=outcome.user_abandon_signal,
            user_accept_signal=outcome.user_accept_signal,
            user_correction_signal=outcome.user_correction_signal,
            correction_distance=outcome.correction_distance,
            final_latency_ms=outcome.final_latency_ms,
            final_cost_micro=outcome.final_cost_micro,
            cost_measurement=CostMeasurement(outcome.cost_measurement),
            outcome=outcome.outcome,
            finalized_at=_ensure_utc(outcome.finalized_at),
        )

        # Signals for this run (non-late)
        sig_stmt = (
            select(TelemetryOutcomeSignal)
            .where(
                TelemetryOutcomeSignal.run_id == run.run_id,
                TelemetryOutcomeSignal.late.is_(False),
            )
            .order_by(TelemetryOutcomeSignal.observed_at.asc(), TelemetryOutcomeSignal.signal_id.asc())
        )
        sig_rows = session.scalars(sig_stmt).all()
        signals = [
            SignalRecord(
                signal_id=s.signal_id,
                run_id=s.run_id,
                signal_type=SignalType(s.signal_type),
                strength=SignalStrength(s.strength),
                confidence=s.confidence,
                source=SignalSource(s.source),
                observed_at=_ensure_utc(s.observed_at),
            )
            for s in sig_rows
        ]

        # Feedback for this run (non-late)
        fb_stmt = (
            select(TelemetryFeedback)
            .where(
                TelemetryFeedback.run_id == run.run_id,
                TelemetryFeedback.late.is_(False),
            )
            .order_by(TelemetryFeedback.created_at.asc(), TelemetryFeedback.feedback_id.asc())
        )
        fb_rows = session.scalars(fb_stmt).all()
        feedback = [
            FeedbackRecord(
                feedback_id=f.feedback_id,
                run_id=f.run_id,
                feedback_type=FeedbackType(f.feedback_type),
                original_value_hash=f.original_value_hash,
                sanitized_corrected_value=f.sanitized_corrected_value,
                correction_distance=f.correction_distance,
                created_at=_ensure_utc(f.created_at),
            )
            for f in fb_rows
        ]

        # ExportedRunV1: request_fingerprint is never exported.
        exported_runs.append(
            ExportedRunV1(
                run_id=run.run_id,
                request_id=run.request_id,
                session_id_hash=run.session_id_hash,
                anonymous_actor_id=run.anonymous_actor_id,
                started_at=_ensure_utc(run.started_at),
                completed_at=_ensure_utc(run.completed_at),
                task_domain=run.task_domain,
                tier=run.tier,
                harness_version=run.harness_version,
                prompt_version=run.prompt_version,
                policy_version=run.policy_version,
                feature_schema_version=run.feature_schema_version,
                telemetry_schema_version=run.telemetry_schema_version,
                app_version=run.app_version,
                status=RunStatus(run.status),
                features=json.loads(run.features_json),
                eligible_models=json.loads(run.eligible_models_json),
                eligibility_rejections=json.loads(run.eligibility_rejections_json),
                live_fallback_reason=run.live_fallback_reason,
                shadow_error=run.shadow_error,
                decisions=decisions,
                attempts=attempts,
                tool_events=tool_events,
                outcome=outcome_v1,
                signals=signals,
                feedback=feedback,
            )
        )

    # Convert late items
    exported_late_signals = [
        SignalRecord(
            signal_id=s.signal_id,
            run_id=s.run_id,
            signal_type=SignalType(s.signal_type),
            strength=SignalStrength(s.strength),
            confidence=s.confidence,
            source=SignalSource(s.source),
            observed_at=_ensure_utc(s.observed_at),
        )
        for s in late_signal_rows
    ]

    exported_late_feedback = [
        FeedbackRecord(
            feedback_id=f.feedback_id,
            run_id=f.run_id,
            feedback_type=FeedbackType(f.feedback_type),
            original_value_hash=f.original_value_hash,
            sanitized_corrected_value=f.sanitized_corrected_value,
            correction_distance=f.correction_distance,
            created_at=_ensure_utc(f.created_at),
        )
        for f in late_feedback_rows
    ]

    # 5. Canonical JSON payload sha256
    payload_dict = {
        "runs": [r.model_dump(mode="json") for r in exported_runs],
        "late_signals": [s.model_dump(mode="json") for s in exported_late_signals],
        "late_feedback": [f.model_dump(mode="json") for f in exported_late_feedback],
    }
    payload_canonical_bytes = json.dumps(
        payload_dict, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(payload_canonical_bytes).hexdigest()

    # 6. Assemble TelemetryBatchV1
    batch = TelemetryBatchV1(
        batch_id=batch_id,
        generated_at=_ensure_utc(now),
        producer=ProducerV1(version=producer_version),
        telemetry_schema_version=TELEMETRY_SCHEMA_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        feature_names=list(FEATURE_NAMES_V1),
        payload_sha256=payload_sha256,
        runs=exported_runs,
        late_signals=exported_late_signals,
        late_feedback=exported_late_feedback,
    )

    # 7. Privacy sanitization validation (fail-closed: write nothing, mark nothing on failure)
    sanitizer.validate_export(batch.model_dump(mode="json", by_alias=True))

    # 8. Write files to out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    final_file = out_dir / f"telemetry-batch-{batch_id}.json"
    sha_file = out_dir / f"telemetry-batch-{batch_id}.json.sha256"

    batch_json_bytes = batch.model_dump_json(by_alias=True, indent=2).encode("utf-8")

    fd, tmp_path_str = tempfile.mkstemp(dir=out_dir, prefix="batch_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(batch_json_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path_str, final_file)
    except Exception:
        if os.path.exists(tmp_path_str):
            os.remove(tmp_path_str)
        raise

    file_bytes = final_file.read_bytes()
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()
    sha_file.write_text(f"{file_sha256}  {final_file.name}\n", encoding="utf-8")

    # 9. Mark exported rows in database
    for run, _ in run_pairs:
        run.export_batch_id = batch_id
    for s in late_signal_rows:
        s.export_batch_id = batch_id
    for fb in late_feedback_rows:
        fb.export_batch_id = batch_id

    total_signals = sum(len(r.signals) for r in exported_runs) + len(exported_late_signals)
    total_feedback = sum(len(r.feedback) for r in exported_runs) + len(exported_late_feedback)

    existing_batch = session.get(TelemetryExportBatch, batch_id)
    if existing_batch is None:
        export_batch_row = TelemetryExportBatch(
            batch_id=batch_id,
            created_at=now,
            run_count=len(exported_runs),
            signal_count=total_signals,
            feedback_count=total_feedback,
            payload_sha256=payload_sha256,
            path=str(final_file),
        )
        session.add(export_batch_row)
    else:
        existing_batch.path = str(final_file)
        existing_batch.payload_sha256 = payload_sha256
        existing_batch.run_count = len(exported_runs)
        existing_batch.signal_count = total_signals
        existing_batch.feedback_count = total_feedback
    session.flush()

    # 10. Metrics
    METRICS.inc("telemetry_export_batches_total")
    oldest_unexp = session.scalar(
        select(TelemetryRun.completed_at)
        .join(TelemetryRunOutcome, TelemetryRun.run_id == TelemetryRunOutcome.run_id)
        .where(
            TelemetryRunOutcome.finalized_at.is_not(None),
            TelemetryRun.export_batch_id.is_(None),
        )
        .order_by(TelemetryRun.completed_at.asc())
        .limit(1)
    )
    oldest_age_s = max(0.0, (now - oldest_unexp).total_seconds()) if oldest_unexp is not None else 0.0
    METRICS.set_gauge("telemetry_oldest_unexported_age_s", oldest_age_s)

    return ExportResult(
        batch_id=batch_id,
        path=final_file,
        run_count=len(exported_runs),
        signal_count=total_signals,
        feedback_count=total_feedback,
        payload_sha256=payload_sha256,
    )
