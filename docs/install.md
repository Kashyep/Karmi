# Installing Karmi

Karmi is distributed through GitHub Releases. There is no Play Store or App Store listing.

> No release has been published yet. The links below start working after the first release is
> published from a `v*` tag by the `release` workflow.

Releases are created as drafts and reviewed by the maintainers before they go public. Builds
marked "pre-release" (`-beta`, `-rc`) are test builds.

## Android

Requirements: an Android phone that allows installing apps from outside the Play Store.

### Recommended: Obtainium (installs and updates)

[Obtainium](https://github.com/ImranR98/Obtainium) installs apps straight from GitHub Releases
and notifies you about new ones.

1. Install Obtainium from its [releases page](https://github.com/ImranR98/Obtainium/releases)
   (or F-Droid).
2. Open this link on your phone: <obtainium://add/https://github.com/Ruud-en-Blauw/Karmi>
   (if the link does nothing, open Obtainium, tap **Add App** and paste
   `https://github.com/Ruud-en-Blauw/Karmi`).
3. To receive pre-release builds, enable **Include prereleases** for the app in Obtainium.

### Manual install

1. Open <https://github.com/Ruud-en-Blauw/Karmi/releases/latest> and download
   `karmi-<version>.apk`.
2. Open the file and allow your browser or file manager to install unknown apps when asked.

### Check the download

Each release lists the SHA-256 of the signing certificate in its notes and has a
`SHA256SUMS.txt` asset.

```sh
sha256sum karmi-<version>.apk          # compare with SHA256SUMS.txt
apksigner verify --print-certs karmi-<version>.apk   # Android SDK build-tools
```

The `certificate SHA-256 digest` line must match the value in the release notes.

### Updating and signing keys

Android only updates an app when the new APK is signed with the same key. If an update is
refused (for example because an earlier test build was signed with a different key), uninstall
Karmi once and install the new APK. Uninstalling removes the app's local data.

## iOS (experimental, untested on device)

The iOS build is **experimental and has not been tested on a device**. It is an unsigned IPA:
Apple does not allow installing it directly, so it has to be signed on your own device by a
sideloading tool using your own Apple ID. Minimum iOS version: 15.0.

Known limitations:

- Google sign-in is not wired for iOS (the app registers no `ai.karmi.app` URL scheme on iOS).
  Use the email-code sign-in instead. This is inferred from the app configuration and has not
  been tested on a device.
- With a free Apple ID, sideloaded apps expire after 7 days and must be refreshed, and only
  3 sideloaded apps can be active at a time
  ([AltStore](https://faq.altstore.io/altstore-classic/activating-apps),
  [SideStore](https://docs.sidestore.io/docs/faq)).
- iOS 16 or later needs Developer Mode turned on:
  **Settings -> Privacy & Security -> Developer Mode**
  ([Apple](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)).

### Option 1: SideStore or AltStore source (updates inside the app)

Each release publishes an AltStore-format source at:

```text
https://github.com/Ruud-en-Blauw/Karmi/releases/latest/download/source.json
```

Both [SideStore](https://docs.sidestore.io/docs/installation/prerequisites) and
[AltStore](https://faq.altstore.io/) can add it.

1. Install SideStore or AltStore by following their own instructions.
2. Add the source:
   - SideStore: open `sidestore://source?url=https://github.com/Ruud-en-Blauw/Karmi/releases/latest/download/source.json`
     on the device. This link fails if SideStore is not installed.
   - AltStore: open
     `altstore://source?url=https://github.com/Ruud-en-Blauw/Karmi/releases/latest/download/source.json`,
     or add the source URL above manually in the **Browse** tab.
3. Open the Karmi entry and tap **Free** / **Install**.

`releases/latest` points at the newest published non-pre-release. Pre-release builds are not
listed in this source.

### Option 2: Sideloadly (manual)

1. Install [Sideloadly](https://sideloadly.io) on a Mac or Windows PC.
2. Download `karmi-<version>.ipa` from the
   [latest release](https://github.com/Ruud-en-Blauw/Karmi/releases/latest).
3. Connect the device, drag the IPA into Sideloadly, enter your Apple ID and install.

Do not use third-party "enterprise certificate" installers: they ask you to trust a stranger's
signing identity and can be revoked at any time.

### Later: web app (PWA)

An installable web app would avoid sideloading. It is not available yet: the web shell only
supports developer sign-in, the mobile app has no web target, and there is no offline support.

## Report a problem

Use the in-app bug report (preferred), or open an issue at
<https://github.com/Ruud-en-Blauw/Karmi/issues>.

## For developers

The backend Python package is `daily-agent` (`src/daily_agent/`). The release workflow is
`.github/workflows/release.yml`; `scripts/release/make_altstore_source.py` builds `source.json`
and extracts the release notes from `CHANGELOG.md`. Release checklist:

1. Set the version in `mobile/pubspec.yaml` (`X.Y.Z[-beta|-rc[.N]]+BUILD`) and add a matching
   `## [X.Y.Z]` section to `CHANGELOG.md`.
2. Push the tag `vX.Y.Z`. The workflow builds the artifacts and creates a **draft** release.
3. Review the draft and publish it manually.

Android CI signing needs the repository secrets `ANDROID_KEYSTORE_BASE64`,
`ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`. If any is missing,
the workflow skips the APK (it never debug-signs a release) and the APK has to be built and
uploaded by hand.
