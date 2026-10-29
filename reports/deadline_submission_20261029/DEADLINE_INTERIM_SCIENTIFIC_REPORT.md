# LAMOST six-experiment research: consolidated interim submission

**INTERIM - not final project completion.** Read-only registry snapshot: 2026-10-29T10:13:56.191835+00:00 UTC on the existing EC2. This submission combines frozen E1/E2 reports with current E3-E6 case outcomes and metrics from saved, validated evaluation JSONs. No model was loaded, fit, retuned, or used for inference; no bootstrap was run. Existing test outcomes are already observed, so later cohorts are not described as an untouched prospective test.

## Current status

| Experiment | Planned | Successful/evaluated | Scientific failures | Unsupported | Unavailable | User-stopped | Not attempted | Operationally interrupted | Operationally invalid | Packaging pending | Waiting/active |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| E2 primary | 150 | 108 | 0 | 0 | 42 | 0 | 0 | 0 | 0 | 0 | 0 |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| E4 | 1,773 | 1621 | 71 | 0 | 3 | 67 | 0 | 0 | 0 | 0 | 11 |
| E5 | 960 | 700 | 50 | 0 | 78 | 101 | 0 | 0 | 0 | 0 | 31 |
| E6 primary ensembles | 6 | 0 | 3 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| E6 member references | 15 | 12 aliases | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |

**Stopped E1 recovery supplement (separate from the frozen ledger):**

| Planned retry rows | Successful retries | Retry failures | User-stopped partial | Not attempted after stop | Pending |
|---|---|---|---|---|---|
| 91 | 24 | 10 | 2 | 55 | 0 |


E4/E5 have 42 planned cases waiting in the registry snapshot. The [complete E3-E6 case ledger](planned_case_ledger.csv), [condition repetition coverage](condition_repetition_coverage.csv), [per-repetition metrics](per_repetition_metrics.csv), [per-class metrics](per_class_metrics.csv), [confusion matrices](confusion_matrices_long.csv), [current paired differences](matched_paired_differences_current.csv), [E4 control comparisons](E4_CONTROL_TREATMENT_PAIRED_CURRENT.csv), [E5 corruption comparisons](E5_clean_corrupted_paired_metrics_CURRENT.csv), and [evaluation input hashes](evaluation_input_hashes.csv) accompany this report. The [current status chart](current_status_coverage.svg) uses this registry snapshot. Other experiment figures remain dated to their validated analysis cutoff.

## Prospective repetition-scope amendment

A score-independent amendment was applied and verified at 2026-10-29T08:39:50.880664+00:00. It selects one pending evaluation key per unique method/condition case from the original three-repetition plan, along with its reviewed dependency closure. All prior terminal outcomes are preserved. The original 2,823 scientific-case plan and task-manifest SHA remain unchanged. It marks 168 pending scientific repetition rows user-stopped, not failed or unavailable; 167 closure tasks are in the full amendment set and 90 tasks were pending in the selected closure at application time. Selected cases may already have completed by this snapshot. See the sanitized [amendment](scope_amendment_public.json) and [application summary](scope_application_public.json). Actual repetition counts vary by condition; see [condition repetition coverage](condition_repetition_coverage.csv). Paired summaries use matched available repetitions; sample SD is undefined and blank at n=1. The original full three-repetition grid is not complete.

## Shared data and protocol

The baseline has approximately 2,330,835 source representatives, seven labels (A, F, G, K, M, GALAXY, QSO), six predictors (Pan-STARRS g/r/i/z/y and Gaia G), and a fixed 500,000-source test cohort. IDs, labels, spectra, and audit metadata are not predictors. Fit, tuning, calibration, and test roles remain separate. E1/E2 test outcomes were observed before later experiment plans were frozen. Nominal conformal target is 90%; prediction-set size is interpreted together with overall and classwise coverage. No bootstrap confidence intervals or significance claims are included.

## E1 - frozen benchmark and stopped recovery

<!-- GENERATED_TABLES_START -->
### Method-by-budget outcomes

This all-method summary weights each successful repetition equally within budget. Failure and unsupported counts are separate; the linked 153-row source table retains per-method means, sample SDs, and actual successful repetitions.

| Budget rows | Successful reps | Failed | Unsupported | Mean BA | Mean coverage | Mean set size |
|---|---|---|---|---|---|---|
| 100 | 80/85 | 0 | 5 | 0.420335 | 0.924616 | 4.295946 |
| 300 | 80/85 | 0 | 5 | 0.481049 | 0.917200 | 3.586178 |
| 1,000 | 84/85 | 1 | 0 | 0.566273 | 0.901416 | 2.843982 |
| 3,000 | 82/85 | 3 | 0 | 0.604196 | 0.894520 | 2.652939 |
| 10,000 | 82/85 | 3 | 0 | 0.624684 | 0.902862 | 2.669991 |
| 30,000 | 74/85 | 11 | 0 | 0.631495 | 0.903298 | 2.552719 |
| 100,000 | 67/85 | 18 | 0 | 0.642155 | 0.905848 | 2.552764 |
| 300,000 | 65/85 | 20 | 0 | 0.642321 | 0.906403 | 2.576699 |
| 1,000,000 | 60/85 | 25 | 0 | 0.640226 | 0.906089 | 2.553513 |



Frozen E1 is unchanged: 765 terminal, 674 successful, 81 failed (55 resource failures and 26 supervisor-terminal cells whose manifests remained started), and 10 unsupported. The 100k budget was terminal with 67 successes and 18 failures. E1's per-cell table, method-by-budget summaries, learning curves, coverage, set size, and actual successful repetition counts are in the [frozen report](../../experiments/E1/frozen/E1_WRAPUP.md) and [765-cell ledger](../../experiments/E1/frozen/E1_frozen_cells_765.csv). Frozen execution used 180 seconds per trial and a 6-GiB worker limit; timing depends on hardware and shared load.

The recovery supplement is separate and stopped: 24 successes, 10 retry failures, 2 user-stopped partial cells, 55 not attempted. Recovery never replaces frozen E1. Historical fitted classifiers and per-test-row predictions were omitted in the compact migration. Seven auxiliary tuning-history discrepancies remain documented.

## E2 - generator fidelity and direct classification

The primary grid is 108/150, with 42 unavailable because the frozen E1 selected fit did not exist. A separate classical reference set is 120/120. Original/reconstructed provenance remains explicit: 31 reconstructed balanced-accuracy comparisons failed the documented equality gate, and 210 of 1,596 class reports are low precision. Only four of 30 budget/repetition strata have all five primary generator families; their descriptive Spearman values are 0.700, 0.100, 0.300, and 0.700. These four strata do not support a general fidelity-classification relationship. See the [E2 report](../../experiments/E2/E2_CURRENT_REPORT.md), [combined 270 rows](../../experiments/E2/E2_all_generators_270.csv), [1,596 class reports](../../experiments/E2/E2_all_class_reports_1596.csv), and [integrity audit](../../experiments/E2/E2_INTEGRITY_AUDIT.json).

## E3 - direct Bayes, synthetic-only, real-only

### Route and learner metrics

Means are over successful repetitions only; the paired-n column reports synthetic-versus-shared-real availability for that generator/learner. Direct and real-only rows have no such synthetic-real comparison. Individual repetition outcomes, failure states, class metrics, and paired deltas remain in the linked route ledger.

| Route | Generator | Learner | Successful / planned | Mean BA | Mean coverage | Mean set size | Synthetic-real paired n |
|---|---|---|---|---|---|---|---|
| direct | gmm | direct_bayes | 3/3 | 0.805554 | 0.899597 | 1.486998 | NA |
| direct | copula | direct_bayes | 3/3 | 0.579193 | 0.897579 | 2.371102 | NA |
| direct | arf | direct_bayes | 3/3 | 0.646093 | 0.896926 | 2.278413 | NA |
| direct | kde | direct_bayes | 0/3 | NA | NA | NA | NA |
| direct | chow_liu | direct_bayes | 3/3 | 0.611824 | 0.898709 | 2.538669 | NA |
| synthetic | gmm | logistic | 3/3 | 0.643587 | 0.899696 | 1.855751 | 3 |
| synthetic | gmm | random_forest | 2/3 | 0.772208 | 0.897302 | 1.530816 | 2 |
| synthetic | gmm | hist_gb | 3/3 | 0.770601 | 0.898261 | 1.526658 | 3 |
| synthetic | copula | logistic | 3/3 | 0.565320 | 0.898741 | 2.262671 | 3 |
| synthetic | copula | random_forest | 3/3 | 0.588790 | 0.898079 | 2.313463 | 3 |
| synthetic | copula | hist_gb | 3/3 | 0.590860 | 0.897288 | 2.304406 | 3 |
| synthetic | arf | logistic | 3/3 | 0.541470 | 0.899551 | 2.486415 | 3 |
| synthetic | arf | random_forest | 3/3 | 0.649737 | 0.896602 | 2.148537 | 3 |
| synthetic | arf | hist_gb | 3/3 | 0.642805 | 0.896578 | 2.170914 | 3 |
| synthetic | kde | logistic | 3/3 | 0.605638 | 0.899114 | 2.109751 | 3 |
| synthetic | kde | random_forest | 2/3 | 0.679103 | 0.895558 | 1.866283 | 2 |
| synthetic | kde | hist_gb | 3/3 | 0.683502 | 0.894734 | 1.867981 | 3 |
| synthetic | chow_liu | logistic | 3/3 | 0.486735 | 0.898448 | 2.516338 | 3 |
| synthetic | chow_liu | random_forest | 3/3 | 0.623972 | 0.900541 | 2.261587 | 3 |
| synthetic | chow_liu | hist_gb | 3/3 | 0.631414 | 0.897743 | 2.187619 | 3 |
| real | shared | logistic | 3/3 | 0.651228 | 0.899251 | 1.770429 | NA |
| real | shared | random_forest | 3/3 | 0.761516 | 0.900631 | 1.564507 | NA |
| real | shared | hist_gb | 3/3 | 0.755706 | 0.897815 | 1.561025 | NA |



E3 is terminal at 64/69 successful, 3 scientific failures, 2 unavailable. All 15 generator datasets were produced. Nine generator fits reused matching E2 reconstructed selected pipelines; six ARF/KDE fits were new E3 dependencies. All three direct-KDE test phases hit the fixed 600-second limit. Two GMM/KDE rep-2 synthetic random-forest cases are unavailable because their downstream fit tasks exceeded the 10-GiB process-tree policy. These are feasibility outcomes and carry no fabricated accuracy. See the [reviewed E3 report](../E3_FINAL_DESCRIPTIVE_REPORT.md) for route-specific denominators, repetitions, paired comparisons, conformal metrics, and phase cost scope.

## E4 - imbalance and restoration

### All current matched-condition summaries

The CSV covers every planned E4 comparison stratum (direct altered versus unchanged; each treatment versus unchanged; each treatment versus untreated altered), including strata with no matched repetitions. No metric is averaged across different targets, learners, or severities here. Each CSV row includes actual paired n, mean difference, and sample SD for BA, overall coverage, set size, target recall, and target coverage.

| Comparison | Planned strata | n=3 | n=2 | n=1 | n=0 | Total BA paired reps |
|---|---|---|---|---|---|---|
| altered_direct_minus_unchanged_control | 238 | 194 | 2 | 3 | 39 | 589 |
| treatment_minus_unchanged_control | 336 | 297 | 39 | 0 | 0 | 969 |
| treatment_minus_untreated_altered | 336 | 297 | 39 | 0 | 0 | 969 |



E4 currently has 1621 successes, 71 failures, 3 unavailable, and 11 waiting. The reviewed direct-KNN block contains all 45 cells (3 controls plus 42 altered); every altered condition is paired to the matching repetition's unchanged control. Across the 14 target-by-severity means, target-class recall fell in each condition. The 0.1 retained-share conditions include large classwise recall losses; some returned full seven-label sets with coverage 1, which is not an efficiency benefit.

The reviewed direct-kernel block shows availability and evaluation feasibility separately: all 45 RBF-SVM selected models existed, but 18 evaluations succeeded and 27 failed under the fixed policy. All 45 KDE selected models existed; 42 altered test phases timed out and 3 unchanged-control aliases were unavailable because E3 direct KDE timed out. See the [direct-KNN block](../e4_direct_knn_block_20261027/E4_DIRECT_KNN_BLOCK_REPORT.md) and [direct-kernel block](../e4_direct_kernel_block_20261027/E4_DIRECT_KERNEL_BLOCK_REPORT.md). These are condition-specific findings, not a universal restoration effect.

## E5 - fitting-data corruption

### All current matched corruption summaries

Each mechanism row below summarizes availability across its full planned method/route/generator-by-rate grid; no scores are pooled across methods or mechanisms. The linked table reports each condition BA, overall coverage, and set-size change with actual matched n and sample SD; the separate per-class table reports recall, coverage, and set-size changes for all seven labels.

| Mechanism | Planned strata | n=3 | n=2 | n=1 | n=0 | Total BA paired reps |
|---|---|---|---|---|---|---|
| feature_noise | 96 | 66 | 3 | 3 | 24 | 207 |
| label_noise | 96 | 72 | 0 | 0 | 24 | 216 |
| missingness | 96 | 63 | 0 | 0 | 33 | 189 |



E5 currently has 700 successes, 50 failures, 78 unavailable, and 31 waiting. The reviewed direct-RF and direct-KNN blocks each include all 30 cells (3 clean controls and 27 corrupted) and all nine mechanism/rate strata with three matched repetitions. At 20% label noise, mean balanced-accuracy change was -0.017309 for RF and -0.023067 for KNN. At 20% feature noise it was -0.010556 and -0.009613; at 20% missingness -0.005531 and -0.006139. These compare only two direct routes under the specified masks. No universal ranking follows; coverage, set size, per-class effects, failures, and unavailable cases remain included in the component tables. See the [RF report](../e5_direct_rf_block_20261027/E5_DIRECT_RF_BLOCK_REPORT.md) and [KNN report](../e5_direct_knn_block_20261027/E5_DIRECT_KNN_BLOCK_REPORT.md).

## E6 - posterior ensembles

Twelve of 15 member-reference rows are successful aliases to existing E3 evaluations; three KDE references are unavailable following E3 direct-KDE timeouts. The six primary ensembles have no successful test evaluation: all three equal-weight test phases timed out, and learned-weight tasks are unavailable after the shared test phase terminated. This report therefore makes no ensemble performance or weight-benefit claim and does not label tuning-only artifacts as tested ensembles. See the [E6 interim record](../E6_CURRENT_DESCRIPTIVE_INTERIM_20261027T204752Z.md).

<!-- GENERATED_TABLES_END -->

## Tables, figures, and provenance files

- [All 2,823 E3-E6 planned cases with state and available metrics](planned_case_ledger.csv)
- [Per-repetition metrics](per_repetition_metrics.csv); [per-class metrics](per_class_metrics.csv); [confusion matrices](confusion_matrices_long.csv)
- [E3-E6 condition summaries](condition_metric_summary.csv); [current status chart](current_status_coverage.svg)
- [E4 all matched control/treatment repetition rows](E4_CONTROL_TREATMENT_PAIRED_CURRENT.csv) and [condition summary](E4_CONTROL_TREATMENT_PAIRED_SUMMARY_CURRENT.csv)
- [E5 clean-corrupted matched rows](E5_clean_corrupted_paired_metrics_CURRENT.csv), [condition summary](E5_clean_corrupted_paired_metrics_SUMMARY_CURRENT.csv), [per-class paired rows](E5_per_class_paired_differences_CURRENT.csv), and [per-class summary](E5_per_class_paired_summary_CURRENT.csv)
- [E1 method-budget summary](../../experiments/E1/frozen/E1_method_budget_summary_153.csv); [E3 route repetitions](../E3_FINAL_ROUTE_REPETITIONS.csv)
- [Evaluation JSON input hashes](evaluation_input_hashes.csv); [submission receipt](submission_receipt.json)


## Timing, provenance, and remaining validation

E1 used 180-second/6-GiB settings. E3-E6 settings are 600-second/10-GiB per worker; admission profiles and hardware differ, and timing is not directly comparable across all experiments. Phase-cost records are available in the dated [cost table](../costs.csv) and [cost summary](../cost_summary.csv); they are not reinterpreted as timings for the current registry snapshot. Final native calibration replay, full artifact validation, the cross-experiment final report, and final full/small archive CRC/SHA verification remain pending. This delivery is an interim scientific submission; it does not stop authorized work or mark pending cases terminal.


### Snapshot history
This 2026-10-29T10:13:56.191835+00:00 UTC interim refresh supersedes the earlier 03:53Z interim snapshot. The earlier snapshot remains available in Git history at commit c6112170e168fda4a81fb1f9e72d942e2152b24e.