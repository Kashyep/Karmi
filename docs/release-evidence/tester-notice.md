# Tester notice (in-app, shown on first launch, versioned)

**LEGAL REVIEW REQUIRED before any tester sees this.** Many students are under 18. India's Digital
Personal Data Protection Act, 2023 requires verifiable parental consent for processing children's
personal data and restricts tracking/targeted advertising to children. The current text is a
placeholder, not a consent mechanism. Review must also cover: sending prompts to third-party model
providers (OpenRouter and the upstream hosts of free models, some of which may retain or train on
prompts), storage and retention of messages and feedback, deletion requests, grievance contact, and
whether minors may be testers at all.

Text in the app (`mobile/lib/features/welcome/tester_notice.dart`, version 1):

> This is a test build. AI replies may be wrong. Messages may be stored and used to evaluate and
> improve models. Do not enter sensitive personal information. Data handling is pending legal review.

Behaviour: the user must acknowledge it before the app is usable; bumping `kTesterNoticeVersion`
re-prompts. Recommended invitation rule until legal review is done: adult testers only.
