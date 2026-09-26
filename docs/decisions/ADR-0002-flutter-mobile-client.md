# ADR 0002: Flutter Mobile Client

Date: 2026-09-26
Status: Accepted

## Context

Karmi requires a customer UI that ships natively on Android and iOS. The existing channel is a web/PWA shell serving a synthetic backend, which cannot support the required mobile experience and offline requirements natively on devices. The decision was made to build a new native mobile application. 

## Decision

We will implement the native application using **Flutter (Dart)** for both Android and iOS platforms. 
None of the React/web based libraries previously proposed (e.g., `loading-dev`, `beui`, etc.) can be used on Flutter. We will instead build native equivalents with `liquid_glass_widgets` for glass effects, `google_fonts`, and other native Flutter ecosystem libraries.

### Q1-Q9 Resolutions

- **Location (Q1)**: The mobile application will reside in the `mobile/` directory within this repository. The application ID will be `ai.karmi.app`.
- **Glass / Perf Limits (Q2)**: Given the absence of CONTEXT.md and KARMI_THEME files, the implementation will proceed with the proposed minimum limits from the plan (e.g. glass tint alpha >= 0.72 light / 0.78 dark; TTFF <= 2.0s; input-to-frame <= 100ms). These will be adjusted if updated context files are provided.
- **Production Auth (Q3)**: For V1 development, we will mock auth with `/dev/token`. Production auth integration is deferred.
- **Missing APIs (Q4)**: Chat history, task list, and missing payloads will be implemented via separate backend task cards following the repository's `CLAUDE.md` rules.
- **Hindi Support (Q5)**: We will bundle `Noto Sans Devanagari` and `Noto Serif Devanagari` to satisfy the Hindi language requirements out-of-the-box.
- **Palette Supersession (Q6)**: The mobile app will strictly use the new green-based palette (Primary: `#2c6d34`, Accent: `#42a980`) and designated fonts (Exo, Proza Libre, Trykker), completely superseding the blue `#254EDB` tokens in `Design.md`. White text will strictly avoid being overlaid on accent colors.
- **iOS Build Infrastructure (Q7)**: Given the Windows environment, local iOS compilation cannot be performed. We will rely on GitHub-hosted macOS runners (`macos-latest`) for CI and release iOS builds.
- **Reference Low-end Device (Q8)**: Minimum supported levels are API 21 for Android and iOS 14.
- **Web/PWA (Q9)**: The existing web shell will be kept in parallel as a testing surface and alternative access route.

## Consequences

- The project becomes a monorepo containing a Python backend and a Dart/Flutter frontend.
- Requires Flutter toolchain setup on developer machines.
- A new CI job will be needed for Dart/Flutter tests and build verification. 
