# E4 output column dictionary

This note clarifies the hash and metric columns in the E4 block outputs. It adds no results and does not modify the existing tables.

## Hash columns

| Column | Meaning |
|---|---|
| evaluation_sha256 | SHA-256 of the actual runtime_20261025/artifacts/<task_key>/evaluation.json bytes read by the analyzer. |
| validation_sha256 | Expected evaluation-file SHA-256 stored in registry.sqlite at tasks.record -> result.validation -> files -> evaluation.json. The analyzer compared this value with evaluation_sha256. It is not the SHA-256 of a separate receipt or validation.json. |
| registry_task_row_sha256 | SHA-256 of the exact serialized SQLite tasks.record string for this task key. That record contains the embedded result.validation object, so this digest binds the validation metadata together with the rest of the task row. |

The receipt locator is runtime_20261025/registry.sqlite, table tasks, row selected by key = <task_key>, nested field record.result.validation. The expected evaluation digest is record.result.validation.files["evaluation.json"]. The actual file is runtime_20261025/artifacts/<task_key>/evaluation.json. No separate validation-receipt file hash is claimed.

E4_EVALUATION_INPUT_HASHES.csv provides these three hash columns per successful validated evaluation. E4_VALIDATED_EVALUATION_METRICS.csv carries the same bindings beside its metrics. The manifest's registry_rows_sha256_concatenation binds the sorted task-key/row-hash sequence for the selected E4 evaluation rows.

## Metric and key columns

| Columns | Meaning |
|---|---|
| task_key, rep | Registry evaluation-cell identity and paired repetition (1-3). |
| method, route, condition, treatment | Recorded classifier, direct/treatment route, E4 cohort condition, and restoration/imbalance treatment. |
| target_class, target_class_label, ratio | Zero-based target label and its name, plus the altered target-share ratio. Controls have null target and ratio metadata. |
| score_kind | Recorded conformal nonconformity convention. Numeric thresholds across score kinds are not compared. |
| balanced_accuracy, coverage, mean_set_size | Saved test metrics; balanced accuracy was recomputed from the 7x7 confusion matrix. |
| test_n, calibration_n | Test and calibration sample counts. |
| calibration_fallback_count, test_fallback_count | Recorded fallback counts for calibration and test inference. |
| target_recall, target_coverage, target_set_size | Per-class test metrics for the altered target class; paired-control outputs use the same target-class index on the unchanged reference. |

The successful-metric CSV contains validated successes only; all planned statuses and unmatched comparisons remain in the coverage and paired-block tables.

## Bound source files

The JSON companion records the verified SHA-256 and byte size for the two tables, analyzer, and pre-existing evidence manifest. The evidence manifest itself was not rewritten; this dictionary is an additive clarification.
