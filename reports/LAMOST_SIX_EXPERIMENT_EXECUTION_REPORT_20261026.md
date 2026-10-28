# LAMOST six-experiment execution report: 26 October 2026

**Interim execution report. The six-experiment project is not complete.**

Observed on existing EC2 at 2026-10-25T19:14:39.710565+00:00 (2026-10-26T00:44:39.710565+05:30 Asia/Kolkata). Laptop activity is limited to interaction, reviewing copied figures, checksums and delivery.

| Experiment | Planned outcomes | Successful | Failed | Unsupported / unavailable | Pending / active | Phase |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | Frozen, preserved |
| E2 primary | 150 | 108 | 0 | 42 | 0 | Reporting finalized with incomplete coverage |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | Separate reference analysis |
| E3 | 69 | 64 | 3 | 2 | 0 | Terminal descriptive report reviewed |
| E4 | 1773 | 692 | 0 | 3 | 1078 | Scientific queue active |
| E5 | 960 | 76 | 0 | 23 | 861 | Clean references reused; corruption evaluation pending |
| E6 | 21 | 12 | 0 | 9 | 0 | Member report reviewed; primary ensembles unavailable |

## Frozen results and provenance

Frozen E1 still has all765 planned cells:674 scored successes,55 resource failures,26 supervisor-terminal cells whose old manifests remained started,10 unsupported. The current765-cell CSV and all19 frozen Python source hashes were verified while writing this report. No E1 fitting or recovery was restarted. The existing full E1 archive remains preserved; its earlier validated SHA-256 is bd4834a15d491844203ff7baf07b3b21dcdf972de97af68a744d8d2c042e7d34. This report did not rerun the full multi-gigabyte archive hash/CRC check.

The E1 recovery supplement remains stopped early at user request:24 successful retries,10 failed retries,2 user-stopped partials,55 not attempted. Its outcomes remain separate from frozen E1. The ARF min-leaf variant and abandoned saved-pipeline finalizer were not restarted.

E2 has108/150 primary evaluations and42 unavailable cells; its separate classical reference set has120/120. Four of30 budget/repetition strata have allfive primary generator families. Original and reconstructed provenance remain distinct:43 original saved fits and185 reconstructions across both sets,31 reconstruction accuracy differences,210 low-precision class reports among1596. The four required E2 source documents still match startup hashes. No additional E2 fits were run.

Historical E1 fitted pipelines and per-test-row predictions omitted from compact migration remain unavailable. The seven auxiliary tuning-history discrepancies remain disclosed. No bootstrap has been introduced.

## E3: direct, synthetic-only and real-only learning

All69 evaluation cases are accounted for:64 successful,3 direct-KDE prediction timeouts under the600-second policy,2 unavailable synthetic-RF evaluations caused by GMM/KDE repetition2 fitting memory-limit failures. All15 generator datasets were produced, each400000 rows, totaling6million saved synthetic rows across conditions. All43 successful synthetic learners bind to the exact shared dataset file SHA for their generator/repetition;24 also expose optional per-array hashes,19 older records do not.

Nine GMM/copula/Chow-Liu generators reused validated matching E2 reconstructed predictive components. Six ARF/KDE generator fits belong to E3 and do not repair E1. Shared real-only fits avoid duplicate training.

Direct GMM mean balanced accuracy0.805554, marginal coverage0.899597 and mean set size1.486998 across3 repetitions. Synthetic GMM versus matched real-only mean balanced-accuracy differences are -0.007641 for logistic(n=3),+0.010860 for random forest(n=2),+0.014895 for histogram gradient boosting(n=3). These descriptive contrasts do not establish significance or universal superiority.

A caution is retained: Chow-Liu synthetic logistic has mean marginal coverage about0.8984 but class-A coverage about0.0255 and class-A recall0. Marginal90% coverage does not imply classwise90%.

The selected-trial cost ledger excludes copied elapsed values from duplicate_cached slots while preserving consumed search slots. The two failed RF partial histories are retained; completed-trial time is a lower bound, aborted observations and unattempted slots are separate. Calibration/test phase times include model loading and I/O.

Root reviewed the E3 terminal descriptive report, matched denominators and three final figures. Independent full selected-model auditing remains part of project finalization.

## E4 and E5 remaining work

E4 covers one unchanged control and14 altered class-support conditions per repetition, with all17 direct methods and the prescribed weighting, ROS, SMOTE and five-family generated restorations. The1773 planned evaluation cases remain in the durable dependency graph.

An implementation defect had inserted nonuniform sample weights into untreated E4 cohort containers. All42 cohort containers were preserved and rebuilt with byte-identical scientific arrays/IDs and the correct schema. Only affected operationally invalid GMM attempts and blocked dependents were superseded. Invalid histories remain preserved; this was not an ordinary failed-science retry. Already valid weighted/ROS/SMOTE cohorts were retained.

E5 contains960 evaluation cases. Its currently successful cases are shared clean references; they are not evidence of completed corrupted-condition evaluations. The corruption masks and realizations are saved, with fitting-only changes, clean tune/calibration/test roles, frozen clean-selected configurations and no primary missingness indicators.

## E6 availability and negative result

All21 E6 accounting cases are terminal:12 successful member references,3 unavailable KDE member references and6 unavailable five-member ensembles. All15 selected pipelines exist, but the required3 direct-KDE member evaluations timed out. No ensemble candidate search, ensemble test inference or tuning-best-member selection ran; no ensemble gain is claimed. A successful member reference is not a completed ensemble evaluation.

## Controller, execution safeguards and resources

A single ownership-locked EC2 controller owns the6270-task graph. Atomic state, validated checkpoints, process identity checks and a five-minute watchdog implement the requested airbag method. No installed Airbag skill was available; no such skill is claimed. Actual PIDs plus process-start ticks and command identity are checked, rather than treating heartbeat age as liveness.

The user removed the oldtwo-worker cap. Scheduling now uses measured CPU/RAM headroom and conservative reservations, with10GiB process-tree memory and600-second trial/phase limits unchanged, one nested native thread,50k prediction chunks and30-second termination grace. OS/Harbor capacity is reserved; workers use nice+10. Ordinary terminal timeouts/failures are not automatically retried.

At this observation, available RAM was 24.11GiB and free disk 94.03GiB. Verified currently live scientific task keys:

- e4/rep_1/fit/direct/random_forest/A_half
- e4/rep_1/fit/treatment/hist_gb/F_half_generated_chow_liu
- e4/rep_1/fit/treatment/hist_gb/F_half_generated_copula
- e4/rep_1/fit/treatment/hist_gb/F_tenth_generated_chow_liu

Latest incremental evaluation audit: 762 successful outcome entries checked at 2026-10-25T19:01:39.121670+00:00, 0 integrity issues. The audit recomputes saved evaluation metrics/ID checks; it does not establish independent full model validation or recompute absent calibration score arrays.

## Delivery state and remaining completion requirements

E3 and E6 descriptive reports, complete ledgers and figures are saved under runtime_20261025/reports. E1/E2 frozen reports and archives are preserved. E6 data-only report regeneration now resolves artifacts under the supplied extraction root rather than relying on old absolute EC2 paths. E1/E2 static all-budget figures passed root visual/descriptive review, with48 protected scientific/source hashes unchanged. E1 axes explicitly identify development budgets and their80/10/10 fitting/tuning/calibration allocation. Receipt: reports/engineering_audits/FROZEN_E1_E2_FIGURE_ROOT_QA_PASSED_20261026.json.

Still required: finish all pending E4/E5 tasks under the recorded limits, account for every planned case, finish experiment and cross-experiment reports/tables/figures, perform final artifact/model and report audits, create the full EC2 archive and compact report/table ZIP, verify CRC/size/SHA-256, copy the compact final ZIP to laptop, and stop only project-owned workers/watchers after actual completion. No overall final archive or six-experiment completion is claimed here.

## Resume instructions

Use approved SSH alias w7-ec2 and root /home/ubuntu/lamost_e1_migration_20261023. Active runtime is runtime_20261025. Read AIRBAG_STATE.md, status.json, registry.json, manifests/freeze.json and RUN_RESUME_REPRODUCE.md; verify actual controller/worker identities before any launch. Preserve all current sources, evidence and artifacts. E1/E2 fitting and E1 recovery remain stopped; bootstrap remains dropped.
