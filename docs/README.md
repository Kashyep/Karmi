# Documentation index

Start with the [project README](../README.md). Nothing here has been moved; the "Audience" column
says whether a folder is meant for developers reading the project, or is owner and agent working
material kept for history.

## Developer docs

| Path | What it holds | Audience |
|---|---|---|
| [configuration.md](configuration.md) | Every `DAILY_AGENT_*` setting: default, production requirement, secrecy, meaning. | Developers, operators |
| [architecture.md](architecture.md) | Components, the `POST /v1/messages` flow, and where the blueprint differs from the code. | Developers |
| [install.md](install.md) | Installing the app on Android and iOS (experimental). | Testers |
| [blueprint/](blueprint/) | Product requirements (`PRD.md`), the original architecture proposal, rules, phases, tier entitlements, design and test specs. Planning documents: the code wins where they differ. | Developers, owner |
| [contracts/parakh/](contracts/parakh/) | Vendored JSON schemas for the Parakh telemetry batch and policy bundle, and their README. | Developers |
| [decisions/](decisions/) | Architecture decision records (initial channel, Flutter mobile client). | Developers |
| [runbooks/](runbooks/) | Step-by-step operating guides: local development, backend setup, database connections, scaling, backup and restore, admin dashboard, release signing, release and rollback, deployment. | Developers, operators |

## Owner and agent working notes

These are working records, not user documentation. They can be out of date.

| Path | What it holds | Audience |
|---|---|---|
| [release1/](release1/) | Release 1 scope, release notes, checklists, perf and device-run notes, admin web notes, backlog. | Owner, agents |
| [release-evidence/](release-evidence/) | Test and regression evidence, known issues, tester guide and notice, release notes for the beta. | Owner, agents |
| [reviews/](reviews/) | Audits and review reports. | Owner, agents |
| [task-cards/](task-cards/) | Task cards for mobile, web, model lab, API and capacity work. | Agents |
| [handoffs/](handoffs/) | Hand-off notes between work sessions. | Agents |
| [design/](design/) | Theme tokens, tier colour palettes, an implementation plan and icon and animation assets. | Owner, designers |
| `PROGRESS-2026-10-12.md`, `UI_IMPLEMENTATION_PLAN.md` | Dated progress log and UI plan. | Owner, agents |

`install.md` is added by a separate change; until it merges, that link does not resolve.
