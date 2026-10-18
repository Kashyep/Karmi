# OpenCode AI routing and evaluation readiness

Date: 2026-10-10  
Scope: read-only audit of the current request path, Parakh router, and ModelLab harness. No model
API key was read, no external model request was made, and no paid/free API usage occurred.

## Decision

**Automatic best-model routing is not implemented or working.** Karmi's current message generation
is deterministic demo behavior. The only runtime routing choice is static (`karmi/fake-economy`
or a TypeSafe structured-classification route); the Parakh policy is shadow-only and cannot change
the executed model. There is no OpenCode Zen adapter or live model comparison run.

**The evaluation harness is usable for offline smoke checks and importing results, but is not ready
to select a best model.** The seed suite validates and the existing Python tests pass, but no live
provider runner, multi-model comparison, semantic grading/review workflow, or statistically
supported router evidence is present. Current rubric grades abstain by design.

## Evidence

- `src/daily_agent/services.py::fake_generate` echoes a draft as `Draft ready: …`; it does not call
  a general text-generation model. When `live_models_enabled` is true, TypeSafe classifies the
  request and scores note relevance, then Karmi still formats a fixed response.
- `src/daily_agent/parakh/routing.py::eligible_actions` offers only the local fake action and
  `typesafe/system-one`. `record_routing_evidence` records the executed action with propensity 1.0.
- `src/daily_agent/parakh/receiver.py::shadow_select` records a candidate choice beside the static
  route. `transition` explicitly refuses `canary` and `production`; shadow selection does not
  affect user traffic.
- `benchmarks/seed_cases.jsonl` contains 60 validated authored cases (36 train, 12 calibration, 12
  holdout). `ModelLab` can validate/export/import, fake-run, grade exact JSON, render local reports
  and issue a draft recommendation. It does not invoke models. Rubric answers abstain and need
  human/calibrated review. The benchmark specification says this seed bank is a smoke-test baseline,
  not statistical evidence.
- `scripts/readiness_config.py` deliberately marks `synthetic_provider_disabled` as failing while
  chat falls back to `fake_generate`.
- Automated check on this date: seed validation reported 60 valid cases; the targeted Parakh and
  ModelLab tests passed (24 passed). These checks establish local behavior, not comparative model
  quality.

## OpenCode implications

OpenCode Zen's current official catalog exposes `GET https://opencode.ai/zen/v1/models`; the
catalog lists several free models, but its documentation labels these free offers temporary and
states other models are pay-as-you-go. Some free-model terms permit prompt/completion use for model
improvement, and the NVIDIA free endpoints prohibit personal or confidential input. Consequently,
the first live experiment must use only models allowed by an explicit data policy; no real customer
notes should be used for a free-model bake-off by default.

Sources checked 2026-10-10: [OpenCode Zen API/model catalog and pricing](https://docs.opencode.ai/docs/zen/).

## Required before claiming automatic selection

1. Add a server-side OpenCode adapter with dynamic catalog refresh, a stable allowlist, strict input
   and output limits, request timeouts, clear per-model pricing/provenance, and a free-only filter
   that fails closed when prices or data terms are unknown.
2. Add a protected, candidate-only harness runner that excludes answer keys and split metadata,
   records provider-reported usage/latency, and requires a finite preflight cap. Preserve fixture-only
   execution as the CI path.
3. Expand independent calibration/holdout families; manually review semantic/rubric grades. Compare
   model quality, critical failures, latency and actual cost by task family, not one overall score.
4. Make runtime policy selection evidence-based and start in shadow mode. Test the chosen policy
   against a fixed-model baseline, then separately authorize a controlled canary.
5. Decide which free-model data terms are acceptable before routing customer content to them. Keep
   models with training-improvement or no-confidential-data restrictions out of private-note flows.

Until these gates pass, keep `live_models_enabled=false`; do not advertise chat as AI-generated or
call the model router production-ready.
