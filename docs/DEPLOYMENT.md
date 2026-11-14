# FireRoute local runtime and deferred Hosted MEC deployment plan

## 1. Current execution gate and source requirements

The user changed the strategy on 2026-11-14: Phase 1 completes the current WSL2/Docker/actual ACME system; Phase 2 prepares portable components/configuration/interfaces locally. Phase 3 may access or deploy to the organizer Hosted MEC Sandbox only after a separate explicit user instruction. No Hosted URL probe, login, OAuth flow, namespace/API enumeration or deployment is performed now. Public reference documentation can be read. Phase 4 must submit a functioning local system by Nov 20 even if MEC is incomplete. See ADR-019 and ROADMAP.md; historical P0–P4 references are traceability labels.

The organizer-notice descriptions (ETSI/OAuth login, personal sandbox, per-user Kubernetes namespace, limited platform administration) are user supplied and unverified in the actual environment. Local Sandbox installation is described as officially recommended; it is an optional future reference environment, not a prerequisite for current work. The rest of this document is a conditional future runbook, not evidence of an installed topology or permission to execute it.

Preferred source: [official STF_685/deploy repository](https://labs.etsi.org/rep/mec/etsi-mec-sandbox/-/tree/STF_685/deploy). Reference hosted environment: [Hosted Sandbox](https://82.112.253.59/). Do not disable certificate verification to reach it or infer current API availability from the URL.

The deploy path could not be read with the research tool in this session. This does not establish whether the cause is permissions, availability, or tooling. An ETSILabs account and separate repository approval may be required. The official developer-material index also links a master/playbooks path; do not silently substitute it for the organizer-specified STF_685 revision. Record an authorized commit and reconcile guide/code differences before execution.

Read the acquired oneM2M TR-0086 Developer Guide first, then TR-0077 and ETSI GR MEC-DEC 051 for deployment/interworking. Version numbers, draft status, commit and applicable clauses must be recorded. The TR-0086 body is not yet available in the workspace; exact commands, chart/image versions, IPE placement and cloud-registration settings remain unverified. SOURCES.md records inspected material and gaps.

## 2. Official deployment options and target

The following option definitions are adopted from the user-provided organizer guidance; review against the acquired guide revision before implementation.

| Option | Topology | FireRoute position |
|---|---|---|
| A | MEC-IPE as MEC App, linked to Cloud IN-CSE | Alternative only with verified official support and fit |
| B | MN-CSE + MEC-IPE on a separate Edge node | Conditional candidate alongside A/other official options after permission/API review |
| C | MN-CSE deployed as MEC App on MEC Host | First support assessment during authorized Phase 3, not an assumed Hosted capability |
| D | MN-CSE deployed as MEC Service on MEC Host | Later alternative; avoid unverified service exposure |

If Option C is actually supported, it requires evidence of the MN-CSE artifact running on the selected MEC Host with the supported MEC application onboarding/lifecycle registration. An assigned application ID alone, local container placement, or an external API call is insufficient to prove this placement. Verify what the selected Sandbox actually orchestrates versus emulates. Do not claim hypervisor VM deployment when only a container or an external app is used.

The risk/controller is a FireRoute edge application and oneM2M AE. The MEC-IPE has a separate mapping role and AE identity. It may be provided by the official platform or deployed according to the verified guide; do not fix a deployment location or duplicate a platform IPE before examining the actual integration.

## 3. Planned gated sequence

| Gate | Work to execute after deployment is authorized | Evidence and exit condition |
|---|---|---|
| D0 Access/source | Obtain ETSILabs repo permission and acquired guides; identify server admin/deployer | Readable pinned deploy revision, guide revisions, authorization; otherwise BLOCKED |
| D1 Capacity | Inspect x86 Ubuntu host, official prerequisites, network/virtualization and storage | Actual inventory vs exact-revision requirements; do not use provisional sizing as proof |
| D2 Local core | Prepare isolated actual CSE dev profile and callback receivers | P0 CSE/AE/CNT/CIN/SUB read-back; no MEC claim |
| D3 Sandbox | Apply only reviewed official instructions for pinned revision on permitted host | Deployment logs, version/config hashes, platform health and rollback/start/stop procedure |
| D4 Catalog | Discover services and exported OpenAPI; check app/lifecycle support | Actual API versions, enabled endpoints, credentials/scopes and supported operations |
| D5 Option C | Package/configure MN-CSE as supported MEC App; deploy controller/IPE per guide | Artifact digest, host/app identity, lifecycle/placement logs; no assumed full CSE modification support |
| D6 Registrar | Configure separate Cloud IN-CSE and MN registration via Mcc | Actual CSE types/IDs, CSR read-back, authorized remote resource access and failure/reconnect test |
| D7 Interworking | Exercise supported non-location MEC service through IPE and CSE | Correlated MEC result/notification, mapping, CSE CIN/SUB and application consumer |
| D8 Acceptance | Run T11, T16 and T17 plus P1 regression E2E | Real evidence, limitations and actual topology in STATUS; direct API-only path cannot pass interworking |

Public guide review and local interface/configuration work may run during Phases 1/2. Any Hosted login, access probe, namespace/API review or deployment in D0–D8 requires the separate Phase 3 instruction and actual permission. No commands are supplied as though verified installation scripts exist locally. Authorized Phase 3 must replace this planning sequence with exact reproducible commands taken from the acquired revision and actual executed results.

## 4. Registrar and network checklist

Confirm IN-CSE owner/location, endpoint/base/CSE-ID, MN-CSE type/base/CSE-ID, registrar credentials, POAs, supported release and transport. Configure MN registration in the selected CSE rather than creating a cosmetic AE. Read the registrar's actual remoteCSE resource and the MN's registrar reference where supported; verify remote retrieval using the selected release's addressing rules. Exact resource names are configuration-dependent.

Verify authorized communication paths: devices → MN-CSE/broker; CSE → controller/display notification receivers; IPE ↔ CSE/MEC services; MN-CSE ↔ Cloud IN-CSE; backend → CSE; browsers → backend. Capture private DNS/address mapping in private run metadata and sanitize public evidence. A local IN-CSE process simulates the cloud role and must not be described as a separate cloud host.

Remote registration is distinct from copying all application data, resource announcement, CSE handover and MEC service discovery. Each extra capability needs separate tests.

## 5. Service availability and mapping matrix

| Service | Investigation | Current availability / decision |
|---|---|---|
| MEC 011 | App readiness/lifecycle, platform discovery and service availability support | Not checked on a running environment; operation subset must be read |
| MEC 013 | Location API, source and event support | Unverified; optional feature only |
| MEC 033 | IoT API, officially provided bridge discovery/registration | Unverified; inspect matching IPE/model implementation |
| MEC 046 | Sensor-sharing API and oneM2M mapping | Unverified; draft/release/implementation compatibility must be checked |
| Other non-location service | RNIS/WLAN/service offered by actual catalog with supported IPE mapping | Select only after real probe and project value assessment |

Use service → IPE → CSE → consumer as the first interworking gate. Multiple services and supported reverse control improve the rubric #16 target, but one genuine non-location service is the minimum selected scope, not an Expert guarantee. Never invent unsupported MEC methods or call a custom mapping an official implementation.

## 6. Option C failure and fallback

If C is blocked, preserve the error, guide/repo revision, hardware/software conditions, missing capability, owner and next action. Distinguish: inaccessible repository; host prerequisite failure; unavailable app lifecycle; CSE MN/registrar limitations; absent IPE mapping; unsupported API. Do not wait until submission to investigate these dependencies.

Under ADR-019, support assessment occurs only during separately instructed Phase 3. Select a runnable official topology from actual permissions, APIs and guide revisions: assess C, then A/B/another supported option as evidence permits. Record the reason, exact capability limits and rubric impact in an ADR and rerun only affected integration gates. No earlier topology date or planning note authorizes Hosted access or deployment.

If no supported MEC path is available, preserve the verified local system and report current Phase 3 integration as unavailable/blocked when actually attempted under instruction. Exclude unverified MEC/Expert claims from the article/video. A local MEC mock never removes the blocker. A physical Raspberry Pi can fill B's edge role only after its actual model/capacity/protocol support is confirmed; use x86 Edge as another candidate.

## Current local stabilization and portability commands

make diagnose-cse is read-only and selects Docker state (including OOMKilled/exit), lifecycle events, memory observations and safe startup/shutdown markers. It excludes environment, command arguments, bind-source paths and raw logs. The installed-package signal scan records only source hashes, signal/handler identifiers and line numbers; it is static source evidence, not runtime handler state. Exit 137 without supporting evidence remains undetermined.

make local-stability builds the updated local CSE/core image, creates a run-owned AE/CNT/CIN marker through the actual CSE, records running state, requests a controlled 30-second stop, collects exit/events/log/memory evidence, restarts CSE and reads the identical resources/content/configuration. It preserves volumes and unrelated resources. A failed/forced shutdown keeps overall FAIL even if marker persistence passes. The launcher stores one private non-default key in the data volume and refuses unsafe/corrupt keys rather than rotating them. The new profile passes actual controlled same-container stop/start T27 at evidence/20261114-054111Z-bc1765d8/, with a separate 28-check audit. Old CSE PASS artifacts remain tied to their original config hash; crash/recreation/full application recovery and changed-profile E2E regression remain separate.

ADR-021 records a local workaround for the inspected ACME 2026.5.1 exit cleanup guard. The Dockerfile runs infra/cse/patch_shutdown.py after installing the pinned package; it accepts only upstream CSE.py SHA-256 5b8678ba45450090befef0d183faad429724478122f4f910f368d2a44d83e7ae and adds SHUTTINGDOWN to the existing accepted state list. The image retains upstream bytes otherwise and writes /opt/fire-route/cse-shutdown-patch.json. Startup checks version, manifest, patched hash and exact reversal to the pinned original, then exposes public fingerprints in /metadata/cse.json. No package source is patched in the host Python environment or data volume. No new dependency, schema/cache/durability setting or secret rotation is added. Existing init/SIGINT/30-second settings remain. make local-stability rebuilds/applies the image and requires matching verified patch fingerprints plus actual resource/normal-shutdown checks; the user has built this image and passed controlled T27, while direct agent Docker access remains unavailable. The patched-profile natural-hazard regression now passes at evidence/20261114-063427Z-99186a58/ and selected role/HTTP regression passes at evidence/20261114-123442Z-fabc5346/. Next prioritize actual malformed-event/fault recovery and performance checks. The controlled stop/start result does not establish recreation/crash durability. A different upstream version/hash needs a new review/ADR and regressions before changing this pin; no automatic patch fallback exists.

Current host client endpoint/identity settings are environment/.env based. Docker clients can override CSE_CONTAINER_BASE_URL/CSE_ORIGINATOR without editing source; this does not deploy or configure a remote CSE. infra/profiles/local.env.example documents local defaults; infra/profiles/hosted.env.example is inactive and intentionally blank for unverified endpoints/callbacks. Existing header identity is not full authentication. Real MEC authentication scheme, API URLs, namespace privileges, images and lifecycle interface must be acquired in Phase 3; no guessed API client/manifests are supplied.

Remote Hosted services cannot call back into this WSL instance through 127.0.0.1 or Compose-only DNS names. Phase 3 must establish an authorized reachable path in each required direction and verified TLS/authentication. If a direction or official operation is unsupported, record that limitation and choose only an actually supported alternative; do not disable certificate verification or silently substitute a synthetic callback.
