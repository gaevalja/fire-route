# FireRoute demonstration and submission plan

## 1. Scope labels

This is a proposed storyboard, not an executed or recorded demo. Initial target length is 4–6 minutes, a team proposal until official duration/format rules are obtained. All evidence must come from an actual run; pre-recorded backup is labeled with its run ID/time.

The selected final scenario is now the supplied fire_evac engine (floors 1–10 plus roof/162 zones), not the legacy three-floor regression. Its source tests pass; CSE/route/UI integration is not yet implemented. SCENARIO.md and T23/T24 govern the new live story. Do not present the original standalone preview as an actual oneM2M/MEC demonstration.

Display input provenance (SYNTHETIC/PHYSICAL), actual CSE connection/test status, MEC deployment option/source, Sandbox network emulation and missing integrations. Describe computed alternatives on the synthetic graph without promising actual evacuation safety, fire accuracy or real occupant positioning.

## 2. Storyboard

| Approximate time | Show | Required supporting evidence |
|---|---|---|
| 0:00–0:30 | FireRoute problem, selected synthetic ten-floor building plus roof, separate resident/responder roles | Source manifest, seed/wind, scope/provenance labels; overview figure |
| 0:30–1:10 | Actual AE/CNT/CIN/SUB/GRP/ACP tree and Option C target vs actual placement | CSE read-back, versions/IDs; real deployment facts only |
| 1:10–1:40 | Compute a route for the agreed resident start/exit policy; two live views agree | Actual frame/route CIN/version; policy recorded; not implemented yet |
| 1:40–2:30 | Seeded fire/smoke evolution from the preserved engine, fixed wind and simulated/real time shown | Actual 162-zone CSE CIN and SUB callback; no independent browser state substitution |
| 2:30–3:10 | Policy-blocked/collapsed traversal triggers route recomputation or no-route | Source frame, committed collapse state, agreed movement policy and actual new route CIN |
| 3:10–4:00 | Real GRP/fopt delivers to three independent displays and each ACKs | Aggregate member results, three command CINs, three device ACK CINs |
| 4:00–4:40 | Actual MEC service → IPE → CSE → application; app placement and Cloud IN-CSE registration | T11/T16/T17 evidence; direct API call and emulated network shown separately |
| 4:40–5:30 | No-route clears directions; stop one display; deny unauthorized access; responder synthetic occupants | Actual incomplete/STALE/UNKNOWN status, CSE denial, responder-only timestamped data |
| 5:30–6:00 | Measured results, benefits, reproducibility and limitations | Real N/p50/p95 if available, repository/article links, honest unverified list |

If MEC is blocked, replace its segment with the exact missing integration and working CSE evidence; do not present an architectural slide as an executed MEC trace. If only a lower-tier rubric feature is verified, describe that result without an Expert claim. Use recorded failures/recovery with clear labels if timing cannot be reliably demonstrated live.

## 3. Submission inventory — complete by 2026-11-20

- GitHub fire-route repository/release: source navigation, real commands, version pins, synthetic fixtures, tests, licenses/notices and sanitized evidence index. Repository https://github.com/gaevalja/fire-route exists; executable release/reproduction evidence is still pending.
- Article: system/service overview, hardware/simulator inventory, resource model, protocol rationale, Option C/actual fallback, security/privacy, measured results, oneM2M benefits, limitations and reproduction instructions. Confirm actual publishing platform; rubric refers to hackster.io.
- Video: legible screens/logs, intelligible narration, mode labels, source/run IDs, useful pacing and tested playback/link accessibility. Confirm file/link/length rules.
- Presentation: architecture/Cloud registration, demo flow, resource/protocol choices, project value, results, remaining gaps and team contributions.
- Backup: a genuine prior run, timestamped sanitized traces, pinned artifact/configuration version and recovery procedure.
- Submission receipt: record final links/files, exact submitted version, cutoff/timezone and confirmation. Required portal/formats are not yet independently verified.

The [organizer publication notice](https://estimed.etsi.org/news/estimed_hackathon2/) specifies Apache-2.0 for source and CC BY 4.0 for non-code outputs. The source Apache-2.0 LICENSE now exists. P4 must finish documentation licensing/attribution and third-party notices while retaining their original terms; no publication is performed by this storyboard.

## 4. Rehearsal and interviews

Nov 19: run clean-environment reproduction, verify every link, rehearse live and backup paths, redact secrets, and compare all claims with STATUS. Nov 20: finish all deliverables and submit before the confirmed cutoff. Nov 23–25 interviews/presentations: every presenter explains resource tree, integration methodology, protocol choices, why oneM2M is useful, real vs emulated MEC, failure handling, measured clock boundaries and remaining limitations. Nov 26 selection and Nov 27 ceremony do not extend implementation time.

The original documentation task performed no publication. Later implementation and the user's foundation-branch push are recorded in STATUS; no video, article, presentation or shared deployment is completed by this storyboard.

## 5. Current local rehearsal path — legacy three-floor checkpoint

The HTTP/CSE gate make p1-dashboard passed; it stops its stack on completion. For manual browser rehearsal, run make demo-up and open http://127.0.0.1:3000. Read role codes privately from ignored .runtime/access-codes.json. Use separate browser profiles for simultaneous roles; keep codes out of captures. Start with the resident approved route and the responder synthetic sensors/occupants, then trigger F2_A fire (EXIT_B), F2_B fire (NO_VERIFIED_ROUTE), stop display-c (2/3 ACKs/INCOMPLETE), pause and wait beyond 30 seconds (STALE/UNKNOWN), then reset to a new incident (EXIT_A).

The schematic is a synthetic topology, occupants are generated counts and displays are separate local Python processes. The local API uses real CSE snapshots and role policies; it does not call a MEC service. The first scripted HTTP/CSE gate is verified, while browser layout/accessibility and actual recording remain NOT_RUN. Follow TEST_PLAN.md before presenting the UI as browser-verified. Show the actual standalone IN-CSE label and missing MEC integration until P2 evidence exists.

For the selected source preview, open simulator/scenarios/fire_evac/index.html and use its original seed/wind/floor/playback controls. This preview is isolated local simulation. Replace the legacy rehearsal with the selected live CSE profile only after T23/T24 pass; keep the existing run as a labeled regression/backup, not migration proof.

## 6. Prepared selected dual-mode rehearsal

After make p1-scenario and make p1-scenario-dashboard pass, run make demo-scenario-up and use http://127.0.0.1:3001. A responder sees fixed F7-R3 guidance and a separate moving-resident view over the same fire frame. Show floor/individual selection, +1/+30 seconds, queues, last-reached-node counts, conserved population and actual fixed-sign ACKs. Pause beyond 30 wall seconds to hide directions/positions. A resident must not receive the private people/occupancy payload. Do not expose login codes in captures.

Explicitly label the default 170 people, assumed distances/capacities/speeds and heuristic hazard policy as uncalibrated. Offline seed=2026/wind=5 results describe this simulation only; they are not measured evacuation success or latency. New browser recording/manual QA remains NOT_RUN until performed. The original engine/configuration, selected CSE communication, assumed pedestrian model and missing MEC integration are four distinct claims.

Natural-hazard rehearsal (actual CSE/core verified; video/browser recording pending): run make p1-hazards for a source-seed-59 replay on the selected ten-floor topology. Show the baseline A-stair path, alternate B-stair path avoiding blocked F4-SA (both can reach EXIT_A), a collapsed node excluded from traversal, and no-route from an unblocked fixed origin. Then deliberately stop display-c and show Group writes to all three members with only two ACKs/INCOMPLETE. Stage times are simulated; source/model indices and geometry are uncalibrated. All residents have already evacuated before the later fixed-origin queries under these assumptions, so do not narrate a trapped-person rescue or claim collapse alone caused rerouting. make hazard-preview is only offline preparation and cannot supply a recorded real-CSE demo. Capture only a genuinely passing real run, retaining the explicit fault/mode labels.

Current strategy gate (ADR-019): prepare a complete reproducible local demo independently of Hosted access. No Hosted login/API/deployment is permitted before a separate Phase 3 instruction. Present the standalone analysis worker as a local portable component only. Show actual lifecycle/key/persistence results only after make local-stability passes; preserve any 137/OOM/timeout evidence and keep intentional display-c failure distinct from CSE service failure. If Phase 3 does not complete, submit local system evidence and an explicit MEC omission rather than a simulated success segment.
