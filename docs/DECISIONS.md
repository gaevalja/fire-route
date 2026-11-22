# FireRoute architecture decisions and open questions

Updated: 2026-11-12. DECIDED means a project choice is accepted; it does not mean implemented or verified. Earlier ADRs retain the proposal/status at their decision time; later ADRs and STATUS.md record current implementation and execution. SOURCES.md records source/edition limits.

## ADR-035 — Paired policy playback on a shared timeline (DECIDED)

Date: 2026-11-20. The model replay viewer is the comparison surface. The
existing paired evaluator now supplies both batch outcomes and the viewer's
shared fire frames. Both residents advance on one simulation clock from the
same room with the same 0015 action and outcome rules. Dijkstra follows the
current exit-directed routing policy with its configured blocking thresholds.
PPO uses the pinned 0015 actor. The responder-only comparison endpoint evaluates
a synthetic case in memory. The live dashboard continues to serve CSE guidance
and population views, and prior policy diagnostic payloads remain compatible.

## ADR-034 — Saved PPO replay in the ten-floor demo (DECIDED)

Date: 2026-11-20. The responder dashboard loads the supplied Fire Evac replay
viewer in a same-origin frame on demand. The viewer reuses the pinned fire
engine and the original browser evaluator, applying each actor export's
movement, reward and rescue rules. The app serves the bundled 0015 actor and
training logs through responder-only read routes. An optional read-only runs
directory supplies other actors and live training metrics. File imports and
scenario generation run in the browser. The live scenario continues to use
its own current CSE observations and its existing incident controls.

## ADR-033 — Client-side evacuation timeline and crowd playback (DECIDED)

Date: 2026-11-20. The user asked for residents' movement to play back like
fire_evac/replay.js, with a readable timeline. The live API returns only the
current frame, so frontend/scenario/timeline.mjs records each new fresh
responder frame (fire/smoke/collapse, blocked zones, drawn route, every
resident's link/progress/state, ACK count) in compact typed arrays in the tab's
memory: never localStorage, never the CSE. It is cleared on logout, reset or a
new incident, capped at 2,400 frames, and only covers what the tab observed.
No backend history endpoint was added.
The panel provides play/pause, step, start, speed (1–30×), a return-to-live
button, a stacked population chart by resident state with clickable event
markers, and an event list derived from frame differences: route, no-route,
blocked, collapse, fire reaching a floor, ACK drop/recovery, evacuation
milestones and stuck residents. Route-change events closer together than 20 s
are not listed, because congestion-aware routing flips exits often. Residents
glide between frames up to 3 s apart and snap across larger gaps such as +30초.
While replaying, a banner states the map is not the current situation; the
live guidance cards stay live.
The WebGL view draws every resident by state colour on top of zones; lower
floors show faintly through the floors above. Floor tabs show the people still
inside and fire per floor. Polling drops to 800 ms while the scenario runs.
Residents are responder-only data, so the timeline is hidden for residents.
The SVG schematic is unchanged apart from replayed frames.

## ADR-032 — WebGL 3D/2D building view in the selected dashboard (DECIDED)

Date: 2026-11-20. The user asked for the building to be rendered with OpenGL so
people can read the situation in 3D and 2D instead of the node schematic. The
browser form of OpenGL is WebGL, so frontend/scenario/building-view.mjs draws
the 164-zone network with raw WebGL 1 (no library): 3D with an orbit camera and
see-through floors above the selected one, or a 2D top-down plan of one floor.
Zone colours follow route > fire > smoke priority under blocked/collapsed, the
route has an x-ray pass so stairwell segments stay visible, and clicking a zone
shows its values and moves to its floor. No dependency was added: the HTTPS
profile's CSP allows scripts from 'self' only, which rules out CDN libraries.
The room layout is the same assumed schematic as the route model, not a
surveyed plan. The view only renders data the role already receives, so
residents see the route without hazard values. The SVG schematic stays in the
DOM and is the automatic fallback when WebGL is unavailable or the context is
lost; the browser gate's SVG checks are therefore unchanged. The new module is
served through the existing static whitelist (missing whitelisted files now
return 404) and packaged in pyproject data-files. Pure layout/colour/picking
helpers have Node unit tests; the rendered view still needs the real browser
gate (make p1-browser) before it is described as browser-verified.

## ADR-031 — Lower Dijkstra blocking thresholds to fire 45 / smoke 60 (DECIDED)

Date: 2026-11-19. The user requested that FireRoute Dijkstra exclude zones with
fire >=45, smoke >=60 or collapse, replacing 55/70. The only behavioral change is
`fire_block_index`/`smoke_block_index` in fixtures/evacuation_assumptions.json,
so the fixed query, moving residents, MEC risk service, hazard oracle and the
one-person PPO comparison all use the same new policy. The blocked origin still
yields NO_VERIFIED_ROUTE. The policy SHA-256 changes, so results recorded under
55/70 stay valid only for their recorded policy hash. These remain uncalibrated
demo thresholds, not tenability limits. The legacy three-floor synthetic smoke
threshold (mec/risk/routing.py, 70) and the 0015 PPO terminal rules (fire 60,
smoke 80) are unchanged.

## ADR-030 — Shared 0015 scenario and policy comparison (DECIDED)

The user approved the 0015 engine and trained PPO weights, preserving FireRoute
Dijkstra and the 170-resident model. Compare one resident per policy with the
same seed, wind, room, action delays and terminal rules. Dijkstra retains its
route calculation and uses the common exterior exit action at the lobby.
Waiting in a room after no route can yield room rescue. Collapse follows the
source generator. Keep the comparison in the responder diagnostic record and
bind it to the existing MEC result verification. See EVACUATION_MODEL.md.

## ADR-001 — Identity and safe directory change (DECIDED / directory verified)

Name: FireRoute. Full name: FireRoute: Intelligent Fire Evacuation and Rescue Guidance System. Repository and checkout: fire-route. The starter was a nested directory beneath the workspace parent; no nested Git metadata, symlinks or visible process using that directory as cwd was found, and the destination did not exist. It was renamed within the writable workspace. No Git history existed to rewrite; parent .git is empty. That was the pre-upload inventory; the user later configured gaevalja/fire-route and pushed main. ADR-007 records the current branch/base.

All existing Markdown documents are updated to the new identity. Preserve the existing fixture bytes/fixture_id for data compatibility; no service or fixture migration is performed by this documentation task. Pre-edit file hashes were saved outside the project for review.

## ADR-002 — Team integration and module boundaries (DECIDED / not implemented)

Personal clone/IDE/Codex per contributor; main plus feature/* and reviewed PRs. Shared x86 server runs integration/demo from a deployment-owned checkout/artifact; no concurrent direct editing. Adopt backend/, frontend/, simulator/, onem2m/, mec/, infra/, tests/, docs/ responsibilities from ARCHITECTURE.md. Keep current placeholder directories; create missing implementation directories only when work starts. No code/package imports currently need migration.

## ADR-003 — Local Sandbox and Option C first (DECIDED target / unverified)

Prefer the organizer-specified Local ETSI MEC Sandbox STF_685/deploy revision. First target is MN-CSE as MEC App on MEC Host (Option C), with an explicit Cloud IN-CSE registrar relationship. Separate CSE common services, MEC lifecycle, MEC-IPE mapping and risk/controller logic. Acquired TR-0086 revision review is mandatory before claiming its deployment procedure is followed. A simple local CSE remains the P0/P1 development path.

If C is unavailable, preserve the failure and assess official Option B first, or another verified official option. Record actual topology/permissions and affected tests; never silently relabel it C. The current full guide and repository remain inaccessible/unacquired. Plan fallback checkpoints for Nov 12/16; no server deployment is authorized by a documentation change.

## ADR-004 — Environment roles and access (DECIDED plan / unverified hardware)

Personal PCs support independent local development. Shared x86 Ubuntu 24.04 planning size is 4–6 vCPU, 12–16 GB RAM, SSD >=100 GB; not official minimums. Verify exact Sandbox requirements and actual capacity. Raspberry Pi is an optional AE/sensor/display/fault-test endpoint; model and specs unknown. Full Sandbox ARM64 support is not assumed. Use private VPN, per-person SSH public keys, least privilege and separate deployer permissions.

## ADR-005 — Core contracts, evidence and scope (DECIDED / not implemented)

Retain F01–F19 and T01–T15 traceability; add temperature, synthetic occupants, deployment/registration and clearing/contract tests. Keep the original graph and baseline/A-block/no-route behavior. Commands and independent ACKs are separate CSE resources. Add durable deduplication/version/outbox recovery and role-filtered timestamped occupant data. Internal application contracts are proposals, never fabricated standard API responses.

Use docs/STATUS.md as the sole progress record; do not create a second root STATUS.md. Keep actual CSE/MEC tests separate from unit mocks and documentation checks. Evidence must show implementation/deployment provenance, real responses and measured timing. Raw evidence remains ignored; future publication curates sanitized artifacts.

## ADR-006 — Deadline and rubric selection (DECIDED scope / source inspected)

Use P0 environment/CSE, P1 actual fire-response E2E, P2 MEC deployment/interworking, P3 hardening/measurements, P4 all submissions, completed by Nov 20. The former detailed phases are regrouped rather than dropped: reconnaissance/foundations/CSE → P0; routing/group/UI → P1; MEC → P2; security/protocols/discovery/fault/metrics → P3; publication → P4. Advanced handover/location/semantics/agent/FL are conditional scope.

Original rubric now inspected: 17 Expert cells and relevant prerequisite tiers. Prioritize selected rows listed in RUBRIC.md, with no guaranteed score. Label discovery/FCNT, single MEC service and simple app deployment are lower-tier results until additional Expert conditions are demonstrated. Preserve this distinction in article/video/interviews.

## Open technical decisions

| Topic | Working proposal | What must be verified / responsible lane |
|---|---|---|
| CSE | Configurable adapter; ACME candidate supporting MN-CSE | Installed version/plugins/release, real SUB/fopt/ACP/MQTT and registrar behavior / oneM2M |
| Runtime | Python 3.12; standard-library API/unittest and buildless HTML/CSS/JS (ADR-013) | Actual target-runtime CI, browser QA and immutable dependency/image lock / infra + owners |
| CSE execution | Compose where supported, process alternative | Docker socket/network/port capabilities; host Python currently 3.10 / infra |
| GitHub | gaevalja/fire-route; main and feature/* | Membership, branch protection, actual CI runs and deploy permissions / integration owner |
| Cloud IN-CSE | Separate registrar role | Actual host/owner/credentials/POAs; label same-host simulation / oneM2M + infra |
| TR-0086 / Sandbox | Official compatible revision | Full guide, ETSILabs approval, pinned deploy commit, actual lifecycle/orchestration / MEC |
| MEC-IPE | Official provided compatible bridge first | Placement/model, implemented operations, catalog/OpenAPI incl. MEC 013/033/046 / MEC |
| Application state | Minimal persistent dedup/outbox or CSE recovery | Concurrency/retention/crash recovery; choose smallest proven store / backend |
| Timing policy | Configurable TTL/skew/ACK/retry | Demo values and boundary tests before P1; clock method before metrics / backend + QA |
| Temperature | Typed synthetic degC collection | Any additional blocking rule requires a declared demo policy / simulator + risk |
| Occupants | Synthetic zone/count data | Seed/scenario/reset/null handling and role policy / simulator + backend |
| Raspberry Pi | Endpoint only | Actual model/architecture/OS, network, sensor/display hardware / IoT |
| Submission | GitHub/article/video/presentation by Nov 20 | Exact cutoff/timezone, platform/formats/durations and license files / publication |

Every future decision records alternatives, evidence, owner, date, impact and tests. Unknown access or runtime behavior remains unknown rather than becoming a default success.


## ADR-007 — P0 actual-CSE foundation (DECIDED / local T05 verified)

User authorized development on 2026-11-11. Base main a6e3509 is pushed to gaevalja/fire-route with Apache-2.0 LICENSE. Work branch: feature/p0-cse-foundation. Earlier statements of unknown Git/owner describe the pre-upload inventory.

Use the published acmecse==2026.5.1 package for the isolated development CSE; website/master 2026.05.3 is not assumed equivalent. Standalone IN-CSE avoids inventing unavailable registrar settings; MN-CSE/Option C remain P2. Each run uses owned expiring resource names, actual returned AE IDs, an ACP reference by actual resource ID, a real SUB handshake and CIN read-back/callback comparison.

The HTTP binding client, notification persistence and sensor contract use the standard library. This removes external package requirements for offline core tests and keeps business logic independent of a web framework. Defer FastAPI to P1 application APIs; use unittest now, compatible with later pytest selection. Python product runtime remains >=3.11/3.12 target. Host Python 3.10 unit execution is a compatibility check only.

Build dependency setuptools==80.9.0 provides explicit package discovery/metadata without adding an application runtime dependency; its release/minimum Python were checked on PyPI. The CSE package is a necessary external runtime implementation, not a custom CSE. Record its actual installed dependency set. The Python Docker base is a 3.12 family tag; an immutable image digest/transitive lock is still required before claiming a fully locked deployment. Direct package/image build and target runtime remain unavailable in the agent sandbox. The user's later successful T05 run verified actual ACME 2026.5.1 / Python 3.12.16; its installed distribution list is captured in the original meta.json. This does not verify a separately installed FireRoute wheel or all CSE capabilities.

Confirmed sandbox limitations: AF_INET/socket bind and Docker Unix socket denied; PyPI DNS unavailable. Do not lower standards by substituting a fake CSE. Finish/review the runnable profile, retain real BLOCKED output, and obtain a user-terminal or CI actual-CSE run. HTTP-only header identity is an isolated development limitation, not completed security/Expert evidence.


## ADR-008 — Independent graph work while actual CSE execution is blocked

Follow ROADMAP parallel lanes: implement the pure Dijkstra/synthetic-smoke policy under mec/risk/ while awaiting the user's actual-CSE run. T01 and T03 are unit-level requirements; T02's algorithm subcase can PASS while its CSE-persistence subcase stays NOT_RUN. This is the project's actual graph algorithm, not a fixture feasibility script or a MEC mock. No controller/event ordering, route CIN, fan-out, ACK or UI completion is inferred. Packaging includes the canonical fixture as a data file; the existing fixture bytes remain unchanged. Package installation itself is unverified in this sandbox.

## ADR-009 — CSE config filename and visible startup failures (DECIDED / actual startup verified)

The user's initial 2026-11-11 run built the actual CSE image, printed ACME 2026.05.1, and exited (0) before becoming healthy. The original adapter passed an absolute --config path together with CLI --headless. Inspected upstream Configuration.initDirectories rejects any directory in that argument; its early error printer suppresses output when CLI headless is set. This was the source-supported explanation; the subsequent real package run verified the corrected startup path without requiring a version change or data deletion. The exact installed source has not been extracted.

Stage the bundled config as /data/fire-route-<SHA256>.ini and pass its basename with -dir /data. Create only an owned content-addressed file; preserve user acme.ini, previous managed configs and CSE database volumes. Reuse identical files and reject modified managed files rather than overwrite them. Set [console] headless=True in the config and omit CLI --headless so early configuration errors are visible. Emit only safe version/config-filename startup metadata, without config contents.

Keeping the original absolute argument is incompatible with the inspected implementation. Blindly switching CSE versions or deleting data volumes would not address the known adapter error. Seven focused regressions pass (62 total units); Compose parsing and compilation pass. Owner: infrastructure/oneM2M lane. The actual user-terminal rerun reached Healthy and passed T05; original evidence is evidence/20261111-100438Z-d1cfa0f4/. Post-test exit 137 remains a separate shutdown issue and does not establish successful recovery.

## ADR-010 — Durable ordered incident decisions before Group dispatch (DECIDED / actual route gate verified)

After actual T05 PASS, implement the next dependency: sensor notification → ordered incident state → computed hazard/route → actual CSE CIN persistence. Reuse the verified P0 callback/client and original graph; add no runtime dependency. SQLite stores application deduplication, per-sensor sequence/time/binding, per-incident version/blocks and a persistence outbox in one transaction. It does not expose oneM2M services or replace CSE resources.

Persist event IDs with content digests, reject conflicting reuse/sensor rebinding and ignore older, stale or excessively future observations. Replays reuse the existing decision; a lower smoke reading never clears a block. Initial policy is explicitly synthetic; temperature retains degC and has no invented fire threshold. A stored graph/policy/source fingerprint requires explicit migration when recovery rules change.

Decision publication uses deterministic event-derived resource names, GET before CREATE and actual read-back before marking the entry persisted. A partial or ambiguous CREATE remains pending; a later reconciliation finds any committed CIN instead of blindly repeating POST. This outbox tracks decision persistence only; future command delivery and ACK completion need their own state. P1-scoped ACPs are opt-in during bootstrap so P0's verified default behavior is preserved: controller creates/reads decisions, resident reads routes, responder reads routes/hazards. Actual denial/authentication proof must still be tested.

The initial 18 new units passed (80 total). User run evidence/20261111-103437Z-cff86001/ subsequently passed actual P1_ROUTES, including three hazard/route records and two CSE denials. The agent's direct runtime remains blocked; that limitation is distinct from the actual user execution. Full restart/service resume, periodic controller stale guidance, role APIs/UI and MEC remain subsequent work. Owner: backend/oneM2M.

## ADR-011 — Actual Group with independent display ACK producers (DECIDED / isolated actual gate verified)

Implement a real CNT-member GRP/fopt command followed by three independently generated ACK CINs. The aggregate has OK status while successful member CREATEs have CREATED status in the inspected official TR-0025 example. Validate request correlation, member count/parent IDs, distinct created CINs and actual member read-back; never interpret fan-out success as display application.

Use three Python spawn processes inside the local runner container, each with its own actual AE-ID, command SUB/receiver, persistent display state and ACK writer. The coordinator passes no admin credentials to these processes and never generates their ACKs. Separate containers/physical devices are unnecessary for this first simulated-device gate; do not claim physical IoT hardware, network fault isolation or MEC deployment from these processes. Process PIDs, AE IDs and individual sanitized wire logs are evidence.

Display schema_version=1 adds explicit guidance_status to the previously proposed command contract before its first implemented use. Validate action/exit/nullability/UTC expiry; persist command digests, version high-water state and ACK outbox. Duplicates reuse an ACK; older/expired/future/foreign-source commands cannot replace valid directions. No-route and local expiry clear the displayed exit. Controller ACK subscriptions use a decoder bound to each actual reference; validate device/incident/event/version/command and actual ACK CIN read-back. New child-type ACP restrictions allow SUB CREATE while denying fabricated command/ACK CIN writes; live enforcement remains to be tested.

The actual make p1-group gate passed in evidence/20261111-115340Z-34c169f6/: three complete A/B/no-route deliveries, then three stored command CINs but two ACKs/INCOMPLETE after stopping display-c. Missing ACKs stay outside complete counts. Original group/member/callback/ACK/state evidence passed 50 independent audit checks. Authentication/TLS, full restart/dispatch recovery, live roles and MEC remain separate gaps. The full unit suite now passes 107 tests, including the late worker-error guard and ADR-012 regressions. No runtime dependency or external/shared deployment was added.

## ADR-012 — Local Group member identity matches CSE canonical representation (DECIDED / actual rerun verified)

The first actual P1_GROUP attempt, evidence/20261111-114816Z-fbc3f740/, received HTTP 201 / RSC 2001 and an actual three-member GRP. The request used SP-relative /<cse-id>/<CNT-ri> members; the observed ACME 2026.5.1 response stored the same local members as bare CNT resource IDs. Generic ensure correctly refused the unequal strings, so the first run stopped before fan-out/device application.

Use the actual local command CNT IDs directly in this local Group. Keep exact ensure/read-back comparisons and require three distinct IDs; do not ignore mid, overwrite unknown resources or strip arbitrary remote prefixes. Remote Group membership is outside this local slice. Four regressions exercise canonical CREATE/reuse, changed-member rejection, duplicate-ID rejection and bad member-count rejection. The subsequent actual Group/ACK rerun passed. Owner: oneM2M/backend. This fixes address representation without relaxing membership identity or changing the CSE implementation.

## ADR-013 — Local role dashboards on the verified CSE loop (DECIDED / HTTP-CSE slice verified)

Date: 2026-11-12. Owner: backend/frontend/QA lanes. After the user pushed 80f6e87 on feature/p0-cse-foundation, continue on feature/p1-role-dashboards based on that verified commit. This is a stacked development branch because main still contains the documentation baseline; do not silently merge main or discard the verified foundation. Integrate the foundation first, then review/rebase the dashboard branch through the team PR workflow.

Use Python's existing standard library HTTP server, unittest and buildless HTML/CSS/ES modules for this bounded local PoC. FastAPI/Vue were initial proposals; adding those dependencies would not improve the required real-CSE path at this stage. Keep pure view/state functions and explicit role/API contracts (ROLE_API.md) so a later framework migration remains possible. Node is a frontend-test tool only. No application runtime dependency was added. This server choice is for isolated local demonstration, not a claim of hardened public hosting.

Generate separate high-entropy role codes into ignored mode-0600 files; load only hashes in the app and use expiring HttpOnly/SameSite=Strict sessions, same-origin writes and bounded login attempts. Keep CSE identities server-side. Extend actual CSE resources via opt-in public status, private diagnostics and occupancy policies; preserve earlier smoke defaults. Whitelist API fields, correlate incident/event/version, return PENDING during updates and remove directions for stale/missing/CSE-error states. Synthetic occupants keep null as UNKNOWN and expire independently. Old APPLIED device observations become STALE. Device ACK producers and CSE storage remain independent of the API.

The long-running simulator writes actual telemetry CINs, consumes real SUBs, computes/persists decisions and controls actual Group members/ACKs. Heartbeats are scheduled after each completed action so missing-ACK waits leave a visible INCOMPLETE state. Reset creates a new owned namespace/incident and retains CSE data. Notification SQLite connections now close deterministically for the long-running process; existing durability/concurrency regressions remain green. Restart/dispatch recovery is still a separate unverified requirement.

Actual P1_DASHBOARD passed 17 checks, including role/session denial, CSE occupant ACP denial, A/B/no-route, missing ACK, expiry and reset. The latest rerun includes ACK-age behavior and per-stage role responses; exact runs/audits are indexed in STATUS. Browser rendering/accessibility, actual TLS/CSE authentication, CI and MEC remain unverified. Existing profile/security limitations remain explicit. No Sites hosting, shared deployment, PR, main merge or new-branch push was performed.

## ADR-014 — Adopt the user's fire_evac scenario without changing its model (DECIDED / source tests verified)

Date: 2026-11-12. User direction: use the scenario in C:\Users\lilkid\Downloads\fire_evac. Owner: simulator/backend/UI lanes. This supersedes the three-floor building as the final scenario target while preserving its verified fixture, code and CSE runs as regressions. No previous PASS is reattributed to the new 162-zone scenario.

Preserve all seven supplied files byte-for-byte under simulator/scenarios/fire_evac/ and record source hashes in manifest.json. Keep the external originals unchanged and remove any requirement that other developers have that Windows Downloads path. The original Node tests are exposed through make test-scenario and CI source configuration; no new application runtime or simulator container is introduced in this import. Source provenance/attribution remains visible because no license declaration was supplied.

The source owns fire/smoke transport, seeded randomness, wind, interpolation, collapse and termination; SCENARIO.md records those exact rules. FireRoute owns a future typed current-frame/CSE publisher, deduplication/clock contract, evacuation traversal policy, Group/ACK and protected role views. Human movement, entrance edges/costs, fire/smoke traversal thresholds and occupant behavior are absent from the source. They remain unresolved rather than being guessed from spread links or legacy node IDs. Private precomputed next-minute state must not be published as current telemetry; accelerated simulation time is separate from real communication/TTL clocks.

Rejected shortcuts: replacing the source with the existing three-floor smoke-button demo; copying the scenario UI over the real-CSE dashboard and claiming integration; interpreting fire index as temperature; adding arbitrary people/RL rules; or treating source-engine tests as selected-profile E2E. Keep the existing app working while adding a separately tested profile. T22 source/engine checks pass; T23 actual frame/CSE and T24 integrated routing/Group/UI remain NOT_STARTED/NOT_RUN. No push, PR, deployment or change to the supplied engine/configuration was performed.

## ADR-015 — Both modes with an explicitly assumed pedestrian network (DECIDED / unit-offline verified)

Date: 2026-11-12. The user requested both fixed-origin guidance and moving synthetic residents with realism, then explicitly delegated dimensions/population choices (no measured inputs available). This authorizes a new declared evacuation layer while preserving ADR-014's original fire engine. Owner: risk/simulator/backend/UI. EVACUATION_MODEL.md and fixtures/evacuation_assumptions.json define the contract and uncalibrated defaults.

Reuse one source state/clock and one model for both views. Fixed queries do not move residents. Moving residents use seeded departure/speed variability, edge travel time, shared finite capacities, fair queues and replanning at nodes. Collapse/hazard blockage cannot erase a person or imply a casualty; in-transit blocked occupants remain counted. External exits, distances, capacities, slowdown and blocking indices are project assumptions. NIST S12/S13 inform model components/tests, not numeric calibration or compliance. Geometry and source hashes are evidence; no real building plan or actual person location is inferred.

Node 24.22.1 is the observed host tool pin (.node-version) for a built-in-module headless wrapper. No new third-party application dependency or Node installation in the Python container is needed. The wrapper verifies the source snapshot, exports bounded current states with a trace digest, and strips private future state. Python validates/replays each frame; actual CSE ingestion/subscriptions precede model updates. Source manifests now include .cjs, JSON fixtures and the Node version file. Wheel metadata includes source/assumption/dashboard data; package installation and immutable image/transitive locks remain unverified.

Separate local profiles preserve the verified legacy app: p1-scenario is the selected actual CSE/core gate; p1-scenario-dashboard is its HTTP/role/expiry gate; demo-scenario-up serves the new fixed/moving UI on 127.0.0.1:3001. Moving/private counts remain responder-only, and the common three-sign Group illustrates the configured fixed guidance query. This does not claim actuator placement/orientation per resident. Missing/stale/mismatched CSE state clears directions and positions. Model units/offline replay pass; actual selected CSE/HTTP execution, browser rendering, full restart recovery and MEC remain separate unverified gates.

## ADR-016 — Inspect paused resident records without extending live guidance (DECIDED / HTTP-CSE slice verified)

Date: 2026-11-12. User reported no resident options and UNKNOWN in moving mode after pausing. Live observation expiry correctly removed private current fields, but the UI discarded the selection list and rebuilt it on every poll. Preserve stable same-incident selections and use an explicitly historical record when live data is unavailable. Logout, role change and incident reset clear private cached records.

The selected responder-only snapshot endpoint reads the latest committed public status, then that version's named immutable route/moving/occupancy/frame CINs through the actual responder CSE client. Validate incident/event/version/time/policy and population conservation before returning the original recorded time and explicit HISTORICAL/is_live=false/route=null fields. Reads do not advance simulation or renew observation timestamps. Show recorded people/counts/positions with their time while live directional guidance remains expired. The legacy endpoint set stays unchanged. No local invented population or weakened TTL is used as a fallback.

164 Python and 15 frontend-state tests pass locally. The extended actual HTTP gate and native browser dropdown checks remain NOT_RUN; previous baseline HTTP evidence does not verify this endpoint. No dependency or deployment is added. Owner: backend/frontend/QA; see STATUS.md for command output and next verification.

## ADR-017 — Give selected HTTP checks an explicit initial state (DECIDED / actual rerun verified)

Date: 2026-11-12. User run evidence/20261112-105931Z-f68c1310/ failed initial_both_modes_available. Both original HTTP snapshots show CSE=LIVE, simulation_second=30, version=31, STALE and three observed ACKs. Compose reported the existing app Running; the gate assumed a fresh second-zero instance. The failure occurred before the historical endpoint assertions, so it neither verifies nor disproves that endpoint.

Initialize the selected HTTP gate by authenticated reset, require a different paused READY incident, and retain pre/post status and partial assertions. Retry only an explicit busy rejection (409), never an accepted or ambiguous POST. Force container recreation for the selected gate and demo start so the regenerated trace (written by atomic rename) gets a fresh bind mount even when source/configuration is unchanged. These commands intentionally restart the selected local demo; CSE volumes and old evidence are retained. Keep real CSE assertions unchanged. No engine/model/TTL change or new dependency is needed. Owner: backend/QA/infra. Actual CSE rerun and browser QA remain separate gates.

Verification update for ADR-016/017: user run evidence/20261112-121211Z-6e06237b/ passed all 18 HTTP/CSE assertions. New paused incident, live expiry, resident snapshot denial and responder historical people retrieval are verified for this slice. Separate read-only audit evidence/20261112-124857Z-678e9961/ passed 23 checks including actual named-CIN responses and source hashes. Earlier pending statements above describe the pre-rerun checkpoint; native browser dropdown QA, broader fault cases and CSE shutdown diagnosis remain open.

## ADR-018 — Verify natural ten-floor hazard progression separately from baseline (DECIDED / actual CSE core verified)

Date: 2026-11-14. Owner: backend/QA/infra. Resume from published main 7c5b396 on feature/p1-hazard-validation. Keep the seven source files and default seed-2026 interactive demo unchanged. A dedicated trace uses source seed 59/wind 5 with 900 exported seconds, because execution observed an asymmetric stair blockage that the symmetric seed-2026 downstairs ignition does not provide. No hazard or collapse payload is hand-edited.

backend/hazard_checks.py derives blocking from the validated current source frame and uses independent BFS reachability to reject fabricated no-route or unsafe/unknown route edges. Coverage requires baseline, an alternate path excluding a blocked original-path node, collapsed-node exclusion and disconnection while the origin remains unblocked. Alternative paths may still reach the same exit. Population, recorded zones, source event/version/time/policy, Group member identities, independent ACK set and applied display state are checked. Collapse may occur on an already fire-blocked node; no collapse-only rerouting claim is made. All residents may already have evacuated before these later fixed-origin checks.

make hazard-preview is offline only. make p1-hazards reuses the real ScenarioSession: every source second is ingested/read/notified through the actual CSE before model acceptance. Observed stages publish real records and Group commands with three independent ACKs. After full coverage/no-route, stop display-c, accept the next source second and require three member CINs but two ACKs/INCOMPLETE. This is a missing-device subcase, not restart/service-continuity recovery. Role ACP denials remain required. Evidence and dedicated trace paths are separate from the interactive profile; no fake CSE or new dependency is added. Actual CSE execution is unavailable to the agent, so only local/offline results may be marked verified here.

ADR-018 verification update: user run evidence/20261114-021459Z-02e80b4c/ passed the actual gate on ACME 2026.5.1/Python 3.12.16. All 729 source frames had matching CIN creation/read-back/SUB; stages at 0/466/600/727 received three independent ACKs, then version 729 received two/INCOMPLETE after display-c stopped. Five Group operations created 15 command CINs and 14 independent device ACKs were read back; two private-read denials passed. Separate read-only audit evidence/20261114-022105Z-09c654f5/ passed 24 checks and hashed original artifacts. Earlier agent-only/offline limitations above describe the pre-user-run checkpoint. Hazard browser QA, full recovery, CSE shutdown and MEC remain open; no application code change was needed after this run.

## ADR-019 — Local completion first; Hosted integration is separately gated (DECIDED)

User direction, 2026-11-14: preserve WSL2 + Docker Compose + actual ACME CSE. Phase 1 completes local functions, security/fault handling and evidence; Phase 2 prepares a separately runnable risk component, external configuration, images and documented interfaces locally; Phase 3 accesses/integrates the organizer Hosted MEC Sandbox only under a separate explicit instruction; Phase 4 finishes submission by Nov 20. A local-only working submission must remain possible if MEC is unavailable. Historical P0–P4/F/T identifiers are preserved for traceability, with the new phase mapping in ROADMAP.md.

Hosted account/OAuth login, personal sandbox, Kubernetes namespace and restricted platform administration are user-provided notice descriptions, not verified runtime capabilities. Do not visit/probe/login/deploy to the Hosted endpoint during Phases 1/2. Option C is a later support assessment; A/B/another official topology may be selected only against acquired guides and actual permissions. Keep direct MEC API use distinct from MEC-IPE-mediated oneM2M resources. Remote services cannot reach WSL localhost; future deployment needs an authorized routable callback path, verified TLS and authentication rather than guessed endpoints or disabled certificate checks.

First local stabilization slice: persist a private non-default CSE secret without rotation on restart; add read-only Docker lifecycle diagnostics that select safe fields instead of logging environment/credentials; add real-CSE persistence read-back across a controlled restart. Exit 137 alone is not an OOM diagnosis. A shutdown fix requires actual Docker state, events, memory observations and relevant logs; unit fixtures must not become actual CSE evidence. CSE internal-secret configuration is not complete originator authentication or transport security.

ADR-019 implementation checkpoint: local startup key handling, selected-field Docker diagnostics, controlled actual-CSE persistence probe, inactive Hosted profile guard and standalone network-free JSONL risk worker are implemented. The worker reuses the existing model and does not alter the local app/CSE/Group path. New regression total is 214 Python tests; 15 frontend and original-engine checks pass. The local worker CLI accepted three archived actual source envelopes with event/version/UTC retained and CSE/MEC=NOT_CONTACTED. Actual updated CSE lifecycle/key behavior is BLOCKED in the agent environment; no 137 cause or runtime fix is claimed without the prepared user-terminal test. Public ACME/Docker docs were reviewed, no Hosted request was made, and no new dependency was added. STATUS.md links exact raw outputs/provenance.

## ADR-020 — Test graceful CSE interruption after observed stop timeout (IMPLEMENTED_UNVERIFIED)

Date: 2026-11-14. Owner: infra/QA. Actual run evidence/20261114-044119Z-73dadf33/ records SIGTERM, about 30 seconds, SIGKILL, exit 137 and OOMKilled=false, with no shutdown-complete log. Prepare/read-back passed; healthy restart retained the AE identity but the marker CNT lookup returned HTTP 404/RSC 4004. This supports a controlled-stop timeout and failed marker verification; it does not prove every earlier 137 was identical, actual disk corruption, or an exact TinyDB buffering/index failure. Keep all old evidence unchanged.

Set local Compose CSE init: true and stop_signal: SIGINT with the existing 30-second grace period. Docker's built-in init forwards signals and reaps processes; no Python dependency or upstream CSE patch is introduced. Public ACME master CSE.forceShutdown uses SIGINT and exposes graceful shutdown logic. That source is a rationale for this candidate, not proof of the pinned installed 2026.5.1 behavior. The limited installed-source scan does not establish runtime signal handlers. Actual success must come from the next lifecycle test; changing the signal is not completion.

Preserve actual CSE resources, version, key and volumes. No missing marker recreation, volume reset, mock substitution or database migration is permitted to make this gate pass. Require exit 0/no OOM plus a shutdown-complete marker within this controlled stop's log window, then healthy restart and identical AE/CNT/CIN IDs/content/configuration. A failed attempted read is persistence FAIL, not NOT_RUN; retain actual HTTP/RSC. Overall remains FAIL if shutdown fails even when persistence succeeds. Classify SIGINT timeout only when configured SIGINT, observed interrupt/KILL and measured grace agree. Strip full exec commands from Docker event actions.

Local 226-test regression and Compose field validation pass at evidence/20261114-044944Z-507a5d0d/; 12 read-only actual-run checks pass separately. Actual corrected lifecycle execution is BLOCKED at the agent's Docker preflight. Next: user-terminal make local-stability; investigate actual outcomes before accepting this candidate or changing anything else. Hosted contact/deployment and Git publication remain outside this change.

ADR-020 verification update: actual evidence/20261114-045529Z-4bea3b88/ exits 0 in 0.657 seconds without KILL/OOM, but lacks a shutdown-complete marker and loses the latest named CIN lookup; retained CNT counters revert. The candidate is not a complete fix and T27 remains FAIL. Next inspect the pinned installed lifecycle/storage code with make inspect-cse-runtime before selecting another correction. Collection reads only selected package source with literals removed, not runtime settings/data, and makes no lifecycle mutation. Seven new synthetic tests/full 233-test suite pass; actual source collection is BLOCKED for the agent. Source-collection PASS cannot become product lifecycle PASS. STATUS records exact evidence; no further runtime guess or DB workaround is applied here.

## ADR-021 — Correct the inspected, hash-pinned ACME exit guard (VERIFIED for controlled stop/start)

Date: 2026-11-14. Owner: infra/QA. Actual installed-source collection evidence/20261114-050745Z-321ec6ce/ contains 15 ACME 2026.5.1 source records. CSE.py original SHA-256: 5b8678ba45450090befef0d183faad429724478122f4f910f368d2a44d83e7ae. The source sets SHUTTINGDOWN in shutdown(), while the atexit _shutdown() guard admits only RUNNING/SHUTTINGDOWNRESTART. A request through that state therefore skips service cleanup/storage.shutdown()/closeDB(). The console's post-loop cseShutdown call and buffered-storage close behavior are also present in the inspected files. This is a source-confirmed guard defect consistent with the observed missing latest update; no on-disk corruption, exact extent of lost data or successful historical-data recovery is established.

Apply a single additional accepted state (SHUTTINGDOWN) in the existing guard at image build time, using infra/cse/patch_shutdown.py after the existing pinned package installation. Keep upstream bytes/comments/license otherwise intact; change no service ordering, oneM2M resource/HTTP API, secret, database format or caching setting. The adapter rejects another version, source hash or AST shape. An image manifest identifies the patch and original/patched hashes. Startup verifies that reversing exactly the insertion restores the pinned original; it refuses unrelated/tampered source even with an edited manifest. Record this as ACME 2026.5.1 plus FireRoute patch acme-2026.5.1-shutdown-state-guard-v1, never as unchanged stock upstream behavior.

The existing filename staging, persistent private key, init/SIGINT and 30-second grace remain. Actual T27 must see verified identical patch/config fingerprints across restart, exit 0/no OOM, this stop's cleanup-complete marker and the same actual AE/CNT/CIN IDs/content, with no resource recreation. Missing/unverified/different patch metadata fails the local gate. A new upstream release/hash needs explicit source review and regressions before renewing/removing this workaround; it is never patched automatically. No dependency, custom CSE substitute, data-volume mutation/migration or Hosted operation is introduced by this adapter.

Eight adapter tests and two probe provenance regressions extend the full unit suite to 243 PASS. A separately extracted installed cleanup function, using injected mock collaborators, skips storage close in SHUTTINGDOWN before the correction and closes once afterward, ignoring a repeated call after STOPPED. This reproduces source control flow; it does not execute a real CSE/DB flush. Evidence/20261114-052225Z-fab1dcc0/ includes raw output and source/config provenance. At this preparation checkpoint image build/lifecycle were unverified because Docker access was blocked for the agent. The subsequent actual verification update below supersedes that pending T27 step; affected scenario/role gates remain next. Existing actual failure evidence stays unchanged; no commit/push/PR is performed.

ADR-021 actual verification update: user run evidence/20261114-054111Z-bc1765d8/ passes T27 with the built patched image. Controlled stop takes 0.832 seconds, emits this stop's completion marker and exits 0 without OOM/KILL. Actual same AE/CNT/CIN IDs/content and cni/st survive healthy restart; config/key and patch fingerprints match, with no observed default-key warning. Patched CSE.py SHA-256: 457eb8f64809d93286fb3c9ffd5ee52d7b27f4913d35593402c41027da5995c9. Independent read-only review evidence/20261114-061431Z-ed937160/ passes 28 checks over 16 actual exchanges. This supersedes the earlier runtime-pending checkpoint for controlled same-container stop/start only. Container recreation, crash durability, full application recovery and historical missing-data recovery are not established. Next rerun natural-hazard and selected role gates on this patched profile. Source/tests are unchanged; no Git publication/Hosted contact is performed.

ADR-021 hazard regression update: actual evidence/20261114-063427Z-99186a58/ passes the existing natural-hazard core gate at the same verified patch/config fingerprint. The independent 28-check review at evidence/20261114-123016Z-78235456/ confirms 729 frame exchanges/notifications, 15 command CINs, 14 independent ACK CINs, expected INCOMPLETE and two ACP denials, without changing model/source/tests. User terminal additionally shows CSE completion and exit 0; this is labeled as terminal evidence. Selected role/HTTP regression remains next; full application recovery/browser/MEC are not established.

ADR-021 selected HTTP regression update: actual evidence/20261114-123442Z-fabc5346/ passes all 18 role/fixed/moving/stale/history assertions; app evidence/20261114-123450Z-8c86fb0b/ carries the same verified patch. Independent review evidence/20261114-123938Z-aa825610/ passes 29 checks against HTTP, actual CSE and separate device records, including 31 frame matches, six ACKs and original historical timestamps. The local patched lifecycle/hazard/role regression checkpoint is now verified. Browser rendering/full recovery/security/performance and MEC remain separate open work; no new service code, dependency or publication is introduced by this evidence update.

## ADR-022 — Separate live acceptance from offline replay; validate bounded input/read-link faults (LOCAL_SLICE_VERIFIED)

Date: 2026-11-14. Owner: backend/QA. Baseline: clean committed 5a8fcf2. Judging value: verifiable oneM2M usage, reliability, Security/Privacy and interview evidence; cost: one small live-input guard and an integration harness reusing actual CSE/roles/Group/devices. Risk control: preserve source physics/assumptions and old gates, reject before model mutation, pin the fault profile to local CSE, record expected versus observed outcomes. No optional AI/MEC feature or dependency is added.

Pure Evacuation remains independent of wall time. Its existing ordering/context failures gain a ValueError subclass raised before movement. The live guard revalidates ScenarioFrame, accepts fresh next frames, rejects expired/future/regressing UTC or ordering/context errors, and recognizes exact replay without moving people or refreshing source time. Unexpected model errors propagate. ScenarioSession requires matching durable actual notification content/CIN RI and journals dispositions; its existing normal source path uses this guard. Session incident/source binding applies even to the first frame, so a valid callback cannot choose a foreign context. An accepted callback means durable schema receipt, not automatic business acceptance. Expired live role reads skip private latest telemetry so malformed/uncommitted sensor CINs cannot mask expiry; fresh invalid private verification still fails closed, and historical snapshots retain original time.

T29 keeps the CSE and producer/device paths alive and injects only the resident/responder read-client connection fault using a loopback TCP endpoint that accepts/closes without HTTP bytes. This is explicitly not a CSE replacement, actual server outage, transparent proxy or complete recovery implementation. A private authenticated production API server is used for actual role GETs; there is no public fault endpoint/action. Bad inputs are intentional application-envelope mutations stored/read through the actual sensor AE; original engine output is unchanged. Controller replay reuses an already durable real callback and is not misrepresented as new network redelivery.

The gate expects unchanged decisions/clock/hazards under invalid input, UNKNOWN/503 during read-link loss, source/device expiry, STALE after transport-only reconnect and recovery only after the next fresh real CIN/SUB with three independent ACKs, same incident and retained blocked stair. Group operations and fault resource counts are derived from execution; no fabricated success/status/log is allowed. Full CSE/container outage, ambiguous CREATE retry, automatic process/selected-model recovery and latency benchmarking remain separate work. Run serially with demos; retain CSE volumes and old evidence.

Local evidence/20261114-134320Z-1c85e068/ records 261 Python/15 frontend/original engine checks and an offline source preflight PASS, with source/assumptions unchanged. The agent-only attempt remains BLOCKED (Python 3.10 and Docker denial). Subsequent actual user execution evidence/20261114-143344Z-72482bb4/ passes T29's 56 checks: 468 accepted frames, nine fault CINs, three Group operations/nine independent ACKs, expiry and same-incident fresh-frame recovery. A separate 37-check read-only review at evidence/20261114-150845Z-7af50c01/ confirms source/wire/HTTP/device correlations. Verification is limited to this local input/read-link slice. Affected normal hazard and selected role/HTTP gates now also pass at evidence/20261114-151353Z-146f4874/ and evidence/20261114-151744Z-5bedbd29/, with a separate 44-check review at evidence/20261114-174340Z-66948580/. Owner next: preserve this verified feature checkpoint, then implement/test full CSE/write/process recovery and performance. No new Git publication or Hosted access occurs.

## ADR-023 — Preserve pending synthetic input across controlled CSE outages (LOCAL_CONTROLLED_SLICE_VERIFIED)

Date: 2026-11-15. Owner: backend/DevOps/QA. Baseline: clean committed e723463, user reports push complete. Judging value: actual oneM2M service continuity, visible failures and reproducible evidence; cost: small pending-input/app-loop changes plus a host-controlled gate. Risk: uncertain CREATE/partial-dispatch outcomes, expired observations and cursor loss. No new dependency, fire-engine/assumption change or MEC call is introduced.

Keep the exact pending raw row/envelope across transport loss, with bounded half-second retries using the existing CSE readiness budget. Named GET/strict actual NOT_FOUND precedes CREATE; matching committed content is reconciled without blind POST replay. Never overwrite/restamp a stored expired/conflicting CIN. For the existing synthetic trace producer only, an expired sample may be re-emitted with new identity/time after actual proof that its named CIN is absent. Log old/new identity and actual 404/4004. This is an explicit new synthetic sample, not an old physical measurement made fresh.

Keep the original step/batch progress and paused intent. Input transport loss is RECOVERING/UNKNOWN with no live guidance; successful fresh CSE/SUB acceptance permits one publish and independent ACK verification. Permission/protocol/expired-committed failures, exhausted budget and ambiguous publish/partial fan-out remain fail-closed DEGRADED/reset. Process restart and durable pending/model/outbox restoration remain separate work.

Use host Docker to stop/start only the existing local CSE while the app, callback receiver and devices survive. Reuse private production API handlers for role probes; host/control evidence must show the same real container/image and graceful stop, then retained actual AE/CNT/SUB/GRP/CIN IDs, verified config/patch, new CIN/SUB/fan-out/ACKs and ACP denials. Do not mount Docker into the runner or create a fake outage server. The new T30 gate starts its outage before the pending frame CREATE; network loss after CREATE has meaningful unit fixtures but remains actual integration NOT_RUN. Crash/recreation/process recovery and performance are excluded.

Executed preparation: 282 Python unit tests and existing frontend/original-engine checks pass; real host gate attempt evidence/20261114-180110Z-50b60ea6/ is BLOCKED before start/stop by Docker access. No actual recovery PASS is claimed. Next run make p1-recovery from the user's Docker-capable terminal, inspect real artifacts, resolve failures and rerun affected normal/fault gates. Continue latency measurement after this gate stabilizes. No commit/push/PR or Hosted access is performed here.

Actual follow-up: evidence/20261115-013857Z-ee51c168/ failed before input recovery because the private test server still had an empty action allowlist and rejected step with HTTP 400. CSE stop itself passed. The fix keeps the default T29 probe read-only and explicitly allows only step for recovery, with child/host configuration validation before CSE stop. This corrects test wiring; it does not change public API authorization or backend/CSE behavior. Five new regression cases/full 287-unit PASS are recorded at evidence/20261115-015148Z-4aef0b9a/; at that correction checkpoint actual T30 remained NOT_RUN; subsequent verification follows below. Keep the original failed run and 11-check cause review; do not turn a reviewer/unit PASS into service-recovery PASS.

Subsequent actual execution now passes: host evidence/20261115-111029Z-2af5bd5a/ (eight checks), child evidence/20261115-111037Z-132f860e/ (52 checks), and independent read-only review evidence/20261115-112046Z-df473295/ (39 checks). Same-container graceful stop/start preserves actual resources, frozen pending input recovers only after real NOT_FOUND/fresh synthetic emission, and version 468 receives three independent ACKs. Counts are 468 accepted frames/three Group operations/nine ACKs; actual source hashes match this checkout. Earlier failure/BLOCKED evidence remains unchanged. This verifies the surviving-process, pre-input-CREATE controlled-outage design only. The subsequent affected T29/hazard/role regressions pass; ADR-024 records the subsequent separate observer measurement; durable app-process/partial-dispatch recovery and actual ambiguous-CREATE network loss remain open.

## ADR-024 — Measure a real-CSE observer pipeline without cross-host clock subtraction (LOCAL_BASELINE_VERIFIED)

Date: 2026-11-15. Owner: QA/backend. The three post-recovery regression gates pass on source manifest 10133093ea3ba6e94e57ecca29999b4ec8912e0601efa643e7d9786681b19b5a. Judging value: reproducible performance evidence, communication-protocol proof and interview/article quality. Cost: a standalone runner/reporter using the existing real CSE session; no runtime dependency, risk/source rule or normal application API change. Preserve the verified production path.

Use one coordinator's perf_counter_ns domain. Start immediately before submitting a source frame through ScenarioSession.accept_raw. The primary Observer_verified_all_acks_ms ends when the original DeliverySession.dispatch returns after actual member-CIN/independent-ACK read-back and display-state checks. This includes observer polling/verification/journaling overhead; it is not a synchronized sensor-to-device arrival metric. A temporary instance wrapper records boundaries and calls the original method exactly once, restoring it even on failure. Observer_pipeline_commit_ms ends after publish also persists public status. Record input acceptance, pre-fanout persistence, fanout/ACK verification, public commit and attempt-end ticks; do not subtract device UTC clocks. Cross-host E2E remains unavailable because offset uncertainty is not measured.

Run a fixed sequential local workload: original seed 2026/wind 5, simulated seconds 0–34, 170 assumed residents, three independent display processes, one outstanding frame. Five identified warmups precede 30 measured attempts. Every attempted result remains recorded, including INCOMPLETE/FAILURE and warmup failures. Protocol/transport exceptions stop further submissions to avoid unsafe replay; planned-but-unattempted counts remain explicit. Successful measured observations alone enter nearest-rank p50/p95, computed from raw integer nanoseconds; zero successful observations have null statistics. A green gate requires all 35 attempts complete and real evidence/counts match, without a claimed latency SLO. This baseline is not a hazard/load/concurrency/physical-sensor/MEC benchmark.

Store the measurement plan/clock/version/provenance, per-attempt identities and raw ticks, existing real CSE/Group/device traces, and a recalculable report. A read-only report CLI recalculates from plan/samples without changing original evidence. Unit clock/transport fixtures remain separate from actual measurements. At preparation, real measurement was NOT_RUN/BLOCKED with null statistics. Subsequent actual user execution evidence/20261115-123305Z-389f0ade/ passes five warmups/30 measured attempts, 35 Group operations and 105 independent ACK CINs. Separate review evidence/20261115-124131Z-a59ba704/ passes 23 actual-artifact/math checks; primary p50/p95 are 1684.876/2556.166 ms and status-commit p50/p95 are 2037.361/3109.567 ms. Original artifacts stay unchanged. [PERFORMANCE](PERFORMANCE.md) provides curated publication assets. Local Matplotlib 3.5.1 was used only for static data export, with no runtime dependency. No browser/cross-host/load/MEC timing or SLO is inferred.

## ADR-025 — Complete the local submission scope with separate acceptance gates (IMPLEMENTED_UNVERIFIED)

Date: 2026-11-15. The user requested rapid completion and explicitly chose local work. Start from clean committed ae6ac82. Preserve the original fire source, assumptions, working HTTP demo, CSE volume and earlier evidence. Do not install/probe Hosted or local MEC as a substitute for the selected local product.

Select basic discovery, a genuine oneM2M MQTT binding gate, rendered browser checks, optional browser/API HTTPS and clean-commit reproduction. Judging value: concrete protocol/discovery evidence, secure-transport/ACP explanation, reproducible GitHub and usable submission materials. Cost: isolated optional stacks, small explicit client/API extensions and dependency-free browser tooling. Risks: new transport compatibility, certificate ownership, browser timing and source regression. Keep all real claims gated on actual execution. Advanced SDT/SAREF, cryptographic CSE-originator binding, durable model/process/partial-fanout recovery and MEC remain explicit gaps; the new HTTPS listener does not silently satisfy them.

Use Eclipse paho-mqtt==2.1.0 only in the new standards image, rather than hand-writing an MQTT wire protocol. Its [official release page](https://pypi.org/project/paho-mqtt/2.1.0/) and [VERSION2 callback documentation](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html) were inspected. The [official Mosquitto v2.0.22 release](https://github.com/eclipse-mosquitto/mosquitto/releases/tag/v2.0.22) supplies the selected isolated broker version; image availability/digest is still unverified. ACME's [MQTT configuration](https://acmecse.net/setup/Configuration-mqtt/) and [CLI binding option](https://acmecse.net/setup/Running/) document the candidate settings, but current online documentation is not proof of the installed 2026.5.1 MQTT behavior. T32 must verify the exact real implementation. Default CSE command/config remains unchanged.

MQTT primitive/topic design follows [Release 4 TS-0010 V4.0.1](https://www.etsi.org/deliver/etsi_ts/118100_118199/118110/04.00.01_60/ts_118110v040001p.pdf). Discovery uses the documented RETRIEVE/filter/URI-list approach in [TR-0025](https://specifications.onem2m.org/tr/tr-0025/latest/8.7/) and [TS-0009 parameter mappings](https://specifications.onem2m.org/ts/ts-0009/latest/6.2/). Basic labels alone are not advanced semantic interoperability. No guessed response is accepted as an actual result.

The CDP driver uses Node built-ins and official protocol commands with a temporary sandboxed profile and pipe, following [Chrome's debugging-profile isolation](https://developer.chrome.com/blog/remote-debugging-port) and [Chromium's pipe framing](https://chromium.googlesource.com/chromium/src/+/main/content/browser/devtools/devtools_pipe_handler.cc). Pinned development-certificate trust applies only in that ephemeral test profile. Passwords, cookies, login bodies and raw browser console values are never exported. Genuine screencast frames are optional; local FFmpeg is an optional external encoder, not an application dependency or fabricated video.

The main browser/API HTTPS option uses Python ssl, OpenSSL-generated private local CA files, certificate verification and existing role controls. It adds no CA to an OS trust store. API connections have bounded reads and lazy per-thread TLS handshakes. CSE callbacks and internal HTTP/MQTT remain separate development transports. Clean reproduction extracts only reviewed regular files/directories from the committed tree, uses isolated projects/ports and never resets volumes. CI is configured with .node-version and new gates; configuration is not an executed GitHub result.

English article, eight-slide HTML presentation, actual-local topology SVG and narration are prepared under docs/submission/. Publication, polished video, PDF rendering, final release and submission receipt remain actual external/manual results. Do not insert placeholder public URLs or claim an Expert score. Owner: backend/oneM2M/QA/publication; exact local results/BLOCKED evidence and next command are in STATUS.

Follow-up actual execution: T32 passes nine checks at evidence/20261115-134325Z-aab15d43/. Read-only review evidence/20261115-134851Z-d60d6c19/ passes 13 checks over 57 HTTP exchanges, three MQTT primitive exchanges, eight discovered/read-back AEs and two SUB verification/event callbacks. This verifies the bounded basic discovery/mixed-binding slice, not advanced semantics, TLS, originator authentication or rendered UI.

The enclosing acceptance run evidence/20261115-134253Z-59070d03/ fails at CSE-core because Docker cannot bind already-used 127.0.0.1:18080; the P0 application never starts. Fixed acceptance ports were an orchestration defect, not a new CSE protocol failure. Replace all four fixed assignments with OS-selected free loopback ports, reserve them together during selection, record them in metadata and forward the same values into both browser commands/Compose/HTTPS checks. Close reservations before Compose; retain failure evidence for any later external race. Never stop an unknown listener. Six runner/allocator tests/full 336 units pass at evidence/20261115-134934Z-2b4c37e4/. Actual updated acceptance remains NOT_RUN; its 12 previously unattempted steps stay unverified. No dependency, CSE/algorithm/source-model or normal demo-port change is introduced.

Next actual acceptance evidence/20261115-142714Z-ae131e33/ passes 15 stages, proving the selected-port path reaches CSE/Group/hazard/fault/recovery/observer gates, then fails rendered-browser with three HTTPS steps unattempted. Actual Chrome 157.0.8103.78 passes four login/label/focus/control-visibility assertions before NEW_INCIDENT. No reset POST reaches the backend. Read-only review evidence/20261115-144705Z-68f3a307/ matches the original executed driver hash, unchanged product sources and original child PASS summaries. Initial result commits at 14:33:48.235Z, while the inferred previous UI poll was at 14:33:47.930Z; backend-ready probes finish at 48.277/48.282 and the browser stops by 48.305. The old helper throws immediately on a disabled button; its error was collapsed to Error. Readiness race is the evidence-supported inference; the original DOM/error detail was not saved.

Correct the test driver rather than forcing enabled controls or changing backend behavior: wait on actual presence/visibility/enabled/hit-test/finite coordinates before a single dispatch; no action replay. Store bounded boolean-only diagnostics/fixed error codes and a password-free failure screenshot. Eleven driver/control unit checks pass at evidence/20261115-144733Z-99d81d41/; these fixtures do not establish actual updated-browser PASS. No CSE, frontend, algorithm, Python dependency or runtime policy changed. Next make p1-browser, then actual HTTPS gates/full acceptance after browser stability.

The next focused attempt evidence/20261115-145032Z-f8887326/ is BLOCKED before page creation/any assertion, despite a valid Chrome version. Its failure.json has no rendered state and the old generic BROWSER_OPERATION_FAILED code. Linked app audit 145032Z-558933c9 has no page/login/scenario request; first /healthz succeeds at 14:50:35.211Z, after failure metadata at 14:50:32.674Z. The initial CSE-backed result with three ACKs follows at 14:50:39.304Z. Read-only review evidence/20261115-145928Z-f08aa862/ passes seven checks, including reconstructed original Makefile/browser hashes and unchanged product sources. Startup-navigation timing is inferred; the exact original network error was not recorded.

Make both selected HTTP/HTTPS startup commands wait for actual healthchecks with --wait --wait-timeout 120 (supported by installed Compose help). Retain backend/model/DOM readiness checks separately. Add bounded initial read-only navigation retry only for connection-refused/reset/empty-response; never retry certificate errors or authenticated/mutating actions. Retain sanitized network code/attempt count and distinct NAVIGATION/PAGE_READY phases. Fifteen CDP/navigation/control unit cases pass; dry-run startup arguments and syntax/whitespace checks also pass. Actual updated startup/browser/HTTPS remain unverified. Product/CSE/frontend/engine/assumptions are unchanged; no dependency, publication or Hosted action is added.

Latest focused Chrome run evidence/20261115-150352Z-dea91b59/ successfully navigates on attempt 1 and passes 11 assertions through reset, selection, advancement, ACK rendering and playback/pause. It then reports PAGE_EVALUATION_FAILED at RESIDENT_ISOLATION. Linked audit evidence/20261115-150349Z-2eef59d7/ serves the second document at 15:04:24.595Z, app.js at .608Z and model.mjs at .630Z, then a GET / returns 400 at .632Z without a second session POST. The HTTP handler rejects query-bearing GET requests before static delivery. Native form submission before the deferred module's listener is installed is the evidence-supported cause; the original raw exception and resident DOM were not retained. The old failure screenshot depicts the responder, so it cannot prove resident-page state. Ten independent read-only checks pass at evidence/20261115-161909Z-664b1934/; original runs are retained.

Correct the driver without changing product behavior: wait for the exact destination document to reach complete (including deferred modules) in each isolated context; a completed about:blank or a parser-created form does not suffice. Before the single requestSubmit, add a trailing temporary guard that observes the application's preventDefault; if absent, prevent native navigation, clear the password and fail with LOGIN_HANDLER_NOT_READY. Do not replay uncertain credentials/actions or suppress arbitrary page exceptions. Separate resident navigation/login/isolation phases, diagnose only the active role's page under the existing screenshot guard, and hash all four driver modules in metadata. Twenty-three unit cases (14 CDP/document + nine control/login) pass at evidence/20261115-162104Z-ff5ca811/; product hashes are unchanged. The agent's actual attempt evidence/20261115-162117Z-ef75a100/ is BLOCKED at Chrome startup with zero assertions. No updated actual browser, HTTPS or full acceptance PASS is claimed. Owner/next: make test-browser in the user's already-running HTTP demo, or make p1-browser to start it; then the remaining HTTPS/full gate.

Actual follow-up on 2026-11-16 KST: focused browser 20261115-163629Z-b879ec54 passes all 20 assertions. The subsequent current-worktree acceptance 20261115-164139Z-e3f6e93b passes every one of 19 stages, zero unattempted, cleanup exit 0. Python 336/frontend 15/browser-driver 23 and all actual CSE/MQTT/Group/hazard/fault/controlled recovery gates pass; HTTP and HTTPS Chrome each pass 20 checks, HTTPS certificate/role gate passes eight with TLS 1.3. A 57-check read-only review 20261115-165511Z-77d52c9a matches all runtime/test hashes and correlates both browser incidents with 33 actual source frames and four three-ACK deliveries each. No service change or repeated unrelated suite is needed to document this actual result. Retain the original failures and blocked agent attempts as revision-specific history.

Freeze/review this verified working tree, commit, then run make verify-clean: the existing PASS is not clean-commit/remote-CI/release proof. Inspected real Chrome screenshots lack readable Hangul glyphs, a visual recording-environment issue outside the DOM/layout assertions. Correct font coverage and inspect the rerun before capture; do not call the video complete from a functional browser PASS. Article/slides now cite verified local transport/browser scope while CSE cryptographic identity, process/partial-dispatch recovery, MEC and publication remain explicit gaps. The acceptance observer repeat measures p50/p95 557.233/740.982 ms; keep it distinct from the original baseline/chart and avoid a controlled-speedup claim. No dependency, runtime code, server/MEC deployment, credential output, commit/push/PR or public post is introduced by this evidence/documentation review.


## ADR-026 — remaining local CSE security/MEC preparation after verified baseline

The user authorized commit/push and remaining work on 2026-11-16, then confirmed no ETSI account/Sandbox/repository access and selected local implementation first. Commit a66059f preserves the real 19-stage baseline. Push failed on GitHub DNS resolution; clean-commit acceptance is BLOCKED before all 19 steps because Docker access is unavailable. Neither result is fabricated as success.

Implement a separate certificate-bound CSE profile rather than interpreting a valid Basic/Bearer credential as permission to claim any originator header. The real ACME CSE remains authoritative. NGINX verifies the client certificate and binds its CN to X-M2M-Origin; a different header is rejected before forwarding, and real ACP denials remain distinct. Enrollment signs the CSE-returned actor IDs and keeps the CA key only in its privileged runner. Separate networks/volumes/no host ports preserve the main demo. Backend/callback HTTP, main scenario/MQTT migration and production PKI remain explicit limits. NGINX 1.30.6 is selected from the official stable release list; image pull/digest/actual runtime remain unverified. This new dependency supplies a standard maintained TLS reverse proxy, not a custom replacement CSE. Details and primary links are in SECURITY.md.

Implement only the MEC011 service-availability operation confirmed in the inspected official OpenAPI history, with a compatible structural subset and externally supplied URL/app ID/token/CA. Reject invalid status/HTML/redirects/oversize/unsafe settings, preserve actual HTTP failure status without credentials, and retain only safe catalog metadata. Optional real CSE publication verifies an existing labeled dedicated CNT and matching CIN read-back; no uncertain CREATE is replayed. This is an application-AE bridge, not standardized MEC-IPE, Option C placement or proof that MEC013/033/046 exist. The organizer deployment guide/TR-0086 body remain unreadable with the tool, and actual account access is separately confirmed absent; no guessed Kubernetes/deployment API is implemented. No new Python dependency is needed.

To repair recording-environment Hangul, register the existing Noto Korean font only in the disposable Chrome profile using private Fontconfig. This avoids system/package changes or redistributing a Windows font in Git. Actual font resolution selects Noto Sans KR and local coverage checks find Hangul; new screenshots/video still require actual browser inspection. Preserve sandbox and TLS checks. Browser source identity now includes the font helper.

Final preparation evidence/20261115-173533Z-6a1f8ad9 passes 360 Python units, 25 browser-driver cases, compilation, Compose parsing and seven isolation/preservation checks. Later affected MEC failure-status tests are rerun before commit. Real security attempt 172711Z-236fe00d is Docker-BLOCKED; MEC probe 172712Z-ebb133c9 is BLOCKED before network because no endpoint is configured. New actual secure CSE/MEC/renderer results remain pending. Commit/push authorization is explicit, but network failure must be reported honestly; no shared deployment or Hosted contact occurred.


T36 actual follow-up: user-terminal 20261116-040708Z-ba53f73b passes 11 checks on pushed aa79ace/source manifest f8aac0f7fc95f404a809cc529f6858c7e1ae709c081db1d26532bd830b095492. Read-only review 20261116-042739Z-0906daca passes 18 checks over 48 native exchanges/two callbacks/eight public certificates, without private-key reads. One old predicate name containing credentials is redacted; preserve that original and correct the future label, rather than weakening the secret filter or rewriting evidence. Duplicate upstream Server warnings do not coincide with any captured request-ID/RSC/CIN mismatch; leave the upstream warning visible. This verifies the bounded isolated gateway, not secure main-scenario/MQTT/callback/MEC/clean reproduction. The operator next runs make verify-clean.

Actual clean follow-up: the user pushes efc65cb and 20261116-044349Z-18300187 passes all 19 make verify-clean stages, zero unattempted and cleanup 0. A 51-check read-only review verifies the archived source, runtime manifest, actual browser/CSE/device correlations and observer arithmetic. Both 20-check browsers use the private Korean font and inspected screenshots are readable. Preserve this verified runtime and add only reviewed screenshots/curated results/documentation now; do not repeat unchanged integration suites for documentation-only edits. The result is same-host clean-source reproduction, not remote CI or a different machine. T36 remains separate, no official MEC/IPE support is inferred, and actual video/editorial/publication/submission remain the next deliverables. No new architecture, dependency, service implementation or original-evidence rewrite is required to record this result.

## ADR-027 — Acquire official local MEC and verify a bounded catalog-to-CSE path

Date: 2026-11-16. The user excludes video work and explicitly requests local MEC integration. This authorizes local official-source acquisition/review/integration now; the organizer Hosted service remains excluded. Preserve the running demo, passed efc65cb checkpoint and original source/evidence. No further account-readiness question is required.

The [public official deployment commit 92b3b430](https://labs.etsi.org/rep/mec/etsi-mec-sandbox/-/commit/92b3b4309e5df4260465b4d863cb7e2539ccd58a) is newly readable through the research tool. It describes Kubernetes/Helm/OAuth and host-level deployment work, with moved paths still referring to the earlier playbooks location. Current STF_685 deployment bodies remain unacquired. Do not execute guessed commands or silently select master: acquire both official STF_685 repositories, freeze the actual resolved commits/trees and deployment-file hashes, then inspect those exact sources before choosing the installation path. The source helper never runs downloaded scripts, changes host settings or resets Docker/CSE.

Build a separate private integration client plus real ACME CSE. For a configured actual local MEC011 root, read/validate the real catalog, create two actual application AEs and a dedicated expiring CNT/ACP/SUB, publish one catalog CIN, match its writer/reader read-back and durable callback, and require a reader 403/4103 write denial. Reject public/Hosted targets and container-loopback misconfiguration before network; unsupported auth must fail rather than be dropped. No new dependency or custom platform server is introduced. Existing catalog fields and APPLICATION_AE_BRIDGE_NOT_MEC_IPE label remain unchanged. Discovery does not establish application placement, official IPE, useful MEC service consumption or Option C.

Judging value: actual service discovery/interoperability, scoped access and reproducible official-source provenance. Cost: isolated source helper, existing client/notification components and seven prepared runtime assertions. Risks: unknown current deployment prerequisites/API version, unavailable source/network, host-wide installer effects and uncertain CREATE outcomes. Controls: locked source/review before install, private separate projects/volumes, no CREATE replay and explicit BLOCKED/FAIL results. Owner: MEC/DevOps plus oneM2M/QA.

Actual attempts: source acquisition 20261116-054618Z-315206e2 is BLOCKED with ETSI_DNS_UNAVAILABLE; no installer runs. Local catalog/CSE 20261116-054618Z-0b98f0f2 is BLOCKED before network because no MEC_LOCAL_SERVICE_MGMT_URL exists. Implementation verification 20261116-060540Z-0f196edf passes all 376 Python units and 12 compilation/whitespace/source/evidence-preservation checks; the new 16 tests use explicit local Git/SQLite/config/CSE fixtures, not actual MEC. Frontend 15/original-engine and Compose configuration checks also pass. No real local platform/API/CSE-integration success is claimed. Next execute make mec-local-prepare in a network-capable terminal, inspect acquired sources, then install/test the verified local platform path. Video remains outside the agent's work.

Actual source acquisition supersedes that blocker: user 20261116-062033Z-fbbbbe96 obtains both STF_685 repositories, and 20261116-064534Z-9a6586f6 revalidates the locks/clean trees. Inspect backend 8c66f08e (tree aded204f) and frontend df11a72b. Current full deployment uses PyInfra/Kubernetes/OAuth with host mutations; the official MEC011 Go component itself requires private Redis and its documented MEEP environment. Select a bounded local Compose packaging of that unmodified official component, not a host-wide installer or fabricated platform. This costs a source staging helper/image/overlay and six focused fixtures; judging value is actual implementation/API/interworking evidence while preserving the running local demo. Full Sandbox UI/orchestration and Option C remain separate.

Stage only committed Go component/package/license objects: 2,199 files at 20261116-064118Z-1b2ee3ed. The first staging attempt 064010Z-fb0fee40 rejected Git's legitimate go-apps ancestor directory; narrow the guard to allow ancestor directories only, retaining traversal/symlink rejection. Do not modify the official checkout. The Go builder pin 1.25.0 comes from acquired deployment settings; Redis 6.2.24-bookworm is present in the official Docker image manifest and retains a legacy-compatible server series for go-redis v6. Build-copy module resolution/Go metadata/license are retained in the image; actual compiler/pull compatibility is unverified until execution. No new Python runtime dependency is introduced. Runtime data is not pre-seeded; upstream logging without an active scenario is retained.

make p1-mec-local starts/waits for the real component, Redis and dedicated ACME, then builds/runs the real catalog consumer with --use-aliases. It retains services/volumes for inspection. The earlier explicit-endpoint mode becomes p1-mec-external. Agent make mec-local-up reaches Docker but socket access is denied; no build or API success is invented. Final implementation evidence 20261116-064910Z-d6b70a5d passes 382 Python units and 20 compile/merged-topology/source/preservation checks. Next obtain actual make p1-mec-local output from the Docker-capable user terminal; no further source-readiness question is needed.

Actual follow-up: user make p1-mec-local now completes Go/image build and three healthy services, then passes seven native checks at 20261116-114543Z-372e392f. All 153 executed source hashes match the prepared worktree. Six actual creates, 16 native exchanges, two callbacks, exact catalog/CIN/durable-row equality and reader 403/4103 support the bounded result. Read-only review retains 24 native/source predicates; its one raw-versus-redacted hash comparison is corrected in a separate eight-check review without changing originals or weakening redaction. STATUS/SOURCES index both reviews and their scope. Do not repeat this unchanged gate for documentation alone; preserve and commit the verified component milestone.

The actual empty catalog is a successful availability/discovery result, not useful application service consumption or full deployment. Keep those claims separate and continue with supported real app/service registration before risk-service use or official IPE. The acquired IPE actually initializes MEC from Server.StartServer; its required app/service state and native Sandbox controller's additional CouchDB/InfluxDB prerequisites must be handled explicitly. Do not add a made-up app UUID or Redis seed to obtain an attractive service count. The existing profile remains the reproducible baseline; further manager/service components require their own tests and actual evidence. Hosted/video stay excluded.

## ADR-028 — Register and consume a real FireRoute risk service through a project IPE

Date: 2026-11-16. The user requests completion of remaining local MEC work after the actual seven-check component milestone. Build the acquired native Sandbox controller with its actual CouchDB/InfluxDB prerequisites, use its server-assigned external-app ID, confirm READY through App Enablement and register/discover a real FireRoute provider. Preserve the existing successful project. A guarded build-copy patch changes only Couch auth configuration; exact upstream source remains untouched. Private generated Couch/API configuration is separate and ignored.

Use a versioned project IPE request/result contract to connect the existing actual CSE to that provider. This directly serves the application's risk scenario and can be tested with existing natural hazards, Group/fopt and independent ACKs. It does not claim execution of the much broader upstream meep-ipe/MEC033/046 lifecycle. The cost is two required native stores, controller/provider/IPE images, a persistent input/output boundary and focused tests; the judging value is real service registration/use and bidirectional oneM2M interworking. Unknown upstream placement/IPE services are not guessed. Hosted, VM orchestration and video remain excluded.

The optional port-3002 dashboard requires fresh source-correlated remote computation and full-model parity before publishing; no automatic local fallback hides a MEC failure. Invalid/expired/unavailable results expose UNKNOWN and no route. Journaling protects current-frame idempotence; a named output outbox reconciles uncertain CSE CREATE without replay. Consumer SUBs on the shared results container carry unique ownership/expiry. Cleanup verifies exact resource ID/callback/owner, issues a single standard DELETE (HTTP 200/RSC 2002), confirms actual absence, then closes the callback listener. This prevents repeated demo resets from leaving active observers targeting removed containers. Core DELETE checks retain request-ID/RSC/no-retry behavior.

MEC_SERVICES.md defines interfaces and real commands. Unit/offline/static success remains separate from actual deployment proof. The agent's actual make attempt is denied at Docker access before build/start; no runtime PASS is fabricated. The Docker-capable user run is the remaining acceptance boundary; no new approval or ETSI account is required.

ADR-028 startup correction: successful actual builds expose Couch exit 1 with empty logs before dependent services start. The version-specific upstream ownership pass can silently fail on the host-owned read-only INI. Package this nonsecret setting in a small same-version image with native ownership and writable image configuration; keep the original entrypoint and existing data volume. A small Bash status probe avoids another dependency/pull just for health checking. Add HTTP-status fixtures and include shell source in evidence identity. Do not reset volumes, change credentials or infer a new runtime PASS until the actual rerun. The official source explains the compatible fix; the exact installed-image error remains unavailable because logs are empty and inspect is denied.

## ADR-029 — Access-event occupancy as a second registered MEC service; controller room guidance (IMPLEMENTED_UNVERIFIED)

Context: the interim report (2026-10-13) made access-record occupancy on simulated data mandatory (UC-05) and put residents' own-location guidance in scope (1.2). Neither was implemented. Rubric #16 also lists multiple MEC services as unverified.

Decision:
- Generate anonymous passage events from the existing simulated residents, which stay the ground truth. Drop a declared, seeded 5% of passages.
- Store the events as AccessGatewayAE CINs.
- Have the project IPE, triggered by a request CIN that carries only references, RETRIEVE those CINs with its own ACP grant and call a second registered MEC service, `FireRoute Occupancy v1`.
- The dashboard publishes a responder-only estimate after correlation, freshness and hash checks.
- Room guidance is a controller-computed route table CIN from the same frame. It is deliberately not claimed as MEC output, so the verified risk-result contract is unchanged.
- The occupancy journal retains the newest 32 incidents and caps one incident at 5,000 batches.

Consequences:
- More oneM2M use: two new AE roles' resources, label discovery, cross-AE RETRIEVE under ACP, a second SUB pair, and resident ACP exclusion. MEC: a second app/service registration and discovery.
- Occupancy failure is isolated from route guidance and reported as UNKNOWN.
- Offline replay shows that missed internal departures leave residue in POSSIBLE zones. The headline count therefore uses exit passages (registered − detected exits), and POSSIBLE zones rank after all HIGH zones.
- Not claimed: person detection, Wi-Fi/BLE fusion (UC-06 probability correction), field accuracy, official meep-ipe, Option C.
- Docker and actual-runtime gates are pending.

ADR-029 addendum (UC-06):
- Offline replay showed the access-only estimate leaves missed-departure residue that looks like presence.
- Added a synthetic PresenceScannerAE (anonymous per-zone device counts every 10 s, declared carriage/detection/false rates) and replaced the staleness rule with a per-zone naive-Bayes probability: access-count prior updated by scans taken since the zone's last passage.
- Effect in the same replay: HIGH-level precision rises (t=60 s: 23/38 → 23/23), and residue moves to LOW.
- Trade-off: people without a detectable device can also become LOW. They stay listed when count-backed.
- The IPE now retrieves both sensor CINs per reference; the provider journal stores aligned access+presence units.
