# E5 direct random-forest corruption block

Descriptive results for the direct random-forest route only: three repetitions, one clean control per repetition, and all three fitting-data corruption mechanisms at 5%, 10%, and 20%. This block does not complete E5.

All 30 planned cells (three clean controls and 27 corrupted cells) are validated. Each corrupted cell is paired with the clean control from the same repetition. Differences are corrupted minus clean. Means and sample SDs use the three paired repetitions; they are descriptive summaries, not confidence intervals. No bootstrap or significance tests were used.

Class order is A, F, G, K, M, GALAXY, QSO. Each evaluation has 10,000 calibration rows and 500,000 test rows. Balanced accuracy recomputed from the saved seven-by-seven confusion matrices matches the recorded value. Corrupted fits use the repetition-matched clean-selected configuration and fitting IDs; no tuning on corrupted data was used.

| Mechanism | Rate | Matched n/3 | Change in balanced accuracy | SD | Change in coverage | SD | Change in set size | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| feature_noise | 5% | 3/3 | -0.003190 | 0.000493 | 0.000164 | 0.001665 | 0.007137 | 0.008300 |
| feature_noise | 10% | 3/3 | -0.005699 | 0.000504 | 0.000159 | 0.001318 | 0.015058 | 0.008862 |
| feature_noise | 20% | 3/3 | -0.010556 | 0.000554 | 0.000101 | 0.002135 | 0.029072 | 0.009062 |
| label_noise | 5% | 3/3 | -0.002250 | 0.000710 | 0.000395 | 0.001683 | 0.036146 | 0.008998 |
| label_noise | 10% | 3/3 | -0.005713 | 0.000878 | 0.002129 | 0.001363 | 0.095913 | 0.007914 |
| label_noise | 20% | 3/3 | -0.017309 | 0.001158 | 0.000416 | 0.003392 | 0.242023 | 0.027214 |
| missingness | 5% | 3/3 | -0.001244 | 0.000155 | -0.000980 | 0.000197 | 0.001094 | 0.000782 |
| missingness | 10% | 3/3 | -0.003096 | 0.000350 | 0.001205 | 0.000307 | 0.017559 | 0.000782 |
| missingness | 20% | 3/3 | -0.005531 | 0.000655 | 0.000130 | 0.003013 | 0.020881 | 0.015593 |

All individual repetitions and per-class recalls, coverage and set size are in the CSV tables. Interpret set-size changes together with coverage.

## Limits

These findings cover only direct random forest under the saved clean-selected configurations and these specified corruption mechanisms. They do not generalize to other classifiers, synthetic routes, or all astronomical measurement errors. The wider E5 grid and its independent global validation remain pending; no overall E5-completion claim follows from this block.

The analysis read only task records, evaluation JSONs, fit selection/result metadata, and the fixed class-order manifest. It did not load pipelines, fit models, generate predictions, or alter scientific inputs. Per-cell artifact hashes are bound in the output tables and evidence manifest.
