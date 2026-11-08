# Release 1 Scope and Timeline

Owner: Manager-ProgramDirector. Branch: `release1/chat-redesign` (from `origin/main` dcf4f75).
Source plan: `/home/rosso/Downloads/ai_chat_ui_ux_redesign_plan_2026.md` §7 (roadmap). Repo (Flutter + Python) is source of truth; web libraries in the plan are adapted.

## In scope for R1 (plan IDs)

| Plan ID | Deliverable | Issues | Squad | Plan effort (days, estimate) |
|---|---|---|---|---|
| R1-1 | Complete, resumable streaming; no silent cutoff; Continue/Resume/Stop/Regenerate; heartbeats; finish-reason; typed events | #6 | A | 3 |
| R1-2 | Persistent chats: history, search (titles+content), rename/pin/archive/delete+Undo, drafts; New Chat creates no empty records | #2, #7 | B | 4 |
| R1-3 | Responsive workspace; stable end-anchored scroll; Jump to Latest; history rail; tablet/mobile layouts | #1, #5, #8 | C | 4.5 |
| R1-4 | Safe rich rendering: markdown, code (copy/lang/wrap), tables, files, citations, long outputs | #3 | D | 3.5 |
| R1-5 | Clear processing / retry / stop / categorized error states (summarized processing only; no chain-of-thought) | #4 | E | 3 |
| R1-6 | Multiline composer: drafts, attachments, long-paste chips, keyboard support, optimistic send | #11 | E | 3.5 |
| R1-7 | Perf (faster load, lazy heavy modules, batched stream updates, reliable motion); dark-mode token patch; inline 80% usage warning; reduced-motion/transparency; a11y | #12, #10, #14, #8 | F + G + H | 3 |

Plan effort total ≈ 24.5 engineer-days, executed as parallel squads, so calendar time is governed by dependency gates, not by the sum.

## Out of scope for R1 (R1.1 and later)

Onboarding, profiles, settings modal, usage/plans center, full liquid-glass dark system: documented as implementation-ready tickets in `docs/release1/R1_1_BACKLOG.md` only. Nothing from that list is implemented in R1. Plan Phase 3 items (projects, memory, locked chats, arena, daily brief) are out of scope entirely.

## Hard constraints

- No production deploy, no production migration, no live charges, no real messages.
- Additive migrations only. Clean cutover: obsolete code removed, no shims.
- No destructive git. Preserve untracked `Claude outputs/` and `docs/release-evidence/device/*.png`.
- Commit small and recoverably on `release1/chat-redesign`; isolated work in git worktrees under `/tmp` or `.worktrees`; merges by Manager-IntegrationLead only.

## Phases and gates

| Phase | Content | Exit gate | Status |
|---|---|---|---|
| 0 Discovery | 5 explorers: architecture, UX inventory, perf baseline, data/API audit, test/release audit → `docs/release1/discovery/*.md` | Discovery files exist; perf baseline numbers recorded | DONE |
| 0 Contract | `docs/release1/EXECUTION_CONTRACT.md` (models, stream events, finish/error, API ownership, tokens, file ownership, test reqs, metrics, migration + rollback) | Contract merged on branch; DEPENDENCY_BOARD references it | DONE (5de20a8) |
| 1 Build | Squads A–G implement; H writes tests and strategy; shared files serialized per board | Each squad handoff in `docs/release1/handoffs/` with files, tests, risks | MERGED (handoffs A–G, BW, FIX, QA1, WIRING present) |
| 2 Integrate | Merge in contract order; backend `make`/pytest; `flutter analyze`; `flutter test` incl. goldens (IST); new tests for stream interruption/resume, persistence/search/delete/archive, composer paste, scroll behaviour; perf before/after; independent audit of risky work | QA_REPORT approval by Manager-QAReleaseLead | IN PROGRESS. Backend re-run at `4b95f5c` clean. Supervisor: analyze clean, a11y/chat 103 passed at `4b95f5c`. QA_REPORT updated for Boss rejection round 1; not signed off. |
| 2 Release | `RELEASE_REPORT.md`, Memory.md updated with verified state only | Acceptance evidence list complete | IN PROGRESS. `RELEASE_REPORT.md` final; PENDING-USER items (section 11) not run. |

## Sequencing (critical path)

1. Contract (blocks everything).
2. F tokens and A stream schema in parallel (both first-writer on their shared files).
3. B persistence schema after contract; A message persistence consumes it.
4. D renderer after A typed parts; C and E after B and F; G last among builders (needs A batching and F tokens).
5. H verification and integration gate; then release report.

## Timeline

Calendar dates are not committed here: the phases are gated by completion evidence, not by a fixed date. Plan's indicative window (Weeks 1–3 for R1, Weeks 4–5 for R1.1) is recorded for reference only. Any date commitment requires Supervisor approval.

## Risks and decisions log

- D-1 (open): Flutter adaptation of web-only plan items (virtualization, markdown streaming, Dexie cache) is decided in the contract, not here.
- D-2 (open): R1.1 start is gated on R1 completion; R1.1 is not scheduled.
