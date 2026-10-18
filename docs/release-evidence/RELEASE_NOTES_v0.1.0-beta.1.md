# Karmi v0.1.0-beta.1 (beta, Android)

First tester build. Every plan uses **free AI models only**; higher plans get more daily usage and
stronger model classes. Replies can be wrong. Prompts go to third-party free-model hosts, so do not enter
sensitive personal information. Legal review of the in-app notice is still pending: invite adults only.

## What is in this build
- Chat with an automatic model router (free OpenRouter models; maths, code and Hindi/Hinglish probed).
- Thumbs up/down with a reason, and Regenerate (retries on a stronger model).
- Beta **access codes**: Settings > Plans and access code. A code unlocks Yanta, Trika or Parth.
  The maintainer hands codes out personally.
- First-launch tester notice that must be acknowledged.
- Server address: Welcome screen > Server address (https only).

## Before it works for you
The app needs a running Karmi backend. This release is built with a placeholder server address; set the
real one under Welcome > Server address (or rebuild with `--dart-define=API_BASE_URL=https://...`).
Hosting steps: `ops/deploy/README.md`.

## Install
Download `app-release.apk`, check its SHA-256 against `app-release.apk.sha256`, allow installs from this
source, install. The APK is signed with the Android debug key (no release keystore exists yet), so
updates must be installed over the same debug-signed build.

## Known limits
OpenRouter free models: 20 requests/min and 50 requests/day per key without credits, so total beta
capacity is small. Only 7 of 15 free chat models answered the capped probe; scores are provisional.
See `docs/release-evidence/known-issues.md`.
