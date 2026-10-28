# Experiment 4 direct-kernel block - descriptive interim report

Block scope: direct RBF-SVM and KDE across one unchanged control plus 14 altered fitting cohorts (7 targets x half-share/one-tenth-share) for each of 3 repetitions. This block is not the full E4 analysis. Snapshot assembled from validated registry/evaluation records on EC2. No fit, model load, prediction, or new evaluation was performed for this report.

## Planned case coverage

| Method | Planned | Successful evaluations | Scientific failures | Unavailable dependencies | Selected models available |
|---|---:|---:|---:|---:|---:|
| RBF-SVM | 45 | 18 | 27 | 0 | 45/45 |
| KDE | 45 | 0 | 42 | 3 | 45/45 |

RBF-SVM has 18 valid evaluations and 27 terminal scientific failures. All 45 selected fit dependencies completed successfully and the selected pipeline artifacts are present. KDE has 42 successful altered-condition fits, but all 42 altered-condition evaluations ended in terminal evaluate-phase timeouts. Its 3 unchanged-control rows are aliases to E3 direct-KDE evaluation results and are unavailable because the E3 evaluations failed; their KDE selected model fits/generation had succeeded. Thus the 45 KDE model references are available while 0/45 KDE block evaluation outcomes are successful. A missing model is not the cause of the KDE availability gap.

All 27 RBF-SVM and 42 KDE altered evaluation failures are recorded as evaluate-phase timeouts under the 600-second per-phase limit. Observed elapsed times are censored at the deadline and are not reported as completed inference costs. The 3 KDE control aliases cite upstream E3 direct-KDE scientific failures. Failure and unavailable cases have no fabricated metric values.

## RBF-SVM successful metrics by every planned condition

Means below are conditional on successful evaluations. n is the number of valid repetitions out of 3; sample SD is in the machine-readable summary. Empty cells indicate no valid evaluation, not zero performance. No RBF-SVM control evaluation succeeded, so there are no matched altered-minus-control pairs and no estimated treatment effects for this method.

| Condition | Success n/3 | Failure | BA mean | Coverage mean | Mean set size | Target recall mean |
|---|---:|---:|---:|---:|---:|---:|
| control | 0/3 | 3 |  |  |  |  |
| A_half | 0/3 | 3 |  |  |  |  |
| A_tenth | 2/3 | 1 | 0.7411 | 0.9009 | 1.6907 | 0.1877 |
| F_half | 2/3 | 1 | 0.7684 | 0.8967 | 1.6734 | 0.2311 |
| F_tenth | 3/3 | 0 | 0.7500 | 0.8993 | 2.2503 | 0.0002 |
| G_half | 3/3 | 0 | 0.7939 | 0.8983 | 1.6456 | 0.4758 |
| G_tenth | 3/3 | 0 | 0.7469 | 0.8982 | 2.5652 | 0.0003 |
| K_half | 0/3 | 3 |  |  |  |  |
| K_tenth | 2/3 | 1 | 0.7503 | 0.8981 | 1.7903 | 0.3270 |
| M_half | 1/3 | 2 | 0.7924 | 0.9012 | 1.6192 | 0.8614 |
| M_tenth | 0/3 | 3 |  |  |  |  |
| GALAXY_half | 1/3 | 2 | 0.7961 | 0.9016 | 1.5983 | 0.9421 |
| GALAXY_tenth | 0/3 | 3 |  |  |  |  |
| QSO_half | 0/3 | 3 |  |  |  |  |
| QSO_tenth | 1/3 | 2 | 0.7520 | 0.9020 | 1.6249 | 0.5654 |

The KDE condition rows all have n=0 valid evaluations. Its cell-level outcomes and dependency reasons are retained in E4_DIRECT_KERNEL_90_OUTCOMES.csv; no KDE performance means are shown. Per-class values are available only for the 18 valid RBF-SVM evaluations (126 class-metric rows). Classwise paired-difference rows include every planned target/severity/repetition/class combination; values are blank where a valid matched control is absent.

## Model selection and resource record

Model identities and fit_result hashes, pipeline digests, recorded fit timing, parameter selections, and selection metadata are in E4_DIRECT_KERNEL_FIT_PROVENANCE.csv. E4_DIRECT_KERNEL_RESOURCE_POLICY.csv includes the evaluation/alias records and all 87 distinct direct fit task records (45 RBF-SVM and 42 altered KDE). They were checked from small JSON metadata only; model binaries were not loaded. Successful RBF-SVM evaluations use native margin scoring (`score_kind=margin`, `nonconformity_rule=negative_margin`, `prediction_rule=argmax_class_score`). Numeric margin thresholds are not compared across methods. KDE has no valid block evaluation score. The global E4 calibration-quantile replay remains pending; this report uses only saved validated evaluation metrics and does not recalibrate.

The task records retain a 10 GiB worker memory limit and a 600-second phase timeout. Admission reservations are scheduling estimates: the recorded evaluation reservation was 3 GiB for the 45 RBF-SVM cells and 2 GiB for the 42 KDE altered cells; these reservations are not alternative hard memory limits. The 3 KDE control aliases have no E4 worker reservation because they reuse E3 evaluation outcomes.

Recorded successful model-fit seconds are phase measurements. Timeout elapsed values are censored at the deadline. Queue delay and interrupted/invalid attempt overhead are not added to final fit seconds. The rep-3 RBF-SVM K_half fit had a prior operationally invalid/interrupted attempt preserved separately. Its final selected fit has five successful trial slots, 144.321704 seconds recorded fit_seconds and 145.613910 seconds supervised final-fit phase time; the subsequent evaluation timed out after 600.267484 seconds. The evidence is separately bound in E4_DIRECT_KERNEL_KHALF_RECOVERY_CONTEXT.csv to root receipt `BOUNDED_OPERATIONAL_RECOVERY_FINAL_OUTCOMES_20261027.json` (SHA-256 `21a22e1fb71d0dbaa3ce71c372289396661f06da5533d761e56231826907aacc`). The timeout is a terminal evaluation failure, not an accuracy result or completed 600-second inference cost.

## Interpretation and limits

The 18 successful RBF-SVM evaluations are a conditional subset; their performance does not establish a general advantage and can reflect survivorship. No matched comparison to an unchanged RBF-SVM control is estimable because all three RBF-SVM control evaluations timed out. The KDE model artifacts are available, but the 600-second full-cohort evaluation phase was infeasible for all 42 altered cases, while the 3 clean evaluation aliases inherit E3 failures. This is a resource-feasibility result for the specified evaluation path, not evidence that the selected KDE model could never classify.

The block uses the fixed 500,000-row test cohort and 10,000-row calibration cohort, class order A, F, G, K, M, GALAXY, QSO. Test outcomes have been observed; they are not a prospective holdout for the remaining project. Per-repetition results and sample SDs are descriptive, not confidence intervals; there is no bootstrap or significance test. Timing is hardware- and admission-policy-dependent.

## Reproduction and outputs

Run on the existing EC2 from the runtime root: `nice -n 19 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 python3 reports/e4_direct_kernel_block_20261027/analyze_block.py`. This validates registry hashes and writes the complete ledger and descriptive tables without loading models or test-row arrays. The three PNGs are data-only figures generated by `render_plots.py` from the saved CSVs. Input JSON/registry hashes and output hashes are recorded in E4_DIRECT_KERNEL_EVIDENCE.json and the block receipt. This block does not imply final global E4 calibration-q or project validation.
