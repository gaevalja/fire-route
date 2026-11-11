# FireRoute source provenance and verification limits

Review completed: 2026-11-11 (Asia/Seoul); research began 2026-11-10. User-confirmed scope is authoritative for project choices. Standard/API behavior still requires the acquired version's documentation and actual execution. A research tool access error does not prove that a server is down or that authorization is the only cause.

## 1. Primary material and inspected references

| ID | Source / inspected edition | What is established | Limit / required next evidence |
|---|---|---|---|
| S01 | User-supplied Hackathon Rubric 2026.pdf, one page, SHA-256 42b38857fffae7c92739f84440b9db020ec6b79897c0f70db64c465ffd2cdfad | All 17 rows and Expert cells read from tagged PDF content/coordinates; Article/Interview prerequisite tiers also checked | No revision number printed/established; original remains outside repo; no inferred weights or guaranteed score |
| S02 | User-provided summary of organizer notice dated 2026-10-30 and confirmed project instructions | Local Sandbox preference, A–D definitions/Option C target, subset-of-rubric policy and supplied schedule adopted | Original notice not supplied/read independently; do not invent additional instructions or exact cutoff |
| S03 | [oneM2M WI-0120](https://git.onem2m.org/specifications/wi/wi-0120/-/blob/main/WI-0120-Edge_Deployment_using_ETSI_MEC.md) | Lists TR-0086 Developer Guide: oneM2M and MEC deployment among work items | TR-0086 full body/revision not acquired; attempted online location inaccessible; exact commands/placement must be checked before P2 |
| S04 | [TR-0077 online v0.1.0 registration section](https://specifications.onem2m.org/tr/tr-0077/v0.1.0/7.1/) and [Release 5 index](https://www.onem2m.org/technical/published-specifications/release-5) | Online draft covers CSE/IPE registration and MN-as-MEC-App alternatives; catalog lists a v0.3.0 draft | Online edition/catalog differ; select acquired compatible revision; skeletal headings are not executable procedures |
| S05 | [GR MEC-DEC 051 change snapshot 800ee511](https://forge.etsi.org/rep/mec/specifications/gr-mec-dec-051/-/commit/800ee511b874476a5351dd3d8259f465a907a3d3) | Inspected snapshot changes draft version from v4.0.4 to v4.0.5; interworking is evolving | Current full main/master body could not be read; no final publication/completeness claim. Acquire applicable revision and relevant clauses |
| S06 | [Organizer-specified STF_685/deploy](https://labs.etsi.org/rep/mec/etsi-mec-sandbox/-/tree/STF_685/deploy) and [ESTIMED developer index](https://estimed.etsi.org/dev_material/) | Required repository path supplied; official index provides deployment/developer material | Required path was inaccessible to research tool; no deploy scripts executed. Index also links master/playbooks: reconcile revisions, do not silently substitute |
| S07 | [Official competition schedule](https://onem2m-hackathon.io/schedule.asp) | Development ends Nov 20, final presentation/Q&A Nov 23–25, ceremony Nov 27 | Nov 26 selection comes from user guidance; final submission cutoff/timezone/formats remain to be obtained |
| S08 | [ETSI MEC Sandbox Help](https://mecwiki.etsi.org/index.php?title=MEC_Sandbox_Help) | Sandbox models emulated network/platform behavior; external app instance IDs and API subsets are documented | Not proof of actual local deployment, eligible-host orchestration or installed API support |
| S09 | [ACME supported features](https://acmecse.net/home/Supported/) and [installation](https://acmecse.net/setup/Installation/) | Candidate documents MN/IN types, SUB, Group/fopt, ACP, discovery and bindings; minimum Python 3.11 | No ACME version installed/verified here; MQTT needs separate broker; actual release/plugin behavior must be probed |
| S10 | [Organizer output/publication notice](https://estimed.etsi.org/news/estimed_hackathon2/) | Source Apache-2.0, non-code CC BY 4.0 described for outputs | Repository license files, third-party notices and actual publication remain future work |

## 2. Use and update rules

For each acquired guide, record title, printed version/date, draft/approved status, source URL/access date, file checksum and relevant clauses. For deployment repositories record branch and immutable commit; for images/packages record actual version/digest. Local access-approved material need not be redistributed; keep restricted originals out of public Git and retain permitted attribution.

Official Expert criteria in RUBRIC.md are summaries of S01. FireRoute feature choices are separate engineering targets. In particular, labels/FCNT are not automatically Expert semantics; one non-location service is not Expert multi-service bidirectionality; an Option C app on one server is not automatically Expert orchestration across eligible hosts.

The reference Hosted Sandbox URL is https://82.112.253.59/ as provided by the user. No live API probe, certificate acceptance, login, installation or server modification was performed there. Do not equate an available web page with a configured FireRoute integration.

Before calling any MEC API supported, inspect the actual environment's catalog/OpenAPI and record the real response. Before claiming TR-0086 conformance, acquire its full revision and check the deployed registration, lifecycle, IPE and cloud topology against it. This source review does not certify standard compliance.
