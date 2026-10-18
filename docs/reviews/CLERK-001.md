# CLERK-001 — Clerk backend session verification

Status: `ACCEPT_RECOMMENDED` for the local code candidate. This is not production readiness or
deployment approval.

## Scope

- Verify Clerk session JWTs with RS256, exact issuer, expiry, issued-at, and session ID checks.
- Resolve immutable Clerk `sub` to one Karmi user and tenant account; first sign-in provisions a
  customer on the free Ananta plan.
- Preserve the local development token path while rejecting it outside development.
- Add a nullable unique user subject and a reversible Alembic migration.
- Load ignored `.env.clerk` through the app runtime settings loader, validate its issuer/key shape,
  and report production auth readiness without exposing key values.

## Review

An independent read-only supervisor review returned `ACCEPT_RECOMMENDED`. The initial P2 concern
that arbitrary nonempty key text could look ready was fixed: configuration now requires an HTTPS
issuer and successfully parses the decoded PEM as an RSA key; the release readiness check uses the
same predicate. Regression coverage rejects malformed keys. No review agent read `.env.clerk` or
accessed Neon.

The Neon migration helper also received a separate read-only review. Its preflight now recognizes
only an empty database, the known previous revision, or the fully migrated target; unexpected and
partial states are refused. It runs Alembic to the pinned target revision, and verifies the Clerk
column and one-column UNIQUE constraint. The reviewer did not run it against Neon; the later
authorized application is recorded below.

The review task requested `gpt-6-sol` at medium effort. Effective model metadata was unavailable,
so it is not asserted here.

## Verification

- Unit/ModelLab/web: 87 passed.
- API E2E: 29 passed.
- Ruff and repository secret scan: passed.
- Strict mypy over 25 source files: passed.
- Fresh disposable SQLite migration to `1a2b3c4d5e6f` and `alembic check`: passed with no drift.
- Private Clerk settings loaded and the saved RSA public key parsed locally; values were not printed.

## Limits

- At review time, Neon was at revision `c5d7e9f1a2b4`; the additive migration was later applied with
  explicit user authorization, as recorded below.
- The current Flutter client still obtains a local development token; it has not been connected to
  Clerk sign-in or configured to send Clerk session JWTs.
- Offline signature verification cannot observe Clerk session revocation until token expiry.
- No production deployment, app startup against Neon, paid provider call, or live customer action was
  performed.

## Authorized Neon application

On 2026-10-10, the user explicitly authorized applying the migration. The reviewed helper confirmed
`neondb`, `public`, PostgreSQL 18.6, and prior revision `c5d7e9f1a2b4`, then applied only
`1a2b3c4d5e6f`. Its postflight verified 20 public tables and the target revision, Clerk subject
column, and unique constraint. No app startup or live provider action was performed.
