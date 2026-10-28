# E3 conformal coverage checkpoint - INTERIM

Observed UTC: 2026-10-25T16:09:30.357880+00:00

This is a descriptive checkpoint of all 23 planned route/generator/learner groups, not a final E3 report or a model-selection analysis. E3 has 69 planned repetition outcomes; 61 successful outcomes currently have class diagnostics. The remaining outcomes retain their actual state; unavailable or failed evaluations have no imputed scores. No new fitting or inference was performed.

The nominal conformal target is 90%. Overall coverage is population weighted across the fixed test cohort. It does not imply 90% coverage separately within each class. The table reports the smallest class mean coverage solely as a diagnostic; the companion class CSV reports every class and every available repetition. Means are descriptive, conditional on success. Sample SDs are repetition variability, not confidence intervals. No thresholds were adjusted.

| Route | Generator | Learner/method | Successful/planned repetitions | Overall coverage | Mean set size | Lowest class mean coverage |
|---|---|---|---:|---:|---:|---|
| direct | arf | arf | 3/3 | 0.8969 | 2.2784 | A 0.5178 |
| direct | chow_liu | chow_liu | 3/3 | 0.8987 | 2.5387 | A 0.6131 |
| direct | copula | copula | 3/3 | 0.8976 | 2.3711 | A 0.4973 |
| direct | gmm | gmm | 3/3 | 0.8996 | 1.4870 | A 0.7856 |
| direct | kde | kde | 0/3 | unavailable | unavailable |  unavailable |
| real | shared real | hist_gb | 3/3 | 0.8978 | 1.5610 | A 0.6630 |
| real | shared real | logistic | 3/3 | 0.8993 | 1.7704 | A 0.5069 |
| real | shared real | random_forest | 3/3 | 0.9006 | 1.5645 | A 0.7201 |
| synthetic | arf | hist_gb | 3/3 | 0.8966 | 2.1709 | A 0.4424 |
| synthetic | arf | logistic | 3/3 | 0.8996 | 2.4864 | A 0.1329 |
| synthetic | arf | random_forest | 3/3 | 0.8966 | 2.1485 | A 0.4503 |
| synthetic | chow_liu | hist_gb | 3/3 | 0.8977 | 2.1876 | A 0.4357 |
| synthetic | chow_liu | logistic | 3/3 | 0.8984 | 2.5163 | A 0.0255 |
| synthetic | chow_liu | random_forest | 3/3 | 0.9005 | 2.2616 | A 0.4650 |
| synthetic | copula | hist_gb | 3/3 | 0.8973 | 2.3044 | A 0.2968 |
| synthetic | copula | logistic | 3/3 | 0.8987 | 2.2627 | A 0.1643 |
| synthetic | copula | random_forest | 3/3 | 0.8981 | 2.3135 | A 0.3192 |
| synthetic | gmm | hist_gb | 3/3 | 0.8983 | 1.5267 | A 0.6975 |
| synthetic | gmm | logistic | 3/3 | 0.8997 | 1.8558 | A 0.4484 |
| synthetic | gmm | random_forest | 2/3 | 0.8973 | 1.5308 | A 0.7104 |
| synthetic | kde | hist_gb | 2/3 | 0.8934 | 1.8687 | A 0.3510 |
| synthetic | kde | logistic | 2/3 | 0.8980 | 2.1072 | A 0.3425 |
| synthetic | kde | random_forest | 1/3 | 0.8921 | 1.8594 | A 0.3486 |

Source tables were SHA-256 checked unchanged during the calculation. Their exact hashes and output hashes are in the companion JSON receipt. Earlier E1/E2 test results were already observed. These are later-experiment results under the recorded E3 policy; they do not repair frozen E1 failures or fill unavailable E2 primary cells.
