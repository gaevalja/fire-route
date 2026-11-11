# P0 implementation slice — actual CSE communication

Started 2026-11-11 on feature/p0-cse-foundation from a6e3509. The working tree was clean. GitHub main/remote and the Apache-2.0 LICENSE now exist; earlier reconnaissance statements are historical.

Checkpoint: the user executed make p0-smoke successfully on 2026-11-11. Actual run evidence/20261111-100438Z-d1cfa0f4/ passes T05 on ACME 2026.5.1 / Python 3.12.16. The original startup adapter bug is resolved; post-test shutdown, shared-profile security and fresh-clone/CI reproduction remain open. STATUS.md contains the exact evidence and limitations.

## Scope

1. Add a dependency-free Python protocol core: validated configuration/synthetic sensor contract, strict HTTP oneM2M client, and durable subscription receiver.
2. Register namespaced sensor/controller/display/application AEs and CNTs on an actual CSE, with actual returned AE IDs. Prove telemetry CIN read-back and matching SUB verification/notification (T05). Do not implement a CSE.
3. Supply a local isolated ACME CSE and smoke-runner Compose profile, a process-based alternative, automatic unit tests and an actual-CSE integration runner. Capture sanitized actual evidence and fail/report BLOCKED if infrastructure is unavailable.
4. Update README, environment examples, decisions, test commands and STATUS with executed results. No push, PR, shared-server deployment, UI or MEC implementation in this slice.

## Confirmed constraints and choices

- The agent sandbox has Python 3.10.12, denies AF_INET socket creation/local bind and Docker socket access, and cannot resolve PyPI. Product runtime remains Python >=3.11, target 3.12. Portable unit checks may execute on host Python 3.10; that does not prove the target runtime or real CSE integration.
- ACME package 2026.5.1 is listed on the inspected PyPI release page. The website/master reports 2026.05.3; do not assume those are the same artifact. Pin the published package and record its actual installed version/dependencies in the CSE runtime metadata.
- Use a standalone IN-CSE for the isolated P0 profile. MN-CSE requires registrar settings; the Option C/MN-to-IN deployment remains P2 and is not claimed by this profile.
- The first client/receiver needs only Python's standard library; defer FastAPI to the application API phase. This keeps protocol and schema tests runnable without package downloads. Tests use unittest and remain compatible with a later pytest runner.
- Keep bootstrap admin, sensor and controller identities separate in resource operations. HTTP-only development and header identity checks are explicitly a private local profile, not full authenticated/TLS security evidence.

## Gates

Unit: invalid inputs, malformed/mismatched HTTP/RSC/request IDs, redirect rejection, callback verification, duplicate/conflicting callbacks, persistence, namespaced resource ownership and secret redaction.

Actual CSE: real base/type/release read-back; actual AE IDs and resource IDs; SUB verification; stored synthetic telemetry CIN and matching durable notification. No mock is selectable in this path.

If the agent cannot run the actual profile, finish and review the runnable implementation, save the genuine blocked result, and request the user's local-terminal run of the prepared command. Never convert successful unit mocks into T05 PASS.

## Independent P1 preparation completed at the unit layer

ROADMAP.md permits pure risk/graph work alongside the CSE foundation. While awaiting the actual user-terminal CSE run, implement only the deterministic graph and synthetic smoke-blocking function under mec/risk/, with T01–T03 unit assertions and malformed/no-route boundary cases. This is local edge-application logic, not MEC API integration/deployment. Do not claim the complete P1 controller, persistence, Group/ACK or live dashboards are finished.

## P1 handoff after actual T05 PASS

The real-CSE communication dependency is satisfied. Preserve the source run and use T05 as a regression gate. The next bounded slice is now implemented: backend/incidents.py handles durable ordered incident state; onem2m/decisions.py persists/reconciles hazard/route CINs; backend/p1_routes.py drives the actual notification-to-route gate. ARCHITECTURE.md's schema_version=1 envelope and event_id/incident_id/route_version linkage are retained; route versions advance only for accepted new work. Execute make p1-routes for the container gate or make test-routes for an existing CSE with a reachable callback.

Acceptance for that slice: compute EXIT_A from the original graph; receive actual smoke at F2_A and persist EXIT_B excluding F2_A; block both stairwell nodes and persist NO_VERIFIED_ROUTE with null exit/empty path. Duplicate delivery must create no additional route version/CIN; older per-sensor work must not overwrite newer state. Preserve pending writes across a controlled process failure and reconcile actual CSE resources before retrying a CREATE. Record each integrated result independently from the existing pure graph tests.

The initial 80-unit route checkpoint was followed by an actual P1_ROUTES PASS at evidence/20261111-103437Z-cff86001/: real A/B/no-route records, four sensor notifications and two ACP denials. The agent's Python 3.10 limitation remains separate from that user execution. Full P1/process recovery/automatic resume/controller stale guidance remain incomplete.

The Group/device slice now passes actual P1_GROUP at evidence/20261111-115340Z-34c169f6/. It verifies real aggregate/member identities and CINs, three independent display processes/command SUBs/ACK writers, controller ACK SUBs, no-route clearing and additional scoped CSE denials. Three deliveries complete; after stopping display-c, three command CINs exist but only two ACKs and INCOMPLETE. The initial mid canonicalization mismatch was fixed using actual local container IDs with exact comparison retained. Four regressions bring the full unit suite to 107 PASS. No dependency was added. Device-local expiry clearing has unit coverage; live expiry, full controller/dispatch restart recovery and authenticated deployment remain future work.

This completes the requested local backend checkpoint through actual Group/device ACKs. The user requested committing/publishing the feature branch before further features. Subsequent work: authenticated role APIs/live dashboards with synthetic occupants, complete stale/recovery handling and MEC deployment/interworking. Full P1/T07 authentication and broader T20/T12 coverage remain incomplete. CSE shutdown diagnosis/default-secret replacement remain open infrastructure work; neither is an excuse to replace real CSE traffic with mocks.
