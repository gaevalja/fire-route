# Selected FireRoute scenario: fire_evac

## Authority and implementation boundary

On 2026-11-12 the user selected `C:\Users\lilkid\Downloads\fire_evac` as the scenario source. Its README, configuration, engine, UI and tests were inspected. The seven original files are preserved byte-for-byte under `simulator/scenarios/fire_evac/`; `manifest.json` records SHA-256 hashes. That repository snapshot makes the source reproducible without access to a developer's Downloads directory. External originals are unchanged. The supplied folder has no license declaration; retain its provenance and resolve publication attribution in P4.

This is the selected submission scenario. The existing `fixtures/building_3f.json`, three-floor dashboard and actual T05/routes/Group/dashboard evidence remain regression checkpoints. The selected source-frame/controller/CSE core and role HTTP baseline gates have passed. The natural-hazard actual CSE/core extension has also passed, while comprehensive browser/fault checks remain open. The user's latest direction is to implement both modes and choose missing dimensions/population assumptions; EVACUATION_MODEL.md defines that added layer. No MEC service is connected. Opening the supplied standalone index.html still runs the original local maker, not the CSE dashboard.

## Rules taken from the source

| Item | Selected behavior |
|---|---|
| Building | Floors 1–10 plus floor 11 roof; 162 hazard zones in total |
| First floor | Four rooms, one lobby, two stair zones and one elevator zone: eight hazard zones |
| Floors 2–10 | Nine rooms, five corridor segments, two stair zones and one elevator zone per floor: 17 zones per floor |
| Roof | One zone, F11-ROOF, linked to both floor-10 stairs |
| Entrances | Two drawn first-floor entrance boundaries; they are not hazard zones or executable evacuation exits in this engine |
| Ignition | One of 85 rooms, chosen by the seeded generator; initial fire index 18 |
| Wind | One fixed speed from 1, 5, 10 or 15 m/s; default 5; no wind direction |
| Quantities | Fire and smoke indices 0–100; illustrative relative values, not temperature, ppm or measured fire data |
| Fire transport | Undirected connections; vertical transport only through stairs, upward and downward; no elevator shaft connection |
| Smoke transport | Floor corridor smoke is shared by all five segments; vertical transport through stairs is upward only; no elevator shaft connection |
| Smoke cap | At most local fire + 30, capped at 100; corridor cap uses that floor's average corridor fire + 30 |
| Time | Simultaneous one-minute updates based on previous state, displayed by one-second interpolation; collapse/events/end become committed at minute boundaries |
| Collapse | Probability uses previous fire level, starts at configured threshold 55, maximum per-minute probability 0.001; total at most two collapsed zones; stairs/elevators never collapse |
| Collapse effect | Blocks the intended human traversal; does not remove fire/smoke transport edges or stop the engine |
| Termination | All 162 hazard zones, including stairs/elevators/roof, reach fire 100; this does not mean evacuation or rescue succeeded |
| Tunable values | The preserved config.js is authoritative for exact coefficients and relative sizes; lobby/roof size 5 are provisional source values |

Zone IDs remain unchanged: F1-L, F1-R1…R4, F<n>-R1…R9, F<n>-C1…C5, F<n>-SA/SB/E and F11-ROOF. Do not rename them into the old F2_A/F3_ROOM1 namespace or silently reduce the building to three floors.

The original UI runs one simulated second every 100/40/10 ms (10×/25×/100× playback). A playback change does not change physical-model coefficients. Same seed, wind, configuration and engine revision reproduce the same simulated state.

## Integration contract to implement

1. Keep config.js/engine.js behavior unchanged. Run the authoritative engine in one controlled simulator process; browsers receive state rather than starting independent authoritative random runs. Any future source update needs a new recorded checksum/revision and regression execution.
2. Keep make demo-up/p1-dashboard as legacy regressions. The new commands are make p1-scenario (CSE/core gate), make p1-scenario-dashboard (HTTP/CSE gate), and make demo-scenario-up (persistent ten-floor dashboard on 127.0.0.1:3001). Source checks alone do not verify those runtime profiles.
3. Publish a versioned FireRoute ScenarioFrame as an actual CIN under the simulator AE's telemetry container. This is a custom application payload, not a new oneM2M resource type. Proposed fields: schema_version, profile_id, source_manifest_sha256, event_id, incident_id, sequence, seed, wind_mps, simulation_second, timestamp_utc, source, data_origin=SYNTHETIC and zones containing the 162 current zone_id/fire_index/smoke_index/collapsed values. Static topology is identified separately. Validate complete unique zone coverage and ranges before acceptance.
4. Keep simulated time separate from actual emission/observation UTC and monotonic transport timing. Accelerated replay must not cause sensor TTL to compare simulation seconds with wall time. Repeated/old frame IDs must not create extra route versions.
5. Publish a complete frame atomically before recomputing. Avoid mixing zones from different simulated seconds or issuing one Group command for every individual zone. Choose and measure emission/backpressure/ACK budgets before supporting accelerated live replay. The original one-second simulation step remains intact.
6. Extend the typed SUB decoder/controller to validate a frame and commit one consistent hazard state/decision. The current SensorEvent decoder and IncidentStore.accept do not already support this frame. Drop private `_anchorZones`, `_minuteTarget` and rngState from public/CSE payloads; those include precomputed future minute state, not current observations.
7. Define a separate evacuation graph/policy, then exclude collapsed/blocked traversal nodes and compute paths to explicitly modeled external exits. Fire/smoke transport links are not automatically approved human movement links. Store decisions as real CSE resources and reuse actual Group/fopt plus independent ACK producers.
8. Extend both role views to floors 1–11 and actual correlated CSE frames/routes. Preserve resident/private diagnostic boundaries, stale/no-route behavior and explicit simulation/MEC labels. Synthetic occupants remain a separately identified source.

No Node runtime is installed in the Python image. Host Node 24.22.1 (.node-version) runs simulator/export_scenario.cjs using built-in modules and the unchanged engine, creating an ignored bounded .runtime/fire-evac-trace.jsonl. Python validates each current trace state and stamps real emission UTC only when publishing to the actual CSE. This is explicit synthetic source replay. Exporting future trace rows does not make them current observations or expose them through the browser API. Exhaustion pauses the app and allows guidance to expire; it is not automatically the fire-model terminal state.

## Added assumptions and remaining limits

- The user authorized assumptions because no actual dimensions/population were supplied. The separate evacuation layer uses two people per room (170), seeded individual speeds/departure delays, one-second movement and finite shared link capacities. Fixed guidance defaults to F7-R3; fixed queries never move the population. These defaults are editable in fixtures/evacuation_assumptions.json.
- The added movement graph connects the two source entrance markers to F1-L as EXIT_A/EXIT_B. It has 164 nodes (162 hazard zones plus two external exits), isolated elevators and a roof that is not an exit. This is a project assumption, not a modified source transport graph.
- Geometry, travel costs, heuristic smoke slowdown, and fire>=55/smoke>=70/collapse blocking are uncalibrated demo policy. No measured visibility/toxic dose, accessibility guarantee, assisted rescue or injury/death outcome is implemented. See EVACUATION_MODEL.md for conservation, queuing and in-transit blockage semantics.
- Collapse does not imply that occupants disappear, become zero or are rescued. The engine has no human simulation or reinforcement-learning rewards.
- Fire index cannot be converted to degrees Celsius. Typed temperature samples, if retained, need their own labeled generator/device source.
- The engine has no oneM2M, MEC, routing, Group, ACK or role security integration. Each hop needs its own real evidence.

## Gates

| Gate | Completion evidence | Current state |
|---|---|---|
| T22 source/engine | Seven hashes match source; original four test groups execute; seed/wind/topology/direction/caps/time/end checked | Imported; executed source checks PASS, exact output in STATUS |
| T23 frame/CSE | Actual 162-zone CIN read-back and SUB; no future-state exposure; ordering/clock/provenance | Actual core baseline PASS for 181 frames; negative ordering subcases have unit coverage; broader live fault coverage remains pending |
| T24 integrated scenario | Declared movement/exit policy, alternatives/collapse exclusion/no-route, Group/ACK and role views | Actual core, HTTP baseline and natural-hazard core PASS: blocked-original-path alternative, collapsed-node exclusion, no-route and stopped-display incomplete ACKs verified; full restart/fault and hazard browser QA remain incomplete |

T05/routes/Group/dashboard remain regression commands for the three-floor checkpoint. T22 is an engine-level test and cannot pass T23/T24, MEC deployment or actual evacuation claims.

Run `make test-scenario` for the preserved source tests. Open `simulator/scenarios/fire_evac/index.html` for the original standalone preview; browser rendering is separately unverified here. No source scenario test is reported as a real-CSE integration run.
