# FireRoute

**FireRoute: Intelligent Fire Evacuation and Rescue Guidance System**

A simulation-based PoC for the 2026 oneM2M × ETSI MEC international hackathon. GitHub repository and checkout directory: **fire-route**. Repository: [gaevalja/fire-route](https://github.com/gaevalja/fire-route).

> Current state: actual T05, P1_ROUTES, P1_GROUP and P1_DASHBOARD passed on ACME 2026.5.1 / Python 3.12.16. The local loop includes authenticated role APIs, synthetic occupants, CSE notifications → computed routes → Group/fopt → independent simulated display ACKs. Browser rendering has not been checked. Controlled local CSE shutdown/persistence now passes; MEC, full application recovery and authenticated CSE transport remain open. See [STATUS](docs/STATUS.md) for the exact tested revision and subsequent changes.

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

# Natural hazards, actual Group/ACKs, then a stopped-device INCOMPLETE case.
make p1-hazards

# Persistent ten-floor dashboard; open http://127.0.0.1:3001.
make demo-scenario-up
~~~

Node 24.22.1 is the observed/tested host tool version, recorded in .node-version; it exports source traces using built-in modules. Python containers need no Node/npm package. Default seed=2026/wind=5, core replay length=180 seconds; live export defaults to 1800 seconds. Override SCENARIO_SEED, SCENARIO_WIND or SCENARIO_SECONDS explicitly before generation. Run integration profiles one at a time; make down preserves evidence/CSE volumes.

The hazard gate uses its own ignored .runtime/fire-evac-hazards.jsonl, separate from the interactive trace. Defaults are HAZARD_SEED=59, HAZARD_WIND=5 and HAZARD_SECONDS=900, with the original engine/configuration unchanged. make hazard-preview verifies the model offline and explicitly reports CSE/Group/ACKs=NOT_RUN. Observed model stages are baseline at 0, an alternative avoiding blocked F4-SA at 466, collapse at 600 and no route from the still-unblocked fixed origin at 727 simulated seconds. The alternate path can reach the same EXIT_A; an exit-name change alone is not the hazard test. Under these assumptions all 170 residents have already reached exits by the later queries, so this run does not demonstrate rescuing trapped people or a collapse-only route change.

make p1-hazards is the separate actual-CSE gate: every source second must have a real CIN read-back and matching durable SUB notification before model acceptance. Each observed stage requires three Group member CINs and independent ACK/device states. It then stops display-c and checks the next source frame produces three member writes but two ACKs/INCOMPLETE, plus private CSE access denial. Progress prints every 60 simulated seconds; simulation time differs from execution time. Run serially with other integration profiles; Compose stops its stack afterward. The actual gate passed in user run evidence/20261114-021459Z-02e80b4c/: 729 frame CINs/SUBs, five Group operations, 15 command CINs, 14 independent ACKs and two actual private-read denials. Its final deliberate delivery is INCOMPLETE with two ACKs while the overall test is PASS. A separate 24-check audit passed. Browser hazard QA, restart recovery and MEC remain unverified. See STATUS.md for evidence and open MEC/security/shutdown work.

The selected HTTP gate recreates its containers and explicitly resets to a new paused incident before checking simulated second zero. It records before-reset-status.json, initial-status.json and assertions even on failure. This stops a previously used/expired demo from becoming the test baseline. make demo-scenario-up also recreates its containers so the atomically replaced trace file is mounted afresh; expect a new incident, not continuation of an earlier run. Existing CSE volumes and evidence remain. These commands interrupt the selected local demo; run them serially.

Patched-CSE regression update: evidence/20261114-063427Z-99186a58/ passes the same 729-frame hazard gate with the verified local shutdown patch. An independent 28-check review confirms 15 Group command CINs, 14 independent ACK CINs, the expected stopped-device INCOMPLETE and actual ACP denials. The user terminal reports CSE shutdown completion/exit 0 afterward. The selected role/HTTP regression subsequently passed as recorded below; browser rendering, full recovery and MEC remain separate.

Patched-profile role/HTTP regression also passed: evidence/20261114-123442Z-fabc5346/ passes 18 checks, linked to actual app evidence/20261114-123450Z-8c86fb0b/. A separate 29-check review confirms CSE-backed fixed/moving views, role denials, independent Group ACKs, expiry and protected historical snapshots at the original timestamp. The user terminal reports both app and CSE exit 0. Together with T27 and the hazard gate, this is a verified local regression checkpoint; browser execution, full security/fault recovery, performance, fresh-environment reproduction, submission materials and MEC remain unfinished. STATUS defines the next actual-CSE malformed-event/recovery and measurement work.

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

The CSE launcher stages the bundled config as an owned content-hashed file in /data and passes only a filename to ACME's --config option. Existing data/config files are retained. After a launcher/config update, rerun make p0-smoke to rebuild the changed layer. The initial filename startup bug was fixed and the actual rerun passed. The smoke command stops its containers after p0 exits; use make up-core to keep only the CSE running. Historical post-test CSE exits are tracked separately from T05; the updated profile now passes controlled shutdown/persistence T27, with earlier failure evidence retained. See [status and diagnosis](docs/STATUS.md).

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

## Development strategy and future MEC integration

Keep the current WSL2 + Docker Compose + actual ACME CSE setup. Phase 1 completes and verifies the local system; Phase 2 prepares independent analysis components, external configuration, Docker artifacts and interfaces locally. Phase 3 integrates the organizer Hosted MEC Sandbox only under a separate explicit instruction. Phase 4 submits the functioning system and all materials by 2026-11-20. A working local submission remains required if MEC is incomplete. Historical P0–P4 command/test labels remain traceability identifiers; see [ROADMAP](docs/ROADMAP.md).

Hosted login/OAuth, personal sandbox, per-user Kubernetes namespace and limited platform-admin privileges are organizer-notice descriptions supplied by the user, not verified capabilities. The Hosted endpoint has not been contacted for this strategy. Option C means assessing whether an MN-CSE can be deployed as a MEC App; actual support is unknown, so A/B/another officially supported topology may be considered later. No Kubernetes deployment interface, MEC API or IPE mapping is assumed or implemented as verified. Direct MEC API calls and oneM2M-mediated IPE use require separate evidence.

Host CLI CSE settings use ignored .env/environment values; Docker clients use CSE_CONTAINER_BASE_URL on their private network. The [local example](infra/profiles/local.env.example) documents current defaults. The [Hosted planning template](infra/profiles/hosted.env.example) sets FIREROUTE_PROFILE=hosted_pending, which the runtime rejects before connecting; it also deliberately leaves endpoint/identity/callback fields empty and is not a deployable profile. A remote Sandbox cannot reach WSL localhost; future callbacks require an authorized routable path and verified authentication/TLS. See [deployment plan](docs/DEPLOYMENT.md).

## Independently runnable analysis component

python -m mec.risk.worker accepts bounded newline-terminated ScenarioFrame JSONL on stdin and emits versioned FireRouteRiskResult envelopes on stdout. It reuses the same risk/movement model; accepted results preserve the original event/version/UTC, duplicates produce no new result, and invalid input emits UNKNOWN/no direction then stops. No CSE or MEC client is created. Per-person output remains synthetic and private to a consuming responder adapter. The analysis Compose profile packages this component with network disabled, no credentials/data mounts and a read-only filesystem; image execution and Hosted lifecycle remain unverified. See ARCHITECTURE.md for the exact stream contract.

## Local CSE key, shutdown diagnostics and restart persistence

The updated launcher generates one 256-bit private CSE key in the existing data volume, reuses it on restart and injects it only into an owned runtime configuration. The source configuration and Git contain no key. A missing/unsafe/corrupt existing key fails closed instead of rotating silently. This addresses the default internal-key setting; full CSE authentication/TLS remain separate work. Earlier functional PASS evidence predates this startup change. The updated profile now passes controlled shutdown/persistence T27; affected scenario/role regressions remain next.

~~~bash
# Read-only existing-container state/events/memory/log markers; does not start/stop it.
make diagnose-cse

# Build updated local images, create/read a real marker, stop/start CSE,
# compare the same AE/CNT/CIN IDs/content and configuration, collect stop evidence.
make local-stability
~~~

The lifecycle test intentionally restarts the local CSE and must run serially with demos. It preserves data volumes and unrelated resources and leaves CSE running when successful. It records persistence and shutdown separately: data may survive while the overall test still FAILs for exit 137. The script does not claim a shutdown fix; it distinguishes observed OOM, supported controlled-stop timeout, and an undetermined exit. A single memory sample is not a historical peak. Docker environment/credentials, raw config and raw log bodies are excluded from diagnostics. After the new runtime passes, rerun the real scenario gates such as make p1-hazards.

Both startup and restart wait up to 90 seconds for the existing CSE healthcheck before running a marker probe. A started container or open port alone is insufficient. Evidence records ready-before-prepare.json and ready-before-verify.json; failures retain failure-observation.json and any failed child probe's evidence/reason. An initial readiness/prepare failure leaves shutdown and persistence NOT_RUN. The Nov 14 prepare failure, readiness correction and later actual T27 PASS are recorded in STATUS; broader updated-runtime scenario/role regressions remain pending. Diagnostic event windows handle Docker nanosecond timestamps on the Python 3.10 host without inferring a 137 cause from missing events.

The later actual run reached prepare/restart but recorded SIGTERM → 30-second timeout → SIGKILL/137, then HTTP 404/RSC 4004 for the original marker container. Compose now uses init: true and stop_signal: SIGINT as a locally prepared candidate; the same volumes/grace period and real ACME version remain. The combined guard correction subsequently passed T27. Rerun make local-stability after future runtime changes. Its shutdown PASS requires exit 0, no OOM and this stop's shutdown-complete log; persistence PASS requires the same actual IDs/content/config after restart, without recreating missing resources. An attempted failed verify reports persistence FAIL. See ADR-020 and STATUS for exact evidence and limitations.

The SIGINT candidate subsequently exited 0 but failed completion/persistence: AE/CNT survived while the CIN lookup returned 404 and counters reverted. The user then collected the installed 2026.5.1 source with make inspect-cse-runtime. Its shutdown() sets SHUTTINGDOWN, but the exit cleanup guard excludes that state and skips the DB close path. The image now applies one state-list insertion through infra/cse/patch_shutdown.py, restricted to the exact inspected version/source hash. It changes no oneM2M API or storage format. Startup verifies and records the local patch; the test compares its fingerprint across restart. Unexpected source fails the build/start rather than receiving an unreviewed patch. Actual corrected-runtime T27 passed in evidence/20261114-054111Z-bc1765d8/, including retained resource IDs/content and a normal shutdown log; a separate 28-check review passed. The patched-profile hazard and selected role/HTTP regressions now both pass; next priorities are malformed-event/recovery validation and declared performance measurement. This is controlled same-container stop/start proof, not crash/recreation durability or full application recovery. See ADR-021 and STATUS. The read-only source-audit command remains available and never reads settings/environment/DB contents; its PASS is only source collection.

## Development and team structure

Each developer works on a personal clone and feature/* branch; main receives reviewed PRs. A shared x86 Ubuntu server runs integration/demo services from a deployment-owned checkout. Raspberry Pi is an optional IoT/Edge node, with model and hardware still undecided. Developers do not concurrently edit a shared server directory.

| Path | Responsibility | Current contents |
|---|---|---|
| backend/ | API, incident state, event orchestration | Durable notifications/incidents, Group orchestration, local sessions and actual-CSE role views |
| frontend/ | Resident/responder dashboards | Buildless HTML/CSS/JS and SVG schematic; browser QA pending |
| simulator/ | Synthetic sensors, displays, scenarios | Typed sensors/occupants, independent display application/ACKs and scenarios |
| onem2m/ | CSE adapter, registration, SUB, Group, ACP | Verified local HTTP/bootstrap/decisions/Group/fopt/scoped ACPs; MQTT/full authentication pending |
| mec/ | Edge risk logic and future MEC/IPE integration | Shared pure model and standalone JSONL worker; no MEC API/deployment |
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
| [ROADMAP](docs/ROADMAP.md) | Current Phase 1–4, historical mapping, dependencies and deadline |
| [DEMO](docs/DEMO.md) | Proposed demonstration and submission checklist |
| [DECISIONS](docs/DECISIONS.md) | Decisions and unresolved technical questions |
| [STATUS](docs/STATUS.md) | Single implementation/test progress record |
| [SOURCES](docs/SOURCES.md) | Inspected references, versions and access limits |

[CODEX_FIRST_PROMPT](CODEX_FIRST_PROMPT.md) is a bounded implementation-task template, not an instruction to rebuild the project.

## Schedule and publication

All functioning software, GitHub material, article, video, and presentation files must be complete by **2026-11-20**. Interviews/presentations: November 23–25; team selection: November 26; ceremony: November 27. November 26 is user-confirmed; the public schedule independently confirms the development end, presentation period and ceremony. Exact submission cutoff/timezone and required formats remain to be checked. See [ROADMAP](docs/ROADMAP.md) and [official schedule](https://onem2m-hackathon.io/schedule.asp).

Keep real .env, passwords, API tokens and SSH keys out of Git. Use per-user SSH keys and private VPN access. Raw evidence is ignored by default; select only sanitized artifacts for publication. The organizer describes Apache-2.0 for code and CC BY 4.0 for non-code outputs; the source Apache-2.0 LICENSE is present; documentation licensing and third-party publication notices remain P4 work. See [organizer publication notice](https://estimed.etsi.org/news/estimed_hackathon2/).
