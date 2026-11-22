# FireRoute local submission package

These are local artifacts for review and export, not a claim of publication or final submission. The verified product uses real ACME CSE communication and simulated fire/people/devices. Published efc65cb passes clean-archive acceptance 20261116-044349Z-18300187, all 19 stages: bounded MQTT/discovery, actual CSE/Group/ACKs, faults/recovery/observer, HTTP/HTTPS Chrome (20 checks each) and eight TLS 1.3/certificate/role checks. A separate 51-check read-only review matches source and actual protocol/device artifacts; reviewed Korean text is readable. This is same-host clean-source reproduction. Remote CI, actual video and publication remain unverified. STATUS is authoritative.

| Artifact | Use |
|---|---|
| [ARTICLE](ARTICLE.md) | English Hackster-ready manuscript; publish after links and final result review |
| [Presentation](presentation.html) | Eight local slides; open in a browser, use arrow keys, print to PDF |
| [Architecture](architecture.svg) | Actual local topology; intentionally does not depict a running MEC platform |
| [Video narration](VIDEO_SCRIPT.md) | Spoken script, capture sequence and claim/credential checks |
| [Performance](../PERFORMANCE.md) | Actual 30-sample observer results, CSV and figure |
| [Runbook](../LOCAL_ACCEPTANCE.md) | One-command acceptance, isolated reproduction and optional HTTPS |
| [Clean result](../assets/local-acceptance-20261116.json) | Curated machine-readable result; exact tested commit, counts and limits |
| [HTTP screenshot](../assets/clean-http-dashboard.png) | Unedited responder status view, synthetic input; readable Korean and three verified ACKs |
| [HTTPS mobile screenshot](../assets/clean-https-mobile.png) | Unedited 390-pixel status/controls view; not a hazard video |

The draft uses verified run identifiers rather than an invented CI/release/article URL. Before publication, replace draft status with actual article/video/release links and add that final run's evidence. Do not label an old run as verification of later source changes. Exact portal, cutoff timezone and submission formats still need the organizer's final instructions.

No public post, Git push, PR, account change or external deployment is performed by generating this package. Keep credentials, .runtime files and unreviewed evidence/screenshots out of Git. Diagrams/text describe a simulation PoC, not emergency advice or a validated evacuation model.
