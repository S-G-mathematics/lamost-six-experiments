# Latest project progress snapshot

Observer timestamp: 2026-10-28T11:12:34.883459+00:00 UTC (2026-10-28 16:42:34 IST), read from runtime/status.json. The active list is not an OS process inventory or liveness check.

| Experiment | Planned | Successful | Scientific failures | Unsupported or unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 |
| E1 recovery supplement | 91 | 24 retries | 10 retries | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1563 | 71 | 3 | 136 |
| E5 | 960 | 700 | 50 | 78 | 132 |
| E6 | 21 | 12 historical member references | 3 primary failures | 6 unavailable | 0 |

E1 remains frozen at 765 terminal: 674 successful, 81 failed (55 resource failures and 26 supervisor-terminal cells whose manifests remained started), plus 10 unsupported. Its recovery supplement remains separate and stopped: 24 successful retries, 10 retry failures, 2 user-stopped partial cells and 55 not attempted.
E2 remains incomplete on the primary grid: 108/150 primary evaluations and 120/120 separate classical references. Preserve 31 reconstruction accuracy differences, 210 low-precision class-report flags and four complete primary correlation strata. E3 remains 64 successful, 3 failed and 2 unavailable.
At this observer snapshot E4 has 136 waiting cases and E5 has 132. The dated incremental supplement contains newly validated E4 outcomes since the previous Git snapshot.
E6 has no successful primary ensemble test evaluation. The 12 saved member-reference scores are not ensemble outcomes. No ensemble-benefit claim is supported.
The latest portable engineering qualification is 667/667 passed on EC2 at 2026-10-28T10:00:33.925387+00:00; 653/653, 596/596 and earlier 587/587 proofs remain retained as history. These engineering tests do not count as scientific evaluations. This is an interim snapshot, not a final six-experiment report. Global calibration-q replay, cross-experiment validation and final project delivery remain pending.
No bootstrap was used. Historical E1 pipelines and predictions omitted from the compact migration and seven auxiliary tuning-history discrepancies remain documented. Hardware and resource-policy differences limit timing comparisons.
