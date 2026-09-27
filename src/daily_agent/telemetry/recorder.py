"""Maps request-path observations onto the RunRecord telemetry contract.

Pure functions only: the API collects timings/attempts/tool observations and calls
:func:`build_run_record`; emission happens through the collector.
"""

from __future__ import annotations

import difflib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from daily_agent import __version__
from daily_agent.harness.versioning import HARNESS_VERSION
from daily_agent.policy_artifacts.schema import HarnessBundleV1
from daily_agent.routing.models import (
    FEATURE_NAMES_V1,
    FEATURE_SCHEMA_VERSION,
    RoutingDecision,
    RoutingOutcome,
)
from daily_agent.services import AttemptOutcome
from daily_agent.telemetry.events import (
    AttemptRecord,
    CostMeasurement,
    DecisionRecord,
    FeedbackRecord,
    FeedbackType,
    ImmediateOutcome,
    RunRecord,
    RunStatus,
    ToolEventRecord,
)
from daily_agent.telemetry.pseudonym import value_hash
from daily_agent.telemetry.sanitizer import sanitize_free_text

# Bound on the text compared for correction distance (keeps difflib cost small).
_MAX_COMPARED_CHARS = 2_000
# Recorded when no policy produced a decision (no eligible model, routing crashed).
NO_POLICY_VERSION = "none"


@dataclass(frozen=True)
class ToolObservation:
    tool_name: str
    schema_valid: bool
    execution_success: bool
    latency_ms: int
    error_class: str | None = None


def _decision(
    decision: RoutingDecision, *, shadow: bool, live_model: str | None, at: datetime
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision.decision_id,
        policy_version=decision.policy_version,
        feature_schema_version=decision.feature_schema_version,
        algorithm=decision.algorithm,
        selected_model=decision.selected_model,
        selected_provider=decision.selected_provider,
        selection_probability=decision.selection_probability,
        action_probabilities=dict(decision.action_probabilities),
        eligible_models=list(decision.eligible_models),
        exploration=decision.exploration,
        shadow=shadow,
        agreed_with_live=(decision.selected_model == live_model) if shadow else None,
        created_at=at,
    )


def _attempts(attempts: Sequence[AttemptOutcome], decision_id: str | None) -> list[AttemptRecord]:
    records: list[AttemptRecord] = []
    failures_before = 0
    for attempt in attempts:
        records.append(
            AttemptRecord(
                attempt_id=str(uuid.uuid4()),
                decision_id=decision_id,
                provider=attempt.provider,
                model=attempt.model,
                operation=attempt.operation,
                latency_ms=attempt.latency_ms,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                estimated_cost_micro=attempt.cost_micro,
                cost_measurement=CostMeasurement(attempt.cost_measurement),
                success=attempt.success,
                error_type=attempt.error_type,
                # Number of failed attempts that preceded this one within the run.
                retry_number=failures_before,
            )
        )
        if not attempt.success:
            failures_before += 1
    return records


def build_run_record(
    *,
    run_id: str,
    request_id: str,
    actor_id: str,
    fingerprint: str | None,
    started_at: datetime,
    completed_at: datetime,
    tier: str,
    task_domain: str,
    harness: HarnessBundleV1,
    routing: RoutingOutcome | None,
    rejections: dict[str, tuple[str, ...]] | None,
    status: RunStatus,
    attempts: Sequence[AttemptOutcome],
    tools: Sequence[ToolObservation],
    outcome: str | None,
    final_latency_ms: int,
    final_cost_micro: int | None,
    live_fallback_reason: str | None = None,
    fallback_decision: RoutingDecision | None = None,
) -> RunRecord:
    """``fallback_decision`` records the baseline route served when routing itself failed."""
    decisions: list[DecisionRecord] = []
    live_id: str | None = None
    features: dict[str, float] = {}
    eligible: list[str] = []
    fallback = live_fallback_reason
    shadow_error: str | None = None
    policy_version = NO_POLICY_VERSION
    if routing is not None:
        live_id = routing.live.decision_id
        policy_version = routing.live.policy_version
        decisions.append(_decision(routing.live, shadow=False, live_model=None, at=started_at))
        if routing.shadow is not None:
            decisions.append(
                _decision(
                    routing.shadow,
                    shadow=True,
                    live_model=routing.live.selected_model,
                    at=started_at,
                )
            )
        features = dict(zip(FEATURE_NAMES_V1, routing.feature_vector, strict=True))
        eligible = list(routing.eligibility.eligible_models)
        rejections = routing.eligibility.rejections
        fallback = fallback or routing.live_fallback_reason
        shadow_error = routing.shadow_error
    elif fallback_decision is not None:
        live_id = fallback_decision.decision_id
        policy_version = fallback_decision.policy_version
        decisions.append(_decision(fallback_decision, shadow=False, live_model=None, at=started_at))
        eligible = list(fallback_decision.eligible_models)

    attempt_records = _attempts(attempts, live_id)
    choice = [a for a in attempts if a.operation == "choice"]
    if final_cost_micro is None:
        measurement = CostMeasurement.UNKNOWN
    elif any(a.provider != "local" for a in attempts):
        measurement = CostMeasurement.MEASURED
    else:
        measurement = CostMeasurement.FIXED
    immediate = ImmediateOutcome(
        completed=status == RunStatus.COMPLETED,
        first_shot_success=bool(attempts)
        and all(a.success for a in attempts)
        and outcome == "ACCEPT",
        structured_output_valid=choice[0].success if choice else None,
        tool_success=all(t.execution_success for t in tools) if tools else None,
        retry_count=sum(not a.success for a in attempts),
        final_latency_ms=final_latency_ms,
        final_cost_micro=final_cost_micro,
        cost_measurement=measurement,
        outcome=outcome,
    )
    return RunRecord(
        run_id=run_id,
        request_id=request_id,
        session_id_hash=None,  # Karmi has no conversation-session concept yet.
        anonymous_actor_id=actor_id,
        request_fingerprint=fingerprint,
        started_at=started_at,
        completed_at=completed_at,
        task_domain=task_domain,
        tier=tier,
        harness_version=HARNESS_VERSION,
        prompt_version=harness.prompts.prompt_version,
        policy_version=policy_version,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        app_version=__version__,
        status=status,
        features=features,
        eligible_models=eligible,
        eligibility_rejections={model: list(codes) for model, codes in (rejections or {}).items()},
        live_fallback_reason=fallback,
        shadow_error=shadow_error,
        decisions=decisions,
        attempts=attempt_records,
        tool_events=[
            ToolEventRecord(
                event_id=str(uuid.uuid4()),
                tool_name=tool.tool_name,
                attempt_number=1,
                schema_valid=tool.schema_valid,
                execution_success=tool.execution_success,
                latency_ms=tool.latency_ms,
                error_class=tool.error_class,
            )
            for tool in tools
        ],
        outcome=immediate,
    )


def build_feedback_record(
    *,
    run_id: str,
    feedback_type: str,
    original_response: str | None,
    corrected_text: str | None,
    key: bytes,
    store_text: bool,
) -> FeedbackRecord:
    """Explicit user feedback reduced to hashes and a distance; text only when opted in.

    The id is derived from (run, feedback type), so each run's owner contributes at most
    one record, and one strong signal, per feedback type; repeats are writer no-ops.
    """
    distance: float | None = None
    if feedback_type == FeedbackType.CORRECTION and corrected_text and original_response:
        ratio = difflib.SequenceMatcher(
            None,
            original_response[:_MAX_COMPARED_CHARS],
            corrected_text[:_MAX_COMPARED_CHARS],
            autojunk=False,
        ).ratio()
        distance = round(1.0 - ratio, 4)
    stored = sanitize_free_text(corrected_text) if store_text and corrected_text else None
    kind = FeedbackType(feedback_type)
    return FeedbackRecord(
        feedback_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"karmi-feedback-v1:{run_id}:{kind.value}")),
        run_id=run_id,
        feedback_type=kind,
        original_value_hash=value_hash(key, original_response) if original_response else None,
        sanitized_corrected_value=stored,
        correction_distance=distance,
        created_at=datetime.now(UTC),
    )
