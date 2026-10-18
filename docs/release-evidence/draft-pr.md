# Draft PR (local only, not opened): Free-model gateway, tier quotas, feedback loop, tester build

Base: `readiness-harness` working tree as of 0c3d11e. Head: `mvp-gateway`.

## What
- `daily_agent/gateway/`: model-registry.v1 loader (free models only), OpenRouter and OpenCode adapters,
  rules router (tier class floors, task type, context, privacy, escalation), circuit breaker and cooldowns,
  kill switch. `fake_generate` replaced by classify -> route -> generate; deterministic demo path kept.
- Plans carry model classes, INR price labels and daily token quotas; reserve/settle/release extended with token holds.
- Feedback: ratings and regenerate routes, migration `3c4d5e6f7081`; sanitized feedback in TelemetryBatchV1.
- Hardening: per-user rate limit, log redaction, real cutover check in `scripts/readiness_config.py`.
- Flutter: thumbs, reasons, regenerate, versioned tester notice.

## Verify
See `docs/release-evidence/mvp-tester-release-2026-10-19.md`. Not verified: live models, Docker, physical phone.

## Review notes
Seed registry classes are unreviewed; quotas provisional; notice needs legal review; single-replica assumption.
