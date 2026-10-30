# E3 and E4 terminal findings (descriptive, interim)

Observed 2026-10-30T02:10:15.742120+00:00. This note uses existing validated E3/E4 metric tables only. No model loading, prediction-array reading, fitting, new test inference, bootstrap, significance test, or test-selected ranking was performed.

## Status and denominators

| Experiment | Planned evaluations | Successful | Scientific failure | Unavailable | User-stopped | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |

E4 uses the applied single-evaluation scope amendment. Its 67 user-stopped rows are not failures and are excluded from metric summaries. These counts agree with the latest E4 terminal ledger/manifest (23:19:28 UTC, 2026-10-29) and current registry observation (02:01 UTC, 2026-10-30).

## E3 route and paired findings

Route group means are over successful repetitions only. Direct Bayes has 12/15 successful evaluations: group-mean balanced accuracy ranges 0.5792–0.8056, coverage 0.8969–0.8996, mean set size 1.4870–2.5387. Synthetic learners have 43/45 successful evaluations: corresponding ranges are 0.4867–0.7722, 0.8947–0.9005, and 1.5267–2.5163. Real-only learners have 9/9: group means range 0.6512–0.7615 in balanced accuracy, 0.8978–0.9006 in coverage, and 1.5610–1.7704 in set size. These ranges retain separate generator/learner strata; they are not pooled estimates.

Matched differences require the same generator, learner and repetition; 45 pair slots were planned per contrast. Synthetic-only minus real-only has 25 matched repetition pairs across 15 strata (8 strata n=3, 1 n=1, 6 n=0). Per-repetition balanced-accuracy differences range -0.1872 to +0.0199, coverage differences -0.00814 to +0.00748, and set-size differences -0.0568 to +0.9265. Direct Bayes minus real-only has 27/45 matched pairs (9 strata n=3 and 6 n=0); balanced-accuracy differences range -0.1958 to +0.1556, coverage -0.00874 to +0.00825. The ranges show heterogeneity rather than a universal route winner.

Across the 64 successful E3 cells, class-specific coverage values in the saved ledger range 0.009–0.988. Overall coverage near 0.90 does not imply 90% coverage for every class. The frozen finite-sample conformal rule is unchanged; no new threshold or calibration claim is made.

## E4 target/severity/treatment findings

The paired summaries preserve method, target class, severity ratio, treatment and comparator. Values below are ranges across available stratum means, with repetitions paired within each stratum; unlike strata are not averaged together.

| Comparison | Planned strata | Matched repetitions by stratum (n=3 / 2 / 1 / 0) | Matched repetition pairs |
| altered_direct_minus_unchanged_control | 238 | 194 / 2 / 14 / 28 | 600 |
| treatment_minus_unchanged_control | 336 | 297 / 39 / 0 / 0 | 969 |
| treatment_minus_untreated_altered | 336 | 297 / 39 / 0 / 0 | 969 |

Altered direct versus unchanged control: 238 target/severity/method strata, with 600 matched repetitions (194 strata n=3; 2 n=2; 14 n=1; 28 n=0). Available stratum-mean balanced-accuracy changes range -0.1106 to +0.0376; target-class recall changes range -0.8668 to +0.0007.

Restoration treatment versus unchanged control: 336 strata and 969 matched repetitions (297 n=3; 39 n=2). Stratum-mean balanced-accuracy changes range -0.1710 to +0.0137; target recall changes range -0.7733 to +0.0885. Treatment versus untreated altered control: also 336 strata and 969 matched repetitions; balanced-accuracy changes range -0.1519 to +0.0811, target-recall changes -0.0966 to +0.8987. The broad target-recall ranges show why target-level results must remain visible beside overall balanced accuracy, coverage and set size.

Unmatched strata remain explicit in the full paired tables. For n=1, sample SD is undefined. No bootstrap interval, significance claim or universal restoration benefit is inferred.

E3 sources: [route repetitions](E3_FINAL_ROUTE_REPETITIONS.csv), SHA-256 17d5db807bd77fe5e559b6ca433c094a94dd17946d91ec70b60a3679eaabc9e2; [matched route pairs](E3_SHARED_REAL_PAIRED.csv), SHA-256 bcb3d8dc46cfaff8598f4aa66b5d5512b32ea29d798fddace4ae868ddac20e9a; [cell ledger](E3_FINAL_CELL_LEDGER_69.csv).

E4 sources: [latest snapshot manifest](E4_DESCRIPTIVE_REFRESH_20261029T231928Z/MANIFEST.json), SHA-256 c6f7cecf25d55e1399b0cbb31d20c5acc6ba36b3e21ee3449e6fa45a7da9d3a4; [paired summary](E4_DESCRIPTIVE_REFRESH_20261029T231928Z/E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv), SHA-256 61180bc37a36c3c618fd1597fa092c0fc83476baf7fa653b790d5aea725dd9e8; [cell ledger](E4_DESCRIPTIVE_REFRESH_20261029T231928Z/E4_CURRENT_CELL_LEDGER.csv), SHA-256 b7a796acd8c6cb89927efd003d34108d7d90a3bf3b5235ac166fe35b8f3b6fc4. E4 manifest states no bootstrap/significance, no model opening and no test-array reading.

Supporting denominator/range table [E3_E4_TERMINAL_FINDINGS_20261030.csv](E3_E4_TERMINAL_FINDINGS_20261030.csv), SHA-256 48c03625da6b838924941d364c5b5c879c2feac3f69199ce9e11becec3de668c, binds each row to its source-table hash.

Full final artifact validation and calibration-quantile replay remain pending. This descriptive note does not change the E1/E2 records and is not the final six-experiment report.
