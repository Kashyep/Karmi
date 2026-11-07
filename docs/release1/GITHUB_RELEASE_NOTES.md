# Karmi v0.1.0 — tester release

Karmi v0.1.0 is a tester release of the redesigned chat experience. It is distributed as an Android APK for sideloading; this is not an iOS release. Please treat responses as fallible and report problems with enough context for reproduction, without including private or sensitive data.

## What is new

- **Redesigned chat:** persistent chats, history search and management, resumable streaming states, Continue/Resume/Stop/Regenerate actions, multiline composition, text-only attachments, safe rich rendering, feedback, and clearer processing/error states. The release report records these R1 chat capabilities as implemented, with the documented scope limitations.
- **New onboarding:** first-run tester notice, Clerk email-code sign-in, profile/onboarding flow, and free-tier provisioning. The notice must be acknowledged before use.
- **Admin dashboard (web and app):** operator tooling protected by Clerk authentication, an allowlist, and a personal admin code. Admins can manage tester users and plans and review audit activity.
- **Tester plan management:** assign or change tiers, set expiry, bulk-update tester plans, and use tester labels and notes where available.
- **Scale fixes:** bounded gateway/provider work, per-user protections, daily shared capacity handling, and operational hardening. Free-model capacity remains limited (see below).

## Install

1. Download the APK supplied by the release organizer.
2. Verify its SHA-256 against the checksum supplied with that APK.
3. On Android, allow installation from the source used to obtain the APK, then sideload it.
4. Open Karmi, read and accept the tester notice, and sign in with the email code from Clerk.

## Downloads

- `karmi-v0.1.0-arm64-v8a.apk` (arm64-v8a, most phones; versionCode 2005)
- `karmi-v0.1.0-armeabi-v7a.apk` (armeabi-v7a; versionCode 1005)
- `karmi-v0.1.0-x86_64.apk` (x86_64; versionCode 4005)

All builds have versionName `0.1.0` and are release-signed with cert SHA-256:
`14a65fffbc383685c3460aee7ad9df03ac58d628427b87e606cfd90c12f88ba1`

Verify integrity with `sha256sum -c SHA256SUMS`.

**Upgrade note:** this release-signed build cannot update over an earlier debug-signed tester install. Uninstall first; local app data is lost.

## Known limits

- OpenRouter free models are subject to upstream rate limits. The evidence records a shared free key with a 50-request/day cap and 20 requests/minute, and only a capped model probe; availability and quality can vary.
- WhatsApp is blocked/disabled for this release.
- There is no iOS tester build/support for this release.
- Checkout and paid billing are disabled; tier prices are labels, not a live payment flow.
- Responses can be wrong. Do not enter passwords, bank or identity numbers, or another person's private information.

## Reporting bugs

Report a problem with:

- what you expected and what happened;
- the approximate time and device/Android version;
- a screenshot or short screen recording when safe;
- the steps and non-sensitive text needed to reproduce it; and
- the APK version/checksum, if available.

Remove personal data before sharing. Do not include credentials, Clerk codes, access codes, or private conversation content. The official bug-report destination and response-time expectation are **PENDING**.

## Release evidence and open items

The supporting evidence is in `docs/release-evidence/` and `docs/release1/`. Device Clerk sign-in was not recorded in the earlier evidence, and live-provider/device checks may not cover every path. Treat any item not explicitly verified there as **PENDING**, rather than as a guarantee.
