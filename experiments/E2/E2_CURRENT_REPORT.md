# Experiment 2 current report

Updated: 2026-10-24T19:22:02.996089+00:00 (UTC).

## Results

Primary grid: **108/150** paired fidelity and direct classification cells (19 original saved selected fits; 89 reconstructed selected fits). The remaining 42 primary cells failed frozen E1 and have no valid selected classification outcome.

Separate classical generative reference set: **120/120** paired cells (24 original saved fits; 96 reconstructed fits). It is not part of the five-family primary rank comparison.

Saved per-class Quality Reports: **1596**, seven per evaluated fit. Class report statuses: {'valid_low_precision': 210, 'valid': 1386}.

Each class uses the six native predictors and a fixed calibration-role reference, with matched generated/real diagnostic sizes capped at 2,000. Seven SDMetrics 0.32.0 scores are averaged equally.

## Complete primary five-family strata

**4/30** budget/repetition strata have all five primary generators:

| Budget | Repetition | Spearman rho |
|---:|---:|---:|
| 3,000 | 3 | 0.700 |
| 3,000 | 5 | 0.100 |
| 10,000 | 1 | 0.300 |
| 10,000 | 2 | 0.700 |

These correlations are descriptive within each stratum. The other 26 five-family comparisons are unavailable, mostly because ARF or KDE had no successful E1 selected outcome at larger budgets. No cross-budget correlation is claimed.

## Provenance

At user request, missing saved models from successful E1 cells were reconstructed on EC2 using original fit-role IDs, selected parameters, preprocessing and seed formula. No retuning occurred. Each reconstructed fit uses its own fixed-test balanced accuracy in E2; E1 results were not overwritten. Original saved fits and reconstructed fits remain marked separately.

Reconstruction equality gate versus frozen E1 balanced accuracy, absolute tolerance 1e-10: {'reproduced_original_test_balanced_accuracy': 154, 'classification_not_reproduced': 31}.

The frozen E1 ledger and recovery cutoff are unchanged. No bootstrap, test-based model selection, TSTR, or Experiment 3-6 runs were performed.

## Deliverables

See E2_all_generators_270.csv, E2_all_class_reports_1596.csv, E2_all_method_budget_summary.csv, E2_combined_spearman_30.csv, and E2_combined_fidelity_vs_accuracy.html. Full cell-level samples, Quality Report details, and pipelines remain in the EC2 E2 directory.


## Integrity and availability audit

The EC2 audit checked all 228 evaluated cells: pipeline hashes, class-score aggregation, saved diagnostic hashes and shapes, fixed reference IDs across models and provenance sets, exclusion of test IDs from fidelity references, and paired classification scores. **No integrity errors** were found.

Of 1,596 class reports, 210 are flagged low precision (<20 diagnostic rows). These occur at 3k and 10k, including all four complete five-family strata. They remain in the protocol's equal seven-class average and limit precision of those descriptive correlations.

Among 185 reconstructed fits, 154 reproduced the recorded E1 balanced accuracy to 1e-10 and 31 differed; the maximum absolute difference was 0.00003174. Every E2 pairing uses the classification score measured from its own reconstructed fit.

The 42 unavailable primary cells comprise 40 frozen E1 resource failures and 2 supervisor-terminal failures. They are all ARF or KDE; 21 recorded a 180-second trial timeout, 19 recorded all trials failed, and 2 have no ordinary cell error because the supervisor terminalized the cell. See E2_missing_primary_42.csv.

E2_within_stratum_descriptive_30.csv provides available-only rank correlations for the 26 incomplete strata, separately labeled exploratory; it never treats a three- or four-family correlation as the protocol five-family result. No budget pooling or bootstrap was added.
