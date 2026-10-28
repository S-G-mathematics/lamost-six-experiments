# E5 direct K-nearest-neighbor corruption block

Descriptive results for the direct K-nearest-neighbor route only: three repetitions, one clean control per repetition, and all three fitting-data corruption mechanisms at 5%, 10%, and 20%. This block does not complete E5.

All 30 planned cells (three clean controls and 27 corrupted cells) are validated. Each corrupted cell is paired with the clean control from the same repetition. Differences are corrupted minus clean. Means and sample SDs use the three paired repetitions; they are descriptive summaries, not confidence intervals. No bootstrap or significance tests were used.

Class order is A, F, G, K, M, GALAXY, QSO. Each evaluation has 10,000 calibration rows and 500,000 test rows. Balanced accuracy recomputed from the saved seven-by-seven confusion matrices matches the recorded value. Corrupted fits use the repetition-matched clean-selected configuration and fitting IDs; no tuning on corrupted data was used.

| Mechanism | Rate | Matched n/3 | Change in balanced accuracy | SD | Change in coverage | SD | Change in set size | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| feature_noise | 5% | 3/3 | -0.002557 | 0.001013 | -0.000099 | 0.001008 | 0.006427 | 0.004919 |
| feature_noise | 10% | 3/3 | -0.005004 | 0.001257 | 0.000424 | 0.002917 | 0.016579 | 0.014517 |
| feature_noise | 20% | 3/3 | -0.009613 | 0.001446 | -0.000293 | 0.003788 | 0.027821 | 0.021699 |
| label_noise | 5% | 3/3 | -0.002372 | 0.002123 | 0.001177 | 0.001525 | 0.115237 | 0.098021 |
| label_noise | 10% | 3/3 | -0.007285 | 0.005835 | 0.000571 | 0.002160 | 0.232643 | 0.199965 |
| label_noise | 20% | 3/3 | -0.023067 | 0.017826 | 0.000125 | 0.002330 | 0.494126 | 0.415414 |
| missingness | 5% | 3/3 | -0.001386 | 0.000316 | 0.000428 | 0.001098 | 0.008077 | 0.005427 |
| missingness | 10% | 3/3 | -0.003240 | 0.000288 | 0.000796 | 0.000886 | 0.015917 | 0.002539 |
| missingness | 20% | 3/3 | -0.006139 | 0.000423 | -0.000031 | 0.001582 | 0.024659 | 0.014463 |

All individual repetitions and per-class recalls, coverage and set size are in the CSV tables. Interpret set-size changes together with coverage.

## Limits

These findings cover only direct K-nearest-neighbor under the saved clean-selected configurations and these specified corruption mechanisms. They do not generalize to other classifiers, synthetic routes, or all astronomical measurement errors. The wider E5 grid and its independent global validation remain pending; no overall E5-completion claim follows from this block.

The analysis read only task records, evaluation JSONs, fit selection/result metadata, and the fixed class-order manifest. It did not load pipelines, fit models, generate predictions, or alter scientific inputs. Per-cell artifact hashes are bound in the output tables and evidence manifest.

## Matched comparison with direct RF

For each repetition and corruption condition, each classifier?s change is first calculated against its own clean control. The table below reports the KNN change minus the RF change for the same repetition and condition; n is the number of matched repetition pairs. These contrasts are descriptive and do not imply universal superiority. Individual repetition values are in the linked CSV.

| Mechanism | Rate | Matched n/3 | KNN?RF ? balanced accuracy | SD | KNN?RF ? coverage | SD | KNN?RF ? set size | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| feature_noise | 5% | 3/3 | 0.000633 | 0.001427 | -0.000263 | 0.000748 | -0.000710 | 0.004970 |
| feature_noise | 10% | 3/3 | 0.000695 | 0.001660 | 0.000265 | 0.004208 | 0.001521 | 0.023248 |
| feature_noise | 20% | 3/3 | 0.000943 | 0.001890 | -0.000394 | 0.002473 | -0.001251 | 0.020236 |
| label_noise | 5% | 3/3 | -0.000122 | 0.002253 | 0.000782 | 0.002355 | 0.079091 | 0.104213 |
| label_noise | 10% | 3/3 | -0.001573 | 0.005238 | -0.001557 | 0.002750 | 0.136730 | 0.207208 |
| label_noise | 20% | 3/3 | -0.005758 | 0.018788 | -0.000291 | 0.004567 | 0.252103 | 0.438334 |
| missingness | 5% | 3/3 | -0.000143 | 0.000469 | 0.001408 | 0.000983 | 0.006983 | 0.004756 |
| missingness | 10% | 3/3 | -0.000144 | 0.000145 | -0.000409 | 0.000857 | -0.001642 | 0.002074 |
| missingness | 20% | 3/3 | -0.000608 | 0.000593 | -0.000161 | 0.003370 | 0.003778 | 0.022209 |
