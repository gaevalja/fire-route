# FireRoute architecture and module contracts

## 1. Status and deployment choice

This is the target design, not an installed topology. **Option C is the first MEC deployment target**: host a oneM2M MN-CSE as a MEC App on a Local ETSI MEC Sandbox MEC Host. A separate Cloud IN-CSE is the intended registrar. The option names A–D and preference are user-confirmed; the exact acquired TR-0086 revision and deployment procedures still require review. Draft TR-0077 and GR MEC-DEC 051 describe evolving interworking; they do not prove that an installed Sandbox supports every described function. See SOURCES.md and DEPLOYMENT.md.

~~~text
Personal PCs: independent clones, local real CSE, module/unit tests
                            |
                     GitHub main + PRs
                            |
Shared x86 Ubuntu integration environment (deployment-owned checkout)
  +-- Local ETSI MEC Sandbox / MEC Platform
  |     +-- selected MEC Host / MEC App lifecycle
  |     |     +-- oneM2M MN-CSE (Option C target)
  |     |     +-- FireRoute risk/controller MEC Edge Application
  |     |     +-- MEC-IPE role/placement per verified official integration
  |     +-- supported MEC Services, discovered and tested at runtime
  +-- Backend API, Frontend, integration runner, logs/monitoring

IoT simulator or Raspberry Pi AE -- Mca MQTT/HTTP --> MN-CSE
Risk controller AE <-- Mca SUB/notify --> MN-CSE
Risk controller AE -- routes CIN + GRP/fopt --> MN-CSE
Three display AEs <-- commands SUB --> MN-CSE <-- three ACK CINs
Resident/Responder browser --> authenticated Backend --> role-scoped CSE access
MEC Services <--> MEC-IPE mapping <--> MN-CSE resources <--> consuming AE
MN-CSE -- Mcc registration/remote access --> Cloud IN-CSE registrar
~~~

Cloud IN-CSE is a logical cloud role, not a claim that a cloud VM exists. A separately configured IN-CSE instance on the same permitted machine may be used only as a labeled local topology simulation. It is not evidence of cloud geography or multi-host orchestration. Raspberry Pi is an endpoint, not the default Sandbox host. Ordinary CSE containers outside MEC lifecycle remain a development topology.

## 2. Protocol and responsibility boundaries

| Component / module | Owns | Interface and exclusions |
|---|---|---|
| backend/ | Incident orchestration, authorization, read models, ACK completion | Uses onem2m/ client and domain contracts; never reimplements CSE |
| frontend/ | Resident and responder views | Versioned backend API; no privileged CSE credentials |
| simulator/ | Seeded sensors, three independent display consumers, synthetic occupants | Typed events, oneM2M requests, actual command consumption/ACK |
| onem2m/ | Request primitives/bindings, AE/CNT/CIN/SUB/GRP/ACP/discovery/registration | CSE-specific serialization/path handling stays here; no route policy |
| mec/ | Edge risk computation and MEC-IPE/service adapters | Pure graph/policy functions plus verified MEC interfaces; no generic fake MEC server |
| infra/ | Pinned runtime, network/TLS, lifecycle and deployment configuration | Local/shared profiles, secrets injection, health probes |
| tests/ | Cross-module unit/integration/E2E/fault acceptance | Mock fixtures only in unit/preview tests |
| docs/ | Contracts, ADRs, evidence and submission claims | STATUS.md is the single progress ledger |

Initial risk computation may run locally in P1 for deterministic validation. In P2 its artifact must be deployed and identified in the selected edge environment. It remains custom application logic, not a CSE standard function.

Mca connects an AE and CSE. Mcc connects MN-CSE and its IN-CSE registrar. Mp1/service APIs connect a MEC App/IPE and MEC Platform services. An IPE is a mapping bridge with a oneM2M AE identity; it is not itself a CSE, and its mapping is not automatically a standardized resource model.

Use HTTP(S) first for inspectable app requests and callbacks. Add actual oneM2M MQTT for constrained/device links in P3; broker delivery of arbitrary JSON alone is not proof of the oneM2M MQTT binding. Document the selected TS-0010 request/response topics/primitives, broker configuration and CSE CIN read-back. Transport selection follows link conditions and deployment constraints.

## 3. CSE hierarchy and Cloud registration

Target names below are illustrative, configurable resource names, not observed resource IDs or API responses.

~~~text
Cloud IN-CSE /<in-base>
  /<mn-registration>                 remoteCSE (CSR) for registered MN-CSE

MEC-hosted MN-CSE /<mn-base>
  /<registrar-reference>             CSR if created by selected registration procedure
  /<least-privilege-policies>         ACPs for individual actors
  /SmokeSensorAE
    /telemetry                      CNT; SensorEvent CINs
      /controller-sub               SUB
    /profile                        labels first; FCNT only with definition/support
  /FireRiskControllerAE
    /hazards                        CNT; versioned hazard observations
    /routes                         CNT; RouteDecision CINs
    /DisplayCommandGroup            GRP; members are three commands CNTs
      /fopt                         CSE virtual fanOutPoint
  /DisplayA_AE                      same structure for DisplayB_AE and DisplayC_AE
    /commands                       CNT; DisplayCommand CINs + display SUB
    /acks                           CNT; DisplayAck CINs + controller SUB
  /ResidentAppAE                    role-scoped application identity
  /RescueAppAE                      responder-scoped application identity
  /OccupancyScenarioAE
    /observations                   CNT; synthetic occupant summaries, restricted
  /MEC-IPE-AE                       actual IPE only
    /services                       CNT/defined supported model for service metadata
    /observations                   service results with source API/version/time
    /requests                       optional operation requests if verified mapping exists
    /results                        correlated results for supported operations
~~~

The intended MN-to-IN registration is a real Mcc registration and remoteCSE relationship, not an AE pretending to be an MN-CSE. Record CSE types, CSE-IDs, CSEBase names, registrar address, POAs, credentials and actual CSR IDs. Verify registrar reachability and remote retrieval, with permissions. Do not assert automatic mirroring of all local AEs/CINs to the cloud. Resource announcement/synchronization is a separate supported feature and not required for the first local loop. Exact registration steps must be checked against the acquired TR-0086 and CSE configuration.

Group members are the actual command CNT URIs accepted by the installed CSE. Fan-out creates a CIN at each member. Check group type/member count/consistency policy, original-originator permissions, each aggregate member result and each CIN read-back. No-route/status commands use the same channel. The initial three displays show a common exit/status; device-specific turn arrows require placement/orientation data beyond the existing fixture.

The controller subscribes to telemetry and every ACK CNT; each display subscribes to its own commands. Bring receivers up before creating SUBs, answer verification requests according to the selected release/binding, and persist accepted events before acknowledging callbacks. Deduplicate notifications and reconcile CSE state after restarts; periodic recovery reconciliation does not replace SUB evidence.

## 4. Two distinct MEC interaction paths

1. **Direct diagnostic path:** a MEC client invokes a supported service API. Capture it as DIRECT_MEC_API; this alone does not prove oneM2M interworking.
2. **oneM2M-mediated path:** an actual IPE creates/consumes CSE resources while invoking/receiving the corresponding MEC service operation. Correlate the CSE request/subscription, IPE conversion, MEC operation/notification and resulting CSE resource/consumer. Label ONE_M2M_MEDIATED only after this trace exists.

First prove a non-location service flowing MEC → IPE → CSE → consumer. If the verified official mapping supports commands, additionally prove CSE request → IPE → MEC operation → CSE result. Never invent write operations for read-only services. The provided MEC 033 IoT / MEC 046 sensor-sharing integration is a candidate to inspect, not a confirmed installed mapping. Prefer the official compatible IPE when available. If a custom bridge is necessary, document its limited mapping and label it custom rather than claiming full TR conformance.

Inventory MEC 011 lifecycle/discovery and MEC 013/033/046 plus any non-location candidates from the actual service catalog/OpenAPI. Service existence in a standard or another Sandbox release is insufficient. Network/API data in a Sandbox may be emulated even when HTTP communication with its real service process is verified.

## 5. Versioned application contracts

These are proposed FireRoute payloads inside CSE CIN content, not oneM2M primitive definitions or existing API responses. Use schema_version=1. Every message has timestamp_utc (UTC RFC3339), source (logical producer ID) and data_origin (SYNTHETIC or PHYSICAL). Use independently generated IDs and actual timestamps at runtime.

| Contract | Required fields beyond common envelope | Rules |
|---|---|---|
| SensorEvent | event_id, incident_id, sensor_id, sensor_type, location_node, value, unit, sequence | Known node/type; smoke 0–100 with unitless_0_100; temperature_celsius with degC; other fire observations require a typed schema |
| HazardObservation | incident_id, event_id, route_version, observed_node, sensor_id, sensor_type, value, unit, blocked_nodes, synthetic_smoke_threshold | P1 synthetic policy snapshot; retains prior blocks, no temperature fire threshold inferred |
| RouteDecision | incident_id, event_id, route_version, source_node, target_exit, path, blocked_nodes, reason, status, routing_cost | Monotonic version per incident; target_exit=null/path=[]/routing_cost=null for NO_VERIFIED_ROUTE; cost is synthetic graph cost |
| DisplayCommand | command_id, incident_id, event_id, route_version, action, route_exit, guidance_status, expires_at_utc | DISPLAY_ROUTE requires a known exit/ROUTE_AVAILABLE; CLEAR_ROUTE requires null/NO_VERIFIED_ROUTE; DISPLAY_STATUS uses null and UNKNOWN/STALE |
| DisplayAck | ack_id, command_id, device_id, incident_id, event_id, route_version, status | APPLIED or REJECTED with reason; bind authenticated AE/resource identity to device_id |
| OccupancyObservation | event_id, incident_id, zone_id, remaining_count, sequence | SYNTHETIC only in baseline; count is nonnegative or null=UNKNOWN; responder-only |
| MECObservation | event_id, service_id, api_version, operation, deployment_option, correlation_id, result_reference | Retain actual response reference, simulation provenance and mapping version; no guessed MEC response schema |

Do not place all correlation keys on unrelated messages as dummy values. Preserve meaningful links: sensor event → route → command → device ACK; MEC requests/results use their own operation correlation and optional incident reference.

Proposed internal interfaces, to be made executable during P0/P1:

- onem2m/ exposes register/read/create_content/subscribe/fanout/discover/policy operations, returning resource identity and both transport/oneM2M status or a typed error. Unknown responses fail visibly. Existing-resource conflicts require read-and-compare, not unconditional success.
- mec/ risk function accepts graph, active blocked nodes and source; returns computed path/exit or NO_VERIFIED_ROUTE. No CSE calls inside pure graph logic.
- backend/ consumes validated observations and owns ordered incident updates/outbox delivery; simulator/ devices reject expired/older route versions and deduplicate command_id.
- Backend API candidates: GET /api/v1/incidents/<id>/resident and /responder, plus GET /api/v1/status; authenticated role-filtered read models and optional SSE updates. Callback handlers under /onem2m/notify are separate protocol receivers. The P0 notification receiver is implemented; the listed application API endpoints are still proposals.
- Contract changes include a schema version, consuming-module review, migration note and tests under tests/contracts/. Frontend may use explicitly labeled fixtures while the real backend is developed.

P1 route slice status: IncidentStore.accept validates synthetic SensorEvents, commits per-sensor sequence/time ordering, per-incident versions, blocked nodes and hazard/route outbox entries in one SQLite transaction. Exact event replays are idempotent; conflicting reuse is rejected. A policy/graph/source fingerprint prevents silent recovery under changed rules. publish_pending reconciles deterministic named CINs via GET/CREATE/read-back and marks only decision persistence complete. A partial/ambiguous write stays pending; there is no blind POST replay. Actual P1_ROUTES passed; its application entrypoint coordinates notification consumption for the test. SQLite is application recovery state, never a CSE substitute.

The verified isolated P1_GROUP slice reuses this route flow and opts into device policies/callbacks. Three spawned Python processes each own an actual AE-ID, command SUB, durable display state, duplicate/version/expiry checks and ACK outbox. The coordinator uses a real Group of the three commands CNTs, checks outer OK/member CREATED and reads every member CIN. Local members use actual CSE-relative CNT IDs, matching the canonical mid returned by ACME; changed/duplicate identities remain errors. It consumes ACK SUBs with a decoder bound to each actual subscription, then validates device/event/incident/version/command and actual ACK CIN read-back. A successful aggregate never creates synthetic ACKs in the controller. Local ports 8000–8003 stay inside the runner's Compose network; spawned processes are simulated devices, not physical hardware or MEC hosts.

guidance_status makes command nullability explicit in the first executable display schema_version=1 contract. No existing implemented display payload/state needs migration; older proposed examples without this field must be updated before use. Existing SensorEvent validation and its default notification decoder are preserved. Typed command/ACK inboxes use command_id/ack_id as durable dedup keys while preserving event_id correlation in content; the legacy SQL event_id column is an internal message-key column, not a standard resource attribute.

Commands and ACK policies grant their writer CREATE/RETRIEVE; the reader has RETRIEVE plus CREATE restricted to SUB children through acod.ty=3/chty=[23]. Actual P1_GROUP verifies that the controller cannot create device ACK CINs, a device cannot create command CINs/another device's ACKs, and a resident cannot fan out. Baseline header originators are not authenticated identity proof. Full service resume/dispatch recovery, periodic controller STALE guidance, role APIs/UI and MEC remain pending.

## 6. Synthetic policy and recovery

Use preserved fixtures/building_3f.json, an undirected positive-weight graph. Baseline F3_ROOM1 prefers EXIT_A; block F2_A at synthetic index >=70 and recompute to EXIT_B. Dijkstra or an equivalent deterministic algorithm is sufficient. Temperature collection is supported without inventing a certified fire threshold. A temperature-driven blocking rule needs a separately documented demo policy/test.

Maintain blocked nodes across active sensor observations. A quiet/stale sensor does not erase hazards. Clear hazards through a documented scenario reset or newer explicit clear event, with ordering tests. Missing/stale data produces UNKNOWN/STALE and invalidates current guidance according to the scenario policy. No-route produces a new CLEAR_ROUTE command so devices remove prior arrows.

P0 must declare scenario values for sensor TTL, maximum clock skew, ACK timeout, retry interval/count and retention. Snapshot them in run metadata. Per-sensor sequence and event IDs prevent duplicate/late events; route versions and command IDs protect devices. Use durable deduplication/outbox state or CSE-backed reconciliation; do not assume exactly-once transport delivery. Bound partial fan-out retries and never invent ACKs during recovery.

## 7. Authorization, privacy and measurements

Actors: bootstrap admin (setup only), individual sensors/displays, controller, resident proxy, responder proxy and IPE. Sensors create only their telemetry; displays read their commands and create only their ACKs; controller writes hazards/routes/group commands and reads ACKs; residents read approved route/status; responders additionally read diagnostics/synthetic occupants; IPE accesses its mapped resources. Test policy inheritance and group-member authorization in the selected CSE. Authentication must establish the claimed originator; a user-supplied originator header alone is insufficient identity proof.

Transport credentials remain server-side. Restrict callbacks to known subscription/resource paths and validate event identity/provenance. Do not publish raw resident data, tokens or private network details in evidence.

Record event generation → CSE CIN → notification → compute → route CIN → fan-out → each device application/ACK. E2E_all_acks_ms ends at the latest of three matching device ACK timestamps; incomplete sets are not successful latency samples. Also measure source-runner monotonic event submission → observed third ACK to avoid silently comparing unsynchronized host clocks. TEST_PLAN.md defines sample counts, clock metadata and reporting.
