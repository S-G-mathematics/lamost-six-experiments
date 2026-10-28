# Latest project progress snapshot

Observer time: 2026-10-28T07:25:59.962952+00:00 UTC (2026-10-28 12:52 IST), read from runtime/status.json. No scientific workers were active in that snapshot; storage-forecast admission backoff left 281 scientific evaluation cases waiting (148 E4 and 133 E5). This is a timestamped snapshot, not a claim about later liveness.

| Experiment | Planned | Successful | Scientific failures | Unsupported or unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 |
| E1 recovery supplement | 91 | 24 retries | 10 retries | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1551 | 71 | 3 | 148 |
| E5 | 960 | 699 | 50 | 78 | 133 |
| E6 | 21 | 12 historical member references | 3 | 6 | 0 |

E1 remains frozen. Its 81 failures comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained started; 10 unsupported cells are separate. Recovery is stopped and separate.

E2 remains incomplete on the primary grid. Preserve 31 reconstruction accuracy differences, 210 low-precision class flags, and four complete correlation strata. E3 remains 64 successful, 3 failed, and 2 unavailable.

The active E6 v2 primary grid has no successful ensemble test evaluations: six planned cases comprise three scientific failures and three unavailable dependencies. Historical member-reference scores are not ensemble outcomes. No ensemble-benefit claim is supported.

The 587/587 portable engineering qualification includes the earlier 579-test closure plus eight new tests. It does not represent scientific evaluation or make this Git snapshot self-contained. No bootstrap was used. Calibration-q replay and full project validation remain pending.
