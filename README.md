# LAMOST DR10: six-experiment research project

Code, recorded results, figures and scientific provenance for seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

**Interim research snapshot — 28 October 2026, 12:58 IST (07:27 UTC).** This repository is a saved research record, not a claim that all six experiments have passed final validation. E4 and E5 still have pending evaluations. Existing E1 failures are preserved, E2 has incomplete primary coverage, and E6 has no successful primary ensemble test evaluations.

## Experiment status and navigation

| Experiment | Question | Recorded status | Start here |
|---|---|---|---|
| E1 | Frozen classification benchmark | 765 terminal: 674 successful, 81 failed, 10 unsupported | [E1 report and ledger](experiments/E1/README.md) |
| E2 | Generator fidelity versus classification | 108/150 primary evaluations; 120/120 separate classical references | [E2 report and provenance](experiments/E2/README.md) |
| E3 | Direct Bayes, synthetic-only and real-only learning | 69 terminal: 64 successful, 3 failed, 2 unavailable | [E3 results](experiments/E3/README.md) |
| E4 | Imbalance and target-class restoration | 1,551 successful, 71 failed, 3 unavailable, **148 pending** / 1,773 | [E4 interim results](experiments/E4/README.md) |
| E5 | Fitting-data corruption | 699 successful, 50 failed, 78 unavailable, **133 pending** / 960 | [E5 interim results](experiments/E5/README.md) |
| E6 | Generative posterior ensembles | 12 member-reference successes, 3 primary failures, 6 unavailable / 21; primary ensemble successes: **0** | [E6 availability and findings](experiments/E6/README.md) |

At the 07:22 UTC status snapshot, 281 E4/E5 scientific evaluation cases remained waiting (148 E4, 133 E5); no science workers were active because storage-forecast admission was in backoff. This is a point-in-time status, not a liveness claim.

The stopped E1 recovery supplement is separate: 24 successes, 10 failures, 2 user-stopped partial cells and 55 not attempted. These outcomes never replace frozen E1.

Counts refer to scientific evaluation cases, not controller dependency tasks. Later reports may contain dated historical counts; the [timestamped snapshot](metadata/current_execution_snapshot.json) identifies this export's observation.

## Repository contents

- [Frozen E1 code](code/E1_benchmark/) and [later-experiment implementation](code/source/).
- [Engineering tests](code/tests/), [frozen manifests and configurations](provenance/manifests/).
- [Experiment navigation](experiments/), [reports, CSV tables and figures](reports/).
- [Per-repetition metrics](reports/per_repetition_metrics.csv), [per-class metrics](reports/per_class_metrics.csv), [coverage ledger](reports/experiment_outcome_coverage.csv), [resource failures](reports/resource_failure_ledger.csv).
- [File-level source/export hashes](file_manifest.csv), [snapshot hashes](snapshot_manifest.json), [explicit exclusion inventory](exclusion_inventory.csv).

Large scientific result arrays and role-membership arrays are delivered separately through [GitHub Releases](https://github.com/S-G-mathematics/lamost-six-experiments/releases), with member manifests, ZIP CRC verification and SHA-256 checksums. The [verified array delivery](docs/RESULT_ARRAYS.md) contains 19 ZIPs (7.25 GB), with remote SHA-256 and byte-size verification. Fitted-model files and FITS files are excluded. Raw/generated training datasets are not part of this code-and-results repository.

## Scientific interpretation

Balanced accuracy is the primary classification criterion. Conformal summaries use the established nominal 90% target; interpret prediction-set size together with achieved overall and per-class coverage. Results show individual repetitions and actual successful counts. Comparisons conditional on success can have survivorship bias. No bootstrap analysis is included.

E2 retains original-versus-reconstructed provenance: 31 reconstructed accuracy differences and 210 low-precision class-report flags remain disclosed. Only four strata contain all five generator families; these correlations are descriptive and cannot establish a general fidelity–classification relationship.

Historical fitted E1 models and per-test-row prediction arrays omitted from the compact migration are still missing. Seven auxiliary tuning-history discrepancies remain documented; no missing history was fabricated. Hardware and resource-policy differences limit timing comparisons. E1/E2 test results had already been observed before later experiment plans were frozen.

## Reproduction and validation

Read the authoritative E1 protocol and dependency specification in [code/E1_benchmark](code/E1_benchmark/), then the experiment-specific manifests. Preserve original dataset identities, fitting/tuning/calibration/test roles, class order, seed and source hashes. The baseline is approximately 2,330,835 source representatives with a fixed 500,000-source test cohort.

This export preserves available source and evidence; it is not self-contained for model reuse because fitted models and raw data are excluded. Do not rerun frozen E1 or the stopped recovery study to fill gaps. New execution needs the matching verified EC2 dataset/artifacts and the recorded resource policy.

Final calibration replay, cross-experiment validation and final project delivery remain pending. Historical reports with “final” in their filenames refer to their documented component or observation, not completion of the entire project.

See [export provenance and sanitization](docs/EXPORT_PROVENANCE.md) for source-versus-export hash differences.
