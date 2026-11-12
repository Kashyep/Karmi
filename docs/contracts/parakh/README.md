# Parakh exchange (TelemetryBatchV1 out, PolicyBundleV1 in)

Parakh is the offline optimization lab. Karmi never imports Parakh code: the JSON schemas in this
directory are copied from Parakh `contracts/`, byte-identical to Parakh main 6ef18fc (checked with cmp);
`src/daily_agent/parakh/` holds Karmi's side. Nothing here changes which route serves a request.

## Telemetry out

Every `POST /v1/messages` run writes, in the run's own transaction:

- `routing_records`: tier (contract spelling: plan `parth` → tier `part`), task domain (from
  intent/heuristics), feature-only routing context, attempt metrics, latency and cost micro-units.
- `routing_decisions`: the executed live decision (`karmi-static-v1`, probability 1.0, no
  exploration) and, when a bundle is in SHADOW, the bundle's own decision with its exact probability.

User feedback is exported in the `feedback` array: explicit ratings (`feedback_type: "rating"`,
`sanitized_corrected_value` set to the rating token, and `correction_kind_hint` set to the reason token)
and retry/regenerate links (`feedback_type: "retry"`, `correction_kind_hint` set to the regenerate reason token).
Run `outcome` records summarize these through `user_accept_signal` and `user_retry_signal`. No message or
response text, note content, account/user ids or client idempotency keys are ever exported.

`karmi-parakh export-telemetry --start ISO --end ISO --out batch.json` writes TelemetryBatchV1 for
runs completed in `[start, end)`. Run and decision ids are prefixed hex (`run-...`, `dec-...`, `att-...`,
`fb-...`). The batch id and `generated_at` are derived from the window and content, so re-exporting an
unchanged window is byte-identical and Parakh imports it idempotently. Costs are Karmi's synthetic micro-units
/ 10⁶ with currency `XTS` (no approved currency), which Parakh deliberately does not normalize as USD.

## Bundles in

Karmi states: `received → staged → shadow → retired`. Every transition needs `--actor` and
`--reason` and appends a `policy_bundle_events` row.

```bash
export DAILY_AGENT_PARAKH_TRUSTED_PUBLIC_KEYS='["<parakh public key hex>"]'
karmi-parakh receive-bundle /path/to/policy-YYYY.MM.DD.N --actor NAME --reason WHY
karmi-parakh stage   policy-YYYY.MM.DD.N --actor NAME --reason WHY
karmi-parakh shadow  policy-YYYY.MM.DD.N --actor NAME --reason WHY   # retires any older shadow bundle
karmi-parakh bundles
```

`receive-bundle` verifies the Ed25519 signature over `checksums.json` against the configured keys,
every file's SHA-256 with no extra files or symlinks, artifact/policy schema, `routing-features.v1`,
that every action is known to Karmi: static routes (`karmi/fake-economy`, `typesafe/system-one`) plus
every model in the gateway registry (`src/daily_agent/gateway/data/model_registry.json`, e.g. `openrouter/...`, `opencode/...`),
the minimum Karmi version and a parameter self-test. It then stores a read-only copy under
`data_dir/policy_bundles/` and re-verifies it before `stage`/`shadow`. With no trusted keys every
bundle is refused.

SHADOW only records the candidate's choice; a failing shadow evaluation is logged and skipped, never
failing the request. `canary` and `production` would change live traffic and are refused: they need
a separately authorized rollout design.

## Contract check

Cross-repo compatibility is verified against a local Parakh checkout:

```bash
PARAKH_DIR=../Parakh python scripts/tasks.py parakh-contract
```

The check requires the two schema copies (`telemetry_batch_v1.schema.json` and `policy_bundle_v1.schema.json`)
to be byte-identical to Parakh's `contracts/` and runs Parakh's cross-repo test suite
(`tests/test_cross_repo_readiness.py`) under Karmi's Python environment with Karmi's `src` on the path.

In CI, the `.github/workflows/parakh-contract.yml` workflow runs this contract check on pull requests and
pushes affecting contract schemas, routing code, gateway configuration, migrations, or contract tests.

## Known limits

- Live routing is static: logged propensity is 1.0 and, with live models off, one action is
  eligible. Parakh's off-policy evaluation therefore has no support for alternative actions; learning
  a better router needs a separately authorized, budgeted exploration policy.
- While user feedback is exported (ratings and retry/regenerate links with sanitized tokens, never message text),
  free-text user corrections are not captured and unrated runs still rely primarily on the run completion outcome.
- Parakh cannot verify a bundle over Karmi's real actions until those actions have authorized pilot
  evidence on its frozen 60-case benchmark; Parakh's verifier fails closed without it.
