# Experiment 3: final descriptive report

Observed: 2026-10-25 20:57:34 UTC (2026-10-26 02:27:34 IST).

**Status:** all 69 planned E3 evaluation cells are terminal and accounted for. This is the reviewed E3 descriptive report, not a declaration that the six-experiment project is complete. Root semantic and figure review passed for this E3 descriptive package; the full six-experiment project remains in progress. E1 and E2 records were not rewritten; no model was loaded, fitted, tuned, or predicted during this export.

## Question and frozen design

E3 compares direct Bayes classification from a fitted class-conditional generator, a discriminative learner trained on generated examples, and the same learner trained on real fitting data. The design was frozen before E3 test evaluation. It uses five generator families (GMM, Gaussian copula, ARF/FORDE, KDE, Chow-Liu), one 100,000-row development cohort in each of three repetitions (80,000 fit, 10,000 tune, 10,000 calibration), and the fixed 500,000-source test cohort. Six predictors and class order are recorded in the E3 manifest.

Each successful generator condition produced 400,000 synthetic fitting rows, five times its 80,000 real fitting rows, allocated by deterministic largest remainder from real-fit class proportions. All three synthetic learners in a generator/repetition use the same saved synthetic dataset. Synthetic-only means the learner is fit only on synthetic rows; the pipeline still learns the generator from real fit data and uses real tuning and calibration data. The real-only baselines are shared once per learner/repetition. No real-plus-synthetic arm was run.

Role IDs are the frozen E1 100k repetition memberships copied into the E3 manifest; fit, tune and calibration hashes are present for all three repetitions. Each successful evaluation used calibration n=10,000 and test n=500,000. The test cohort is fixed and its E1/E2 outcomes were already observed; these are not prospective untouched test results.

## Planned outcomes and coverage

| Planned E3 evaluation cells | Successful | Scientific failures | Unavailable dependency | Pending |
|---:|---:|---:|---:|---:|
| 69 | 64 | 3 | 2 | 0 |

| Route group | Planned | Successful | Failed | Unavailable |
|---|---:|---:|---:|---:|
| Direct Bayes (5 generators x 3 reps) | 15 | 12 | 3 | 0 |
| Synthetic-only (5 generators x 3 learners x 3 reps) | 45 | 43 | 0 | 2 |
| Real-only shared (3 learners x 3 reps) | 9 | 9 | 0 | 0 |

All 153 E3 planned tasks are terminal: 69 evaluation cases, 69 fit dependencies and 15 generation dependencies. Fit dependencies: 67 successful and 2 terminal 10 GiB process-tree-limit failures. All 15 generator datasets were successfully produced (6,000,000 generated rows counted across the 15 saved datasets; these are repeated draws from estimated distributions, not independent evidence about real-world diversity).

The three direct-KDE evaluation cases hit the declared 600-second phase limit; each saved no classification or conformal score. The two synthetic-RF cases unavailable by dependency are GMM/rep 2 and KDE/rep 2, because those learner fit dependencies exceeded the 10 GiB per-process-tree limit. These two unavailable evaluations are not new evaluation failures. Nothing here calls the two resource-limited fits an algorithmic or accuracy failure.

## Selected-generator provenance and reuse

Nine generator fits (GMM, copula and Chow-Liu, each across three repetitions) reused the corresponding E2 reconstructed selected pipelines, with matching role identities, preprocessing, fitted predictive components and selection parameters. The independent component audit reports all nine component sets equal. Pipeline file bytes differ because E3 adds/updates root provenance metadata; that does not indicate a fitted-component change. E2 and E3 balanced-accuracy floats match exactly for all nine direct comparisons. Exact score equality alone is not model or prediction identity; identity claims are grounded in the component audit, and these nine remain explicitly E2-reconstructed provenance.

The six ARF/KDE generator fits were new E3 dependencies fitted on their permitted 80,000 fitting rows with tuning-only selection. They do not repair or alter E1/E2 outcomes. All six selected generator fits completed. Their fit task and selected pipeline provenance is in the cell ledger and original registry. Two later downstream RF fits (GMM/KDE rep 2) exceeded the fixed 10 GiB limit.

## Descriptive results

| Direct Bayes generator | Successful reps / 3 | Mean balanced accuracy | Mean marginal coverage | Mean set size |
|---|---:|---:|---:|---:|
| gmm | 3/3 | 0.805554422524 | 0.899596666667 | 1.486998 |
| copula | 3/3 | 0.579192520472 | 0.897578666667 | 2.371102 |
| arf | 3/3 | 0.646093115827 | 0.896926 | 2.27841266667 |
| kde | 0/3 | NA | NA | NA |
| chow_liu | 3/3 | 0.61182401467 | 0.898708666667 | 2.53866933333 |

KDE direct has no valid mean because all three planned direct evaluation phases timed out. No score was imputed. The full per-repetition route table and 69-cell ledger preserve individual outcomes and denominators. Synthetic RF has 2/3 successful repetitions for GMM and KDE; it has 3/3 for copula, ARF and Chow-Liu. Logistic and histogram-gradient-boosting synthetic routes each have 3/3 for every family.

| Generator | Learner | Paired synthetic - real n | Mean delta balanced accuracy | Mean delta set size | Mean delta coverage |
|---|---|---:|---:|---:|---:|
| gmm | logistic | 3 | -0.00764104869723 | 0.0853213333333 | 0.000445333333333 |
| gmm | random_forest | 2 | 0.0108598549107 | -0.034127 | -0.00337 |
| gmm | hist_gb | 3 | 0.0148952818091 | -0.0343673333333 | 0.000446666666667 |
| copula | logistic | 3 | -0.085908758737 | 0.492241333333 | -0.00051 |
| copula | random_forest | 3 | -0.172726684167 | 0.748955333333 | -0.00255133333333 |
| copula | hist_gb | 3 | -0.164845332859 | 0.743380666667 | -0.000526666666667 |
| arf | logistic | 3 | -0.109758663818 | 0.715985333333 | 0.000300666666667 |
| arf | random_forest | 3 | -0.111779522199 | 0.584029333333 | -0.00402866666667 |
| arf | hist_gb | 3 | -0.112900108466 | 0.609888666667 | -0.00123666666667 |
| kde | logistic | 3 | -0.0455898123171 | 0.339321333333 | -0.000136666666667 |
| kde | random_forest | 2 | -0.0822453979056 | 0.30134 | -0.005114 |
| kde | hist_gb | 3 | -0.072203638893 | 0.306956 | -0.00308066666667 |
| chow_liu | logistic | 3 | -0.164493599831 | 0.745908666667 | -0.000802666666667 |
| chow_liu | random_forest | 3 | -0.137544568758 | 0.697079333333 | -8.93333333333e-05 |
| chow_liu | hist_gb | 3 | -0.124291068401 | 0.626593333333 | -7.2e-05 |

These are descriptive paired differences among repetitions where both routes completed; n ranges from 2 to 3. They do not estimate a population effect or support significance claims. Direct-versus-synthetic and direct-versus-real matched contrasts are also tabulated per generator/learner in the route CSV, with exact matched n.

Class-specific coverage can diverge sharply from marginal coverage. For Chow-Liu synthetic-only logistic, the three repetition-level marginal coverages are 0.8907, 0.9042 and 0.9004 (mean 0.8984), while class-A coverage is 0.0089, 0.0341 and 0.0334 (mean 0.0255); class-A recall is 0 in each. The full per-route/per-repetition ledger retains every class recall, coverage, set size and support. This example illustrates that marginal 90% coverage does not guarantee 90% classwise coverage.

## Conformal method and evaluation

The saved evaluations use probability nonconformity 1 - p_true, the finite-sample split-conformal order statistic k = ceil((n+1) x 0.90) = 9,001 for n=10,000, and include a label when 1 - p_class <= threshold. Thresholds were selected from the permitted calibration cohort and were not changed after test evaluation. No bootstrap or test-based method selection was performed. The ledger includes calibration n, threshold, fallback counts, 500,000-row confusion matrices and all per-class metrics.

## Resource and cost accounting

The cell ledger and route table report selected model-fit time, tuning-trial time, generator-fit time, generation time, calibration-phase wall time, test-inference-phase wall time, peak phase RSS and evaluation-worker wall time separately when recorded. Calibration and test inference measurements were recovered from exact engine-attempt phase receipts and cross-checked against `reports/costs.csv` by task key, engine attempt ID and stage. Phase wall durations include pipeline/model loading and result I/O; they are not pure kernel timings. Among the 69 planned evaluation cases, calibration phase time is recorded for 67 (64 scored cases plus the three direct-KDE cases that calibrated before evaluation timeout); inference phase time is recorded for those same 67, including the three 600-second KDE timeouts. The two unavailable RF evaluations never started and have blank phase cost fields with explicit reasons. Unique E3 evaluation-phase totals, deduplicated by task key/engine attempt/stage, are calibration n=67, sum 353.1662 seconds, and test inference n=67, sum 3951.3304 seconds. The route CSV attributes shared generator-fit and generation costs to each corresponding synthetic learner row; do not sum those repeated attribution values as physical totals. Use unique `(task_key, attempt_id, stage)` records in `costs.csv` for deduplicated phase totals. Reused E2 generator fits have blank E3 fit/trial durations because no E3 model refit/tune time was measured; E3 reuse validation task wall time remains recorded.

Trial-history accounting covers 60 newly fitted dependencies: 58 published selection histories, 2 exact-attempt terminal-cutoff partial histories verified from raw receipts during live export, and 0 curated partial-history projections whose raw receipt gate was verified before archive creation; 0 dependencies lack retained history. The histories contain 563 selection slots with recorded terminal outcomes (including duplicate_cached budget slots); 28 `duplicate_cached` slots carried copied elapsed values totaling 9918.58855703 seconds and are excluded from physical tuning time while remaining consumed slots in the fixed search budget. The recorded non-cached completed-trial subtotal is 71523.1648616 seconds across 535 durations. For the two failed RF fits, raw histories were validated before archiving against exact attempt identity and before/after source hashes; offline regeneration validates the projection SHA and preserves original source/evidence hashes, but cannot rerun the raw private-receipt gate. Their active trial's last observed elapsed values (851.710797332 seconds total) are reported separately and excluded from completed-trial time; 5 unattempted slots have no assigned duration. This remains a lower bound, not the full tuning cost. Partial selection-file hashes and the cutoff-ledger hash are recorded in the receipt; no raw process receipt payload is reproduced. Any missing duration remains blank rather than being treated as zero.

Resource policy history records an initial two-worker, 10 GiB policy (04:46 UTC to 16:56 UTC), then user-authorized adaptive CPU/RAM scheduling, followed by peak-safe queue packing from 17:12 UTC. Per-task policy labels are derived from each latest attempt start timestamp and that history. Trial/phase limits remained 600 seconds, process-tree memory cap remained 10 GiB, nested threads remained one, host/Harbor reserve was 6 GiB, and new workers used nice +10 after the concurrency amendment. Wall-clock timings are hardware/load dependent, with concurrent unrelated Harbor use; do not compare them as portable algorithmic cost benchmarks.

Observed ARF fit attempt selection histories include fixed-budget trial timeouts before a successful selected trial in completed repetitions; these are preserved in the original fit artifacts, not replaced or hidden.

## Limits and provenance

Results are conditional on the fitted generators and selected downstream configurations, observed test cohort, and successful cells. Resource-limited fits, direct-KDE timeouts and unavailable dependencies make route coverage uneven. Comparisons must use the paired n in the route CSV; survivorship can favor settings whose difficult cases completed. Do not call the best successful route universally superior.

The historical E1 pipelines and per-test-row predictions omitted from compact migration remain omitted. E3 reuse depended on available E2 reconstruction artifacts; this report does not claim restoration of historical E1 models or predictions. Preserve the known seven auxiliary E1 tuning-history discrepancies and E2 reconstruction limitations from the project report. Previously verified E1 completion metrics are not invalidated by those auxiliary-history caveats.

The three final E3 figures were reviewed against the corrected descriptive results; root figure-hash bindings and semantic review are recorded in `engineering_audits/E3_DESCRIPTIVE_ROOT_REVIEW_PASSED_20261026.json`. The receipt covers E3 descriptive outputs only and does not complete the independent full selected-model audit required during final project validation.

## Files and reproduction

- `E3_FINAL_CELL_LEDGER_69.csv`: one row per planned evaluation; includes terminal outcome/reason, fit and generation provenance, resource policy, timing fields, all seven class recalls/coverages/set sizes/supports, confusion matrices and calibration/test counts.
- `E3_FINAL_ROUTE_REPETITIONS.csv`: route means/sample SDs with actual n, individual repetition scores, separate recorded cost summaries and matched route differences with paired n.
- Generator fits, selection histories, generated datasets, model fits and evaluation artifacts remain under the EC2 runtime artifacts tree; source hashes and full manifest/registry hashes are in the receipt.
- Rebuild from an extracted package root on EC2: `cd <extraction-root>; python3 runtime_20261025/source/export_e3_descriptive.py --runtime runtime_20261025 --project project --output runtime_20261025/reports --partial-projection runtime_20261025/reports/E3_PARTIAL_HISTORY_VALIDATED_PROJECTION_20261026.json`. Artifact paths are resolved from task keys under the supplied runtime, so the current working directory and historical host absolute paths are not used. If exact archived phase receipts are absent, phase costs fall back only to exact task/attempt/stage matches in the included validated `reports/costs.csv`. The exporter reads metadata/evaluation JSON and audit tables only; it performs no model load, fitting, tuning, generation, calibration, or inference.

