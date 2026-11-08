# Karmi R1 QA Report (Boss rejection round 1)

Branch: `release1/chat-redesign`, HEAD `4b95f5c`. Supersedes the `r1/finalqa` verdict (GO at `9343b44`, 506 passed, with 3 open non-blocking findings). Those three findings are now fixed at `4b95f5c`.

## Verdict

**Resubmitted for Boss review after rejection round 1. Not signed off by QA.**

- Backend: Critical 1 and High 3 audit findings are fixed with regression tests. All 10 backend audit findings are marked Fixed in `QA_AUDIT_BACKEND.md`. Re-verified at HEAD: lint, typecheck, unit (226), e2e (62), integration (6) all pass.
- Client: AUDIT-01 and AUDIT-02 fixed in `147b1ee` and `90586b6`. AUDIT-03, AUDIT-04 and AUDIT-05 fixed in `4b95f5c`. No Critical or High client finding is open. AUDIT-02 has a residual (section "Client audit").
- Accessibility: the one failing a11y test at `959958b` (ErrorCard Retry contrast 4.40:1) is fixed by `777919a`. Supervisor reports the a11y and chat suites green at HEAD (103 passed). Not re-run by QA.
- Flutter analyze: clean at HEAD (Supervisor).
- Whole-suite Flutter run including goldens: the Supervisor's final count is to be recorded from its run at HEAD. The earlier figure (506 passed, `9343b44`, `--exclude-tags golden`) is superseded.
- Open items that block sign-off are the PENDING-USER checks in `RELEASE_REPORT.md` section 11 (no device run, no real provider or model, no auth sign-in, no onboarding). None of them was run or passed.

## Scope of this verdict

- Verified here: backend checks (re-run at `4b95f5c`, see `RELEASE_REPORT.md` section 4).
- Quoted from the Supervisor (not re-run here): Flutter analyze at HEAD, a11y and chat suites (103 passed), full Flutter suite.
- Not verified: device behaviour, real provider streaming (D4), goldens visual review (R-9), Clerk sign-in, onboarding.

## Client audit (`QA_AUDIT_CLIENT.md`)

| ID | Severity | Status | Fix | Notes |
|---|---|---|---|---|
| AUDIT-01 | High | Fixed | `147b1ee`, regression `90586b6` | Owned stream stopped on conversation switch; transcript kept on fetch failure. |
| AUDIT-02 | High | Fixed, residual | `147b1ee` | Drafts cleared on sign-out. Residual: two accounts on one device without sign-out share `draft.v1.new`. |
| AUDIT-03 | Medium | Fixed | `4b95f5c` | Rename controller disposed. |
| AUDIT-04 | Medium | Fixed | `4b95f5c` | `hasNewContent` wired to `JumpToLatestButton`. |
| AUDIT-05 | Low | Fixed | `4b95f5c` | Attachment remove target 48dp. |

The AUDIT-03, -04 and -05 fixes are not covered by a separate test run in this package. They are included in the Supervisor's full-suite gate.

## Accessibility

- Golden, semantics and keyboard suites: `docs/release1/QA_A11Y.md`.
- Earlier run at `959958b`: 23 of 24 passed. The failure was ErrorCard Retry contrast. `777919a` fixed it.
- Supervisor at HEAD: a11y and chat suites 103 passed.
- Not covered: macOS and Windows goldens; reduced-transparency and high-contrast fallbacks not separately asserted.

## Whole-suite result

- Supervisor's full Flutter run (`TZ=Asia/Kolkata flutter test`, goldens included) at HEAD `4b95f5c`: to be recorded from the Supervisor's final message. Three test files were under triage at the time of writing (fixes for drafts and perf in flight), so no final count is quoted here.
- History: `9343b44` `--exclude-tags golden`: 506 passed, 0 failed. The first run of that suite failed `composer_test.dart` "paste >= 2500 chars becomes chip" because b8a4fff made the threshold strict. Fixed by aligning the test in `9343b44`.

## Backend (`QA_AUDIT_BACKEND.md`)

All 10 findings are marked Fixed, with regression tests named in `RELEASE_REPORT.md` section 5. Re-run at HEAD `4b95f5c`: lint and secret scan clean, mypy clean (49 files), unit 226 passed, e2e 62 passed, integration 6 passed (podman, postgres:17, redis:8).

## Perf (`perf/AFTER.md`)

Host-VM proxies only, not device numbers. Cold-start proxy and scroll p95 are noisy at this sample size. Filtered rebuilds per send rose from a median of 9 to 20 under the same method. This is a regression signal. It does not support a batching improvement claim, because the perf test does not exercise per-delta streaming. APK size, unfiltered rebuilds, streaming frame timing and device jank are NOT MEASURED. AFTER was measured at `e9dd199`; the `4b95f5c` changes did not touch the measured paths, but this is not re-measured.

## Commits relevant to this verdict

- `4b95f5c`: AUDIT-03/04/05 fixes and format pass (Boss rejection round 1)
- `777919a`: ErrorCard retry contrast fix, error goldens regenerated
- `959958b`: a11y contrast tokens and composer tab-order test
- `90586b6`: AUDIT-01 regression fix and screen scroll tests
- `9343b44`: composer paste-threshold test alignment
- `147b1ee`: AUDIT-01 and AUDIT-02 fixes
- `a834142`, `28a30f4`, `eda49f8`, `16249fa`: QA report, client audit, and perf docs

## Items for the Boss before sign-off

1. Decide whether the PENDING-USER items (`RELEASE_REPORT.md` section 11) block R1 release or are accepted with a follow-up.
2. Decide whether the perf regression signal (filtered rebuilds 9 to 20) must be investigated before release.
3. Review the goldens visually (R-9). They were regenerated and not reviewed by a person.
4. Accept or schedule the AUDIT-02 residual (shared device, two accounts, no sign-out).
