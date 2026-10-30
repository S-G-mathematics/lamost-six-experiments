# LAMOST DR10: six-experiment research project

Code, recorded results, figures and scientific provenance for seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

**Interim research checkpoint - 2026-10-30T14:55:25.944320+00:00.** The project is not complete. See [LATEST_PROGRESS.md](LATEST_PROGRESS.md) for the current ledger and the [full work report](handoff/LAMOST_ALL_EXPERIMENTS_WORK_REPORT_20261030.md) and [supervisor prompt](handoff/LAMOST_SUPERVISOR_PROMPT_20261030.md). Older status sections and figures retain their stated cutoffs.


## Operational source update (2026-10-29T06:31:00Z)

The qualified ET4/archive source profile is installed. Its bounded portable qualification recorded 776 passed tests, 3 warnings and 85 subtests. The archive handoff was paused at this observation; no scientific workers were active, and 220 E4/E5 scientific cases remained waiting (88 E4, 132 E5). The 4 GiB batch, 8 GiB encoded temporary-output and 5,400-second archive limits are qualified policy bounds, not measured throughput or claimed speedup. No new scientific results are represented by this source update. See [qualification and profile note](docs/QUALIFIED_CODEC4_776_AND_ET4_PROFILE_20261029.md) and [source-map provenance](provenance/qualification_codec4_776/OPERATIONAL_SOURCE_MAP_PROVENANCE_NOTE_20261029.md).

## Qualified codec payload update (2026-10-30)

The installed codec payload profile is recorded in [the public activation evidence](reports/engineering_audits/CODEC12_PUBLIC_ACTIVATION_20261030.json). The exact 827-test portable qualification and its source/test fixtures are included under code/ and provenance/qualification_codec12_827/. This is an operational storage/admission update plus an E6 figure-layout correction; it does not change the scientific plan or recorded metric values. The explicit descriptor ceiling is 12 GiB per payload, while untagged legacy payloads remain capped at 2 GiB. The qualification used fixtures and one exact 3.8 GB payload roundtrip; it did not run a production 12 GiB archive transaction or fit. The 5,400-second archive setting is a cap, not a measured completion time. The archived portable bundle retains historical staging-purpose wording; the activation record supersedes that wording for the installed state.

## Earlier coherent registry snapshot (historical, 2026-10-29T07:49:47.720386+00:00 UTC)

This earlier record had E4 1,616 successful, 71 failed, 3 unavailable and 83 waiting cases, and E5 700 successful, 50 failed, 78 unavailable and 132 waiting cases. The read-only snapshot accounts for all 2,823 E3-E6 scientific cases; 2,392 validated metric rows have saved evaluation JSON inputs and none were missing. The [timestamped report and tables](reports/deadline_submission_20261029/snapshot_20261029T074947Z/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md) and [current cell ledger](reports/CURRENT_CELL_LEDGER.csv) preserve these counts. The snapshot includes a status figure; the broader E1-E6 figures remain tied to their earlier stated cutoffs. Waiting counts are ledger states, not process-liveness claims.

## Result coverage and storage checkpoint

The [11:05 UTC asset coverage and resource-approval update](handoff/LAMOST_RESULT_ASSET_AND_RESOURCE_APPROVAL_20261030T1105Z.md) links the metadata-only GitHub release audit and distinguishes the 10:04 UTC case-ledger snapshot from the later storage observation. The audit confirms 2,322 exact-member-verified later outcome arrays with 2,214 base-release overlaps and 108 unique additions. It also verifies 80 of 674 frozen E1 primary prediction arrays and 24 of 24 stopped-recovery prediction arrays; fitted models are not in the GitHub assets.

After the 10:45-10:47 UTC cleanup, free space was 19,182,096,384 bytes at 11:05:18 UTC, below the existing 20 GiB storage floor. The user approved a 6 GiB working reserve with one concurrent fit, retaining the 10 GiB/600-second hard limits, but implementation and validation are pending; this setting is not active and no fit has started under it.

## Current status (2026-10-30)

See [LATEST_PROGRESS.md](LATEST_PROGRESS.md) for the latest counts: E4 1,632 successes, E5 726, with five E5 cases still waiting; E6 has zero successful primary ensemble tests. The nine newest E5 rep-1 results and their metadata are documented in [the incremental results folder](reports/E5_REP1_NINE_VALIDATED_20261030/README.md). This is an interim record, not project completion.

## Current case ledger

The canonical current 2,823-row planned outcome and reason ledger is [reports/planned_case_ledger.csv](reports/planned_case_ledger.csv), mirrored by the source-bound dated capture [PLANNED_CASE_OUTCOMES_2823.csv](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/PLANNED_CASE_OUTCOMES_2823.csv), captured 2026-10-30T10:04:33.369017+00:00. The prior 05:19Z pre-scope public ledger is preserved byte-for-byte at [history/planned_case_ledger_20261030T051951Z.csv](reports/history/planned_case_ledger_20261030T051951Z.csv). The current ledger keeps the original denominator and distinguishes successful aliases, recorded failures, unavailable, user-stopped, and pending outcomes.

## Experiment status and navigation

| Experiment | Question | Current recorded outcome at 2026-10-30T10:04:33Z | Start here |
|---|---|---|---|
| E1 | Frozen classification benchmark | 765 terminal: 674 successful, 81 recorded failures, 10 unsupported | [E1 report and ledger](experiments/E1/README.md) |
| E2 | Generator fidelity versus classification | 108/150 primary evaluations; 120/120 separate classical references | [E2 report and provenance](experiments/E2/README.md) |
| E3 | Direct Bayes, synthetic-only and real-only learning | 64 successful, 3 recorded failures, 2 unavailable / 69 | [E3 results](experiments/E3/README.md) |
| E4 | Imbalance and target-class restoration | 1,632 successful, 71 recorded failures, 3 unavailable, 67 user-stopped, 0 pending / 1,773 | [E4 results](experiments/E4/README.md) |
| E5 | Fitting-data corruption | 717 successful, 50 recorded failures, 78 unavailable, 101 user-stopped, 14 pending / 960 | [E5 results](experiments/E5/README.md) |
| E6 | Generative posterior ensembles | 12 successful member-reference aliases, 3 recorded failures, 6 unavailable; 0/6 successful primary ensemble test evaluations | [E6 results](experiments/E6/README.md) |

At the coherent registry snapshot 2026-10-30T10:04:33.369017+00:00, E5 has 14 pending scientific cases; E4 has none pending under the prospective scope amendment. These are ledger states, not process-liveness claims. E1 recovery remains separate: 24 successes, 10 failures, 2 user-stopped and 55 not attempted.

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

Read-only registry snapshot 2026-10-29T10:57:08.012357+00:00 UTC: E3: 64 successful, 3 recorded scientific failures, 0 unsupported, 2 unavailable, 0 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 0 waiting/active / 69; E4: 1,624 successful, 71 recorded scientific failures, 0 unsupported, 3 unavailable, 67 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 8 waiting/active / 1,773; E5: 700 successful, 50 recorded scientific failures, 0 unsupported, 78 unavailable, 101 user-stopped, 0 operationally interrupted, 0 operationally invalid, 0 packaging-pending, 31 waiting/active / 960. Operational interruptions/invalidations, user-stopped work, and packaging-pending work are counted separately from scientific failures. E6 has 12 successful member-reference aliases and 0/6 successful primary ensembles. E1 remains frozen at 674 successful, 81 failed (55 resource; 26 supervisor-terminal manifests remained started) and 10 unsupported; E2 remains 108/150 primary and 120/120 classical references. The E3-E6 ledger accounts for all 2,823 planned cases in this snapshot. This is interim; final calibration replay and full artifact validation remain pending.

<!-- CURRENT REPETITION SCOPE -->
## Current repetition-scope amendment

At the registry snapshot in the linked interim report, the original 2,823 E3-E6 scientific cases and 6,270 DAG task rows remain the denominator. The score-independent amendment retained 45 selected E4/E5 evaluation cases with their dependency closure and marked 168 other pending E4/E5 scientific repetitions user-stopped. The complete selected dependency closure contained 167 tasks; 90 selected-closure tasks were pending at application. Previously terminal outcomes remain unchanged. Selected cases can complete after application; reports distinguish their current status from user-stopped work. The original three-repetition plan hash is unchanged, and the original full grid is not complete.

<!-- END CURRENT REPETITION SCOPE -->

## Portable qualification 807

Portable engineering qualification passed: **807/807**. Bundle fingerprint d3ce1b3657ac513573b1fb8ec7994a9aa272ec2b7c68641c78b2b21e3bfda825, manifest SHA-256 9c17f0e7f2ee715b0c22ef7f942d047fd5acf347f3d43e52552ba9e9b9759857, pass receipt [PORTABLE_TEST_PASS_d3ce1b3657ac513573b1fb8ec7994a9aa272ec2b7c68641c78b2b21e3bfda825.json](reports/PORTABLE_TEST_PASS_d3ce1b3657ac513573b1fb8ec7994a9aa272ec2b7c68641c78b2b21e3bfda825.json). Frozen E1 results remain unchanged. No fitted models or prediction arrays are included. The scientific project remains incomplete. See [qualification details](docs/QUALIFICATION_807.md), [delivery manifest](metadata/PORTABLE_QUALIFICATION_807_DELIVERY_MANIFEST.json), and [export curation](docs/EXPORT_CURATION.md).


## Current update (2026-10-30T12:08:13.342926Z)

The latest case ledger has 2,433 successful E3-E6 rows including 12 E6 member-reference aliases, 127 recorded failures, 89 unavailable, 168 user-stopped, and 6 pending. The original planned denominator remains 2,823.

See [latest progress](LATEST_PROGRESS.md), [current case ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/PLANNED_CASE_OUTCOMES_2823.csv), and [new E5 rep-1 results](reports/E5_REP1_INCREMENTAL_RESULTS_20261030T120813Z/RESULTS.csv). 8 additional exact test-outcome arrays are in a remote-verified [GitHub release asset](https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_8_validated_outcomes_20261030T120813Z.zip). No fitted models or raw training data are included.

The [B668 controller and approved source closure](provenance/working_reserve_storage_20261030/README.md) records a 6 GiB working reserve with one fit; the 10 GiB per-fit cap and 600-second phase cap remain unchanged. Final calibration replay and project validation remain pending.
