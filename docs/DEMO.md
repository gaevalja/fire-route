# FireRoute demonstration and submission plan

## 1. Scope labels

This is a proposed storyboard, not an executed or recorded demo. Initial target length is 4–6 minutes, a team proposal until official duration/format rules are obtained. All evidence must come from an actual run; pre-recorded backup is labeled with its run ID/time.

Display input provenance (SYNTHETIC/PHYSICAL), actual CSE connection/test status, MEC deployment option/source, Sandbox network emulation and missing integrations. Describe computed alternatives on the synthetic graph without promising actual evacuation safety, fire accuracy or real occupant positioning.

## 2. Storyboard

| Approximate time | Show | Required supporting evidence |
|---|---|---|
| 0:00–0:30 | FireRoute problem, synthetic three-floor building, separate resident/responder roles | Scope/provenance labels; overview figure |
| 0:30–1:10 | Actual AE/CNT/CIN/SUB/GRP/ACP tree and Option C target vs actual placement | CSE read-back, versions/IDs; real deployment facts only |
| 1:10–1:40 | Algorithm computes EXIT_A from F3_ROOM1; two live views agree | Route CIN/version; no prerecorded route substitution |
| 1:40–2:30 | Publish synthetic smoke index 90 at F2_A and typed temperature sample | Real CSE CIN and SUB callback referencing the source event |
| 2:30–3:10 | Risk policy excludes F2_A and computes EXIT_B | New version/path/CSE record; threshold labeled demo policy |
| 3:10–4:00 | Real GRP/fopt delivers to three independent displays and each ACKs | Aggregate member results, three command CINs, three device ACK CINs |
| 4:00–4:40 | Actual MEC service → IPE → CSE → application; app placement and Cloud IN-CSE registration | T11/T16/T17 evidence; direct API call and emulated network shown separately |
| 4:40–5:30 | No-route clears directions; stop one display; deny unauthorized access; responder synthetic occupants | Actual incomplete/STALE/UNKNOWN status, CSE denial, responder-only timestamped data |
| 5:30–6:00 | Measured results, benefits, reproducibility and limitations | Real N/p50/p95 if available, repository/article links, honest unverified list |

If MEC is blocked, replace its segment with the exact missing integration and working CSE evidence; do not present an architectural slide as an executed MEC trace. If only a lower-tier rubric feature is verified, describe that result without an Expert claim. Use recorded failures/recovery with clear labels if timing cannot be reliably demonstrated live.

## 3. Submission inventory — complete by 2026-11-20

- GitHub fire-route repository/release: source navigation, real commands, version pins, synthetic fixtures, tests, licenses/notices and sanitized evidence index. Remote owner is not yet configured.
- Article: system/service overview, hardware/simulator inventory, resource model, protocol rationale, Option C/actual fallback, security/privacy, measured results, oneM2M benefits, limitations and reproduction instructions. Confirm actual publishing platform; rubric refers to hackster.io.
- Video: legible screens/logs, intelligible narration, mode labels, source/run IDs, useful pacing and tested playback/link accessibility. Confirm file/link/length rules.
- Presentation: architecture/Cloud registration, demo flow, resource/protocol choices, project value, results, remaining gaps and team contributions.
- Backup: a genuine prior run, timestamped sanitized traces, pinned artifact/configuration version and recovery procedure.
- Submission receipt: record final links/files, exact submitted version, cutoff/timezone and confirmation. Required portal/formats are not yet independently verified.

The [organizer publication notice](https://estimed.etsi.org/news/estimed_hackathon2/) specifies Apache-2.0 for source and CC BY 4.0 for non-code outputs. P4 must add appropriate files/attribution while retaining third-party license terms; none is implemented by this storyboard.

## 4. Rehearsal and interviews

Nov 19: run clean-environment reproduction, verify every link, rehearse live and backup paths, redact secrets, and compare all claims with STATUS. Nov 20: finish all deliverables and submit before the confirmed cutoff. Nov 23–25 interviews/presentations: every presenter explains resource tree, integration methodology, protocol choices, why oneM2M is useful, real vs emulated MEC, failure handling, measured clock boundaries and remaining limitations. Nov 26 selection and Nov 27 ceremony do not extend implementation time.

No public posting, upload, video recording, Git push or presentation delivery is performed in this documentation task.
