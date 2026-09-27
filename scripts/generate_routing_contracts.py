"""Regenerate the JSON Schemas exchanged with Parakh from Karmi's frozen models."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def generate(root: Path) -> None:
    # Like scripts/tasks.py, use this checkout even with a different editable install.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from daily_agent.policy_artifacts.schema import (
        ChecksumsV1,
        EvaluationSummaryV1,
        HarnessPromptsV1,
        LinUCBPolicyV1,
        PolicyBundleManifestV1,
        ProvenanceV1,
        RecoveryPolicyV1,
        RouterMetadataV1,
        RoutingFeatureSchemaV1,
    )
    from daily_agent.telemetry.events import TelemetryBatchV1

    contracts = {
        "TelemetryBatchV1": TelemetryBatchV1,
        "PolicyBundleV1.manifest": PolicyBundleManifestV1,
        "PolicyBundleV1.routing_policy": LinUCBPolicyV1,
        "PolicyBundleV1.feature_schema": RoutingFeatureSchemaV1,
        "PolicyBundleV1.router_metadata": RouterMetadataV1,
        "PolicyBundleV1.evaluation_summary": EvaluationSummaryV1,
        "PolicyBundleV1.provenance": ProvenanceV1,
        "PolicyBundleV1.checksums": ChecksumsV1,
        "PolicyBundleV1.harness_prompts": HarnessPromptsV1,
        "PolicyBundleV1.harness_recovery_policy": RecoveryPolicyV1,
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, model in contracts.items():
        path = root / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(by_alias=True), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )



if __name__ == "__main__":
    generate(Path(__file__).resolve().parent.parent / "docs" / "contracts")
