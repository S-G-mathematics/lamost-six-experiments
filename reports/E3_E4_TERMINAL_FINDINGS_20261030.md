# E3 and E4 terminal findings (descriptive, interim)

Observed 2026-10-30T02:23:08.412852+00:00. E3 pairs in this correction were recomputed from read-only SQLite terminal records and successful cells evaluation.json/validation.json files. No model load, prediction-array read, fitting, test inference, bootstrap, significance testing, or test-selected ranking was performed.

## Correction to prior E3 pairing summary

This version supersedes the E3 pair counts and deltas in the prior 8a8c483 snapshot. That report and its supporting summary remain preserved under reports/history as explicitly superseded. The old E3_SHARED_REAL_PAIRED.csv remains unchanged as historical evidence, but it left 37 currently validated pairs blank. The correction joins each preplanned candidate and baseline by repetition and learner; generator-specific comparisons also match the same generator. Every successful evaluation is bound to the registry task key, single declared fit dependency, fit-result pipeline SHA, evaluation JSON digest in validation.json, 7-class confusion matrix, probability score, 10,000 calibration rows and 500,000 test rows. For each repetition, tuning and calibration role-ID hashes are constant across the E3 cell ledger.

The 69 E3 evaluations comprise 64 successful, 3 scientific failures and 2 unavailable dependencies. Each comparison had 45 preplanned pair slots. Current matched counts are:

| Comparison | Matched pairs / 45 | Matched strata n=3 / 2 / 1 / 0 |
|---|---:|---:|
| direct_bayes minus real_only | 36 | 12 / 0 / 0 / 3 |
| direct_bayes minus synthetic_only | 35 | 11 / 1 / 0 / 3 |
| synthetic_only minus real_only | 43 | 13 / 2 / 0 / 0 |

Synthetic-only minus real-only: 43/45 matched pairs; balanced-accuracy deltas -0.18721 to +0.01994, coverage deltas -0.00814 to +0.00748, and mean-set-size deltas -0.05681 to +0.92651.
Direct Bayes minus real-only: 36/45 pairs; balanced-accuracy deltas -0.19583 to +0.15564, coverage deltas -0.00874 to +0.00825. Direct Bayes minus synthetic-only has 35/45 pairs, with balanced-accuracy deltas -0.02460 to +0.16697. These condition-specific ranges do not establish a universal route winner.

Across generator/learner route groups, the verified direct, synthetic-only and real-only group means range respectively: balanced accuracy 0.5792-0.8056, 0.4867-0.7722, 0.6512-0.7615; coverage 0.8969-0.8996, 0.8947-0.9005, 0.8978-0.9006; set size 1.4870-2.5387, 1.5267-2.5163, 1.5610-1.7704. These are ranges across separate groups, not pooled averages.
Per-class coverage among the 64 successful E3 evaluations ranges 0.009-0.988; overall coverage near 0.90 is not a guarantee of classwise 90% coverage.

## Corrected E3 figures

The E3-only refreshed figures are in [E3_FIGURE_REFRESH_20261030T021523Z](E3_FIGURE_REFRESH_20261030T021523Z/). They use the validated E3 ledger and reporting plot function. For synthetic GMM/random forest, repetitions 1 and 3 succeeded and repetition 2 is unavailable, so each route-triple figure uses n=2. The prior PNGs remain unchanged. Ledger SHA-256 d5c9c918f031a0121a8be07e0771a9000ce8d244c0c7881d46be8629ae8b55c2; plotting-source SHA-256 d7f8d302fad59310f4c101b27a23575a66012b612f376df79fb277b02915cf19.

## E4 target/severity/treatment results

E4 remains 1,632 successful, 71 scientific failures, 3 unavailable and 67 user-stopped out of 1,773; user-stopped rows are not failures. This uses the latest 2026-10-29 23:19:28 UTC snapshot. Comparisons preserve method, target class, severity, treatment and comparator.

| Comparison | Planned strata | Matched repetitions by stratum (n=3 / 2 / 1 / 0) | Matched pairs |
| altered_direct_minus_unchanged_control | 238 | 194 / 2 / 14 / 28 | 600 |
| treatment_minus_unchanged_control | 336 | 297 / 39 / 0 / 0 | 969 |
| treatment_minus_untreated_altered | 336 | 297 / 39 / 0 / 0 | 969 |

Altered direct versus unchanged control has 238 method/target/severity strata and 600 matched pairs (194 strata n=3, 2 n=2, 14 n=1, 28 n=0). Across available stratum means, balanced-accuracy deltas range -0.1106 to +0.0376 and target-class recall deltas -0.8668 to +0.0007.

Treatment versus unchanged control has 336 strata and 969 matched pairs (297 n=3, 39 n=2); stratum-mean balanced-accuracy deltas range -0.1710 to +0.0137 and target-recall deltas -0.7733 to +0.0885. Treatment versus untreated altered control has the same 336 strata and 969 pairs; balanced-accuracy deltas range -0.1519 to +0.0811 and target-recall deltas -0.0966 to +0.8987. These are not pooled effects or significance claims. Sample SD is undefined for n=1.

## Source binding and limits

E3 read-only registry projection (69 task rows) SHA-256 6f82c637a224166989cb20d9c2df144ae71d841d666c152a314611293977f1a3; E3 cell ledger SHA-256 d5c9c918f031a0121a8be07e0771a9000ce8d244c0c7881d46be8629ae8b55c2; old incomplete pair table SHA-256 bcb3d8dc46cfaff8598f4aa66b5d5512b32ea29d798fddace4ae868ddac20e9a, historical matched counts {'direct_bayes minus real_only': 27, 'synthetic_only minus real_only': 25, 'direct_bayes minus synthetic_only': 25}. The recomputed table has {'direct_bayes minus real_only': 36, 'synthetic_only minus real_only': 43, 'direct_bayes minus synthetic_only': 35}; 37 previous blank rows are now matched and 0 prior BA deltas differ.
Current matched-pair details: [E3_CURRENT_MATCHED_PAIRS_20261030.csv](E3_CURRENT_MATCHED_PAIRS_20261030.csv), SHA-256 aef7321d362b234a49cce4db69193790ba55a1897ab79516bcd2e21a8be6e989. E3/E4 denominator and range table: [E3_E4_TERMINAL_FINDINGS_20261030.csv](E3_E4_TERMINAL_FINDINGS_20261030.csv), SHA-256 34597c6cc701001f244d0055294a620123902650e46fa11072bcef78436e94f5. The E4 manifest SHA-256 is c6f7cecf25d55e1399b0cbb31d20c5acc6ba36b3e21ee3449e6fa45a7da9d3a4 and the paired summary SHA-256 is 61180bc37a36c3c618fd1597fa092c0fc83476baf7fa653b790d5aea725dd9e8.

Full final artifact validation and calibration-quantile replay remain pending. This note is an interim E3/E4 correction and does not change E1, E2, E5 or E6.
