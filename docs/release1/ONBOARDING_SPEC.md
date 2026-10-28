# Karmi Release 1: Onboarding Specification

## 1. Overview & Architecture
This document details the redesigned first-run and onboarding experience for Karmi Release 1, referencing patterns from the Mobbin onboarding flow (`docs/release1/onboarding-ref/`). The flow cleanly decouples introductory education, authentication via Clerk, user profile onboarding, free-tier subscription provisioning, and system permissions.

### Current Inventory
- **Auth & Clerk**: `ClerkSignInCard` (`mobile/lib/auth/clerk_sign_in_card.dart`), `ClerkEmailCodeActions` (`mobile/lib/auth/clerk_email_code_actions.dart`), `KarmiSession` (`mobile/lib/auth/session.dart`).
- **First-run Screens**: `WelcomeScreen` (`mobile/lib/features/welcome/welcome_screen.dart`), `TesterNoticeScreen` (`mobile/lib/features/welcome/tester_notice_screen.dart`), `PlanSelectionScreen` (`mobile/lib/features/plans/plan_selection_screen.dart`).
- **Routes / Shell Root**: `KarmiApp` in `mobile/lib/app.dart` switches between `TesterNoticeScreen`, `WelcomeScreen`, and `KarmiShell`.
- **Tests & Goldens**: `clerk_sign_in_card_test.dart`, `tester_notice_test.dart`, `screens_test.dart`, `golden_test.dart` (`welcome_obsidian`, `welcome_daybreak`).

---

## 2. Onboarding Flow Sequence

1. **Step 1: Welcome & Value Propositions (`WelcomeStep`)**
   - Hero brand presentation (Karmi eco icon, wordmark, tagline).
   - Swipeable carousel/cards highlighting key values: Intelligent Drafts, Cross-Tool Tasks, Local Context & Control.
   - Primary Action: `PillCta(label: "Get Started")` -> advances to Sign Up/In.
   - Secondary Action: `TextButton("Already have an account? Sign in")`.

2. **Step 2: Authentication via Clerk (`AuthStep`)**
   - Seamless Clerk integration supporting Email + OTP verification, plus Google OAuth when configured.
   - Fields: Email entry with auto-focus; transition to 6-digit OTP code input (`OtpField`).
   - Error states: Invalid email, expired/incorrect OTP, network timeout.
   - Mid-flow resume: Leverages `ClerkEmailCodeActions.isMidSignUp` to preserve progress across cold starts.

3. **Step 3: User Profile & Name (`ProfileStep`)**
   - Friendly greeting, requests preferred First & Last name (or display handle).
   - Validation: First name required (minimum 2 characters, trimmed).
   - Backend sync: Persisted via backend profile update endpoint.

4. **Step 4: Language & Karmi Preferences (`PreferencesStep`)**
   - Selection of UI language / response locale (English, Indonesian, etc.) and prompt interaction mode.
   - Uses `ChoiceTile` widgets for single-select or multi-select option matrices.
   - Stored locally in `KarmiSettings` and synchronized with user account profile.

5. **Step 5: Plan Introduction - Ananta Free Tier (`PlanIntroStep`)**
   - Value highlight of the Ananta tier: Unmetered conversational assistance, local caching, baseline intelligence tokens.
   - Visual tier card mapped to `KarmiTier.ananta` styling.
   - Primary Action: `PillCta(label: "Continue with Ananta Free")`.

6. **Step 6: Notification & System Permissions (`PermissionsStep`)**
   - Soft pre-prompt explaining why notifications help (task background completion, draft readiness).
   - "Allow Notifications" triggers platform permission dialogue; "Maybe Later" gracefully defers without blocking.

7. **Step 7: Onboarding Completion (`CompleteStep`)**
   - Confetti/welcome celebration micro-interaction.
   - Sets `hasCompletedOnboarding = true` in persistent preferences.
   - Cutover transitions navigation root directly to `KarmiShell`.

---

## 3. Component Architecture & Token Mapping

All components MUST bind strictly to Karmi's design system tokens (`KarmiColors`, `KarmiTokens`, `KarmiGlass`, `KarmiMotion`):

| Component | Role / Specs | Token & Styling Mapping |
| :--- | :--- | :--- |
| `OnboardingScaffold` | Multi-step wrapper with animated progress bar, back navigation, safe-area management, and scrollable content slot. | Background: `KarmiColors.background`. Header: `KarmiTokens.paddingLg`. Progress Track: `KarmiColors.surfaceSubtle`, Active: `KarmiColors.accentPrimary`. |
| `PillCta` | Full-width or inline rounded high-contrast primary call-to-action button. Loading spinner replacement when busy. | Height: 52dp (>= 48dp target). Shape: StadiumBorder / 26dp radius. Background: `KarmiColors.accentPrimary`, Text: `KarmiColors.onAccentPrimary`. Motion: `KarmiMotion.quick`. |
| `OtpField` | 6-box individual or segmented pin field with auto-advance, backspace handling, clipboard paste, and error shake. | Height/Width: 48x56dp per cell. Border: `KarmiColors.borderSubtle`, Focused: `KarmiColors.borderActive` (2dp), Error: `KarmiColors.danger`. Font: `text.headlineMedium` tabular figures. |
| `ChoiceTile` | Selectable card with radio/check indicator, headline, description, and optional icon. | Background: `KarmiColors.surface`, Selected: `KarmiColors.surfaceAccent` with `KarmiColors.accentPrimary` border (1.5dp). Radius: `KarmiTokens.radiusMd` (12dp). Padding: 16dp. |

---

## 4. Copy & State Matrix

### States
- **Loading / Submitting**: `PillCta` displays a centered `CircularProgressIndicator` (stroke width 2.5), buttons disabled, inputs read-only.
- **Validation Errors**: Inline error text beneath inputs using `KarmiColors.danger` with `Icons.error_outline` semantic icons.
- **Offline / Connectivity**: Top banner inside `OnboardingScaffold` indicating offline mode; retries backed by exponential backoff.
- **Back Navigation**: Explicit back chevron in top-left app bar. Back navigation saves state to avoid losing field input.
- **Resume Mid-Flow**: Onboarding step index and completed form draft stored in `SharedPreferences` under key `onboarding_active_step`. App relaunch auto-navigates to last uncompleted step.

### Copy Table
- **Welcome Title**: "Meet Karmi"
- **Welcome Subtitle**: "One intelligent workspace for your thoughts, tasks, and drafts."
- **Auth Title**: "What's your email?"
- **Auth Helper**: "We'll send a 6-digit confirmation code. No password needed."
- **OTP Title**: "Enter verification code"
- **OTP Subtitle**: "We sent a code to {email}. Use the newest email from Clerk."
- **OTP Resend**: "Didn't get a code? Resend in {seconds}s"
- **Profile Title**: "What should we call you?"
- **Profile Subtitle**: "Your name helps personalize conversations and generated drafts."
- **Preferences Title**: "Set your preferences"
- **Plan Title**: "You're starting on Ananta Free"
- **Plan Description**: "Enjoy essential features, reliable local execution, and free community models."
- **Notification Title**: "Stay updated on background tasks"
- **Notification Subtitle**: "Get notified when complex generations or multi-step tasks finish."

---

## 5. Accessibility (A11y) & Usability

1. **Touch Targets**: All interactive controls (`PillCta`, `ChoiceTile`, text links, back buttons) enforce minimum 48x48dp interactive bounding boxes.
2. **TalkBack / VoiceOver Semantics**:
   - `OnboardingScaffold` announces step progress: `Semantics(liveRegion: true, label: "Step X of Y")`.
   - Headers explicitly tagged with `Semantics(header: true)`.
   - `OtpField` provides grouped semantics announcement: "Verification code input, 6 digits. Current code entered: ...".
   - `ChoiceTile` includes `selected` boolean in semantics node.
3. **Typography & Text Scaling**:
   - Scales smoothly up to 200% (`textScaleFactor: 2.0`) without layout clipping or text truncation.
   - All scrolling views utilize `ListView` / `SingleChildScrollView` with bounce to accommodate oversized text.
4. **Contrast Compliance**:
   - Primary, secondary, and error typography strictly observe WCAG AA (>= 4.5:1) against both Obsidian (dark) and Daybreak (light) backgrounds.
