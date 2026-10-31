# Results guide

## Scope and reading rules

The aggregate snapshot is timestamped 2026-10-31T01:05:34.402480Z. It records 2,823 planned E3-E6 scientific cases, 2,438 successful evaluation references, 127 scientific failures, 90 unavailable dependencies and 168 user-stopped repetitions. The successful-reference count includes 12 reused E6 member aliases, not 12 ensemble evaluations. All 6,270 task rows are terminal under the approved prospective scope amendment.

E4 and E5 originally planned three repetitions per condition. Previously completed repetitions remain intact. The amendment selected one further evaluation for 45 cases and stopped 67 E4 plus 101 E5 remaining repetitions. Stopped cases are not failures; the original repeated grid is not complete.

All means and paired deltas are descriptive. Pairing preserves exact condition and repetition. No bootstrap, confidence interval, significance test or universal method ranking is reported. Failure/unavailable rows have blank metrics. At n=1, sample SD is undefined and blank.

The fixed 500,000-row test cohort and prior E1/E2 outcomes were already observed before E3-E6. Later comparisons are not prospective untouched-test validation. Global calibration-quantile replay and the final artifact audit remain pending.

## Shared data and metrics

The classification target has seven labels (A, F, G, K, M, GALAXY, QSO) and six photometric predictors (Pan-STARRS g, r, i, z, y and Gaia G). The later E3-E6 design reuses repetition-matched roles: 80,000 fitting rows, 10,000 tuning rows, 10,000 calibration rows and a fixed 500,000-row test role per repetition. The fixed role membership and class ordering are recorded in the manifests and result provenance. E1 and E2 retain their own budget and diagnostic designs.

Balanced accuracy is the unweighted mean of class recalls. Coverage is the fraction of test observations whose conformal prediction set contains the observed class; set size is the average number of included classes. These metrics answer different questions: greater coverage can coincide with larger sets, and a set-size change is not automatically a calibration benefit. Class-level values and fallback diagnostics remain available in the [per-class table](../reports/per_class_metrics.csv) and [support/fallback tables](../reports/evaluation_support_fallbacks_per_class.csv).

## E1: frozen benchmark and recovery

Frozen E1 has 765 cells: 674 successful, 81 recorded failures and 10 unsupported outcomes. The 81 comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained started; unsupported is separate. E1 covers 17 methods, nine budgets and five repetitions per method-budget cell. The [153-row method-budget summary](../experiments/E1/frozen/E1_method_budget_summary_153.csv) gives successful n and mean/sample SD for balanced accuracy, marginal coverage and mean set size. See the [budget figure](../reports/frozen_e1_e2_figures/E1_frozen_all_budget_summary.png) and [765-cell ledger](../experiments/E1/frozen/E1_frozen_cells_765.csv).

Recovery is separate: 24 successes, 10 failures, 2 user-stopped partial cells and 55 not attempted. See its [cutoff](../experiments/E1/recovery_stopped/RECOVERY_CUTOFF.json) and [91-row table](../experiments/E1/frozen/E1_recovery_cutoff_91.csv). It stopped early at the user's request. Historical model and prediction availability is incomplete; [data availability](DATA_AVAILABILITY.md) gives exact array coverage.

## E2: fidelity and reconstruction

The primary five-generator grid has 108/150 evaluated and 42 unavailable cells. The separate classical-reference set has 120/120 and is not part of the primary comparison. Only 4/30 budget-repetition strata include all five primary generators: budget 3,000/repetition 3 (rho=0.7), 3,000/repetition 5 (0.1), 10,000/repetition 1 (0.3), and 10,000/repetition 2 (0.7). The other strata are incomplete; no cross-budget correlation is claimed.

Across 228 evaluated cells, E2 has 1,596 seven-class quality reports, including 210 low-precision reports (<20 diagnostic rows), and no integrity errors. Reconstruction reproduced frozen balanced accuracy exactly in 154 comparisons; 31 differ, with maximum absolute difference 3.1739351391335546e-05. Original and reconstructed fits remain separately labeled. See the [E2 report](../experiments/E2/E2_CURRENT_REPORT.md), [reconstruction amendment](../experiments/E2/E2_RECONSTRUCTION_AMENDMENT.md), [stratum table](../experiments/E2/E2_combined_spearman_30.csv) and [class reports](../experiments/E2/E2_all_class_reports_1596.csv).

## E3: direct, synthetic-only and real-only routes

E3 has 69 terminal cases: 64 successes, 3 scientific failures and 2 unavailable dependencies. Direct Bayes succeeded in 3/3 repetitions for GMM, copula, ARF and Chow-Liu; KDE direct timed out in all three. Successful direct Bayes mean balanced accuracy / coverage / set size: GMM 0.80555 / 0.89960 / 1.4870 (n=3); copula 0.57919 / 0.89758 / 2.3711 (n=3); ARF 0.64609 / 0.89693 / 2.2784 (n=3); Chow-Liu 0.61182 / 0.89871 / 2.5387 (n=3). KDE has no score.

Synthetic-only versus real-only learners are paired by repetition, generator and learner. For copula/random-forest, synthetic-minus-real balanced accuracy is -0.17273 (sample SD 0.01258; n=3); full BA/coverage/set-size deltas are in the [dedicated summary](../reports/descriptive_summaries_20261031/E3_dedicated_pair_summaries.csv). Results vary by generator and learner.

The [dedicated 135-row E3 comparison ledger](../reports/E3_CURRENT_MATCHED_PAIRS_20261030.csv) has 114 paired comparisons. It includes a direct Bayes-minus-real comparison absent from the generic aggregate when the synthetic counterpart is unavailable. The generic matched file has 113 E3 rows because of a legacy omission: the rep-2 GMM/random-forest direct-minus-real pair (BA delta +0.0443761964) was absent when the synthetic counterpart was unavailable. The dedicated ledger correctly includes this available direct-real pair. Use the dedicated 114-pair ledger for complete E3 pair accounting. See the [reviewed E3 report](../reports/E3_FINAL_DESCRIPTIVE_REPORT.md).

## E4: target-class imbalance and restoration

E4 retains 1,773 cases: 1,632 successful references (21 aliases), 71 failures, 3 unavailable and 67 user-stopped. The design varies target class, severity, learner, treatment and repetition. See [class histograms](../reports/E4_class_histograms.csv), the [case ledger](../reports/CURRENT_CASE_OUTCOME_LEDGER_20261031/PLANNED_CASE_OUTCOMES_2823.csv), and [figures and tables](../reports/AGGREGATE_SNAPSHOT_20261031T010534Z/README.md).

The 2,730-row treatment/control ledger keeps direct, generated, unchanged-control and untreated-altered contrasts separate. Direct altered-versus-unchanged has 600 available pairs among 714 contrast rows; 714 are contrast rows, not unique evaluation cases. Generated-treatment availability is itemized in [pair availability](../reports/descriptive_summaries_20261031/E4_pair_availability.csv). The [effect table](../reports/descriptive_summaries_20261031/E4_treatment_control_pair_summaries.csv) preserves method, target and severity. One exact stratum, direct ARF targeting class A (index 0) at ratio 0.5, has altered-minus-unchanged BA -0.00600 (sample SD 0.01681; n=3). This does not summarize other strata.

## E5: fitting-data corruption

E5 retains 960 cases: 730 successful references (88 aliases), 50 failures, 79 unavailable and 101 user-stopped. It varies feature noise, label noise and missingness at 5%, 10% and 20%. The [realization table](../reports/E5_corruption_realization_summary.csv) records affected rows and hashes. Label-noise source-class rates use original fitting-cohort counts as denominators; see [source-class rates](../reports/E5_label_noise_source_class_rates.csv) and [transition counts](../reports/label_transition_counts.csv).

The clean/corrupted ledger has 864 planned method/route/generator/severity/repetition rows. Available contrast rows by mechanism and rate (96 planned rows per rate, not 96 unique evaluations): feature noise 69/96, 72/96, 76/96; label noise 76/96, 76/96, 75/96; missingness 66/96 at each rate. The [derived paired summary](../reports/descriptive_summaries_20261031/E5_clean_corrupted_pair_summaries.csv) retains learner, route, generator, mechanism and rate. Example: direct CART under 5% feature noise has corrupted-minus-clean BA -0.00749 (sample SD 0.00067; n=3), one exact stratum only.

## E6: no primary ensemble test result

All 21 rows are terminal. The 15 member-reference rows include 12 successful aliases and 3 unavailable aliases to E3 direct evaluations. The six primary cases have zero successful test evaluations: 3 equal-weight test-prediction failures and 3 learned-weight unavailable outcomes through the shared posterior dependency. No primary ensemble BA, coverage, set size or benefit estimate exists.

Three learned weight vectors were frozen before calibration/test. Candidate counts were 1,606, 1,558 and 1,606. Across n=3 vectors, mean weights (sample SD) are GMM 0.7743 (0.0449), copula 0.0416 (0.0167), ARF 0.0097 (0.0030), KDE 0.1074 (0.0561), Chow-Liu 0.0670 (0.0890). This is tuning-only variation, not test evidence. See [vectors](../reports/descriptive_summaries_20261031/E6_learned_weights_tuning_only.csv), [summary](../reports/descriptive_summaries_20261031/E6_weight_stability_tuning_only.csv) and [candidate ledger](../reports/E6_candidate_ledger.csv).

E6-v2 amended its execution rule after the first E3 KDE timeout. Six zero-attempt v1 dependency-gate outcomes remain superseded history; v2 was not the original frozen executable semantics.

## Costs and operating limits

Recorded fit and evaluation phase costs are in the [cost ledger](../reports/costs.csv) and [cost summary](../reports/cost_summary.csv); trial-level selection outcomes and failure reasons are in the [selection ledger](../reports/model_selection_ledger.csv) and [resource-failure ledger](../reports/resource_failure_ledger.csv). The E3-E6 scientific worker policy used a 10 GiB process-tree memory cap and 600-second scientific phase limit. Recorded durations are phase observations under shared EC2 load, not isolated wall-clock benchmarks; queue, archive and recovery overhead must not be treated as model-compute time. See the [execution resource/delivery note](../reports/FINAL_EXECUTION_RESOURCE_DELIVERY_NOTES_20261031.md) for the one-off final dispatch/storage amendment and archive status.

## Rebuild descriptive summaries

Run python3 analysis/descriptive_summary.py from repository root. It reads committed per-repetition, per-class, paired and E6 weight/candidate CSVs only. It writes condition-preserving CSVs and input/output byte/SHA manifest under reports/descriptive_summaries_20261031/. It reads no SQLite, model, NPZ, prediction or raw dataset and performs no inference, resampling or significance tests. Source tables/figures are linked from the [aggregate snapshot index](../reports/AGGREGATE_SNAPSHOT_20261031T010534Z/README.md).
