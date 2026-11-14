# FireRoute — Hackathon Rubric 2026 implementation and evidence map

## 1. Source and scoring boundary

The user supplied Hackathon Rubric 2026.pdf. Its one-page tagged table was read locally; all 17 criterion labels and Expert cells were extracted with their column coordinates and no unmapped characters. SHA-256: 42b38857fffae7c92739f84440b9db020ec6b79897c0f70db64c465ffd2cdfad. The original stays outside this repository; references/README.md explains provenance. The official Expert summaries below are faithful paraphrases of that supplied source, not invented team targets.

The PDF labels Expert 4–5, Proficient 2–3 and Emerging 0–1; no category weights or total-score formula is specified. The user reports the organizer explicitly allows selecting a subset of rows. Do not infer that every criterion is mandatory or that this engineering map guarantees an Expert award.

Selected high priorities: #1, #2, #3, #10, #11, #13, #16, #6, #4, #5 and #9. #7 follows from good communication; #8 records genuine public technical participation only. #12/#14/#15/#17 are conditional. Phase names P0–P4 come only from ROADMAP.md.

Current strategy: prioritize verified local operation/security/reproducibility (Phase 1), portable component/configuration preparation locally (Phase 2), separately instructed Hosted integration only (Phase 3), and publication by Nov 20 (Phase 4). MEC deployment/service rows remain conditional and unverified until real authorized evidence exists. Persistent internal key configuration, lifecycle diagnostics and the standalone worker can support security/GitHub/interview preparation but do not themselves establish Expert scores, complete authentication or MEC lifecycle compliance.

## 2. Criterion-by-criterion plan

### 1. Innovative use of oneM2M — selected

- Official Expert: use at least one complex service, such as Group, announcement or pollingChannel.
- FireRoute feature: real Group/fopt coordinates three displays; SUB/ACP support the application.
- Work: onem2m/ group creation, accepted member URIs, fan-out results; simulator/ independent consumers.
- Verify: T05–T07; inspect group/member count, three command CINs, actual callbacks and ACKs.
- Judge evidence: sanitized request/aggregate response, tree/resource IDs and demo segment.
- Current status: VERIFIED for the selected local Group function: actual P1_GROUP PASS proves four fopt operations, 12 member command CINs, independent ACKs and a stopped-device incomplete case. Evidence/audit are indexed in STATUS. This demonstrates the selected complex service; final Expert scoring remains the judges' assessment.

### 2. Use of appropriate communication protocols — selected

- Official Expert: devices and applications use multiple different protocols according to communication conditions.
- FireRoute feature: device oneM2M MQTT, application HTTP(S); TLS profiles where supported.
- Work: actual CSE binding/broker, device request/response handling and protocol-selection rationale.
- Verify: T08 with matching oneM2M request IDs and CSE CIN read-back for MQTT and HTTP(S).
- Judge evidence: sanitized binding/connection traces, configuration versions and rationale.
- Current status: NOT_STARTED / NOT_RUN. Gap: no broker/binding traffic verified; an HTTP-only P1 is not this target.

### 3. Innovative scenarios — selected

- Official Expert: a complex device-to-CSE-to-multiple-application scenario, using oneM2M service functions rather than implementing those functions in devices/apps.
- FireRoute feature: sensors, edge risk controller, three display actuators, resident and responder applications.
- Work: real SUB → compute → route CIN → GRP/fopt → ACK; shared live incident/version.
- Verify: T01–T07, T15, T18–T20 and integrated scenario.
- Judge evidence: one correlated run spanning both roles, resource tree and error cases.
- Current status: VERIFIED for the legacy three-floor backend and role HTTP/CSE slice. P1_GROUP and P1_DASHBOARD prove sensor → notification → computed route CIN → real fan-out → simulated device ACK plus two role-scoped APIs/synthetic occupants, expiry and incomplete delivery. The selected ten-floor core and role HTTP/CSE baseline gates have also passed (latest 18 assertions). The natural-hazard actual CSE/core gate also passed: 729 frames, blocked-path alternative, collapse exclusion, no-route and an intentionally incomplete stopped-device delivery; comprehensive browser QA remains pending. Full recovery and MEC remain open; no final scenario score is claimed.

### 4. Quality of Article — selected

- Official Expert: cover all basic requirements plus additional insights and the benefits of oneM2M. Basic requirements include system/service overview, hardware, resource design/protocol usage where possible, and pictures/diagrams/text.
- FireRoute feature: standalone build story with measured results and honest simulation/deployment limits.
- Work: article draft, architecture/resource figures, reproduction steps, hardware/simulator inventory and insights.
- Verify: P4 reviewer follows clean-clone instructions; every factual claim links an executed result.
- Judge evidence: final article URL/export, figures and evidence references.
- Current status: NOT_STARTED / NOT_RUN. Gap: no article or measured implementation insights.

### 5. Quality of Video — selected

- Official Expert: above-average, enjoyable production with reasonable effort; encourage article reading or tie the article's story together.
- FireRoute feature: clear baseline → smoke → reroute → fan-out → ACK → MEC/evidence narrative.
- Work: readable capture, narration/audio, mode labels, captions and real-run backup.
- Verify: P4 playback review, timestamps matched to real traces, no simulated-success presentation.
- Judge evidence: submitted video, capture run IDs and storyboard in DEMO.md.
- Current status: NOT_STARTED / NOT_RUN. Gap: no recorded video; duration/format rules remain to be checked.

### 6. Quality of Github — selected

- Official Expert: standalone repository explaining purpose, source navigation, build and deployment without requiring the article, while linking the hackster.io article.
- FireRoute feature: fire-route repository with reproducible local/shared profiles and tests.
- Work: source, lockfiles, README, setup/test commands, CI, licenses, evidence index and article link.
- Verify: new environment reproduction from the release commit; link/secret/license review.
- Judge evidence: public repository/release URL, CI output and reproduction log.
- Current status: PARTIAL implementation. The user pushed foundation checkpoint 80f6e87 and subsequently confirmed publishing dashboard checkpoint 7c5b396 to main. The natural-hazard extension is local on feature/p1-hazard-validation. Actual T05/routes/Group/role HTTP-CSE evidence is recorded. Fresh-clone reproduction, executed CI, release and article link remain unverified.

### 7. Promotion of oneM2M — supporting

- Official Expert: article/video/repository provide a well-written endorsement of oneM2M.
- FireRoute feature: demonstrate practical reuse of standard resource management, SUB, Group and ACP.
- Work: explain actual benefits, implementation choices and limitations using the working scenario.
- Verify: P4 editorial review against protocol evidence; no unsupported compliance statements.
- Judge evidence: coherent article/video/repository passages and linked live trace.
- Current status: NOT_STARTED / NOT_RUN. Gap: no completed publication or working benefit demonstration.

### 8. Judge points — supporting, no manufactured activity

- Official Expert: public forum interactions/discussions (for example Slack/GitHub, not private email) show beneficial aspects or a good grasp of oneM2M.
- FireRoute feature: genuine technical questions/findings from actual implementation.
- Work: team members participate when useful and explicitly authorized; record public links.
- Verify: real public thread, technical relevance and attribution.
- Judge evidence: traceable public URLs and context.
- Current status: NOT_STARTED / NOT_RUN. Gap: no public interactions provided. Codex must not send messages or create activity automatically.

### 9. Interview points — selected

- Official Expert: beyond explaining resource structure and benefits, team members explain the integration methodology and why they would continue using oneM2M.
- FireRoute feature: every presenter can explain the end-to-end protocol flow and design choices.
- Work: resource walkthrough, methodology/tradeoff notes, role-specific Q&A and rehearsal.
- Verify: P4 peer interview covers resources, protocols, failure handling, MEC placement, simulation and benefits.
- Judge evidence: presentation, diagrams and reproducible demo/answers; interview outcome belongs to judges.
- Current status: NOT_STARTED for rehearsal / NOT_RUN. Actual local CSE/role integration provides concrete material; team explanation, MEC methodology and peer interview still need preparation.

### 10. Security and Privacy — selected

- Official Expert: use secure protocols together with ACP.
- FireRoute feature: HTTPS/MQTTS, authenticated identities, least-privilege resource policies and responder-only synthetic occupants.
- Work: TLS/CA configuration, role credentials, CSE ACPs, backend authorization, secret-safe logs.
- Verify: T09 and T15; permit intended actions, deny unauthorized writes/reads and identity misuse.
- Judge evidence: transport configuration/connection proof, ACP read-back and positive/negative outputs.
- Current status: PARTIAL verified local protection. P1_GROUP proves six scoped CSE denials; P1_DASHBOARD verifies separate role sessions, direct backend denial and actual CSE resident occupant denial. Full CSE-originator authentication/TLS remain unverified and the default-secret warning remains; local HTTP/header identity does not satisfy official Expert secure-protocol requirements.

### 11. Data Interoperability and Discoverability — selected, tiered scope

- Official Expert: advanced semantics, including SAREF, or SDT data models from TS-0023.
- FireRoute feature: labels first; compatible FCNT/discovery next; SDT or semantics only if feasible and genuinely implemented.
- Work: verify model support; define FCNT specialization and discovery; conditional semantic/SDT model and executed query.
- Verify: T10 basic/FCNT subcases; separate advanced-model test before any Expert-level claim.
- Judge evidence: model definition, real resources, discovery/query requests/results and app use.
- Current status: NOT_STARTED / NOT_RUN. Gap: labels+CIN correspond to Emerging, FCNT+queries to Proficient; neither alone meets the official Expert criterion. Advanced model support/time unverified.

### 12. CSE Handover & Service Continuity — conditional

- Official Expert: automated handover driven by location/load/latency/availability; preserve/rebuild state, subscriptions and security context; measure interruption or loss.
- FireRoute feature: optional policy-driven dual-CSE continuity experiment.
- Work: two actual CSEs, trigger policy, state/SUB/security restoration and loss accounting.
- Verify: T14 including automated trigger; a manually changed endpoint is only a preliminary check.
- Judge evidence: trigger/restore trace, before/after resources, outage/loss measurements.
- Current status: NOT_STARTED / NOT_RUN, DEFERRED. Gap: dual-CSE runtime/time; excluded until P0–P2 and required submissions work.

### 13. oneM2M–MEC Application / VM Deployment — selected, tiered scope

- Official Expert: custom project-specific geography/topology and oneM2M–MEC services, demonstrating orchestration across eligible hosts.
- FireRoute feature: actual Option C first, with labeled synthetic building topology; verified Option B fallback if needed.
- Work: Local Sandbox access, acquired guide, app artifact/lifecycle, MN-to-IN registration, placement evidence; additional multi-host orchestration only if supported.
- Verify: T16/T17 plus deployment review; verify what is a container, VM, external app or emulated platform.
- Judge evidence: pinned deployment procedure, host/app identities, topology, lifecycle logs and registration read-back.
- Current status: NOT_STARTED / NOT_RUN. Gap: no Sandbox/CSE deployment. Deploying/registering an app/CSE/VM with documentation is the Proficient description; Option C on one host does not itself prove Expert orchestration.

### 14. Federated Learning (TR-0084) — conditional

- Official Expert: custom oneM2M models coordinate participants, datasets/tasks, status/results; dynamic client selection and resilient multi-round training; solution uses ESTIMED VM.
- FireRoute feature: no baseline FL feature; assess fit only after core completion.
- Work: genuine multi-client training/data/model resources, selection, recovery and required VM access if selected.
- Verify: separate multi-round tests with real training and failure/rejoin; record model/data provenance.
- Judge evidence: ESTIMED VM deployment, client/round traces and real results.
- Current status: NOT_STARTED / NOT_RUN, DEFERRED. Gap: no FL implementation, data justification or VM; route algorithm is not FL.

### 15. Geolocation Services — conditional

- Official Expert: combine network/MEC/oneM2M location services for mobility, handover, geofencing, placement or policy, with event-driven behavior.
- FireRoute feature: optional service-driven context; no real occupant positioning claim.
- Work: verify MEC 013 and mapping, consent/privacy scope and event policy; avoid confusing synthetic room labels with network location.
- Verify: actual location response/notification → IPE/CSE → policy reaction, with source labels.
- Judge evidence: API/version, subscription/notification trace and corresponding behavior.
- Current status: NOT_STARTED / NOT_RUN, DEFERRED. Gap: API availability and project value unverified; baseline uses synthetic zones only.

### 16. MEC Services — selected, tiered scope

- Official Expert: discover, configure and consume multiple MEC services through oneM2M, with bidirectional MEC–oneM2M interaction.
- FireRoute feature: first one verified non-location service via IPE/CSE; expand to multiple services/reverse operation only if real support/time exists.
- Work: actual catalog/OpenAPI inventory, official compatible IPE/mapping, correlated observation/request/result resources; no invented write operations.
- Verify: T11; separate direction/service traces for any expanded Expert-level claim.
- Judge evidence: discovery/configuration calls, MEC responses/notifications, CSE resources and consuming application's reaction.
- Current status: NOT_STARTED / NOT_RUN. Gap: direct MEC calls are Emerging; one non-location service through oneM2M is Proficient; multiple services and bidirectionality are unverified.

### 17. AI Agents & MCP Integration — conditional

- Official Expert: an agent orchestrates multiple tools/MCP servers and complex oneM2M/MEC workflows with persistent state or advanced routing.
- FireRoute feature: optional diagnostic agent; deterministic route/risk decisions stay outside agent control.
- Work: real tools/servers, workflow state, validation, permission/error handling and reproducible task cases.
- Verify: separate multi-tool workflow, state persistence and failure tests; an isolated LLM call does not establish this criterion.
- Judge evidence: tool invocation trace, persisted workflow state and verified outcomes.
- Current status: NOT_STARTED / NOT_RUN, DEFERRED. Gap: no agent/MCP implementation or demonstrated need.

## 3. Claim control

Before submission, attach evidence for every claimed criterion in STATUS.md and article/video timestamps. Distinguish source criterion verified, feature implemented, feature tested, and judge assessment. The supplied rubric is inspected and the P0 CSE primitive slice is now verified; full selected product/scoring targets remain incomplete. Optional rows can be explicitly excluded. Never convert a documented plan, deployed URL, or lower-tier success into an Expert claim.
