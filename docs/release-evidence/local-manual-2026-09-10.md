# Local manual evidence — 2026-09-10

Environment: Windows native checkout, Python 3.14.3, local SQLite development database, no live
provider/payment/channel credentials. All content was synthetic.

| Check | Expected | Observed | Status |
|---|---|---|---|
| Start server | Uvicorn starts and root loads | Startup completed at `127.0.0.1:8000`; root returned 200 | PASS |
| Owned-channel content | Meaningful page with accessible navigation and four plans | Browser accessibility tree exposed skip link, primary nav, labelled composer, Ananta/Yanta/Trika/Part, privacy copy and usage placeholders | PASS |
| Synthetic sign-in/usage | Dev-only identity resolves server-side and usage appears | `/dev/token` and `/v1/usage` returned 200; shell displayed Ananta synthetic policy, `0 of 20`, exact reset timestamp | PASS |
| Draft journey | Request reaches backend and final state is distinguishable | Entered “Write a concise hello for a project update”; UI changed to `Task status: Completed` and displayed the bounded response; `/v1/messages` returned 200 | PASS |
| Visual desktop | No blank/error overlay; critical controls readable | Screenshot showed nav, heading, labelled composer and start button at desktop viewport | PASS |
| 360/768/1440, 200% zoom, keyboard-only | Critical controls remain available | CSS/structure assertions pass, but exact interactive viewports were unavailable in the fallback browser API | NOT RUN |
| Browser console | No runtime console errors | Prescribed `agent-browser` CLI was absent and fallback API did not expose console logs; HTTP path was successful | NOT RUN |
| PostgreSQL/Redis concurrency | Disposable services start and atomic test passes | Docker CLI exists, but Docker Desktop engine did not become ready within 55 seconds | BLOCKED |
| Actual WhatsApp/payment/provider | Live permitted integration succeeds | No eligibility/credentials/authorization; no call attempted | BLOCKED |

Cleanup: test browser closed and Uvicorn stopped cleanly. The synthetic development SQLite file is
ignored by Git. No external message, charge, provider call, deployment or production mutation occurred.
