# Karmi Release 1 — Owner Pixel 9a Acceptance Checklist

This document is the authoritative physical device acceptance checklist for the Karmi Release 1 candidate. The repository owner executes these verification steps on a Google Pixel 9a handset against the hosted Azure Container App beta backend (`karmi-beta`).

Every test item cites its authoritative source file. All environment parameters, release commit SHAs, signing certificate digests, and artifact checksums are verified and filled by the Boss; sensitive operator credentials remain owner-held and are not recorded in the repository.

---

## 0. Pre-Install Facts & Environment

### 0.1 Target Environment & Artifact Metadata
- **Target Device**: Google Pixel 9a (Android 17 / API 35+).
- **Target Release Branch**: `origin/release1/final-clean` (PR #43).
- **Target Release APK**: `mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk` (built via `flutter build apk --release --split-per-abi` per `docs/release1/SHA256_AND_SIGNING.md` §1).
- **Hosted Beta Backend**: Azure Container App `karmi-beta` (`https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io`).
- **Release Signing Certificate SHA-256 Digest**: `14a65fffbc383685c3460aee7ad9df03ac58d628427b87e606cfd90c12f88ba1` (CN=Karmi Release, OU=Mobile, O=Karmi; APK Signature Scheme v2).
- **Release Main Commit SHA**: `3326303` (merge of PR #44, palette; on top of the PR #43 merge c1ec00c).
- **Hosted Backend Container Image Tag**: `karmiprod49bem0.azurecr.io/karmi-backend:3326303` (rollback: `54582e4`).
- **Release APK**: `~/karmi-release-artifacts/r1-3326303/karmi-0.1.0+5-3326303-arm64-v8a-release.apk`, sha256 `8ac586a41a0c1ab3f729b8bcb7623ba9620f68409487b7237c1344d96908bd80`, package `ai.karmi.app` versionName 0.1.0 versionCode 2005 (arm64 split; build number 5).

### 0.2 Critical Reinstallation Warning (Local Data Wipe)
> **WARNING: UNINSTALL WIPES ALL LOCAL APP DATA**
>
> Prior to installing the signed release APK, any existing debug or profile build must be uninstalled:
> ```bash
> adb uninstall ai.karmi.app
> ```
> Android PackageManager strictly enforces certificate signature continuity. Attempting to install the release APK over a debug-signed build will fail with `INSTALL_FAILED_UPDATE_INCOMPATIBLE` (`docs/release1/OWNER_STEPS.md` §9.3).
>
> **Notice**: Running `adb uninstall ai.karmi.app` completely wipes all local application data, including local SQLite databases, SharedPreferences, cached tokens, and offline queues (`tool/device_driver.py:283`, `docs/release1/OWNER_STEPS.md` §9.3). Ensure any diagnostic logs from previous test runs are saved prior to uninstalling.

### 0.3 Clean Installation & Reverse Port Forwarding Cleanup
1. Ensure reverse port forwarding rules from previous local mock runs are removed:
   ```bash
   adb reverse --remove-all
   ```
   *(Source: `docs/release1/OWNER_STEPS.md` §9.4)*.
2. Install the signed production release APK:
   ```bash
   adb install mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
   ```
   *(Source: `docs/release1/OWNER_STEPS.md` §9.3)*.

---

## 1. Clerk Dashboard Pre-Requisites & Hosted Admin Setup

Authoritative citations: `docs/release1/OWNER_STEPS.md` §2.6 & §3.1, `docs/release1/GOOGLE_SSO.md`, `docs/runbooks/admin-backend.md`, `src/daily_agent/config.py:135-154`.

### 1.1 Clerk Dashboard Configuration
Before starting the device test run, the owner must confirm the following configuration in the Clerk Dashboard:
1. **Enable Google Social Connection**:
   - In the Clerk Dashboard for the instance, navigate to **User & Authentication -> Social Connections**.
   - Enable **Google** SSO. (Dev instances use Clerk-managed OAuth credentials; production uses custom Google Cloud credentials per `docs/release1/OWNER_STEPS.md` §3.1).
2. **Native OAuth Redirect URI Allowlist**:
   - Navigate to **User & Authentication -> Paths** (or **SSO / Redirect URLs**).
   - Add the native application callback URI:
     ```
     ai.karmi.app://sso-callback
     ```
   - Verify Android package name `ai.karmi.app` matches the intent filter in `mobile/android/app/src/main/AndroidManifest.xml` (`docs/release1/OWNER_STEPS.md` §3.1).

### 1.2 Hosted Admin Access Setup (for Owner Clerk User ID)
Admin endpoints (`/v1/admin/*`) and the web dashboard (`/admin`) enforce four independent gates (`docs/runbooks/admin-backend.md` lines 3-15):
1. **Valid Clerk Token**: Sign in with the owner's Clerk user account.
2. **Allowlisted Clerk Subject**:
   - The owner's Clerk User ID (`user_...`, owner-held; not recorded in the repo) must be configured in `DAILY_AGENT_ADMIN_CLERK_USER_IDS` on the Azure Container App (`src/daily_agent/config.py:137-140`, `docs/release1/OWNER_STEPS.md` §2.6). `DAILY_AGENT_ADMIN_CLERK_USER_IDS` is already set on karmi-beta (value not shown).
   - If setting multiple IDs, use a comma-separated list.
3. **Database Role Flag**:
   - The user row in the Neon database must have `users.role = 'admin'` (`docs/runbooks/admin-backend.md` line 8).
   - Run SQL command:
     ```sql
     UPDATE users SET role = 'admin' WHERE clerk_subject = '<owner-clerk-user-id>';
     ```
4. **Admin Personal Code**:
   - Enroll an admin personal developer code (minimum 12 alphanumeric characters) for the owner's Clerk subject using `scripts/admin_set_code.py` (`docs/runbooks/admin-backend.md` lines 50-61):
     ```bash
     ADMIN_CLERK_USER_IDS=<owner-clerk-user-id> python scripts/admin_set_code.py --clerk-subject <owner-clerk-user-id> --generate
     ```
   - Exchange this code via `POST /v1/admin/session` to obtain the 30-minute `X-Admin-Session` token used for admin UI access.

---

## 2. Numbered Verification Checklist (Release 1 Items 1–9)

Citations: `docs/release1/PR_DRAFT.md` lines 64-73, `docs/release1/RELEASE_NOTES_v0.1.0.md` lines 62-71, `Memory.md` lines 14-23.

### Item 1: Admin Backend Additions & Monitoring Metrics
- **Source**: `docs/release1/PR_DRAFT.md` line 65; `docs/runbooks/admin-backend.md` lines 78-86; `Memory.md` line 15.
- **Steps**:
  1. Open a browser and navigate to `https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io/admin`.
  2. Authenticate using the allowlisted owner Clerk user account and provide the admin personal session code.
  3. Verify that the overview dashboard loads without console errors or CSP violations.
  4. Inspect the monitor metrics (or query `GET /v1/admin/monitor`).
- **Expected Result**: Monitor returns HTTP 200 with JSON payload containing: `requests_today`, `open_bug_reports`, `cost_today_inr`, and `model_health`. Overview tiles render properly.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 2: Measured Optimization & Performance
- **Source**: `docs/release1/perf/R1_FINAL.md` lines 1-58; `docs/release1/PR_DRAFT.md` line 66; `Memory.md` line 16.
- **Steps**:
  1. On the Pixel 9a, launch the installed signed release APK (`app-arm64-v8a-release.apk`).
  2. Confirm package size on disk matches the split-per-abi baseline (~23.00 MB / 21.94 MiB per `docs/release1/perf/R1_FINAL.md` line 53).
  3. In the Chat tab, send prompt: `long` or a multi-line conversation with markdown formatting.
  4. Scroll rapidly through message history while new tokens render.
- **Expected Result**: Chat rendering operates smoothly; Markdown AST is cached across rebuilds without re-parse stutter (`ParsedMarkdownCache`); composer interaction does not hitch.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 3: Loading Motif & Skeletons
- **Source**: `docs/release1/PR_DRAFT.md` line 67; `Memory.md` line 17; `mobile/test/widgets/karmi_typing_dots_test.dart`; `mobile/test/widgets/karmi_skeleton_test.dart`.
- **Steps**:
  1. In the Chat tab, enter a prompt and tap Send.
  2. Observe the message bubble before the first streaming token arrives.
  3. Verify the loading animation motif.
  4. Trigger a provider failure on an empty turn (e.g. prompt: `fail`).
- **Expected Result**: Animated typing dots (`KarmiTypingDots`) or placeholder skeleton shimmer (`KarmiSkeleton`) displays smoothly while waiting for response. On an empty failed turn, a clean error card is displayed without dangling action buttons.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 4: Google Sign-in / SSO via Clerk OAuth
- **Source**: `docs/release1/GOOGLE_SSO.md` lines 30-34; `docs/release1/OWNER_STEPS.md` §3; `docs/release1/PR_DRAFT.md` line 68; `Memory.md` line 18.
- **Steps**:
  1. Launch Karmi from a fresh installation or after signing out.
  2. On the Welcome / Onboarding screen, tap **Continue with Google**.
  3. When the external Google authentication sheet/browser appears, press the device Back button to test cancellation.
  4. Tap **Continue with Google** again and complete sign-in with your Google account.
- **Expected Result**:
  - Cancellation returns gracefully to the onboarding view with message `"Google sign-in was cancelled."` without crashing.
  - Completion redirects via `ai.karmi.app://sso-callback` into the Karmi application shell as an authenticated user without duplicate account provisioning.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 5: Money & INR Representation
- **Source**: `docs/blueprint/Tier_Entitlements.md` lines 11-16; `docs/release1/PR_DRAFT.md` line 69; `Memory.md` line 19; `mobile/test/widgets/money_test.dart`.
- **Steps**:
  1. Open the **Settings** tab -> tap **Plans and access code** (or view the subscription plan selection list).
  2. Verify all currency symbols and plan pricing figures across the screen.
- **Expected Result**:
  - All prices are displayed strictly in Indian Rupees (₹) with zero dollar signs (`$`):
    - **Ananta**: `₹0`
    - **Yanta**: `₹149`
    - **Trika**: `₹399`
    - **Parth**: `₹899`
  - Decimal values format cleanly (`MICRO_PER_INR = 1_000_000`); no `NaN` or `Infinity` artifacts appear (guarded to fallback to `₹0`).
- **Result**: `[ ] pass  [ ] fail`

---

### Item 6: Bug Reporting System
- **Source**: `docs/release1/PR_DRAFT.md` line 70; `docs/release1/OWNER_STEPS.md` §2.4; `Memory.md` line 20; `migrations/versions/a5b6c7d8e9f0_bug_reports.py`.
- **Steps**:
  1. In the app, navigate to **Settings** -> tap **Report a Bug**.
  2. Enter description: `Pixel 9a R1 Owner Acceptance Test Report`.
  3. Attach a screenshot using the attachment button.
  4. Tap **Submit**.
- **Expected Result**:
  - Bug report submits successfully within the 5 MB payload limit (F-02 body limit).
  - UI displays a clear, readable ticket confirmation number (e.g. `BUG-...`).
  - Report row is stored in PostgreSQL table `bug_reports` and appears in the admin Bug Inbox.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 7: Unified Shell Layout
- **Source**: `docs/release1/PR_DRAFT.md` line 71; `Memory.md` line 21; `mobile/lib/shell/karmi_shell.dart:288-375`; `mobile/test/shell/shell_parity_test.dart`.
- **Steps**:
  1. Switch between all four primary bottom tabs: **Chat**, **Tasks**, **Usage**, and **Settings**.
  2. Go to **Settings** -> toggle **Reduce Transparency** to switch between Liquid Glass (translucent) and Solid (opaque) shell modes.
  3. Inspect top app bar, bottom navigation pill, and content scroll padding.
- **Expected Result**:
  - Layout tree remains identical across both modes; tab bar semantics and icons match perfectly.
  - Switching modes changes material transparency smoothly without widget jumps, layout shifts, or clipping.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 8: Error Card Copy Rewrite & Jump Pill
- **Source**: `docs/release1/PR_DRAFT.md` line 72; `Memory.md` line 22; `mobile/lib/features/chat/chat_screen.dart:715-725`; `mobile/lib/features/chat/scroll/end_anchored_scroll.dart`.
- **Steps**:
  1. Trigger an error card in Chat (e.g., prompt `fail` or disconnect Wi-Fi before sending).
  2. In a conversation with multiple messages, scroll upward by >48dp from the bottom.
  3. Observe the floating **Jump to latest** pill. Tap the pill.
- **Expected Result**:
  - Error cards display plain-words, single-sentence explanations without raw stack dumps or unhandled exception traces.
  - The "Jump to latest" pill floats cleanly above the composer dock without obscuring input controls; tapping it smoothly animates scroll to the latest message and dismisses the pill.
- **Result**: `[ ] pass  [ ] fail`

---

### Item 9: Web Admin Dashboard Additions
- **Source**: `docs/release1/PR_DRAFT.md` line 73; `Memory.md` line 23; `docs/runbooks/admin-backend.md` lines 89-103.
- **Steps**:
  1. In a web browser, open the hosted admin dashboard at `https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io/admin`.
  2. Navigate to the **Bug Inbox** view.
  3. Locate the bug report submitted in Item 6 and click to view its detail view.
  4. Click the attached screenshot link/thumbnail.
- **Expected Result**:
  - Bug report detail shows sanitized diagnostics JSON (allowlisted parameters only).
  - Screenshot loads and displays via an authenticated `blob:` URL without CSP refusal (`img-src` allows `blob:`).
  - Filtering by status (`open`, `resolved`) works properly without 422 errors (F-08).
- **Result**: `[ ] pass  [ ] fail`

---

## 3. Ananta Teal Palette & Launcher Icon Verification

Authoritative citations: Prompt specification, `docs/design/karmi_tier_color_palettes.md` §Tier 1, `mobile/lib/theme/tier_tokens.g.dart:6-59`.

### 3.1 Palette Color Specifications
The Ananta (free tier) palette is refreshed with the new teal color system:

| Mode | Token Role | Hex Color | Expected Visual Appearance |
| :--- | :--- | :--- | :--- |
| **Light** | Primary | `#0B3D3B` | Deep Teal; used for structural headers, primary text, and solid elements |
| **Light** | Accent | `#14B8A6` | Bright Teal; used for primary CTAs, active highlights, progress indicators |
| **Light** | Secondary | `#99F6E4` | Pale Mint/Teal; used for secondary chips and subtle accents |
| **Light** | Surface | `#E6FFFB` | Mint Tinted Surface; used for elevated card surfaces |
| **Light** | Background | `#F8FFFE` | Soft Mint Canvas; main screen background |
| **Dark** | Background | `#051B1B` | Deep Obsidian Teal; main dark canvas |
| **Dark** | Card / Surface | `#072928` | Elevated Dark Teal; card containers and message bubble surfaces |

### 3.2 Screens to Inspect
1. **Android Home Screen / Launcher**:
   - Inspect the Karmi application launcher icon on the Pixel 9a home screen and application drawer.
   - **Expected**: Launcher glyph is recoloured to teal (matching `#14B8A6` / `#0B3D3B`), replacing legacy mint green.
2. **Welcome & Onboarding Screens**:
   - Inspect background canvas (`#F8FFFE` in light mode) and primary action buttons (`#14B8A6` / `#0B3D3B`).
3. **Chat Tab**:
   - In Light Mode: Background is soft mint `#F8FFFE`; message cards are `#E6FFFB`; primary CTAs and active send button are `#14B8A6` / `#0B3D3B`.
   - In Dark Mode: Background is deep obsidian teal `#051B1B`; message cards are elevated `#072928`; highlights pop in teal `#14B8A6`.
4. **Settings & Armory Tabs**:
   - Header titles and active indicators reflect the teal palette; Ananta status chip shows "Active" with teal badge.

- **Result**: `[ ] pass  [ ] fail`

---

## 4. Paid Tiers via Armory & Bottom Strip Verification

Authoritative citations: `docs/blueprint/Tier_Entitlements.md`, `docs/design/karmi_tier_color_palettes.md`, `mobile/lib/theme/tier_tokens.g.dart`, `mobile/lib/shell/karmi_shell.dart:301-321`, `mobile/lib/features/armory/armory_screen.dart`.

### 4.1 Paid Tier Palette Matrix

| Tier | Monthly Price | Theme Name | Key Palette Hex Codes |
| :--- | :--- | :--- | :--- |
| **Tier 1: Ananta** | ₹0 | The Foundation | Teal — Light: `#0B3D3B` / `#14B8A6` / `#F8FFFE`; Dark: `#051B1B` / `#072928` |
| **Tier 2: Yanta** | ₹149 | The Control | Electric Cyan (`#00D4FF`), Cobalt Navy (`#1A365D`), Ice White (`#F4F6F9`), Deep Slate (`#0A111C`) |
| **Tier 3: Trika** | ₹399 | The Trinity | Sunset Ember (`#FF5722`), Terracotta (`#8C3B20`), Warm Cream (`#FCF8F5`), Charcoal (`#171210`) |
| **Tier 4: Parth** | ₹899 | The Apex | Metallic Gold (`#D4AF37`), Iridescent Purple (`#9B4F96`), Pure White (`#FFFFFF`), Obsidian (`#000000`) |

### 4.2 Armory Gallery & Bottom Strip Inspection Steps
1. Navigate to **Settings** -> tap **Armory** (`mobile/lib/features/armory/armory_screen.dart`).
2. Verify that **Ananta** is marked **Active**.
3. Confirm that locked tiers (**Yanta**, **Trika**, **Parth**) display:
   - Padlock icon overlay.
   - `blur(4px) grayscale(80%)` filter over tier artwork (`TierPreviewArt`).
   - "Activate" button disabled / locked.
   - "Preview 10 s" button enabled.
4. **Preview Yanta (Tier 2)**:
   - Tap **Preview 10 s** on Yanta card.
   - Confirm floating `ArmoryPreviewBanner` pill appears with 10-second countdown.
   - **Check Bottom Strip**: Inspect the bottom navigation bar (`GlassTabBar.bottom` in `mobile/lib/shell/karmi_shell.dart:301-321`). The bottom pill tint immediately reflects Yanta's Electric Cyan (`#00D4FF`) and Navy glass base (`#1A365D`).
5. **Preview Trika (Tier 3)**:
   - Tap **Preview 10 s** on Trika card.
   - **Check Bottom Strip**: Bottom navigation bar tint reflects Trika's Sunset Ember (`#FF5722`) and Terracotta glass base (`#8C3B20`).
6. **Preview Parth (Tier 4)**:
   - Tap **Preview 10 s** on Parth card.
   - **Check Bottom Strip**: Bottom navigation bar tint reflects Parth's Metallic Gold (`#D4AF37`) and Obsidian glass base (`#000000`).
7. **Reversion Verification**:
   - Allow the 10-second timer to expire (or tap **End preview**).
   - Confirm app theme and bottom navigation bar cleanly revert to Ananta Teal without lingering artifacts or crashed views.

- **Result**: `[ ] pass  [ ] fail`

---

## 5. Bug Report End-to-End Verification

Authoritative citations: `docs/release1/PR_DRAFT.md` (Item 6), `docs/runbooks/admin-backend.md`, `mobile/lib/features/bug_report/bug_report_screen.dart`.

### 5.1 Submission Steps
1. In the Karmi app on the Pixel 9a, open **Settings** -> **Report a Bug**.
2. Enter description: `Pixel 9a E2E Verification Report - Release 1 Candidate`.
3. Tap the screenshot picker and attach a real device screenshot.
4. Tap **Submit Report**.

### 5.2 Verification Checks
1. Confirm a snackbar or dialog displays a readable ticket number (e.g. `BUG-` prefix followed by uppercase alphanumeric identifier).
2. Open the hosted admin dashboard in your browser:
   `https://karmi-beta.gentlepebble-6595a0fa.eastasia.azurecontainerapps.io/admin`
3. Navigate to **Bug Inbox**:
   - Verify the newly submitted ticket number appears in the list.
   - Confirm metadata: user account, device model (Pixel 9a), and category.
4. Open the ticket:
   - Confirm the entered description matches.
   - Confirm the attached screenshot renders via `blob:` URL without errors.

- **Result**: `[ ] pass  [ ] fail`

---

## 6. Jank & Performance Verification (Item 2)

Authoritative citations: `docs/release1/perf/R1_FINAL.md`, `docs/release1/perf/measure.sh`, Android dumpsys gfxinfo documentation.

### 6.1 Visual Scrolling Fluidity Check
1. In the Chat tab, open or create a long thread with at least 15–20 messages.
2. Perform rapid upward and downward flings, as well as slow finger drag scrolls.
3. Switch between tabs repeatedly.
4. **Expected**: Transitions and scrolling maintain smooth 60 Hz or 120 Hz refresh rate without stutter, dropped frames, or hitching.

### 6.2 Quantitative ADB Gfxinfo Check (Optional / Recommended)
To gather objective frame timing metrics from the Pixel 9a:
1. Reset existing graphics statistics:
   ```bash
   adb shell dumpsys gfxinfo ai.karmi.app reset
   ```
2. Interact actively with the application for 15–20 seconds (scroll through chat, open Armory, switch tabs).
3. Capture the frame profile data:
   ```bash
   adb shell dumpsys gfxinfo ai.karmi.app
   ```
4. **Evaluation Thresholds**:
   - **Janky frames percentage**: Must be `< 5.0%`.
   - **90th percentile frame time**: Must be `<= 16.6 ms` (60 Hz baseline) or `<= 8.3 ms` (120 Hz display mode).
   - **95th percentile frame time**: Must be `<= 24.0 ms`.

- **Result**: `[ ] pass  [ ] fail`

---

## 7. Failure Diagnostic Package (What to Send Back on Failure)

Authoritative citations: `docs/release1/OWNER_STEPS.md`, `docs/release1/DEVICE_TESTING.md`.

If any verification step fails, do not proceed with release tagging. Collect and return the following diagnostic artifacts:

### 7.1 ADB Logcat Capture
Capture the full buffered system and application logcat:
```bash
adb logcat -d > pixel9a_failure_logcat.txt
```
To capture a focused log of Flutter, Karmi, and Android crash exceptions:
```bash
adb logcat -d -s flutter:V Karmi:V AndroidRuntime:E CRASH:E > pixel9a_crash.txt
```

### 7.2 Device Screenshots & Screen Recording
Capture a high-resolution screenshot of the failing screen:
```bash
adb exec-out screencap -p > pixel9a_failure_screenshot.png
```
Or record a video demonstrating reproduction:
```bash
adb shell screenrecord /sdcard/failure_repro.mp4
# Perform reproduction steps, then press CTRL+C
adb pull /sdcard/failure_repro.mp4 .
```

### 7.3 Performance & Jank Dump (if Performance Issue)
```bash
adb shell dumpsys gfxinfo ai.karmi.app > pixel9a_jank_gfxinfo.txt
```

### 7.4 Triage Note Format
Along with the diagnostic files, provide a brief triage summary:
- **Failed Step Number**: (e.g., Section 2 Item 4)
- **Observed Behavior**: Exact behavior seen on phone.
- **Expected Behavior**: What was anticipated according to the checklist.
- **Network State**: Wi-Fi vs Cellular (LTE/5G).
- **Device Timestamp**: UTC time of occurrence.

---

## 8. Owner Acceptance Verdict & Sign-Off

Review all test steps above. Record the final verdict below:

- [ ] **APPROVED**: All Release 1 acceptance criteria pass on the Google Pixel 9a against the hosted beta backend. The release candidate is approved for tagging and release.
- [ ] **REJECTED**: Blockers or visual/functional regressions were encountered. See attached failure diagnostic package.

**Owner Name**: ____________________________________________

**Owner Signature**: ____________________________________________

**Date / Timestamp**: ____________________________________________

---

## 9. Summary of Verified Release Values & Owner Credentials

All release environment parameters and build artifacts have been verified by the Boss:
1. **Release Signing Certificate SHA-256 Digest**: `14a65fffbc383685c3460aee7ad9df03ac58d628427b87e606cfd90c12f88ba1` (CN=Karmi Release, OU=Mobile, O=Karmi; APK Signature Scheme v2).
2. **Release Candidate Main Commit SHA**: `3326303` (merge of PR #44, palette; on top of the PR #43 merge c1ec00c).
3. **Hosted Backend Container Image Tag**: `karmiprod49bem0.azurecr.io/karmi-backend:3326303` (rollback: `54582e4`).
4. **Owner Clerk User ID (`user_...`)**: owner-held; not recorded in the repo. `DAILY_AGENT_ADMIN_CLERK_USER_IDS` is already set on karmi-beta (value not shown).
5. **Admin Personal Code**: owner-held; not recorded in the repo. The owner enrolls it with `scripts/admin_set_code.py`.
