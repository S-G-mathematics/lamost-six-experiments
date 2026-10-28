# E5 completed generator-route comparison

## Scope and data

This read-only descriptive slice compares three flexible generators (GMM, Gaussian copula, continuous Chow-Liu) under two E5 routes: the generator direct Bayes classifier and synthetic-only downstream logistic regression or histogram gradient boosting. Routes are matched by generator family, repetition, corruption condition, and rate. The clean control and all three fitting-only corruption mechanisms at 5%, 10%, and 20% are included.

All 270 planned cells in this subset have validated successful registry outcomes and saved evaluation JSON files whose SHA-256 matches the registry validation record: 90 direct route cells and 180 synthetic-only cells. There are 180 route rows (including clean comparisons), 162 corrupted route rows, and 1,134 per-class corrupted rows. The report summarizes 54 route-by-condition strata and 378 per-class strata; each has three paired repetitions. Cell availability is listed in planned_case_availability.csv.

Inputs are registry metadata and validated aggregate evaluation JSON only. No models, NPZ role or prediction arrays, or per-row predictions were read; no refits, rescoring, recalibration, or test-driven model selection occurred. E1/E2 outcomes have already been observed, so this is descriptive and does not claim an untouched prospective test cohort. Global calibration replay validation and root review remain pending.

## Paired contrasts

direct_corruption_change_* is the corrupted-condition metric minus the route-matched clean metric for the same repetition. synthetic_corruption_change_* is the corresponding synthetic-only route change. synthetic_minus_direct_change_* is the synthetic change minus the direct change. Raw corrupted-condition route differences use synthetic_minus_direct_*. Negative values are lower changes or scores; signs are descriptive, not significance or superiority claims.

Balanced accuracy is the primary predictive metric. Coverage is shown alongside mean conformal set size. Per-repetition values are retained; means and sample standard deviations are descriptive, with no bootstrap or significance tests.

## Example: 20 percent label noise

Values are means over three paired repetitions. Change is corrupted minus route-matched clean. Coverage and set size are reported together.

| Generator | Synthetic learner | Direct BA | Synthetic BA | Direct BA change | Synthetic BA change | Difference in BA change (synthetic minus direct) | Direct coverage / size | Synthetic coverage / size |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| GMM | Logistic | 0.7831 | 0.5558 | -0.0225 | -0.0877 | -0.0652 | 0.8990 / 1.6357 | 0.8968 / 2.0252 |
| GMM | HistGB | 0.7831 | 0.7505 | -0.0225 | -0.0201 | 0.0023 | 0.8990 / 1.6357 | 0.8970 / 1.6034 |
| Gaussian copula | Logistic | 0.5411 | 0.5018 | -0.0381 | -0.0635 | -0.0254 | 0.8992 / 2.5550 | 0.8983 / 2.3392 |
| Gaussian copula | HistGB | 0.5411 | 0.5652 | -0.0381 | -0.0257 | 0.0125 | 0.8992 / 2.5550 | 0.8988 / 2.4511 |
| Chow-Liu | Logistic | 0.5924 | 0.3446 | -0.0194 | -0.1421 | -0.1227 | 0.8993 / 3.1375 | 0.8980 / 2.5539 |
| Chow-Liu | HistGB | 0.5924 | 0.6257 | -0.0194 | -0.0057 | 0.0137 | 0.8993 / 3.1375 | 0.8980 / 2.2330 |

This condition shows route- and generator-specific changes. HistGB degradation is smaller than direct Bayes for these three families, while logistic route differences vary by family. Set-size changes must be interpreted with achieved coverage; a smaller set alone does not establish a better calibrated procedure. These three-repetition results do not support a universal route ranking.

## Cost evidence

Registry task wall spans are shown separately from subprocess phase receipts. Recorded task wall spans run from registry started_utc to finished_utc; they include worker/controller observation overhead, exclude pre-admission queue waiting, and are not a complete accounting of earlier invalid or interrupted attempts. Do not add task wall spans to the phase totals. Shared dependencies are counted once in the unique-task ledger and are not apportioned among routes. Timing is hardware- and scheduling-dependent.

| E5 component | Unique tasks | Task wall seconds sum | Mean task seconds | Median task seconds |
|---|---:|---:|---:|---:|
| Direct generator fitting | 81 | 418.84 | 5.17 | 4.18 |
| Synthetic generation | 81 | 384.50 | 4.75 | 4.66 |
| Synthetic-only downstream fitting | 162 | 4119.99 | 25.43 | 18.86 |
| Direct evaluation task wall | 81 | 529.93 | 6.54 | 6.35 |
| Synthetic evaluation task wall | 162 | 3168.64 | 19.56 | 12.96 |
| Direct clean evaluation aliases | 9 | 18.38 | 2.04 | 2.01 |
| Synthetic clean evaluation aliases | 18 | 50.35 | 2.80 | 2.75 |

### Calibration and test-inference phase receipts

| Route | Phase | Successful / planned receipts | Sum seconds | Mean seconds | Sample SD | Median seconds | Min to max seconds | Missing or failed |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| direct | calibration | 81 / 81 | 95.45 | 1.18 | 0.13 | 1.29 | 1.03 to 1.32 | 0 |
| direct | test_inference | 81 / 81 | 269.69 | 3.33 | 0.73 | 3.37 | 2.59 to 5.18 | 0 |
| synthetic | calibration | 162 / 162 | 247.46 | 1.53 | 0.42 | 1.34 | 1.04 to 2.41 | 0 |
| synthetic | test_inference | 162 / 162 | 2412.16 | 14.89 | 15.11 | 2.62 | 1.56 to 46.99 | 0 |

Phase durations come from per-attempt phase_calibrate_result.json and phase_evaluate_result.json. Calibration and test inference are separate here; the broader task wall duration remains a separate measurement. The full per-task evidence paths, hashes, phase exit statuses, and RSS values are in evaluation_phase_costs.csv. The unique task cost ledger also records shared E3 fits and E4 clean-control references.

## Figures

Figures show changes from route-matched clean values; tables report achieved coverage alongside set size. Each plotted mean has n=3 paired repetitions:

- E5_balanced_accuracy_degradation.png
- E5_coverage_degradation.png
- E5_set_size_degradation.png

## Limitations and reproduction

This is a completed subset, not the full E5 grid: ARF, KDE, other downstream learners, and other direct methods are outside this report. Results are conditional on the exact completed cells and three paired repetitions. The defined corruption mechanisms do not represent every astronomical measurement error. No bootstrap intervals or significance claims are reported.

Reproduce on EC2 with the existing environment and plotting overlay (venv first; this preserves the installed NumPy):

    PYTHONPATH=/home/ubuntu/lamost_e1_migration_20261023/venv/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages:/usr/lib/python3/dist-packages OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MPLBACKEND=Agg nice -n 19 /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/e5_completed_generator_routes_20261027/reproduce_report.py

The script rechecks each evaluation JSON against the registry validation SHA, rebuilds the availability and paired tables, reads saved phase supervision receipts for separate calibration and test inference timing, and refreshes input/output hashes. It does not modify registry or scientific artifacts.
