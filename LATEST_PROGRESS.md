# Latest project progress snapshot

Read-only registry snapshot observed at 2026-10-28T20:41:01.275758+00:00 UTC on the existing EC2. This is a database snapshot, not a live-process inventory. Existing figures remain tied to the validated 2026-10-28T17:00:39.712874Z analysis snapshot; they were not regenerated for this status refresh.

| Experiment | Planned | Successful | Scientific failures | Unsupported / unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 (55 resource; 26 supervisor-terminal manifests still started) | 10 unsupported | 0 |
| E1 recovery | 91 separate supplement | 24 | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1,773 | 1605 | 71 | 3 | 94 |
| E5 | 960 | 700 | 50 | 78 | 132 |
| E6 | 21 | 12 successful aliases | 3 ensemble failures | 6 unavailable | 0 |

The six E6 primary ensemble cases remain separate from the 15 member-reference aliases. The 759-case qualification verifies operational code/tests, not scientific completion. The 759 portable qualification fingerprint is 585030a538d446ab8be76db1ac40af837cf5766115e9dea3b040069e96bbbbd4.

Six successful validated E4 rep-3 random-forest treatment evaluations newer than the previous 18:38 registry snapshot are preserved in E4_INCREMENTAL_VALIDATED_20261028T200243Z_metrics.csv and E4_INCREMENTAL_VALIDATED_20261028T200243Z_per_class.csv, with source evaluation JSONs and hashes. The existing aggregate tables and figures remain dated to the 17:00:39Z analysis snapshot and do not include these six records.

E1 and E2 remain frozen. E2 retains 31 reconstruction accuracy differences, 210 low-precision class-report flags and four complete five-family correlation strata. Historical E1 models and per-test-row predictions remain omitted; seven auxiliary tuning-history discrepancies remain disclosed. Recovery remains a separate stopped supplement.

No bootstrap, bootstrap intervals or unsupported significance claims are included. E1's 180-second/6-GiB limits differ from later experiments' 600-second/10-GiB policy. Timing depends on hardware and shared-host load.

Fitted models, FITS, credentials, private process receipts, baseline/raw datasets and cache/archive payloads are excluded from this Git snapshot. Final publication remains gated on the full scientific ledger and validated final packages.
