# LAMOST current execution snapshot

Observed 2026-10-30T18:55:02.789384+00:00 / 2026-10-31T00:25:02.789384+05:30 IST. Interim status, not a completion report.

| Experiment | Planned | Successful/evaluated | Failed | Unsupported/unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | 0 |
| E1 stopped recovery (separate) | 91 | 24 | 10 | 55 not attempted | 2 | 0 |
| E2 primary | 150 | 108 evaluated | — | 42 unavailable | 0 | 0 further fits authorized |
| E2 classical reference | 120 | 120 evaluated | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1773 | 1632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 727 | 50 | 79 | 101 | 3 |
| E6 | 21 | 12 | 3 | 6 | 0 | 0 |

E6 successes are 12 reused member-reference evaluations. Zero primary ensemble test evaluations succeeded; three equal-weight ensemble tests timed out and three learned ensembles are unavailable. Do not interpret member references as ensemble successes.

## Remaining execution

- e5/rep_1/fit/direct/extra_trees/missingness_05 — waiting_for_dependency
- e5/rep_1/eval/direct/extra_trees/missingness_05 — waiting_for_dependency
- e5/rep_1/fit/direct/extra_trees/missingness_10 — waiting_for_dependency
- e5/rep_1/eval/direct/extra_trees/missingness_10 — waiting_for_dependency
- e5/rep_1/fit/direct/extra_trees/missingness_20 — waiting_for_dependency
- e5/rep_1/eval/direct/extra_trees/missingness_20 — waiting_for_dependency

Three scientific E5 cases remain, represented by three fit and three evaluation tasks. Their outcomes are not presumed successful. Existing ordinary scientific failures will not be retried.

## Approved resource policy

One fitting worker at a time, 6 GiB working-space reserve, 10 GiB process-tree memory limit, 600-second scientific phase/trial limits, 30-second termination grace, nested threads capped. Retired-result restoration liability and retrieval headroom are additionally reserved; final-archive capacity is assessed separately.

The verified controller and a storage-archive transaction are active at this observation. No model worker is active during that storage transaction. Disk pressure remains the execution bottleneck. Archive speedup was qualified on 844 tests; the first production pass still performs a full old-member verification, so no production speedup is claimed yet.

## Publication and validation

GitHub: https://github.com/S-G-mathematics/lamost-six-experiments . Both main and results/snapshot-2026-10-28 were independently verified at c860db7b5d75fb4f6b32212b76d1025fb88180c1. Appropriate available code, tables, figures and result arrays are published. Fitted models/FITS are excluded. This does not imply all unavailable historical E1 artifacts were recovered.

Root pre-reviewed existing E3 and E4 figures and saved reports/engineering_audits/ROOT_E3_E4_VISUAL_PREREVIEW_20261031.json. This is not a final candidate approval.

After the three cases are terminal: restore retired result arrays, run calibration replay and artifact validation, regenerate/validate final tables and figures, review the immutable final report candidate, verify full/compact archives and laptop delivery, publish final results and stop only project-owned watchers. Those steps remain pending.

Frozen E1 and its stopped recovery stay separate. E2 remains an explicitly incomplete primary analysis: 31 reconstruction accuracy differences, 210 low-precision class flags, and four complete five-family correlation strata retained. Bootstrap remains dropped. Harbor/shared caches and AWS infrastructure are untouched.
