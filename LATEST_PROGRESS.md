# Latest project progress snapshot

Observer timestamp: 2026-10-28 04:09:30 UTC (09:39:30 Asia/Kolkata), on EC2. At that observation, no model workers were verified alive. A STORAGE_HOLD marker was present and the controller disk estimate was in backoff. This is a point-in-time observation, not a claim about later liveness.

| Experiment | Planned | Successful | Scientific failures | Unsupported or unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 |
| E1 recovery supplement | 91 | 24 retry successes | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary generators | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1546 | 71 | 3 | 153 |
| E5 | 960 | 697 | 50 | 78 | 135 |
| E6 | 21 | 12 historical member references | 3 | 6 | 0 |

Frozen E1 remains unchanged: its 81 failures comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained started; the 10 unsupported cells are distinct. The stopped recovery supplement is separate.

E2 is incomplete on its primary grid. The 31 reconstruction accuracy differences, 210 low-precision class flags, and four complete primary correlation strata remain disclosed. No bootstrap was run.

E3 is terminal at 64 successful, 3 failed, and 2 unavailable. E4 gained eight validated rep-2 random-forest treatment evaluations since the earlier export; their evaluation, validation, and task-result JSON are included below provenance/artifacts. The existing E4/E5 descriptive tables and figures were unchanged; no aggregate tables or figures were regenerated. E5 remains at 697 successful, 50 failed, 78 unavailable, and 135 waiting.

E6 has 15 historical member-reference rows (12 successful, 3 unavailable) and six primary ensemble rows (0 successful, 3 scientific failures, 3 unavailable). There is no successful five-member ensemble test evaluation and no ensemble-benefit claim. Calibration-q replay and final package validation remain pending.

This is an interim snapshot, not a completion claim. No new fitting, model scoring, or held-out inference was performed for this export update.
