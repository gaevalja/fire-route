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

Selected source: simulator/scenarios/fire_evac/ contains a byte-preserved portable copy of the user's ten-floor source. make test-scenario runs its pure-engine tests; its index.html is the original standalone preview. Neither command is a CSE/MEC profile. make demo-up and p1-dashboard remain legacy three-floor commands; the new selected-profile commands are listed next.

Dual-mode implementation update: host Node 24.22.1 (recorded in .node-version) now exports a bounded .runtime/fire-evac-trace.jsonl; it is generated synthetic data, ignored by Git/build context and mounted read-only into Python profiles. make scenario-preview runs both modes offline. make p1-scenario provides actual frame/core/Group checks; make p1-scenario-dashboard provides actual authenticated HTTP/CSE checks. These gates are prepared, not runtime PASS from configuration alone. make demo-scenario-up exports 1800 source seconds by default and serves the selected app on 127.0.0.1:3001 (SCENARIO_HOST_PORT override). It shares only the private hashed auth file, role setup and standard CSE services; full moving data is never a browser CSE credential. Use make demo-scenario-logs and make down for all profiles. Run one integration profile at a time.

The local Compose profiles pass T05, routes, Group/devices and authenticated role HTTP/CSE scenarios on ACME 2026.5.1 / Python 3.12.16. Browser QA, full recovery and MEC integration remain future work. These profiles run without MEC credentials. The full Sandbox may have its own official deployment tooling; do not assume it can be placed in an arbitrary Compose service. mec/risk/ is local deterministic graph code, not an installed MEC service.

Alternative when Docker is unavailable: isolated Python >=3.11 (3.12 proposed) running the selected real CSE and backend processes, a separately configured MQTT broker when needed, and frontend dev tooling. Verify Python/CSE compatibility and dependency pins first. Unit tests, pure routing and labeled UI previews can proceed before CSE/MEC access; they do not satisfy integration gates.

Implemented core commands: make test-unit, make test-frontend, make compose-check, make up-core, make test-cse, make p0-smoke and make down. make p0-smoke, make p1-routes, make p1-group and make p1-dashboard have actual local PASS records; make test-routes/make test-group select a configured CSE/Python >=3.11 instead. The group runner spawns three independent Python processes, not three physical nodes, with own callbacks on base bind port+1/+2/+3. Internal defaults are 8000–8003; no extra callback host ports are exposed. Each profile uses its own service name/run-owned resources. Run one integration profile at a time. make down handles all profiles and preserves volumes. MEC/shared deployment and shared CSE reset/cleanup remain unimplemented.

make demo-up prepares private access files and starts CSE/app persistently. Open http://127.0.0.1:3000 and read the selected role code privately from .runtime/access-codes.json in an editor. No npm install/build is required; Node is only needed for make test-frontend. make p1-dashboard starts a separate real HTTP test service and stops the stack after its checks, including a 31-second expiry wait. Do not run it concurrently with a manual demo in the same Compose project. See ROLE_API.md and README.md for role isolation and controls.

Local settings: APP_HOST_PORT defaults to 3000; Compose sets APP_PUBLIC_ORIGIN to http://127.0.0.1:<port>, APP_BIND_HOST=0.0.0.0 inside the private container and APP_AUTH_FILE=/run/fire-route/auth.json. The host publication remains 127.0.0.1 only. Direct Python execution defaults to 127.0.0.1 binding and requires Python >=3.11. `.runtime/access-codes.json` stores private plaintext operator codes; `.runtime/auth.json` stores hashes. Both are mode 0600 and ignored by Git/Docker build context; the app mounts only the hash file read-only. Existing files are validated and not silently replaced. Role codes are not complete CSE-originator authentication or shared-server TLS.

## 3. Local observations and subsequent verification (2026-11-10–11)

This workspace is WSL2, not evidence of a configured shared Ubuntu server. Earlier read-only agent inventory observed Python 3.10.12, Node 24.22.1, npm 11.19.1 and uv in PATH; Python >=3.11 was not found in PATH. Docker/Compose CLIs exist; direct agent access to the Docker API is restricted. No actual .env was present at reconnaissance. P0 now adds pyproject metadata, source modules, Compose and tests.

The user's terminal can build/run Docker. Actual run evidence/20261111-100438Z-d1cfa0f4/ now verifies T05 with ACME 2026.5.1, Python 3.12.16, x86_64, standalone IN-CSE and release 4. It does not establish shared-server/MEC readiness. The smoke runner passed before Compose stopped the services; post-test CSE exit 137 needs state/shutdown investigation. The default CSE-secret warning remains a shared-deployment blocker; the isolated local profile is not the full security profile. make up-core keeps the CSE running for further local development, while make p0-smoke intentionally stops its stack after the selected runner exits.

The project checkout is now fire-route beneath the workspace parent. At reconnaissance the parent .git was empty and no project Git history existed. The user subsequently initialized the nested repository, merged its Apache-2.0 LICENSE and pushed main to https://github.com/gaevalja/fire-route.git (a6e3509). Verified P0/P1 backend checkpoint 80f6e87 was pushed on feature/p0-cse-foundation; current role work is on the stacked feature/p1-role-dashboards branch. Branch protection/team/deployer permissions remain unverified.

## 4. Configuration inventory

.env.example and backend/config.py implement local CSE/callback/time-budget settings. Environment variables override literal .env assignments without shell evaluation. Runtime profiles accept only real CSE + unavailable MEC + simulator input. Bootstrap uses actual returned role AE identities; local API access-file settings are implemented above. Registrar/MQTT/MEC integration keys below remain proposals/reserved settings, not implemented options of a CSE binary. P1 applies declared TTL/skew/ACK budgets; P0 applies request/startup/notification deadlines and resource retention.

| Group | Current/proposed application configuration | Required validation |
|---|---|---|
| CSE | CSE_BASE_URL, CSE_BASE_RESOURCE, CSE_RELEASE, CSE_ORIGINATOR; proposed CSE_TYPE and CSE_ID | Actual base/ID/type/release and JSON encoding; map to selected implementation settings |
| Roles | Actual bootstrap/sensor/controller/display/resident/responder/occupancy AE identities; separate local API role codes; IPE identity reserved | Current app retains bootstrap admin server-side for reset/setup; no admin in browser/device processes; full credential separation/authentication still pending |
| Registration | Proposed registrar URL/base/CSE-ID and credential reference | MN-to-IN relationship over Mcc, POAs and authorization |
| Notification | NOTIFICATION_PUBLIC_URL and proposed per-display callback URLs | Reachable from CSE, SUB verification, protocol response |
| MQTT/TLS | CSE_MQTT_URL; proposed CA path, broker user/secret reference, TLS verify flags | Actual broker/CSE binding; no certificate-verification bypass for shared demo |
| MEC | MEC_BASE_URL, MEC_SERVICE_API, MEC_ACCESS_TOKEN; proposed app instance ID, catalog URL, IPE identity, deployment option | Values from acquired guide/catalog, not guessed endpoint paths |
| Modes | Implemented: CSE_MODE=real, MEC_MODE=unavailable, DEMO_MODE=simulator | Runtime rejects other modes; unit transport fixtures are separate, never an actual-CSE gate |
| Provenance | Proposed MEC_ENVIRONMENT=local_sandbox/hosted_sandbox/assigned_platform/unavailable and input data_origin | Distinguish actual endpoint communication from emulated network data |
| Scenario | SYNTHETIC_SMOKE_THRESHOLD=70; implemented TTL/skew/ACK/retry/retention settings; seed extension reserved | Explicit demo values and units in metadata, tested boundary behavior |
| Isolation | Proposed resource namespace/run ID and service ports | No resource collisions between developers or destructive shared cleanup |

Store actual values only in ignored .env/secrets outside Git. Separate local example defaults from shared-server configuration. CSE callback URLs inside a container network must use reachable service addresses; 127.0.0.1 refers to the current process/container host, not a remote peer. Public callbacks must not be opened merely to make a test pass; use an authorized reachable private path or record the limitation.

## 5. Access and deployment privileges

- Use Tailscale or existing VPN for private access, per-person SSH accounts and public-key authentication. Do not share SSH passwords/private keys.
- Give ordinary developers access to their own workspaces; restrict deployment/runtime secrets and service-management permissions to deployment roles.
- Allow only needed private network flows. TLS, authenticated originators, backend permissions and CSE ACP remain required in addition to VPN access.
- Obtain explicit authorization before modifying shared/external infrastructure. This revision performs no VPN enrollment, account creation, deployment or network change.
- Keep raw logs/evidence private until sanitized. .gitignore already ignores .env and evidence/*; P4 must explicitly curate publishable evidence without broadly unignoring secret-bearing runs.

See TEAM_WORKFLOW.md for source integration and DEPLOYMENT.md for access/installation gates.

## Natural-hazard verification profile (2026-11-14)

make hazard-trace exports an ignored .runtime/fire-evac-hazards.jsonl from the unchanged source, with HAZARD_SEED=59, HAZARD_WIND=5 and HAZARD_SECONDS=900 by default. It does not overwrite .runtime/fire-evac-trace.jsonl used by the interactive demo. make hazard-preview is offline only; make p1-hazards runs scenario-hazards on the existing isolated real-CSE Compose network, callback ports 8000–8003 internally, with no new host port or credentials. The gate recreates its containers to refresh the trace mount and stops its stack afterward. Run it serially with other profiles; CSE volumes/evidence are retained. Current agent host Python 3.10.12 and denied Docker API access cannot execute the real profile; use the user's Python 3.12 Compose environment. No new dependency or MEC deployment is added.

## Current profile policy and local lifecycle tools (ADR-019)

Keep WSL2/Docker/ACME as the development environment. A shared x86 server or ETSILabs account is not required for current Phases 1/2. Hosted login/namespace/admin descriptions are user supplied and unverified. No Hosted connection/deployment is performed until a separate Phase 3 instruction; optional Local Sandbox installation is not a prerequisite.

FIREROUTE_PROFILE=local is the only active application profile. The inactive hosted_pending planning example is rejected by Settings before connection setup; it cannot silently become a working Hosted client by filling blank URLs. Host CSE_BASE_URL and Docker CSE_CONTAINER_BASE_URL are separate. CSE_ORIGINATOR is an external header identity setting, not complete authentication. MEC_BASE_URL/MEC_SERVICE_API/MEC_ACCESS_TOKEN remain reserved settings without an API client or verified authentication scheme. Use ignored .env/credential files, never Git. Examples are infra/profiles/local.env.example and hosted.env.example.

The CSE launcher creates/reuses /data/fire-route.secret with 0600 permissions and stages the internal key into its managed runtime configuration, leaving the source and prior managed files intact. It refuses symlink/world-readable/invalid keys. No key value is logged. This startup change is not yet actual-runtime verified; earlier CSE PASS records retain their old config hash. make diagnose-cse observes only; make local-stability intentionally stop/starts the local CSE while preserving volumes and checks actual marker persistence, stable config and shutdown evidence. No stop signal is changed on inference alone.

The analysis profile executes python -m mec.risk.worker with stdin JSONL ScenarioFrame input and stdout application-result envelopes, no network or data/credential mounts, and a read-only filesystem. Explicit assumptions are supplied by --assumptions/RISK_ASSUMPTIONS_FILE only from a validated local file; this is a portable component, not a verified Hosted deployment. Consumer adapters must honor REJECTED/UNKNOWN, duplicate/no-fresh-result and source UTC/TTL, and enforce responder privacy on per-person output.
