# LAMOST DR10: six-experiment research project

Code, recorded results, figures and scientific provenance for seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

**Interim research snapshot - read-only registry observed 2026-10-29T03:53:22.951438+00:00 UTC.** This saved research record does not claim all six experiments have passed final validation. Existing aggregate tables and figures remain bound to their documented analysis snapshot unless explicitly identified as incremental results.

## Experiment status and navigation

| Experiment | Question | Recorded status | Start here |
|---|---|---|---|
| E1 | Frozen classification benchmark | 765 terminal: 674 successful, 81 failed, 10 unsupported | [E1 report and ledger](experiments/E1/README.md) |
| E2 | Generator fidelity versus classification | 108/150 primary evaluations; 120/120 separate classical references | [E2 report and provenance](experiments/E2/README.md) |
| E3 | Direct Bayes, synthetic-only and real-only learning | 69 terminal: 64 successful, 3 failed, 2 unavailable | [E3 results](experiments/E3/README.md) |
| E4 | Imbalance and target-class restoration | 1,605 successful, 71 failed, 3 unavailable, **94 waiting** / 1,773 |
| E5 | Fitting-data corruption | 700 successful, 50 failed, 78 unavailable, **132 waiting** / 960 |
| E6 | Generative posterior ensembles | 12 successful member-reference aliases, 6 unavailable cases and 3 ensemble failures; **0/6** successful primary ensembles |

At the registry snapshot 2026-10-29T03:53:22.951438+00:00, E4/E5 have 226 waiting scientific cases (94 E4; 132 E5). This is a task-ledger snapshot, not a process-liveness claim. E1 recovery remains separate: 24 successes, 10 failures, 2 user-stopped and 55 not attempted.

The stopped E1 recovery supplement is separate: 24 successes, 10 failures, 2 user-stopped partial cells and 55 not attempted. These outcomes never replace frozen E1.

Counts refer to scientific evaluation cases, not controller dependency tasks. Later reports may contain dated historical counts; the [timestamped snapshot](metadata/current_execution_snapshot.json) identifies this export's observation.

## Repository contents

- [Frozen E1 code](code/E1_benchmark/) and [later-experiment implementation](code/source/).
- [Engineering tests](code/tests/), [frozen manifests and configurations](provenance/manifests/).
- [Experiment navigation](experiments/), [reports, CSV tables and figures](reports/).
- [Per-repetition metrics](reports/per_repetition_metrics.csv), [per-class metrics](reports/per_class_metrics.csv), [coverage ledger](reports/experiment_outcome_coverage.csv), [resource failures](reports/resource_failure_ledger.csv).
- [File-level source/export hashes](file_manifest.csv), [snapshot hashes](snapshot_manifest.json), [explicit exclusion inventory](exclusion_inventory.csv).
- [Current scientific cell ledger](reports/CURRENT_CELL_LEDGER.csv) contains all 2,823 E3-E6 case states from the read-only registry snapshot; it is not a process-liveness inventory.
- [Consolidated deadline interim scientific report and current tables](reports/deadline_submission_20261029/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md).
- [Current 764 qualification and interim report snapshot](docs/QUALIFIED_764_AND_INTERIM_REFRESH.md).
- [Incremental validated E4/E5 results](reports/E4_INCREMENTAL_RESULTS_20261028T084431Z.md) record three post-snapshot validated ledger entries and link the two unique outcome arrays.
- [E4 rep-3 incremental validated results](reports/E4_INCREMENTAL_VALIDATED_20261028T200243Z.md) contains six later RF treatment evaluations and 42 class-level rows; older derived tables and figures remain dated to the 17:00:39Z analysis snapshot.

Large scientific result arrays and role-membership arrays are delivered separately through [GitHub Releases](https://github.com/S-G-mathematics/lamost-six-experiments/releases), with member manifests, ZIP CRC verification and SHA-256 checksums. The [verified array delivery](docs/RESULT_ARRAYS.md) contains 19 ZIPs (7.25 GB), with remote SHA-256 and byte-size verification. Fitted-model files and FITS files are excluded. Raw/generated training datasets are not part of this code-and-results repository.

- [Frozen E1/E2 identity audit](provenance/identity/FROZEN_E1_E2_CURRENT_IDENTITY_20261029.json) records a 29-file current identity check; its archive check was a stat-chain check, not a fresh full archive hash.

- [764 selection-provenance audit](provenance/qualification_764/selection_receipt_metadata_audit_20261029.json) reports 578 canonical bindings passed and 27 cases excluded for missing fit-publication evidence; it opened zero model payloads and zero archive payloads.

## Scientific interpretation

Balanced accuracy is the primary classification criterion. Conformal summaries use the established nominal 90% target; interpret prediction-set size together with achieved overall and per-class coverage. Results show individual repetitions and actual successful counts. Comparisons conditional on success can have survivorship bias. No bootstrap analysis is included.

E2 retains original-versus-reconstructed provenance: 31 reconstructed accuracy differences and 210 low-precision class-report flags remain disclosed. Only four strata contain all five generator families; these correlations are descriptive and cannot establish a general fidelity–classification relationship.

Historical fitted E1 models and per-test-row prediction arrays omitted from the compact migration are still missing. Seven auxiliary tuning-history discrepancies remain documented; no missing history was fabricated. Hardware and resource-policy differences limit timing comparisons. E1/E2 test results had already been observed before later experiment plans were frozen.

## Reproduction and validation

Read the authoritative E1 protocol and dependency specification in [code/E1_benchmark](code/E1_benchmark/), then the experiment-specific manifests. Preserve original dataset identities, fitting/tuning/calibration/test roles, class order, seed and source hashes. The baseline is approximately 2,330,835 source representatives with a fixed 500,000-source test cohort.

This export preserves available source and evidence; it is not self-contained for model reuse because fitted models and raw data are excluded. Do not rerun frozen E1 or the stopped recovery study to fill gaps. New execution needs the matching verified EC2 dataset/artifacts and the recorded resource policy.

Final calibration replay, cross-experiment validation and final project delivery remain pending. Historical reports with “final” in their filenames refer to their documented component or observation, not completion of the entire project.

See [export provenance and sanitization](docs/EXPORT_PROVENANCE.md) for source-versus-export hash differences.

## Current status note

Read-only registry snapshot 2026-10-29T03:53:22.951438+00:00 UTC: E3 has 64 successes, 3 scientific failures, and 2 unavailable cases; E4 has 1,605 successes, 71 failures, 3 unavailable, and 94 waiting; E5 has 700 successes, 50 failures, 78 unavailable, and 132 waiting. E6 has 15 member-reference aliases (12 successful, 3 unavailable) and six primary ensembles (3 failures, 3 unavailable; 0/6 successful test evaluations). E1 remains frozen at 674 successful, 81 failed (55 resource failures; 26 supervisor-terminal manifests remained started) and 10 unsupported. E2 remains 108/150 primary and 120/120 classical-reference evaluations. The current E3-E6 ledger contains all 2,823 planned cases, including 226 waiting cases. No bootstrap or significance claims are made. Final native calibration replay, full artifact validation, final cross-experiment report, and full/small archive verification remain pending. This is an interim submission, not project completion.
