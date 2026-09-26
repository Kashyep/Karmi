# Karmi mobile client (Flutter, Android + iOS)

Decision record: `docs/decisions/ADR-0002-flutter-mobile-client.md`.
Plan: `docs/UI_IMPLEMENTATION_PLAN.md` (sections 2–8). Task cards: `docs/task-cards/MOB-*.md`.

- Flutter 3.47.5 (Dart 3.13.4). Application / bundle ID: `ai.karmi.app`.
- Dependencies are exact-pinned in `pubspec.yaml`; fonts are bundled under
  `assets/google_fonts/` (runtime fetching is disabled, OFL licences are on the licences page).

## Run against the local backend

```sh
python scripts/tasks.py dev                      # repo root: http://127.0.0.1:8000
cd mobile
flutter run                                      # Android emulator: default http://10.0.2.2:8000
adb reverse tcp:8000 tcp:8000                    # physical device, then:
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Sign-in is development-only (`POST /dev/token`). It is on by default outside release builds;
`--dart-define=KARMI_DEV_AUTH=true|false` overrides it. Debug and profile builds allow cleartext
HTTP for the local backend; release builds do not.

## Gates (run from `mobile/`)

| Gate | Command |
| --- | --- |
| Format | `dart format --output=none --set-exit-if-changed .` |
| Analyze | `flutter analyze` |
| Tests | `flutter test --exclude-tags golden` |
| Goldens | `flutter test --tags golden` |
| Android build | `flutter build appbundle --release` |
| iOS build (macOS only) | `flutter build ipa --release --no-codesign` |

Goldens are stored per host OS (`test/goldens/<os>/`) because text rasterisation differs between
platforms; CI compares against `test/goldens/linux/`. To regenerate the Linux set on Windows, run
`flutter test --tags golden --update-goldens` inside a Linux container with Flutter 3.47.5
(see `docs/task-cards/MOB-003.md`). Review every changed image before committing it.

In widget tests liquid_glass_widgets cannot load its fragment shaders, so glass renders its
non-shader fallback in goldens; real glass is checked on device.
