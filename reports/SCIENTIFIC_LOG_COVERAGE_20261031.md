# Scientific trial and execution-log coverage audit (interim)

Observed 2026-10-31T01:34:20Z UTC from one read-only SQLite transaction. All 6,270 registry task rows are validated terminal. The original 2,823 planned E3-E6 scientific-case denominator is preserved: 2,438 successful references (including aliases), 127 recorded scientific failures, 90 unavailable dependencies, 168 prospective user-stopped repetitions, and zero pending.

The [current case ledger](CURRENT_CASE_OUTCOME_LEDGER_20261031/PLANNED_CASE_OUTCOMES_2823.csv) carries sanitized reasons and artifact pointers. The [2,438-row successful-evaluation SHA crosswalk](E3_E6_SUCCESS_EVALUATION_SHA_CROSSWALK_20261031.csv) binds every successful reference to a tracked Git evaluation JSON. Binding classes: {'canonical_artifact_path': 2356, 'curated_result_snapshot_sha_match': 82}. Alternate paths are explicit; alias source keys remain in the CSV.

| Experiment | Planned cases | Successful | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 including 21 aliases | 71 | 3 | 67 | 0 |
| E5 | 960 | 730 including 88 aliases | 50 | 79 | 101 | 0 |
| E6 | 21 | 12 member-reference aliases | 3 | 6 | 0 | 0 |

E6 has zero successful primary ensemble test evaluations: three equal-mode evaluations are recorded failures and three learned-mode cases are unavailable. No ensemble performance benefit is claimed.

## Trial history and phase-cost coverage

| Experiment | Published artifact inventory | Coverage statement |
|---|---|---|
| E1 | 765-cell frozen ledger; 754 study_trials.csv and 754 trials.jsonl files | Exact key crosswalk leaves 11 cells without study-trial files; all 11 are supervisor-terminal manifests still marked started. See [the 11-key list](E1_NO_STUDY_TRIAL_FILE_CASES_20261031.csv). They are not reclassified as scientific failures. Seven documented auxiliary-history caveats remain. |
| E2 | 108/150 primary evaluations; 120/120 separate references; 1,596 class reports | Reports, integrity/reconstruction provenance, and aggregate fidelity tables are present. The audit records 31 reconstruction accuracy differences, 210 low-precision flags, and four complete correlation strata. Raw generated training data are excluded. |
| E3 | 67 fit-result JSONs; 64 evaluation JSONs; 62 checkpoint trial-history files across 60 fit keys | Selection, fit, validation, evaluation, failure reason, and cost projections are included where recorded. Nine successful fit cases reused selected parameters rather than running fresh optimizer trials. |
| E4 | 1590 fit-result JSONs; 1582 evaluation JSONs; 1611 checkpoint trial-history files across 1569 fit keys | Per-task selection, fit, validation, evaluation and history projections are retained where emitted. User-stopped repetitions remain separately identified in the case ledger. |
| E5 | 678 fit-result JSONs; 698 evaluation JSONs; zero checkpoint trial-history files | Fits use fixed clean-selected parameters and zero retuning trials; absence of optimizer histories is consistent with this protocol. |
| E6 | 12 member-reference evaluation JSONs; six primary phase-terminal records; three learned candidate ledgers | Twelve successes are aliases. Tuning artifacts do not provide primary test metrics. |

Saved cost-table inputs: reports/costs.csv, reports/cost_summary.csv, reports/e5_completed_generator_routes_20261027/dependency_cost_ledger.csv, reports/e5_completed_generator_routes_20261027/evaluation_phase_costs.csv, reports/E6_V2_INTERIM_20261027T204752Z/E6_V2_PHASE_COSTS.csv. Fit-result and selection JSONs preserve phase timings/trial summaries where recorded. Raw stdout/stderr, private phase/process receipts, process inventories, and unreviewed sampler databases are excluded.

## Qualification and limits

The current source/test closure is pinned to bundle SHA bac77c40050163c8b449971708d00eb21d03aaa96c58ca17dfe6c012124ecf7c, fingerprint 1e68ddc3d21dae8decadcc602dcfcd84e42f34bdf822df47c50bdb962c2a4f49, with 863/863 engineering/fixture tests passed. This does not validate scientific completion. E1 remains 674 successful, 81 recorded failures (55 resource plus 26 supervisor-terminal manifests still started), and 10 unsupported; stopped recovery is separate at 24 successful, 10 failed, 2 user-stopped and 55 not attempted. Historical fitted models are omitted; frozen E1 prediction release covers 80/674 successful cases. No E1/E2 bootstrap or refit is claimed.

Full artifact review and global calibration/quantile replay remain pending. This is an interim snapshot, not a final project-completion claim.
