# Known issues and open items (as of this branch)

- No live model has been called. The OpenRouter key (`.env.openrouter`) and the owner-approved
  request cap do not exist, so the free-model catalog snapshot, scores, shortlist and the real
  `model-registry.v1` are NOT produced. Karmi ships a packaged **seed** registry (OpenCode free
  models, classes and 32k context are unreviewed estimates). Replace it with the Parakh registry.
- Parakh's `pilot run` only accepts exactly 36 train-split cases at concurrency 1 and does not use the
  new OpenRouter adapter. Running the 49-case student set needs a reviewed change (see
  `Parakh/docs/live_pilots/OPENROUTER_PILOT.md`).
- Plan quotas (requests/day, tokens/day) are provisional. The "Revenue_model" document was not found
  in either repo; prices (0/149/399/899 INR) come from the work order. The "Deep Task" billing unit is
  not implemented.
- Circuit breaker, model cooldowns and the per-user rate limit are per process; run one replica.
- OpenRouter free tier: 20 requests/min, 50/day without credits. Tester capacity is bounded by this.
- Docker is not installed on the dev machine. Integration tests ran against a disposable local
  PostgreSQL 18 and Valkey on the compose ports, not through `docker compose`.
- Clerk email-code sign-in on a physical phone is not verified (no phone connected).
- The release APK is built against a placeholder backend URL and signed with the debug key until the
  hosting and signing decisions are made.
- Notes are attached to a model prompt only for explicit "draft ... using my notes" requests and only to
  models with `no_training` terms; prompts themselves still go to third-party model providers.
- Regenerate requires the client to resend the original prompt (the server stores only its hash).
- Typesafe live scoring (`DAILY_AGENT_LIVE_MODELS_ENABLED`) is a paid provider path and stays off.
- Pre-existing: legacy `tests/model_lab` and `model_lab run-opencode` still exist in Karmi next to Parakh.
