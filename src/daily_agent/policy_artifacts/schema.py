"""PolicyBundleV1 contract (ADR-0003): the only artifact format Karmi accepts from Parakh.

A bundle is a directory of JSON documents. Nothing in it is executable: no pickles, no
templates evaluated with ``str.format``, no code. Every model uses ``extra="forbid"``.

Layout (exactly these paths; any other file rejects the bundle)::

    manifest.json            PolicyBundleManifestV1
    routing_policy.json      LinUCBPolicyV1
    router_metadata.json     RouterMetadataV1 (includes cross-implementation self-test cases)
    feature_schema.json      RoutingFeatureSchemaV1 (must equal Karmi's FEATURE_NAMES_V1)
    evaluation_summary.json  EvaluationSummaryV1
    provenance.json          ProvenanceV1
    checksums.json           ChecksumsV1 (sha256 of every other file except signature.sig)
    signature.sig            base64 Ed25519 signature over the raw bytes of checksums.json
    harness/prompts.json           optional HarnessPromptsV1 (iff manifest.harness_included)
    harness/recovery_policy.json   optional RecoveryPolicyV1 (iff manifest.harness_included)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

BUNDLE_SCHEMA = "PolicyBundleV1"

MANIFEST = "manifest.json"
ROUTING_POLICY = "routing_policy.json"
ROUTER_METADATA = "router_metadata.json"
FEATURE_SCHEMA = "feature_schema.json"
EVALUATION_SUMMARY = "evaluation_summary.json"
PROVENANCE = "provenance.json"
CHECKSUMS = "checksums.json"
SIGNATURE = "signature.sig"
HARNESS_PROMPTS = "harness/prompts.json"
HARNESS_RECOVERY = "harness/recovery_policy.json"

REQUIRED_FILES: frozenset[str] = frozenset(
    {
        MANIFEST,
        ROUTING_POLICY,
        ROUTER_METADATA,
        FEATURE_SCHEMA,
        EVALUATION_SUMMARY,
        PROVENANCE,
        CHECKSUMS,
        SIGNATURE,
    }
)
HARNESS_FILES: frozenset[str] = frozenset({HARNESS_PROMPTS, HARNESS_RECOVERY})
# Upper bound on any single bundle file; larger files are rejected before parsing.
MAX_FILE_BYTES = 2_000_000

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")]
Version = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")]
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("non-finite number")
    return value


Finite = Annotated[float, AfterValidator(_finite)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyBundleManifestV1(_Strict):
    schema_: Literal["PolicyBundleV1"] = Field(alias="schema")
    artifact_version: Version
    policy_schema_version: Literal["LinUCBPolicyV1"]
    feature_schema_version: Identifier
    algorithm: Literal["linucb"]
    min_karmi_version: SemVer
    # Route ids the policy scores. Every id must exist in Karmi's model registry.
    model_registry: list[Identifier] = Field(min_length=1, max_length=64)
    evaluation_run_ids: list[Identifier] = Field(default_factory=list, max_length=256)
    created_at: AwareDatetime
    previous_compatible_version: Version | None = None
    harness_included: bool = False
    # Optional narrowing of tier entitlement per route. Can only restrict, never widen,
    # Karmi's registry entitlements (verifier enforces the subset rule).
    tier_restrictions: dict[Identifier, list[Identifier]] = Field(default_factory=dict)


class LinUCBArmV1(_Strict):
    theta: list[Finite] = Field(min_length=1, max_length=256)
    a_inv: list[list[Finite]] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _square(self) -> LinUCBArmV1:
        size = len(self.theta)
        if len(self.a_inv) != size or any(len(row) != size for row in self.a_inv):
            raise ValueError("a_inv must be a square matrix matching theta")
        return self


class LinUCBPolicyV1(_Strict):
    schema_: Literal["LinUCBPolicyV1"] = Field(alias="schema")
    feature_schema_version: Identifier
    alpha: Finite = Field(ge=0.0, le=100.0)
    arms: dict[Identifier, LinUCBArmV1] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _uniform_dimension(self) -> LinUCBPolicyV1:
        sizes = {len(arm.theta) for arm in self.arms.values()}
        if len(sizes) != 1:
            raise ValueError("all arms must share one feature dimension")
        return self

    @property
    def dimension(self) -> int:
        return len(next(iter(self.arms.values())).theta)


class RoutingFeatureSchemaV1(_Strict):
    schema_: Literal["RoutingFeatureSchemaV1"] = Field(alias="schema")
    feature_schema_version: Identifier
    feature_names: list[Identifier] = Field(min_length=1, max_length=256)


class SelfTestCaseV1(_Strict):
    feature_vector: list[Finite] = Field(min_length=1, max_length=256)
    eligible_models: list[Identifier] = Field(min_length=1, max_length=64)
    # Argmax Parakh computed for this vector in exploitation mode; Karmi must agree.
    expected_model: Identifier


class RouterMetadataV1(_Strict):
    schema_: Literal["RouterMetadataV1"] = Field(alias="schema")
    description: str = Field(default="", max_length=500)
    self_test_cases: list[SelfTestCaseV1] = Field(min_length=1, max_length=512)


class EvaluationSummaryV1(_Strict):
    schema_: Literal["EvaluationSummaryV1"] = Field(alias="schema")
    evaluation_run_ids: list[Identifier] = Field(default_factory=list, max_length=256)
    metrics: dict[Identifier, Finite] = Field(default_factory=dict, max_length=256)
    # Parakh's regression verdict. Promotion (not staging/shadow) requires True.
    passed_regression: bool


class ProvenanceV1(_Strict):
    schema_: Literal["ProvenanceV1"] = Field(alias="schema")
    producer_repo: Identifier
    producer_version: Identifier
    telemetry_batch_ids: list[Identifier] = Field(default_factory=list, max_length=10_000)
    benchmark_ids: list[Identifier] = Field(default_factory=list, max_length=1_000)


class ChecksumsV1(_Strict):
    schema_: Literal["ChecksumsV1"] = Field(alias="schema")
    algorithm: Literal["sha256"]
    files: dict[str, Sha256Hex] = Field(min_length=1, max_length=32)


INTENT_LABELS: tuple[str, ...] = ("query_memory", "store_memory", "create_task", "general_draft")
NOTE_REF_PLACEHOLDER = "{note_ref}"

PromptText = Annotated[str, StringConstraints(min_length=1, max_length=2_000)]


class HarnessPromptsV1(_Strict):
    """Prompt text only. Labels/criteria keys are fixed by Karmi and cannot change here."""

    schema_: Literal["HarnessPromptsV1"] = Field(alias="schema")
    prompt_version: Version
    intent_instructions: PromptText
    intent_criteria: dict[str, PromptText]
    # Plain substitution of NOTE_REF_PLACEHOLDER (never str.format).
    relevance_instructions_template: PromptText
    relevance_criteria: list[PromptText] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _fixed_contract(self) -> HarnessPromptsV1:
        if set(self.intent_criteria) != set(INTENT_LABELS):
            raise ValueError("intent_criteria keys must be exactly the supported intents")
        if self.relevance_instructions_template.count(NOTE_REF_PLACEHOLDER) != 1:
            raise ValueError("relevance template must contain the note placeholder once")
        return self


class RecoveryPolicyV1(_Strict):
    schema_: Literal["RecoveryPolicyV1"] = Field(alias="schema")
    # Provider retries per call; Karmi clamps to its compiled hard maximum.
    max_provider_retries: int = Field(ge=0, le=1)
    # When the live route fails, answer from the deterministic local route.
    fallback_to_local: bool = True


class HarnessBundleV1(_Strict):
    prompts: HarnessPromptsV1
    recovery: RecoveryPolicyV1


class LoadedBundle(_Strict):
    """A fully verified bundle, parsed into memory. Only verifier.verify_bundle builds it."""

    manifest: PolicyBundleManifestV1
    policy: LinUCBPolicyV1
    metadata: RouterMetadataV1
    feature_schema: RoutingFeatureSchemaV1
    evaluation: EvaluationSummaryV1
    provenance: ProvenanceV1
    harness: HarnessBundleV1 | None
    # sha256 of checksums.json: a stable content identity for audit records.
    content_sha256: Sha256Hex
    verified_at: datetime
