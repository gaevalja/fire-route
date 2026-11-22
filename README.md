# FireRoute

**FireRoute: Intelligent Fire Evacuation and Rescue Guidance System**

The local MEC risk service, project IPE and optional port-3002 dashboard are now implemented for actual validation. Run `make p1-mec-services`; normal use is `make demo-mec-up`. [MEC_SERVICES](docs/MEC_SERVICES.md) explains native registration, CSE request/result subscriptions, failure/expiry handling and the exact remaining runtime boundary. New unit/static success is separate from the earlier component PASS below.

**Local MEC011 is now actually running and its CSE bridge passes seven checks.** User run 20261116-114543Z-372e392f builds the official Go component from reviewed backend 8c66f08e, starts healthy MEC/Redis/ACME containers and verifies actual HTTP discovery → CIN/read-back/SUB plus a reader write denial. The catalog currently contains zero registered services; risk-app registration/consumption, official IPE, manager-controlled app/VM placement and Option C remain unfinished. This is a separate local profile; the main dashboard is not silently labeled MEC-connected. See [LOCAL_MEC](docs/LOCAL_MEC.md) and [STATUS](docs/STATUS.md). Video remains outside the agent task.

Earlier full-system checkpoint: published commit efc65cb passes `make verify-clean` — all 19 stages from a clean Git archive, zero unattempted steps and cleanup exit 0. Python 360/frontend 15/browser-driver 25 cases pass; actual CSE/Group/independent ACKs, faults/recovery, MQTT/discovery and HTTP/HTTPS Chrome all pass. Both browsers pass 20 checks and now render readable Korean. A separate 51-check review matches the complete archived source and actual browser/CSE/device evidence. See the [curated result](docs/assets/local-acceptance-20261116.json), [actual HTTP image](docs/assets/clean-http-dashboard.png), [mobile image](docs/assets/clean-https-mobile.png) and [STATUS](docs/STATUS.md).

The separate [certificate-bound CSE profile](docs/SECURITY.md) also passes 11 actual checks on aa79ace, with an 18-check native-CSE/public-certificate review. It is separate from the 19-stage plan. Main-demo certificate migration, encrypted callbacks/MQTTS, actual MEC deployment/IPE, video recording and publication remain unfinished. Clean-source reproduction is verified on the recorded local host, not a remote CI or different-machine result.

~~~bash
# Actual isolated mTLS/AE-identity/ACP/CIN/SUB gate; normal demo stays separate.
make p1-cse-security
make cse-security-down

# Build/start official local MEC011 + Redis + CSE and verify their actual integration.
make p1-mec-local
# Stop this separate stack while retaining data.
make mec-local-down

# External endpoint mode requires an actual configured MEC011 root.
make mec-discover
# Optional existing dedicated CNT: see DEPLOYMENT.md and .env.example.
make mec-catalog-to-cse
~~~

A simulation-based PoC for the 2026 oneM2M × ETSI MEC international hackathon. GitHub repository and checkout directory: **fire-route**. Repository: [gaevalja/fire-route](https://github.com/gaevalja/fire-route).

> Local release checkpoint (2026-11-16): `make verify-clean` reproduces all 19 stages from efc65cb. Runtime manifest: 4d5319f108a3bc41a873cde03527a6cd9a6b0f1771d361fdbf0e5ec52817fd9d. The application remains a synthetic PoC using the actual CSE. [Submission artifacts](docs/submission/README.md) are prepared locally; actual recording/article publication/MEC remain separate outcomes.

Earlier worktree evidence/20261115-164139Z-e3f6e93b/ retains its 19-stage result and 57-check review with Python 336/frontend 15/driver 23. Its missing Hangul glyphs are resolved in the subsequent clean-commit screenshots above. Original runs are retained with their own versions and counts; no earlier image/latency result is silently relabeled. See [local acceptance](docs/LOCAL_ACCEPTANCE.md) for commands and limits.

Normal use: `make demo-scenario-up`, then http://127.0.0.1:3001/. Read the private role codes from .runtime/access-codes.json. Stop with `make down`.

[FireRoute 시연 사용설명서](docs/USER_GUIDE.md)

The simulator header has a **한국어 / English** selector. The browser keeps the
selection for the sign-in screen, live dashboard, comparison replay and PPO
model review.

~~~bash
# One serial acceptance plan in a separate local Compose project.
make verify-local

# After committing reviewed changes, reproduce from an isolated clean commit.
make verify-clean

# Focused new gates / optional local HTTPS / genuine screen capture.
make p1-standards
make p1-browser
make demo-secure-up
make test-https
make record-demo
~~~

Run these commands from a Docker-capable terminal, one at a time. Chrome with a working sandbox is required for rendered-browser checks; FFmpeg is optional for MP4 encoding. HTTPS uses https://127.0.0.1:3443/ and a generated local development CA. It does not complete CSE originator authentication or encrypt the separate dev CSE/MQTT links. Full procedures and scope are in LOCAL_ACCEPTANCE.md.

> Current state: actual T05, P1_ROUTES, P1_GROUP and P1_DASHBOARD passed on ACME 2026.5.1 / Python 3.12.16. The local loop includes authenticated role APIs, synthetic occupants, CSE notifications → computed routes → Group/fopt → independent simulated display ACKs. The selected ten-floor HTTP/HTTPS browser flow and full 19-stage local gate now pass. Controlled local CSE shutdown/persistence passes; MEC, full application-process/partial-dispatch recovery and authenticated CSE transport remain open. See [STATUS](docs/STATUS.md) for exact evidence and boundaries.

> Scenario update: the user selected **fire_evac: floors 1–10 plus roof, 162 zones**, then requested both fixed guidance and moving residents. Original source is unchanged. The assumed-geometry model, CSE/core runner and ten-floor role dashboard pass selected baseline, natural-hazard, HTTP/HTTPS browser and bounded fault/recovery gates. Korean readability is verified in the clean-run samples; browser hazard-stage recording and broader process-recovery verification remain open. Earlier three-floor runs remain regressions. See [scenario](docs/SCENARIO.md) and [evacuation model](docs/EVACUATION_MODEL.md).

> Verified local checkpoints: T30 controlled CSE stop/start and affected fault/hazard/role regressions pass with real protocol/device evidence. T31's original 30-sample observer baseline is p50 1684.876 ms/p95 2556.166 ms; the later acceptance run measures 557.233/740.982 ms under the same declared metric, without a controlled optimization or speedup claim. See [PERFORMANCE](docs/PERFORMANCE.md) for both run identities and the original graph. Full application-process/partial-dispatch recovery, CSE authentication/MQTTS/advanced semantics and MEC remain open.

Run `make test-scenario` to execute the original engine tests. Opening `simulator/scenarios/fire_evac/index.html` runs its standalone scenario maker, with no CSE/MEC integration. Fire/smoke/collapse rules stay as supplied; the added movement/entrance assumptions are defined separately in EVACUATION_MODEL.md.

## Dijkstra and PPO on the 0015 fire scenario

The selected ten-floor scenario uses the FIRE_EVAC_0015 fire engine. The
standalone two-policy comparison starts two independent simulated evacuees in
the same room at the same time. FireRoute Dijkstra supplies an exit-directed
next move, excluding zones with fire >=45, smoke >=60 or collapse (ADR-031).
PPO uses the deterministic actor exported from the stored MaskablePPO checkpoint.
Both policies use the 0015 departure delay, action timing, exit action and terminal
rules. Open **다익스트라 · PPO 비교** from the responder dashboard to replay the
pair on one timeline with policy results beside the shared map.

```sh
python -m pip install ".[comparison]"
python -m simulator.fire_policy.evaluate
```

The default evaluates 200 paired cases for each of 1, 5, 10 and 15 m/s. The
report at `.runtime/fire-evac-comparison.json` records every action, outcome and
completion time, grouped counts, and the engine and model hashes. To check the
same report against native MaskablePPO, run the following command in a Python
environment with the fire_evac training requirements available. Point to the
original 0015 run directory containing its `source_snapshot`.

```sh
python -m simulator.fire_policy.verify_original "/absolute/path/to/fire_evac/runs/FIRE_EVAC_0015" .runtime/fire-evac-comparison.json
```

`make demo-scenario-up` shows the comparison at port 3001. `make demo-mec-up`
shows it at port 3002 using the risk service and project IPE. Sign in as a
responder to view the comparison. The commands regenerate the source trace for
the 0015 profile. See [comparison rules](docs/EVACUATION_MODEL.md#single-resident-policy-comparison) and
[verification status](docs/STATUS.md).

## Paired policy replay in the demo

Sign in as a responder on port 3001 or 3002 and select **다익스트라 · PPO 비교**.
Set one wind, seed, ignition room and start room, then select **비교 재생 만들기**.
The same fire instance drives both policies using the 0015 movement and rescue
rules. Compare the terminal outcome, its simulated time, and movement and wait
counts in the policy cards. Use the shared timeline to follow both tracks and
inspect each visited path and the fire, smoke and collapse in the same frame.

**저장 PPO 모델 검토** in the same viewer displays individual PPO replays,
action rewards and training curves. The bundled FIRE_EVAC_0015 actor and its
original curves are available immediately.

Use **runs 폴더 선택** for saved models with their training logs, or **모델 파일만 선택**
for an individual `browser_policy.json`. Local file imports are read in your
browser. To list all runs on the demo server and watch training metrics refresh
every five seconds, set `FIRE_EVAC_RUNS_DIR=../fire_evac/runs` in `.env` before
starting the demo. The path is relative to `fire-route-git` for Compose. On a
direct Python launch the adjacent `fire_evac/runs` directory is also discovered.
Replay uses the original browser evaluator and the rules in the selected actor
export. For a checkpoint that only has `model.zip`, export `browser_policy.json`
with the original `fire_evac/export_browser_policy.py --run FIRE_EVAC_XXXX`.

## Selected scenario: fixed and moving guidance

~~~bash
# Original source -> bounded trace -> offline fixed and moving model (no CSE).
make scenario-preview

# Actual CSE/frame/SUB/fixed decision/moving records/Group/ACK gate.
make p1-scenario

# Actual authenticated HTTP/CSE gate for the ten-floor dashboard.
make p1-scenario-dashboard

# Natural hazards, actual Group/ACKs, then a stopped-device INCOMPLETE case.
make p1-hazards

# Actual-CSE invalid input, source expiry and injected API-read-link recovery.
make p1-faults

# Actual controlled CSE stop/start; app and device processes survive.
make p1-recovery

# Verified local observer benchmark: 5 warmups + 30 measured real-CSE attempts.
make p1-latency

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

## Live input and read-link fault validation

The make p1-faults gate passed 56 checks against the actual CSE in evidence/20261114-143344Z-72482bb4/: 468 accepted source frames, nine fault CINs and three Group operations with nine independent device ACKs. A separate 37-check read-only review confirms wire/callback/device/HTTP evidence and matching executed source hashes. The gate exports its own ignored .runtime/fire-evac-faults.jsonl (original seed 59/wind 5, seconds 0–470), replays to the known blocked F4-SA at second 466, then writes nine deliberately invalid/conflicting application payloads through the real sensor AE. Payload mutations are labeled fault injection, not original engine output. Schema rejection, ordered live ingestion, replay without fresh timestamps/extra decisions, source silence and independent display expiry are checked. A temporary TCP endpoint accepts/closes connections without sending any HTTP/oneM2M response; only the dashboard's CSE read clients use it. The actual CSE and callback/device paths stay running. Authenticated production API handlers return UNKNOWN/503 during this read-link fault, then STALE without positions after reconnect until a new source frame is accepted. Recovery keeps the same incident/hazards and receives three real device ACKs.

Run this gate serially with demos; it rebuilds/restarts the local test stack and stops it afterward while preserving volumes/evidence. Progress prints every 60 source seconds, followed by an intentional expiry wait until the existing command expires. No test-only fault controls are added to the public dashboard. The profile pins this local Compose CSE and rejects remote CLI targets. This tests an injected read-client link failure, not full CSE outage, producer ambiguous-write recovery, process restart, browser rendering, latency benchmarks or MEC. Live source time now has TTL/skew/ordering guards; pure offline source replay remains independent of wall time. STATUS.md records the actual T29 result and earlier agent-only BLOCKED attempts.

Post-guard normal regressions now pass too: evidence/20261114-151353Z-146f4874/ repeats the 729-frame hazard gate with 15 command CINs/14 independent ACKs and expected stopped-device INCOMPLETE. Evidence/20261114-151744Z-5bedbd29/ passes the selected dashboard's 18 HTTP/CSE checks, linked to actual app evidence/20261114-151748Z-e76b9a88/. A separate 44-check review confirms matching current source hashes, original frames, actual commands/ACKs, role views and expiry. This completes the affected regression pair for T29; full CSE/write/process recovery, latency and the other open scopes above remain next work.

## Controlled CSE outage recovery (verified bounded slice)

make p1-recovery passed eight host/52 child checks at evidence/20261115-111029Z-2af5bd5a/ and evidence/20261115-111037Z-132f860e/. It exports a separate seed-59/wind-5 trace, starts a private runner, and replays to blocked F4-SA at second 466. The host stops only this local Compose CSE, verifies its actual exit/logs, waits for the surviving application/devices to observe the outage and expiry, then starts the same CSE and checks recovery. The runner receives no Docker socket, published API port or private role files. Host progress includes source replay and a deliberate roughly 31-second expiry wait. Run serially with other local integration/demo profiles. Volumes and old evidence are preserved; CSE remains running afterward and the stopped named runner is retained for inspection.

The application keeps the exact pending trace row/event while input transport is unavailable, exposes RECOVERING/UNKNOWN without guidance, and retries within the existing STARTUP_TIMEOUT_SECONDS budget (default 60 seconds), with half-second spacing and per-request deadlines. Recovery completes the original step/batch once. Before any CREATE it retrieves the deterministic CIN name. Only a real HTTP 404/RSC 4004 permits CREATE; lost responses are reconciled by GET, never an unconditional POST replay. If a still-absent synthetic trace observation expired while disconnected, it can be sampled again with a new event/time only after that actual NOT_FOUND, recording both identities. An existing expired or conflicting CIN is never restamped/overwritten; it requires explicit reset. This resampling rule is for the synthetic trace producer, not physical sensor measurements.

The verified run retains eight AE/12 CNT/seven SUB identities, the Group and historical route CIN; clears stale displays; preserves hazards; and recovers the same incident at version 468 with three fresh independent ACKs. Actual totals are 468 accepted frames, three Group operations/nine commands/nine ACKs. A separate 39-check review at evidence/20261115-112046Z-df473295/ confirms current source hashes and real protocol/device/HTTP artifacts. Application process restart, partial fan-out recovery, crash/power-loss durability, real ambiguous-CREATE network injection, browser rendering, latency benchmarks and MEC are excluded. Publish/dispatch ambiguity remains DEGRADED and requires reset. See STATUS.md for earlier failure evidence and the subsequently passed fault/hazard/role regressions and measurement next steps.

## Observer latency measurement (local baseline verified)

make p1-latency passed in actual user run evidence/20261115-123305Z-389f0ade/: all five warmups and 30 measured attempts completed, 35 Group operations/105 command CINs/105 independent ACK CINs including warmups. A separate 23-check read-only review confirms raw-tick statistics and actual protocol evidence. It uses a separate ignored .runtime/fire-evac-latency.jsonl, original seed 2026/wind 5/seconds 0–34, one outstanding frame and three independent displays. Five warmups precede 30 measured attempts. Its observer timer starts before actual sensor submission and ends after the original dispatch verifies all three independent ACK CINs/display states. This includes protocol, computation, polling/verification and evidence overhead; a second metric also includes public-status commit. No production algorithm, CSE client or default API is replaced.

The prerequisite post-recovery regressions passed: faults evidence/20261115-114241Z-5a695e0e/, hazards evidence/20261115-114942Z-04e93c8f/ and selected HTTP evidence/20261115-115427Z-aa195e09/, with separate 37/44-check reviews. The new measurement tools leave those production modules unchanged. Their full 306-unit/local static checks pass; the later actual user execution supplies the measured result. Earlier agent BLOCKED evidence remains historical.

Run it serially with demos/tests. Progress reports each actual attempt; the final JSON reports counts and Observer_verified_all_acks_p50_ms/p95_ms only when calculable. Failure/incomplete/warmup records remain visible, and planned-but-unattempted counts stay explicit. Successful measured rows alone enter nearest-rank statistics; zero observations have null percentiles. Gate PASS requires all 35 attempts verified, not a claimed speed/SLO. Browser rendering, synchronized physical sensor/device timing, loaded/hazard benchmarking and MEC latency are unmeasured.

The evidence directory stores latency-plan.json, latency-samples.jsonl, latency-report.json and the existing actual CSE/Group/device traces. To recompute without changing evidence, use python3 -m tests.integration.latency_report evidence/REPLACE_WITH_RUN_ID with the printed run path. Its success validates statistics inputs, not CSE authenticity by itself. [PERFORMANCE](docs/PERFORMANCE.md) contains the actual metric table, curated CSV/figure and scope; STATUS.md distinguishes fixtures/static checks, actual execution and read-only review.

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
