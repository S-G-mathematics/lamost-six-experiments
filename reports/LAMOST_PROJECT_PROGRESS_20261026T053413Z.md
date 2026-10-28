# LAMOST six-experiment interim progress

Observed: 2026-10-26T11:04:15.799752+05:30 (Asia/Kolkata).

The complete six-experiment project remains active. Final validation and delivery are pending. Scientific work continues only on the existing EC2 instance i-095641a281a4038b9; unrelated Harbor work was not modified.

| Experiment | Successful/evaluated | Scientific failure | Unsupported/unavailable | Pending or active |
|---|---:|---:|---:|---:|
| Frozen E1 | 674 | 81 | 10 | 0 |
| E2 primary | 108 | — | 42 | 0 |
| E3 | 64 | 3 | 2 | 0 |
| E4 | 1172 | 42 | 3 | 556 |
| E5 | 613 | 27 | 23 | 297 |
| E6 | 12 | 0 | 9 | 0 |

E2 also retains 120/120 classical-reference evaluations. Its primary coverage remains 108/150; unavailable cells are not filled by new E2 fitting. E6 has 12 member-reference results and 9 unavailable outcomes, including all six primary ensemble cases. No ensemble weight search or selected weights are fabricated.

## Execution and resource changes

An actual process check verified the controller and 3 model workers at this observation. Available RAM was 23.64 GiB and free storage 69.06 GiB. Process identities were checked using kernel PID/start ticks and worker command lines; heartbeat files were not used as liveness evidence.

The user-authorized concurrency ceiling is derived from CPU/headroom rather than the former two-worker cap. Native numerical threads remain capped, with capacity reserved for the OS and Harbor. Hard scientific limits remain 10 GiB per later-experiment worker and 600 seconds per trial/final-fit/generation/calibration/evaluation phase; frozen E1 retains its different original policy.

Validated admission estimates allow narrow, never-attempted RF evaluations and fitting cells to share memory more efficiently. A pinned 25-fit audit contains 202 executed tuning phases and 25 selected-fit phase receipts, with maximum recorded phase RSS 3,907,392 KiB. The prospective 5 GiB RF-fit estimate is confined to the recorded 80,611–82,394-row envelope and exact supported input/configuration gates. This estimate is not a hard cap or a worst-case guarantee; measured growth promotes reservation to 10 GiB and pauses new admissions. Existing attempts keep their recorded profiles.

The estimate now also covers matching future repetitions of RF trained on KDE-restored data for the five measured condition types. Raw KDE methods and their terminal timeout outcomes are unchanged. A pending 80,610-row cell falls outside that lower envelope and keeps the previous reservation.

## Validation and reporting work completed

- A bounded independent audit of the saved E3 real-only RF repetition-1 model passed with zero issues or diagnostics. Model, selection, role and source files were unchanged. The historical publication receipt remains absent and was not reconstructed. The audit performed no fitting, calibration, generation or test prediction.
- Eleven reporting/storage-reader source files were installed after byte-hash, import, extracted-layout and integration checks. Fitting-engine sources and active worker requests were unchanged; scientific workers were not signaled.
- E4 control contrasts, E5 overall and per-class paired effects, and summaries now preserve exact repetition/condition/method/route matching, per-metric n and sample SD, explicit missing comparisons, and undefined singleton SD.
- Complete condition appendices cover all 910 E4 summary strata, 288 E5 overall strata and 2,016 E5 per-class strata. Exact planned repetition totals are 2,730, 864 and 6,048 respectively. Duplicate, missing or foreign repetition IDs fail validation.
- Main heatmaps keep all planned cells, show matched n/3, and use shared color scales only within compatible metrics. Grey cells mean no matched repetitions; they are not assigned zero scores. Crowded overview plots remain secondary to the readable effect figures.
- Portable engineering tests and their tiny public fixtures were published. All 86 passed in a relocated archive-native layout without access to the original staging code or research models. Run on EC2 with LAMOST_TEST_PYTHON set to the recreated environment, then bash runtime_20261025/tests/run_portable_tests.sh.

## Artifact storage and delivery state

No fitted model path was removed and no BUILDING or final overall archive was created during this work. The first candidate was checked read-only: E4 repetition-1 direct RF/A_half, 58,703,060 bytes, three owned hardlinks, one terminal consumer and no matching live process. Its proposed archive transaction must revalidate all identities before execution.

The installed archive tools use verified ZIP members, immutable model identities, journaled recovery, alias restoration, and the same growing ZIP for eventual full packaging. Two public resource-review JSONs are included byte-for-byte in the future archive; private operational process/cleanup records remain excluded.

The original E1 snapshot and stopped recovery supplement remain separate. Recovery counts remain 24 successful retries, 10 retry failures, 2 user-stopped partial cells and 55 not attempted. Bootstrap remains dropped. No E1 or E2 fitting was started.

Historical missing E1 models/predictions and seven auxiliary tuning-history discrepancies remain disclosed. E2 original/reconstructed indicators, 31 classification differences, 210 low-precision class reports and four complete correlation strata remain unchanged.

## Remaining completion work

Continue E4/E5 through their fixed scientific queues and account for every planned case. Then perform the full fresh selected-model and outcome audit, regenerate final tables/figures and condition appendices, review the exact final report candidate, verify the full archive CRC/size/SHA-256 and compact delivery ZIP, transfer the compact package to the laptop, and stop only project-owned services after completion. There is no current external access/resource blocker.

Current companion case-index snapshot: reports/overall_case_index/snapshot_20261026T053413Z. It contains 3,858 main scientific cases and 91 separate recovery rows. Controller dependencies remain a separate 6,270-task DAG.

This file is an interim progress report. It does not declare the project complete.
