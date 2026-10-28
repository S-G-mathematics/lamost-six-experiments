# Common science engine API (runtime_20261025)

science.execute(task, runtime) executes one planned task in a distinct attempt directory and returns a JSON-safe record. It never schedules another task. Task keys accept slash-delimited alphanumeric, dot, underscore, and hyphen components; artifact output is rooted at runtime/artifacts/<key>.

## Inputs

- kind: fit, eval, or generate.
- Fit tasks require method, rep, seed; optional train_path NPZ has X,y and optional ids,sample_weight. Otherwise cache/roles/rep_<r>.npz supplies fitting data. Fixed selection reads selection_source/selection.json (or selection_source may name that JSON file directly) (selected_params or params). A reuse_pipeline path loads and copies an already compatible pipeline without fitting.
- Role NPZ contains X_fit,y_fit,fit_ids,X_tune,y_tune,tuning_ids,X_cal,y_cal,calibration_ids. Test data live in cache/test.npz with X,y,ids.
- Eval tasks require fit_key,rep. Generate tasks require fit_key and either n_rows with optional seven-count proportions, or target_class,added_count (or a cohort metadata key).
- Controller may resolve train_key and selection_key into these paths before dispatch. source_metadata is retained for reused pipelines.

## Outputs and states

Each invocation writes attempt evidence in artifacts/<key>/attempts/<timestamp_uuid>/ and a current result JSON. A fit writes pipeline.joblib, selection.json, and fit_result.json. Evaluation writes test_outcomes.npz and eval_result.json. Generation writes native-unit data.npz (X float64, y int8). set_mask is a seven-class little-endian bit field stored as one uint8 per test row; decode its lowest seven bits in class order 0..6.

Return statuses include successful, scientific_failure, unsupported, unavailable_dependency, and operationally_invalid. Adapter/schema/data-shape defects are operationally_invalid. Estimator fit failures and hard scientific trial/final phase timeout or RSS-cap outcomes are scientific_failure; a failed trial consumes its planned slot. Queued work remains a controller state, not an engine failure.

Each model phase runs in a fresh Python subprocess group with one nested thread, 600-second deadline, 10 GiB aggregate RSS limit and 30-second TERM grace followed by KILL of the launched process group. Phase state/result JSON includes actual PID/PGID, timestamps, peak RSS and outcome. Fit trials use Optuna TPE seeded from optimizer_seed, three startup trials, fixed method trial budgets, and do not replace failures. A task-hash-scoped SQLite Optuna study and trial ledger support validated continuation; the engine code hash participates in task identity. Final model preprocessing is fit-only median imputation followed by standard scaling. Eval calibrates at nominal 90% using frozen project conformal helpers and predicts in 50,000-row chunks. No bootstrap is implemented.

The runner imports frozen model factories/evaluation from the existing project/benchmark tree read-only. New outputs belong to this runtime.
