# FireRoute roadmap — local completion, then gated Hosted integration

Planning baseline: 2026-11-11; progress updated 2026-11-14 (Asia/Seoul).

## 1. Fixed dates and scope

- 2026-11-20: functioning selected system and all final deliverables submitted.
- 2026-11-23–25: judge interviews/presentations; not an implementation extension.
- 2026-11-26: winning-team selection (user-confirmed organizer schedule).
- 2026-11-27: ceremony.

The [public schedule](https://onem2m-hackathon.io/schedule.asp) confirms development ends November 20, final evaluation November 23–25 and ceremony November 27. Exact submission cutoff/timezone, platform, article/video formats and presentation duration are still unverified; obtain them before the final day. The user-supplied latest notice takes precedence over older drafts. See SOURCES.md.

Current execution uses Phase 1–4 below under the user instruction dated 2026-11-14. Historical P0–P4 labels remain in commands, requirements, tests and earlier records for traceability; they no longer define execution order. Documentation completion does not complete a development phase.

## 2. Current phases, deliverables and gates

| Current phase / planning window | Deliverables | Exit conditions and limits | Dependencies |
|---|---|---|---|
| Phase 1 — local completion, Nov 14–17 | Preserve WSL2/Docker/actual ACME; finish local sensor/risk/routing/moving people/roles/Group/ACKs, least-privilege security, timeout/malformed/duplicate events, fault handling and evidence | Preserve the actual 729-frame hazard result; rerun affected real CSE gates; diagnose 137 from Docker state/events/memory/logs, remove default-key warning, prove restart persistence; broader security/recovery/UI gaps stay explicit | Existing local environment; no Hosted account/server dependency |
| Phase 2 — portable MEC-ready structure, local work alongside Phase 1 | Independently executable risk component, versioned data interfaces, configurable CSE endpoint/identity, inactive MEC endpoint/auth settings, local/Hosted templates, Docker artifact | Local component/config/image checks; no invented MEC deployment/API; direct API and IPE-mediated paths remain distinct; document remote callback reachability | Existing pure model and local contracts; no Hosted access |
| Phase 3 — Hosted integration, only after separate explicit instruction, planning Nov 17–18 if authorized | Confirm login/namespace/API/permissions; assess Option C, then A/B/another official supported topology; deploy only using verified interfaces; run real service and possible IPE flows | Actual lifecycle/API/IPE/network/timing evidence for claimed subsets; no access/deploy before separate instruction; unsupported/unavailable capabilities remain gaps | Stable local system, explicit instruction, actual Hosted permissions and acquired compatible guides |
| Phase 4 — submission, draft now; finalize Nov 18–20 | Reproducible GitHub, Hackster.io Article, actual video, diagrams/resource tree, measured tests, interview slides and submission receipt | Working local submission by Nov 20 even if MEC is incomplete; include verified MEC results and visible omissions; no Expert guarantee | Local verified checkpoint; optional actual Phase 3 results |

Historical mapping: P0/P1 and local portions of P3 feed current Phase 1; independent structure/config work feeds Phase 2; historical P2 deployment/interworking feeds gated Phase 3; historical P4 feeds Phase 4. Preserve all F01–F25/T01–T26 and existing make command names. T27 adds the controlled CSE restart diagnostic/persistence slice; it is not automatic application recovery.

New-feature choices must document expected judging value, implementation cost, feasible test and failure risk. Current choices:

| Work | Expected judging value | Cost / test | Risk and control |
|---|---|---|---|
| Stable private CSE key | Security/privacy and reproducible GitHub | Small adapter change; unit checks and actual restart read-back | Preserve one volume key; no silent rotation; controlled T27 compatibility now verified, broader durability/security remain open |
| Docker stop diagnostics + persistence | Evidence quality, scenario reliability and interview explanation | Local orchestration + actual AE/CNT/CIN before/after restart | Read-only observation first; controlled stop is labeled; preserve volumes, leave unrelated resources untouched |
| Live-input/read-link fault gate (ADR-022/T29) | Reliability, Security/Privacy, oneM2M evidence and interview explanation | 261 units and actual 56-check gate pass; 37-check evidence review confirms 468 accepted frames, nine fault CINs, nine independent ACKs; normal hazard/HTTP regressions also pass with a 44-check review | Pin local CSE; label mutated application payloads/TCP-close injection; no fabricated CSE response, automatic full outage recovery or latency claim |
| Portable analysis boundary | Future deployment and GitHub quality | Reuse pure model; standalone stream component and unit checks implemented; image execution pending | No guessed Hosted API, Kubernetes privileges or fake IPE |
| Optional AI/FL/handover/location | Conditional rubric rows | Higher integration cost and additional environments | Deferred until selected local/system/submission gates are secure |

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

## 4. Current checkpoints and scope cuts

- Nov 14 verified checkpoint: T27 controlled CSE stop/start, patched-profile 729-frame hazard E2E and selected-dashboard 18-check HTTP/CSE gates now pass. STATUS links original artifacts and independent audits. This resolves that lifecycle/regression sequence; next prioritize bounded actual-CSE malformed/duplicate/timeout handling, fault recovery and declared latency measurement. Browser QA, portable-image execution and publication artifacts remain parallel work. It is not full Phase 1 completion or permission for Hosted access.
- Latest T29/regression checkpoint: actual input/read-link faults pass 56 checks at evidence/20261114-143344Z-72482bb4/ with a separate 37-check review. Both affected normal gates subsequently pass on the changed guard/read model: hazards evidence/20261114-151353Z-146f4874/ and selected role/HTTP evidence/20261114-151744Z-5bedbd29/, with a separate 44-check review at evidence/20261114-174340Z-66948580/. Preserve a feature-branch commit checkpoint, then implement/test full service/write/process recovery and declared latency boundaries; browser QA, portable-image execution and submission drafts remain parallel. Existing T29 does not prove a full CSE outage or remove the separate Hosted gate.
- Nov 14–16: retain passed local evidence, run CSE lifecycle/key/persistence checks and resolve real failures. No Hosted request is permitted during this work.
- Nov 17: stabilize the selected local scenario and portable interfaces. Phase 3 starts only if separately instructed; lack of Hosted readiness does not block the local submission.
- Nov 18: freeze optional handover/location/FL/AI work. Record actual Hosted supported/unsupported results if Phase 3 has run; otherwise document MEC as unverified. Finalize publication artifacts.
- Nov 19: fresh-environment rehearsal, backup real-run video, article/diagrams/slides and evidence review.
- Nov 20: submit functioning local system and all required materials before the confirmed cutoff; preserve the receipt. Exact cutoff/timezone/formats still require confirmation.

A working local release is mandatory even when MEC is incomplete. Keep baseline permissions and explicit failure states. Never substitute unit mocks, an inactive configuration template or co-located containers for actual MEC evidence.

## 5. First implementation slice

The first actual-CSE slice has passed T05 in the user's local environment (2026-11-11): eight distinct AEs, ten CNTs, real SUB verification and matching CIN read-back/notification. STATUS.md records the original run and independently inspected artifacts. Clean-clone/CI reproduction, graceful shutdown and shared-profile security remain open; do not treat this single run as full product completion.

The ordered incident/actual hazard-route CIN slice passed make p1-routes. make p1-group then passed actual Group/fopt, three independent display processes, command/ACK subscriptions, no-route clearing, expected-incomplete delivery after stopping one device and six ACP denials. The user committed/pushed that checkpoint (80f6e87). The stacked feature/p1-role-dashboards branch now passes make p1-dashboard: local sessions, both live role APIs, synthetic occupants, actual resident CSE denial, A/B/no-route, missing ACK, expiry and explicit reset. Browser QA and full stale-command/restart/dispatch recovery remain open; this is not full P1 completion or authenticated CSE security.

These are historical implementation checkpoints. Current next work is Phase 1 local stability/security and Phase 2 local portability, followed by Phase 4 deliverables. Phase 3 Hosted access is deferred until a separate explicit instruction; current account/server readiness is not a blocker for local work.

## 6. Selected-scenario change, Nov 12

The user selected the supplied fire_evac engine rather than the old three-floor scenario. Its seven files are preserved, and make test-scenario executes the original four engine test groups. Source import/engine success is T22 only; no ten-floor CSE/route/UI gate has run. Keep the tested baseline working while adding this profile.

Merge/development dependencies: (1) source manifest + frame schema/time semantics → (2) headless simulator publisher + actual CIN/SUB T23 → (3) agreed movement/exit/threshold mapping + collapse-aware route controller → (4) actual Group/ACK and both ten-floor role views T24. Source publisher/backend contracts, floor UI and policy/topology work can proceed in separate modules once their contracts are agreed. Occupant generation is a separate lane because the supplied engine has no residents/movement. No optional RL feature is introduced.

Until the user supplies or the team explicitly records missing movement/entrance rules, do not fabricate a computed ten-floor evacuation result. Keep the Nov 20 deadline: assess T23/T24 at the Nov 15 P1 checkpoint and record any selected-scenario gap explicitly, rather than relabeling the old three-floor run as completed migration. Current Phase 2 local design and Phase 4 outlines remain parallel work; Hosted access is separately gated.

Latest direction: the user requested both modes and authorized assumed dimensions/population. The shared fixed/moving model, source trace wrapper, selected CSE session, protected ten-floor app and actual core/HTTP gate commands are now implemented. Actual selected core and role HTTP/CSE baseline checks have passed, including the extended 18-check gate; the user confirmed the requested manual selection/pause smoke check. On Nov 14, make p1-hazards also passed its actual CSE/core run with 729 frames, hazard stages and Group/independent ACKs; broader browser/fault QA and MEC remain next gates. Use T25/T26 alongside T23/T24. Do not add further pedestrian physics, RL or optional features before executing these prepared gates and retaining their evidence. Public guide review and local portability work remain independent of the movement model; no Hosted access is performed now.

Nov 14 checkpoint: work from published main 7c5b396 on feature/p1-hazard-validation. The natural-hazard actual run now passes that T24 core slice; full P1, hazard browser QA and restart recovery remain open. Source seed 59/wind 5 gives reproducible blocked-path alternative/collapse/isolation with unchanged engine rules; default demo seed/population are retained. Under the latest strategy, continue local completion/portability and public guide review; no MEC deployment, Hosted access, lifecycle or API is verified. Preserve the Nov 20 submission deadline with a working local fallback.
