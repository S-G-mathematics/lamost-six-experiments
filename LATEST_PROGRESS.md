# Latest project progress snapshot

Coherent read-only registry snapshot: 2026-10-29T07:49:47.720386+00:00 UTC. This is an interim ledger observation, not a claim of worker liveness or project completion.

| Experiment | Planned | Successful/evaluated | Recorded failures | Unsupported/unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 (55 resource; 26 supervisor-terminal manifests still started) | 10 unsupported | 0 |
| E1 recovery supplement | 91 separate | 24 | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 unavailable | 0 |
| E4 | 1,773 | 1,616 | 71 | 3 unavailable | 83 |
| E5 | 960 | 700 | 50 | 78 unavailable | 132 |
| E6 all ledger rows | 21 | 12 successful member-reference aliases | 3 primary ensemble failures | 6 unavailable | 0 |

E4/E5 have 215 waiting cases in this ledger snapshot. No process liveness is inferred from those counts. E6 has zero successful primary ensemble test evaluations.

[Current timestamped report and tables](reports/deadline_submission_20261029/snapshot_20261029T074947Z/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md). [Current E3-E6 cell ledger](reports/CURRENT_CELL_LEDGER.csv). Existing broad figures retain their documented earlier cutoffs.

Frozen E1 and its stopped recovery supplement remain separate. E2 remains 108/150 primary with 120/120 classical references; reconstruction and low-precision caveats are retained in its report. Bootstrap remains dropped. E1 historical fitted-model/prediction omissions and seven auxiliary tuning-history discrepancies remain disclosed. Final calibration replay, full artifact validation and the final archive are pending; this project is not complete.
