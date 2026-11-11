# FireRoute product requirements

## 1. Outcome and limits

FireRoute: Intelligent Fire Evacuation and Rescue Guidance System demonstrates actual oneM2M service-layer coordination and MEC interworking for a synthetic three-floor building with two stairwells. It collects temperature, smoke, and fire-related observations, computes deterministic risk/route decisions at the edge, controls three display endpoints, and presents separate resident/responder views.

This hackathon PoC does not guarantee fire detection accuracy, real occupant positions, or safe evacuation. Smoke index is synthetic and unitless 0–100. Remaining occupants are scenario records, not detected people. Physical sensor samples, if added, must retain their measured units and source provenance; measurement alone does not establish fire-detection accuracy.

## 2. Priorities

- MUST: required for the selected submission baseline; an unavailable environment is reported as a gap, never converted into a PASS.
- SHOULD: high-value work following the working core.
- OPTIONAL: selected only with explicit justification, time, infrastructure and acceptance tests.
- P0–P4 are development phases from ROADMAP.md, not rubric scores or weights. Not all 17 judging rows need implementation, according to the user-provided organizer clarification.

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
| F14 | MUST / P2 | Deploy selected official MEC topology and use a non-location MEC service through oneM2M interworking | Deployment identity and service → IPE → CSE → consumer trace |
| F15 | SHOULD / P3 | Report measured p50/p95 with sample count and defined clock boundary | Reproducible calculation from real hop logs |
| F16 | OPTIONAL | Controlled CSE handover | Actual dual-CSE outage/loss/restoration measurement |
| F17 | OPTIONAL | MEC network location/geofencing | Supported real API trace; synthetic indoor coordinates never count |
| F18 | OPTIONAL | Advanced semantics/SDT | Compatible implementation, models and executed query |
| F19 | OPTIONAL | Diagnostic AI/MCP or TR-0084 FL | Separate genuine implementation/tests; no AI control of route safety |
| F20 | MUST / P1 | Ingest typed synthetic temperature and smoke/fire observations | Correct units/provenance, validation and CSE read-back; smoke drives initial hazard policy |
| F21 | MUST / P1 | Show synthetic remaining-occupant scenario information to responders | Timestamped synthetic count/zone records; resident access denied; unknown is not zero |
| F22 | MUST target / P2 | Option C: MN-CSE as MEC App on MEC Host, with explicit Cloud IN-CSE registrar relation | Lifecycle/placement record, CSE registration evidence and acquired-guide conformance review |
| F23 | MUST / P0–P4 | Independent local modules, PR integration and reproducible setup | Clean-clone setup and tests; shared deployment tied to a reviewed commit |

If F22 cannot run, retain the selected-baseline gap and record a justified official fallback (first assess Option B). Never report Option B or a standalone CSE as Option C. A documented fallback is a scoped result, not completion of the original topology.

## 4. Non-functional requirements

- Preserve fixtures/building_3f.json: deterministic topology, seedable scenarios, arbitrary routing costs. Add separate scenarios without silently changing fixture meaning.
- Use bounded request/retry budgets, TTL/ACK deadlines and visible failure states; configuration values are declared and included in run metadata.
- Persist enough deduplication/outbox/version state for controlled recovery. CSE remains the owner of oneM2M resources.
- Keep sensor/controller/device/IPE identities distinct. Apply backend permissions and CSE ACPs; privileged CSE credentials never enter browsers.
- Use HTTPS/MQTTS for shared/deployed paths where supported; a private local HTTP development profile records its limitation. VPN does not replace resource authorization or application authentication.
- Clearly display synthetic/physical input, real CSE status, MEC source, deployment option and network emulation. Configuration alone is not connection evidence.
- Local development does not require the shared server. Define versioned module contracts and provide Compose or a documented process-based alternative.
- Never depend on unverified MEC 013/033/046 availability, full ARM64 Sandbox support, or an assumed Raspberry Pi model.

## 5. Selected success story

Start with a computed baseline at EXIT_A. Publish a synthetic F2_A smoke event through the actual CSE. The subscription drives the edge risk controller, which persists the next route version to EXIT_B. Real group fan-out delivers to three display consumers; all three ACK CINs confirm application. Both role views update, with synthetic occupant information visible only to responders. A verified MEC service operation traverses the IPE/oneM2M path, and the deployment evidence states the actual option and Sandbox emulation. Demonstrate no-route and incomplete delivery without fabricated success.

## 6. Out of scope and submission

No fire certification, live emergency advice, real-person tracking, emergency-service dispatch, physical building interlocks or guaranteed real-time deadlines. Optional handover/location/FL/AI work may be omitted.

By 2026-11-20 deliver the functioning selected scope, source repository, article, video, presentation and sanitized evidence. Remaining gaps must be visible in STATUS.md and submission materials. See ROADMAP.md, TEST_PLAN.md and DEMO.md.
