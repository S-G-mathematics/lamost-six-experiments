# Validated E5 results update

Registry snapshot: 2026-10-30T00:20:32.094209+00:00. E5 planned denominator is 960. The snapshot records:
- successful: 709
- scientific_failure: 50
- unavailable_dependency: 78
- user_stopped: 101
- waiting_for_dependency: 22

These three successful cases are paired only with their same-repetition, same-method, same-route, same-generator clean baseline. Each comparison is n=1 of 3; sample SD is undefined. Results are descriptive and do not establish a general robustness effect. No bootstrap or significance tests were run.

| Mechanism / generator | Rate | Metric | Corrupted | Clean | Corrupted minus clean |
|---|---:|---|---:|---:|---:|
| feature_noise / copula | 0.2 | balanced accuracy | 0.561860 | 0.595396 | -0.033536 |
| feature_noise / copula | 0.2 | coverage | 0.891764 | 0.891792 | -0.000028 |
| feature_noise / copula | 0.2 | set size | 2.417564 | 2.198152 | +0.219412 |
| label_noise / arf | 0.05 | balanced accuracy | 0.656745 | 0.658155 | -0.001409 |
| label_noise / arf | 0.05 | coverage | 0.892292 | 0.895476 | -0.003184 |
| label_noise / arf | 0.05 | set size | 1.991344 | 2.010262 | -0.018918 |
| label_noise / chow_liu | 0.05 | balanced accuracy | 0.623465 | 0.626125 | -0.002660 |
| label_noise / chow_liu | 0.05 | coverage | 0.899266 | 0.896382 | +0.002884 |
| label_noise / chow_liu | 0.05 | set size | 2.250880 | 2.216446 | +0.034434 |

Seven-class paired differences and artifact hashes are in the accompanying files. Saved NPZ arrays contain test outcomes only; no fitted models are included.

## Separate E1/E2 descriptive-table audit

Independent saved-table arithmetic audit: reports/E1_E2_INDEPENDENT_DESCRIPTIVE_TABLE_AUDIT_20261030.json (SHA-256 da54541d5ab0fe4f11c5f46f6c766bc42d3365e6b49d24f9d9fa5118b18da9db). It rechecked E1 765 cell and 153 method-budget denominators/means/SDs (maximum difference 8.88e-16) and E2 equal-seven-class averages/within-stratum Spearman values across the saved 270/1,596 tables (maximum differences 2.22e-16 and 1.39e-17); issue count 0. This table arithmetic audit does not certify full-project completion or calibration-quantile replay.
