# Karmi Release 1 — APK Checksums & Signing Verification

This document specifies the local checksum generation recipe, signing certificate verification, and repository signing configuration for Karmi Release 1 (build 0.1.0+5).

---

## 1. SHA256SUMS Recipe

The release owner runs these commands locally after building release APKs.

### Build Step
From the repository's `mobile/` directory:

```bash
# Build release APKs (split per ABI)
flutter build apk --release --split-per-abi
```

*Note: In resource-constrained environments, wrap the build with the heavy lock:*
```bash
flock -w 900 /tmp/karmi-heavy.lock flutter build apk --release --split-per-abi
```

### Output Directory
The build artifacts are located at:
- `mobile/build/app/outputs/flutter-apk/` (relative to repository root)
- `build/app/outputs/flutter-apk/` (relative to `mobile/`)

When built with `--split-per-abi`, documented output artifacts include:
- `app-arm64-v8a-release.apk` (documented in `release_completion.md`)
- `app-armeabi-v7a-release.apk`
- `app-x86_64-release.apk`

*(If built without `--split-per-abi`, the artifact is `app-release.apk`.)*

### Generate Checksums
From the APK output directory:

```bash
cd mobile/build/app/outputs/flutter-apk
sha256sum *.apk > SHA256SUMS
```

### Verify Checksums
To verify that built or downloaded APKs match the recorded checksums:

```bash
cd mobile/build/app/outputs/flutter-apk
sha256sum -c SHA256SUMS
```

All files should report `OK`.

---

## 2. Signing Certificate Verification

### Certificate Fingerprint
The release signing certificate SHA-256 fingerprint:
- **Prefix:** `14a65fff`
- **Suffix:** `8ba1`

### Verification Command
The full certificate fingerprint must be verified by the owner on the built APK using `apksigner` from the Android SDK build tools:

```bash
<android-sdk>/build-tools/<ver>/apksigner verify --print-certs mobile/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
```

*(Replace `<android-sdk>` with your local Android SDK root, e.g., `$ANDROID_HOME` or `~/Android/Sdk`, and `<ver>` with your installed build-tools version, e.g., `34.0.0` or `35.0.0`.)*

Confirm that:
1. `Signer #1 certificate SHA-256 digest` matches the full fingerprint beginning with `14a65fff` and ending with `8ba1`.
2. `Verifies` reports `true` for APK Signature Scheme v2/v3.

### Key Custody & Security Policy
- The private release signing keystore is stored strictly outside the repository (at `~/.karmi-keys/karmi-release.jks`, per `docs/runbooks/release-signing.md`).
- **CRITICAL**: The signing keystore and `key.properties` MUST NOT be copied into the repository, tracked in git, or printed to terminal logs, issues, or chats.
- Never open, print, or disclose the contents of `~/.karmi-keys` or any private key credentials.

---

## 3. Repository Signing Configuration & Status

### Unsigned-in-Repo Status
As documented across repository documentation (`docs/runbooks/release-signing.md`, `release_completion.md`, `Memory.md`), the release APK is **unsigned-in-repo**. The git checkout intentionally contains no keystore files or passwords.

### Configuration in `mobile/android/app/build.gradle.kts`
The Gradle configuration handles release signing as follows:

1. **Keystore Properties Lookup**:
   Looks for `key.properties` in `mobile/android/` (`rootProject.file("key.properties")`).

2. **Mandatory Guard on Release Builds**:
   ```kotlin
   val keystorePropertiesFile = rootProject.file("key.properties")
   val keystoreProperties = Properties()
   val allowDebugSigning = System.getenv("KARMI_ALLOW_DEBUG_SIGNING") == "1"
   val releaseBuildRequested = gradle.startParameter.taskNames.any { task ->
       task.contains("release", ignoreCase = true)
   }
   if (releaseBuildRequested && !keystorePropertiesFile.exists() && !allowDebugSigning) {
       throw GradleException(
           "Release signing requires mobile/android/key.properties; set KARMI_ALLOW_DEBUG_SIGNING=1 only for debug signing."
       )
   }
   ```
   If a release build is requested and `key.properties` is missing, the build fails immediately unless explicitly overridden with `KARMI_ALLOW_DEBUG_SIGNING=1`.

3. **Signing Configurations Definition**:
   ```kotlin
   signingConfigs {
       if (keystorePropertiesFile.exists()) {
           create("release") {
               keyAlias = keystoreProperties["keyAlias"] as String
               keyPassword = keystoreProperties["keyPassword"] as String
               storeFile = file(keystoreProperties["storeFile"] as String)
               storePassword = keystoreProperties["storePassword"] as String
           }
       }
   }
   ```

4. **Build Type Mapping**:
   ```kotlin
   buildTypes {
       release {
           signingConfig = if (keystorePropertiesFile.exists()) {
               signingConfigs.getByName("release")
           } else {
               signingConfigs.getByName("debug")
           }
       }
   }
   ```

To perform an official signed release build, the owner creates local `mobile/android/key.properties` (git-ignored) pointing to the external keystore before invoking `flutter build apk --release`.
