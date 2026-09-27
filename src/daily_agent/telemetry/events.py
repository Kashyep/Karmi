"""Telemetry records and the TelemetryBatchV1 export contract (ADR-0003).

Every record is structured and ``extra="forbid"``. Free text is structurally impossible
except ``FeedbackRecord.sanitized_corrected_value``, which is opt-in and passes through
:mod:`daily_agent.telemetry.sanitizer` before it is constructed. Identifier-like fields
are pattern-constrained so arbitrary user text cannot be smuggled through them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

TELEMETRY_SCHEMA_VERSION = "telemetry-v1"
BATCH_SCHEMA: Literal["TelemetryBatchV1"] = "TelemetryBatchV1"
PRODUCER_REPO: Literal["kashyep-karmi"] = "kashyep-karmi"

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")]
Uuid = Annotated[str, StringConstraints(pattern=r"^[0-9a-f-]{36}$")]
HexDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Priority(StrEnum):
    # Never intentionally dropped: spilled to the local spool when the queue is full.
    MANDATORY = "mandatory"
    # May be dropped under backpressure.
    OPTIONAL = "optional"


class RunStatus(StrEnum):
    COMPLETED = "completed"
    DEFERRED = "deferred"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    NO_ELIGIBLE_MODEL = "no_eligible_model"


class CostMeasurement(StrEnum):
    MEASURED = "measured"
    FIXED = "fixed"
    UNKNOWN = "unknown"


class SignalType(StrEnum):
    RETRY = "retry"
    ACCEPT = "accept"
    REJECT = "reject"
    CORRECTION = "correction"
    PREFERENCE = "preference"
    CHANGED_INTENT = "changed_intent"
    EXECUTION_FAILURE = "execution_failure"
    TASK_COMPLETED = "task_completed"
    NO_FOLLOWUP_AFTER_ASK = "no_followup_after_ask"


class SignalStrength(StrEnum):
    STRONG = "strong"
    WEAK = "weak"


class SignalSource(StrEnum):
    EXPLICIT_FEEDBACK = "explicit_feedback"
    DERIVED = "derived"


class FeedbackType(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    CORRECTION = "correction"
    PREFERENCE = "preference"
    CHANGED_INTENT = "changed_intent"


class DecisionRecord(_Strict):
    decision_id: Uuid
    policy_version: Identifier
    feature_schema_version: Identifier
    algorithm: Identifier
    selected_model: Identifier
    selected_provider: Identifier
    selection_probability: Probability
    action_probabilities: dict[Identifier, Probability]
    eligible_models: list[Identifier]
    exploration: bool
    shadow: bool
    # Shadow rows only: whether the shadow policy picked the executed live model.
    agreed_with_live: bool | None = None
    created_at: AwareDatetime


class AttemptRecord(_Strict):
    attempt_id: Uuid
    decision_id: Uuid | None
    provider: Identifier
    model: Identifier
    operation: Identifier
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_micro: int | None = Field(default=None, ge=0)
    cost_measurement: CostMeasurement
    success: bool
    error_type: Identifier | None = None
    retry_number: int = Field(ge=0)


class ToolEventRecord(_Strict):
    event_id: Uuid
    tool_name: Identifier
    attempt_number: int = Field(ge=1)
    schema_valid: bool
    execution_success: bool
    latency_ms: int = Field(ge=0)
    error_class: Identifier | None = None


class ImmediateOutcome(_Strict):
    completed: bool
    first_shot_success: bool
    structured_output_valid: bool | None
    tool_success: bool | None
    retry_count: int = Field(ge=0)
    final_latency_ms: int = Field(ge=0)
    final_cost_micro: int | None = Field(default=None, ge=0)
    cost_measurement: CostMeasurement
    outcome: Identifier | None


class RunRecord(_Strict):
    kind: Literal["run"] = "run"
    run_id: Uuid
    request_id: Uuid
    session_id_hash: HexDigest | None
    anonymous_actor_id: HexDigest
    # Keyed HMAC of the request text used only for in-Karmi retry detection. Never exported.
    request_fingerprint: HexDigest | None
    started_at: AwareDatetime
    completed_at: AwareDatetime
    task_domain: Identifier
    tier: Identifier
    harness_version: Identifier
    prompt_version: Identifier
    policy_version: Identifier
    feature_schema_version: Identifier
    telemetry_schema_version: Identifier = TELEMETRY_SCHEMA_VERSION
    app_version: Identifier
    status: RunStatus
    features: dict[Identifier, float]
    eligible_models: list[Identifier]
    eligibility_rejections: dict[Identifier, list[Identifier]]
    live_fallback_reason: Identifier | None = None
    shadow_error: Identifier | None = None
    decisions: list[DecisionRecord]
    attempts: list[AttemptRecord]
    tool_events: list[ToolEventRecord]
    outcome: ImmediateOutcome


class SignalRecord(_Strict):
    kind: Literal["signal"] = "signal"
    signal_id: Uuid
    run_id: Uuid
    signal_type: SignalType
    strength: SignalStrength
    confidence: Probability
    source: SignalSource
    observed_at: AwareDatetime


class FeedbackRecord(_Strict):
    kind: Literal["feedback"] = "feedback"
    feedback_id: Uuid
    run_id: Uuid
    feedback_type: FeedbackType
    original_value_hash: HexDigest | None
    # Only when DAILY_AGENT_TELEMETRY_STORE_CORRECTION_TEXT is enabled, after sanitisation.
    sanitized_corrected_value: str | None = Field(default=None, max_length=2_000)
    correction_distance: Probability | None = None
    created_at: AwareDatetime


class OpsEventRecord(_Strict):
    kind: Literal["ops"] = "ops"
    event_id: Uuid
    event_type: Identifier
    detail: Identifier | None = None
    policy_version: Identifier | None = None
    created_at: AwareDatetime


TelemetryEvent = Annotated[
    RunRecord | SignalRecord | FeedbackRecord | OpsEventRecord, Field(discriminator="kind")
]


def priority_of(event: RunRecord | SignalRecord | FeedbackRecord | OpsEventRecord) -> Priority:
    return Priority.OPTIONAL if isinstance(event, OpsEventRecord) else Priority.MANDATORY


# ---- Export contract -------------------------------------------------------------------


class FinalOutcomeV1(_Strict):
    completed: bool
    first_shot_success: bool
    structured_output_valid: bool | None
    tool_success: bool | None
    retry_count: int = Field(ge=0)
    user_retry_signal: bool
    user_abandon_signal: bool
    user_accept_signal: bool
    user_correction_signal: bool
    correction_distance: Probability | None
    final_latency_ms: int = Field(ge=0)
    final_cost_micro: int | None = Field(default=None, ge=0)
    cost_measurement: CostMeasurement
    outcome: Identifier | None
    finalized_at: AwareDatetime


class ExportedRunV1(_Strict):
    run_id: Uuid
    request_id: Uuid
    session_id_hash: HexDigest | None
    anonymous_actor_id: HexDigest
    started_at: AwareDatetime
    completed_at: AwareDatetime
    task_domain: Identifier
    tier: Identifier
    harness_version: Identifier
    prompt_version: Identifier
    policy_version: Identifier
    feature_schema_version: Identifier
    telemetry_schema_version: Identifier
    app_version: Identifier
    status: RunStatus
    features: dict[Identifier, float]
    eligible_models: list[Identifier]
    eligibility_rejections: dict[Identifier, list[Identifier]]
    live_fallback_reason: Identifier | None
    shadow_error: Identifier | None
    decisions: list[DecisionRecord]
    attempts: list[AttemptRecord]
    tool_events: list[ToolEventRecord]
    outcome: FinalOutcomeV1
    signals: list[SignalRecord]
    feedback: list[FeedbackRecord]


class ProducerV1(_Strict):
    repo: Literal["kashyep-karmi"] = PRODUCER_REPO
    version: Identifier


class TelemetryBatchV1(_Strict):
    schema_: Literal["TelemetryBatchV1"] = Field(default=BATCH_SCHEMA, alias="schema")
    batch_id: HexDigest
    generated_at: AwareDatetime
    producer: ProducerV1
    telemetry_schema_version: Identifier = TELEMETRY_SCHEMA_VERSION
    feature_schema_version: Identifier
    feature_names: list[Identifier]
    # sha256 over canonical JSON of {"runs", "late_signals", "late_feedback"}.
    payload_sha256: HexDigest
    runs: list[ExportedRunV1]
    # Signals/feedback that arrived after their run was already exported.
    late_signals: list[SignalRecord] = Field(default_factory=list)
    late_feedback: list[FeedbackRecord] = Field(default_factory=list)
