# E4 completed paired blocks - descriptive status

Observed UTC: 2026-10-26T22:22:46.016616+00:00. This is a bounded E4 snapshot from the SQLite task registry and validated saved evaluation JSONs; E4 was still running during analysis.

The 1,773 planned evaluation rows currently include 1278 successful, 42 scientific failures, 0 unsupported, 3 unavailable dependencies, and 450 waiting for dependencies.

This report includes only three-repetition matched contrasts in its complete-block claims. The CSV summary retains all 910 planned comparison strata, including partial and zero-match rows, and the repetition table retains all 2,730 planned rep-pairs with unmatched states and blank metrics.

| Comparison | Planned strata | Complete n=3 | Partial n=1-2 | No matched reps |
|---|---:|---:|---:|---:|
| altered_direct_minus_unchanged_control | 238 | 168 | 1 | 69 |
| treatment_minus_unchanged_control | 336 | 201 | 85 | 50 |
| treatment_minus_untreated_altered | 336 | 201 | 85 | 50 |

## Full three-repetition comparisons

All complete strata are enumerated in E4_COMPLETE_THREE_REP_BLOCKS.csv. They report paired changes in balanced accuracy, overall coverage, mean set size, and target-class recall/coverage/set size. Differences are arm minus reference. Values are not pooled across methods, target classes, severities, or treatments; inspect each row with its actual matched n.

## Planned-cell availability

The method/route status table shows current coverage by planned method and treatment. Waiting dependencies remain pending; terminal failures and unavailable dependencies are kept separate. No cell was assigned a metric without a validated evaluation JSON.

| Method | Route | Treatment | Planned | Successful | Scientific failure | Unsupported | Unavailable | Waiting |
|---|---|---|---|---:|---:|---:|---:|---:|
| arf | direct | none | 45 | 4 | 0 | 0 | 0 | 41 |
| cart | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| chow_liu | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| copula | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| extra_trees | direct | none | 45 | 0 | 0 | 0 | 0 | 45 |
| gaussian_nb | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| gmm | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| hist_gb | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | generated_arf | 42 | 1 | 0 | 0 | 0 | 41 |
| hist_gb | treatment | generated_chow_liu | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | generated_copula | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | generated_gmm | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | generated_kde | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | ros | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | smote | 42 | 42 | 0 | 0 | 0 | 0 |
| hist_gb | treatment | weighted | 42 | 42 | 0 | 0 | 0 | 0 |
| kde | direct | none | 45 | 0 | 42 | 0 | 3 | 0 |
| knn | direct | none | 45 | 0 | 0 | 0 | 0 | 45 |
| lda | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| linear_svm | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| logistic | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| logistic | treatment | generated_arf | 42 | 1 | 0 | 0 | 0 | 41 |
| logistic | treatment | generated_chow_liu | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | generated_copula | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | generated_gmm | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | generated_kde | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | ros | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | smote | 42 | 42 | 0 | 0 | 0 | 0 |
| logistic | treatment | weighted | 42 | 42 | 0 | 0 | 0 | 0 |
| qda | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| random_forest | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |
| random_forest | treatment | generated_arf | 42 | 0 | 0 | 0 | 0 | 42 |
| random_forest | treatment | generated_chow_liu | 42 | 21 | 0 | 0 | 0 | 21 |
| random_forest | treatment | generated_copula | 42 | 21 | 0 | 0 | 0 | 21 |
| random_forest | treatment | generated_gmm | 42 | 21 | 0 | 0 | 0 | 21 |
| random_forest | treatment | generated_kde | 42 | 16 | 0 | 0 | 0 | 26 |
| random_forest | treatment | ros | 42 | 20 | 0 | 0 | 0 | 22 |
| random_forest | treatment | smote | 42 | 20 | 0 | 0 | 0 | 22 |
| random_forest | treatment | weighted | 42 | 25 | 0 | 0 | 0 | 17 |
| rbf_svm | direct | none | 45 | 0 | 0 | 0 | 0 | 45 |
| shared_diagonal | direct | none | 45 | 45 | 0 | 0 | 0 | 0 |

## Interpretation limits

This is an available-cell description for the E4 blocks that had validated saved metrics at the observation time; unresolved and failed blocks remain visible in the coverage ledger. It is not the final E4 analysis, and no global calibration-q validation is claimed complete. Conformal set size is interpreted with achieved overall and target-class coverage. Timing/resource feasibility is not inferred from predictive scores. No bootstrap, confidence intervals, significance tests, or test-based selection were used.

The E4 evaluation score type is retained per arm; numeric conformal thresholds are not compared across probability and native-margin score conventions. Only coverage and set size are used as comparable conformal summaries.

## Reproduction and evidence

Run analyze_completed_blocks.py on EC2 with the same runtime. It reads only the E4 scientific-evaluation task rows from registry.sqlite in a read-only transaction and validated evaluation.json files. It does not deserialize pipelines, inspect raw test predictions, or fit/infer. Row and file SHA-256 values are saved in the companion CSV and evidence manifest.

