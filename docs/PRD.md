# FireRoute product requirements

## 1. Outcome and limits

FireRoute: Intelligent Fire Evacuation and Rescue Guidance System demonstrates actual oneM2M service-layer coordination and MEC interworking. The user-selected scenario is the supplied fire_evac engine: floors 1–10 plus an eleventh-floor roof, 162 hazard zones and two stairwells. Preserve its seeded fire/smoke/collapse behavior as documented in SCENARIO.md. The existing three-floor graph/runtime is a verified regression checkpoint, not the selected final building.

The target collects declared temperature/smoke/fire observations, computes risk/route decisions, controls three display endpoints and presents resident/responder views. The selected engine itself generates fire/smoke indices and collapse states only; temperature and occupant records need separately labeled sources. Evacuation movement/exit rules are additional application contracts, not existing engine behavior.

This hackathon PoC does not guarantee fire detection accuracy, real occupant positions, or safe evacuation. Smoke index is synthetic and unitless 0–100. Remaining occupants are scenario records, not detected people. Physical sensor samples, if added, must retain their measured units and source provenance; measurement alone does not establish fire-detection accuracy.

## 2. Priorities

- MUST: required for the selected submission baseline; an unavailable environment is reported as a gap, never converted into a PASS.
- SHOULD: high-value work following the working core.
- OPTIONAL: selected only with explicit justification, time, infrastructure and acceptance tests.
- Current execution uses Phase 1–4 in ROADMAP.md (local completion, local portability, separately authorized Hosted integration, final submission). P0–P4 labels in the requirement table are historical workstream identifiers, not current execution order or rubric scores. Not all 17 judging rows need implementation, according to the user-provided organizer clarification.

## 3. Functional requirements

Existing F01–F19 identifiers are retained for traceability.

| ID | Priority / phase | Requirement | Acceptance signal |
|---|---|---|---|
| F01 | MUST / P0 | Register sensor, controller, three display and two application AEs with actual CSE resources | Real tree read-back, AE IDs and resource IDs |
| F02 | MUST / P0 | Create telemetry CIN and consume actual SUB notification, including verification | Matching event ID in CSE read-back and callback |
| F03 | MUST / P1 | Compute baseline route from F3_ROOM1 | EXIT_A selected from fixture graph |
| F04 | MUST / P1 | Block F2_A for synthetic smoke index 90 and recompute | EXIT_B selected; F2_A absent |
| F05 | MUST / P1 | Store versioned hazard/route decisions in CSE | Read-back matches incident, source event and version |
| F06 | MUST / P1 | Create identical command through actual GRP/fopt for three commands CNTs | Three member results plus three matching CINs |
| F07 | MUST / P1 | Independent display consumers apply commands and create individual ACKs | Three distinct device ACKs for matching command/version |
| F08 | MUST / P1 | Resident and responder views share live incident/version with role restrictions | Resident sees approved route/status; responder sees risk, sensor/ACK diagnostics |
| F09 | MUST / P1 | Validate identifiers, deduplicate and reject outdated work | Duplicate/old events create no new decision or stale display application |
| F10 | MUST / P1 | No-route, sensor timeout and missing ACK have explicit status | NO_VERIFIED_ROUTE clears directions; UNKNOWN/STALE and incomplete delivery visible |
| F11 | SHOULD / P3 | Device oneM2M MQTT and app HTTP(S), with protocol rationale | Actual request/response bindings produce CSE resources |
| F12 | MUST / P3, baseline P1 | Separate least-privilege ACP, role authorization and deployment transport security | Authorized actions succeed; forbidden CSE writes and responder reads are denied |
| F13 | SHOULD / P3 | Discover resources via labels; add FCNT if supported | Actual discovery results; FCNT definition/read-back when claimed |
| F14 | CONDITIONAL / current Phase 3 (historical P2) | After separate instruction, verify a supported Hosted/official MEC topology and service; distinguish direct API from supported IPE-mediated interworking | Deployment identity and service → IPE → CSE → consumer trace |
| F15 | SHOULD / P3 | Report measured p50/p95 with sample count and defined clock boundary | Reproducible calculation from real hop logs |
| F16 | OPTIONAL | Controlled CSE handover | Actual dual-CSE outage/loss/restoration measurement |
| F17 | OPTIONAL | MEC network location/geofencing | Supported real API trace; synthetic indoor coordinates never count |
| F18 | OPTIONAL | Advanced semantics/SDT | Compatible implementation, models and executed query |
| F19 | OPTIONAL | Diagnostic AI/MCP or TR-0084 FL | Separate genuine implementation/tests; no AI control of route safety |
| F20 | MUST / P1 | Ingest typed synthetic temperature and smoke/fire observations | Correct units/provenance, validation and CSE read-back; smoke drives initial hazard policy |
| F21 | MUST / P1 | Show synthetic remaining-occupant scenario information to responders | Timestamped synthetic count/zone records; resident access denied; unknown is not zero |
| F22 | CONDITIONAL / current Phase 3 (historical P2) | Assess actual Option C support (MN-CSE as MEC App and registrar relationship); select only a supported official topology | Lifecycle/placement record, CSE registration evidence and acquired-guide conformance review |
| F23 | MUST / P0–P4 | Independent local modules, PR integration and reproducible setup | Clean-clone setup and tests; shared deployment tied to a reviewed commit |
| F24 | MUST / P1 | Integrate the user-selected fire_evac scenario unchanged, with seeded wind/time/collapse semantics and all 162 zones | Source/engine T22; actual atomic frame/CSE/SUB T23; agreed movement policy, route/Group/ACK/role views T24 |
| F25 | MUST / P1 | Provide both fixed-origin guidance and seeded moving synthetic residents on the same hazard state, with explicitly assumed geometry/population | Analytic movement/queue/conservation tests T25; protected actual HTTP/CSE selected-profile views T26; no real-person or calibrated safety claim |

If F22 cannot run, record the actual limitation and assess Option A/B or another officially supported topology against acquired guides and real permissions. Never report Option B or a standalone CSE as Option C. A documented fallback is a scoped result, not completion of the original topology.

## 4. Non-functional requirements

- Preserve fixtures/building_3f.json and its existing F03/F04 regression expectations. The selected source is separately versioned under simulator/scenarios/fire_evac/; do not silently alter either topology. F03/F04's EXIT_A/EXIT_B baseline checks remain regression requirements; F24 covers the selected building.
- Use bounded request/retry budgets, TTL/ACK deadlines and visible failure states; configuration values are declared and included in run metadata.
- Persist enough deduplication/outbox/version state for controlled recovery. CSE remains the owner of oneM2M resources.
- Keep sensor/controller/device/IPE identities distinct. Apply backend permissions and CSE ACPs; privileged CSE credentials never enter browsers.
- Use HTTPS/MQTTS for shared/deployed paths where supported; a private local HTTP development profile records its limitation. VPN does not replace resource authorization or application authentication.
- Clearly display synthetic/physical input, real CSE status, MEC source, deployment option and network emulation. Configuration alone is not connection evidence.
- Local development does not require the shared server. Define versioned module contracts and provide Compose or a documented process-based alternative.
- Never depend on unverified MEC 013/033/046 availability, full ARM64 Sandbox support, or an assumed Raspberry Pi model.

## 5. Selected success story

For the selected scenario, choose and record seed/wind/configuration, then publish current 162-zone frames through the actual CSE. The subscription drives the risk controller under an explicitly agreed movement/exit policy. Evolving fire/smoke and committed collapse trigger computed route updates; real Group/fopt and independent ACKs confirm device application. Both role views agree on incident/frame/version; separately generated occupant data stays responder-only. Verify MEC service/IPE interworking and report the actual deployment option. Do not predetermine an EXIT_A→EXIT_B transition on the ten-floor source without executing its new routing policy.

The existing three-floor regression story remains: baseline EXIT_A, F2_A smoke → EXIT_B, both stair nodes blocked → NO_VERIFIED_ROUTE, with actual CIN/SUB/Group/ACK evidence. Its successful tests do not complete F24/T23/T24.

## 6. Out of scope and submission

No fire certification, live emergency advice, real-person tracking, emergency-service dispatch, physical building interlocks or guaranteed real-time deadlines. Optional handover/location/FL/AI work may be omitted.

By 2026-11-20 deliver the functioning selected scope, source repository, article, video, presentation and sanitized evidence. Remaining gaps must be visible in STATUS.md and submission materials. See ROADMAP.md, TEST_PLAN.md and DEMO.md.

## Current strategy acceptance additions (2026-11-14)

Phase 1 must remain independent of Hosted access: preserve actual local CSE behavior, verify shutdown cause/key/persistence, distinguish intentional missing-device tests from service failures, and retain safe handling of malformed/duplicate/stale observations. Phase 2 prepares a reusable standalone risk/route component, external local/Hosted settings and image/interfaces with no Hosted connection. Phase 3 is separately gated; user-described namespace/login details are unverified. Phase 4 submits working local artifacts even if MEC remains incomplete. No inactive template, unit mock or container running outside verified MEC lifecycle counts as F14/F22 completion.
