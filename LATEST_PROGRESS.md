# Latest project progress

Observation: 2026-10-30T22:36:34.427111+00:00 UTC from one read-only SQLite transaction; interim status. Final artifact validation and global calibration replay remain pending.

| Experiment | Planned | Successful / evaluated | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 0 | 0 | 0 |
| E1 unsupported | 10 | 0 | 0 | 10 unsupported | 0 | 0 |
| E1 stopped recovery supplement | 91 | 24 | 10 | 0 | 2 user-stopped | 55 not attempted |
| E2 primary | 150 | 108 | 0 new failures | 42 unavailable | 0 | 0 |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 728 | 50 | 79 | 101 | 2 |
| E6 | 21 | 12 aliases | 3 | 6 | 0 | 0 |
| E3-E6 total | 2,823 | 2436 including aliases | 127 | 90 | 168 | 2 |

E6 has zero successful primary ensemble test evaluations; its 12 successful rows are member-reference aliases. E5 remains incomplete. Latest validated result: rep-1 direct Extra Trees on missingness_05, BA 0.766318, coverage 0.895524, set size 1.539060 (n=500,000 test; 10,000 calibration; one selected repetition). Its validated test-outcome array is a [separately verified release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_missingness05_et_20261030T223329Z.zip); the canonical payload count is 2,324 based on the prior 2,323-row audit plus this exact new member. The paired label_noise_20 ET fit failed the configured RSS limit; its evaluation is unavailable and no partial model is published. See the [current full case ledger](reports/planned_case_ledger.csv) and [dated snapshot](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030T223634Z/README.md). The [latest payload coverage addendum](reports/RESULT_PAYLOAD_COVERAGE_DELTA_20261030T223634Z.json) records this one-array increase.

The current archive-profile source and focused qualification are included as exact-hash provenance. The focused suite is fixture-based and does not establish a completed production archive transaction. Full artifact review and global calibration replay remain pending.

## Earlier E5 repetition-1 results (12:08 UTC snapshot)

8 newly indexed E5 rep-1 evaluations validated by the snapshot. See [the case table](reports/E5_REP1_INCREMENTAL_RESULTS_20261030T120813Z/RESULTS.csv) for method, route, corruption, balanced accuracy, coverage, set size, and sample sizes. The exact test-outcome arrays were uploaded and verified as a separate [GitHub release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_8_validated_outcomes_20261030T120813Z.zip).

At that 12:08 UTC snapshot, the E5 plan had 6 pending evaluations. These individual repetition-1 results do not form three-repetition means or universal rankings; later availability is recorded in the current case ledger above.

## Frozen boundaries and source update

E1 remains frozen at 674 successful, 81 recorded failures (55 resource outcomes and 26 supervisor-terminal outcomes), and 10 unsupported of 765. The stopped recovery supplement is separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. The compact migration still omits most historical E1 model artifacts and per-row predictions; release evidence covers 80 of 674 primary prediction arrays and 24 of 24 recovery arrays.

E2 remains 108/150 primary evaluations, 42 unavailable original-model dependencies, and 120/120 classical references. Its reconstruction has 31 reconstruction-accuracy differences, 210 low-precision flags, and four complete correlation strata; this does not complete primary E2 coverage.

The prospective scope amendment selected 45 evaluations and marked 168 other E4/E5 repetitions user-stopped. Prior results and the original plan are preserved.

The installed controller is B668 bound to freeze F9FB. The [source closure and public qualification evidence](provenance/working_reserve_storage_20261030/README.md) records the approved 6 GiB working reserve with one concurrent fit. The 10 GiB per-fit ceiling and 600-second phase cap remain unchanged. This registry snapshot does not make a claim about current worker liveness.

Bootstrap remains dropped. No fitted models, FITS files, or raw training data are in Git or the result-array ZIP.

## Working-storage source qualification (2026-10-30T18:22:37.090314Z)

The current portable engineering bundle passed 844/844 cases (105 subtests) at 18:05 UTC. The update adds exact member-verification reuse under validated prior-commit proof; new payload checks remain unchanged and absent proof still triggers full streaming verification. The 6 GiB working reserve, one fit, 10 GiB worker limit, and 600-second phase/trial caps are unchanged. The adoption snapshot at 18:16 UTC records the first current-source archive pass running; production cache-reuse speedup has not been measured. Read-only registry status remains 2,435 successes (including 12 E6 aliases), 127 failures, 90 unavailable, 168 user-stopped, and 3 pending. See [the qualification note](docs/WORKING_STORAGE_844.md) and [current case ledger](reports/planned_case_ledger.csv).


## New E5 evaluation (snapshot 2026-10-30T22:36:34.427111+00:00)

The direct Extra Trees E5 missingness_05 repetition-1 evaluation validated successfully at 2026-10-30T22:33:29.794927+00:00 UTC: balanced accuracy 0.766318, coverage 0.895524, set size 1.539060, with 10,000 calibration and 500,000 test rows. It is a single selected repetition (n=1); no SD or inferential claim is made. The current ledger records 2,436 successful E3-E6 rows (including 12 E6 aliases), 127 failures, 90 unavailable, 168 user-stopped, and 2 pending. E5 has 728 successful, 50 failed, 79 unavailable, 101 user-stopped, and 2 pending of 960. E6 still has zero successful primary ensemble test evaluations. [Case result](reports/E5_MISSINGNESS05_ET_REP1_20261030T223634Z/README.md) and [full ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030T223634Z/README.md).
