# FireRoute — bounded implementation task template

Read AGENTS.md, README.md, and every document in docs/ before editing. Preserve existing implementation, configuration, Git history, and team members' uncommitted work.

Requested phase: **P0 — development environment and basic actual oneM2M communication**. This template does not itself authorize deployment, Git push, or PR creation. Follow the user's current scope.

1. Inspect local runtime, existing source, Git state, and CSE availability; record observations rather than assuming a working installation.
2. Propose the smallest concrete task for this phase, identify module ownership/interfaces, and implement only the authorized task.
3. For P0, prepare reproducible pinned local setup and actual CSE AE/CNT/CIN creation/read-back with a real notification receiver and SUB verification. Use the planned onem2m/, infra/, simulator/, and tests/ boundaries; do not build a custom CSE.
4. Keep Option C (MN-CSE as MEC App on Local ETSI MEC Sandbox) as the P2 target. Verify the acquired TR-0086 revision and ETSILabs access before using deployment scripts. An ordinary local CSE is a P0 environment, not a completed MEC deployment.
5. Execute relevant unit and actual-CSE tests, save sanitized request/response and test evidence, and report unrun/blocked checks honestly. Mock test success cannot satisfy real integration gates.
6. Update docs/DECISIONS.md and docs/STATUS.md. Report changed files, exact test commands/results, remaining gaps, and the next dependency.

Phase names are P0 environment/CSE, P1 fire-response E2E, P2 MEC deployment/interworking, P3 hardening/measurements, P4 submissions. A request for analysis or documentation only must stop after those deliverables without implementing services.
