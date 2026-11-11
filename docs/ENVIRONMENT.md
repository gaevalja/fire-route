# FireRoute environments and configuration

## 1. Environment roles

| Environment | Role | Boundary |
|---|---|---|
| Personal PC | Per-person Codex/IDE clone, unit/module tests, real local CSE | Works without shared server; no concurrent editing of server checkout |
| Shared x86 Ubuntu | CSE, permitted Local MEC Sandbox, backend, frontend, integration tests, monitoring/logs | Integration/demo environment; deploy reviewed artifacts/commit |
| Raspberry Pi | Sensor/simulator, oneM2M AE, MQTT publisher, display/actuator simulation, disconnect/recovery tests | Model/RAM/storage/OS/CPU architecture unknown; not default main server |
| Cloud IN-CSE registrar | Separate logical registrar for MN-CSE | Actual endpoint/owner/access not supplied; same-host simulation must be labeled |
| Hosted Sandbox reference | Evaluate documented APIs when permitted | Limited platform customization; not the preferred deployment target |

Provisional shared-server starting point: Ubuntu 24.04, x86, 4–6 vCPU, 12–16 GB RAM, SSD >=100 GB. These are team planning values, not official minimums or a guaranteed fit. Validate the exact Sandbox revision's nested runtime, virtualization/network, disk, CPU/RAM and port requirements from its deployment guide and actual results. Co-locating services requires measured capacity. Full ARM64 support is unverified.

## 2. Local development paths

Preferred future path: pinned Docker Compose profiles for core real-CSE development, integration tests and optional MEC integration. A CSE-only profile must run without MEC credentials. The full Sandbox may have its own official deployment tooling; do not assume it can be placed in an arbitrary Compose service.

Alternative when Docker is unavailable: isolated Python >=3.11 (3.12 proposed) running the selected real CSE and backend processes, a separately configured MQTT broker when needed, and frontend dev tooling. Verify Python/CSE compatibility and dependency pins first. Unit tests, pure routing and labeled UI previews can proceed before CSE/MEC access; they do not satisfy integration gates.

Required future onboarding commands: install dependencies, start/stop core, probe CSE, bootstrap namespaced resources, run unit/CSE/E2E tests, collect sanitized evidence, recover/restart. No Makefile, Compose file or executable setup/test commands exist yet. P0 must implement and document exact commands, including cleanup limited to the developer's test resources.

## 3. Current local observations (2026-11-10)

This workspace is WSL2, not evidence of a configured shared Ubuntu server. Earlier read-only inventory observed Python 3.10.12, Node 24.22.1, npm 11.19.1 and uv in PATH; Python >=3.11 was not found in PATH. Docker/Compose CLIs exist; docker ps showed no running containers, while image listing failed with socket permission denied. No .env, package manifest, service implementation or integration evidence is present. Recheck all runtime observations during P0; do not convert CLI presence into deployment readiness.

The project checkout is now fire-route beneath the workspace parent. The parent .git is empty and git status does not identify a repository; no Git history was found or rewritten. Configure a real personal clone/repository before applying the team Git workflow. The GitHub organization/owner and remote URL remain unknown.

## 4. Configuration inventory

.env.example currently has example CSE/MEC values only and no settings loader. Preserve it until P0 adds validated runtime configuration. The following additional keys/groups are a contract proposal, not supported options of a CSE binary.

| Group | Current/proposed application configuration | Required validation |
|---|---|---|
| CSE | CSE_BASE_URL, CSE_BASE_RESOURCE, CSE_RELEASE, CSE_ORIGINATOR; proposed CSE_TYPE and CSE_ID | Actual base/ID/type/release and JSON encoding; map to selected implementation settings |
| Roles | Proposed role-scoped originators/credential references for bootstrap, sensor, controller, each display, resident, responder, IPE | Unique least-privilege identities; setup admin excluded from runtime/browser |
| Registration | Proposed registrar URL/base/CSE-ID and credential reference | MN-to-IN relationship over Mcc, POAs and authorization |
| Notification | NOTIFICATION_PUBLIC_URL and proposed per-display callback URLs | Reachable from CSE, SUB verification, protocol response |
| MQTT/TLS | CSE_MQTT_URL; proposed CA path, broker user/secret reference, TLS verify flags | Actual broker/CSE binding; no certificate-verification bypass for shared demo |
| MEC | MEC_BASE_URL, MEC_SERVICE_API, MEC_ACCESS_TOKEN; proposed app instance ID, catalog URL, IPE identity, deployment option | Values from acquired guide/catalog, not guessed endpoint paths |
| Modes | CSE_MODE=real/mock; MEC_MODE=real/mock/unavailable; DEMO_MODE=simulator | mock restricted to unit/preview; real mode still requires runtime evidence |
| Provenance | Proposed MEC_ENVIRONMENT=local_sandbox/hosted_sandbox/assigned_platform/unavailable and input data_origin | Distinguish actual endpoint communication from emulated network data |
| Scenario | SYNTHETIC_SMOKE_THRESHOLD=70; proposed TTL/skew/ACK timeout/retry/retention and seed settings | Explicit demo values and units in metadata, tested boundary behavior |
| Isolation | Proposed resource namespace/run ID and service ports | No resource collisions between developers or destructive shared cleanup |

Store actual values only in ignored .env/secrets outside Git. Separate local example defaults from shared-server configuration. CSE callback URLs inside a container network must use reachable service addresses; 127.0.0.1 refers to the current process/container host, not a remote peer. Public callbacks must not be opened merely to make a test pass; use an authorized reachable private path or record the limitation.

## 5. Access and deployment privileges

- Use Tailscale or existing VPN for private access, per-person SSH accounts and public-key authentication. Do not share SSH passwords/private keys.
- Give ordinary developers access to their own workspaces; restrict deployment/runtime secrets and service-management permissions to deployment roles.
- Allow only needed private network flows. TLS, authenticated originators, backend permissions and CSE ACP remain required in addition to VPN access.
- Obtain explicit authorization before modifying shared/external infrastructure. This revision performs no VPN enrollment, account creation, deployment or network change.
- Keep raw logs/evidence private until sanitized. .gitignore already ignores .env and evidence/*; P4 must explicitly curate publishable evidence without broadly unignoring secret-bearing runs.

See TEAM_WORKFLOW.md for source integration and DEPLOYMENT.md for access/installation gates.
