# Supervisor review prompt — interim project state

Observed UTC: 2026-10-29T10:07:37.284807+00:00; IST: 2026-10-29T15:37:37.284807+05:30.

Please review the LAMOST six-experiment study below and give concrete scientific/reporting instructions for the submission deadline. This is an interim handoff, not a claim that the project is complete. Execution of the already authorized remaining cases continues; your review does not require reopening frozen results.

## Authoritative locations

- Existing approved SSH: `w7-ec2`; existing instance `i-095641a281a4038b9`. All scientific work remains on EC2; preserve the separate Harbor workload.
- Migration root: `/home/ubuntu/lamost_e1_migration_20261023`.
- Project: `project`; later runtime/controller: `runtime_20261025`; E2: `e2_20261024`.
- GitHub: https://github.com/S-G-mathematics/lamost-six-experiments . Both published branches were verified at `97185c6bef04f0858cbcde7a844a71b5f3f8644b`. That public-results snapshot is cut off at 08:55:39 UTC; subsequent live successes are not implied to be in that commit.
- Read the authoritative protocol, frozen configuration and memberships, E1 validated report, E2 report/reconstruction amendment/integrity audit, experiment manifests, and current SQLite registry. Check actual processes; never infer liveness from heartbeat files.

## Current scientific accounting

- Frozen E1 remains 765/765 terminal: 674 successful, 81 failed, 10 unsupported. Distinguish 55 resource failures from 26 supervisor-terminal cells whose old manifests remained started.
- E1 recovery remains a separate early-stopped supplement: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, 55 not attempted. No more E1 fits, recovery queues or ARF variants.
- E2 primary: 108/150 evaluated, 42 unavailable; classical references 120/120. Preserve 31 reconstruction accuracy differences, 210 low-precision class reports, 4/30 complete five-family correlation strata, and the original/reconstructed provenance distinction. The recorded integrity audit covers 228 evaluations/1,596 class reports with zero recorded integrity errors; this is a saved audit, not a new full rerun.

| Experiment | Successful | Scientific failure | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|
| E3 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1621 | 71 | 3 | 67 | 11 |
| E5 | 700 | 50 | 78 | 101 | 31 |
| E6 | 12 | 3 | 6 | 0 | 0 |

E6 successful rows above are 12 member-reference aliases, not successful ensembles. The six primary ensembles have zero successful test evaluations: three equal-weight test timeouts and three unavailable learned-weight comparisons. Do not make ensemble-benefit claims.

## User-approved scope and analysis boundaries

- The user explicitly cut further repetitions: retain all existing observations and attempt one evaluation for each still-uncovered method/condition group. The immutable original 6,270-task / 2,823-scientific-case plan remains preserved.
- The applied amendment selected 45 remaining E4/E5 evaluations and stopped 168 extra unattempted repetitions (E4:67, E5:101), or 334 task nodes including their unused dependencies. These are user-stopped, not scientific failures.
- Amendment: `runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json`, SHA-256 `e11d77d793539517fccb4bfe6260d74fb4c8ba92960450706463d4e7cd2f57fb`. Application receipt: `reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json` under the runtime.
- New groups contribute one evaluation; previously completed groups may retain multiple repetitions. Report actual successful counts and matched available repetitions. Do not manufacture three-repetition variability or significance.
- Bootstrap remains dropped. No test-based model selection, new E1/E2 fitting, resource-relaxed E2 campaign, or substitution of recovery scores into frozen E1.
- Six photometric predictors and seven classes remain fixed. Fitting, tuning, calibration and test roles stay separated. E1/E2 test outcomes were already observed; do not describe later work as an untouched prospective test.
- Preserve seven auxiliary tuning-history discrepancies, omitted historical E1 models/per-row predictions, conditional-on-success bias, unavailable dependencies, and hardware/load-dependent timings.
- Later fits retain 600-second trial/phase limits and 10 GiB per-worker limits. Existing RAM/CPU/disk admission guards remain active. Read-only optimization checks did not justify reducing the general fit memory reservation; no new reservation or growth-margin policy was deployed.

## Delivery and remaining work

- A verified interim ZIP is already on the laptop: `D:\LAMOST_Overall_EC2_Handoff_20261023\delivery\LAMOST_SCOPE_AMENDMENT_INTERIM_20261029T091814Z_97185c6.zip`.
- Its size is 92,769,172 bytes; SHA-256 `6ab2f215615531afbded804eefe2ff0a85cb5e691ee4a3117372fd99216e35bb`. EC2 CRC passed and the laptop copy matched the exact hash. It contains code, reports/results/tables/figures, not fitted models or raw array payloads.
- The readable interim report is on the laptop as `LAMOST_AMENDED_SCOPE_REPORT_20261029.md`. Its saved cutoff is 08:55:39 UTC, earlier than this live accounting.
- A one-shot fresh reporting job is armed for 16:15 IST today; check its actual outcome before claiming a newer ZIP exists. The report deadline supplied by the user is 17:00 IST.
- Remaining authorized work: finish selected cases under fixed policies, incremental artifact validation, required native calibration replay/audit, final descriptive analyses/figures/report, full EC2 archive CRC/SHA/member-manifest verification, final GitHub results push, small delivery ZIP and verified laptop transfer, then cleanly stop only project-owned workers/watchers.
- Current storage compaction is a live operational dependency, not a scientific evaluation. Verify its actual process/journal and the current queue before acting. Do not provision/resize AWS or delete unique results, historical backup pieces or unrelated Harbor material.

## Questions for your review

1. Which conclusions are defensible for submission from the currently validated, incomplete coverage, especially E2 and the E6 negative availability result?
2. Are the single-evaluation scope amendment, unequal repetition counts, reconstruction differences and low-precision flags disclosed clearly enough?
3. Identify any concrete scientific error, leakage, inconsistent denominator or unsupported claim in the saved report/tables; tie each finding to a file/cell rather than proposing broad new campaigns.
4. Prioritize essential reporting corrections and state any further scientific work as a separate future instruction. Do not treat a deadline as permission to fabricate success, relabel pending cases as failed, or reopen frozen E1.

