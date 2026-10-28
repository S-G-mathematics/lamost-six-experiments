# E6-v2 Descriptive Interim Report

Created: 2026-10-27 20:49:33 UTC / 2026-10-28 02:19:33 IST
Registry observer snapshot: 2026-10-27 20:47:52 UTC / 2026-10-28 02:17:52 IST
EC2: i-095641a281a4038b9
Scope: metadata and saved evaluation/report artifacts only. No fitting, model loading, prediction, calibration inference, or test inference was performed to create this report.

## E6 result coverage

The registry contains 21 terminal E6 entries: 15 historical member-reference aliases and 6 corrected E6-v2 primary ensemble tasks.

| Group | Planned | Successful | Scientific failure | Unavailable dependency | Operationally invalid | Pending |
|---|---:|---:|---:|---:|---:|---:|
| Historical E3 member references | 15 | 12 | 0 | 3 | 0 | 0 |
| Corrected E6-v2 ensembles | 6 | 0 | 3 | 3 | 0 | 0 |
| Total current E6 entries | 21 | 12 | 3 | 6 | 0 | 0 |

The historical reference rows are E3 evaluations aliased into the E6 comparison record. They are not evaluations newly performed by E6. The 12 successful references are GMM, copula, ARF, and Chow-Liu across three repetitions. The three KDE references are unavailable because their corresponding E3 direct KDE evaluations timed out. This is unavailable evaluation evidence, not proof that the KDE model fit was absent.

The six old E6-v1 zero-attempt gate decisions remain preserved as superseded history and are not included as current scientific E6 outcomes. The E6-v2 dependency amendment was made after the first E3 KDE direct-evaluation timeout; the old E3-evaluation hard gate was not the original frozen executable semantics.

## Corrected primary outcomes by repetition

| Rep | Equal-weight task | Learned-weight task | Shared E6 test-posterior result |
|---:|---|---|---|
| 1 | Scientific failure: prediction timeout during test | Unavailable dependency | Equal task's terminal test-posterior failure; learned task reused the terminal shared failure |
| 2 | Scientific failure: prediction timeout during test | Unavailable dependency | Equal task's terminal test-posterior failure; learned task reused the terminal shared failure |
| 3 | Scientific failure: prediction timeout during test | Unavailable dependency | Equal task's terminal test-posterior failure; learned task reused the terminal shared failure |

The learned tasks did not start a duplicate same-policy test-posterior inference after the shared phase had already terminated. All six tasks are terminal, but none has a valid test evaluation. The saved availability table records member_comparison_present=False for all six. There are zero valid E6-v2 member_comparisons artifacts, zero successful ensemble test metrics, and zero five-member ensemble comparisons.

## Tuning-only evidence

All six tasks have validated frozen tuning weights. The three equal-weight tasks retain the predeclared [0.2, 0.2, 0.2, 0.2, 0.2] vector. The three learned tasks retain their tuning-selected vectors and candidate ledgers. None of those artifacts represents calibration or test performance. The saved table marks test_evaluation_present=False and performance_metrics_included=False for every task.

The learned candidate ledger counts are 1,606 for repetition 1, 1,558 for repetition 2, and 1,606 for repetition 3. These counts describe the saved tuning search artifacts only. Do not interpret the selected tuning weights as a test-selected winner or as evidence of ensemble benefit. The tuning-best member comparator was not evaluated on test data because the shared test-posterior phase did not complete.

## Frozen protocol and information limits

E6-v2 uses five flexible generative members: GMM, Gaussian copula, ARF/FORDE, KDE, and continuous Chow-Liu. It compares equal weights with one global simplex vector selected on tuning balanced accuracy. The weights must be frozen before calibration and test evaluation. The planned search includes the equal vector, five simplex vertices, 1,000 seeded Dirichlet candidates, refinement of the top ten by pairwise transfers of 0.10, 0.05, and 0.01, and a 2,000-candidate maximum. The tuning evidence is retained, but there are no calibrated ensemble or test metrics from these six tasks.

No partial-member primary result is claimed. No bootstrap, significance, universal benefit, or test-selected winner claim is made. The fixed test cohort was already evaluated in E1/E2/E3; it is not an untouched prospective test set.

## Reproducible saved outputs

A data-only E6-v2 descriptive export was generated from the registry and saved result JSON/CSV files. Its receipt explicitly records no fitting, model loading, posterior generation, calibration/test inference, or bootstrap.

- E6 export directory: runtime_20261025/reports/E6_V2_INTERIM_20261027T204752Z
- 21-row ledger: E6_V2_MAIN_CELL_LEDGER_21.csv
- Six-cell primary availability: E6_V2_AVAILABILITY.csv
- Tuning-only artifacts: E6_V2_PARTIAL_TUNING_EVIDENCE.csv and E6_V2_TUNING_WEIGHT_STABILITY.csv
- Superseded v1 gate history: E6_SUPERSEDED_AVAILABILITY_GATE_HISTORY.csv
- Corrected status prose: E6_V2_STATUS.md
- Export receipt SHA256: 672406b56c9ae4c24997e3f0a49466515b6cb21bc8fef7022f679f00dcb82e80
- Corrected status file SHA256: ba42d3e600de2b236a2f477b6701fe7330e213a0744197d6e91b1135ef460bbf

This E6 report is an interim descriptive output, not overall project completion. Global calibration-q replay and final project packaging remain pending.

