# LAMOST Supervisor / Resume Handoff

Continue the authorized six-experiment LAMOST project on the existing EC2. Do not restart from stale counts or rerun frozen E1/E2. Read first:

/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/LAMOST_DETAILED_CURRENT_STATUS_20261027T213218Z.md

## Current state and guardrails

The latest observer at 2026-10-27 21:29:56 UTC / 2026-10-28 02:59:56 IST verified the controller and two workers. It also marked one E5 evaluation running-unverified. Verify exact process identity before treating that row as live or dead.

Current experiment status:
- E1 frozen: 674 successful, 81 failed (55 resource, 26 supervisor-terminal manifest-started), 10 unsupported; 765/765 terminal.
- E1 recovery: separate and stopped at user request, 24 successful retries, 10 failures, 2 user-stopped, 55 not attempted.
- E2 primary: 108/150; 42 unavailable. Classical refs: 120/120.
- E3: 64 successful, 3 failures, 2 unavailable; 69/69 terminal.
- E4: 1,524 successful, 71 failures, 3 unavailable, 175 waiting. Direct route is 720/765 terminal, with 45 Extra Trees cells still waiting.
- E5: 657 successful, 50 failures, 34 unavailable, 218 waiting, and 1 running-unverified.
- E6: 15 historical E3 references (12 successful, 3 unavailable) plus six corrected primary tasks (3 test-posterior timeout failures, 3 dependent-unavailability outcomes; 0 valid ensemble test evaluations).

## Continue under existing authorization

Do not ask for routine permission to move among the already-authorized E3-E6 work. Do not change frozen E1 or refit E1/E2. Keep recovery, E2 reconstructed provenance and later experiment fits in their own groups. Bootstrap is dropped.

Keep waiting, scientific failure, unsupported, unavailable dependency, operationally invalid, and validated success distinct. Use actual successful repetition denominators and conditional-on-success caveats. Do not claim significance, a universal winning method, or that the test cohort is untouched; E1/E2/E3 already evaluated it.

## E6 state

E6-v2 correction and permanent restart fix are qualified, deployed, and adopted. Current freeze SHA256 is 9994b586264f7b36c6355e051fac5ad2f17a3e4738dc2d4f7e036b9f08e96a00; controller source SHA256 is 68b081487afd8f7572362d33601b276b245150d9bca587aca5bf3b9cace75c10. Activation receipt:

runtime_20261025/reports/engineering_audits/E6_IDEMPOTENT_RESUME_EFFECTIVE_ACTIVATION_20261028.json
SHA256 b32d48294c6a7282335c6ccd3cb97ccd88e78cae352cf2e49a1714619af468ed

The old six zero-attempt E6-v1 gate outcomes and six later operationally-invalid feature-order attempts are both preserved, with distinct provenance. The feature-order attempts were superseded by the corrected E6 execution; neither history group is a scientific failure. Do not retry the current three equal-weight test-posterior timeouts or repeat same-policy learned test inference: learned tasks correctly depend on the failed shared posterior phase. No valid E6 ensemble test metrics or benefit claims exist; tuning weights and learned candidate ledgers are tuning-only evidence.

## Continue E4/E5 and final delivery

Continue the already-running E4/E5 queues under controller admission. Recheck the E5 running-unverified row with process identity first. Do not touch Harbor. The prospective RF4 policy is four fit trials, one predict trial, one native thread, 10 GiB and existing 600-second phases, but this snapshot did not verify an RF4-profile scientific worker; do not claim one has been run.

Complete remaining E4/E5 cases, project-wide native calibration-q replay, conformal checks, updated E3 prior-test-exposure disclosure, and final cross-experiment reporting. The 45 direct Extra Trees E4 cases remain pending.

The 36.3-GB archive currently named LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip is not the final delivery. Do not reread/re-hash its payload for this interim report; use its existing metadata binding until final packaging is authorized. Produce the final overall archive and compact laptop ZIP only after all case accounting and report validation. Verify CRC, member manifest, size, and SHA256, then use the existing laptop handoff directory. Do not declare the project complete before both packages validate and all planned cases have explicit outcomes.

Continue without routine confirmation. If a real blocker appears, record exact evidence and proceed with independent authorized work.

