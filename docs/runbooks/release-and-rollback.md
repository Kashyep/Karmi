# Release and rollback runbook

## Preflight

- Exact candidate commit and migration revision recorded.
- `test-release` passes, including disposable PostgreSQL/Redis checks.
- Production settings validate with finite approved budgets and non-development secrets.
- Live provider rates/allowlists, payment mode and channel eligibility are separately approved.
- Database backup/restore evidence exists; alerts and spending kill switch have an owner.

## Roll forward

Apply backward-compatible migrations before switching application traffic. Keep WhatsApp, checkout
and live models independently disabled. Verify `/health` and `/ready`, then use synthetic traffic
within an explicitly approved spend ceiling. No deployment is authorized by this repository alone.

## Roll back

Disable new ingress and provider dispatch first. Preserve inbox, outbox, ledger and action receipts.
Reconcile executing/unknown work; do not blindly replay external mutations. Route traffic to the
previous application image. Use a forward fix for compatible additive migrations; restore only to
an isolated target unless the incident commander explicitly authorizes production recovery.

