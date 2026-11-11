# FireRoute acceptance tests and evidence

## 1. Status, layers and baseline

Test states: NOT_RUN, PASS, FAIL, BLOCKED. Implementation states are separate: NOT_STARTED, IMPLEMENTED_UNVERIFIED, VERIFIED, BLOCKED. A test passes only after execution with recorded assertions and output. Missing infrastructure is BLOCKED/NOT_RUN with a reason, not PASS; a deliberately excluded optional test is recorded as DEFERRED scope, not a successful test.

At this documentation revision all product tests below are NOT_RUN. Tests, harnesses and setup commands do not exist yet. Mock tests prove only unit/contract behavior; real-CSE and real-MEC gates require actual processes/endpoints and sanitized request/response evidence.

Retain existing T01–T15 IDs and add explicit deployment/occupancy/temperature/contract cases. Phase mapping is in ROADMAP.md; F IDs refer to PRD.md.

## 2. Cases and observable success criteria

| Test / requirements | Inputs / preconditions | PASS assertions | Layer / phase |
|---|---|---|---|
| T01 / F03 | Preserved graph, source F3_ROOM1, no blocked nodes | Computed path reaches EXIT_A, cost 13, all edges exist | Unit / P1 |
| T02 / F04 | Synthetic smoke index 90 at F2_A, threshold 70 | Risk state blocks F2_A; computed path reaches EXIT_B at cost 16 and excludes F2_A; actual route record agrees in integrated subcase | Unit + real CSE / P1 |
| T03 / F10 | Block both F2_A and F2_B | NO_VERIFIED_ROUTE, target_exit=null, path=[]; no fabricated exit | Unit / P1 |
| T04 / F09 | Replay event_id, duplicate notification, old sequence/timestamp, restart and replay | No extra incident/route version/effective command application; older work never replaces newer state | Unit + integration / P1, restart expansion P3 |
| T05 / F01–F02 | Running real CSE/receiver; create AE/CNT/SUB; create telemetry CIN | Actual resource IDs/tree/CIN read-back; SUB verification completed; callback matches source event/resource; request/oneM2M status captured | Actual CSE / P0 |
| T06 / F06 | Actual GRP of three commands CNT members | Real fopt operation; inspect all member results and read three matching CINs; a member error is not treated as full success | Actual CSE / P1 |
| T07 / F07/F10 | Three independent consumers and actual commands SUBs | Distinct authenticated devices apply same command/version and write ACK CINs; three duplicates from one device never count as three; stop one consumer and completion remains incomplete | Actual CSE + display simulators / P1 |
| T08 / F11 | CSE MQTT binding/broker and HTTP(S) app | oneM2M request/response correlation over both bindings; sensor MQTT operation creates real CIN; app HTTP(S) reads it | Actual CSE/broker / P3 |
| T09 / F12 | Least-privilege actor policies, authentication and deployment TLS | Intended operations succeed; unauthorized route/command/ACK writes denied by CSE, resources unchanged; originator identity misuse fails at auth boundary; inspect TLS verification | Actual CSE/security / P3, baseline P1 |
| T10 / F13/F18 | Known labeled resources; supported FCNT specialization where claimed | Label query returns correct resources; separate FCNT definition/query/app-use subcase; semantics/SDT needs its own compatible model/query test | Actual CSE / P3, advanced optional |
| T11 / F14 | Selected actual MEC service, supported IPE mapping and CSE consumer | Non-location result/notification → IPE conversion → actual CSE CIN/SUB → consumer, correlated and validated; direct-only API call cannot pass; add reverse-operation/multi-service subcases only where supported | Actual MEC + CSE / P2 |
| T12 / F09–F10 | Stop consumer/controller/CSE link or disconnect Pi/network, then recover | Pending/STALE/UNKNOWN within configured budgets, retries bounded, old directions not replayed; reconcile SUB/outbox/ACK state; report actual outage/loss | Integration/fault / P3; basic status P1 |
| T13 / F15 | Repeated real E2E with declared seed/topology/timeout and clocks | Recompute latency samples/counts/p50/p95 from raw logs; identify incomplete runs; >=30 measured attempts after 5 declared warmups is team target, not an executed count | Measurement / P3 |
| T14 / F16 | Actual second CSE and optional automated policy trigger | Restore state, SUB and security context; report trigger, interruption, sent/received/lost event counts; manual switching is preliminary only | Actual dual CSE / optional |
| T15 / F08/F12 | Resident/responder authenticated roles | Both agree on incident/version; resident backend/CSE access cannot read responder diagnostics or occupant records; direct API requests also denied | Actual CSE + API/UI / P1 |
| T16 / F22 | Actual Local Sandbox and MN-CSE MEC App artifact | Verify actual host/app lifecycle/placement, version/digest and authorized guide-based onboarding; distinguish container/VM/external/emulated paths; record C vs actual fallback option | Actual MEC deployment / P2 |
| T17 / F22 | MN-CSE and intended Cloud IN-CSE registrar | Real Mcc registration, registrar CSR read-back, CSE types/IDs and authorized remote retrieval; disconnect/reconnect observed; same-host cloud role labeled simulation | Actual two CSEs / P2 |
| T18 / F21 | Synthetic zone/count observations, then missing/expired update | Responder-only, SYNTHETIC label and timestamp; UNKNOWN for missing count, never silently zero; resident access denied | Contract + CSE/API/UI / P1 |
| T19 / F20 | Typed synthetic temperature and smoke, malformed units/node/range | Accepted valid CINs preserve values/units/provenance; invalid inputs rejected visibly; temperature alone does not imply a certified hazard threshold | Contract + actual CSE / P1 |
| T20 / F10 | Previously displayed valid route, then no-route or stale guidance | New CLEAR_ROUTE/DISPLAY_STATUS reaches all available devices; old direction removed; matching ACKs or explicit incomplete status; expired/older command not applied | Actual CSE + simulator/UI / P1 |
| T21 / F09/F23 | Versioned event/API contracts and per-run resource namespace | Producers/consumers agree on IDs/nullability/status/error fields; namespace collisions rejected; fixture endpoints/weights valid; example schema validated | Unit/contract / P0–P1 |

## 3. Actual CSE verification procedure

1. Record implementation/package/image version, digest/commit, CSE type/ID/base, release, binding, public nonsecret config, producer identities and run resource namespace.
2. Start reachable controller/display receivers before SUB creation. Capture verification requests and required binding responses; verify the selected release's headers/encoding rather than copying guessed values.
3. Create/retrieve AEs/CNTs/SUBs. On name conflicts, compare actual existing resources and ownership; do not convert an arbitrary conflict into success.
4. Publish an actual generated SensorEvent; read back the created CIN and capture the corresponding notification. Controller decisions must reference that event.
5. Read hazard/route CINs, issue a real GRP/fopt command, inspect each aggregate member status and each commands CIN.
6. Collect independent ACK CINs and validate producer/resource identity, command_id, incident_id, event_id and route_version. A returned HTTP success code alone does not prove oneM2M or device success.
7. Replay/stop/recover within declared test budgets and compare resulting resources/state. Cleanup only the run's owned resources after saving evidence; never reset a shared CSE.

P0 must add exact executable install/start/bootstrap/test commands and selection markers for actual CSE/MEC tests. Candidate future commands are python -m pytest tests/unit, python -m pytest tests/integration -m real_cse, and python -m pytest tests/e2e; they are not runnable commands of the current starter. Integration selection must fail/report BLOCKED when required configuration is missing, without silently substituting mocks. Tests can run in a disposable local CSE and an authorized shared environment; record which.

## 4. MEC verification procedure

Record acquired TR-0086 revision, relevant TR-0077/GR MEC-DEC 051 revision, Sandbox deploy branch/commit, lifecycle support, app/host identity, actual CSE registration and IPE implementation/model. Inventory enabled services and OpenAPI versions; record supported/unsupported operations for MEC 013/033/046 and chosen non-location services.

Capture direct API probes separately from oneM2M-mediated operations. For T11, correlate the original MEC response/notification, IPE mapping, CSE resource and consuming app. For supported reverse operations, start at an actual CSE request resource and trace the resulting MEC operation and CSE result. Do not invent payloads, endpoints or support merely to complete a trace.

T16 verifies placement/lifecycle; T17 verifies registrar registration; T11 verifies interworking. All three are needed for the selected Option C story. A real Sandbox API can operate over emulated network data: record both facts. A fallback records the actual option and changed gates; it does not produce an Option C PASS.

## 5. Fault timing and latency definition

Declare sensor TTL, allowed clock skew, ACK deadline, retry schedule/count, request deadline and namespace before execution. These are team demo parameters, not safety guarantees; P0 records selected values and boundary tests. Assert status changes and retry limits against those configured budgets, allowing declared test scheduling tolerance.

For each command, record producer generation, CSE write/read, SUB arrival, compute start/end, route write, fan-out start/member responses, device apply/ACK creation, and observer ACK arrival. Use correlation IDs and actual UTC timestamps; measure local durations with a monotonic clock.

- E2E_all_acks_ms = latest of three matching device ACK timestamps minus source event generation timestamp. Use only when host clock offsets/uncertainty are recorded and acceptable for the claimed resolution. Otherwise report this cross-host metric unavailable, not a number inferred from unsynchronized clocks.
- Observer_all_acks_ms uses one test coordinator's monotonic clock from initiating the sensor emission until observing the third actual matching ACK. This includes trigger/observation overhead and is a different metric; do not relabel it as synchronized device-to-device latency.
- Missing/rejected/late ACK sets are incomplete/failures, excluded from successful-latency percentiles but included in attempted/completed/incomplete/failure counts. Publish success ratio and timeout to avoid hiding slow failed runs.
- Report warmups, attempted N, valid sample N, synthetic/physical input, actual CSE/MEC mode, topology, load and clock method. Team sampling target: 5 identified warmups then at least 30 measured attempts. A smaller run is an explicitly limited result.
- Sort valid samples; use declared nearest-rank percentile x[ceil(p*N)-1] for p=0.50 and 0.95. N=0 has no percentile. Preserve raw samples and analysis command; make recalculation agree with the reported rounding.

No latency values or pass counts are available yet.

## 6. Evidence format and claims

Use evidence/YYYYMMDD-HHMMSSZ/ per executed run:

| Artifact | Required contents |
|---|---|
| meta.json | Actual versions/digests, guide/deploy revisions, topology/host architecture, namespace, modes, deployment option, network emulation, UTC/clock method, nonsecret config; actual Git commit or null plus source-manifest hash when Git is unavailable |
| requests.jsonl | Sanitized actual request/response method/path, request ID, HTTP/RSC, resource IDs, member outcomes, timing and correlation |
| events.jsonl | Producer/consumer hops, sequence/version, provenance, command/ACK identity and timing |
| tests.txt | Exact executed commands and original output; no edited or fabricated PASS strings |
| summary.json | Test states, attempted/completed/incomplete/failure counts; latency formula, valid N and percentiles only when calculable |
| deployment.json | Actual option, host/app IDs/artifact digest, CSE registrar relation, supported APIs and IPE mapping version for MEC claims |

Redact passwords/tokens/keys and personal data before publication; keep useful status/resource correlation. .gitignore excludes raw evidence by default. Curate sanitized public artifacts explicitly and reference them from STATUS, article and video. Never publish secret-bearing raw output merely to prove reproducibility.

## 7. Phase and submission gates

P0: T05 and foundational T21. P1: T01–T07, T15, T18–T20 and live two-view agreement; record integrated subcases. P2: T11/T16/T17 for the actual selected deployment. P3: T08–T10/T12–T13 and regression checks. T14 and advanced rubric tests are conditional.

P4 reviewers reproduce from a fresh environment and reconcile source, test evidence, article/video/presentation claims and known gaps. No feature passes based on a screenshot or this document. An explicit fallback/omission preserves truthful claims but does not fulfill a missing original requirement.

## 8. Documentation-only review

For this revision, check all relative Markdown links, balanced code fences, unique F01–F23/T01–T21 definitions, 17 rubric sections, consistent phase names/dates, and absence of old branding. Compare non-Markdown file hashes and source-tree inventory against the pre-edit snapshot. Confirm no source/config/fixture change, no duplicate root STATUS, no new service implementation or deployment. Record results in STATUS only after execution; this review cannot mark product tests PASS.
