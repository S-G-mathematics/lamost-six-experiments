# LAMOST execution continuation report

Observed EC2 state: 2026-10-26T22:06:31.212799+05:30 (Asia/Kolkata), 2026-10-26T16:36:31.212799+00:00 UTC.

The six-experiment project remains in progress. This is a dated checkpoint, not the final project report or final archive. Scientific work, engineering validation, models and artifacts remain on the existing approved EC2 host. No E1/E2 fits, stopped E1 recovery, bootstrap, AWS changes or Harbor operations were started.

## Verified current coverage

| Experiment | Planned evaluations | Successful | Failed | Unsupported/unavailable | Pending/active |
|---|---:|---:|---:|---:|---:|
| Frozen E1 | 765 | 674 | 81 | 10 | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 | 0 |
| E2 classical reference | 120 | 120 evaluated | - | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1256 | 42 | 3 | 472 |
| E5 | 960 | 613 | 27 | 23 | 297 |
| E6 | 21 | 12 | 0 | 9 | 0 |

Planned later experiment cases total 2,823, represented by 6,270 immutable dependency/evaluation tasks. E3 and E6 scientific grids are terminal, including failures/unavailable cases; final independent calibration-threshold validation and final project review remain outstanding. E4/E5 have pending planned comparisons. Frozen E1 source files (19), its exact 765-cell CSV hash, its validated report and four accepted E2 evidence documents were rechecked against the original source/startup records during this report.

E1 failures remain 55 resource failures plus 26 supervisor-terminal cases whose individual manifests remained started; the 10 unsupported cases are separate. The separate stopped E1 recovery supplement remains 24 successful retries, 10 failed retries, 2 user-stopped partial cells and 55 not attempted. None replace frozen E1 outcomes.

E2 reporting remains explicitly incomplete in primary coverage: 108/150 plus 120/120 classical references. Preserve 19 original/89 reconstructed primary and 43 original/185 reconstructed overall provenance, 31 reconstruction accuracy differences, 210 low-precision class reports, 1,596 total class reports and four complete five-family correlation strata out of 30. Do not generalize a relationship or significance from those four strata.

## What changed in this continuation

1. Reconnected to approved w7-ec2 and verified instance i-095641a281a4038b9, controller source identity, real model-worker process identities and actual queue state. A genuine storage-admission pause was diagnosed and resolved; a heartbeat or marker was not treated as liveness.
2. Applied the weighted-mean admission metadata precision correction. A finite numeric sample_weight_mean within 1e-12 of 1 now passes the already approved weighted 80k-RF resource profile. Three never-attempted tasks became eligible. No weights, model definitions, seeds, trial counts, trial search domains, fit caps or results changed. Controller bytes remained unchanged. Applied receipt: reports/engineering_audits/WEIGHTED_MEAN_PRECISION_GATE_APPLIED_20261026.json.
3. Installed the guarded one-shot cold-model archive driver and exact five-minute LAMOST_COLD_STORAGE_AIRBAG schedule. It verifies ownership, real controller/worker identities, source pins, queue state, storage, memory commitments, locks and archive journal lineage. It delegates at most one bounded transaction, backs off when memory is committed to scientific fits, and stops acting when science is terminal. Three failed started operations in one hour require review rather than endless retry.
4. The first actual guarded driver transaction completed on 2026-10-26T16:25:11Z: seven already consumed, validated model groups, 2,141,085,819 original bytes, 99.01 seconds, CRC verified. Their exact bytes are retained in the current BUILDING archive before redundant native paths are removed. No scientific model worker was signaled or new fit launched by this archive operation.
5. Updated exact-owned delivery cleanup for the added archive schedule; all three owned cron lines are recognized. Harbor and unrelated same-tag entries remain preserved. Cleanup fixture passed separately.
6. Installed a portable bundle of 145 unique tests across 14 test files and 20 current source records. The relocated suite passed in 12.35 seconds under 1 GiB/30-second bounds. Python3.12.3, NumPy2.3.5, sklearn1.8.0, SciPy1.17.0 and joblib1.5.3 came from the existing scientific venv; plotting support is separately recorded. A duplicate 12-test file was rejected before counting; an earlier wrong dependency precedence was preserved and superseded by the corrected proof. Receipt: reports/engineering_audits/PORTABLE_145_UNIQUE_CORRECT_ENV_PASSED_20261026.json.
7. The lightweight observer now uses a coherent read-only SQLite transaction and explicitly distinguishes an old storage marker from the controller's actual current disk inequality. It starts no work.
8. Read-only storage capacity/layout checks found the model writer already uses joblib compress=3, with little extra prefix compression; the cold format remains ZIP_STORED. Most attempt/checkpoint/canonical models already share inodes. No unique model, result, membership, incident evidence or backup piece was deleted. Future storage demand remains uncertain and will be monitored; illustrative median-size arithmetic is not a forecast.

## Current actual execution and resource policy

Controller actual identity verified: True. Actual verified model workers: 2. Unverified registry-running records: 0. Available RAM: 27.89 GiB; disk free: 53.6 GiB. These are this observation, not a promised future capacity.

Current worker tasks:
- e4/rep_1/fit/treatment/random_forest/G_tenth_generated_gmm; reservation 10.0 GiB; elapsed 1446.8 seconds across its trial/final-fit phases
- e4/rep_1/fit/treatment/random_forest/G_tenth_generated_kde; reservation 10.0 GiB; elapsed 453.1 seconds across its trial/final-fit phases

There is no fixed two-worker ceiling. Admission is bounded by actual CPU/RAM and proven task profiles, with host/Harbor reserve6GiB plus2GiB growth allowance, one nested thread, nice+10, hard10GiB process-tree fit cap,600-second scientific trial/phase limits and30-second termination grace. A fit task can last longer than600seconds because its fixed trials and final fit are separately capped. No replacement trials or automatic ordinary scientific retries are permitted.

Storage observation: {"estimate_refresh_interval_seconds": 300, "free_bytes_now": 57556086784, "headroom_bytes": 1486649901, "hold_marker_present": true, "minimum_free_bytes_from_controller": 56069436883, "note": "Storage marker is historical evidence, not a scheduling lock; controller uses free bytes and its current conservative input estimate.", "observation_age_seconds": 2.57, "observed_utc": "2026-10-26T16:36:28.638529+00:00", "status": "allowed_by_current_recorded_estimate"}.

## Validation still being completed

The latest saved incremental outcome audit validated 1,886 successful outcomes (1,771 physical plus115 aliases), including412 new outcomes, with zero integrity issues,18 known diagnostic limitations and9 validated supersessions. It read saved outcomes; it did not load/fit classifiers or independently recompute the conformal quantile. This audit is a dated subset, not coverage of results that completed later.

A real final-validation gap is being closed: replay each later successful physical route on its exact saved clean calibration rows, independently recompute k=ceil((n+1)*0.9) and the corresponding order statistic, compare saved q without changing it, and verify alias inheritance. The staged implementation uses frozen score interfaces/class order, immutable nonconformity vectors, provenance identities, a private durable phase ledger and externally verified600-second/10GiB supervision. The parent receipt and separate qualification must bind the raw audit without rewriting it.

No real calibration replay has run in this continuation as of this checkpoint. The full final artifact audit, calibration qualification, final numerical/figure review, final archive, laptop reports ZIP and final owned-worker/watchdog shutdown have not yet completed. Do not fabricate q validation or label the project complete. Preserve raw private process evidence on EC2 and exclude it from public packages.

## Archive custody, not final delivery

Current archive path: /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip
Current recorded bytes: 5504037167
Current recorded SHA-256: f879d959f3986afc3e4bd725487eacb6e3e3e7738974a0a01bc3eb17a03b2b49
Current retained model members: 30
Latest transaction: a5ca93fb432b48d9a4de71852701ce6e

This is a verified evolving BUILDING prefix, not the final six-experiment archive. Its recorded hash will change after a valid append. The first guarded batch's CRC/SHA, transaction and logical resolver checks are in reports/engineering_audits/cold_auto_compaction/20261026T162511Z_auto_storage_20261026T162325Z_70afb7ca.json. Existing frozen snapshot and E1 archive remain preserved.

## Scientific caveats and next execution

Preserve omitted historical E1 fitted pipelines/test-row predictions, the seven documented auxiliary E1 tuning-history discrepancies, original-versus-reconstructed E2 provenance, incomplete E2 primary coverage, low-precision classes, timing dependence on hardware/load, conditional-on-success comparisons, actual paired repetition counts and observed test information history. No bootstrap, significance claim or universally superior-method claim is introduced.

Keep E4/E5 running through the single controller, with validated checkpoints, no duplicate model queues and no ordinary terminal retries. Finish the externally supervised calibration replay integration, run small engineering checks, validate all planned terminal cases and complete exact candidate review. Then build the full archive and compact report/tables ZIP, verify CRC/byte size/SHA, copy the compact ZIP to the laptop, verify its hash and clean only exact-owned workers/watchdogs.

Resume from /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json, current SQLite state, actual process identities and the original immutable manifests. The dated laptop reports are historical observations.
