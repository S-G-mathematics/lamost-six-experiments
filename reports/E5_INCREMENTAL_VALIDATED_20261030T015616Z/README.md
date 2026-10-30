# Incremental validated E5 results

Read-only registry snapshot: 2026-10-30T01:56:16.520900+00:00. Planned E5 denominator: 960; current counts: 713 successful, 50 scientific failures, 78 unavailable, 101 user-stopped, and 18 waiting.

New validated cases since the preceding published scope/E6 note are listed below. Each is paired only with its same-repetition, same-learner, same-route, same-generator clean reference. Every pair is n=1 of 3; sample SD is undefined. These are descriptive comparisons, not general robustness claims.

| Mechanism / generator | Rate | Metric | Corrupted | Matching clean | Corrupted minus clean |
|---|---:|---|---:|---:|---:|
| label_noise / copula | 0.05 | balanced accuracy | 0.582086 | 0.595396 | -0.013310 |
| label_noise / copula | 0.05 | coverage | 0.893820 | 0.891792 | +0.002028 |
| label_noise / copula | 0.05 | set size | 2.252508 | 2.198152 | +0.054356 |
| label_noise / arf | 0.1 | balanced accuracy | 0.653976 | 0.658155 | -0.004178 |
| label_noise / arf | 0.1 | coverage | 0.893378 | 0.895476 | -0.002098 |
| label_noise / arf | 0.1 | set size | 2.017652 | 2.010262 | +0.007390 |
| label_noise / chow_liu | 0.1 | balanced accuracy | 0.623227 | 0.626125 | -0.002898 |
| label_noise / chow_liu | 0.1 | coverage | 0.897520 | 0.896382 | +0.001138 |
| label_noise / chow_liu | 0.1 | set size | 2.257902 | 2.216446 | +0.041456 |
| label_noise / copula | 0.1 | balanced accuracy | 0.577932 | 0.595396 | -0.017464 |
| label_noise / copula | 0.1 | coverage | 0.891124 | 0.891792 | -0.000668 |
| label_noise / copula | 0.1 | set size | 2.277474 | 2.198152 | +0.079322 |

Seven-class metrics, validation bindings, and array hashes are in the accompanying CSV/JSON files. The NPZ archive contains only saved test outcomes; it contains no fitted models. No model fitting, inference, bootstrap, calibration replay, or full-project audit was performed.
