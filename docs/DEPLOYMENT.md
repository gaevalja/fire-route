# FireRoute Local MEC Sandbox and CSE deployment plan

## 1. Scope and source gate

This is a future deployment runbook with acceptance gates. No MEC/shared-server installation or deployment has been performed by the agent. A separate P0 local IN-CSE Compose profile and T05 runner now exist; their actual execution is tracked in STATUS.md and does not count as Option C.

Preferred source: [official STF_685/deploy repository](https://labs.etsi.org/rep/mec/etsi-mec-sandbox/-/tree/STF_685/deploy). Reference hosted environment: [Hosted Sandbox](https://82.112.253.59/). Do not disable certificate verification to reach it or infer current API availability from the URL.

The deploy path could not be read with the research tool in this session. This does not establish whether the cause is permissions, availability, or tooling. An ETSILabs account and separate repository approval may be required. The official developer-material index also links a master/playbooks path; do not silently substitute it for the organizer-specified STF_685 revision. Record an authorized commit and reconcile guide/code differences before execution.

Read the acquired oneM2M TR-0086 Developer Guide first, then TR-0077 and ETSI GR MEC-DEC 051 for deployment/interworking. Version numbers, draft status, commit and applicable clauses must be recorded. The TR-0086 body is not yet available in the workspace; exact commands, chart/image versions, IPE placement and cloud-registration settings remain unverified. SOURCES.md records inspected material and gaps.

## 2. Official deployment options and target

The following option definitions are adopted from the user-provided organizer guidance; review against the acquired guide revision before implementation.

| Option | Topology | FireRoute position |
|---|---|---|
| A | MEC-IPE as MEC App, linked to Cloud IN-CSE | Alternative only with verified official support and fit |
| B | MN-CSE + MEC-IPE on a separate Edge node | First fallback if C cannot be supported |
| C | MN-CSE deployed as MEC App on MEC Host | First target |
| D | MN-CSE deployed as MEC Service on MEC Host | Later alternative; avoid unverified service exposure |

Option C requires evidence of the MN-CSE artifact running on the selected MEC Host with the supported MEC application onboarding/lifecycle registration. An assigned application ID alone, local container placement, or an external API call is insufficient to prove this placement. Verify what the selected Sandbox actually orchestrates versus emulates. Do not claim hypervisor VM deployment when only a container or an external app is used.

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

D0/D1 investigation can run beside P0/P1 development. D3–D8 require permitted infrastructure and the core contracts. No commands are supplied as though verified installation scripts exist locally. P2 must replace this planning sequence with exact reproducible commands taken from the acquired revision and actual executed results.

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

At the 2026-11-12 checkpoint, assign each unresolved MEC dependency and begin an Option B compatibility assessment. By 2026-11-16 select a runnable topology based on evidence: C first; B if verified; A/D only with a documented official supported path. Record the change as an ADR, impact on rubric #13/#16, and rerun T11/T16/T17 plus P1 regression. A topology decision is not deployment authorization; shared/external changes require the user's deployment scope.

If no supported MEC path is available, continue reproducible real-CSE P1 and report P2 BLOCKED. Exclude unverified MEC/Expert claims from the article/video. A local MEC mock never removes the blocker. A physical Raspberry Pi can fill B's edge role only after its actual model/capacity/protocol support is confirmed; use x86 Edge as another candidate.
