# Known issues and open items (v0.1.0-beta.1)

- **Only a capped probe was run, not the full pilot.** OpenRouter's free tier allows 50 requests/day and
  20/min per key (the key is not funded). 15 free chat models were found (`catalog` snapshot 2026-10-19,
  19 free ids incl. 4 non-chat). The probe used about 41 of the 50 daily requests: maths + Hindi on all
  models, code on the 7 that answered. Results: 7 models answered; 4 timed out at 90 s
  (xing4.0-29b, nemotron-3.5-super-vl, dots-3-note-preview, laguna-s-2.1); the two Gemma 4 models returned
  HTTP 429 from the upstream provider; both inkling models return 403 ("agentic harnesses only").
  Scores are 1 case per task type, 1 repeat, all provisional; the cases are too easy to rank models.
  Classes are size-based labels. The full 49-case, 3-repeat pilot needs a funded key (1000/day) or several days.
- Parakh's `pilot run` still only accepts exactly 36 train cases at concurrency 1 and does not use the new
  adapter; the probe used a standalone capped script (`Parakh/scripts/openrouter_probe.py`) instead.
- **No hosted backend.** Nothing was deployed (no cloud login). The APK is built with a placeholder server
  address; set the real one under Welcome > Server address, or rebuild. See `ops/deploy/README.md`.
- **Sign-in not verified on a device.** The Pixel 9a was connected earlier in the session but dropped off
  adb before the APK could be installed; Clerk's emailed code also needs a human. Run the checklist in
  `docs/release-evidence/device-checklist.md`.
- APK is signed with the Android **debug** key (no release keystore decision yet).
- Access codes (one per paid tier) are shared secrets: anyone with a code gets that tier. Codes only ever
  upgrade; there is no revoke list except replacing `data/access_codes.json` and redeploying.
- Plan quotas and the seed OpenCode registry entries are provisional estimates. Prices (0/149/399/899 INR)
  are labels only; checkout is disabled; "Deep Task" is not implemented.
- Circuit breaker, cooldowns, per-user rate limit and access-code guess throttle are per process: one replica.
- Regenerate needs the client to resend the original prompt (the server keeps only its hash).
- The in-app notice is a placeholder and needs legal review (minors, DPDP Act 2023). Invite adults only.
- Integration tests ran under rootless podman (Postgres 17, Redis 8, host networking), not Docker.
