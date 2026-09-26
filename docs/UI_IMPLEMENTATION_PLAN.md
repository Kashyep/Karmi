# Karmi UI Implementation Plan (Flutter, Android + iOS)

Status: plan only, 2026-09-26. No packages were installed and no source files were edited.
Base commit: `d3eb193` (main).

Everything marked **UNVERIFIED** could not be checked against a primary source (package
registry, the package's README, or the repo) while writing this. Treat those items as
assumptions to confirm during the task that first depends on them.

---

## 1. Findings

### 1.1 Detected stack (repo as of `d3eb193`)

| Area | Finding | Evidence |
| --- | --- | --- |
| Backend | Python ≥3.12, FastAPI, SQLAlchemy, Alembic, Pydantic; mypy strict; ruff (line length 100) | `pyproject.toml`, `CLAUDE.md` |
| Existing UI | A single web/PWA shell with no dependencies. Its HTML, CSS and JS are Python string constants, served at `/` | `src/daily_agent/web/shell.py`, `manifest.webmanifest` |
| UI tests | 3 pytest tests on the rendered HTML: skip link, nav landmark, manifest, no model picker, four plan labels, no invented balances, escaped task states | `tests/web/test_shell.py` |
| JS/Flutter tooling | None. There is no `package.json`, `pubspec.yaml`, `components.json`, Tailwind or shadcn on `main` or any remote branch | `git ls-tree` over all branches |
| Existing tokens | Blue/grey system (`#254EDB` accent, `#F7F8FA` canvas), system-ui font | `docs/blueprint/Design.md`, `shell.py` `_STYLES` |
| Agent rules | AGENTS.md and CLAUDE.md require task cards, disjoint worker ownership, `Memory.md` once implementation starts, and VERIFIED / NOT VERIFIED reporting. They also forbid enabling WhatsApp, checkout or live charges | `AGENTS.md`, `CLAUDE.md` |
| CI | One Python job (lock check, lint, typecheck, unit, e2e, benchmark, integration) | `.github/workflows/ci.yml` |
| Pre-commit | None (`.pre-commit-config.yaml` and `.husky/` are absent) | repo root |

API surface the app will consume (from `src/daily_agent/api.py` and `schemas.py`):

- `POST /v1/messages` takes `{text, idempotency_key}` and returns `MessageView{run_id, status, outcome, response, route}`.
  The response is synchronous; there is no streaming endpoint. A duplicate request that is still in flight gets HTTP 409.
- `GET /v1/usage` returns `UsageView{plan_id, plan_label, everyday_used, everyday_limit, reserved_micro, settled_micro, spend_limit_micro, reset_at, period_reset_at, policy_version}`.
- Notes (used for memory): `POST`, `GET` and `DELETE /v1/notes`.
- Tasks: `POST /v1/tasks` and `PATCH /v1/tasks/{id}/complete`. There is **no `GET /v1/tasks`**.
- Reminders: `POST /v1/reminders` only.
- Auth: a `Bearer` token is required (`require_principal`). The only token issuer is `POST /dev/token`, which works in development only.
- `Outcome` values: `ACCEPT, REPAIR, ESCALATE, ASK_USER, SAFE_STOP, DEFERRED`.

### 1.2 Target platform (decided by the owner on 2026-09-26)

Karmi's customer UI ships **only as native Android and iOS apps built with Flutter**. The repo has
no Flutter project yet, so this is a new project (proposed location: `mobile/`, see Q1). The
backend and the existing Python web shell are left unchanged by this plan (see Q7).

### 1.3 Stack-mismatch verdict

**Verdict: FLUTTER. None of the four npm/shadcn libraries can be used.** All four are
React-DOM code. Each one was verified from its registry entry or its source:

| Requested | What it actually is | Why it can't run in Flutter |
| --- | --- | --- |
| `npm install loading-dev` | npm `loading-dev@0.3.4` (published 2026-09-20). "Beautiful loading indicators for React": 29 components such as `Arc`, `Ring` and `Pulse`, with `size`, `color` and `duration` props. Respects reduced motion. Peer dependencies `react >=19`, `react-dom >=19`. Repo `jakubkrehel/loading`, MIT license | React components; there is no Dart build |
| `npx skills add starc007/ui-components --skill beui` | An agent skill (`skills/beui/SKILL.md`) that installs `@beui/*` React motion components through the shadcn registry. Components depend on `motion`, `clsx`, `tailwind-merge` and `lucide-react`. The live registry has 125 items. There is no runtime package | Needs React, Tailwind, shadcn and motion/react |
| `npx shadcn@latest add zzzzshawn/orbkit/shdr-01` | orbkit registry item `shdr-01` (`registry:ui`). Files: `components/ui/orbkit-core.tsx` and `components/ui/shdr-01.tsx`. A WebGL shader orb for React. **License: the shdr-01 shader is by XorDev and is "Non-commercial use only, with attribution"** (from the file header). The orbkit runtime is MIT | WebGL/TSX. Its license also blocks use in a paid product (see §4) |
| `npx shadcn@latest add @toggles/lightbulb` | `@toggles` is listed in the shadcn registry index (toggles.dev). `lightbulb` is a `registry:block` with one file, `src/Lightbulb.tsx`: a `<button>` with an SVG lightbulb and `toggled` / `duration` props | React/SVG/CSS |

`CONTEXT.md` targets Flutter `liquid_glass_widgets`, which now matches the chosen stack. The glass
package is used directly; there is no need to translate it to CSS `backdrop-filter`.

### 1.4 Missing inputs (**UNVERIFIED**)

`CONTEXT.md`, `KARMI_THEME-codes.txt` and `KARMI_THEME-palette.png` are not in the repo or on the
build machine. This plan uses:

- the hex/HSL values and font roles from the task brief;
- the CONTEXT.md rules as summarised in the brief (glass only on nav chrome and a few floating
  controls, opaque dense content, accessibility fallbacks, performance budgets, one
  representative screen first);
- the design guidance published in `liquid_glass_widgets`' own README, which says the same things.

Any specific numbers CONTEXT.md sets (blur radius, frame budgets, count limits) are not known.
Section 8 marks where they plug in.

### 1.5 Flutter-side packages (verified on pub.dev and flutter.dev, 2026-09-26)

| Package / SDK | Version | Published | Constraints | Notes |
| --- | --- | --- | --- | --- |
| Flutter stable | 3.47.5 (Dart 3.13.4) | 2026-09-18 | n/a | From `releases_windows.json` |
| `liquid_glass_widgets` | 1.7.2 | **2026-09-22 (less than 7 days old)** | Flutter ≥3.41.0, Dart ≥3.5.0; depends only on the `flutter` SDK | MIT. See the supply-chain note in §4 |
| `google_fonts` | 8.2.1 | 2026-07-31 | Flutter ≥3.38.0, Dart ^3.10.0; depends on `crypto`, `http`, `path_provider` | Supports bundling fonts as assets |
| `cupertino_icons` | already a dependency in a default `flutter create` app | n/a | n/a | `liquid_glass_widgets` requires it (its README "Known Limitations") |

---

## 2. Design tokens

### 2.1 Decision

The brand palette **replaces** the blue tokens in `docs/blueprint/Design.md` for the mobile app
(Q2 confirms this). Tokens are written in shadcn CSS-variable HSL format (`H S% L%`) because the
brief asked for it and it makes a single source of truth. Flutter consumes the same values through
`ColorScheme` plus a `ThemeExtension<KarmiColors>`. No CSS is shipped.

Values not in the brand palette (muted, border, destructive, all dark-mode values) are **derived**
from the palette hues 127–156°.

### 2.2 Light

| Token | HSL (shadcn format) | Hex | Source |
| --- | --- | --- | --- |
| `--background` | `129 47% 97%` | `#f4fbf5` | brand Background |
| `--foreground` | `129 47% 6%` | `#08160a` | brand Text |
| `--card` / `--popover` | `0 0% 100%` | `#ffffff` | derived: opaque content surface |
| `--card-foreground` | `129 47% 6%` | `#08160a` | brand Text |
| `--primary` | `127 42% 30%` | `#2c6d34` | brand Primary |
| `--primary-foreground` | `129 47% 97%` | `#f4fbf5` | brand Background |
| `--secondary` | `153 44% 67%` | `#86d0af` | brand Secondary |
| `--secondary-foreground` | `129 47% 6%` | `#08160a` | brand Text |
| `--accent` | `156 44% 46%` | `#42a980` | brand Accent |
| `--accent-foreground` | `129 47% 6%` | `#08160a` | brand Text (**never white**, see §2.4) |
| `--muted` | `130 32% 93%` | `#e6f2e8` | derived |
| `--muted-foreground` | `129 11% 33%` | `#4b5e4e` | derived |
| `--border` / `--input` | `127 11% 49%` | `#6f8a72` | derived; meets the 3:1 non-text contrast minimum for control outlines |
| `--border-subtle` (decorative separators only) | `129 29% 87%` | `#d5e8d8` | derived; decorative, so the contrast rule does not apply |
| `--ring` | `127 42% 30%` | `#2c6d34` | = primary |
| `--destructive` | `354 67% 42%` | `#b42332` | kept from Design.md `error` |
| `--destructive-foreground` | `0 0% 100%` | `#ffffff` | n/a |

### 2.3 Dark (derived)

| Token | HSL | Hex | Notes |
| --- | --- | --- | --- |
| `--background` | `129 47% 6%` | `#08160a` | brand Text used as the canvas |
| `--foreground` | `129 39% 94%` | `#e8f5ea` | n/a |
| `--card` / `--popover` | `130 41% 9%` | `#0d1f10` | opaque content surface |
| `--card-foreground` | `129 39% 94%` | `#e8f5ea` | n/a |
| `--primary` | `153 44% 67%` | `#86d0af` | brand Secondary becomes primary on dark |
| `--primary-foreground` | `129 47% 6%` | `#08160a` | n/a |
| `--secondary` | `127 42% 30%` | `#2c6d34` | brand Primary becomes secondary on dark |
| `--secondary-foreground` | `129 39% 94%` | `#e8f5ea` | n/a |
| `--accent` | `156 44% 46%` | `#42a980` | brand Accent (unchanged) |
| `--accent-foreground` | `129 47% 6%` | `#08160a` | n/a |
| `--muted` | `129 28% 14%` | `#1a2e1d` | n/a |
| `--muted-foreground` | `127 11% 69%` | `#a6b8a8` | n/a |
| `--border` / `--input` | `128 14% 44%` | `#5f7f63` | n/a |
| `--ring` | `153 44% 67%` | `#86d0af` | n/a |
| `--destructive` | `353 100% 81%` | `#ff9ca7` | kept from Design.md dark `error` |
| `--destructive-foreground` | `129 47% 6%` | `#08160a` | n/a |

Status colours (success, warning) keep Design.md's pairs until the owner supplies branded ones.
Success must stay distinguishable from primary green, so success states always carry an icon and
a word, never colour alone (as Design.md already requires).

### 2.4 WCAG 2.x contrast check

Ratios were computed with the WCAG relative-luminance formula. Pass thresholds:

- **AA**: 4.5:1 for normal text, 3:1 for large text (≥24px, or ≥18.66px bold) and for non-text UI parts.
- **AAA**: 7:1.

**Brand pairs**

| Text / element | On | Ratio | Result |
| --- | --- | --- | --- |
| Text `#08160a` | Background `#f4fbf5` | **17.68** | AAA |
| Text `#08160a` | Card `#ffffff` | **18.59** | AAA |
| Primary `#2c6d34` (as text/link) | Background `#f4fbf5` | **5.97** | AA |
| Primary `#2c6d34` | White `#ffffff` | **6.28** | AA |
| Background `#f4fbf5` | Primary `#2c6d34` (primary button) | **5.97** | AA |
| White `#ffffff` | Primary `#2c6d34` | **6.28** | AA |
| Text `#08160a` | Primary `#2c6d34` | **2.96** | **FAIL**: never put dark text on a primary fill |
| **White `#ffffff` | Accent `#42a980`** | **2.91** | **FAIL** (not even large-text AA). Never use white on accent |
| Text `#08160a` | Accent `#42a980` | **6.39** | AA: the required accent-foreground |
| Accent `#42a980` (as text) | Background `#f4fbf5` | **2.77** | **FAIL**: accent is never used as text or icon colour on light surfaces |
| Accent `#42a980` (as text) | White | **2.91** | **FAIL** |
| **Text `#08160a` | Secondary `#86d0af`** | **10.32** | AAA: text on secondary is fine when it is the dark text colour |
| White `#ffffff` | Secondary `#86d0af` | **1.80** | **FAIL** |
| Primary `#2c6d34` | Secondary `#86d0af` | **3.49** | Large text / non-text only; **fails** for normal text |
| Secondary `#86d0af` (as text) | Background `#f4fbf5` | **1.71** | **FAIL**: secondary is a fill colour only on light surfaces |

**Derived light pairs**

| Text / element | On | Ratio | Result |
| --- | --- | --- | --- |
| Muted-fg `#4b5e4e` | Background `#f4fbf5` | 6.63 | AA |
| Muted-fg `#4b5e4e` | Muted `#e6f2e8` | 6.06 | AA |
| Text `#08160a` | Muted `#e6f2e8` | 16.14 | AAA |
| Primary `#2c6d34` | Muted `#e6f2e8` | 5.45 | AA |
| Border `#6f8a72` (input outline) | Background `#f4fbf5` | 3.59 | AA non-text |
| Border-subtle `#d5e8d8` | Background `#f4fbf5` | 1.22 | Decorative only; must never be the only boundary of a control |
| Ring `#2c6d34` | Background `#f4fbf5` | 5.97 | AA non-text |
| Destructive `#b42332` (text) | Background `#f4fbf5` | 6.19 | AA |
| White | Destructive `#b42332` | 6.51 | AA |

**Dark pairs**

| Text / element | On | Ratio | Result |
| --- | --- | --- | --- |
| Foreground `#e8f5ea` | Background `#08160a` | 16.54 | AAA |
| Foreground `#e8f5ea` | Card `#0d1f10` | 15.30 | AAA |
| Foreground `#e8f5ea` | Muted `#1a2e1d` | 12.86 | AAA |
| Primary `#86d0af` (text/link) | Card `#0d1f10` | 9.55 | AAA |
| Primary `#86d0af` (text/link) | Muted `#1a2e1d` | 8.02 | AAA |
| Primary-fg `#08160a` | Primary `#86d0af` | 10.32 | AAA |
| Secondary-fg `#e8f5ea` | Secondary `#2c6d34` | 5.59 | AA |
| Accent `#42a980` (text) | Card `#0d1f10` | 5.91 | AA (acceptable on dark only) |
| Accent-fg `#08160a` | Accent `#42a980` | 6.39 | AA |
| Muted-fg `#a6b8a8` | Card `#0d1f10` | 8.23 | AAA |
| Muted-fg `#a6b8a8` | Muted `#1a2e1d` | 6.91 | AA |
| Border `#5f7f63` | Card `#0d1f10` | 3.85 | AA non-text |
| Destructive `#ff9ca7` (text) | Card `#0d1f10` | 8.66 | AAA |
| Destructive-fg `#08160a` | Destructive `#ff9ca7` | 9.35 | AAA |

**Glass caveat.** These ratios hold only for opaque surfaces. Text on glass takes the colour of
whatever scrolls behind it, so it can't be checked statically. §5 handles this with a tint floor
and a check against the worst-case backdrop.

---

## 3. Typography system

### 3.1 Roles

| Font | Role | Where used |
| --- | --- | --- |
| **Exo** (primary) | Display, headings, navigation | App-bar titles, screen headings, tab-bar labels, plan names, large numerals on the Usage screen |
| **Proza Libre** (secondary) | Body and UI labels | Chat prose, task/usage details, buttons, form labels, helper and error text |
| **Trykker** (tertiary) | Accents only | Welcome tagline, empty-state quotes, one callout style ("Tip"). Never in dense content, buttons or state labels |

### 3.2 Loading on Flutter

The web-only options in the brief (`next/font`, a `<link>` with `display=swap`) do not apply. Plan:

1. Add `google_fonts: 8.2.1`.
2. **Bundle the font files as assets** under `mobile/assets/google_fonts/`. The `google_fonts`
   README says files matching its naming in `pubspec.yaml` `assets` take priority over HTTP
   fetching. This keeps the app offline-first and avoids a flash of the fallback font (the Flutter
   equivalent of FOUT).
3. Turn off runtime fetching in release builds. The exact API (`GoogleFonts.config.allowRuntimeFetching = false`)
   is **UNVERIFIED** against 8.2.1; confirm it in the package's API docs during T1.3.
4. Register each family's `OFL.txt` with `LicenseRegistry`, following the README's "Licensing
   Fonts" section, so the licences appear on the in-app licences page.
5. Reference the fonts in one `KarmiTypography` builder. Widgets never call `GoogleFonts.*`
   directly.

### 3.3 Weights to bundle (availability verified on the Google Fonts CSS2 API)

| Family | Available | Bundle |
| --- | --- | --- |
| Exo | 100–900, upright and italic (variable) | 500, 600, 700 upright only |
| Proza Libre | 400, 500, 600, 700, 800 upright; italic verified for 400 (other italics **UNVERIFIED**) | 400, 400 italic, 600 |
| Trykker | **400 upright only (no italic)** | 400. Quotes must not use `FontStyle.italic`, or Flutter will synthesise a fake slant |

Character subsets: the CSS2 responses did not show subset labels, so which scripts each family
covers is **UNVERIFIED**. I believe all three are Latin / Latin Extended only and **do not include
Devanagari**. Design.md requires Hindi, so every text style sets `fontFamilyFallback` (below).

### 3.4 Fallback stacks (`fontFamilyFallback`)

| Font | Fallback chain |
| --- | --- |
| Exo | `Noto Sans Devanagari` (bundled, see Q5), then the platform default (Roboto on Android, SF Pro on iOS) |
| Proza Libre | `Noto Sans Devanagari`, then the platform default |
| Trykker | `Noto Serif Devanagari`, then the platform serif |

Code and data use the platform monospace, as Design.md specifies.

### 3.5 Type scale

Values are logical pixels; line height is written as a multiplier. The scale follows Design.md:
16px body at 1.5–1.6, labels 13–14px, headings 20/24/32.

| M3 slot | Font / weight | Size / line height | Use |
| --- | --- | --- | --- |
| `displaySmall` | Exo 700 | 32 / 1.25 | Welcome and Usage headline |
| `headlineSmall` | Exo 600 | 24 / 1.33 | Screen headings |
| `titleLarge` | Exo 600 | 20 / 1.4 | Section headings, plan names |
| `titleMedium` | Exo 600 | 16 / 1.5 | App-bar title, card titles |
| `labelLarge` | Proza Libre 600 | 14 / 1.43 | Buttons |
| `labelMedium` (nav) | Exo 500 | 13 / 1.3 | Tab-bar labels |
| `bodyLarge` | Proza Libre 400 | 16 / 1.55 | Chat prose, default body |
| `bodyMedium` | Proza Libre 400 | 14 / 1.5 | Secondary detail |
| `labelSmall` | Proza Libre 600 | 13 / 1.38 | Status chips, metadata (never smaller than 13) |
| `KarmiText.quote` (extension) | Trykker 400 | 18 / 1.55 | Accent callouts only |

Every size scales with `MediaQuery.textScalerOf`. Layouts must reflow at 2.0× without clipping
(Design.md's 200% gate). Chat bubbles stay within roughly 65–75 characters per line by capping
their width.

---

## 4. Library integration (Flutter equivalents)

| # | Requested | Decision | Flutter approach | Theming | Risks |
| --- | --- | --- | --- | --- | --- |
| 1 | `loading-dev` | **Omit; replace** | Use Flutter's built-in `CircularProgressIndicator` / `LinearProgressIndicator` in one `KarmiLoader` widget. Optional third-party alternatives, both verified on pub.dev: `loading_animation_widget` 1.3.0 (2024-10-02) and `flutter_spinkit` 5.2.2 (2025-08-11). Neither is needed for v1 | Colours from `ColorScheme.primary` / `secondary` | Design.md forbids "fake reasoning animations": a loader shows only while a real request is pending (for example between `POST /v1/messages` and its response). Under reduced motion, show a static icon and text |
| 2 | beUI skill | **Omit** | The skill installs React TSX through shadcn; there is nothing for Dart. The components it would have supplied map to Flutter as follows: `bottom-sheet` → `GlassModalSheet` / `showModalBottomSheet`; `prompt-input` → an app-owned `Composer` widget; `message-bubble` → an app-owned `MessageBubble`; `animated-toast-stack` → `ScaffoldMessenger` SnackBar; `todo-list` → `ListView` of `TaskTile` | Tokens from §2 | No Flutter port of beUI was found. Its catalogue is only used as naming inspiration |
| 3 | orbkit `shdr-01` | **Omit for v1 (hard license blocker)** | shdr-01's shader is "Non-commercial use only" (XorDev), and Karmi has paid tiers (yanta, trika, part), so it cannot ship. If an orb is still wanted, write an **original** GLSL fragment shader, load it through Flutter's `FragmentProgram` (`flutter: shaders:` in `pubspec.yaml`), and use it only as the Welcome-screen hero behind glass. Optional helper: `flutter_shaders` 0.1.3 (2024-09-26, verified) | Uniforms carry the primary, secondary and accent colours | GPU cost stacks with the glass shader, so the orb is limited to one static screen. It pauses when off screen, shows a static frame under reduced motion, and is disabled on `GlassQuality.minimal` devices. Budget in §8 |
| 4 | `@toggles/lightbulb` | **Omit; re-create the behaviour** | Put a theme control in Settings: System / Light / Dark as a `GlassSegmentedControl` (named in the `liquid_glass_widgets` README; constructor API **UNVERIFIED**) inside the glass settings header, or a Material `SegmentedButton` inside opaque content. A lightbulb-style animated icon could be drawn with `CustomPainter` from an original design. The toggles.dev licence is **UNVERIFIED**, so do not copy its SVG paths | Selected state uses primary; the icon uses foreground | Persist the choice locally (`shared_preferences` 2.5.5, published 2026-03-25, verified on pub.dev) |
| n/a | `liquid_glass_widgets` (from CONTEXT.md) | **Use** | `await LiquidGlassWidgets.initialize()` in `main()`. Then `runApp(LiquidGlassWidgets.wrap(child: KarmiApp(), brightnessResolver: Theme.maybeBrightnessOf, adaptiveQuality: true, theme: GlassThemeData(...)))`. Screens use `GlassScaffold` + `GlassAppBar` + `GlassTabBar.bottom`. Under `MaterialApp`, the `builder` must return `Material(type: MaterialType.transparency, child: child!)` (README "Known Limitations") | `GlassThemeData(light: GlassThemeVariant(...), dark: ...)`. The glass tint is taken from `--background` / `--card` at the alpha floor in §5 | 1.7.2 is **less than 7 days old** (2026-09-22). Pin an exact earlier release that is at least 7 days old; candidate: 1.6.2 (published 2026-09-18, verified on pub.dev); re-check at install. Its "adaptive quality" is marked *experimental*. Premium quality must not be used inside scrolling lists (README) |

---

## 5. Glass treatment

### 5.1 Surface map (follows CONTEXT.md as summarised, and the `liquid_glass_widgets` "Glass vs Content" rules)

| Glass | Opaque (`--card` / `--background`) |
| --- | --- |
| `GlassAppBar` on every tab | Chat message list and bubbles |
| `GlassTabBar.bottom` (main navigation) | Task list and task cards |
| Chat composer tray: a `GlassContainer` holding an **opaque** text field and a `GlassIconButton` send control | Usage numbers and reset times, plan cards |
| Theme switch / segmented control in the Settings header | Memory (notes) list, forms, all body text |
| Overflow `GlassMenu` from app-bar actions | Task-confirmation sheet **content**: exact action, date and timezone must be readable, so the sheet's body is opaque even if the sheet frame is glass |
| n/a | Error, limit-reached and offline banners |

Rules:

- **Glass is a platter, not a wrapper.** Never nest glass controls inside `GlassCard` or
  `GlassContainer` (per the README), except the documented icon button inside the composer
  tray, which must be checked in T2.4.
- At most **3 glass surfaces on screen at once**: app bar, tab bar, and composer or menu. The
  exact limit CONTEXT.md sets is **UNVERIFIED**.
- The app bar and tab bar use the quality `GlassScaffold` assigns (it promotes bars to premium
  through `GlassIsolationScope`). Everything else uses `standard`, and `minimal` on low-end
  devices through `adaptiveQuality`.
- **Legibility floor:** glass tint alpha ≥ 0.72 in light mode and ≥ 0.78 in dark mode (proposed;
  replace with CONTEXT.md's value). Label text on glass must reach ≥4.5:1 against the tint
  composited over the worst-case backdrop. Worst case = a pure-white bubble behind light glass
  and a pure-`#08160a` region behind dark glass. Verified with golden tests in §8.

### 5.2 Reduced transparency and high contrast

- `liquid_glass_widgets` automatically swaps its shader for a plain frosted `BackdropFilter` when
  `MediaQuery.highContrastOf` is true. Its README says this signal maps to iOS **Increase
  Contrast**, **not** Reduce Transparency, and that Flutter exposes no reduce-transparency flag.
  The README describes the auto-bridge for iOS and macOS only; behaviour on Android is **UNVERIFIED**.
- Karmi therefore adds its own switch: **Settings → Display → Reduce transparency** (off by
  default). It is on automatically when `highContrast` is true. When on:
  1. A `GlassAccessibilityScope(reduceTransparency: true)` wraps the app.
  2. `KarmiGlass` wrappers render **fully opaque** `--card` surfaces with a 1px `--border` stroke
     instead of frosted glass, so contrast is fixed and equals the §2.4 ratios.
- With high contrast on, borders switch to `--foreground` and focus rings grow to 3px.

### 5.3 Reduced motion

- `MediaQuery.disableAnimationsOf(context)` is read once in a `KarmiMotion` helper.
- `liquid_glass_widgets` already snaps its spring and jelly animations when Reduce Motion is on
  (per its README).
- App transitions use 120–180ms fades or slides normally (Design.md) and `Duration.zero` under
  reduced motion.
- The loader becomes a static icon plus a text label, gyroscope lighting (`GlassMotionScope`) is
  not used, and any optional shader renders a single static frame.

---

## 6. Screen and component inventory

Taken from Design.md "Information architecture" and "Required screens", filtered to what the API
supports today.

| Screen | API today | Gaps |
| --- | --- | --- |
| Welcome / sign-in | `POST /dev/token` (dev only) | **No production auth** (Q3) |
| **Chat** | `POST /v1/messages` | No history endpoint and no streaming. States: empty, generating (while the request is pending), `outcome` → copy mapping, failed, offline, 409 in-flight, limit reached |
| Tasks / reminders | `POST /v1/tasks`, `PATCH .../complete`, `POST /v1/reminders` | **No `GET /v1/tasks` or reminders list** (Q4) |
| Usage & plan | `GET /v1/usage` | No plans catalogue endpoint; the labels come from `plans.py` |
| Memory | `GET`, `POST`, `DELETE /v1/notes` | n/a |
| Settings | Local only: theme, reduce transparency, sign out | n/a |
| Plan selection | none | Checkout is forbidden; show the four plans read-only with "Purchases unavailable" |
| Task confirmation sheet | Driven by `outcome = ASK_USER` | Needs a structured action payload from the backend (Q4) |

Shared components: `KarmiApp` (theme + glass wrap), `KarmiShell` (`GlassScaffold` + tabs),
`KarmiGlass` (glass wrapper with the opaque fallback), `MessageBubble`, `Composer`, `StatusChip`
(word + icon + colour for every `TaskState` / `Outcome`), `KarmiLoader`, `UsageMeter`, `PlanCard`,
`NoteTile`, `EmptyState` (Trykker callout), `ErrorBanner`.

### 6.1 Representative screen: **the Chat tab inside the app shell**

Why Chat goes first: it exercises every rule at once.

- Glass chrome: app bar, tab bar and composer tray.
- Opaque dense content scrolling behind the glass. This is the worst case for performance and
  legibility.
- All three fonts: Exo title and tabs, Proza Libre prose, Trykker empty-state line.
- The richest set of states, and the core API call.

**Rollout order:** Chat shell → Usage & plan → Memory → Settings (theme, reduce transparency) →
Welcome / sign-in → Tasks (after the backend list endpoint) → Plan selection (read-only) →
Task confirmation sheet → optional original hero shader.

---

## 7. Phased task list

Each task gets a task card under `docs/task-cards/MOB-xxx.md`, as AGENTS.md requires. `mobile/`
stands for the Flutter project root chosen in Q1.

**Phase 0: decisions (no code)**

- **T0.1** Resolve Q1–Q7 and record them in `docs/decisions/ADR-0002-flutter-mobile-client.md`.
  *Done when:* the ADR is merged and the Design.md token supersession is recorded.
- **T0.2** Update the `Design.md` token table and font section to the Karmi palette and fonts,
  keeping the old values in history. *Files:* `docs/blueprint/Design.md`. *Done when:* the table
  matches §2.2–2.3 of this plan.

**Phase 1: scaffold**

- **T1.1** Create the Flutter project with `flutter create --org <Q6> --platforms android,ios mobile`
  using Flutter 3.47.5 (pin it with `.fvmrc` or document the version; see Q6).
  *Files:* `mobile/**` (generated), `.gitignore` if needed. *Done when:* `flutter analyze` is
  clean and the counter app runs on an Android emulator and an iOS simulator.
- **T1.2** Add dependencies, exact-pinned and each at least 7 days old: `liquid_glass_widgets`,
  `google_fonts`, `cupertino_icons`, `shared_preferences`, `http`.
  *Files:* `mobile/pubspec.yaml`, `mobile/pubspec.lock`. *Done when:* `flutter pub get` succeeds
  and the lockfile is committed.
- **T1.3** Bundle the fonts and licences (§3.2–3.3), plus Noto Devanagari.
  *Files:* `mobile/assets/google_fonts/*`, `mobile/pubspec.yaml`, `mobile/lib/main.dart`.
  *Done when:* a widget test renders every text style with runtime fetching disabled, and the
  licence page lists OFL for each family.

**Phase 2: foundation**

- **T2.1** Add the tokens: `mobile/lib/theme/karmi_colors.dart` (ThemeExtension, light and dark,
  §2) and `karmi_theme.dart` (ColorScheme + TextTheme, §3.5). *Done when:* a unit test asserts
  every hex value and recomputes every §2.4 ratio. Any pass/fail change fails the test.
- **T2.2** Wire up the glass setup: `main.dart` (`initialize`, `wrap`, `brightnessResolver`,
  the `Material` transparency builder) and `lib/theme/karmi_glass.dart` (tint floor and opaque
  fallback). *Done when:* the app boots in light and dark with no yellow text underlines, and
  toggling `highContrast` in a test swaps glass for an opaque surface.
- **T2.3** Add `lib/theme/karmi_motion.dart` and the reduce-transparency setting (persisted).
  *Done when:* widget tests cover animations on and off, and transparency on and off.
- **T2.4** Add the API client: `lib/api/karmi_api.dart`, models mirroring `MessageView`,
  `UsageView`, `NoteView` and `Outcome`, and an idempotency-key generator. Base URL comes from
  `--dart-define`; the dev default is `http://10.0.2.2:8000` on the Android emulator.
  *Done when:* unit tests with a mocked `http.Client` cover 200, 401, 409 in-flight and
  network-error paths.

**Phase 3: representative screen (Chat + shell)**

- **T3.1** Build `lib/shell/karmi_shell.dart`: `GlassScaffold`, `GlassAppBar`, and
  `GlassTabBar.bottom` with 5 destinations (Chat, Tasks, Usage, Memory, Settings) and placeholder
  bodies. *Done when:* the tab order works with TalkBack, VoiceOver and a keyboard; tap targets
  are ≥48dp; goldens pass in light and dark.
- **T3.2** Build `lib/features/chat/`: `chat_screen.dart`, `message_bubble.dart`, `composer.dart`
  and `status_chip.dart`. Cover the empty, pending, each-outcome, failed, offline, 409 and
  limit-reached states. Copy follows Design.md ("Could not confirm completion", etc.).
  *Done when:* a widget test exists for each state, text scale 2.0 does not overflow, and the
  §8 perf gate passes on the reference low-end device.
- **T3.3** Review checkpoint: owner sign-off on screenshots before rollout.

**Phase 4: rollout** (one task per screen, in the order in §6.1)

- **T4.1** Usage & plan (`lib/features/usage/`). Only real `UsageView` values are shown; when the
  server hasn't answered, show "unavailable" (existing web-shell rule).
- **T4.2** Memory (`lib/features/memory/`).
- **T4.3** Settings (`lib/features/settings/`): theme segmented control, reduce transparency,
  licences, sign out.
- **T4.4** Welcome / sign-in (blocked on Q3).
- **T4.5** Tasks (blocked on the backend list endpoint; the backend work goes in a separate task
  card that follows CLAUDE.md rules).
- **T4.6** Plan selection, read-only.
- **T4.7** Task confirmation sheet.
- **T4.8** Optional original hero shader.

*Done when (each):* the screen's states have widget tests, goldens pass in light and dark, and the
§8 a11y gate passes.

**Phase 5: CI and release evidence**

- **T5.1** Add a separate `flutter` job to CI (`.github/workflows/ci.yml`; this is a shared file,
  so it is integrated serially). It runs format check, analyze, tests and goldens on Linux, plus
  an Android release build. *Done when:* the job is green and the Python jobs are unchanged and green.
- **T5.2** Record manual device observations in
  `docs/release-evidence/mobile-<date>.md`. *Done when:* every §8 manual item has an observation
  or is explicitly marked NOT RUN.

---

## 8. Verification gate

All commands run from `mobile/`. Python gates (`python scripts/tasks.py lint|typecheck|test-unit`) must stay green whenever backend files change.

| Gate | Check | Pass |
| --- | --- | --- |
| Typecheck / analyze | `flutter analyze` (analysis_options with `flutter_lints` or stricter) | 0 issues |
| Format / lint | `dart format --output=none --set-exit-if-changed .` | No diff |
| Tests | `flutter test` | All pass |
| Goldens | `flutter test --tags golden` for each screen × light/dark × text scale 1.0/2.0 × reduce transparency on/off | Match approved baselines |
| Build | `flutter build appbundle --release`; `flutter build ipa --release` (**macOS only**, Q7) | Both succeed |
| Contrast | Token unit test (T2.1) + glass legibility golden over worst-case backdrop | ≥4.5:1 text, ≥3:1 non-text |
| Focus / keyboard | Hardware keyboard on emulator + iPad/iOS simulator: Tab order, visible 2px `--ring` focus, Enter activates | Every control reachable |
| Screen reader | TalkBack (Android) and VoiceOver (iOS): labels, roles, state words for `StatusChip`, live-region announcement when a reply arrives; `flutter test` with `meetsGuideline(androidTapTargetGuideline)`, `iOSTapTargetGuideline`, `labeledTapTargetGuideline`, `textContrastGuideline` | All guidelines pass; manual run recorded |
| Text scaling | OS font size max and `textScaler` 2.0 | No clipping/overflow |
| Reduced motion / transparency | OS toggles on both platforms | §5.2–5.3 behaviour observed |
| Performance (profile/release build, reference low-end Android + oldest supported iPhone) | Flutter equivalents of LCP/INP: **time to first frame** (`flutter run --profile --trace-startup`), **input latency** from tap Send / tab switch to first changed frame (DevTools timeline) | Proposed: TTFF ≤ 2.0 s cold on low-end Android; input-to-frame ≤ 100 ms. CONTEXT.md budgets **UNVERIFIED**, replace when supplied |
| Glass frame budget | DevTools performance overlay while scrolling Chat behind glass app bar + tab bar + composer | Proposed: p90 UI and raster ≤ 16 ms each at 60 Hz (≤ 8 ms on 120 Hz devices), 0 shader-compilation jank after warm-up (Impeller) |
| shdr-01 cost | **Not applicable: shdr-01 is omitted (license).** If an original shader is reintroduced (T4.8): measure raster time with and without it on the low-end device, GPU memory, and battery drain over 5 min on Welcome | Proposed: shader adds ≤ 3 ms raster p90; auto-disabled on `minimal` quality |

---

## 9. Open questions and risks

**Needed from you**

1. **Q1 Location/package:** `mobile/` inside this repo (proposed) or a separate repo? Application ID / bundle ID (e.g. `ai.karmi.app`, **UNVERIFIED**)?
2. **Q2 CONTEXT.md and KARMI_THEME files:** still missing. Please commit them so glass limits, tint alpha and perf budgets marked UNVERIFIED can be replaced with the real values.
3. **Q3 Production auth:** only `POST /dev/token` exists. Which provider (phone OTP, Google/Apple sign-in, other)? Apple requires Sign in with Apple if other third-party logins are offered (App Store guideline 4.8; confirm current wording).
4. **Q4 Missing APIs:** chat history, `GET /v1/tasks`, reminders list, structured `ASK_USER` action payload, plan catalogue. OK to add these as separate backend task cards?
5. **Q5 Hindi:** Design.md requires Hindi. Bundle Noto Sans/Serif Devanagari as fallback (adds several hundred KB, size **UNVERIFIED**), or ship English-only first?
6. **Q6 Palette supersession:** confirm the green palette and three fonts replace Design.md's blue `#254EDB` tokens and system fonts. Confirm that accent `#42a980` is never used with white text and that primary `#2c6d34` is the only filled-button colour in light mode (§2.4).
7. **Q7 iOS build infrastructure:** this Windows host cannot build iOS. Mac for local builds, or macOS CI runner (GitHub-hosted `macos-*`, cost) plus Apple Developer account and signing?
8. **Q8 Reference low-end Android device** for the perf gate (model / Android version), and minimum supported Android API level and iOS version.
9. **Q9 Web/PWA:** ADR-0001 makes owned web/PWA the initial channel. Supersede it with the mobile ADR (T0.1), or keep the web shell in parallel?

**Risks**

- `liquid_glass_widgets` 1.7.2 is < 7 days old; adaptive quality is experimental; single-maintainer package risk (**UNVERIFIED**). Mitigation: exact pin, `KarmiGlass` wrapper so the package can be swapped for a plain `BackdropFilter`.
- Glass shaders on low-end Android may miss the frame budget; mitigation is `adaptiveQuality` plus the opaque fallback.
- No Reduce Transparency signal in Flutter; mitigated by the in-app setting.
- orbkit shdr-01 non-commercial licence (blocking); toggles.dev and beUI licences **UNVERIFIED** (not used).
- Chat without streaming or history feels less responsive; set expectations with honest "working" state only.
- The ADR, Design.md and CI files are shared/protected documents; changes go through their own reviewed tasks.
