# Experiment 6: generative posterior ensembles - final descriptive report

Registry snapshot: 2026-10-25T17:34:13.619761+00:00; assembled 2026-10-25T17:34:26Z UTC (2026-10-25T23:04:26+05:30 Asia/Kolkata).
This is an E6 accounting and descriptive report. All 21 planned cells are terminal, but the primary ensemble comparison has no valid ensemble scores.

## Outcome coverage

| Cell group | Planned | Successful | Unavailable dependency | Primary attempts |
|---|---:|---:|---:|---:|
| Individual member references | 15 | 12 | 3 | n/a |
| Equal and learned primary ensembles | 6 | 0 | 6 | 0 of 6 |
| Total | 21 | 12 | 9 | 0 of 6 |

All 15 selected generator pipelines exist and are recorded successful. Twelve reference evaluations are validated saved results: GMM, Gaussian copula, ARF and Chow-Liu, each at three repetitions. The three KDE references are unavailable because each E3 direct KDE evaluate phase timed out at the fixed 600-second limit. KDE fitting and generation succeeded in all three repetitions; this is not a fit failure or missing historical model.

Each primary ensemble requires all five declared member evaluation references. The three KDE references are unavailable, so all six equal/learned ensemble cells are unavailable dependencies. The declared-member gate was applied before any E6 ensemble attempt. There were zero ensemble attempts, posterior phases, weight searches, calibration/test predictions, or ensemble metric artifacts. Neither benefit nor lack of benefit can be concluded; no partial-member sensitivity is reported.

## Member pipeline provenance

| Family | Pipelines | Member evaluations | Actual n | Fit provenance | Evaluation source |
|---|---:|---:|---:|---|---|
| gmm | 3/3 | 3/3 | 3 | E2 reconstructed fit reused through E3; original E1 omitted | saved E3 direct evaluation reused by E6 alias |
| copula | 3/3 | 3/3 | 3 | E2 reconstructed fit reused through E3; original E1 omitted | saved E3 direct evaluation reused by E6 alias |
| arf | 3/3 | 3/3 | 3 | new E3 selected fit, separate from frozen E1 | saved E3 direct evaluation reused by E6 alias |
| kde | 3/3 | 0/3 | 0 | new E3 selected fit, separate from frozen E1 | E3 direct evaluation timed out at fixed 600s limit |
| chow_liu | 3/3 | 3/3 | 3 | E2 reconstructed fit reused through E3; original E1 omitted | saved E3 direct evaluation reused by E6 alias |

The nine GMM/copula/Chow-Liu pipelines are E2 reconstructions rather than recovered original E1 models. Matching roles, selected parameters, preprocessing, and reconstructed model identities were validated for reuse. GMM reconstruction gates reproduced the original saved E1 test balanced accuracy. Copula and Chow-Liu retain documented reconstruction accuracy mismatches; E3 reuse checks found their saved direct balanced accuracies match measured E2 reconstructed results. Six ARF/KDE pipelines are new E3 fits and do not replace frozen E1. Omitted historical E1 pipelines and per-test-row prediction arrays remain unavailable.

E6 member-reference cells alias saved E3 direct evaluation outcomes; no second E6 member-scoring pass occurred.

## Validated member metrics

Each available family has n=3 paired repetitions, a 500,000-row test cohort and 10,000 calibration rows. Means and sample SDs describe the three saved repetitions; they are not confidence intervals.

| Family | n | Balanced accuracy mean +/- SD | Coverage mean +/- SD | Set size mean +/- SD |
|---|---:|---:|---:|---:|
| gmm | 3 | 0.8056 +/- 0.0006 | 0.8996 +/- 0.0050 | 1.4870 +/- 0.0269 |
| copula | 3 | 0.5792 +/- 0.0115 | 0.8976 +/- 0.0046 | 2.3711 +/- 0.1265 |
| arf | 3 | 0.6461 +/- 0.0103 | 0.8969 +/- 0.0037 | 2.2784 +/- 0.3439 |
| kde | 0 | unavailable | unavailable | unavailable |
| chow_liu | 3 | 0.6118 +/- 0.0034 | 0.8987 +/- 0.0053 | 2.5387 +/- 0.1134 |

Per-repetition and seven-class metrics are in E6_MEMBER_PER_REPETITION.csv. The class table averages each saved class metric across the three repetitions.

| Family | Class | Test n | Recall | Coverage | Mean set size |
|---|---|---:|---:|---:|---:|
| gmm | A | 28207 | 0.6835 | 0.7856 | 1.3149 |
| gmm | F | 111549 | 0.6205 | 0.8423 | 1.6183 |
| gmm | G | 194818 | 0.7631 | 0.9366 | 1.6260 |
| gmm | K | 107016 | 0.7717 | 0.8913 | 1.3412 |
| gmm | M | 43202 | 0.9126 | 0.9550 | 1.1380 |
| gmm | GALAXY | 7680 | 0.9523 | 0.9602 | 1.0520 |
| gmm | QSO | 7528 | 0.9351 | 0.9556 | 1.1072 |
| copula | A | 28207 | 0.0825 | 0.4973 | 2.7580 |
| copula | F | 111549 | 0.2824 | 0.9213 | 2.5083 |
| copula | G | 194818 | 0.6500 | 0.9525 | 2.4979 |
| copula | K | 107016 | 0.5686 | 0.9034 | 2.3080 |
| copula | M | 43202 | 0.6287 | 0.8188 | 1.7519 |
| copula | GALAXY | 7680 | 0.9587 | 0.9658 | 1.0720 |
| copula | QSO | 7528 | 0.8835 | 0.9253 | 1.3837 |
| arf | A | 28207 | 0.2405 | 0.5178 | 2.4508 |
| arf | F | 111549 | 0.3687 | 0.8481 | 2.3046 |
| arf | G | 194818 | 0.5997 | 0.9381 | 2.4134 |
| arf | K | 107016 | 0.6616 | 0.9414 | 2.2792 |
| arf | M | 43202 | 0.8084 | 0.9560 | 1.8321 |
| arf | GALAXY | 7680 | 0.9435 | 0.9616 | 1.1715 |
| arf | QSO | 7528 | 0.9002 | 0.9367 | 1.4304 |
| chow_liu | A | 28207 | 0.1726 | 0.6131 | 2.5078 |
| chow_liu | F | 111549 | 0.4428 | 0.8776 | 2.7029 |
| chow_liu | G | 194818 | 0.4526 | 0.9187 | 2.7514 |
| chow_liu | K | 107016 | 0.5915 | 0.9230 | 2.5383 |
| chow_liu | M | 43202 | 0.8477 | 0.9749 | 1.5689 |
| chow_liu | GALAXY | 7680 | 0.9074 | 0.9513 | 1.3513 |
| chow_liu | QSO | 7528 | 0.8681 | 0.9271 | 1.4979 |

Descriptively, GMM had the largest observed mean balanced accuracy among the four families with complete saved evaluations: 0.8056 (SD 0.0006), coverage 0.8996, set size 1.4870. Copula values were 0.5792, 0.8976, 2.3711; ARF 0.6461, 0.8969, 2.2784; Chow-Liu 0.6118, 0.8987, 2.5387. These are member results, not ensemble comparisons or test-selected winners. No significance or universal ranking claim is made. Per-class coverage varies; see class metrics.

Conformal outputs use the saved probability-score policy (1 minus class posterior), 10,000 calibration rows and saved finite-sample thresholds at nominal 90% coverage. Thresholds were not recomputed because calibration scores are absent. Calibration/test fallback counts are retained in the per-repetition CSV.

## Frozen conformal rule and classwise coverage

The frozen evaluation uses probability nonconformity 1 - p_true. The calibration threshold is the finite-sample order statistic at k = ceil((n + 1) × 0.90), selected as the kth smallest score by numpy.partition; if k exceeds n, threshold is infinity. With n=10,000, k=9,001. A test class is included when 1 - p_class <= threshold; no label is forcibly inserted. No threshold was changed after test evaluation. Overall coverage near 90% does not imply 90% coverage for every class. Across three saved repetitions, class A mean coverage was GMM 0.7856, copula 0.4973, ARF 0.5178, and Chow–Liu 0.6131 (n=3 each).

The planned tuning-best-member comparator was not selected or evaluated because required member availability prevented the E6 posterior phase; neither ensemble weight search nor tuning-best selection ran.

## Data-only regeneration

From the extraction root run: `cd <extraction-root>; /usr/bin/python3 runtime_20261025/source/export_e6_descriptive.py --runtime runtime_20261025 --project project --output runtime_20261025/reports`. The exporter reads registry records, reviewed provenance templates and saved evaluation JSONs only; it performs descriptive table and summary generation only, with no new fitting, posterior generation, or calibration/test inference.

## Figure visual QA

The three published E6 figures passed root visual and semantic review at 2026-10-25T17:56:54Z. Receipt: `reports/engineering_audits/E6_FIGURE_VISUAL_QA_PASSED_20261025.json` (SHA-256 `def9a7e57f2d738a0d2affe338a43a11e4fc3b4cda73c6ab4d1dc56b3e26d05a`). The receipt binds the exact figure hashes recorded in E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json.

## Primary ensemble method and state

The frozen comparison specified equal weights (0.2 each) versus one global nonnegative simplex vector selected on tuning balanced accuracy. The planned learned search included equal weights, five simplex vertices, 1,000 seeded Dirichlet(1,...,1) candidates, refinement of the top ten by pairwise transfers 0.10, 0.05, 0.01, and a 2,000-candidate cap. Exact ties favored closeness to equal weights, then deterministic candidate order. Weights would freeze before calibration; averaged normalized posterior probabilities, not densities, feed the ensemble.

No search or ensemble evaluation ran. There are no E6 frozen weights, candidate ledger, ensemble evaluation JSON, or ensemble test outcomes. Existing E6_weights.csv, E6_candidate_ledger.csv, and E6_ENSEMBLE_MEMBER_PAIRED.csv contain planned/blank unavailable entries, not measured weights or effects.

All three KDE direct evaluations timed out during the fixed 600-second evaluate phase; their fits and generated datasets succeeded. Amendment e6_declared_member_gate_20261025 requires all five declared member evaluation references before any E6 posterior phase. It preserves the plan hash and original freeze timestamp and was applied before E6 ensemble attempts.

## Resources, figures, and limitations

The ARF/KDE E3 fits used the recorded 10 GiB worker limit, 600-second trials and fit/prediction phases, 30-second termination grace, one nested native thread, and 50,000-row prediction chunks. E6 performed no fit work. Operational scheduling began with a two-worker cap, then explicit user authorization changed to adaptive CPU/RAM/storage admission; later queue packing prioritized admissible light work while retaining a heavy lane. Recorded policy reserves 6 GiB for host/Harbor, 0.25 GiB for aliases, 10/2 GiB heavy/light admission reservations, 2 CPU reserve cores, and nice 10 for new workers. These changes did not extend scientific limits. No ensemble cost or RSS was measured.

Existing figures: E6_balanced_accuracy_member_ensemble.png, E6_coverage_member_ensemble.png, E6_set_size_member_ensemble.png. Their denominator is 21 planned E6 cells: 12 have member metrics, 9 have no score (3 KDE aliases and 6 primary ensembles). No ensemble metric point exists.

- E1/E2 test results were observed before later studies. E6 member metrics reuse E3 results on the fixed cohort; these are not prospective replications. No E6 ensemble test result exists.
- E2-sourced models are reconstructions, not historical original E1 pipelines. Missing historical pipelines and per-test-row arrays were not recovered.
- Three KDE comparisons and six ensemble cases have no metrics; available-only means retain survivorship limits.
- Bootstrap remains dropped. No bootstrap intervals or significance tests are reported.
- Auxiliary E1 tuning-history discrepancies remain disclosed in E1/E2; no missing history was fabricated.
- All E6 cells are accounted for, but primary ensemble evaluation is unavailable. This does not complete the six-experiment project.

## Reproduction and evidence

This report was assembled from registry records, E6 task/manifest data and saved alias evaluation JSONs. No model load, fit, posterior generation, calibration/test inference, bootstrap, or queue action occurred.

- E6_FINAL_CELL_LEDGER_21.csv: all 21 terminal outcomes.
- E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv: pipelines, evaluations, aliases and ensemble availability.
- E6_MEMBER_PER_REPETITION.csv: per-repetition overall and seven-class metrics.
- E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json: hashes, timestamps and counts.

Independent evaluation-only audit generated 2026-10-25T17:25:13.179443+00:00: 284 validated successful outcomes, 104 aliases, 0 blocking issues. It audits saved outputs and aliases, not new inference or threshold calculation.
