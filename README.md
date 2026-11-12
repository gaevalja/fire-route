# FireRoute

**FireRoute: Intelligent Fire Evacuation and Rescue Guidance System**

A simulation-based PoC for the 2026 oneM2M × ETSI MEC international hackathon. GitHub repository and checkout directory: **fire-route**. Repository: [gaevalja/fire-route](https://github.com/gaevalja/fire-route).

> Current state: actual T05, P1_ROUTES, P1_GROUP and P1_DASHBOARD passed on ACME 2026.5.1 / Python 3.12.16. The local loop includes authenticated role APIs, synthetic occupants, CSE notifications → computed routes → Group/fopt → independent simulated display ACKs. Browser rendering has not been checked. MEC, full recovery, authenticated CSE transport and shutdown diagnosis remain open. See [STATUS](docs/STATUS.md) for the exact tested revision and subsequent changes.

> Scenario update (2026-11-12): the user selected **fire_evac: floors 1–10 plus roof, 162 zones**, then requested both fixed guidance and moving residents. Original source is unchanged. A new assumed-geometry model, CSE/core runner and separate ten-floor role dashboard are implemented; selected core/HTTP baseline gates have passed while full hazard/fault and browser verification remain open. Earlier PASS evidence above belongs to the three-floor regression. See [scenario](docs/SCENARIO.md) and [evacuation model](docs/EVACUATION_MODEL.md).

> Execution update: the selected core and HTTP baseline gates have now passed in the user's actual CSE environment. A manual run through simulated second 208 was separately audited; full selected hazard/fault coverage, comprehensive browser QA and MEC remain open. [STATUS](docs/STATUS.md) records the exact run IDs and scope.

Run `make test-scenario` to execute the original engine tests. Opening `simulator/scenarios/fire_evac/index.html` runs its standalone scenario maker, with no CSE/MEC integration. Fire/smoke/collapse rules stay as supplied; the added movement/entrance assumptions are defined separately in EVACUATION_MODEL.md.

## Selected scenario: two modes

~~~bash
# Original source -> bounded trace -> offline fixed and moving model (no CSE).
make scenario-preview

# Actual CSE/frame/SUB/fixed decision/moving records/Group/ACK gate.
make p1-scenario

# Actual authenticated HTTP/CSE gate for the ten-floor dashboard.
make p1-scenario-dashboard

# Persistent ten-floor dashboard; open http://127.0.0.1:3001.
make demo-scenario-up
~~~

Node 24.22.1 is the observed/tested host tool version, recorded in .node-version; it exports source traces using built-in modules. Python containers need no Node/npm package. Default seed=2026/wind=5, core replay length=180 seconds; live export defaults to 1800 seconds. Override SCENARIO_SEED, SCENARIO_WIND or SCENARIO_SECONDS explicitly before generation. Run integration profiles one at a time; make down preserves evidence/CSE volumes.

The selected HTTP gate recreates its containers and explicitly resets to a new paused incident before checking simulated second zero. It records before-reset-status.json, initial-status.json and assertions even on failure. This stops a previously used/expired demo from becoming the test baseline. make demo-scenario-up also recreates its containers so the atomically replaced trace file is mounted afresh; expect a new incident, not continuation of an earlier run. Existing CSE volumes and evidence remain. These commands interrupt the selected local demo; run them serially.

Log in using the role code from ignored .runtime/access-codes.json. Responder can switch **고정 위치 안내 / 가상 주민 이동**, choose floors and a synthetic resident, and advance/pause/reset. Resident sees approved fixed-origin guidance only. Defaults are **F7-R3, 170 synthetic residents**, with speed/departure variability and finite link capacity. All lengths/capacities/thresholds are assumptions in fixtures/evacuation_assumptions.json, not measured geometry or validated evacuation predictions. The source fire engine is unchanged. Paused/expired observations remove directions and individual positions. The selected core/HTTP baseline gates have passed in the user environment; full hazard/fault coverage and browser QA remain separate.

Paused resident selection: live guidance still expires after 30 seconds, but the responder can inspect the latest saved people snapshot with an explicit **저장 기록 보기** timestamp. Its blue points/counts are recorded values, not current positions. Current-version matching CSE CINs are read without advancing time; unchanged option lists survive polling/PENDING. The new snapshot endpoint is responder-only. Apply source updates with make demo-scenario-up, then refresh/login; this restarts the app into a new incident while retaining earlier CSE/evidence records. The extended actual HTTP/CSE gate passed 18 checks on 2026-11-12, including protected historical retrieval after live expiry. Browser resident selection across polls/pause/reload still needs manual checking; see STATUS.md for exact evidence.

## Run the P0 foundation

The protocol core has no third-party runtime dependencies. Product runtime: Python >=3.11; local container target: Python 3.12. Read [P0 scope and limitations](docs/IMPLEMENTATION_P0.md).

~~~bash
# Offline protocol/contract tests; unit transport fixtures are explicitly simulated.
make test-unit

# Actual ACME CSE + actual SUB verification/CIN notification in isolated local Docker.
make p0-smoke

# Actual P1 notification -> computed hazard/route CINs (verified local slice).
make p1-routes

# Actual Group/fopt + three display processes/ACKs (verified local backend slice).
make p1-group

# Stop project containers; keep CSE data and recorded evidence.
make down
~~~

make p0-smoke builds the upstream acmecse==2026.5.1 package, starts a local IN-CSE, creates namespaced AEs/CNTs and verifies T05. It never selects a fake CSE or a MEC mock. A successful run prints state=PASS and stores actual meta/requests/notifications/assertions/summary/tests under evidence/<UTC-run-id>/. A blocked/failed run exits nonzero and retains its reason; no success is pre-scripted. First-time image/package downloads require working network and Docker access. The user's 2026-11-11 run passed; original artifacts and audit are indexed in STATUS. A fresh-clone/CI reproduction remains pending.

The Docker CSE is exposed on 127.0.0.1:8080 only; the callback receiver is internal to its Compose network. Set CSE_HOST_PORT if the host port is occupied. Do not run simultaneous smoke jobs against one Compose project. Data volumes are preserved; resource names have unique run prefixes and expiration.

The CSE launcher stages the bundled config as an owned content-hashed file in /data and passes only a filename to ACME's --config option. Existing data/config files are retained. After a launcher/config update, rerun make p0-smoke to rebuild the changed layer. The initial filename startup bug was fixed and the actual rerun passed. The smoke command stops its containers after p0 exits; use make up-core to keep only the CSE running. The observed post-test CSE exit 137 is tracked separately from T05 and still needs shutdown diagnosis. See [status and diagnosis](docs/STATUS.md).

make p1-routes runs a separate owned namespace against the same real CSE. It verifies actual temperature/smoke CINs and SUB notifications, computes EXIT_A → EXIT_B → NO_VERIFIED_ROUTE, and checks the three hazard/route pairs by actual read-back. It checks controller duplicate processing, an actual outdated sensor event, sensor route-write denial, resident hazard-read denial and permitted route reads. Its PASS is only P1_ROUTES, with Group/ACK/UI/MEC explicitly unfinished. Incident/outbox recovery and ambiguous CREATE reconciliation have offline tests; actual restart/fault recovery remains unverified. With an existing reachable CSE/Python >=3.11, use make test-routes instead.

make p1-group adds a real GRP of three commands containers and spawns three independent Python display processes inside the runner container. Each uses its own actual AE-ID, command SUB, durable state and ACK CIN writer; the controller consumes ACK SUBs and reads back the corresponding actual CINs. It checks A/B/no-route application, then stops display-c and requires INCOMPLETE delivery with two ACKs. Group success alone never implies device success. Ports 8000–8003 are private within the Compose network; no additional host ports are published. The 2026-11-11 actual run passed with 12 command CINs, 11 ACK CINs, three complete deliveries, one expected incomplete delivery and six ACP denials; the separate artifact audit passed 50 checks. Local Group members use actual CSE-relative container IDs, matching ACME's observed canonical mid representation. Originator authentication/TLS and full service resume remain separate gaps. Use make test-group for a configured existing CSE.

To use an existing actual CSE with Python >=3.11: copy .env.example to an ignored .env only if absent, configure the actual CSE base/release/identity and a callback URL reachable from that CSE, then run make test-cse. A container CSE cannot notify a host receiver through its own 127.0.0.1. For the bundled CSE Dockerfile's process-based alternative, install acmecse==2026.5.1 in a separate environment and use infra/cse/acme.ini with host/listen/data settings adapted to your machine; the process path is not execution-verified in this sandbox.

These profiles use HTTP and header-based identities on an isolated local network. They are not the authenticated HTTPS/MQTTS security submission profile. The standalone IN-CSE is not Option C and does not prove MN-to-IN registration. p0-smoke is the verified primitive loop; p1-routes is the verified route slice; p1-group is the verified isolated Group/device slice. No profile calls a MEC service. The graph module under mec/risk/ is custom local application logic; its directory name is not a MEC deployment claim.

Python's standard unittest runner is used in P0; pytest can run these tests later but is not a required installed dependency. Host Python 3.10 is used only for portable offline unit checks here, not as the supported product environment. The agent sandbox denies sockets/Docker access; successful unit checks do not imply T05 PASS.

CI is configured for Python 3.11/3.12 units, Node frontend-state tests and actual local ACME gates. This workflow is source configuration until it is run on GitHub; no CI badge/pass is claimed.

## Run the local dashboard

~~~bash
# Offline frontend state checks; Node is needed only for this test command.
make test-frontend

# Actual HTTP sessions/role filtering + actual CSE scenarios; stops after the gate.
make p1-dashboard

# Keep the real CSE and dashboard running for manual browser verification.
make demo-up
~~~

Open **http://127.0.0.1:3000**. The dashboard is served directly by Python; no npm install or frontend build is needed. Open the ignored `.runtime/access-codes.json` privately in your editor and use the code for the selected role. Separate generated resident/responder codes are never printed by the setup command. Keep that file private; do not paste codes into issues, logs or screenshots. Login creates an expiring HttpOnly role-bound session. Two roles can be checked in separate browser profiles/private windows because a browser profile shares its session cookie.

The resident view reads approved route/status only. The responder view adds synthetic sensors, hazards, three display ACK states and synthetic occupants (2 or UNKNOWN, never inferred real people). Responder controls generate actual CSE events for fire at F2_A/F2_B, stopping display-c, pausing/resuming input and resetting to a new simulation. Reset creates a new incident/owned namespace and retains CSE data. Five-second synthetic temperature observations retain earlier hazard blocks; pause lets guidance/occupants expire after the configured 30-second TTL. Missing CSE data clears directions instead of serving cached routes as fresh.

The 2026-11-12 actual gate passed 17 checks, including EXIT_A → EXIT_B → no-route, missing ACK, backend role denial, actual CSE resident occupant denial, stale guidance/counts and a new-incident reset. The latest rerun also records each role response and confirms expired ACK labels. This verifies HTTP/CSE behavior; browser layout, accessibility and browser interaction still need manual verification. See [role API](docs/ROLE_API.md) and [verification record](docs/STATUS.md).

Only 127.0.0.1:3000 is published; the accepted origin uses that exact hostname/port. Set APP_HOST_PORT for a different local port. `.runtime/auth.json` contains hashes and is the only auth file mounted into the app; private plaintext access codes are mounted only into the test runner. `make demo-logs` shows bounded application logs; `make down` stops all profiles while preserving data. This is a local HTTP PoC; CSE header identities/default secret and missing TLS prevent claiming production or shared-server security. The next start creates a new simulation rather than resuming an old incident automatically.

## Verified regression demonstration

The following describes the existing three-floor checkpoint. The selected final scenario and its remaining integration work are defined in SCENARIO.md.

Synthetic temperature/smoke/fire-related sensor observations enter an actual oneM2M CSE. An edge risk application computes a route through a synthetic three-floor graph. Blocking F2_A changes the selected exit from A to B. The controller stores the versioned decision and creates one display command through a real GRP/fopt targeting three command containers. Three independent display consumers apply it and create separate ACKs. Resident and responder applications agree on the incident/version; responder-only diagnostics include synthetic remaining-occupant information.

FireRoute does not certify fire detection accuracy, infer real occupant positions, or guarantee a safe evacuation route. Missing observations and unavailable routes are explicit states.

## Target deployment

The first MEC target is **Option C: MN-CSE deployed as a MEC App on a Local ETSI MEC Sandbox host**, with a separately identified Cloud IN-CSE registrar relationship. MEC-IPE maps supported MEC functions/data to actual oneM2M resources. Local Sandbox deployment is preferred over the reference [Hosted Sandbox](https://82.112.253.59/), whose environment modification is restricted according to the user-provided organizer notice.

This is a deployment plan. TR-0086 revision details, repository access, actual Sandbox services, lifecycle support, and runtime behavior must be verified. Merely running CSE and backend containers together is not proof of Option C. See [architecture](docs/ARCHITECTURE.md), [deployment](docs/DEPLOYMENT.md), and [source provenance](docs/SOURCES.md).

## Development and team structure

Each developer works on a personal clone and feature/* branch; main receives reviewed PRs. A shared x86 Ubuntu server runs integration/demo services from a deployment-owned checkout. Raspberry Pi is an optional IoT/Edge node, with model and hardware still undecided. Developers do not concurrently edit a shared server directory.

| Path | Responsibility | Current contents |
|---|---|---|
| backend/ | API, incident state, event orchestration | Durable notifications/incidents, Group orchestration, local sessions and actual-CSE role views |
| frontend/ | Resident/responder dashboards | Buildless HTML/CSS/JS and SVG schematic; browser QA pending |
| simulator/ | Synthetic sensors, displays, scenarios | Typed sensors/occupants, independent display application/ACKs and scenarios |
| onem2m/ | CSE adapter, registration, SUB, Group, ACP | Verified local HTTP/bootstrap/decisions/Group/fopt/scoped ACPs; MQTT/full authentication pending |
| mec/ | Edge risk logic and future MEC/IPE integration | Pure graph/synthetic policy with unit tests; no MEC API/deployment |
| infra/ | Local/shared deployment configuration | Local CSE/core Dockerfiles and isolated Compose; MEC/shared deployment pending |
| tests/ | Unit, CSE, MEC, fault and E2E tests | Python/Node units; actual T05/routes/Group/role-API gates; MEC/fault expansion pending |
| fixtures/ | Synthetic graph | Existing JSON preserved |
| docs/ | Requirements, contracts, workflow and evidence rules | Revised specifications |
| evidence/ | Sanitized executed-run evidence | Ignored local run output; actual CSE PASS requires its own trace |
| references/ | Reference index and permitted source files | Index only; external rubric inspected in place |

The application uses Python's standard library and buildless HTML/CSS/JavaScript (ADR-013); no third-party application runtime dependency was added. Docker Compose supplies the actual ACME CSE, pinned to package 2026.5.1; its installed dependency list is captured by the CSE entrypoint. The Python image uses the 3.12-slim-bookworm family; resolve its immutable digest/transitive lock before claiming fully locked deployment. FastAPI/Vue were initial proposals. Local alternatives and configuration are in [ENVIRONMENT](docs/ENVIRONMENT.md).

## Specifications

Read [AGENTS](AGENTS.md), then the following documents before implementation:

| Document | Purpose |
|---|---|
| [P0 implementation](docs/IMPLEMENTATION_P0.md) | Current implementation slice, gates and limitations |
| [PRD](docs/PRD.md) | Functional requirements and scope |
| [SCENARIO](docs/SCENARIO.md) | User-selected ten-floor engine, preserved source, missing movement rules and integration gates |
| [EVACUATION_MODEL](docs/EVACUATION_MODEL.md) | Fixed/moving model, explicit assumptions, clocks, queues, population conservation and commands |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Option C, resources, module and event contracts |
| [ROLE_API](docs/ROLE_API.md) | Local sessions, role endpoints, CSE snapshots and stale behavior |
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

Keep real .env, passwords, API tokens and SSH keys out of Git. Use per-user SSH keys and private VPN access. Raw evidence is ignored by default; select only sanitized artifacts for publication. The organizer describes Apache-2.0 for code and CC BY 4.0 for non-code outputs; the source Apache-2.0 LICENSE is present; documentation licensing and third-party publication notices remain P4 work. See [organizer publication notice](https://estimed.etsi.org/news/estimed_hackathon2/).
