# Latest project progress snapshot

Coherent read-only registry snapshot: 2026-10-29T07:49:47.720386+00:00 UTC. This is an interim ledger observation, not a claim of worker liveness or project completion.

| Experiment | Planned | Successful/evaluated | Recorded failures | Unsupported/unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 (55 resource; 26 supervisor-terminal manifests still started) | 10 unsupported | 0 |
| E1 recovery supplement | 91 separate | 24 | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 successful, 3 recorded scientific failures, 0 unsupported, 2 unavailable, 0 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 0 waiting/active / 69 | 3 | 2 unavailable | 0 |
| E4 | 1,773 | 1,621 successful, 71 recorded scientific failures, 0 unsupported, 3 unavailable, 67 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 11 waiting/active / 1,773 | 71 | 3 unavailable | 83 |
| E5 | 960 | 700 successful, 50 recorded scientific failures, 0 unsupported, 78 unavailable, 101 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 31 waiting/active / 960 | 50 | 78 unavailable | 132 |
| E6 all ledger rows | 21 | 12 successful member-reference aliases | 3 primary ensemble failures | 6 unavailable | 0 |

E4/E5 have 215 waiting cases in this ledger snapshot. No process liveness is inferred from those counts. E6 has zero successful primary ensemble test evaluations.

[Current timestamped report and tables](reports/deadline_submission_20261029/snapshot_20261029T074947Z/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md). [Current E3-E6 cell ledger](reports/CURRENT_CELL_LEDGER.csv). Existing broad figures retain their documented earlier cutoffs.

Frozen E1 and its stopped recovery supplement remain separate. E2 remains 108/150 primary with 120/120 classical references; reconstruction and low-precision caveats are retained in its report. Bootstrap remains dropped. E1 historical fitted-model/prediction omissions and seven auxiliary tuning-history discrepancies remain disclosed. Final calibration replay, full artifact validation and the final archive are pending; this project is not complete.

<!-- CURRENT REPETITION SCOPE -->
## Current repetition-scope amendment

At the registry snapshot in the linked interim report, the original 2,823 E3-E6 scientific cases and 6,270 DAG task rows remain the denominator. The score-independent amendment retained 45 selected E4/E5 evaluation cases with their dependency closure and marked 168 other pending E4/E5 scientific repetitions user-stopped. The complete selected dependency closure contained 167 tasks; 90 selected-closure tasks were pending at application. Previously terminal outcomes remain unchanged. Selected cases can complete after application; reports distinguish their current status from user-stopped work. The original three-repetition plan hash is unchanged, and the original full grid is not complete.

<!-- END CURRENT REPETITION SCOPE -->
