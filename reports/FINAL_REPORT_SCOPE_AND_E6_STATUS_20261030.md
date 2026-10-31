> **Superseded dated snapshot (2026-10-30T01:56Z).** E4/E5 counts and pending-case statements below predate later terminal outcomes. Its description of E6-v2 scope is historical; use [the current results guide](../docs/RESULTS_GUIDE.md), which records zero successful primary ensemble test evaluations and the current 2,823-case ledger. Original dated text is retained below.

# Final-report scope supplement: E6 outcomes and E4/E5 scope

Registry snapshot: 2026-10-30T01:56:16.520900+00:00. This is a descriptive supplement, not a final project report. E5 still has waiting cases; full calibration-quantile replay and final artifact audit remain outstanding. No bootstrap intervals or significance tests are claimed.

## E6 primary ensemble results

All 21 E6 scientific rows are terminal in this snapshot. The six primary ensemble rows produced no successful test evaluation. The fifteen member-reference rows are aliases to earlier E3 direct evaluations.

| E6 group | Planned | Successful test evaluations | Scientific failures | Unavailable dependencies |
|---|---:|---:|---:|---:|
| Equal-weight primary ensembles | 3 | 0 | 3 | 0 |
| Learned-weight primary ensembles | 3 | 0 | 0 | 3 |
| E3 member-reference aliases | 15 | 12 | 0 | 3 |

The three equal-weight primary failures were recorded as prediction timeouts during test prediction under the fixed policy. The three learned-weight primaries were unavailable because the corresponding shared E6 test-posterior phase ended under that same recorded timeout/RSS policy. No E6 primary task has a validated test metric or an ensemble test-comparison artifact. Missing ensemble metrics are unavailable; they are not zero performance or zero set size.

The three unavailable member-reference aliases are the E3 direct KDE evaluations that failed their test-evaluation phase. This is an evaluation-availability limitation, not evidence that the KDE fitted pipelines were absent. Model availability and completed test evaluation are separate questions.

The [21-row E6 ledger](E6_V2_INTERIM_20261027T204752Z/E6_V2_MAIN_CELL_LEDGER_21.csv), [availability table](E6_V2_INTERIM_20261027T204752Z/E6_V2_AVAILABILITY.csv), and [partial tuning evidence](E6_V2_INTERIM_20261027T204752Z/E6_V2_PARTIAL_TUNING_EVIDENCE.csv) retain the case-level evidence. The saved [weights](E6_weights.csv), [candidate ledger](E6_candidate_ledger.csv), and [tuning-weight stability table](E6_V2_INTERIM_20261027T204752Z/E6_V2_TUNING_WEIGHT_STABILITY.csv) are tuning-only evidence. They do not establish calibration/test performance, support test-based model selection, or yield an ensemble benefit estimate.

The six zero-attempt v1 dependency-gate decisions are preserved separately as superseded history. E6-v2 was amended after the first E3 KDE direct-evaluation timeout; do not present the v2 dependency rule as the original frozen executable semantics. No partial-member ensemble result replaces the primary analysis.

## E4/E5 scope and denominators

The original scientific-case denominators remain 1,773 for E4 and 960 for E5. The user-approved single-evaluation scope amendment selected one remaining evaluation for each unique condition and marked 67 E4 plus 101 E5 repetition rows as user-stopped. Previously completed repetitions and their outcomes were retained; the denominator was not reduced and user-stopped rows are not scientific failures.

| Experiment | Planned rows | Successful | Scientific failures | Unavailable | User-stopped | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 713 | 50 | 78 | 101 | 18 |

See the current [E4 case ledger](E4_DESCRIPTIVE_REFRESH_20261029T231928Z/E4_CURRENT_CELL_LEDGER.csv), [E5 status snapshot](E5_INCREMENTAL_VALIDATED_20261030T015616Z/E5_STATUS_COUNTS.csv), and the E5 incremental case and paired tables in [the current results batch](E5_INCREMENTAL_VALIDATED_20261030T015616Z/README.md). Paired effects are conditional on successful matched repetitions. A one-repetition pair is n=1/3 and has no defined sample SD; it is not a complete three-repetition estimate.

## New E5 validated-results increment

This snapshot includes 4 newly validated cases after the prior report: e5/rep_1/eval/synthetic/random_forest/label_noise_05_copula, e5/rep_1/eval/synthetic/random_forest/label_noise_10_arf, e5/rep_1/eval/synthetic/random_forest/label_noise_10_chow_liu, e5/rep_1/eval/synthetic/random_forest/label_noise_10_copula. The case-level same-repetition comparisons are in [E5_INCREMENTAL_VALIDATED_20261030T015616Z/E5_MATCHED_CLEAN_DIFFERENCES.csv](E5_INCREMENTAL_VALIDATED_20261030T015616Z/E5_MATCHED_CLEAN_DIFFERENCES.csv).

## E5 label-noise denominators and transitions

The [source-class rate table](E5_label_noise_source_class_rates.csv) uses each class's original fitting-cohort support before relabeling as the denominator. Its changed-label counts are source-class numerators. The [label transition table](label_transition_counts.csv) records original-to-observed label counts; off-diagonal transitions represent changed labels, while diagonal entries remain unchanged. Read these together with the [corruption realization summary](E5_corruption_realization_summary.csv).

The overall planned 5%, 10%, and 20% label-noise rates refer to affected fitting rows; realized source-class rates vary with class support. Only fitting rows are corrupted. Tuning, calibration, and test roles remain clean. Post-corruption label frequencies are not substituted for the original source-class denominators.

## Remaining report gates

The final aggregate report must refresh from a current coherent registry snapshot, integrate this E6 status and the E4/E5 scope accounting, and preserve all failure/unavailable/user-stopped outcomes. The independent [E1/E2 saved-table arithmetic audit](E1_E2_INDEPENDENT_DESCRIPTIVE_TABLE_AUDIT_20261030.json) passed with no issues; it is a table arithmetic check and does not certify native artifact coverage, full calibration-quantile replay, or overall project completion. Do not mark the project complete until those final validation and delivery gates are satisfied.
