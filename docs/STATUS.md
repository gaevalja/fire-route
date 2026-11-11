# FireRoute implementation and validation status

Updated: 2026-11-11. This is the single status file; no root STATUS.md is used.

## Current checkpoint

Development branch: feature/p0-cse-foundation, based on a6e3509. The user previously initialized/pushed main to https://github.com/gaevalja/fire-route.git and merged the source Apache-2.0 LICENSE. The user requested finishing the Group gate and checkpointing this branch. Current commit identity/status is available from git log/status; main merge, PR and shared deployment are outside this checkpoint. Agent remote connectivity currently fails GitHub DNS; publication must be confirmed from actual Git output.

**P0's actual oneM2M communication gate T05 passed** in the user's local Docker environment on 2026-11-11. The source run is evidence/20261111-100438Z-d1cfa0f4/: actual ACME 2026.5.1, Python 3.12.16, eight distinct AEs, ten CNTs, SUB verification, telemetry CIN read-back and one matching durable notification. The agent inspected the original artifacts and independently passed 17 consistency checks over 44 actual request/response records. The earlier startup failure is resolved.

**P1_ROUTES also passed** in user run evidence/20261111-103437Z-cff86001/. Original artifacts show 75 exchanges, four actual sensor notifications, three correlated hazard/route pairs (EXIT_A, EXIT_B, NO_VERIFIED_ROUTE), duplicate/outdated-event handling and two HTTP 403 / RSC 4103 ACP denials. The agent's separate audit passed 18 consistency checks. Temperature retained 22.5 degC/SYNTHETIC provenance.

**P1_GROUP passed** in user run evidence/20261111-115340Z-34c169f6/. Actual Group/fopt produced 12 command CINs. Three independent display processes generated 11 actual ACK CINs: three normal complete deliveries, then two ACKs/INCOMPLETE after display-c stopped. All available displays cleared directions for no-route. Six actual scoped CSE denials passed. The agent independently passed 50 audit checks over 137 coordinator and 42 device exchanges, child PIDs/identities and durable device state.

These results verify the isolated local backend loop, not the full PoC, fresh-clone/CI reproduction or authenticated security. Application APIs/UI and MEC integration remain unimplemented. Post-test CSE exit 137 and the default-secret warning remain open environment issues. Direct agent CSE execution remains unavailable; successful user-terminal results are the actual integration evidence.

## Implementation and verification

| Area | Implementation | Verification | Evidence / gap |
|---|---|---|---|
| Local reproducible core setup | VERIFIED for local T05 slice | User-terminal builds, healthy startup and T05 PASS | ACME 2026.5.1 / Python 3.12.16 / x86_64; fresh-clone run, immutable base/transitive lock and graceful shutdown still pending |
| Sensor contract/generator | VERIFIED for synthetic temperature/smoke round trips | T05 and P1_ROUTES PASS; T19 valid-ingestion subcase PASS, malformed contracts unit PASS | Actual 22.5 degC and smoke 90 preserve units/provenance; no physical sensor claim |
| Actual CSE HTTP client/AE/CNT bootstrap | VERIFIED for P0 primitives | Unit checks and actual T05 PASS | Eight returned unique AE-IDs, ten actual CNT IDs, read-back and real HTTP/RSC evidence |
| Scoped ACPs | VERIFIED for local positive traffic and six denials | P1_GROUP actual sensor route-write, resident hazard-read/fan-out, controller ACK forgery, device command/cross-device ACK denials PASS (403/4103) | Full T09/authentication/TLS/privacy remain pending |
| SUB receiver and durable deduplication | VERIFIED for actual T05 binding and unit durability | SUB handshake/CIN callback PASS; duplicate/conflict/persistence/concurrency units PASS | One event persisted in actual run SQLite; full live restart recovery NOT_RUN; header-only identity remains a limitation |
| Pure routing / synthetic block policy | VERIFIED at unit layer | T01 PASS; T02 algorithm PASS; T03 PASS | Actual Dijkstra module/test_routing.py; weighted-cost change also changes selected exit |
| Controller/route versions/CSE route record | VERIFIED for actual P1_ROUTES slice | Actual A/B/no-route CINs, duplicate and old-sequence subcases PASS; outbox recovery unit PASS | Full T04/restart/periodic stale guidance and dispatch recovery still incomplete |
| Actual GRP/fopt and three commands | VERIFIED for local Group slice | Actual T06 PASS: four fopt operations, 12 member CREATED results/CIN read-backs | Local member IDs match the observed ACME canonical representation; changed/duplicate members still fail |
| Three display consumers/ACKs | VERIFIED for isolated simulated-device slice | P1_GROUP ACK/no-route/stopped-device subcases PASS; state/order/expiry units PASS | Three actual PIDs/AE-IDs/SUBs, 11 device-written ACK CINs; full authenticated T07 and live expiry/restart T20/T12 coverage still incomplete |
| Resident/responder API/UI and occupants | NOT_STARTED | T15/T18 NOT_RUN | Frontend placeholder; receiver is not a dashboard API |
| MQTT + HTTP(S), authenticated TLS profile | NOT_STARTED beyond HTTP client | T08/T09 NOT_RUN | Isolated HTTP dev profile is not security/Expert evidence |
| Discovery/FCNT/advanced model | NOT_STARTED | T10 NOT_RUN | Labels in registration source do not prove discovery/model support |
| Local MEC Sandbox / Option C | NOT_STARTED | T16 NOT_RUN | P0 uses standalone IN-CSE, not MN-CSE as MEC App |
| Cloud IN-CSE registration / IPE/services | NOT_STARTED | T17/T11 NOT_RUN | No MEC API called or emulated here; source/host/service access still needed |
| Full fault recovery / latency | NOT_STARTED beyond durable receiver | T12/T13 NOT_RUN | No measured E2E latency samples or p50/p95 |
| GitHub / CI | Repository exists; workflow IMPLEMENTED_UNVERIFIED | User push verified previously; CI NOT_RUN | Unit and actual-CSE jobs configured locally, not executed on GitHub |
| Article/video/presentation | NOT_STARTED | NOT_RUN | No submission artifact or Expert achievement claimed |
| Optional handover/location/FL/AI | NOT_STARTED, DEFERRED scope | NOT_RUN | Keep behind verified core and submission requirements |

T01/T03 pass their specified unit layer, and actual route/fan-out/application/ACK subcases now pass. T04 duplicate-controller replay and actual outdated-sequence subcases pass; full restart/old-command live coverage remains incomplete. T05/T06 and isolated device/no-route/stopped-device subcases are verified. Full P1, authenticated security, live role applications and MEC gates have not passed.

## Executed checks and real limitations

Latest actual T05 evidence: evidence/20261111-100438Z-d1cfa0f4/ contains original requests.jsonl, notifications.jsonl, resources.json, assertions.json, events.jsonl, meta.json, summary.json, tests.txt and notification-state.sqlite3. The agent's separate offline audit is evidence/20261111-100844Z-t05-evidence-review/review.json (17 checks PASS, original artifact hashes recorded). It audits the existing real run and is not presented as a second integration execution. Raw runs remain ignored/private pending curated publication.

Latest actual P1_ROUTES evidence: evidence/20261111-103437Z-cff86001/ includes decisions.jsonl and durable incident state as well as the normal run artifacts. Offline audit evidence/20261111-104457Z-p1-evidence-review/review.json passes 18 checks: actual CIN content/resource matches, callback provenance, request IDs, three persisted outbox entries and one ignored outdated event. Counts: 32 CREATE successes, 13 GET successes, 28 pre-create not-found probes, two authorization denials. Original run artifacts were not modified. Group/ACK/UI are correctly NOT_RUN in that run; latency sample count is zero.

Actual Group evidence: evidence/20261111-115340Z-34c169f6/ includes original group.json, devices.json, fanout.jsonl, delivery.jsonl, coordinator wire/callback traces and three independent device wire/state directories. Separate audit evidence/20261111-115720Z-group-evidence-review/review.json passes 50 checks and hashes all original artifacts. The audit worked on a temporary copy; originals are unchanged. Four actual fan-out POSTs returned outer OK and 12 member CREATED results; 12 command CINs and 11 device-written ACKs were read back. Display-c's final version stays 3 while available devices apply version 4; the stopped case stays INCOMPLETE and outside complete counts. No latency sample/percentile or MEC result is claimed.

The first actual Group attempt, evidence/20261111-114816Z-fbc3f740/, failed after a successful GRP CREATE because ACME canonicalized SP-relative mid values into local IDs and ensure compared their spelling. The fix uses actual local CNT IDs, retains exact membership comparison and rejects duplicate/changed members. Four added regressions pass; **107 unit tests PASS** overall, raw output/provenance at evidence/20261111-115929Z-mid-fix-unit/. Compose parsing, compileall and diff checks pass. Earlier 103-unit and direct agent-runtime BLOCKED artifacts remain historical environment evidence. The successful actual rerun verifies the corrected Group path; full source publication/CI is still unverified.

Earlier P1 unit checkpoint, before the user's actual PASS: evidence/20261111-102016Z-p1-routes-unit/tests.txt and summary.json recorded 80 units PASS. The agent-runtime make test-routes was genuinely BLOCKED by Python 3.10, pass=0, at evidence/20261111-101950Z-9f46ce7b/. That historical environment result is preserved; the subsequent user execution above now verifies actual route persistence and two ACP denials. Live process/network recovery still has no executed integration result.

Startup-fix unit evidence: evidence/20261111-091413Z-cse-startup-fix/tests.txt and summary.json, with separately attributed initial-failure user-terminal-excerpt.txt. Earlier offline/graph evidence: evidence/20261111-065348Z-p0-p1-unit/.

- make test-unit: **62 tests PASS** after the startup fix (previously 55), including invalid contracts, strict HTTP/RSC/request-ID handling, namespace conflicts, callback verification, durable duplicates/conflicts, 20 concurrent duplicate submissions, secret redaction and actual route algorithm cases. Seven startup regressions cover basename arguments, owned runtime config staging/reuse, preservation of user/existing configs, changed-source staging, tamper rejection and keeping early configuration errors visible. Transport fixtures are unit-only and no fake CSE service is started.
- make compose-check: PASS (Compose parsing only, not image build or runtime).
- python3 -m compileall -q backend onem2m simulator mec infra tests: PASS.
- git diff --check: PASS at the recorded code checkpoint; final document/source review follows.
- Target product runtime remains Python >=3.11, target 3.12. The agent's offline units ran on host Python 3.10.12; the user's actual T05 runtime is Python 3.12.16. Separate package-install, target-version unit matrix and GitHub CI acceptance remain unverified.
- Earlier make test-cse in the agent sandbox: exit 2, genuinely BLOCKED because host runtime is below the product minimum. This is retained as environment history, not the current global T05 result.
- make p0-smoke in the agent sandbox: exit 2 from make; Docker API access denied before any image build/CSE run. Earlier direct socket/DNS probes also found AF_INET and Unix socket access denied and PyPI DNS unavailable. This limitation is distinct from the later user-terminal run below.
- Raw environment command outputs: evidence/20261111-064351Z-p0-unit-and-environment/tests.txt. The standalone blocked runner also created its own timestamped summary. Unit-generated temporary fixture evidence is not presented as CSE evidence.

Initial user-terminal result (historical): make test-unit passed 55 tests. The first make p0-smoke built both images and printed ACME 2026.05.1, then CSE exited (0); Compose failed its dependency gate. The p0 runner did not reach CSE assertions in that failed attempt.

Startup diagnosis/fix: the launcher supplied --config /etc/fire-route/acme.ini, while inspected upstream Configuration.initDirectories rejects a config argument containing a directory; CLI --headless suppresses that early diagnostic. The exact installed package's source has not been extracted. The launcher now stages a content-hashed owned file inside /data and passes only its basename, preserves existing data/configs, and sets noninteractive mode in [console] rather than the CLI. Seven added regressions pass. The subsequent actual package run reached Healthy and passed T05, verifying this startup adapter path (ADR-009).

Successful user-terminal rerun: make p0-smoke rebuilt changed layers, printed CSE started, reached Healthy, and p0 exited 0 with test=T05/state=PASS/pass=1/fail=0/blocked=0. The observed CSEBase is IN (cst=1), release 4. Actual evidence contains 44 exchanges: 21 CREATE successes (8 AE, 10 CNT, 1 ACP, 1 SUB, 1 CIN), 3 successful read-backs and 20 legitimate pre-create not-found probes. Request IDs match all recorded responses. One verification and one event callback were accepted; the CIN ID and complete sensor payload match actual read-back and the durable SQLite record. all_device_acks=NOT_RUN, MEC=unavailable and latency_samples=0 remain accurate.

Open runtime issues: Compose stopped the CSE after p0 exited, then reported cse exit 137. The log places this after successful assertions; it does not prove graceful shutdown, timeout escalation or OOM. Docker inspection is blocked by socket permissions in the agent sandbox; the user was asked for State.ExitCode/OOMKilled/Error. Do not dismiss this as harmless or infer database recovery. The actual run also warns about the default CSE secret. Keep this profile isolated; choose/inject a private persistent secret and verify authenticated transport/authorization before shared deployment. Neither issue is marked resolved.

Earlier P0 source/document review: 25 relative links valid, CI YAML/read-only permissions checked, fixture SHA-256 unchanged, .env/evidence/cache exclusions verified, and no source conflict markers or trailing whitespace. Review details are session-local at /tmp/fire-route-p0-final-review.json. The current P1 review checked AGENTS/README/docs (23 relative links, no missing targets), unchanged fixture hash, ignored raw evidence and git diff --check; all passed. README documents the distinct P0/P1 gate claims and both reproducible commands.

## Remaining work and next dependency

The requested local backend checkpoint is verified: P0 → routes → Group/fopt → independent display application/ACKs, including no-route and stopped-device handling. The user authorized a checkpoint commit/push after this actual pass. Preserve the tested feature branch and excluded private evidence; do not merge main or claim remote publication/CI without the corresponding Git results.

After actual Group/device verification, implement live role APIs/UI, synthetic occupants and complete controller stale/recovery handling. Device-local expiry clears directions in unit tests; full live outage/restart/dispatch recovery is still unverified. Existing T05/P1_ROUTES runs remain regression gates. P2 still needs acquired TR-0086/ETSILabs access, permitted x86 host, registrar and actual service/IPE catalog.

No runtime package installation, real CSE execution, MEC deployment or cloud change succeeded directly in the agent sandbox. User-terminal actual runs supply the protocol evidence. A remote probe failed with GitHub DNS resolution; no PR or main merge is part of this checkpoint.

## Earlier documentation-only checkpoint (before P0 implementation)

- Scope: user-authorized specification/instruction revision only. Name/repository target FireRoute/fire-route; checkout renamed safely under the existing workspace.
- Preserved: existing fixture, .env.example, .gitignore and placeholder files. No service source, server deployment, Git initialization/push or PR creation.
- Updated: original Markdown instructions/specs, task template and reference index; added deployment/environment/team/source documents.
- Source review: user-provided one-page rubric read locally, 17 criteria/Expert cells extracted without unmapped characters; source SHA-256 recorded in RUBRIC/SOURCES. Public schedule and official development references inspected; exact TR-0086 body and deploy scripts unacquired. Original Oct 30 notice is available only as the user's supplied summary.
- Document verification: VERIFIED for documentation only. Executed python3 /tmp/fire-route-doc-review.py: 16 checks PASS, 0 FAIL; 16 Markdown files and 23 relative links checked. Confirmed F01–F23, T01–T21, 17 rubric sections, P0–P4 and required architecture/workflow/date terms. An initial check requested the literal feature/* pattern in TEAM_WORKFLOW; clarified the wording and reran successfully.
- Preservation check: all 20 original files retained; the 8 non-Markdown files match pre-edit SHA-256 hashes. Only 4 planned Markdown files were added. No new service module, duplicate root STATUS or conflict marker exists. The legacy fixture identifier remains unchanged for compatibility.
- Session-local review artifacts: /tmp/fire-route-doc-review-results.json and /tmp/fire-route-docs-baseline-yh3qjttt/manifest.json. The reviewer checks links, identifiers, phase/source inventory and preservation; it is temporary documentation tooling, not a shipped product test harness. External links are source references, not all certified reachable by this check.
- Tool limitation: temporary PDF-reader dependency download failed due DNS; no project dependency was added. The supplied PDF was read using standard-library decompression/text/font mapping. No failed download is reported as installation success.
