# P1 role API and live dashboard contract

Working branch feature/p1-role-dashboards is based on verified checkpoint 80f6e87. This is a local Docker/real-CSE slice; no Sites hosting, shared deployment, main merge or new MEC claim is intended. The API is a FireRoute application API, not a oneM2M binding.

Scope: the first endpoint table describes the legacy three-floor service on port 3000. A separate selected ten-floor service on port 3001 is implemented below and requires its own actual gates. Existing fire_a/fire_b actions belong only to the regression service; they are rejected by the selected seeded-engine service.

Use the current Python standard-library runtime and buildless HTML/CSS/JavaScript. No framework dependency is needed for two read-only role views and a bounded synthetic-scenario controller; the earlier FastAPI/Vue stack was a proposal. Preserve the verified protocol/graph/device modules and original fixture. Local preview/browser QA is unavailable in the agent sandbox (AF_INET denied); do not infer browser success from source checks.

API sessions use generated, separate role access codes, a hashed credential file and expiring HttpOnly/SameSite=Strict cookies. Codes are written only to ignored private files with mode 0600 and never printed or committed. CSE originators/admin remain server-side. This local HTTP API session protection does not complete CSE-originator authentication/TLS. Public/shared deployment remains blocked on that separate security profile.

| Endpoint | Access / behavior |
|---|---|
| GET /healthz | Minimal process readiness, no secrets or resource IDs |
| POST /api/v1/session | Same-origin JSON role/access_code; bounded login attempts; creates role-bound session |
| GET /api/v1/session | Current authenticated role |
| DELETE /api/v1/session | Same-origin logout; revokes current session |
| GET /api/v1/status | Authenticated runtime/active incident; READY is not a fresh CSE connection assertion |
| GET /api/v1/building | Authenticated preserved synthetic graph |
| GET /api/v1/incidents/{id}/resident | Resident or responder; actual role-scoped CSE route/public-status reads only |
| GET /api/v1/incidents/{id}/responder | Responder only; additional actual hazards/diagnostics/occupancy reads |
| POST /api/v1/scenario | Responder only, same-origin JSON action: fire_a/fire_b/stop_display_c/reset/pause/resume |

Resident response fields: schema_version, incident_id, route_version, guidance_status, approved route (source_node/target_exit/path) or null, delivery (state/ack_count/expected_ack_count), observed_at_utc, verified_at_utc, SYNTHETIC provenance, actual CSE connection result and MEC=UNAVAILABLE. No occupants, raw sensor diagnostics, device identities or private resource paths are exposed. Responder additionally receives bounded sensor/device/risk diagnostics and timestamped synthetic occupant counts; missing/old counts are null/UNKNOWN.

Route and public-status correlation must match incident/event/version. Transitional mismatch returns PENDING with no directional route. Expired input produces STALE and no route; unavailable CSE produces UNKNOWN/503 and no route. NO_VERIFIED_ROUTE always has null exit/empty path. Do not serve cached directions as fresh. The graph is a schematic topology, not an actual building plan or safe-evacuation guarantee.

Dashboard resources extend bootstrap only through an opt-in dashboard profile: controller/status is resident-readable, controller/diagnostics and occupancy/observations are responder-only; responder gets diagnostic READ without actuator WRITE. Existing smoke defaults retain their verified behavior. Public and diagnostic snapshots are actual CINs; SQLite remains application recovery state only.

The persistent local demo runs actual telemetry/subscriptions/risk/CSE decisions/group/device ACKs on each synthetic observation. A periodic temperature observation retains declared degC units and does not clear prior hazards. Responder actions generate actual synthetic CINs; reset creates a new owned namespace/incident and never deletes shared CSE data. Process restart starts a new explicit simulation rather than claiming automatic continuation. Full restart/outbox/dispatch recovery remains P3 work.

Acceptance: unit tests cover role/session escalation, CSRF, stale/unknown/version mismatch and synthetic occupant nullability; existing protocol/Group tests remain green. An actual Docker gate must test both authenticated HTTP views against real CSE records, resident API/CSE diagnostic denial, dynamic A→B→no-route, stopped-device incomplete delivery and stale guidance. Browser rendering/accessibility checks remain a separately recorded verification layer.

Execution: make p1-dashboard passed on 2026-11-12, including a rerun with per-stage role response snapshots and ACK-age labels. Exact tested source manifests and evidence are indexed in STATUS.md. The gate prints progress phases, including the intentional 31-second expiry wait. It stops the stack after completion; make demo-up keeps it running for browser QA. No browser-rendering PASS follows from the HTTP gate.

## Selected ten-floor profile (18-check HTTP/CSE gate verified; browser QA pending)

Pause/selection fix contract (2026-11-12): the selected service adds responder-only GET /api/v1/incidents/{id}/snapshot. It reads the latest committed status version, then named immutable route/moving/occupancy/frame CINs for that version. Response is explicitly snapshot_kind=HISTORICAL, is_live=false, route=null, with snapshot_at_utc/simulation_second and recorded population/positions. This read does not advance simulation or refresh observation UTC. Live resident/responder endpoints retain STALE/UNKNOWN and omit old current positions; neither cached nor historical data becomes live guidance. The legacy service does not enable this endpoint. UI preserves same-incident selections during PENDING/STALE, displays the historical timestamp/badge, and clears cached private data at logout, role change or incident reset. Snapshot access still requires the responder session and actual CSE role reads; arbitrary cross-incident/resource lookup is unsupported.

make demo-scenario-up serves frontend/scenario/ on 127.0.0.1:3001 via backend/scenario_demo.py. It reuses the same local role-code/session/host/origin controls. Endpoint paths stay the same, but POST /api/v1/scenario accepts step, advance_30, pause, resume, reset and stop_display_c; the old fire_a/fire_b controls are rejected. Read-only runtime status identifies profile_id=fire_evac_10f_v1 and assumed model provenance. Fixed origin defaults to F7-R3 from the assumptions file; it is not a per-browser source query yet.

The selected HTTP runner initializes its own baseline with the existing authenticated reset action and waits for a different READY/paused incident before second-zero assertions. Only an explicit 409 rejection is eligible for bounded retry; accepted or uncertain actions are not replayed. The selected Make test/demo commands recreate containers to refresh regenerated trace bind mounts and start new incidents; they retain CSE volumes and evidence. The corrected actual 18-assertion rerun passed in evidence/20261112-121211Z-6e06237b/, including expired live fields, protected historical access and 170 recorded residents. Browser interaction remains unverified; STATUS.md links the original run and read-only audit.

Resident view exposes approved fixed route/status, simulated time and actual observed ACK counts. Responder additionally gets CSE-verified hazard frames, private per-person moving state and last-reached-node occupancy counts. These custom selected-profile snapshots differ from the old OccupancyObservation fixture shape; neither old API is silently relabeled. Correlation includes incident/event/route_version/simulation_second/policy hash; malformed delivery/population data fails closed. STALE/UNKNOWN removes direction and all person positions/counts. Both modes share one authoritative model and source trace; changing the UI view does not advance the simulation. No browser has been tested in the agent sandbox; make p1-scenario-dashboard is an actual HTTP/CSE gate, not browser QA.
