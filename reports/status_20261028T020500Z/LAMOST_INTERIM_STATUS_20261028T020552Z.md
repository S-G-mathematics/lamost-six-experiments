# LAMOST six-experiment interim status

Observation: 2026-10-28 02:05:52 UTC / 07:35:52 IST  
EC2: i-095641a281a4038b9  
Project root: /home/ubuntu/lamost_e1_migration_20261023  
Runtime: /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025

This is an interim status record, not a final project report or delivery receipt. The fresh read-only observer was run from the existing EC2 at the observation time. It saw 6,270 registry tasks, a verified controller, zero verified model workers, and zero registry-running tasks whose process identity could not be verified. The observer is at runtime_20261025/source/observe_progress.py.

## Current operating state

At 02:05:52 UTC the observer reported:

- Available RAM: 28.75 GiB.
- Free disk: 34.65 GiB.
- The controller storage estimate was fresh (age 1.87 seconds), but disk headroom was -3,108,928,496 bytes relative to its current minimum-free-space estimate. Storage admission was therefore in backoff.
- Both ADMISSION_HOLD.json and STORAGE_HOLD.json were present.
- No model worker was running or awaiting process-identity verification in the registry.

The last process-specific archive observation available to this report was root's verified check at 02:04 UTC. It identified operation auto_storage_20261028T015304Z_dbcc142b, with its wrapper and child verified and the child creating a backup; no scientific fit was active. The 02:05:52 observer does not inventory that storage child, so this report does not claim that it was still live at 02:05:52. Recheck its actual argv, process start ticks, and operation receipt before relying on liveness.

The archive operation is not a final project archive. The pre-operation archive metadata recorded 37,889,733,875 bytes and SHA-256 beginning 5ec1fb. Repeated verification of the approximately 38 GB archive for small batches has been the storage bottleneck. The raw storage watcher was paused pending a successful transaction. A prior prewrite wrapper stopped on a stale literal source-pin check before archive or scientific mutation; the corrected pin was qualified. Treat that as an operational incident, not a scientific failure. The 8 GiB / 64-group packing profile is staged, not running or qualified. Scientific resource limits have not been raised by that profile. Do not infer that any model timeout was caused by archive I/O without evidence.

## Experiment accounting at the observation

The observer groups validated-terminal outcomes separately from waiting work. Waiting rows are not failures.

| Experiment | Planned scientific cases | Successful | Scientific failures | Unsupported / unavailable | Waiting | Current phase |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | Frozen and terminal; no more E1 fits |
| E2 | 270 across separate primary and classical groups | 228 evaluated | 0 new failed evaluations in this accounting | 42 primary unavailable | 0 | Reporting finalized with incomplete primary coverage |
| E3 | 69 | 64 | 3 | 2 unavailable dependencies | 0 | Terminal; reporting and cross-project synthesis remain |
| E4 | 1,773 | 1,533 | 71 | 3 unavailable dependencies | 166 | Waiting for storage admission; no model workers observed |
| E5 | 960 | 697 | 50 | 78 unavailable dependencies | 135 | Waiting for storage admission; no model workers observed |
| E6 | 21 | 12 | 3 | 6 unavailable dependencies | 0 | Terminal ledger; primary ensemble results remain unavailable |

The E2 row is split as follows: 108 of 150 primary generator evaluations and 120 of 120 classical reference evaluations are present. The 42 missing primary cases arise from unavailable original model dependencies. The 228 evaluated cases produced 1,596 class reports; the integrity audit recorded zero errors and 210 low-precision class flags. The 31 original-versus-reconstructed accuracy differences remain disclosed. Only four five-family correlation strata are complete; describe them as limited descriptive results, not a general relationship.

For E6, keep the 15 historical member-reference rows separate from the six primary ensemble tasks. The references are 12 successful and 3 unavailable. The six E6-v2 primary tasks have 0 successful test evaluations, 3 terminal test-phase timeouts, and 3 unavailable dependent modes sharing those test-phase failures. The earlier six feature-order attempts are preserved as operationally invalid/superseded history; they are not additional scientific failures. The independent E6 tuning-ledger audit below validates tuning artifacts only and does not change these test outcomes.

### Per-repetition validated-terminal and waiting counts

| Experiment | Repetition | Successful | Failure | Unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 |
| E4 | 1 | 548 | 27 | 1 | 15 |
| E4 | 2 | 519 | 23 | 1 | 48 |
| E4 | 3 | 466 | 21 | 1 | 103 |
| E5 | 1 | 233 | 18 | 18 | 51 |
| E5 | 2 | 228 | 16 | 44 | 32 |
| E5 | 3 | 236 | 16 | 16 | 52 |
| E6 | 1 | 4 | 1 | 2 | 0 |
| E6 | 2 | 4 | 1 | 2 | 0 |
| E6 | 3 | 4 | 1 | 2 | 0 |

The six E6 rows per repetition combine the member-reference and primary task categories above; consult the current registry and E6 execution ledger for the category split.

Root's current work estimate is 296 remaining fit cases: E4 has 119 RF treatment fits and 45 ExtraTrees fits; E5 has 105 synthetic RF fits and 27 ExtraTrees fits. The accompanying estimate is 301 evaluation cases, including 3 aliases. The fresh registry observer shows 166 E4 and 135 E5 waiting cases, totaling 301. These estimates are queue metadata, not an ETA. Prior completed RF4 fits took about 5 to 10 minutes under their recorded execution profile; do not project that time to other methods or repetitions.

## Frozen experiments and preserved evidence

### E1

Frozen E1 remains 765/765 terminal: 674 successes, 81 failures, and 10 unsupported cases. Of the 81 failures, 55 were resource failures and 26 were supervisor-terminal cells whose manifests remained marked started. Keep unsupported cells separate from failures. No further E1 fits, retries, ARF variants, or saved-pipeline recovery work are authorized or needed.

The stopped recovery supplement remains separate: 24 successes, 10 failures, 2 user-stopped partial cells, and 55 not attempted after the stop decision. It is not a completed recovery study and its outcomes do not replace frozen E1.

The compact migration omitted historical fitted pipelines and per-test-row prediction arrays. Some original fit artifacts are available; do not describe all historical fits as missing or claim full recovery of the omitted artifacts. Seven auxiliary tuning-history discrepancies remain documented in the affected 10k GMM and 30k CART / linear-SVM cells. Full original tuning histories for the affected study/CSV files remain unavailable. The known history limitations do not invalidate already verified completion metrics.

### E2

E2 remains finalized descriptively but incomplete in primary coverage. Preserve the original-versus-reconstructed provenance flags and all 31 accuracy differences. Retain all 210 low-precision class-report flags and equal-class aggregation. Do not substitute exploratory available-only correlations or classical references for the primary five-family analysis. No additional E2 campaign is authorized.

Useful saved references include:

- runtime_20261025/reports/E2_INDEPENDENT_TABLE_REAUDIT.md
- runtime_20261025/reports/E2_CORRELATIONS_INDEPENDENTLY_VERIFIED.csv
- runtime_20261025/reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv

### E3

E3 is 69/69 terminal: 64 successful, 3 scientific failures, 2 unavailable dependencies. Keep individual repetitions, route comparisons, and failure coverage visible. A known artifact limitation is recorded for the E3 real-only RF rep 1 publication receipt: its selected pipeline, selection, validation, and 80k fit evidence were retained, but fit_publication.json is absent. Preserve the scientific success and disclose the narrower publication-provenance limitation. Do not fabricate the missing receipt.

### E6 tuning-only audit

The independently reproduced tuning search is saved at runtime_20261025/reports/engineering_audits/e6_tuning_only_20261028/E6_TUNING_ONLY_AUDIT.md with audit.json and the input SHA inventory. All six mode/repetition input groups remained unchanged. The learned candidate counts were 1,606 / 1,558 / 1,606; selected indices were 1,050 / 1,058 / 1,261. Recomputed learned tuning balanced accuracy was 0.80750 / 0.80177 / 0.80905; equal-weight tuning balanced accuracy was 0.71054 / 0.71019 / 0.71188. GMM was tuning-best in all three repetitions.

Learned weights (GMM, copula, ARF, KDE, Chow-Liu) were:

| Repetition | Tuning-selected weights |
|---|---|
| 1 | 0.817912, 0.022277, 0.011825, 0.121437, 0.026549 |
| 2 | 0.776926, 0.051456, 0.011086, 0.155207, 0.005325 |
| 3 | 0.728127, 0.050965, 0.006219, 0.045693, 0.168997 |

These are tuning-only selection metrics and weights. They are not test metrics, evidence of conformal performance, or evidence that an ensemble improves performance. No successful E6 primary test evaluation is available.

## Current source, qualification, and remaining gates

- Current controller: runtime_20261025/source/controller.py, SHA-256 d34bf3db889ee7c642cf28d079cbeb32f27fb772584163f497e78499a994d5ac.
- Current freeze: runtime_20261025/manifests/freeze.json, SHA-256 07e8a2abfcd7ad0e7348c880f845e39f9ce4e88de0e2957d317d224f72ac2b2b.
- Portable engineering qualification: reports/PORTABLE_TEST_PASS_b3200c0ac73e311b23048f769b5a1ac0074cd918d35c22c621f4bd8864384a60.json, SHA-256 1d78bda691292515fa4c77fec4a6323c65345d7d332cafab5a2ba697f36f6f86. It records 552 of 552 planned engineering tests passing at 2026-10-28 01:51:13 UTC with measured process-tree RSS. This is software qualification, not scientific completion.
- The 01:41 UTC RF4 and history-cache/reaper qualifications are reports/engineering_audits/RF4_EXECUTION_QUALIFICATION_20261028.json and REAPER_HISTORY_CACHE_QUALIFICATION_20261028.json. Wrapper/controller pin repair is recorded at WRAPPER_CONTROLLER_PIN_REPAIR_20261028.json. These are engineering receipts and do not imply current worker liveness.
- Stale archive zombie/hold recovery was recorded at STALE_ARCHIVE_ZOMBIE_HOLD_RECOVERY_20261028.json. Current storage backoff and hold are new state; do not clear them manually.
- E1 remains frozen at its historical 6 GiB / 180-second policy. Later experiments have a recorded default of at most two fit workers, 10 GiB per worker, and 600-second trial/final phases; where a qualified task-specific admission profile is recorded, keep it limited to those exact task classes. Do not alter either policy to meet a desired outcome.
- There has been no global calibration-q replay validating every final archived evaluation. Calibration thresholds must be replay-validated before final claims and packaging.
- Final project report, all-experiment cross-analysis, final full archive, compact reports/tables/figures ZIP, CRC/SHA/size verification, existing laptop handoff copy, and clean stop of project-owned workers/watchers remain pending.
- The finalizer's collection-manifest history omission has a staged fix awaiting publication. Do not mark the final archive verified until the applied collector includes the required history and its archive manifest is checked.

Bootstrap remains dropped. Do not add bootstrap intervals, statistical significance, or universal method claims. E1/E2 test results have already been observed; the remaining experiments are not a prospective untouched-test project. Preserve role boundaries and keep fit / tuning / calibration / test use explicit. Report descriptive means, sample standard deviations, paired differences, actual successful repetitions, failures, and unavailable cases with denominators. Timing comparisons are hardware-, host-load-, and resource-profile-dependent. The archive overlap is observed, but it does not establish that archive I/O caused any particular model timeout.

## Safe observation and continuation

Approved existing EC2 alias: w7-ec2. Read-only observation command:

    ssh w7-ec2 'cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025 && ../venv/bin/python source/observe_progress.py --by-rep'

Use a fresh observer and actual process-identity checks before any operational decision. Do not treat a heartbeat, registry status alone, or a prior timestamp as proof that a process remains alive. The controller already exists and owns the task registry; do not start a second controller or launch duplicate model workers. Resume authorized scientific work only through the existing controller after its current storage estimate permits admissions. Do not clear ADMISSION_HOLD.json or STORAGE_HOLD.json manually.

Resume the remaining pre-authorized E4/E5 cases after the verified archive transaction succeeds and the controller's storage admission changes to allowed. Keep no more than two fitting workers, respect the frozen experiment policies and fixed search budgets, and never automatically retry ordinary terminal failures. Then finish valid E6-v2 tasks only where their frozen dependencies and fixed policies permit; do not turn the tuning-only audit into test outcomes.

After science reaches terminal states, validate every result and q replay, refresh complete planned-denominator reports/figures and the project completion matrix, then create and CRC/SHA-verify the final full and compact archives. Deliver the compact ZIP to the established laptop handoff directory only after it is verified. Stop project-owned workers/watchers cleanly after completion, without touching Harbor.

## Key resume locations

- Registry and controller: runtime_20261025/registry.sqlite and runtime_20261025/source/controller.py.
- Fresh observer: runtime_20261025/source/observe_progress.py.
- Frozen E1 report: project/benchmark/results/e1_report_validated_no_bootstrap.json.
- E3 terminal report and ledger: runtime_20261025/reports/E3_FINAL_DESCRIPTIVE_REPORT.md and E3_FINAL_CELL_LEDGER_69.csv.
- E2 independent table/reconstruction checks: runtime_20261025/reports/E2_INDEPENDENT_TABLE_REAUDIT.md and E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv.
- E6-v2 task ledger: runtime_20261025/reports/E6_EXECUTION_TERMINAL.json; consult the live registry for current state.
- E6 tuning-only audit: runtime_20261025/reports/engineering_audits/e6_tuning_only_20261028/.
- Full archive area: /home/ubuntu/lamost_e1_migration_20261023/packages/. The existing BUILDING archive is not the final project delivery.
