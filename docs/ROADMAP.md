# FireRoute roadmap — complete submissions by 2026-11-20

Planning baseline: 2026-11-11 (Asia/Seoul), following the initial repository analysis.

## 1. Fixed dates and scope

- 2026-11-20: functioning selected system and all final deliverables submitted.
- 2026-11-23–25: judge interviews/presentations; not an implementation extension.
- 2026-11-26: winning-team selection (user-confirmed organizer schedule).
- 2026-11-27: ceremony.

The [public schedule](https://onem2m-hackathon.io/schedule.asp) confirms development ends November 20, final evaluation November 23–25 and ceremony November 27. Exact submission cutoff/timezone, platform, article/video formats and presentation duration are still unverified; obtain them before the final day. The user-supplied latest notice takes precedence over older drafts. See SOURCES.md.

The old detailed phase numbering is superseded by P0–P4 below; its functional work is retained and regrouped. Documentation completion in this revision does not complete any development phase.

## 2. Phases, deliverables and gates

| Phase / target dates | Deliverables | Concrete exit conditions / tests | Dependencies |
|---|---|---|---|
| P0 environment + basic oneM2M, Nov 11–12 | Local runtime/pins, real CSE profile/alternative, executable contracts, AE/CNT/CIN/SUB adapter, receivers and reproducible commands | Clean setup; actual sensor CIN read-back and SUB verification/notification (T05); basic contracts T21; version/base/IDs recorded | Personal runtime; CSE source/package access; no MEC credential dependency |
| P1 actual fire-response E2E, Nov 12–15 | Risk computation, ordered incident/outbox, temperature/smoke simulator, real group control, 3 displays/ACKs, two live role views, synthetic occupants | T01–T07, T15, T18–T20 PASS; full matching incident/version; no-route clears displays and missing ACK stays incomplete | P0 contracts and CSE/client path; compute/UI/scenarios can be developed beside P0 |
| P2 MEC deployment + oneM2M interworking, Nov 12–17 | Local Sandbox, Option C MN-CSE MEC App, Cloud IN-CSE registration, actual catalog/IPE and non-location service | T11/T16/T17 PASS with source/deployment and correlated MEC/IPE/CSE evidence; a fallback changes actual topology labels and ADR | Early source/host access investigation starts Nov 11; deployment needs authorized host and pinned P1 contracts |
| P3 security/devices/recovery/performance, Nov 15–18 | Full ACP/TLS/auth tests, MQTT+HTTP, discovery/FCNT, restart/disconnect tests, latency report, optional Pi endpoint | T08–T10/T12–T13 and regression gates PASS; partial ACK/fan-out never counted complete; permissions and provenance verified | P1; MEC fault tests additionally require P2; P1 already includes 3 devices/basic permissions/fallback states |
| P4 GitHub/article/video/presentation, outline Nov 11; finalize Nov 18–20 | Standalone repository/release, licensed source/docs, exact reproduction guide, article, video, presentation, evidence index and backup real run | New-environment reproduction; factual claims match verified tests; formats/links/secrets checked; final submission receipt by Nov 20 | Verified P0–P2 selected scope; P3 evidence as obtained; all omissions visible |

## 3. Parallel work and merge order

| Lane | Can start independently | Waits for / feeds |
|---|---|---|
| oneM2M + infra core | Actual CSE selection/probe, request/response client, namespace and callbacks | Provides P0 interface/runtime to all lanes |
| Risk/backend | Pure graph tests, event ordering, authorization/read-model contract | Agreed schemas; later CSE client for persistence/dispatch |
| Simulator/IoT | Seeded typed inputs, display state machine/ACK contract, optional Pi capability inventory | Agreed contracts; then real subscriptions/client |
| Frontend | Role UI and explicit preview data, stale/no-route/ACK states | Backend role API contract; live integration before P1 gate |
| MEC/DevOps | ETSILabs access, TR-0086 revision review, Sandbox prerequisites/catalog/Option C research | Actual permissions; deploy pinned core after P1 path is stable |
| QA/publication | Test definitions, evidence schema, article/video outline, review checklist | Executed traces for final claims |

Dependency chain: contracts/runtime → telemetry CIN/SUB → computed route/CSE record → real fan-out → independent ACKs → live views. MEC infrastructure investigation runs alongside this chain; a complete MEC E2E additionally joins the IPE/service path. Shared-server deployment/test runs are serialized or namespace-isolated; workstream development happens in personal clones.

## 4. Risk checkpoints and scope cuts

- Nov 12: confirm real CSE round-trip and assign every missing ETSILabs/guide/server/registrar access item. Begin Option B assessment if Option C has a concrete blocker.
- Nov 15: require the P1 real-CSE E2E. Stop adding optional features if this fails; focus on the broken hop and regression evidence.
- Nov 16: choose a supported executable MEC topology based on evidence, C first then verified B/other official option. An ADR records reason, guide/implementation version and impact. A decision is not permission to modify a server.
- Nov 17: require a real MEC-through-oneM2M trace for P2. If blocked, state that gap and preserve reproducible CSE functionality; do not substitute mock success.
- Nov 18: freeze optional handover, location, FL, AI/MCP and unverified advanced semantics. Stabilize/reproduce the selected scope; P4 cannot be postponed.
- Nov 19: clean-environment rehearsal, actual-run video backup, all submission links and evidence reviewed.
- Nov 20: submit functioning artifacts and all required materials with time before the confirmed cutoff; retain submission receipt. No feature may be labeled finished solely because it is written in a document.

If time is short, protect working/reproducible P0–P2 and complete P4 deliverables. Keep baseline authorization and honest failure handling; reduce optional features and additional Expert ambitions first. Unmet selected requirements remain visible rather than disappearing from STATUS.

## 5. First implementation slice

The first actual-CSE slice has passed T05 in the user's local environment (2026-11-11): eight distinct AEs, ten CNTs, real SUB verification and matching CIN read-back/notification. STATUS.md records the original run and independently inspected artifacts. Clean-clone/CI reproduction, graceful shutdown and shared-profile security remain open; do not treat this single run as full product completion.

The ordered incident/actual hazard-route CIN slice passed make p1-routes. The subsequent make p1-group run also passed actual Group/fopt, three independent display processes, command/ACK subscriptions, no-route clearing, expected-incomplete delivery after stopping one device and six ACP denials. This is the verified local backend checkpoint; full P1 still needs live role views, synthetic occupants, authentication and complete stale/recovery handling. The user requested a checkpoint commit/push before further feature work. Keep remaining gaps explicit; shared/external deployment and any main merge retain their separate boundaries.
