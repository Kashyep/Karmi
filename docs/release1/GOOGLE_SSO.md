# Google Single Sign-On (SSO) Integration

This document outlines the implementation of Google Single Sign-On (SSO) for the Karmi app, detailing the necessary setup and functionality for enabling this feature.

## Overview
The Karmi app supports Google SSO by integrating with Clerk for user authentication. This feature enables users to sign in using their Google accounts, streamlining the login process and enhancing user experience.

## Features Implemented
- **OAuth Redirect URL**: The app utilizes the redirect URL `ai.karmi.app://sso-callback` as defined in `clerk_sso.dart`.
- **Google Sign-In Action**: The sign-in functionality is encapsulated within the `signInWithGoogle()` method, which returns a `GoogleSignInResult`. This method handles success, cancellation, and error states with a timeout mechanism.
- **User Interface**: The Google sign-in button is displayed in the account onboarding flows when the Clerk configuration is available.

## Code Implementation
1. **Clerk SSO Configuration**: The `clerk_sso.dart` file defines necessary configurations including the OAuth redirection URL and functions to manage the deep link stream. The function `isSsoCallbackLink(Uri)` is used to determine if a link is a valid SSO callback.
2. **SignIn Logic**: Implemented in `clerk_email_code_actions.dart` via `signInWithGoogle()`, which detects cancellations and errors while ensuring a timeout notification is shown if sign-in does not complete in a designated timeframe.
3. **Button Implementation**: The button for triggering Google sign-in is implemented in `google_sign_in_button.dart`, integrated into the onboarding widget within `account_auth_step.dart` to appear conditionally based on Clerk's availability.
4. **Main Application Wiring**: The application's main entry in `main.dart` connects the redirect generator and the deep-link stream to Clerk's authentication functions.

## Android Configuration
- **Manifest Changes**: In `AndroidManifest.xml`, the intent filter for the `MainActivity` is configured to handle the `ai.karmi.app` scheme and `sso-callback` host, ensuring that incoming SSO callbacks are correctly processed.
- **Method and Event Channels**: In `MainActivity.kt`, a MethodChannel named `ai.karmi.app/deep_links/messages` and an EventChannel `ai.karmi.app/deep_links/events` are established to facilitate communication between the Android platform and Flutter's context. The `app_links` package was not utilized due to the unavailability of the package in the offline cache, opting for a minimal platform channel instead.

## Backend Testing
The backend testing is covered in `tests/e2e/test_clerk_sso_identity.py`, verifying that the same Clerk `sub` reuses one user and account, and a distinct `sub` provisions a fresh customer without duplicates. Run the test using:
```bash
python -m pytest tests/e2e/test_clerk_sso_identity.py -q
```

## Owner Checklist
1. In the Clerk dashboard for the DEVELOPMENT instance: enable Google as a social connection (development instances use Clerk-managed Google credentials; production needs your own Google OAuth client).
2. In the Clerk dashboard, add the native redirect `ai.karmi.app://sso-callback` to the allowed redirect URLs / allowlist for the application.
3. Confirm the Android package/applicationId `ai.karmi.app` matches the app and the intent filter.
4. On a real Android device, run Google sign-in, confirm the browser returns to the app, confirm cancel shows 'Google sign-in was cancelled.', and confirm no duplicate accounts after repeat sign-in.
5. Record the result in `docs/release1/` device testing notes. **Do not claim it passed until it does.**

## Verification Status
As of now, the real Google sign-in feature has NOT been VERIFIED on any devices or the live Clerk instance. Only offline gates, such as `flutter analyze`, `flutter test`, and backend end-to-end tests, have been run successfully, alongside a profile APK build being created.