# Core v1 requirement matrix

Status against the current local candidate, not against a deployed service.

| Requirement | Status | Evidence / gap |
|---|---|---|
| REQ-CH-001 | BLOCKED | ADR-0001; official terms rechecked; WhatsApp disabled |
| REQ-ID-001 | VERIFIED LOCALLY | signed server session and cross-account note tests |
| REQ-ID-002 | PARTIAL | role dependency exists; no production OIDC/admin console |
| REQ-PLAN-001 | VERIFIED LOCALLY | server-owned subscription and order-aware sandbox events |
| REQ-PLAN-002 | PARTIAL | synthetic context/output/usage/money fields; rate/concurrency policy incomplete |
| REQ-COST-001 | IMPLEMENTED / INTEGRATION BLOCKED | atomic conditional updates; PostgreSQL concurrency gate awaits Docker engine |
| REQ-COST-002 | PARTIAL | unknown cost preserved/reserved conservatively; full provider units absent |
| REQ-CTX-001 | PARTIAL | tenant-filtered note context and manifest; no vector/files/selected tokenizer |
| REQ-CTX-002 | PARTIAL | note soft deletion blocks current retrieval; derived-index pipeline absent |
| REQ-ROUTE-001 | PARTIAL | deterministic fake route only; no evaluated live model pool |
| REQ-ROUTE-002 | VERIFIED LOCALLY | bounded oversize and allowance outcomes |
| REQ-EXEC-001 | PARTIAL | request spend/input caps; no worker deadline/cancellation engine |
| REQ-EXEC-002 | PARTIAL | typed local CRUD and tenant checks; broader tool registry absent |
| REQ-EVAL-001 | PARTIAL | terminal outcome contract; repair/escalation engine incomplete |
| REQ-ACT-001 | PARTIAL | notes/tasks/reminder create/completion/idempotency; full edit/list CRUD incomplete |
| REQ-ACT-002 | MISSING | remote-action reconciliation worker not implemented |
| REQ-CH-002 | PARTIAL | signed/deduplicated internal inbox; queue/crash/delivery adapter incomplete |
| REQ-BILL-001 | VERIFIED LOCALLY (SANDBOX CONTRACT) | signed duplicate/stale billing fixture tests; no provider checkout |
| REQ-ADMIN-001 | MISSING | admin console/investigation/audit UI absent |
| REQ-LAB-001 | PARTIAL | 60-case validation/candidate export/import/basic grading; live comparison absent |
| REQ-LAB-002 | PARTIAL | provenance/null/escaping covered; broader mappings/reports pending LAB-002 |
| REQ-OPS-001 | PARTIAL | fail-closed settings/runbooks; queue/outage recovery incomplete |
| REQ-PRIV-001 | PARTIAL | scoped retrieval/secret scan; encryption/retention/backup live evidence absent |
| REQ-UX-001 | IMPLEMENTED / MANUAL PENDING | accessible static shell and truthful placeholders; authenticated wiring incomplete |

Core v1 is not release-ready. Phases 0 and the local foundations of 1–3/6 are implemented; phases
4–8 remain partial or missing. No full-roadmap completion is claimed.

