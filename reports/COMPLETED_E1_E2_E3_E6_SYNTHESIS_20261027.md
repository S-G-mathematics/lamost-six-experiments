# Cross-experiment synthesis: E1, E2, E3 and E6

Corrected and revalidated at 2026-10-27T09:33:19+00:00 UTC on the existing EC2 from saved validated reports, ledgers, and summary tables. This is a synthesis for final-report use, not a declaration that the six-experiment project is complete. E4 and E5 remain in progress; global calibration-quantile replay and final project validation are pending.

## Scope and interpretation

The four experiments answer different questions. E1 compares predictive procedures across sample budgets. E2 measures generator fidelity beside classification performance from each original or reconstructed fit. E3 compares direct generator classification with discriminative learners trained on synthetic or real data. E6 has member references, but no ensemble scores. Predictive performance, fidelity, resource feasibility, and artifact reproducibility are reported separately.

E1/E2 test outcomes were observed before E3; E6 reuses E3 direct member evaluations. These are not prospective untouched test measurements. This synthesis reads saved report metadata and aggregate tables only; it does not load models, inspect per-row prediction arrays, fit, predict, or select methods. Bootstrap remains dropped. No statistical significance or universal method claim is made.

The reports use the cleaned LAMOST DR10 v2 baseline, seven labels (A, F, G, K, M, GALAXY, QSO), six photometric predictors, and a fixed 500,000-row test cohort. Role separation and the nominal 90% conformal target are preserved in their source analyses.

## Outcome coverage

| Experiment / group | Planned | Successful | Failed | Unsupported | Unavailable | User-stopped | Not attempted | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 | 0 |
| E1 recovery supplement, separate | 91 | 24 | 10 | 0 | 0 | 2 | 55 | 0 |
| E2 primary five-generator grid | 150 | 108 | 0 | 0 | 42 | 0 | 0 | 0 |
| E2 classical reference set | 120 | 120 | 0 | 0 | 0 | 0 | 0 | 0 |
| E3 evaluation grid | 69 | 64 | 3 | 0 | 2 | 0 | 0 | 0 |
| E6 member references | 15 | 12 | 0 | 0 | 3 | 0 | 0 | 0 |
| E6 primary ensembles | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |

*Recovery is stopped and terminal at the user decision: 2 user-stopped partial cells and 55 not attempted. These are not scientific failures and are not part of frozen E1.

E1's 81 failed cells comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained started. The separate 10 unsupported cases are not failures. The 100,000-row E1 budget had 67 successful of 85 planned and 18 failures. The complete frozen cell ledger and method-budget table retain actual repetition counts by method and budget.

Frozen E1 terminal outcomes by budget (all 85 cells per budget):

| Budget | Planned | Successful | Failed | Unsupported |
|---:|---:|---:|---:|---:|
| 100 | 85 | 80 | 0 | 5 |
| 300 | 85 | 80 | 0 | 5 |
| 1,000 | 85 | 84 | 1 | 0 |
| 3,000 | 85 | 82 | 3 | 0 |
| 10,000 | 85 | 82 | 3 | 0 |
| 30,000 | 85 | 74 | 11 | 0 |
| 100,000 | 85 | 67 | 18 | 0 |
| 300,000 | 85 | 65 | 20 | 0 |
| 1,000,000 | 85 | 60 | 25 | 0 |


## E1: frozen benchmark and stopped supplement

Frozen E1 remains terminal at 765/765: 674 successful, 81 failed, and 10 unsupported. The 81 failures are 55 resource and 26 supervisor-terminal outcomes. Method-budget means are conditional on successful repetitions and should be read with their actual denominator; this synthesis does not average across heterogeneous methods. See E1_frozen_cells_765.csv and E1_method_budget_summary_153.csv for the complete outcomes and actual repetition counts.

The recovery supplement stopped early at the user's request: 24 successful retries, 10 retry failures, 2 user-stopped partials, and 55 not attempted. Its later 600-second/10-GiB settings and outcomes do not replace frozen E1. The compact migration omitted some historical fitted pipelines and per-test-row prediction arrays; a subset of original fits remains available, while omitted artifacts were not universally restored. E2/E3/E6 provenance labels identify original, reconstructed, reused, and new fits where relevant. Seven auxiliary tuning-history discrepancies remain documented for 10k rep3 GMM, 30k rep2 CART, and 30k rep3 linear SVM. Timing varies with host and concurrent load.

## E2: generator fidelity and classification

The primary grid evaluated 108/150 paired cells; 42 were unavailable because the matching frozen E1 selected-model dependencies had failed. The separate classical reference set evaluated 120/120 and is not part of the five-family primary comparison. The evaluated primary set includes 19 original saved fits and 89 reconstructed fits.

The 31 reconstruction accuracy differences remain visible; the maximum absolute difference was 0.000031739351391335546. Each reconstructed model is paired with its own measured classification score. Of 185 reconstructed fits across primary and classical groups, 154 reproduced saved E1 balanced accuracy within 1e-10 and 31 differed. E1 values were not overwritten.

All 1,596 class Quality Reports are retained; 210 have low precision (<20 diagnostic rows) and remain in the equal seven-class average. The integrity audit checked 228 evaluated cells and recorded zero integrity errors. Four of 30 budget/repetition strata had full five-family coverage: 3,000/repetition 3, rho=0.700; 3,000/repetition 5, rho=0.100; 10,000/repetition 1, rho=0.300; and 10,000/repetition 2, rho=0.700. These within-stratum correlations are descriptive; the other 26 strata are incomplete. Four strata do not establish a general fidelity-classification relationship.

## E3: direct Bayes and discriminative routes

E3 accounted for all 69 planned evaluation cells: 64 successful, 3 direct-KDE evaluation timeouts at the fixed 600-second phase limit, and 2 unavailable downstream RF dependencies after fits exceeded the 10-GiB cap. All five generator families had selected fits and all 15 synthetic datasets were generated. Direct KDE scored 0/3 because evaluation timed out, not because fitting or generation failed. Route totals: direct 12/15, synthetic-only 43/45, shared real-only 9/9.

Direct Bayes mean balanced accuracy / marginal coverage / mean set size (n=3 each): GMM 0.8056 / 0.8996 / 1.4870; copula 0.5792 / 0.8976 / 2.3711; ARF 0.6461 / 0.8969 / 2.2784; Chow-Liu 0.6118 / 0.8987 / 2.5387. KDE has no valid score mean.

Synthetic-minus-real paired balanced-accuracy changes varied by generator and learner. GMM changes were +0.0109 for random forest (n=2), -0.0076 for logistic regression (n=3), and +0.0149 for histogram gradient boosting (n=3). Copula changes were -0.0859, -0.1727, and -0.1648 for those learners (n=3 each). These are matched descriptive changes among successful pairs. They do not support a universal route claim. The E3 route table and 69-cell ledger retain individual repetitions, per-class scores, coverage, set size, and resource costs.

Nine GMM/copula/Chow-Liu fits reused matching E2 reconstructed selected pipelines after role, selection, preprocessing, seed, and fitted-component checks. Six ARF/KDE fits were new E3 dependencies. These do not repair frozen E1 or restore omitted historical E1 pipelines.

## E6: members available; ensembles unavailable

All 15 selected generator pipelines exist, but only 12/15 direct member evaluation references are valid: GMM, copula, ARF, and Chow-Liu at three repetitions each. Three KDE references are unavailable because their E3 evaluation phases timed out at 600 seconds; KDE fitting and generation succeeded.

Each primary E6 ensemble requires all five member references. All six equal/learned ensemble cells were gated unavailable before an ensemble attempt. There were zero posterior phases, weight searches, tuning-best-member comparisons, or ensemble test metrics. No claim about benefit or lack of benefit from ensembling is possible.

Available member means (n=3) are reused E3 outcomes: GMM BA/coverage/set size 0.8056/0.8996/1.4870; copula 0.5792/0.8976/2.3711; ARF 0.6461/0.8969/2.2784; Chow-Liu 0.6118/0.8987/2.5387. These are member metrics, not ensemble metrics. Class-A coverage means were 0.7856, 0.4973, 0.5178, and 0.6131 respectively (n=3 each). Marginal coverage near 90% does not imply classwise coverage near 90%.

## Limitations and provenance

Conformal rules, calibration counts, fallback information, and saved thresholds remain in the source experiment reports. Thresholds were not changed after test evaluation. E2 reconstruction differences, low-precision flags, original/reconstructed provenance, and incomplete primary coverage remain visible. E3/E6 results are conditional on available outcomes; E6 reuses E3 and is not an independent replication. Resource feasibility is not an accuracy score. Timing includes supervised phase work and I/O and depends on hardware and concurrent load.

E4 and E5 remain ongoing. Global calibration-quantile replay, final cross-experiment validation, and the full project archive remain pending. This document does not declare the six-experiment project complete.

## Reproduction

Source paths, byte sizes, and SHA-256 hashes are listed in COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027_INPUTS.json. The supporting CSV gives denominators and available saved means; original ledgers retain repetition-level results. E3/E6 reports include their data-only export commands. No model load or per-row inference is required to reproduce this synthesis.
