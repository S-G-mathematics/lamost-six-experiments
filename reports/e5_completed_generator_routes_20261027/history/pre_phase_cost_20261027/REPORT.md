# E5 completed generator-route comparison

## Scope and data

This read-only descriptive slice compares three flexible generators (GMM, Gaussian copula, continuous Chow?Liu) under two E5 routes: the generator's direct Bayes classifier and synthetic-only downstream logistic regression or histogram gradient boosting. Each route is matched by generator family, repetition, corruption condition, and rate. The clean control and all three fitting-only corruption mechanisms at 5%, 10%, and 20% are included.

All 270 planned evaluation cells in this slice have validated successful registry outcomes and saved evaluation.json files whose SHA-256 matches the registry validation record: 90 direct route cells and 180 synthetic-only cells. The comparison contains 180 matched route rows (including clean comparisons), 162 corrupted route rows, and 1,134 per-class corrupted rows. It summarizes 54 generator ? learner ? corruption strata and 378 class-level strata; each has three paired repetitions. Availability is listed cell by cell in planned_case_availability.csv.

Inputs are the EC2 registry and validated aggregate evaluation JSON only. The script does not read models, NPZ role or prediction arrays, or per-row test predictions; it does not refit, rescore, recalibrate, or select models. E1/E2 outcomes have already been observed, so this is descriptive and does not claim an untouched prospective test cohort. Global calibration replay validation and root review remain pending.

## Paired contrast definitions

direct_corruption_change_* is the same direct generator's corrupted-condition metric minus its clean metric for that repetition. synthetic_corruption_change_* is the corresponding synthetic-only route change. synthetic_minus_direct_change_* is the synthetic route change minus the direct route change. Raw corrupted-condition route differences use synthetic_minus_direct_*. Negative differences mean the synthetic route's value/change was lower than the direct route's; the sign is not a significance or superiority claim.

All predictive performance summaries show balanced accuracy. Conformal coverage is shown alongside mean set size. Repetition-level values are retained in the CSVs; means and sample standard deviations are descriptive, with no bootstrap or significance tests.

## Example: 20% label-noise condition

Values are means over three paired repetitions. ?Change? is corrupted minus route-matched clean. Set size is reported with achieved coverage.

| Generator | Synthetic learner | Direct BA | Synthetic BA | Direct BA change | Synthetic BA change | Difference in BA change (synthetic ? direct) | Direct coverage / set size | Synthetic coverage / set size |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Chow?Liu | HistGB | 0.5924 | 0.6257 | ?0.0194 | ?0.0057 | +0.0137 | 0.8993 / 3.1375 | 0.8980 / 2.2330 |
| Chow?Liu | Logistic | 0.5924 | 0.3446 | ?0.0194 | ?0.1421 | ?0.1227 | 0.8993 / 3.1375 | 0.8980 / 2.5539 |
| Copula | HistGB | 0.5411 | 0.5652 | ?0.0381 | ?0.0257 | +0.0125 | 0.8992 / 2.5550 | 0.8988 / 2.4511 |
| Copula | Logistic | 0.5411 | 0.5018 | ?0.0381 | ?0.0635 | ?0.0254 | 0.8992 / 2.5550 | 0.8983 / 2.3392 |
| GMM | HistGB | 0.7831 | 0.7505 | ?0.0225 | ?0.0201 | +0.0023 | 0.8990 / 1.6357 | 0.8970 / 1.6034 |
| GMM | Logistic | 0.7831 | 0.5558 | ?0.0225 | ?0.0877 | ?0.0652 | 0.8990 / 1.6357 | 0.8968 / 2.0252 |

These rows show route- and generator-specific changes: in this condition the HistGB degradation is smaller than direct Bayes for each family, while the logistic comparison varies and is more negative for all three listed families. Set-size changes and coverage must be interpreted together; a lower set size alone does not establish a better calibrated procedure. These three-repetition results do not support a universal route ranking.

## Recorded cost evidence

Task spans below are wall-clock differences between registry started_utc and finished_utc, not CPU time. The evaluation category combines calibration and test inference because the saved records do not separate those phases. Shared dependencies are listed once in dependency_cost_ledger.csv, with consumer counts; their cost is not allocated among routes. Clean aliases reuse prior evaluations and are identified separately. These measurements are hardware- and scheduling-dependent.

| Unique task category | Cells | Sum of task wall spans (s) | Mean (s) | Median (s) | Interpretation |
|---|---:|---:|---:|---:|---|
| E5 direct generator fitting | 81 | 418.84 | 5.17 | 4.18 | Shared dependency for direct and synthetic routes |
| E5 synthetic generation | 81 | 384.50 | 4.75 | 4.66 | Generated examples reused across two downstream learners |
| E5 synthetic-only downstream fitting | 162 | 4,119.99 | 25.43 | 18.86 | One task per repetition ? family ? condition ? learner |
| E5 direct evaluation (calibration + test inference) | 81 | 529.93 | 6.54 | 6.35 | Corrupted conditions; phase costs not separated |
| E5 synthetic evaluation (calibration + test inference) | 162 | 3,168.64 | 19.56 | 12.96 | Corrupted conditions; phase costs not separated |
| E5 clean evaluation aliases | 27 | 75.08 | 2.78 | 2.75 | Reused direct/synthetic clean controls; not new evaluation compute |

The full cost ledger also records shared E3 generator and synthetic-baseline fitting dependencies and linked E4 clean-control references. It does not sum shared task time into multiple route totals.

## Limitations and reproduction

This is a completed subset, not the full E5 grid: ARF, KDE, other downstream learners, and other direct methods are outside this report. The saved metrics are conditional on the exact completed cases and three paired repetitions. Corruption mechanisms are the specified fitting-row perturbations, not a complete model of astronomical measurement errors. No bootstrap intervals or statistical-significance claims are provided.

No figure was emitted because Matplotlib is absent from the existing project virtual environment; no package was installed for this report. The numerical tables remain the source of reported values.

Reproduce on EC2 with the existing environment:

    nice -n 19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg       /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python       /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/e5_completed_generator_routes_20261027/reproduce_report.py

The script rechecks each selected evaluation JSON against its registry SHA, rebuilds availability, paired route and per-class tables, dependency wall-time summaries, and the input/output SHA manifest. It does not modify registry or scientific artifacts.
