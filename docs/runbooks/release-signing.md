# Android release signing

## Key custody

The release keystore is kept outside the repository at `~/.karmi-keys/karmi-release.jks`.
The password file is `~/.karmi-keys/key.properties`; both the directory and password file MUST remain private. A copy is maintained at `~/.karmi-keys/backup/karmi-release.jks`.
Never commit `key.properties` or a keystore, and never paste passwords into logs or chat.

## Local setup

Create `mobile/android/key.properties` with the absolute keystore path and the credentials issued by the release owner:

```properties
storeFile=~/.karmi-keys/karmi-release.jks
storePassword=<release-store-password>
keyAlias=karmi-release
keyPassword=<release-key-password>
```

This file is ignored by `mobile/android/.gitignore`. The Gradle configuration uses the `karmi-release` signing config when the file exists; without it, release variants fall back to the debug signing config for local development only.

## Verify signing configuration

From `mobile/android`, run the report under the shared heavy-build lock:

```bash
nice -n 10 flock -w 900 /tmp/karmi-heavy.lock ./gradlew :app:signingReport
```

Confirm the `release` variant reports alias `karmi-release` and the expected keystore path. Do not run a full release build solely to verify signing.

## Rotation and backup

Do not overwrite an existing keystore. For a planned rotation, create a separately reviewed replacement, update the protected password file, copy the new keystore to the protected backup directory, and verify the report before release. Preserve the old keystore according to the release-retention policy.
