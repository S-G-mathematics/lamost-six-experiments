# E4 incremental validated evaluations

Registry snapshot: 2026-10-28T20:41:01.275758+00:00 UTC. This supplement contains six successful, validated E4 rep-3 random-forest treatment evaluations observed from 2026-10-28T18:48:28.948995+00:00 through 2026-10-28T20:02:43.293652+00:00. Each row is tied to its persisted scientific evaluation.json by SHA-256.

Files:
- E4_INCREMENTAL_VALIDATED_20261028T200243Z_metrics.csv: six cell-level metrics, confusion matrices, sample sizes, fallback counts and provenance.
- E4_INCREMENTAL_VALIDATED_20261028T200243Z_per_class.csv: 42 class-level result rows from the saved evaluations.
- E4_INCREMENTAL_VALIDATED_20261028T200243Z_evaluation_index.csv: task keys, registry observations, artifact paths and hashes.
- incremental_evaluations/e4/rep_3/eval/treatment/random_forest/: six unmodified evaluation.json records.

Each saved evaluation was checked against the read-only registry for successful validated status, task identity, probability score, 10,000 calibration rows and 500,000 test rows. Each seven-class confusion matrix sums to 500,000; saved class supports and recalls, and balanced accuracy, reconcile with it.

These six cases are included in the current registry counts. The older planned-case ledger and aggregate metrics/figures remain a dated analysis snapshot and do not contain these six rows. Use these supplemental per-cell and per-class tables for the six later observations. No models were loaded and no fitting or prediction was run.
