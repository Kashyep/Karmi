# Karmi: UI/UX Engineering & Implementation Plan

This document outlines the technical execution strategy for integrating the four-tier thematic architecture (Ananta, Yanta, Trika, Parth) and the liquid glass design system into the Karmi frontend. 

## 1. Environment & Asset Baseline

### 1.1 Development Environment
*   **Editor & OS:** Initialize the frontend workspace in Zed under the local Linux development environment. 
*   **Framework Selection:** Utilize a modern framework (e.g., React/Next.js or Vue/Nuxt) with Tailwind CSS for rapid semantic styling and token management.
*   **Asset Processing:** Import the raw text-to-image outputs from Google Flow. Process these graphics to standardize dimensions (1024x1024 baseline), remove generation artifacts, and export as SVG/WebP for optimized web delivery and PNG for mobile application manifests.

### 1.2 CSS Tokenization
Establish a strict design token system to separate semantic UI components from hardcoded hex values. This is critical for the `O(1)` complexity theme switching required by the Armory system.

*   `--color-canvas`: The underlying background (e.g., Obsidian for Parth Dark, Ice White for Yanta Light).
*   `--color-glass-base`: The rgba base for frosted panels.
*   `--color-accent-primary`: The active state color (e.g., Bright Mint Green, Electric Cyan).
*   `--color-text-main`: Context-aware typography color.

### 1.3 Liquid Glass Standardization
Define a universal glassmorphism utility class that applies consistently regardless of the active tier.
*   **CSS Class (`.glass-panel`):** `backdrop-filter: blur(16px); background-color: var(--color-glass-base); border: 1px solid rgba(255, 255, 255, 0.1);`
*   **Fallback:** Implement a `@supports not (backdrop-filter: blur(16px))` media query to provide a solid fallback color for browsers or Linux window managers running without hardware acceleration.

---

## 2. Core Architecture & Theming Logic

### 2.1 Dual-Axis Theme Provider
The application state must manage two independent thematic axes: **Mode** (Light/Dark) and **Tier** (Ananta/Yanta/Trika/Parth). 
*   Implement a global context provider (`ThemeContext`) that reads the system `prefers-color-scheme` on first load.
*   Apply the active tier as a data attribute on the root HTML element (e.g., `<html data-tier="yanta" data-theme="dark">`), allowing CSS variables to cascade globally.

### 2.2 Component Decoupling
Ensure that UI components housing triggers for the Karmi WhatsApp agent are entirely decoupled from thematic styling. A button executing a third-party service payload or a location-sharing command must function identically whether rendered in the Ananta or Parth theme.

---

## 3. The Armory: Progression & Gamification System

### 3.1 State Management & Authorization
*   Store user progression in the database with two distinct integer fields: `unlocked_tier` (1-4) and `active_theme` (1-4).
*   **Downward Compatibility Logic:** The application must enforce `active_theme <= unlocked_tier`. If a user's subscription downgrades, a server-side check must reset `active_theme` to match the new `unlocked_tier` if it currently exceeds it.

### 3.2 The Armory Gallery Interface
*   Build a dedicated settings route (`/armory` or `/themes`).
*   Map through a configuration object containing all four tiers. 
*   **Locked State Rendering:** If `theme.id > user.unlocked_tier`, apply a heavy CSS blur filter (`filter: blur(4px) grayscale(80%)`), disable click events for activation, and overlay a padlock icon. 
*   **Preview Mode:** Allow users to temporarily apply a locked theme to their local DOM for 10 seconds before a `setTimeout` function reverts it, serving as a highly effective upsell mechanism.

### 3.3 Dynamic App Icon Switching
*   **PWA:** Update the `manifest.json` dynamically or prompt users to reinstall the PWA to update the home screen shortcut.
*   **Native Wrappers (React Native/Flutter):** Implement native bridges (`setAlternateIconName` for iOS, programmatically enabling `<activity-alias>` in the `AndroidManifest.xml` for Android) to swap the device home screen icon upon theme selection.

---

## 4. Testing & Validation Pipeline

### 4.1 Integration with Niriksh
Leverage the Niriksh testing framework to validate the thematic logic alongside the core task agent functionalities.
*   **Auth Tests:** Write automated tests ensuring user tier upgrades correctly mutate the `unlocked_tier` state and grant access to the corresponding color variables.
*   **Reversion Tests:** Simulate a tier downgrade and verify that Niriksh flags any failure of the system to revert the user to the appropriate baseline theme.

### 4.2 Visual Regression & Contrast Auditing
*   Execute accessibility (a11y) audits on all 8 combinations (4 Tiers × 2 Modes). 
*   Specifically target the Trika (Amber/Charcoal) and Parth (Gold/Obsidian) themes to ensure typography contrast ratios meet WCAG AA standards, adjusting the `--color-text-main` tokens if the liquid glass panels cause text bleeding.

---

## 5. Deployment Sprint Schedule

| Phase | Milestone | Technical Focus |
| :--- | :--- | :--- |
| **Sprint 1** | Assets & Variables | Process Google Flow icons; set up Tailwind/CSS token architecture; finalize `.glass-panel` utilities. |
| **Sprint 2** | Context & Architecture | Build `ThemeContext` provider; implement root HTML data attribute toggling; ensure basic layout inherits styles. |
| **Sprint 3** | The Armory & App Icons | Construct gallery UI; build 10-second preview logic; implement native/PWA icon switching scripts. |
| **Sprint 4** | Integration & Niriksh | Bind UI triggers to the WhatsApp agent backend; write state reversion tests; conduct final WCAG contrast audits. |