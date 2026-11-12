# FireRoute — repository instructions for Codex

## Mission and authority

Build **FireRoute: Intelligent Fire Evacuation and Rescue Guidance System**, a reproducible simulation-based hackathon PoC using actual oneM2M and ETSI MEC implementations. Repository and checkout name: **fire-route**. Do not claim certified fire detection, real occupant positioning, or guaranteed safe evacuation.

Selected scenario: the user's fire_evac engine (floors 1–10 plus roof, 162 hazard zones), preserved under simulator/scenarios/fire_evac/. Keep its engine/configuration unchanged. The user subsequently authorized both fixed-origin and moving-resident modes and delegated unsupplied geometry/population choices. Follow SCENARIO.md, EVACUATION_MODEL.md and fixtures/evacuation_assumptions.json: these are explicit added assumptions, never supplied fire-model rules or measured data. The existing three-floor runs remain regressions. Never convert fire index to temperature or label assumed human behavior/geometry as validated reality.

Read this file, README.md, then every specification in docs/ before changing architecture or implementation. Functional authority is docs/PRD.md; protocol and module contracts are in docs/ARCHITECTURE.md; phase names P0–P4 are defined only in docs/ROADMAP.md. docs/STATUS.md is the single progress record. docs/SOURCES.md distinguishes user-confirmed requirements, inspected sources, drafts, and missing evidence.

The latest explicit user instruction controls the authorized scope. Do not introduce an additional phase approval request when the user has already authorized that work. A documentation-only task authorizes no service implementation, deployment, push, or PR creation.

## Working rules

- Inspect existing code, configuration, documents, Git status, and applicable instructions before editing. Preserve team members' uncommitted work and unrelated files; never overwrite or delete them to simplify a task.
- Work in small reviewable changes on feature/* branches from main. Team members use individual clones/worktrees and local Codex/IDE sessions. Do not let multiple people edit the same shared-server checkout. Follow docs/TEAM_WORKFLOW.md.
- Define module interfaces before parallel implementation. Keep backend/, frontend/, simulator/, onem2m/, mec/, infra/, tests/, and docs/ responsibilities separate. These directories are a target layout, not a claim that modules already exist.
- Add relevant automated tests for each feature and run feasible checks. Run regression tests when changing existing behavior. Record exact commands, results, unavailable environments, and remaining work.
- Never fabricate API responses, protocol support, running services, tests, latency results, compliance, or judging scores. Unavailable integration is NOT_RUN/BLOCKED; implemented but untested behavior is IMPLEMENTED_UNVERIFIED.
- Use actual CSE AE/CNT/CIN/SUB/GRP/ACP functions. A custom REST server or application database must never stand in for a CSE. Unit-test mocks must be explicitly labeled and excluded from integration evidence.
- Verify subscription verification requests, real notifications, member-level fan-out results, each display's command CIN, and independently generated ACK CINs. A successful group response is not device acknowledgement.
- Default target: Local ETSI MEC Sandbox, deployment Option C (MN-CSE hosted as a MEC App). Validate against the acquired TR-0086 revision, TR-0077, GR MEC-DEC 051, and installed code. Do not infer Option C from containers merely sharing an Ubuntu server.
- Keep the CSE's common services, MEC-IPE mapping, MEC platform lifecycle, and FireRoute risk algorithm distinct. Direct MEC HTTP calls and oneM2M-mediated MEC operations require separate labels and evidence.
- If Option C cannot run, record the actual reason and assess Option B or another verified official option. A topology change requires an ADR; retain honest deployment labels and rerun the affected tests.
- Check the installed catalog/OpenAPI and real responses before relying on MEC 013/033/046 or any other MEC service. Access to ETSILabs may require account approval; inaccessible sources or endpoints do not prove installation success.
- Do not deploy or change external/shared infrastructure unless the user has authorized that action. Do not publish, push, open PRs, or send messages unless authorized. Documentation of a future workflow is not authorization to execute it.
- Never print real passwords, API tokens, SSH private keys, or complete secret environment files. Publish .env.example only; keep .env and role-specific credentials outside Git. Use per-user SSH accounts/keys and private VPN access, with deployment privileges separated from developer privileges.
- Document every new dependency's purpose and selection reason, then pin its verified version. Avoid unused abstractions and advanced features without an acceptance test and project need.
- Record major design decisions in docs/DECISIONS.md. After each implemented feature/phase, update docs/STATUS.md with implementation state, tests, evidence, blockers, owner, and next step. Report changed files, checks/results, and unresolved issues to the user.

## Engineering and data rules

- Current local application stack: Python 3.12 (minimum 3.11), standard-library API/unittest and buildless HTML/CSS/JavaScript; Node also exports bounded source-engine traces with built-in modules (.node-version records tested 24.22.1). Node is not installed into the Python app image. FastAPI/Vue were initial proposals; justify new dependencies.
- Use a real configurable CSE implementation. Local ACME 2026.5.1 passed P0 T05, P1_ROUTES and P1_GROUP in the user's Docker environment, including actual IN-CSE resources, notifications, decisions, Group/fopt, independent simulated device ACKs and scoped ACP denials. MN-CSE/registrar, full authentication/TLS, discovery and MQTT still need verification. Use STATUS.md's evidence rather than inferring complete support.
- Local development must be possible without the shared server: use a real local CSE, or an isolated Python CSE process if Docker is unavailable. Mock-only work may cover contracts/UI/unit tests, but cannot satisfy real-CSE gates.
- The shared x86 Ubuntu server is for integration, demo, logs, and permitted Local Sandbox deployment. Raspberry Pi is an IoT/Edge endpoint; its model is unknown. Do not assume full Sandbox support on ARM64.
- Define event_id, incident_id, route_version, command_id, timestamp_utc, source, and simulation provenance as appropriate to each contract. Validate inputs, idempotence, ordering, TTL, recovery, and acknowledgement identity.
- Fire/smoke indices retain the supplied 0–100 relative meaning. The new evacuation layer declares fire>=55, smoke>=70 or collapse as assumed demo blocking policy; these are not tenability or physical visibility limits. All geometry, speed, delay, population and capacity values remain explicit uncalibrated assumptions. Temperature needs an independent source/unit; no fire-index conversion, real ppm or certified threshold may be inferred.
- Show STALE/UNKNOWN for missing or old observations and NO_VERIFIED_ROUTE when no path exists. Clear previous directions on a no-route command. Do not clear a hazard simply because a sensor is silent.
- Resident and responder permissions must be enforced in backend access checks and actual CSE ACPs, not only in UI routes. Remaining-occupant records are synthetic, responder-only, and timestamped; unknown counts remain unknown.
- Keep business logic independent of CSE and UI frameworks. Minimal persistent application state may support deduplication/outbox recovery; standards resources remain in the CSE.
- Record real/simulated input, real-CSE transport, MEC deployment option, Sandbox emulation, and missing integrations separately in logs, UI, and evidence.

## Definition of done

A feature needs code, reproducible local commands, executed relevant tests, real protocol evidence where required, and documented limitations. Evidence contains sanitized request/response headers, HTTP and oneM2M RSC, resource IDs, correlation IDs, timestamps, version/configuration provenance, and raw test output. Follow docs/TEST_PLAN.md.

Priorities: P0 environment and real CSE communication; P1 computed fire-response E2E including three displays/ACKs and two role views; P2 verified MEC deployment/interworking; P3 security, protocols, discovery, recovery and measurements; P4 complete public deliverables by 2026-11-20. Baseline role protection, multiple devices, and failure status belong in P1 and are strengthened in P3.

Do not implement every rubric row merely because it exists. Prefer working, reproducible P0–P2 flows to unverified handover, location, FL, or AI/MCP features. Documentation review success is separate from product integration success.
