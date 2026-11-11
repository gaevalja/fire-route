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

The core Docker Compose profile now passes actual local T05 on ACME 2026.5.1 / Python 3.12.16. Additional profiles for full fire-response E2E and optional MEC integration remain future work. The CSE-only profile runs without MEC credentials. The full Sandbox may have its own official deployment tooling; do not assume it can be placed in an arbitrary Compose service. mec/risk/ is local deterministic graph code, not an installed MEC service.

Alternative when Docker is unavailable: isolated Python >=3.11 (3.12 proposed) running the selected real CSE and backend processes, a separately configured MQTT broker when needed, and frontend dev tooling. Verify Python/CSE compatibility and dependency pins first. Unit tests, pure routing and labeled UI previews can proceed before CSE/MEC access; they do not satisfy integration gates.

Implemented core commands: make test-unit, make compose-check, make up-core, make test-cse, make p0-smoke and make down. make p0-smoke, make p1-routes and make p1-group have actual local PASS records; make test-routes/make test-group select a configured CSE/Python >=3.11 instead. The group runner spawns three independent Python processes, not three physical nodes, with own callbacks on base bind port+1/+2/+3. Internal defaults are 8000–8003; no extra host ports are exposed. Each profile uses its own service name/run-owned resources. Run one smoke profile at a time; none requires MEC credentials. make down handles all three profiles and preserves volumes. MEC/shared deployment and shared CSE reset/cleanup remain unimplemented.

## 3. Local observations and subsequent verification (2026-11-10–11)

This workspace is WSL2, not evidence of a configured shared Ubuntu server. Earlier read-only agent inventory observed Python 3.10.12, Node 24.22.1, npm 11.19.1 and uv in PATH; Python >=3.11 was not found in PATH. Docker/Compose CLIs exist; direct agent access to the Docker API is restricted. No actual .env was present at reconnaissance. P0 now adds pyproject metadata, source modules, Compose and tests.

The user's terminal can build/run Docker. Actual run evidence/20261111-100438Z-d1cfa0f4/ now verifies T05 with ACME 2026.5.1, Python 3.12.16, x86_64, standalone IN-CSE and release 4. It does not establish shared-server/MEC readiness. The smoke runner passed before Compose stopped the services; post-test CSE exit 137 needs state/shutdown investigation. The default CSE-secret warning remains a shared-deployment blocker; the isolated local profile is not the full security profile. make up-core keeps the CSE running for further local development, while make p0-smoke intentionally stops its stack after the selected runner exits.

The project checkout is now fire-route beneath the workspace parent. At reconnaissance the parent .git was empty and no project Git history existed. The user subsequently initialized the nested repository, merged its Apache-2.0 LICENSE and pushed main to https://github.com/gaevalja/fire-route.git (a6e3509). P0 work is isolated on feature/p0-cse-foundation. Branch protection/team/deployer permissions remain unverified.

## 4. Configuration inventory

.env.example and backend/config.py now implement the local P0 CSE/callback/time-budget settings. Environment variables override literal .env assignments without shell evaluation. The P0 runner accepts only real CSE + unavailable MEC + simulator input. Role/registrar/MQTT/MEC integration keys below remain proposals/reserved settings, not implemented options of a CSE binary. Delivery retry/TTL/ACK budgets are declared for P1; P0 only applies request/startup/notification deadlines and resource retention.

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
