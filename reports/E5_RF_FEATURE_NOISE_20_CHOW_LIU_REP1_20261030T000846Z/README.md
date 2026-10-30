# E5 synthetic Random Forest feature-noise 20% result, Chow-Liu generator, rep 1

Validated case e5/rep_1/eval/synthetic/random_forest/feature_noise_20_chow_liu, matched only to same-repetition synthetic Random Forest / Chow-Liu clean baseline e5/rep_1/eval/synthetic/chow_liu/random_forest/clean.

| Metric | Corrupted | Matching clean | Corrupted minus clean |
|---|---:|---:|---:|
| Balanced accuracy | 0.596932 | 0.626125 | -0.029193 |
| Coverage | 0.895216 | 0.896382 | -0.001166 |
| Mean set size | 2.346656 | 2.216446 | +0.130210 |

This is a descriptive matched pair with n=1 of 3; sample SD is undefined. Both results use 10,000 calibration and 500,000 test objects with matching class supports. This one repetition does not establish a general corruption effect. No bootstrap, significance test, model fit, or new inference was performed.
