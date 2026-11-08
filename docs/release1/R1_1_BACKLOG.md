# Release 1.1 Backlog (implementation-ready, NOT in R1 scope)

Owner: Manager-ProgramDirector. Status: DRAFT TICKETS, none started. Nothing in this file is implemented in Release 1.
Source: plan `/home/rosso/Downloads/ai_chat_ui_ux_redesign_plan_2026.md` §3.8, §3.9, §5.4–5.6, §7 Phase 2 (R1.1-1..5). Repo findings are from read-only research on 2026-10-21; `[VERIFIED path:line]` = read in repo, `[PROPOSED]` = new or recommended, `[INFERENCE]` = not directly observed.

## Global gating rules

- **G-1:** No R1.1 ticket starts until R1 squads A and B are MERGED and VERIFIED, F tokens MERGED, and the H regression gate passed (see `DEPENDENCY_BOARD.md`).
- **G-2:** Any payment, checkout, live pricing, or on-demand spend cap is GATED on explicit owner approval. Sandbox/test mode only. `CLAUDE.md` forbids enabling paid checkout; `DAILY_AGENT_PAID_CHECKOUT_ENABLED` defaults false [VERIFIED src/daily_agent/config.py:94, .env.example:54].
- **G-3:** Additive migrations only; no production migration; no deploy.
- **G-4:** Chain-of-thought is never shown; processing states stay summarized.

## Open decisions (approved by Supervisor; drafted assumptions below are now decided)

- **OD-1 (blocks R1.1-1):** Adopt the plan's indigo dark palette (#090B10, 265°) or keep per-tier dark canvases. Repo uses tier palettes: Ananta #0B1A11, Yanta #0A111C, Trika #171210, Parth #000000 [VERIFIED docs/design/karmi_tier_color_palettes.md, mobile/lib/theme/karmi_colors.dart:1-30]. `Design.md` says "Avoid blanket glass effects" [VERIFIED docs/blueprint/Design.md:15]. Drafted assumption: derive all dark tones from KarmiColors per tier.
- **OD-2 (blocks R1.1-2):** Currency and plan names. Plan uses USD and Pro/Team/Ultra; repo uses INR micro and Ananta/Yanta/Trika/Parth [VERIFIED src/daily_agent/plans.py:6, docs/blueprint/PRD.md:37]. Drafted assumption: repo names and INR.
- **OD-3 (blocks R1.1-2G):** Quota pill threshold: plan §3.8 says 70%, R1-7 says 80%. Drafted assumption: 80% (R1-7 is the R1 contract).
- **OD-4 (blocks R1.1-2F):** Whether checkout is in R1.1 at all. Drafted assumption: deferred; only R1.1-2A–2E, 2G proceed.
- **OD-5 (blocks R1.1-3/4):** Whether preferences/Custom Instructions are stored server-side (drafted assumption: yes, `user_preferences` table; no preferences schema exists today [VERIFIED src/daily_agent/models.py:59-78, migrations/versions/]).

## Stack adaptation (plan → repo)

Plan is React/web. Repo is Flutter + Python. Mappings used by every ticket: `focus-trap` → `FocusScope`/`FocusTrap`; CSS tokens → `KarmiColors` via `mobile/tool/derive_theme_tokens.py` and `tier_tokens.g.dart` (generated; never hand-edit); `prefers-reduced-motion` → `MediaQuery.disableAnimationsOf` via `KarmiAccessibility` [VERIFIED mobile/lib/theme/karmi_motion.dart:7-27]; axe-core → `expectA11yGuidelines` incl. `textContrastGuideline` [VERIFIED mobile/test/support/harness.dart:214-221].

---

## R1.1-1 Full Dark-Mode Liquid-Glass System (Flutter)

- **Scope in:** Dark-only glass tuning in `KarmiGlass` / `KarmiGlassSurface`: directional rim (top 0.22 / side 0.09 / bottom 0.04 alpha), top inner highlight, diagonal surface gradient, focus rim brighten to 0.38 plus accent outer ring, non-interactive ambient under-glow behind Composer. Backdrop saturate/brightness via `ImageFilter`/`ColorFilter` only if it does not double-blur `liquid_glass_widgets` (package source not inspected; verify first).
- **Scope out:** Light mode; glass on chat bodies, code, tables (stay opaque `KarmiCard`); any web CSS; new dependencies; the indigo palette unless OD-1 decides it.
- **Acceptance:**
  1. Dark `KarmiGlassSurface` rim has per-side colours top > side > bottom (unit test).
  2. Focused Composer tray in dark: top rim alpha 0.38 and outer accent ring (widget test).
  3. `reduceTransparency` or `highContrast` yields key `karmi-glass-opaque` and no `GlassContainer`; existing `glass_motion_test` still passes.
  4. At most 3 glass surfaces on the chat screen (app bar, tab bar, composer).
  5. `expectA11yGuidelines` incl. `textContrastGuideline` passes dark screens for all 4 tiers.
  6. Dark goldens regenerated for chat, chat_empty, settings, usage, `tier_chat_*_dark`, `glass_legibility_dark`.
- **Files (existing):** `mobile/lib/theme/karmi_glass.dart` [VERIFIED :48-120], `mobile/lib/theme/karmi_colors.dart`, `mobile/lib/theme/tier_tokens.g.dart` (generated, do not hand-edit) [VERIFIED :28-57: glassBase alpha 0xC7 and glassHighlight 0x24 already match; glassBorder 0x1A is uniform 0.10, needs per-side], `mobile/lib/theme/karmi_theme.dart`, `mobile/lib/theme/karmi_motion.dart`, `mobile/lib/shell/karmi_shell.dart`, `mobile/lib/features/chat/composer.dart`, `mobile/lib/features/settings/settings_screen.dart`, `mobile/lib/widgets/focus_ring.dart`, `mobile/test/golden_test.dart`, `mobile/test/theme/glass_motion_test.dart`, `mobile/test/theme/karmi_colors_test.dart`, `mobile/test/support/harness.dart`, `mobile/tool/derive_theme_tokens.py`.
- **Files (new, PROPOSED):** `mobile/lib/theme/karmi_glass_rim.dart` (CustomPainter gradient rim), `mobile/lib/theme/karmi_glass_backlight.dart` (under-glow, inside RepaintBoundary), `mobile/test/theme/glass_dark_test.dart`.
- **CSS → Flutter map (PROPOSED):** `--glass-blur` → `BackdropFilter(ImageFilter.compose(outer: ColorFilter.matrix saturate 1.90 + brightness 1.08, inner: ImageFilter.blur sigma 24))`; `--glass-bg` 135° → `LinearGradient` topLeft→bottomRight over `glassBase`; border top/side/bottom → `CustomPainter` stroke; `--glass-shadow` → `BoxShadow` in `DecoratedBox`; accent radial glow → `RadialGradient` under `RepaintBoundary`; focus ring → `KarmiFocusRing`; reduce-transparency → `KarmiAccessibility.reduceTransparencyOf` [VERIFIED karmi_motion.dart:21-23].
- **Dependencies:** R1-7 dark token patch (top specular border in generator output); R1-6 Composer focus state (none found in `composer.dart` today [INFERENCE from read]). No other R1.1 ticket is a hard dependency.
- **Gating on R1:** R1-7 tokens merged; R1-6 Composer exposes focus state; OD-1 decided.
- **Test requirements:** unit (rim per-side colours, focus alpha, fallback key); a11y `textContrastGuideline` per tier in dark; goldens dark ×1.0/×2.0 with reduceTransparency on and off, per-OS baselines `mobile/test/goldens/linux` and `windows`. Shaders do not load under `flutter test`, so blur/specular are NOT golden-verified; device review is manual, logged with IST timestamps.
- **Size:** S–M (plan 1.5 d). **Risks:** palette conflict (OD-1); possible double blur with `liquid_glass_widgets`; painter cost on up to 3 glass surfaces on low-end Android.

---

## R1.1-2 Usage & Plan Center (split into 2A–2G)

Current state: request count and token window exist; `UsageView` does not parse `tokens_used`/`tokens_limit` [VERIFIED mobile/lib/api/models.dart:107-147]; no customer usage ledger (`cost_ledger` is provider expense, nullable `cost_micro` [VERIFIED src/daily_agent/models.py:174-183]); `PlanPolicy` has no Deep Task pool although `docs/blueprint/Tier_Entitlements.md` requires one [VERIFIED src/daily_agent/plans.py:14-18]; no `pubspec` chart package.

### R1.1-2A Usage read model & aggregation API — BACKEND
- **Scope in:** Extend `GET /v1/usage` with Deep Task pool once defined; add `GET /v1/usage/daily?days=N` returning per-day, per-model customer units for the caller only. **Out:** pricing, payments, UI.
- **Acceptance:** Days with no usage return zeros; NULL `cost_micro` reported as unknown, never 0; `reset_at` is an explicit UTC instant; cross-account request returns 404/403; GET performs no writes [VERIFIED src/daily_agent/api.py:199 comment].
- **Files:** `src/daily_agent/api.py`, `src/daily_agent/schemas.py` (UsageView :73), `src/daily_agent/services.py`, `src/daily_agent/models.py` (BudgetReservation :155, CostLedger :174), `src/daily_agent/plans.py`; new `migrations/versions/xxxx_usage_daily_index.py` [PROPOSED] index on `budget_reservations(account_id, created_at)`.
- **Dependencies:** R1-7 (80% pill consumes it). Blocks 2C, 2D.
- **Gating on R1:** none. **Owner decision:** Deep pool definition (Tier_Entitlements).
- **Tests:** unit (aggregation, UTC day buckets); e2e `tests/e2e/test_api.py` (cross-user denial); integration `tests/integration/test_postgres_redis.py`.
- **Size:** M. **Risk:** No customer-facing usage ledger; `Tier_Entitlements` requires distinct ledgers, so a new append-only usage table may be needed [PROPOSED, decide in contract].

### R1.1-2B Dual-pool quota bars + reset countdown — CLIENT (Deep pool needs 2A)
- **Scope in:** Parse `tokens_used`/`tokens_limit` in `UsageView`; token bar beside request bar in `UsageMeter` [VERIFIED mobile/lib/features/usage/usage_screen.dart:138]; countdown to `reset_at`.
- **Acceptance:** Bars show numbers and words, not bar alone (rule at usage_screen.dart:137); `Semantics` value gives percent and reset time; countdown updates; zero-usage copy from plan §3.8.
- **Files:** `mobile/lib/api/models.dart`, `mobile/lib/features/usage/usage_screen.dart`, `mobile/test/api/karmi_api_test.dart` (:323), `mobile/test/features/screens_test.dart` (:79), `mobile/test/support/fake_backend.dart` (:137), `mobile/test/goldens/linux/usage_*.png` (regenerate).
- **Dependencies:** R1-7; 2A for Deep pool. **Gating on R1:** none for current pools.
- **Tests:** widget tests for loading, failed, normal states; golden light/dark ×1.0/×2.0; Semantics assertions.
- **Size:** S.

### R1.1-2C Daily model burn-rate chart — BACKEND + CLIENT
- **Scope in:** Stacked daily bars per model with multiplier legend from 2A series. **Out:** new chart dependency without approval.
- **Acceptance:** Empty grid with copy "No usage recorded in this billing cycle yet"; legend uses server-declared multipliers, not hard-coded; per-message cost shown only if 2A exposes it.
- **Files:** `mobile/lib/features/usage/usage_breakdown_chart.dart` [PROPOSED]; `mobile/lib/api/karmi_api.dart`; `mobile/pubspec.yaml` (no chart package today).
- **Dependencies:** 2A. **Gating:** approval of chart package (new dependency). **Owner decision:** multipliers exist only in design; `plans.py` has none.
- **Tests:** widget + golden; contrast checks.
- **Size:** M.

### R1.1-2D On-demand spend cap — BACKEND, GATED
- **Scope in:** User-set cap at or below plan policy and approved budget; enforced server-side at reservation.
- **Acceptance:** Cap cannot exceed plan `period_cost_cap_micro` or approved budget; enforced atomically against `UsagePeriod`; lowering the cap never erases settled spend; fixed period boundaries preserved.
- **Files:** `src/daily_agent/models.py` (UsagePeriod :117-131), `src/daily_agent/services.py` (guarded updates ~:380-404), `src/daily_agent/config.py` (:155-158), `src/daily_agent/api.py`, `mobile/lib/features/usage/`.
- **Dependencies:** 2A; OD-2 currency decision; owner pricing approval.
- **Gating:** G-2 (money-facing). **Size:** M. **Risk:** design uses USD ($25 slider); repo budgets are INR micro [VERIFIED plans.py:6].
- **Tests:** unit concurrency and boundary tests; integration Postgres; e2e.

### R1.1-2E Plan matrix cards (read-only) — CLIENT
- **Scope in:** Side-by-side or swipeable cards from server-provided plan data; annual toggle only after approved pricing.
- **Acceptance:** Four canonical plans Ananta, Yanta, Trika, Parth [VERIFIED docs/blueprint/PRD.md:37]; no Pro/Team/Ultra names; prices shown only when non-null; "Purchases unavailable" copy persists while checkout disabled.
- **Files:** `mobile/lib/features/plans/plan_catalog.dart` (PlanInfo :11, kPlans :19), `mobile/lib/features/plans/plan_selection_screen.dart` (:127), `mobile/lib/features/usage/usage_screen.dart` (:120).
- **Dependencies:** R1-3 shell. **Gating:** pricing approval for annual toggle. **Size:** S.
- **Tests:** widget tests for disabled purchase controls; goldens for tier cards (`tier_chat_*` exist in `mobile/test/goldens/linux`).

### R1.1-2F Checkout & on-demand top-up — BACKEND, GATED (NOT TO BE IMPLEMENTED WITHOUT APPROVAL)
- **Verified absent:** no Stripe, checkout, or payment code or dependency in `src/`, `mobile/lib/`, `pyproject.toml`, `requirements.lock`, `.env.example`.
- **Scope in (only after OD-4 approval):** provider adapter behind `paid_checkout_enabled`; test mode only; signed, idempotent webhook following the sandbox pattern [VERIFIED src/daily_agent/api.py:733 `/webhooks/billing-sandbox`] and `BillingEvent` unique constraint [VERIFIED src/daily_agent/models.py:280-282]; entitlements changed only from webhook state, never from return URL [PRD.md:88].
- **Acceptance:** Forged, replayed, duplicate, out-of-order, and refund events tested; startup refuses paid checkout without approved budget [VERIFIED src/daily_agent/config.py:155]; no live keys in repo.
- **Files [PROPOSED]:** `src/daily_agent/billing/` (new), `src/daily_agent/api.py`, migration for subscription states, mobile payment sheet.
- **Dependencies:** 2A; OD-4; Revenue model prices; Tier_Entitlements activation gates.
- **Gating:** G-2. Any live charge violates `CLAUDE.md`. **Size:** L. **Status: BLOCKED pending owner approval.**

### R1.1-2G Sidebar quota pill (threshold 80%, OD-3) — CLIENT
- **Scope in:** Footer pill with plan badge and bar above threshold, opening Usage tab. R1-7 owns the inline 80% warning; this ticket is the sidebar placement.
- **Acceptance:** Threshold matches the value confirmed under OD-3; pill is a button with label and percent; opens Usage tab.
- **Files:** `mobile/lib/shell/karmi_shell.dart` (nav list :28-31 has no footer pill today).
- **Dependencies:** R1-3 shell; R1-7. **Size:** S.

---

## R1.1-3 Zero-Modal Role Onboarding & Dynamic Starter Prompt Scaffolds — CLIENT + BACKEND

- **Scope in:**
  - Lightweight welcome card above the composer in the zero-state workspace, replacing the static `EmptyState` [VERIFIED mobile/lib/features/chat/chat_screen.dart:248-259; mobile/lib/widgets/feedback.dart:51-57].
  - Five role/domain toggle chips: Engineering; Research & Analysis; Product & Design; Writing & Strategy; General Productivity. Plus a Skip control. Up to 2 selectable.
  - Four domain-tailored starter prompt cards below the composer; cross-fade on selection change.
  - Clicking a starter fills the composer with editable slot chips (e.g. `[Paste component or use sample]`).
  - Role preference persisted silently on first send or skip.
  - Note: plan's emoji labels are omitted; repo does not use emoji in UI copy [INFERENCE from repo style].
- **Scope out:** Multi-step blocking modal/wizard; cross-session memory extraction (R2-2); live model calls during template selection.
- **Acceptance:**
  1. First-time authenticated user reaches the workspace in under 15 s with no blocking modal.
  2. Selecting or deselecting a role cross-fades the 4 starter cards in under 150 ms with no layout jump.
  3. Clicking a starter populates the composer with slot chips; Enter sends resolved text.
  4. Role persistence is async and does not delay turn-1 stream start; returning users skip the card.
  5. Skip dismisses the card and applies default General Productivity starters.
- **Files:**
  - `mobile/lib/features/chat/chat_screen.dart` [VERIFIED :248]
  - `mobile/lib/features/chat/composer.dart` [VERIFIED :9, :54-65 plain `TextField` only: needs slot API]
  - `mobile/lib/widgets/feedback.dart` [VERIFIED :51]
  - `mobile/lib/settings/karmi_settings.dart` [VERIFIED :5, local SharedPreferences only]
  - `src/daily_agent/models.py` [VERIFIED :59-78 no preferences model], `src/daily_agent/schemas.py` (:12), `src/daily_agent/api.py` (:244)
  - New [PROPOSED]: `mobile/lib/features/chat/starter_prompts.dart`, `mobile/lib/features/chat/role_onboarding_card.dart`, `migrations/versions/xxxx_user_preferences.py` (additive; shared with R1.1-4).
- **Dependencies:** R1-3 (zero-state shell); R1-6 (composer slot/chip API). R1.1-4 shares the `user_preferences` model: whichever lands first owns it; the other rebases.
- **Gating on R1:** R1-3 zero-state shell merged; R1-6 slot insertion API merged; OD-5 decided.
- **Test requirements:**
  - Unit: role chip state transitions (max 2); starter template interpolation into slot chips.
  - Integration: zero-state first turn → role select → dispatch → silent persistence.
  - Golden: `RoleOnboardingCard` and `StarterPromptGrid` light/dark at ×1.0 and ×2.0, glass and opaque.
  - A11y: chip group semantics, focus moves to composer after starter click, 48 dp minimum touch targets.
- **Size:** S (≈2 engineering days). **Risk:** overflow below 360 dp width with 4 cards plus chips above a docked composer; mitigate with wrap and scrollable zero-state body.

---

## R1.1-4 Unified Settings Modal (Cmd/Ctrl+,) & Profile Custom Instructions with Data Export — CLIENT + BACKEND

- **Current state:** Settings is a bottom-tab `SettingsScreen` inside `IndexedStack` [VERIFIED mobile/lib/shell/karmi_shell.dart:77-88]; no Cmd/Ctrl+, shortcut; `KarmiSettings` stores only local preferences (theme mode, reduce transparency, notice ack, server URL) [VERIFIED mobile/lib/settings/karmi_settings.dart:5-23]; no backend preferences or export endpoint.
- **Scope in:**
  - Modal overlay opened by Cmd/Ctrl+, or the sidebar/avatar footer, without unmounting the active chat or streaming turn.
  - Desktop/tablet: two columns (left categories: Profile & Account, Personalization, Appearance, Data & Privacy, Keyboard Shortcuts; right pane). Mobile below 600 dp: stacked drill-down with Back.
  - Personalization: Custom Instructions ("What would you like Karmi to know about you?" / "How would you like Karmi to respond?") persisted to backend and injected into system context.
  - Appearance: ThemeMode (System/Light/Dark) applied in under 16 ms via `KarmiSettings` ChangeNotifier [VERIFIED karmi_settings.dart:65-69]; font scaling; reduce transparency.
  - Data & Privacy: asynchronous "Export all chats" (zip of JSON and Markdown) with formula-injection sanitization [VERIFIED docs/blueprint/PRD.md:91, docs/blueprint/Acceptance_Testing.md:39]. Account deletion flow: typing `DELETE`, 14-day grace [PROPOSED; not verified in repo, confirm with owner].
  - Backend: `user_preferences` table (custom_instructions, role_domains, theme overrides); `/v1/preferences`; `/v1/user/export`.
- **Scope out:** Payments or billing inside settings; cross-session memory extraction (R2-2); instant shredding that bypasses the grace window.
- **Acceptance:**
  1. Cmd+, / Ctrl+, opens the modal in under 100 ms without interrupting an active stream.
  2. Esc or backdrop dismisses; focus is trapped while open and returns to the invoker on close.
  3. Custom Instructions persist via `/v1/preferences` and appear in subsequent prompts (Acceptance_Testing T10 cycle [VERIFIED docs/blueprint/Acceptance_Testing.md:28]).
  4. Export returns a sanitized zip (JSON + MD) with no formula injection (`=`, `+`, `-`, `@` escaped per REQ-LAB-002).
  5. Theme change applies in under 16 ms with no remount.
- **Files:**
  - `mobile/lib/features/settings/settings_screen.dart` [VERIFIED :16]; `mobile/lib/shell/karmi_shell.dart` [VERIFIED :26]; `mobile/lib/settings/karmi_settings.dart` [VERIFIED :5]; `mobile/lib/api/karmi_api.dart` [VERIFIED :63, :128].
  - `src/daily_agent/models.py`, `src/daily_agent/schemas.py`, `src/daily_agent/api.py`.
  - New [PROPOSED]: `mobile/lib/features/settings/settings_modal.dart`, `personalization_tab.dart`, `data_privacy_tab.dart`; `src/daily_agent/export.py`; `migrations/versions/xxxx_user_preferences_and_instructions.py`.
- **Dependencies:** R1-2 (persistence schema, export source data); R1.1-3 (shared `user_preferences`); R1-3 (desktop shell and footer avatar trigger).
- **Gating on R1:** R1-2 conversation and message tables merged (none exist in migrations today [VERIFIED migrations/versions/]); R1-3 shell merged.
- **Test requirements:**
  - Unit: preference (de)serialization; export archive builder with formula-injection sanitization.
  - Integration: T10 cycle: save → verify prompt inclusion → update → delete → verify purge [VERIFIED Acceptance_Testing.md:28].
  - Golden: 2-column desktop modal and mobile drill-down, light/dark, glass/opaque.
  - A11y: focus trap, Esc handling, semantics headers for categories, high-contrast borders.
- **Size:** M (≈2.5 engineering days). **Risks:** Export zip built on the gateway event loop for large histories (use a background task or streamed response); Cmd+, conflicts with browser/OS shortcuts on desktop targets.

---

## R1.1-5 Contextual Text-Selection Floating Toolbar (Ask follow-up, Verify sources, Edit in Drawer)

- **Scope in:** Text selection in assistant replies. Today replies render as unselectable `Text(reply!.message.response)` [VERIFIED mobile/lib/features/chat/message_bubble.dart:76]; wrap in `SelectionArea` with custom `contextMenuBuilder`. Compact glass pill toolbar anchored to the selection via `SelectableRegion` context-menu anchors (Flutter 3.47.5), styled with `KarmiGlassSurface` [VERIFIED mobile/lib/theme/karmi_glass.dart:47-50]. Actions: `Ask follow-up` (inserts `> "<selection>"` quote into Composer and focuses it), `Verify sources` (filters citation cards from R1 squad D), `Edit in Drawer` (opens an editable excerpt drawer). Platform `Copy` and `Select All` stay.
- **Scope out:** Multi-bubble selection; selection on user bubbles; autonomous memory from selection (R2-2); web context-menu overrides.
- **Acceptance:** (1) Selecting a span in an assistant reply shows the toolbar anchored above it in under 100 ms. (2) `Ask follow-up` dismisses the toolbar, inserts the quote with a blank line after, and focuses the composer without losing existing draft text. (3) `Verify sources` shows matching citations without clearing chat state. (4) `Edit in Drawer` opens the excerpt. (5) Collapse, outside tap, or scroll dismisses the toolbar. (6) Copy copies plain text to the clipboard.
- **Files:** `mobile/lib/features/chat/message_bubble.dart` [VERIFIED :76], `mobile/lib/features/chat/chat_screen.dart` [VERIFIED :267], `mobile/lib/features/chat/composer.dart` [VERIFIED :9], `mobile/lib/theme/karmi_glass.dart` [VERIFIED :47], `mobile/lib/widgets/karmi_card.dart` [VERIFIED :56]. New [PROPOSED]: `mobile/lib/features/chat/selection_toolbar.dart`, `mobile/lib/features/chat/sources_drawer.dart`, `mobile/lib/features/chat/artifact_drawer.dart`.
- **Dependencies:** R1 squad D (citation chips, `citation_chip.dart`) for `Verify sources`; R1 squad E (`Composer` seam) for quote insertion; R1.1-2G none.
- **Gating on R1:** **GAP:** the contract (§6, §7) has NO Artifact Drawer and NO Sources drawer in any squad's file list. Before this ticket starts, the owner must either add the drawer(s) to R1 scope or accept R1.1 creating them. Composer must expose an insert-and-focus method (contract §7 `Composer` seam does not list one; add in squad E or R1.1). Citation structure: the contract derives citations client-side from markdown (D1), so `Verify sources` matches text, not grounded claims.
- **Test requirements:** Unit: selection text extraction, quote formatting, action list assembly. Integration: select text in assistant reply → Ask follow-up → composer text and focus. Golden: toolbar light/dark, glass/opaque. A11y: 48 dp targets; semantics labels `Ask follow-up on selection`, `Verify sources for selection`, `Edit selection in drawer`.
- **Size:** S–M (≈1.5 engineering days, plus drawer work if not in R1). **Risks:** `ListView` virtualization detaching the selection handle (use native `SelectableRegion` anchors); toolbar overflow under 360 dp (scroll horizontally or collapse to icons with tooltips).

---
## R1.1-6 to R1.1-11 Follow-ups from R1 contract deviations

Each is an R1 deviation (`EXECUTION_CONTRACT.md` §0) moved to R1.1. Each needs a full ticket before start; the scope below is the minimum the board tracks.

- **R1.1-6 Structured message parts (D1):** Add `message_parts` (additive) so code, table, citation, and file parts are stored and returned by the API, not derived from markdown. Acceptance: round-trip of each part type; no client-side markdown parsing needed for citations. Gate: R1 rendering (squad D) and P1 schema stable.
- **R1.1-7 Attachment uploads (D2):** Upload route, object storage, image support, and per-user quota. Acceptance: upload, fetch with owner check, delete; size limits enforced server-side. Gate: storage decision and G-2 if billing-linked; privacy review for stored files.
- **R1.1-8 Server-side drafts (D3):** Draft table keyed by conversation, synced across devices. Acceptance: draft written on device A appears on device B after reload; deleting a conversation purges its draft. Gate: owner decision that drafts may leave the device.
- **R1.1-9 Durable stream resume (D5):** Persist the event buffer (Valkey/Redis or DB) so resume works after a restart and across instances. Acceptance: kill and restart the gateway mid-stream; client resume returns the missing events by `seq`; no duplicate terminal event. Gate: multi-instance decision.
- **R1.1-10 Remove legacy routes (D6):** Delete `POST /v1/messages`, regenerate, feedback legacy paths and their tests once `web/` PWA is retired. Acceptance: no caller in repo; `make test-unit` and `test-e2e` pass; contract rollback note updated. Gate: owner confirms `web/` retirement.
- **R1.1-11 Full-text search (D7):** Add Postgres FTS (`tsvector` + GIN) with ranking; keep the ILIKE path until parity is verified. Acceptance: P95 search under 200 ms on the seeded corpus; escaped input; cross-user 404 preserved. Gate: R1 search in production-like tests and a perf baseline.


## Summary table

| ID | Title | Layer | Size | Gating | Status |
|---|---|---|---|---|---|
| R1.1-1 | Dark liquid-glass system | Client | S–M | G-1, OD-1 | Draft, ready after OD-1 |
| R1.1-2A | Usage aggregation API | Backend | M | G-1, Deep pool def. | Draft |
| R1.1-2B | Dual-pool bars + countdown | Client | S | G-1 | Draft |
| R1.1-2C | Daily model chart | Both | M | 2A, chart approval | Draft |
| R1.1-2D | On-demand spend cap | Backend | M | G-2, OD-2 | Gated |
| R1.1-2E | Plan matrix cards | Client | S | G-1, pricing approval for annual | Draft |
| R1.1-2F | Checkout & top-up | Backend | L | G-2, OD-4 | BLOCKED pending approval |
| R1.1-2G | Sidebar quota pill | Client | S | OD-3 | Draft |
| R1.1-3 | Role onboarding & starters | Both | S | G-1, OD-5 | Draft |
| R1.1-4 | Settings modal, Custom Instructions, export | Both | M | G-1, OD-5 | Draft |
| R1.1-5 | Selection floating toolbar (incl. Artifact and Sources drawers) | Client | M | G-1; R1 citation chips merged | Draft, drawers in scope per Supervisor |
| R1.1-6 | Structured message parts (`message_parts` table, typed API parts) | Both | M | D1; R1 stable | Draft |
| R1.1-7 | Attachment uploads with storage, images, size limits | Both | L | D2; storage approval | Draft |
| R1.1-8 | Server-side drafts sync across devices | Both | S | D3 | Draft |
| R1.1-9 | Durable stream resume across process restart | Backend | L | D5; multi-instance decision | Draft |
| R1.1-10 | Remove legacy `/v1/messages`, regenerate, feedback routes after `web/` retirement | Both | S | D6; owner decision on `web/` | Draft |
| R1.1-11 | Full-text search (FTS) for conversations | Backend | M | D7 | Draft |
