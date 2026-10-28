# E4 direct KNN imbalance block

Scope: the direct K-nearest-neighbor route only. The block contains three unchanged controls plus seven target classes at half-share and one-tenth-share severity in each of three repetitions. The full E4 restoration grid is not summarized here. This block does not complete E4.

All 45 planned evaluations validated successfully. Each of the 42 altered-cohort evaluations is paired with the unchanged control from the same repetition. Differences are altered minus control. The condition summaries show n/3, arithmetic means and sample standard deviations across the three paired repetitions. Sample SD is descriptive variability, not a confidence interval. No bootstrap or significance tests were used.

Class order is A, F, G, K, M, GALAXY, QSO. All evaluations used 10,000 calibration rows and 500,000 fixed test rows. Seven-class confusion-matrix recomputation agrees with recorded balanced accuracy. Overall and classwise conformal coverage and prediction-set sizes are reported together. The nominal 90% target does not imply 90% coverage for every class.

Controls: 3 fixed-configuration E4 fits reused the successful imported E1-selected KNN settings (zero tuning trials). Altered KNN fits were selected on their matching altered fitting cohorts. Actual saved trial-history rows: 210 across 42 altered fits; status counts are {"duplicate_cached": 48, "success": 162}. These counts are read from saved task/history records, including duplicate-cached trials; see provenance and trial-history CSVs.

| Target | Retained share | Matched n/3 | Change target recall | SD | Change balanced accuracy | SD | Change overall coverage | SD | Change set size | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 0.5 | 3/3 | -0.063589 | 0.159938 | -0.003556 | 0.031580 | 0.007478 | 0.009890 | 0.051283 | 0.070690 |
| A | 0.1 | 3/3 | -0.277378 | 0.154011 | -0.040257 | 0.031570 | 0.102179 | 0.002448 | 5.334267 | 0.016725 |
| F | 0.5 | 3/3 | -0.149641 | 0.087595 | 0.014495 | 0.030952 | 0.034577 | 0.058567 | 1.812827 | 3.038970 |
| F | 0.1 | 3/3 | -0.386957 | 0.066318 | 0.004095 | 0.026145 | 0.102179 | 0.002448 | 5.334267 | 0.016725 |
| G | 0.5 | 3/3 | -0.324955 | 0.032326 | 0.020482 | 0.030504 | 0.035525 | 0.055607 | 1.856943 | 3.005704 |
| G | 0.1 | 3/3 | -0.729657 | 0.033247 | -0.000896 | 0.027542 | 0.102179 | 0.002448 | 5.334267 | 0.016725 |
| GALAXY | 0.5 | 3/3 | -0.016102 | 0.019322 | 0.009749 | 0.029726 | 0.043607 | 0.054462 | 1.835039 | 3.047787 |
| GALAXY | 0.1 | 3/3 | -0.156120 | 0.081549 | -0.011701 | 0.026884 | 0.068397 | 0.060644 | 3.535661 | 3.121067 |
| K | 0.5 | 3/3 | -0.133139 | 0.009580 | 0.004934 | 0.019753 | 0.036127 | 0.059324 | 1.789404 | 3.086626 |
| K | 0.1 | 3/3 | -0.469157 | 0.032884 | -0.031335 | 0.030937 | 0.102179 | 0.002448 | 5.334267 | 0.016725 |
| M | 0.5 | 3/3 | -0.062628 | 0.023743 | 0.007937 | 0.031434 | 0.010127 | 0.014861 | 0.065404 | 0.102161 |
| M | 0.1 | 3/3 | -0.328727 | 0.044264 | -0.028692 | 0.033066 | 0.040894 | 0.055271 | 1.888899 | 3.000446 |
| QSO | 0.5 | 3/3 | -0.107377 | 0.025715 | 0.003878 | 0.030954 | 0.035801 | 0.059611 | 1.786985 | 3.088516 |
| QSO | 0.1 | 3/3 | -0.501417 | 0.034321 | -0.051897 | 0.029244 | 0.069190 | 0.057189 | 3.570321 | 3.065996 |

Severity `0.5` retains half the target class's original fitting share; `0.1` retains one-tenth. Exact realized class counts, source histograms, selected parameters and each repetition are in the CSV files. No generated restoration, weighting, oversampling or SMOTE comparisons are included in this direct-method block.

## Limits

The findings describe direct KNN for these target/severity/repetition combinations. Per-class recall changes are target-specific; an improvement for one class or severity does not establish a general benefit. E4-wide coverage, failures and other methods are not inferred from this subset. Global E5 q replay validation remains pending. All durations are hardware-dependent.

Only registry rows, validation receipts, evaluation JSON, fit and cohort metadata, publication receipts, and saved tuning histories were read. Pipelines and held-out arrays were not loaded; no fitting, prediction, or inference was run.
