# FireRoute architecture decisions and open questions

Updated: 2026-11-11. DECIDED means a project choice is accepted; it does not mean implemented or verified. SOURCES.md records source/edition limits; STATUS.md records execution status.

## ADR-001 — Identity and safe directory change (DECIDED / directory verified)

Name: FireRoute. Full name: FireRoute: Intelligent Fire Evacuation and Rescue Guidance System. Repository and checkout: fire-route. The starter was a nested directory beneath the workspace parent; no nested Git metadata, symlinks or visible process using that directory as cwd was found, and the destination did not exist. It was renamed within the writable workspace. No Git history existed to rewrite; parent .git is empty. Configure a real repository later; GitHub owner/remote is unknown.

All existing Markdown documents are updated to the new identity. Preserve the existing fixture bytes/fixture_id for data compatibility; no service or fixture migration is performed by this documentation task. Pre-edit file hashes were saved outside the project for review.

## ADR-002 — Team integration and module boundaries (DECIDED / not implemented)

Personal clone/IDE/Codex per contributor; main plus feature/* and reviewed PRs. Shared x86 server runs integration/demo from a deployment-owned checkout/artifact; no concurrent direct editing. Adopt backend/, frontend/, simulator/, onem2m/, mec/, infra/, tests/, docs/ responsibilities from ARCHITECTURE.md. Keep current placeholder directories; create missing implementation directories only when work starts. No code/package imports currently need migration.

## ADR-003 — Local Sandbox and Option C first (DECIDED target / unverified)

Prefer the organizer-specified Local ETSI MEC Sandbox STF_685/deploy revision. First target is MN-CSE as MEC App on MEC Host (Option C), with an explicit Cloud IN-CSE registrar relationship. Separate CSE common services, MEC lifecycle, MEC-IPE mapping and risk/controller logic. Acquired TR-0086 revision review is mandatory before claiming its deployment procedure is followed. A simple local CSE remains the P0/P1 development path.

If C is unavailable, preserve the failure and assess official Option B first, or another verified official option. Record actual topology/permissions and affected tests; never silently relabel it C. The current full guide and repository remain inaccessible/unacquired. Plan fallback checkpoints for Nov 12/16; no server deployment is authorized by a documentation change.

## ADR-004 — Environment roles and access (DECIDED plan / unverified hardware)

Personal PCs support independent local development. Shared x86 Ubuntu 24.04 planning size is 4–6 vCPU, 12–16 GB RAM, SSD >=100 GB; not official minimums. Verify exact Sandbox requirements and actual capacity. Raspberry Pi is an optional AE/sensor/display/fault-test endpoint; model and specs unknown. Full Sandbox ARM64 support is not assumed. Use private VPN, per-person SSH public keys, least privilege and separate deployer permissions.

## ADR-005 — Core contracts, evidence and scope (DECIDED / not implemented)

Retain F01–F19 and T01–T15 traceability; add temperature, synthetic occupants, deployment/registration and clearing/contract tests. Keep the original graph and baseline/A-block/no-route behavior. Commands and independent ACKs are separate CSE resources. Add durable deduplication/version/outbox recovery and role-filtered timestamped occupant data. Internal application contracts are proposals, never fabricated standard API responses.

Use docs/STATUS.md as the sole progress record; do not create a second root STATUS.md. Keep actual CSE/MEC tests separate from unit mocks and documentation checks. Evidence must show implementation/deployment provenance, real responses and measured timing. Raw evidence remains ignored; future publication curates sanitized artifacts.

## ADR-006 — Deadline and rubric selection (DECIDED scope / source inspected)

Use P0 environment/CSE, P1 actual fire-response E2E, P2 MEC deployment/interworking, P3 hardening/measurements, P4 all submissions, completed by Nov 20. The former detailed phases are regrouped rather than dropped: reconnaissance/foundations/CSE → P0; routing/group/UI → P1; MEC → P2; security/protocols/discovery/fault/metrics → P3; publication → P4. Advanced handover/location/semantics/agent/FL are conditional scope.

Original rubric now inspected: 17 Expert cells and relevant prerequisite tiers. Prioritize selected rows listed in RUBRIC.md, with no guaranteed score. Label discovery/FCNT, single MEC service and simple app deployment are lower-tier results until additional Expert conditions are demonstrated. Preserve this distinction in article/video/interviews.

## Open technical decisions

| Topic | Working proposal | What must be verified / responsible lane |
|---|---|---|
| CSE | Configurable adapter; ACME candidate supporting MN-CSE | Installed version/plugins/release, real SUB/fopt/ACP/MQTT and registrar behavior / oneM2M |
| Runtime | Python 3.12, FastAPI/pytest; Vue 3/TypeScript/Vite | Runtime download/package access, compatibility and actual lockfiles / infra + owners |
| CSE execution | Compose where supported, process alternative | Docker socket/network/port capabilities; host Python currently 3.10 / infra |
| GitHub | fire-route, main, feature/* and PRs | Owner/remote, membership, protection/CI and deploy permissions / integration owner |
| Cloud IN-CSE | Separate registrar role | Actual host/owner/credentials/POAs; label same-host simulation / oneM2M + infra |
| TR-0086 / Sandbox | Official compatible revision | Full guide, ETSILabs approval, pinned deploy commit, actual lifecycle/orchestration / MEC |
| MEC-IPE | Official provided compatible bridge first | Placement/model, implemented operations, catalog/OpenAPI incl. MEC 013/033/046 / MEC |
| Application state | Minimal persistent dedup/outbox or CSE recovery | Concurrency/retention/crash recovery; choose smallest proven store / backend |
| Timing policy | Configurable TTL/skew/ACK/retry | Demo values and boundary tests before P1; clock method before metrics / backend + QA |
| Temperature | Typed synthetic degC collection | Any additional blocking rule requires a declared demo policy / simulator + risk |
| Occupants | Synthetic zone/count data | Seed/scenario/reset/null handling and role policy / simulator + backend |
| Raspberry Pi | Endpoint only | Actual model/architecture/OS, network, sensor/display hardware / IoT |
| Submission | GitHub/article/video/presentation by Nov 20 | Exact cutoff/timezone, platform/formats/durations and license files / publication |

Every future decision records alternatives, evidence, owner, date, impact and tests. Unknown access or runtime behavior remains unknown rather than becoming a default success.
