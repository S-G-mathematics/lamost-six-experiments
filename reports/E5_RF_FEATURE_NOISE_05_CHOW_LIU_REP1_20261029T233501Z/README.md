# E5 synthetic Random Forest feature-noise result, rep 1

Validated case: e5/rep_1/eval/synthetic/random_forest/feature_noise_05_chow_liu. Matching clean baseline: e5/rep_1/eval/synthetic/chow_liu/random_forest/clean. The match uses the same repetition, learner, synthetic route, and Chow-Liu generator; no cross-repetition or cross-route pairing is used.

| Metric | Corrupted | Matching clean | Corrupted minus clean |
|---|---:|---:|---:|
| Balanced accuracy | 0.610753 | 0.626125 | -0.015372 |
| Coverage | 0.896618 | 0.896382 | +0.000236 |
| Mean set size | 2.362494 | 2.216446 | +0.146048 |

The pair is n=1 of 3 planned repetitions, so sample SD is undefined. This is a descriptive single-repetition result and does not establish a general corruption effect or robustness claim. Both evaluations use 10,000 calibration and 500,000 test objects, with matching class supports. Per-class metrics and differences are tabulated. No bootstrap, significance test, model fitting, or new inference was performed for this report.
