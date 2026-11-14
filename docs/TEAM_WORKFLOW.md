# FireRoute team workflow and module ownership

## 1. Source integration

Target GitHub repository: fire-route; default branch: main. The user configured https://github.com/gaevalja/fire-route.git, merged the source LICENSE and pushed main (a6e3509). P0 runs on feature/p0-cse-foundation. Team membership and branch protection are still unknown; CI source has been added but no executed GitHub result or PR is claimed.

Each person uses a personal clone (or isolated worktree) with Codex/IDE. Start a feature/* branch, such as feature/<module>-<task>, from current main, make a bounded change, run relevant tests, and open a PR when authorized. Integrate through reviewed PRs. Protect main with review and required CI checks when the actual repository is configured. Do not force-push shared branches or overwrite another member's uncommitted work.

The shared server runs integration/demo from a deployment-owned checkout or pinned artifacts. Developers do not concurrently edit its worktree. Deploy a reviewed commit/digest through one deployment owner; each developer uses their own checkout for debugging. Server hotfixes must return through a reviewed source change before the next deployment.

## 2. Parallel workstreams

Roles below are assignments to fill, not assumed team size or named individuals. One person may own several roles; assign a primary owner and reviewer in the work board before implementation.

| Workstream | Owned paths | Independent early work | Integration dependency |
|---|---|---|---|
| oneM2M | onem2m/ | CSE client, AE/CNT/CIN/SUB, Group/ACP/discovery contracts | Real CSE runtime from infra; schemas from contracts |
| Risk/backend | mec/ risk core; backend/ orchestration | Graph logic, incident ordering/outbox, role read models | Client interface; simulator event contract |
| Devices/scenarios | simulator/, fixtures/ additions | Seeded temperature/smoke events, display consumers, synthetic occupants | CSE client and command/ACK contract |
| UI | frontend/ | Role views, status/ACK display with labeled contract fixtures | Versioned API/auth contract and later live backend |
| MEC/DevOps | mec/ IPE/service adapters; infra/ | Source access, guide review, x86 inventory, Option C assessment | Actual repository permission, host authorization; later CSE/E2E |
| QA/evidence/publication | tests/, docs/ | Acceptance cases, evidence format, article/video outline | Per-feature runtime evidence before claims |

The two mec/ responsibilities require separate subdirectories/owners (risk/ vs interworking/) when created. Avoid file-level overlap. Shared pyproject/lockfiles, Compose, event schemas, API schema, README and STATUS changes need a named editor/reviewer for that change.

## 3. Contracts and pull requests

ARCHITECTURE.md is the current contract source. P0 creates executable schemas and interface definitions; changes to those contracts need review by producer and consumer owners. Agree schema_version, event/command correlation, status/error states and role visibility before parallel implementation. Do not silently change payload fields in one module.

The selected scenario's rules/source manifest and frame/movement boundaries are in SCENARIO.md. Keep simulator/scenarios/fire_evac/'s seven imported files unchanged; wrappers/adapters belong outside that snapshot. An intentional user-approved model update needs recorded hashes and source regression execution. Simulator owns current-frame production; backend/oneM2M owns typed CSE acceptance; risk owns the separately agreed traversal policy; UI consumes backend/CSE state rather than running an independent authoritative scenario.

PR content must state the concrete problem/result, owned scope, contract/config changes, dependency reason/version, executed test commands/results, real-versus-simulated evidence, remaining gaps and rollback/recovery impact. A missing environment is an explicit NOT_RUN/BLOCKED check, not a green integration badge. Unit mocks are labeled.

Run fast deterministic unit/contract checks on PRs. Real CSE tests use disposable isolated resource namespaces; real MEC tests run in the permitted integration environment with secret injection, not from untrusted PR code. Required checks and secrets boundaries must be configured in the real repository before claiming CI coverage.

## 4. Environments and access

Use private Tailscale/existing VPN and individual SSH public keys. Never share passwords, SSH private keys, CSE bootstrap credentials or API tokens. Ordinary developers do not require production/demo deployment privileges. Deployment owners manage the ignored environment file and service access. Public .env.example contains placeholders only.

Local CSE resources are developer/run scoped. Shared integration uses a serialized test/deployment owner or isolated resource prefixes. Cleanup may delete only resources owned by that test run. Record ownership labels and verify before deletion; do not reset a shared CSE for convenience.

## 5. Checkpoints and merge order

- Merge P0 contracts/client/runtime first; risk, scenario and UI work may proceed independently against the agreed interface.
- Integrate sensor → notification → controller → route before Group/ACK/live views. P1 requires the complete live loop, including all three displays and baseline permissions.
- Current Phases 1/2 preserve local CSE operation while preparing portable modules/configuration and reviewing public guides. Hosted access/namespace/API/deployment work begins only under a separate Phase 3 instruction. Preserve the working local demo throughout any later permitted integration.
- P3 adds full transport/security/discovery/fault/latency evidence. P4 publication begins as an outline on day one and uses verified facts only.
- Every merged feature updates its STATUS row and links actual evidence; the integration owner reconciles concurrent ledger changes. Resolve conflicts by preserving both workstreams' results.

The documentation revision created no remote/server resources. The user subsequently created/pushed the repository. P0 adds local CI workflow source; it has not been executed/published by the agent. No PR, branch protection, server account or shared deployment is created.
