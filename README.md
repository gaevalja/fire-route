# FireRoute

**FireRoute: Intelligent Fire Evacuation and Rescue Guidance System**

A simulation-based PoC for the 2026 oneM2M × ETSI MEC international hackathon. GitHub repository and checkout directory: **fire-route**. The GitHub owner/remote URL is not yet configured.

> Current state: specifications and a synthetic building fixture only. No service implementation or real CSE/MEC integration has passed acceptance tests. See [STATUS](docs/STATUS.md).

## Demonstration goal

Synthetic temperature/smoke/fire-related sensor observations enter an actual oneM2M CSE. An edge risk application computes a route through a synthetic three-floor graph. Blocking F2_A changes the selected exit from A to B. The controller stores the versioned decision and creates one display command through a real GRP/fopt targeting three command containers. Three independent display consumers apply it and create separate ACKs. Resident and responder applications agree on the incident/version; responder-only diagnostics include synthetic remaining-occupant information.

FireRoute does not certify fire detection accuracy, infer real occupant positions, or guarantee a safe evacuation route. Missing observations and unavailable routes are explicit states.

## Target deployment

The first MEC target is **Option C: MN-CSE deployed as a MEC App on a Local ETSI MEC Sandbox host**, with a separately identified Cloud IN-CSE registrar relationship. MEC-IPE maps supported MEC functions/data to actual oneM2M resources. Local Sandbox deployment is preferred over the reference [Hosted Sandbox](https://82.112.253.59/), whose environment modification is restricted according to the user-provided organizer notice.

This is a deployment plan. TR-0086 revision details, repository access, actual Sandbox services, lifecycle support, and runtime behavior must be verified. Merely running CSE and backend containers together is not proof of Option C. See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), and [source provenance](docs/SOURCES.md).

## Development and team structure

Each developer works on a personal clone and feature/* branch; main receives reviewed PRs. A shared x86 Ubuntu server runs integration/demo services from a deployment-owned checkout. Raspberry Pi is an optional IoT/Edge node, with model and hardware still undecided. Developers do not concurrently edit a shared server directory.

| Path | Responsibility | Current contents |
|---|---|---|
| backend/ | API, incident state, event orchestration | Placeholder |
| frontend/ | Resident/responder dashboards | Placeholder |
| simulator/ | Synthetic sensors, displays, scenarios | Placeholder |
| onem2m/ | CSE adapter, registration, SUB, Group, ACP | Planned; directory not created |
| mec/ | MEC app/IPE integration | Planned; directory not created |
| infra/ | Local/shared deployment configuration | Planned; directory not created |
| tests/ | Unit, CSE, MEC, fault and E2E tests | Planned; directory not created |
| fixtures/ | Synthetic graph | Existing JSON preserved |
| docs/ | Requirements, contracts, workflow and evidence rules | Revised specifications |
| evidence/ | Sanitized executed-run evidence | Placeholder; no product run evidence |
| references/ | Reference index and permitted source files | Index only; external rubric inspected in place |

Proposed stack: Python 3.12, FastAPI, pytest, Vue 3, TypeScript, Vite, and Docker Compose. Exact versions are selected and locked during P0. No setup/start/test commands are advertised as executable until their files exist. Local alternatives and configuration inventory are in [ENVIRONMENT](docs/ENVIRONMENT.md).

## Specifications

Read [AGENTS](AGENTS.md), then the following documents before implementation:

| Document | Purpose |
|---|---|
| [PRD](docs/PRD.md) | Functional requirements and scope |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Option C, resources, module and event contracts |
| [DEPLOYMENT](docs/DEPLOYMENT.md) | Local Sandbox/CSE plan, registration and fallback gates |
| [ENVIRONMENT](docs/ENVIRONMENT.md) | Personal PC, shared server, Raspberry Pi and configuration |
| [TEAM_WORKFLOW](docs/TEAM_WORKFLOW.md) | Branches, ownership, PRs and integration |
| [TEST_PLAN](docs/TEST_PLAN.md) | Acceptance criteria and measurement method |
| [RUBRIC](docs/RUBRIC.md) | All 17 rows, Expert source and evidence gaps |
| [ROADMAP](docs/ROADMAP.md) | P0–P4, dependencies and deadline |
| [DEMO](docs/DEMO.md) | Proposed demonstration and submission checklist |
| [DECISIONS](docs/DECISIONS.md) | Decisions and unresolved technical questions |
| [STATUS](docs/STATUS.md) | Single implementation/test progress record |
| [SOURCES](docs/SOURCES.md) | Inspected references, versions and access limits |

[CODEX_FIRST_PROMPT](CODEX_FIRST_PROMPT.md) is a bounded implementation-task template, not an instruction to rebuild the project.

## Schedule and publication

All functioning software, GitHub material, article, video, and presentation files must be complete by **2026-11-20**. Interviews/presentations: November 23–25; team selection: November 26; ceremony: November 27. November 26 is user-confirmed; the public schedule independently confirms the development end, presentation period and ceremony. Exact submission cutoff/timezone and required formats remain to be checked. See [ROADMAP](docs/ROADMAP.md) and [official schedule](https://onem2m-hackathon.io/schedule.asp).

Keep real .env, passwords, API tokens and SSH keys out of Git. Use per-user SSH keys and private VPN access. Raw evidence is ignored by default; select only sanitized artifacts for publication. The organizer describes Apache-2.0 for code and CC BY 4.0 for non-code outputs; license files and third-party notices remain P4 deliverables, not completed work. See [organizer publication notice](https://estimed.etsi.org/news/estimed_hackathon2/).
