# Latest project progress

Observation: 2026-10-30T14:55:25.944320+00:00 UTC, based on the current read-only registry snapshot. Interim status; final validation and project completion remain pending.

| Experiment | Planned | Successful / evaluated | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 0 | 0 | 0 |
| E1 unsupported | 10 | 0 | 0 | 10 unsupported | 0 | 0 |
| E1 stopped recovery supplement | 91 | 24 | 10 | 0 | 2 user-stopped | 55 not attempted |
| E2 primary | 150 | 108 | 0 new failures | 42 unavailable | 0 | 0 |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 726 | 50 | 78 | 101 | 5 |
| E6 | 21 | 12 aliases | 3 | 6 | 0 | 0 |
| E3-E6 total | 2,823 | 2,434 including aliases | 127 | 89 | 168 | 5 |

E6 has zero successful primary ensemble test evaluations; its 12 successful rows are member-reference aliases. E5 remains incomplete. The current E5 rep-1 batch comprises nine newly validated cases; see [results and provenance](reports/E5_REP1_NINE_VALIDATED_20261030/README.md) and the complete [case ledger](reports/CURRENT_CELL_LEDGER.csv). The ninth test-outcome array is available as a separate [release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_ninth_validated_20261030T1452Z.zip). The figures and earlier narrative snapshots retain their original cutoffs.

The current archive-profile source and focused qualification are included as exact-hash provenance. The focused suite is fixture-based and does not establish a completed production archive transaction. Full artifact review and global calibration replay remain pending.

## New E5 repetition-1 results

8 newly indexed E5 rep-1 evaluations validated by the snapshot. See [the case table](reports/E5_REP1_INCREMENTAL_RESULTS_20261030T120813Z/RESULTS.csv) for method, route, corruption, balanced accuracy, coverage, set size, and sample sizes. The exact test-outcome arrays were uploaded and verified as a separate [GitHub release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_8_validated_outcomes_20261030T120813Z.zip).

These individual repetition-1 results do not form three-repetition means or universal rankings. The E5 plan remains at 960 rows, with 6 pending evaluations and separately retained failure, unavailable, and user-stopped cases.

## Frozen boundaries and source update

E1 remains frozen at 674 successful, 81 recorded failures (55 resource outcomes and 26 supervisor-terminal outcomes), and 10 unsupported of 765. The stopped recovery supplement is separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. The compact migration still omits most historical E1 model artifacts and per-row predictions; release evidence covers 80 of 674 primary prediction arrays and 24 of 24 recovery arrays.

E2 remains 108/150 primary evaluations, 42 unavailable original-model dependencies, and 120/120 classical references. Its reconstruction has 31 reconstruction-accuracy differences, 210 low-precision flags, and four complete correlation strata; this does not complete primary E2 coverage.

The prospective scope amendment selected 45 evaluations and marked 168 other E4/E5 repetitions user-stopped. Prior results and the original plan are preserved.

The installed controller is B668 bound to freeze F9FB. The [source closure and public qualification evidence](provenance/working_reserve_storage_20261030/README.md) records the approved 6 GiB working reserve with one concurrent fit. The 10 GiB per-fit ceiling and 600-second phase cap remain unchanged. This registry snapshot does not make a claim about current worker liveness.

Bootstrap remains dropped. No fitted models, FITS files, or raw training data are in Git or the result-array ZIP.
