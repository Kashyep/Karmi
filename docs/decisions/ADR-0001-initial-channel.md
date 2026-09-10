# ADR-0001 — Owned web/PWA is the initial release channel

Status: accepted for the local release candidate • 2026-09-10

## Context

The provisional pilot is India-first. The official WhatsApp Business Solution Terms were
rechecked on 2026-09-10 and remain last modified 2026-03-06. Section “AI Providers” prohibits
general-purpose AI as the primary functionality, with an exception for users registered with EEA
or Brazil country codes. A BSP does not remove this restriction.

## Decision

The owned web/PWA is promoted from v1.1 to the initial customer channel. The backend keeps a
channel adapter boundary, but `DAILY_AGENT_WHATSAPP_ENABLED` is rejected by configuration for this
release. The internal signed-event adapter remains available for local durability tests.

## Consequences

- No WhatsApp launch, real message or reminder delivery is claimed.
- A future eligibility decision must cite current official terms, intended users/country codes,
  consent, templates/session rules and provider approval before code can enable the adapter.
- The shared identity, entitlement, context and action backend can continue independently.

Source: <https://www.whatsapp.com/legal/business-solution-terms>

