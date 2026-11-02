# LAMOST Experiment 1: detailed EC2 handoff and status

**Prepared:** 2026-10-24T07:50:19+00:00 UTC  
**Scope:** Frozen Experiment 1, its separately labeled retry/recovery work, packaging, and outstanding decisions. Experiments 2-6 remain dormant.

## Executive status

- Frozen E1 finished all 765 planned cells: **674 successful, 81 failed, 10 unsupported, 0 pending**. The 81 failures comprise 55 reported resource failures and 26 supervisor terminal failures whose cell manifests remained at started status.
- The user explicitly dropped paired bootstrap. The validated descriptive report is on EC2 at /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1_report_validated_no_bootstrap.json.
- After frozen E1 ended, the user explicitly requested retries of failed cells and asked that ARF be made to work where possible. Those runs are separate from the frozen result because compute limits changed.
- Live recovery at this report timestamp: **24 successful, 9 failed, 2 active, 46 queued, 10 small-budget ARF cells awaiting feasibility**. Live model workers at that timestamp: RBF SVM n=100,000 rep=5 (PID 1223873) and ARF n=100,000 rep=4 (PID 1223932). These numbers will change as EC2 queues continue.
- The verified full ZIP on EC2 is a dated **frozen-final plus recovery snapshot**, not a claim that recovery is complete. It captured 19 successful and 6 failed recovery cells at 2026-10-24T06:36:28 UTC.

## Access, host, migration, and verification

- Used the user's existing approved SSH alias **w7-ec2**. No EC2 instance was provisioned, no security settings changed, and no private key material was requested.
- Existing host: instance i-095641a281a4038b9, hostname ip-172-31-11-178, type c7i.4xlarge, 16 CPUs, 30 GiB RAM. At migration, approximately 140 GiB disk was free. At this report, approximately 126.2 GiB is free. Unrelated shared-host processes/containers were left in place.
- Copied the user's ZIP to EC2 and extracted it into a new isolated project directory: /home/ubuntu/lamost_e1_migration_20261023/project. ZIP SHA-256: fee34e6a648c21d67ea5e9d43153f9889bc81fbe69ef27bf4053f7161cb9a0be.
- Ran python3 verify_compact.py --root . --restore-links on EC2. It verified 5263 included files and 19 frozen Python source hashes, and restored 1306 role hardlinks. The original completion hashes matched at migration. A later recheck found 0 mismatches among the 19 frozen Python files.
- Installed the exact 35 dependency pins in an EC2 venv, checked imports and pip consistency. EC2 Python is 3.12.3 versus original 3.12.14; NumPy is 2.3.5. Original native Parquet inputs were used for the runner; the cleaned CSV is only a convenient view.
- Migration receipt: /home/ubuntu/lamost_e1_migration_20261023/migration_receipt.json.

## Frozen E1 execution

- Snapshot arrived with 652/765 terminal cells: 594 successful, 48 failed, 10 unsupported; 113 genuinely pending. The first resumed cell was n_300000/rep_4/arf.
- Ran the documented sequential command durably in tmux on EC2, with one model worker, seed 271828, 180-second trial timeout, 6 GiB process limit, 50,000-row prediction chunks, and resume. Did not retry old terminal cells or the already repaired 3K rep4 ARF collision.
- Exact command, from the project root with the EC2 venv: OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=benchmark/.deps python -u -m benchmark.run_e1_sequential --output benchmark/results --trial-timeout 180 --memory-limit-gib 6 --prediction-chunk 50000 --resume
- The frozen supervisor finished and has no live model process. Its state and summary are in project/benchmark/results/supervisor_state.json and supervisor_summary.json. The report was generated without --bootstrap and audited against all 765 supervisor keys and completion records.

### Frozen outcomes by budget

| Development rows | Successful | Failed | Unsupported | Terminal |
|---:|---:|---:|---:|---:|
| 100 | 80 | 0 | 5 | 85 |
| 300 | 80 | 0 | 5 | 85 |
| 1,000 | 84 | 1 | 0 | 85 |
| 3,000 | 82 | 3 | 0 | 85 |
| 10,000 | 82 | 3 | 0 | 85 |
| 30,000 | 74 | 11 | 0 | 85 |
| 100,000 | 67 | 18 | 0 | 85 |
| 300,000 | 65 | 20 | 0 | 85 |
| 1,000,000 | 60 | 25 | 0 | 85 |

Each budget contains 17 methods x 5 repetitions. Means in the report are conditional on successful evaluations and give actual repetition counts; a method with missing successful repetitions is not a five-run mean.

### Which methods failed

| Method | Frozen failed or unsupported cells | Main evidence |
|---|---:|---|
| ARF | 33 | Ten 100/300-row cells have fewer than five fit observations in at least one class; other cases hit timeout, memory, or supervisor termination. |
| KDE | 20 | Resource/time limits, particularly large fit or test inference. |
| RBF SVM | 20 | Resource/time limits and supervisor terminal failures. |
| Extra Trees | 13 | Supervisor terminal failures, often with incomplete cell manifest despite a terminal supervisor record. |
| Random Forest | 5 | All at 1M rows; resource/time limits. |

The report preserves 26 cells with manifest status started but supervisor status terminal_failure as a separate terminal-failure category. Their absent test metrics were not invented.

## Provenance and scientific limits

- The compact transfer intentionally omitted historical fitted pipeline.joblib files and per-test-row test_predictions.npz for old successful cells. The saved completion JSON, metrics, trial records, manifests, membership and source hashes remain. Those omitted historical artifacts were not refit or fabricated.
- The user explicitly said to stop pursuing the full backup and to omit paired bootstrap. No paired-bootstrap significance claim or historical row-level rescoring is in the final descriptive report.
- Seven auxiliary tuning-history hash discrepancies across 10K rep3 GMM, 30K rep2 CART and 30K rep3 linear SVM remain documented. Original complete JSON hashes matched, and earlier independent rescoring reproduced the affected metrics. The canonical auxiliary-history caveat is preserved.
- Timing and timeout outcomes span two hosts and depend on hardware. Recovery results cannot silently replace frozen E1 results because recovery resources differ.
- Original root-level compact CSVs may reflect the arrival snapshot. For the complete 765-cell status use the validated JSON report or the new E1_all_765_cells.csv in the package.

## Separately labeled recovery study

- The user later authorized retries. The recovery root is /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024. Frozen E1 results/source are not overwritten.
- Recovery uses the same seed, native Parquet input, role sampling, model/trial definitions and 50,000-row prediction chunks, but increases trial timeout from 180 to 600 seconds and process memory headroom from 6 to 10 GiB. It runs at most two model workers in separate output directories. Successful retry membership hashes were checked against the original fit/tune/calibration rows.
- There were 91 frozen non-success cells: 33 ARF, 20 KDE, 20 RBF SVM, 13 Extra Trees, 5 Random Forest. The 10 small-budget ARF support failures are handled separately from 81 resource/terminal failures.
- Live index: /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/recovery_index.json. It auto-refreshes. Queue state files and run logs are in the same recovery root.

### Recovery by method at this report timestamp

| Method | Frozen non-success | Recovered success | Retry failed | Active | Queued | Small-support feasibility |
|---|---:|---:|---:|---:|---:|---:|
| arf | 33 | 10 | 1 | 1 | 11 | 10 |
| kde | 20 | 5 | 5 | 0 | 10 | 0 |
| rbf_svm | 20 | 6 | 3 | 1 | 10 | 0 |
| extra_trees | 13 | 3 | 0 | 0 | 10 | 0 |
| random_forest | 5 | 0 | 0 | 0 | 5 | 0 |

### Example recovered metrics

| Cell | Balanced accuracy | Coverage | Mean set size |
|---|---:|---:|---:|
| n_1000/rep_1/arf | 0.601595 | 0.881364 | 2.151406 |
| n_100000/rep_3/extra_trees | 0.767981 | 0.903896 | 1.578264 |
| n_30000/rep_1/kde | 0.658186 | 0.887598 | 1.903154 |
| n_30000/rep_1/rbf_svm | 0.786785 | 0.886974 | 1.641394 |

These are separate recovery outcomes under changed resource limits, not revised frozen-E1 means.

### ARF support variants and saved-model finalization

- For the 10 original 100/300-row ARF cells, the original ARF requires at least five fit rows per class. A separate min_samples_leaf=1 development variant was tested at 100 rep1 and failed with non-finite FORDE parameters. It was not merged into frozen E1.
- A second variant uses the rarest class's actual fit count (2 or 4) as minimum leaf size. Its feasibility test and conditional 10-cell queue are staged to run after the resource-related ARF queue, keeping the two-worker cap.
- Several large KDE/RBF retries selected and saved a fitted pipeline before test inference timed out. A separate EC2 finalizer is staged to evaluate those saved pipelines in checkpointed test chunks without refitting. It must first exactly reproduce the saved arrays, conformal threshold and metrics of an already successful KDE cell. If that gate fails, the finalizer queue halts. It has not run yet at this report timestamp.
- The resource retry queues and finalizer remain ongoing; do not call the recovery study complete or assume all ARF cases can succeed.

### Durable queue files

| Queue state | Recorded cells | Planned cells | Recorded outcome counts |
|---|---:|---:|---|
| arf_queue_state.json | 10 | 22 | {'success': 9, 'failed': 1} |
| nonarf_queue_state.json | 21 | 57 | {'failed': 8, 'success': 13} |
| small_arf_queue_state.json | 0 | 10 | {} |
| nonarf_finalizer_state.json | 0 | variable | {} |

To inspect liveness on EC2, use tmux ls and ps -eo pid,ppid,pcpu,rss,etime,args; match real benchmark.experiments/finalizer processes. Do not infer liveness from an old heartbeat alone or start duplicate workers.

## Packages and laptop copies

- Full EC2 snapshot ZIP: /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_E1_FROZEN_FINAL_RECOVERY_SNAPSHOT_20261024.zip
- Full ZIP size: 3,667,905,634 bytes; 8,394 entries; SHA-256: bf01a507220eb10e42a891bd04ed1d675f9ea36f8371c2b4bdd2c0558bd498c8. Its ZIP CRC audit passed. Receipt: /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_E1_FROZEN_FINAL_RECOVERY_SNAPSHOT_20261024.receipt.json.
- The full snapshot includes the restored compact project, native baseline Parquet, complete frozen E1 report and artifacts that exist, generated 765-cell CSV, provenance, code/configs, graphs, and 25 recovery cells terminal at packaging time. It excludes active partial recovery directories and the intentionally omitted historical models/predictions.
- Small report/tables ZIP copied to the laptop: D:/LAMOST_Overall_EC2_Handoff_20261023/LAMOST_E1_REPORTS_TABLES_FROZEN_FINAL_RECOVERY_SNAPSHOT_20261024.zip. It is 977,255 bytes and its local SHA-256 matched EC2: ab190ddee81fdd8780a58f00dcffc231d25f53d55061e38b927ab631a6ea90db.
- The 3.5 GB full ZIP remains verified on EC2. Laptop SCP transfer was extremely slow, so the incomplete local copy was removed. The laptop currently has the small ZIP and full ZIP receipt, not the full ZIP.
- A durable watcher named e1_terminal_package_watcher is set to run a gated new package build after both recovery queues, the ARF support variant and the saved-pipeline finalizer stop. It will check queue counts and live processes, write FINAL_PACKAGE_GATE.json, and only label the new archive terminal if that gate passes. No such final-recovery archive exists yet.

## What the supervisor should decide

1. Whether to let the existing two-worker recovery queues continue unchanged, or reprioritize expensive 100K-1M cases. This affects elapsed time and must preserve separate provenance.
2. Whether the min-class ARF variant is scientifically acceptable as a separate sensitivity analysis. A failed feasibility test should leave the original 10 cells unsupported.
3. Whether the saved-pipeline finalizer can contribute no-refit recovery outcomes after its exact reproduction gate passes.
4. Where to deliver the eventual full terminal-recovery archive. The verified 3.5 GB snapshot is on EC2; only the small report ZIP is local.
5. Confirm that E2-E6 remain dormant until separately authorized. Do not reintroduce paired bootstrap unless the user changes that instruction.

## Paste-ready prompt for supervisor chat

> Please read the attached LAMOST E1 detailed handoff report dated 2026-10-24T07:50:19+00:00 UTC before giving further instructions.
> 
> Frozen Experiment 1 is terminal at 765/765: 674 successful, 81 failed, 10 unsupported. Its validated descriptive report is saved on the existing EC2. At this handoff, the separate recovery study has 24 successful retries, 9 failed retries, 2 active cells, 46 queued cells, and 10 small-budget ARF support cases awaiting a feasibility variant. Two EC2 model workers are active; the original frozen E1 source and results remain unchanged. Recovery uses 600-second trials and 10 GiB memory headroom, so its outcomes must remain labeled separately. Bootstrap was explicitly dropped by the user. E2-E6 are not authorized.
> 
> Please review the current EC2 recovery index and this report, then advise:
> 1. Should the two existing recovery queues continue unchanged, or should we prioritize specific methods/budgets?
> 2. Is the staged small-class ARF min-leaf variant scientifically acceptable as a separate sensitivity analysis, or should the 10 unsupported frozen cases stay unsupported?
> 3. After the saved-pipeline finalizer passes its exact reproduction check, may its no-refit outcomes be included in the separate recovery report?
> 4. Where should the final full archive be delivered once all recovery queues reach terminal states?
> 
> Do not start E2-E6, overwrite frozen E1 cells, claim paired-bootstrap evidence, or mark the recovery complete while cells remain queued. Do not request private keys or provision another instance. Give concrete next steps and any scientific corrections needed.

