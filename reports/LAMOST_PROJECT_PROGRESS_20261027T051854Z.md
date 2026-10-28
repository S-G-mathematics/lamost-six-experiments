# LAMOST six-experiment progress - 2026-10-27T10:48:54.577957+05:30

This is an interim execution snapshot, not a final project report or completion claim. Values came from the read-only EC2 registry observer at the timestamp above. The observer verifies active workers against PID start ticks, NUL-delimited arguments, expected worker entrypoint, and request task identity. It does not use old heartbeat files for liveness.

Host: existing EC2 instance i-095641a281a4038b9. Controller identity verified; controller source SHA-256 964e3099ce9b39661519a67943a4db2126632b512ba0e7952c25a71cc10ae903. Observer recorded 25.99 GiB available RAM and 45.86 GiB free disk. These are point-in-time observations. Storage admission status was allowed_by_current_recorded_estimate. A STORAGE_HOLD.json marker is historical evidence, not by itself a scheduling lock.

## Experiment coverage

| Experiment | Planned cases | Successful | Scientific failure | Unsupported/unavailable | Waiting/planned | Running, identity verified |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1773 | 1407 | 70 | 3 | 293 | 0 |
| E5 | 960 | 652 | 27 | 26 | 252 | 3 |
| E6 | 21 | 12 | 0 | 9 | 0 | 0 |

E3-E6 rows cover 2,823 planned scientific evaluation cases; fitting, generation, and helper tasks are not evaluation cases. A scientific failure is a terminal recorded outcome. Unavailable means a dependency or evaluation is unavailable. Waiting/planned is nonterminal. Running is counted only after current process identity verification.

## E1 and E2

Frozen E1 remains 765/765 terminal: 674 successful evaluations, 81 failed cells (55 resource failures and 26 supervisor-terminal failures whose manifests remained started), and 10 unsupported cases. Unsupported cases are not included in the 81 failures. The separate stopped recovery supplement has 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. Recovery outcomes are not substituted into frozen E1.

E2 primary coverage remains 108/150 (19 original saved-fit evaluations and 89 reconstructed-fit evaluations); 42 cases are unavailable because their frozen E1 model dependencies failed. The separate classical-reference set is 120/120. The integrity audit covers 228 evaluated cells and 1,596 class reports, with 210 low-precision flags and zero recorded integrity errors. Four of 30 five-family strata are complete. The 31 reconstruction accuracy differences remain disclosed; no pooled-across-budget correlation or significance claim is made.

## E3-E6 and reviewed blocks

E3 is terminal at 64/69 successful, with 3 scientific failures and 2 unavailable dependencies. E6 is terminal at 12/21 successful member-reference evaluations and 9 unavailable; all 6 primary five-member equal/learned ensemble cases are unavailable. No ensemble evaluation, tuning-weight search, or tuning-best-member comparison was performed; no ensemble benefit is claimed.

Historical E4 comparison only: the progress snapshot dated 26 October 2026 12:48 IST recorded 1,192 successful, 42 failed, 3 unavailable, and 536 pending/active. This is an earlier snapshot, not a current count. Source: LAMOST_PROJECT_PROGRESS_20261026T071827Z.md.

E4 and E5 remain active. The completed blocks below are reviewed descriptive subsets, not evidence that either whole experiment is complete.

**E4 direct KNN:** 45/45 evaluations (3 unchanged controls plus 42 altered conditions); 42 matched altered-minus-control comparisons, 315 per-class metrics, and 294 per-class paired rows. Root arithmetic and figure reviews passed. In 22/42 altered cases, conformal sets contained all seven labels; these cases do not support an efficiency or calibration benefit claim.

**E5 direct Random Forest:** 30/30 evaluations (3 clean aliases plus 27 corrupted-fit evaluations); all 9 conditions are paired to clean controls. **E5 direct KNN:** 30/30 (3 clean aliases plus 27 corrupted-fit evaluations), with 27 matched corruption-minus-clean pairs. At 20% label noise, KNN paired mean changes versus its clean control were balanced accuracy -0.023067, coverage +0.000125, and mean set size +0.494126 (n=3). For the same condition, paired KNN-minus-RF changes were -0.005758, -0.000291, and +0.252103 respectively (n=3). These are descriptive matched-repetition results, not significance tests or universal rankings.

The E4 KNN and E5 RF/KNN blocks retain per-repetition results, per-class tables, provenance, and reviewed figures in this interim archive. E5-wide calibration-quantile replay and global E4/later-project calibration-q validation remain pending.

## Repetition counts

| Exp. | Rep. | Success | Failure | Unavailable | Waiting/planned | Running |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 | 0 |
| E4 | 1 | 536 | 27 | 1 | 27 | 0 |
| E4 | 2 | 458 | 23 | 1 | 109 | 0 |
| E4 | 3 | 413 | 20 | 1 | 157 | 0 |
| E5 | 1 | 218 | 9 | 2 | 88 | 3 |
| E5 | 2 | 216 | 9 | 22 | 73 | 0 |
| E5 | 3 | 218 | 9 | 2 | 91 | 0 |
| E6 | 1 | 4 | 0 | 3 | 0 | 0 |
| E6 | 2 | 4 | 0 | 3 | 0 | 0 |
| E6 | 3 | 4 | 0 | 3 | 0 | 0 |

## Limits and next handoff

No bootstrap was performed. Repetition summaries and paired changes are descriptive. Test outcomes for E1/E2 and reported E3-E6 evaluations have been observed, so the remaining project is not described as having an untouched prospective test set. Historical E1 fitted classifiers and per-test-row predictions were omitted from the compact migration; seven auxiliary tuning-history discrepancies remain documented. Timing depends on hardware and resource policy. Current source integrity is documented in the adjacent source-hash proof. This ZIP contains reports, tables, and figures only, not the full reproducibility archive.

Continue through the authorized controller from current registry and verified process state. Preserve frozen E1/E2 and reviewed block artifacts. Do not infer completion from this snapshot.
