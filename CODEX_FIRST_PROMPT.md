# FireRoute — bounded implementation task template

Read AGENTS.md, README.md, and every document in docs/ before editing. Preserve existing implementation, configuration, Git history, and team members' uncommitted work.

Requested phase: **current Phase 1 local completion and Phase 2 local portability**, unless the user specifies a narrower task. This template does not itself authorize deployment, Git push, or PR creation. Follow the user's current scope.

1. Inspect local runtime, existing source, Git state, and CSE availability; record observations rather than assuming a working installation.
2. Propose the smallest concrete task for this phase, identify module ownership/interfaces, and implement only the authorized task.
3. Preserve the verified actual CSE/Group/ACK/scenario/role path. Complete local security, timeouts, malformed/duplicate input, lifecycle/persistence and evidence work; use backend/, onem2m/, infra/, simulator/, mec/risk/ and tests/ boundaries. Do not replace the CSE or rewrite the source fire model.
4. Prepare portable analysis/configuration/images locally. Do not visit/probe/login/deploy to the Hosted MEC Sandbox now. Phase 3 requires a separate explicit instruction and actual permission/API/lifecycle review; Option C/A/B are conditional options, never assumed support. Keep a working local submission by Nov 20 even if MEC is unavailable.
5. Execute relevant unit and actual-CSE tests, save sanitized request/response and test evidence, and report unrun/blocked checks honestly. Mock test success cannot satisfy real integration gates.
6. Update docs/DECISIONS.md and docs/STATUS.md. Report changed files, exact test commands/results, remaining gaps, and the next dependency.

Current phases are 1 local completion, 2 local portability, 3 separately instructed Hosted integration, 4 submission. Historical P0–P4 labels remain in old commands/records for traceability; ROADMAP.md defines the mapping. A request for analysis or documentation only must stop after those deliverables without implementing services.
