# Latest project progress

Observation: 2026-10-30T12:08:13.342926Z UTC. This interim snapshot uses one read-only SQLite transaction over all 6,270 task rows. The project is not complete; full calibration replay, final artifact review, and final archive review remain pending.

| Experiment | Planned | Successful / evaluated | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 0 | 0 | 0 |
| E1 unsupported | 10 | 0 | 0 | 10 unsupported | 0 | 0 |
| E1 stopped recovery supplement | 91 | 24 | 10 | 0 | 2 user-stopped | 55 not attempted |
| E2 primary | 150 | 108 | 0 new failures | 42 unavailable | 0 | 0 |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 725 | 50 | 78 | 101 | 6 |
| E6 | 21 | 12 aliases | 3 | 6 | 0 | 0 |
| E3-E6 total | 2,823 | 2,433 including aliases | 127 | 89 | 168 | 6 |

E6 has zero successful primary ensemble test evaluations. Its 12 successful entries are E3 member-reference aliases. The 3 E6 failures and 6 unavailable rows do not support an ensemble-benefit claim.

The [current case ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/PLANNED_CASE_OUTCOMES_2823.csv), [ledger summary](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/SUMMARY.json), and [successful metadata crosswalk](reports/SCIENTIFIC_SUCCESS_ARTIFACT_COVERAGE_20261030/SUCCESSFUL_TASK_ARTIFACT_COVERAGE.csv) were refreshed from this snapshot. Historical ledgers remain preserved.

## New E5 repetition-1 results

8 newly indexed E5 rep-1 evaluations validated by the snapshot. See [the case table](reports/E5_REP1_INCREMENTAL_RESULTS_20261030T120813Z/RESULTS.csv) for method, route, corruption, balanced accuracy, coverage, set size, and sample sizes. The exact test-outcome arrays were uploaded and verified as a separate [GitHub release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_8_validated_outcomes_20261030T120813Z.zip).

These individual repetition-1 results do not form three-repetition means or universal rankings. The E5 plan remains at 960 rows, with 6 pending evaluations and separately retained failure, unavailable, and user-stopped cases.

## Frozen boundaries and source update

E1 remains frozen at 674 successful, 81 recorded failures (55 resource outcomes and 26 supervisor-terminal outcomes), and 10 unsupported of 765. The stopped recovery supplement is separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. The compact migration still omits most historical E1 model artifacts and per-row predictions; release evidence covers 80 of 674 primary prediction arrays and 24 of 24 recovery arrays.

E2 remains 108/150 primary evaluations, 42 unavailable original-model dependencies, and 120/120 classical references. Its reconstruction has 31 reconstruction-accuracy differences, 210 low-precision flags, and four complete correlation strata; this does not complete primary E2 coverage.

The prospective scope amendment selected 45 evaluations and marked 168 other E4/E5 repetitions user-stopped. Prior results and the original plan are preserved.

The installed controller is B668 bound to freeze F9FB. The [source closure and public qualification evidence](provenance/working_reserve_storage_20261030/README.md) records the approved 6 GiB working reserve with one concurrent fit. The 10 GiB per-fit ceiling and 600-second phase cap remain unchanged. This registry snapshot does not make a claim about current worker liveness.

Bootstrap remains dropped. No fitted models, FITS files, or raw training data are in Git or the result-array ZIP.
