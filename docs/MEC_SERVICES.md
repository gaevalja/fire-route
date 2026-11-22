# Local FireRoute MEC service and project IPE

Startup follow-up: the user now completes the image pulls/builds, but CouchDB exits 1 before any pipeline gate. The host-owned read-only config bind is removed: a small image copies the same single-node setting with native ownership/mode and keeps the upstream entrypoint and named data volume. Its private /_up probe uses the image's existing Bash, without a curl dependency. Rerun make p1-mec-services; actual corrected startup is still pending.

This increment implements native app/service registration, an independent risk provider, project-specific oneM2M/MEC interworking and an optional authenticated dashboard. The initial actual startup fails at CouchDB; corrected-image execution is pending. Implementation/unit results do not inherit the earlier seven-check component PASS. The upstream meep-ipe, MEC033/046, platform-controlled VM placement and Option C are not claimed.

~~~bash
cd /home/lilkid/fire-evac/fire-route
# Native registration/discovery, natural hazards through actual CSE/IPE/MEC/
# Group/independent device ACKs, then role/movement/expiry HTTP dashboard checks.
make p1-mec-services

# Normal interactive use: http://127.0.0.1:3002/
make demo-mec-up
# Read the existing role codes privately from .runtime/access-codes.json.
# Press 초기화 if the expiry test left the app paused with stale observations.

make mec-services-logs
make mec-services-down
~~~

The separate fire-route-mec-services project retains its named volumes. Only loopback MEC API 8091 (MEC_SERVICES_PORT) and dashboard 3002 (MEC_DASHBOARD_PORT) are published. Redis/CSE/CouchDB/InfluxDB/provider/IPE remain private. The previous component profile on 8090 and default dashboard on 3001 remain separate.

The official Sandbox controller allocates the real app ID; App Enablement confirms READY and allocates the service ID. Registration saves those actual assignments and verifies native read-back. An uncertain CREATE is recorded before submission and reconciled through real GET results; absence/ambiguity blocks instead of replaying POST. No app/service/scene record is manually seeded into Redis. The native controller accepts nodeName mep1 as an external-app label; this does not demonstrate an instantiated host, VM or network-emulation topology.

Provider POST /v1/frames authenticates a private access key, validates the existing ScenarioFrame and computes the unchanged evacuation model. A private SQLite journal commits each frame/result atomically and reconstructs model state on restart. Exact current-frame duplicates do not move people twice; conflicting, skipped, old or expired frames fail. Unit coverage verifies reconstruction; actual crash recovery remains untested. The cache retains 16 incidents and reconstructs older ones. A 20,000-frame PoC journal budget fails closed without deleting data; this single-provider profile is not a multi-replica database design.

The project IPE maps actual request CIN/SUB → discovered ACTIVE provider HTTP → correlated result CIN/SUB. Requests cannot select arbitrary URLs or commands. Result fields bind request/source IDs, incident, version, policy hash, full-model hash, app/service identity and expiry. Result resources omit per-person records. Existing responder-only diagnostics keep their role restrictions. Producer/IPE/reader ACPs deny cross-role writes. The persistent output outbox reconciles a named CIN after an uncertain CREATE and never blindly replays it. A result expiring before publication becomes UNKNOWN with no route. Consumers verify source freshness and expiry again.

Consumer observer subscriptions carry unique ownership and one-hour expiry. Normal close verifies the exact SUB ID/callback/owner, deletes that SUB once and confirms absence before removing its listener. This prevents repeated resets/tests from leaving active callbacks to removed containers. An unconfirmed cleanup is recorded and cannot turn the gate green.

The optional dashboard has no provider key or direct provider-network connection. It submits through actual CSE resources, requires a fresh matching MEC result, compares the full-model hash and publishes the verified decision through the existing Group/device path. Local model parity supports verification and private presentation; it is not a fallback when MEC fails. An incomplete MEC operation degrades guidance and requires explicit reset. Paused observations still expire after 30 wall-clock seconds. MEC 경유 계산 확인 appears only for a current verified result. Existing default-mode behavior and the supplied fire engine stay unchanged.

Native controller initialization requires CouchDB/InfluxDB. [Apache image documentation](https://github.com/apache/couchdb-docker/blob/main/README.md) confirms couchdb:3.5.2.1/admin environment configuration; the [official InfluxDB 1.8.10 image](https://hub.docker.com/layers/library/influxdb/1.8.10/images/sha256-93ee9cd349882c18e69980d85fe4d2d0667c9dcbdd611c019bd1f7816884aa81) matches the upstream v1 HTTP client. Reviewed pins are not installed-version/pull proof. The only controller build-copy patch replaces two hardcoded Couch auth literals with environment reads; exact-context tests reject unexpected upstream changes. The acquired Git tree and prior component stage stay unchanged. Preparation creates separate private mode-0600 .runtime/mec-couch.env and mec-risk.env without printing values. No keys enter Git or the build context. Private HTTP/development CSE header identities remain explicit limitations.

The actual gate must verify native registration/nonempty discovery, request/result read-back and both SUB paths, four natural hazard stages, model parity, Group/fopt/three independent display ACKs, duplicate handling, expired-input UNKNOWN and real ACP denials. It then checks authenticated roles, moving residents, private access and expiry on the MEC dashboard. Browser rendering, official-IPE/VM/Hosted support are separate results. See [STATUS](STATUS.md), [TEST_PLAN](TEST_PLAN.md) and [LOCAL_MEC](LOCAL_MEC.md).

## Second registered service: access-event + Wi-Fi/BLE occupancy estimate (2026-11-19, IMPLEMENTED_UNVERIFIED)

Scope: PRD F26/F27, from the interim report's UC-05 (access-record occupancy on simulated data), UC-06 (Wi-Fi/BLE probability correction and priority list) and resident guidance from their own location (1.2). Docker/CSE/MEC gates have **not** been run for this increment; nothing below is an actual runtime PASS.

Flow (MEC dashboard 3002 only; the 3001 profile and the 12-check E2E keep their previous behaviour):

1. Two synthetic sensors read the simulated residents (the ground truth). Assumptions are in `fixtures/occupancy_assumptions.json` (ASSUMED_NOT_CALIBRATED).
   - Access gateway (`simulator/access.py`): last-reached-node changes become anonymous passage events; a seeded, deterministic 5% are dropped.
   - Presence scanner (`simulator/presence.py`): every 10 s it publishes anonymous per-zone device counts. 90% of residents carry a device (fixed per resident), each scan detects a carried device with probability 0.9, and every linked zone reports a false device with probability 0.02.
   - No resident or device ID is published.
2. At publish, two CINs cover the frames since the last publish: one in `AccessGatewayAE/passages` and one in `PresenceScannerAE/scans`. Each ACP lets the sensor AE write; controller, responder and the project-IPE AE read; residents get nothing. Both containers carry `sensorType:*` and `<kind>:<namespace>` labels; the session verifies them with admin label discovery (`access-discovery.json`, non-fatal).
3. The dashboard's producer AE creates a request CIN in the IPE's `occupancy-requests` container. The request holds only references (path, resource ID, canonical SHA-256) to both sensor CINs.
4. The IPE's `occupancy-sub` notification makes the IPE RETRIEVE each referenced CIN with its own AE identity, verify ID/hash/contract and alignment, discover `FireRoute Occupancy v1` through the MEC service registry, and call `mec-occupancy:8082/v1/batches`.
5. The result CIN in `occupancy-results` reaches the dashboard through a second observer SUB. The dashboard checks correlation, freshness (30 s) and the estimate hash, then writes `controller/occupancy-estimates` (responder-only). This publication adds the priority list and a comparison with the simulated ground truth for each level.
6. Room guidance (F27): every publish also writes `controller/zone-routes` (resident and responder readable): routes from all 85 rooms, computed by the controller from the same frame and blocked set. This is **not** labelled as an MEC computation. The resident's room choice stays in browser storage and is sent only as a path parameter.

Estimator (`mec/occupancy/estimator.py`, naive Bayes per zone):
- Access count sets the prior: 0.8 if the count is ≥1, 0.05 otherwise.
- Scans taken since the zone's last passage (at most the last 3) update it: P(scans | occupied by n) sums over how many of the n people carry a device; P(scans | empty) uses only the false-detection rate.
- Levels: HIGH ≥0.7, POSSIBLE ≥0.4, otherwise LOW. Count-backed zones are always listed, LOW included; zones seen only by the scanner need POSSIBLE.
- The headline remaining count is registered total − detected exit passages; the zone sum is reported separately.
- Limitation: a person without a detectable device cannot be told apart from residue of a missed departure, so either can be LOW.

Failure isolation: an occupancy failure never fails route publication. Unacknowledged evidence is resubmitted on the next publish (the provider returns stored results for identical units). After 32 pending batches the estimate stays UNKNOWN until reset. The view shows an estimate only when it matches the current route version.

Provider journal retention: the newest 32 incidents are kept and one incident is capped at 5,000 batches. This avoids the global-count stop that the risk journal still has (20,000 frames across all incidents).

Offline replay of the original seed-59/wind-5 trace (729 frames, publish every frame, no CSE/MEC). Figures are "actually occupied / zones at that level":

| Time | HIGH, access only | HIGH, with scans | Missed-departure residue |
|---|---|---|---|
| t=60 s | 23/38 | 23/23 | — |
| t=120 s | 16/19 | 15/15 (1 true zone in LOW) | — |
| t=240 s | — | 3/5 (2 true in POSSIBLE, 1 in LOW) | — |
| after everyone exits | — | — | was 26 POSSIBLE zones; now 24–26 LOW, 0–2 transient POSSIBLE from false detections |

- Headline count: 10 after everyone exits (10 exit passages missed).
- Size and time: largest presence CIN 4 KB at 30 s steps; estimator about 0.3 ms per update.

Gates still to run on the Docker host:
1. `make p1-mec-services` (now also builds/starts `mec-occupancy`).
2. `make demo-mec-up`, then a 3002 browser check of room selection and the responder estimate card.
3. Confirm in the evidence: `access-discovery.json` verified for both containers, `access-batches.jsonl` with presence CIN IDs, `mec-occupancy.jsonl` ACCEPTED rows, and a resident 403 on both sensor containers and on `controller/occupancy-estimates`.
