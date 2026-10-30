# E5 synthetic Random Forest feature-noise 20% result, ARF generator, rep 1

Validated evaluation: e5/rep_1/eval/synthetic/random_forest/feature_noise_20_arf. It is compared only with its matched same-repetition, same-learner, same-synthetic-route, ARF clean baseline: e5/rep_1/eval/synthetic/arf/random_forest/clean.

| Metric | Corrupted | Matching clean | Corrupted minus clean |
|---|---:|---:|---:|
| Balanced accuracy | 0.606932 | 0.658155 | -0.051222 |
| Coverage | 0.893502 | 0.895476 | -0.001974 |
| Mean set size | 2.135906 | 2.010262 | +0.125644 |

This is one descriptive pair (n=1 of 3); sample SD is undefined. Both saved evaluations use 10,000 calibration and 500,000 test objects with matching class supports. The per-class file retains all seven class differences. This single repetition does not establish a general robustness effect. No bootstrap, significance test, model fit, or new inference was performed.
