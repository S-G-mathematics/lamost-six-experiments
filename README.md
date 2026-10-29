# LAMOST DR10: six-experiment research project

Code, recorded results, figures and scientific provenance for seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

**Interim research snapshot - scientific results observed 2026-10-29T07:49:47.720386+00:00 UTC.** This saved research record does not claim all six experiments have passed final validation. Existing aggregate tables and figures remain bound to their documented analysis snapshot unless explicitly identified as incremental results.


## Operational source update (2026-10-29T06:31:00Z)

The qualified ET4/archive source profile is installed. Its bounded portable qualification recorded 776 passed tests, 3 warnings and 85 subtests. The archive handoff was paused at this observation; no scientific workers were active, and 220 E4/E5 scientific cases remained waiting (88 E4, 132 E5). The 4 GiB batch, 8 GiB encoded temporary-output and 5,400-second archive limits are qualified policy bounds, not measured throughput or claimed speedup. No new scientific results are represented by this source update. See [qualification and profile note](docs/QUALIFIED_CODEC4_776_AND_ET4_PROFILE_20261029.md) and [source-map provenance](provenance/qualification_codec4_776/OPERATIONAL_SOURCE_MAP_PROVENANCE_NOTE_20261029.md).

## Latest coherent registry snapshot (2026-10-29T07:49:47.720386+00:00 UTC)

E4 records 1,616 successful, 71 failed, 3 unavailable and 83 waiting cases. E5 records 700 successful, 50 failed, 78 unavailable and 132 waiting cases. The read-only snapshot accounts for all 2,823 E3-E6 scientific cases; 2,392 validated metric rows have saved evaluation JSON inputs and none were missing. The [timestamped report and tables](reports/deadline_submission_20261029/snapshot_20261029T074947Z/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md) and [current cell ledger](reports/CURRENT_CELL_LEDGER.csv) preserve these counts. The snapshot includes a status figure; the broader E1-E6 figures remain tied to their earlier stated cutoffs. Waiting counts are ledger states, not process-liveness claims.

## Experiment status and navigation

| Experiment | Question | Recorded status | Start here |
|---|---|---|---|
| E1 | Frozen classification benchmark | 765 terminal: 674 successful, 81 failed, 10 unsupported | [E1 report and ledger](experiments/E1/README.md) |
| E2 | Generator fidelity versus classification | 108/150 primary evaluations; 120/120 separate classical references | [E2 report and provenance](experiments/E2/README.md) |
| E3 | Direct Bayes, synthetic-only and real-only learning | 64 successful, 3 recorded scientific failures, 0 unsupported, 2 unavailable, 0 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 0 waiting/active / 69 | [E3 results](experiments/E3/README.md) |
| E4 | Imbalance and target-class restoration | 1,618 successful, 71 recorded scientific failures, 0 unsupported, 3 unavailable, 67 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 14 waiting/active / 1,773 |
| E5 | Fitting-data corruption | 700 successful, 50 recorded scientific failures, 0 unsupported, 78 unavailable, 101 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 31 waiting/active / 960 |
| E6 | Generative posterior ensembles | 12 successful member-reference aliases, 3 unavailable references; 3 ensemble failures, 3 unavailable ensembles; 0/6 successful primary test evaluations |

At the coherent registry snapshot 2026-10-29T07:49:47.720386+00:00, E4/E5 have 215 waiting scientific cases (83 E4; 132 E5). This is a task-ledger snapshot, not a process-liveness claim. E1 recovery remains separate: 24 successes, 10 failures, 2 user-stopped and 55 not attempted.

The stopped E1 recovery supplement is separate: 24 successes, 10 failures, 2 user-stopped partial cells and 55 not attempted. These outcomes never replace frozen E1.

Counts refer to scientific evaluation cases, not controller dependency tasks. Later reports may contain dated historical counts; the [timestamped snapshot](metadata/current_execution_snapshot.json) identifies this export's observation.

## Repository contents

- [Frozen E1 code](code/E1_benchmark/) and [later-experiment implementation](code/source/).
- [Engineering tests](code/tests/), [frozen manifests and configurations](provenance/manifests/).
- [Experiment navigation](experiments/), [reports, CSV tables and figures](reports/).
- [Per-repetition metrics](reports/per_repetition_metrics.csv), [per-class metrics](reports/per_class_metrics.csv), [coverage ledger](reports/experiment_outcome_coverage.csv), [resource failures](reports/resource_failure_ledger.csv).
- [File-level source/export hashes](file_manifest.csv), [snapshot hashes](snapshot_manifest.json), [explicit exclusion inventory](exclusion_inventory.csv).
- [Current scientific cell ledger](reports/CURRENT_CELL_LEDGER.csv) contains all 2,823 E3-E6 case states from the 2026-10-29T05:02:02.829484+00:00 read-only registry snapshot; it is not a process-liveness inventory.
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

Read-only registry snapshot 2026-10-29T08:55:39.017085+00:00 UTC: E3: 64 successful, 3 recorded scientific failures, 0 unsupported, 2 unavailable, 0 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 0 waiting/active / 69; E4: 1,618 successful, 71 recorded scientific failures, 0 unsupported, 3 unavailable, 67 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 14 waiting/active / 1,773; E5: 700 successful, 50 recorded scientific failures, 0 unsupported, 78 unavailable, 101 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 31 waiting/active / 960. Operational interruptions/invalidations, user-stopped work, and packaging-pending work are counted separately from scientific failures. E6 has 12 successful member-reference aliases and 0/6 successful primary ensembles. E1 remains frozen at 674 successful, 81 failed (55 resource; 26 supervisor-terminal manifests remained started) and 10 unsupported; E2 remains 108/150 primary and 120/120 classical references. The E3-E6 ledger accounts for all 2,823 planned cases in this snapshot. This is interim; final calibration replay and full artifact validation remain pending.

<!-- CURRENT REPETITION SCOPE -->
## Current repetition-scope amendment

At the registry snapshot in the linked interim report, the original 2,823 E3-E6 scientific cases and 6,270 DAG task rows remain the denominator. The score-independent amendment retained 45 selected E4/E5 evaluation cases with their dependency closure and marked 168 other pending E4/E5 scientific repetitions user-stopped. The complete selected dependency closure contained 167 tasks; 90 selected-closure tasks were pending at application. Previously terminal outcomes remain unchanged. Selected cases can complete after application; reports distinguish their current status from user-stopped work. The original three-repetition plan hash is unchanged, and the original full grid is not complete.

<!-- END CURRENT REPETITION SCOPE -->
