# FireRoute architecture decisions and open questions

Updated: 2026-11-11. DECIDED means a project choice is accepted; it does not mean implemented or verified. SOURCES.md records source/edition limits; STATUS.md records execution status.

## ADR-001 — Identity and safe directory change (DECIDED / directory verified)

Name: FireRoute. Full name: FireRoute: Intelligent Fire Evacuation and Rescue Guidance System. Repository and checkout: fire-route. The starter was a nested directory beneath the workspace parent; no nested Git metadata, symlinks or visible process using that directory as cwd was found, and the destination did not exist. It was renamed within the writable workspace. No Git history existed to rewrite; parent .git is empty. That was the pre-upload inventory; the user later configured gaevalja/fire-route and pushed main. ADR-007 records the current branch/base.

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
| GitHub | gaevalja/fire-route; main and feature/* | Membership, branch protection, actual CI runs and deploy permissions / integration owner |
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


## ADR-007 — P0 actual-CSE foundation (DECIDED / local T05 verified)

User authorized development on 2026-11-11. Base main a6e3509 is pushed to gaevalja/fire-route with Apache-2.0 LICENSE. Work branch: feature/p0-cse-foundation. Earlier statements of unknown Git/owner describe the pre-upload inventory.

Use the published acmecse==2026.5.1 package for the isolated development CSE; website/master 2026.05.3 is not assumed equivalent. Standalone IN-CSE avoids inventing unavailable registrar settings; MN-CSE/Option C remain P2. Each run uses owned expiring resource names, actual returned AE IDs, an ACP reference by actual resource ID, a real SUB handshake and CIN read-back/callback comparison.

The HTTP binding client, notification persistence and sensor contract use the standard library. This removes external package requirements for offline core tests and keeps business logic independent of a web framework. Defer FastAPI to P1 application APIs; use unittest now, compatible with later pytest selection. Python product runtime remains >=3.11/3.12 target. Host Python 3.10 unit execution is a compatibility check only.

Build dependency setuptools==80.9.0 provides explicit package discovery/metadata without adding an application runtime dependency; its release/minimum Python were checked on PyPI. The CSE package is a necessary external runtime implementation, not a custom CSE. Record its actual installed dependency set. The Python Docker base is a 3.12 family tag; an immutable image digest/transitive lock is still required before claiming a fully locked deployment. Direct package/image build and target runtime remain unavailable in the agent sandbox. The user's later successful T05 run verified actual ACME 2026.5.1 / Python 3.12.16; its installed distribution list is captured in the original meta.json. This does not verify a separately installed FireRoute wheel or all CSE capabilities.

Confirmed sandbox limitations: AF_INET/socket bind and Docker Unix socket denied; PyPI DNS unavailable. Do not lower standards by substituting a fake CSE. Finish/review the runnable profile, retain real BLOCKED output, and obtain a user-terminal or CI actual-CSE run. HTTP-only header identity is an isolated development limitation, not completed security/Expert evidence.


## ADR-008 — Independent graph work while actual CSE execution is blocked

Follow ROADMAP parallel lanes: implement the pure Dijkstra/synthetic-smoke policy under mec/risk/ while awaiting the user's actual-CSE run. T01 and T03 are unit-level requirements; T02's algorithm subcase can PASS while its CSE-persistence subcase stays NOT_RUN. This is the project's actual graph algorithm, not a fixture feasibility script or a MEC mock. No controller/event ordering, route CIN, fan-out, ACK or UI completion is inferred. Packaging includes the canonical fixture as a data file; the existing fixture bytes remain unchanged. Package installation itself is unverified in this sandbox.

## ADR-009 — CSE config filename and visible startup failures (DECIDED / actual startup verified)

The user's initial 2026-11-11 run built the actual CSE image, printed ACME 2026.05.1, and exited (0) before becoming healthy. The original adapter passed an absolute --config path together with CLI --headless. Inspected upstream Configuration.initDirectories rejects any directory in that argument; its early error printer suppresses output when CLI headless is set. This was the source-supported explanation; the subsequent real package run verified the corrected startup path without requiring a version change or data deletion. The exact installed source has not been extracted.

Stage the bundled config as /data/fire-route-<SHA256>.ini and pass its basename with -dir /data. Create only an owned content-addressed file; preserve user acme.ini, previous managed configs and CSE database volumes. Reuse identical files and reject modified managed files rather than overwrite them. Set [console] headless=True in the config and omit CLI --headless so early configuration errors are visible. Emit only safe version/config-filename startup metadata, without config contents.

Keeping the original absolute argument is incompatible with the inspected implementation. Blindly switching CSE versions or deleting data volumes would not address the known adapter error. Seven focused regressions pass (62 total units); Compose parsing and compilation pass. Owner: infrastructure/oneM2M lane. The actual user-terminal rerun reached Healthy and passed T05; original evidence is evidence/20261111-100438Z-d1cfa0f4/. Post-test exit 137 remains a separate shutdown issue and does not establish successful recovery.

## ADR-010 — Durable ordered incident decisions before Group dispatch (DECIDED / actual route gate verified)

After actual T05 PASS, implement the next dependency: sensor notification → ordered incident state → computed hazard/route → actual CSE CIN persistence. Reuse the verified P0 callback/client and original graph; add no runtime dependency. SQLite stores application deduplication, per-sensor sequence/time/binding, per-incident version/blocks and a persistence outbox in one transaction. It does not expose oneM2M services or replace CSE resources.

Persist event IDs with content digests, reject conflicting reuse/sensor rebinding and ignore older, stale or excessively future observations. Replays reuse the existing decision; a lower smoke reading never clears a block. Initial policy is explicitly synthetic; temperature retains degC and has no invented fire threshold. A stored graph/policy/source fingerprint requires explicit migration when recovery rules change.

Decision publication uses deterministic event-derived resource names, GET before CREATE and actual read-back before marking the entry persisted. A partial or ambiguous CREATE remains pending; a later reconciliation finds any committed CIN instead of blindly repeating POST. This outbox tracks decision persistence only; future command delivery and ACK completion need their own state. P1-scoped ACPs are opt-in during bootstrap so P0's verified default behavior is preserved: controller creates/reads decisions, resident reads routes, responder reads routes/hazards. Actual denial/authentication proof must still be tested.

The initial 18 new units passed (80 total). User run evidence/20261111-103437Z-cff86001/ subsequently passed actual P1_ROUTES, including three hazard/route records and two CSE denials. The agent's direct runtime remains blocked; that limitation is distinct from the actual user execution. Full restart/service resume, periodic controller stale guidance, role APIs/UI and MEC remain subsequent work. Owner: backend/oneM2M.

## ADR-011 — Actual Group with independent display ACK producers (DECIDED / isolated actual gate verified)

Implement a real CNT-member GRP/fopt command followed by three independently generated ACK CINs. The aggregate has OK status while successful member CREATEs have CREATED status in the inspected official TR-0025 example. Validate request correlation, member count/parent IDs, distinct created CINs and actual member read-back; never interpret fan-out success as display application.

Use three Python spawn processes inside the local runner container, each with its own actual AE-ID, command SUB/receiver, persistent display state and ACK writer. The coordinator passes no admin credentials to these processes and never generates their ACKs. Separate containers/physical devices are unnecessary for this first simulated-device gate; do not claim physical IoT hardware, network fault isolation or MEC deployment from these processes. Process PIDs, AE IDs and individual sanitized wire logs are evidence.

Display schema_version=1 adds explicit guidance_status to the previously proposed command contract before its first implemented use. Validate action/exit/nullability/UTC expiry; persist command digests, version high-water state and ACK outbox. Duplicates reuse an ACK; older/expired/future/foreign-source commands cannot replace valid directions. No-route and local expiry clear the displayed exit. Controller ACK subscriptions use a decoder bound to each actual reference; validate device/incident/event/version/command and actual ACK CIN read-back. New child-type ACP restrictions allow SUB CREATE while denying fabricated command/ACK CIN writes; live enforcement remains to be tested.

The actual make p1-group gate passed in evidence/20261111-115340Z-34c169f6/: three complete A/B/no-route deliveries, then three stored command CINs but two ACKs/INCOMPLETE after stopping display-c. Missing ACKs stay outside complete counts. Original group/member/callback/ACK/state evidence passed 50 independent audit checks. Authentication/TLS, full restart/dispatch recovery, live roles and MEC remain separate gaps. The full unit suite now passes 107 tests, including the late worker-error guard and ADR-012 regressions. No runtime dependency or external/shared deployment was added.

## ADR-012 — Local Group member identity matches CSE canonical representation (DECIDED / actual rerun verified)

The first actual P1_GROUP attempt, evidence/20261111-114816Z-fbc3f740/, received HTTP 201 / RSC 2001 and an actual three-member GRP. The request used SP-relative /<cse-id>/<CNT-ri> members; the observed ACME 2026.5.1 response stored the same local members as bare CNT resource IDs. Generic ensure correctly refused the unequal strings, so the first run stopped before fan-out/device application.

Use the actual local command CNT IDs directly in this local Group. Keep exact ensure/read-back comparisons and require three distinct IDs; do not ignore mid, overwrite unknown resources or strip arbitrary remote prefixes. Remote Group membership is outside this local slice. Four regressions exercise canonical CREATE/reuse, changed-member rejection, duplicate-ID rejection and bad member-count rejection. The subsequent actual Group/ACK rerun passed. Owner: oneM2M/backend. This fixes address representation without relaxing membership identity or changing the CSE implementation.
