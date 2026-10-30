# Interim result-coverage and storage update

**Observed:** registry outcome snapshot 2026-10-30 10:04:33 UTC; storage snapshot 2026-10-30 10:49:15 UTC. This remains an interim report. The project is not complete, and the rows marked pending remain in the original 2,823-case denominator.

## Experiment outcomes

The case counts below come from the coherent read-only registry snapshot at 10:04:33 UTC. They are ledger outcomes, not claims about live worker processes.

| Experiment | Planned rows | Successful | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen benchmark | 765 | 674 | 81 | 0 | 0 | 0 |
| E2 primary cases | 150 | 108 | 0 | 42 | 0 | 0 |
| E2 separate classical references | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 717 | 50 | 78 | 101 | 14 |
| E6 | 21 | 12 aliases | 3 | 6 | 0 | 0 |

The E3-E6 denominator is 2,823 rows: 2,425 successful records, 127 recorded failures, 89 unavailable, 168 user-stopped, and 14 pending. The 12 E6 successes are reused E3 member-reference aliases. E6 has zero successful primary ensemble test evaluations: three equal-weight cases ended in test-prediction timeouts; three learned-weight cases are unavailable through a shared posterior dependency. Three of the unavailable E6 rows are KDE reference evaluations. No ensemble performance or benefit claim follows from the aliases.

The prospective repetition-scope amendment selected 45 evaluations (14 E4 and 31 E5) and marked 168 other scientific repetitions user-stopped (67 E4, 101 E5). The original three-repetition plan and all previously recorded results remain intact. Fourteen selected E5 evaluation cases remained pending in the registry snapshot.

E1 remains frozen at 765 rows: its 81 recorded failures comprise 55 resource outcomes and 26 supervisor-terminal outcomes whose manifests remained started; the 10 unsupported rows are a separate category. Its stopped recovery supplement is separate: 24 successes, 10 failures, 2 user-stopped and 55 not attempted. Seven documented historical auxiliary-history caveats remain; this update does not reconstruct them. Some historical E1 model and prediction artifacts were absent from the original transfer and are not recreated here.

E2 has 108/150 primary evaluations and 120/120 separate classical references. Its reconstruction record contains 31 reconstruction-accuracy differences, 210 low-precision flags, and four complete correlation strata. The 42 unavailable primary cases are not counted as new scientific failures.

## Results available in the repository and release

The public planned-case ledger contains all 2,823 rows, including sanitized reasons and distinct successful, failed, unavailable, stopped, and pending outcomes:

- [Current planned-case ledger](../reports/planned_case_ledger.csv)
- [Dated source-bound ledger and summary](../reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/README.md)
- [Successful-case artifact crosswalk](../reports/SCIENTIFIC_SUCCESS_ARTIFACT_COVERAGE_20261030/SUCCESSFUL_TASK_ARTIFACT_COVERAGE.csv)
- [Metadata additions and reconciliation](../reports/SCIENTIFIC_SUCCESS_ARTIFACT_COVERAGE_20261030/ADDED_METADATA_FILES.csv) and [summary](../reports/SCIENTIFIC_SUCCESS_ARTIFACT_COVERAGE_20261030/SUMMARY.json)
- [Verified result-payload catalog](../provenance/result_payload_catalog/20261030/README.md)

The successful-case crosswalk covers 2,425 registry success rows, preserving aliases as separate task rows while pointing them to canonical artifacts. All 2,425 have evaluation and validation metadata. The export added 165 metadata files: 49 evaluation, 57 validation, 56 evaluation-result, and 3 artifact-reference records. For 56 evaluation-result records, only an absolute project root in an artifact path was normalized to a project-relative path; scientific fields were preserved.

The result-payload catalog records 2,322 test-outcome array members with exact member SHA-256, byte size, and CRC verification against the published GitHub result asset. These arrays are release assets rather than Git source files. The repository and result assets exclude fitted models, FITS products, and raw training datasets. Historical E1 omissions described above remain omissions; no missing historical model or prediction artifact is claimed as restored.

## Storage checkpoint

At 10:49:15 UTC, available space on the LAMOST project filesystem was 19,191,664,640 bytes. A bounded cleanup from 10:45 to 10:47 retired 2,132 approved, already-published result-payload groups after verifying their GitHub member references. Those groups accounted for 5,601,906,688 allocated bytes (5,595,808,572 logical bytes). A 628,975,775-byte download cache was verified and evicted separately; it is not included in the reclaimed-byte total. A restore-capable retention index remains in place.

The existing standard storage floor is 21,474,836,480 bytes (20 GiB), so the observed free space was short by 2,283,171,840 bytes, about 2.13 GiB. The storage gate therefore still blocks 13 planned fits and 14 evaluation cases. No scientific work was started by this cleanup. The 10 GiB per-fit ceiling and 600-second phase limit are unchanged. A proposed 6 GiB working reserve is not active; no resource policy was changed.

## Remaining validation

The full artifact audit, final calibration-quantile replay, final scientific report refresh, and final archive review remain pending. This report does not claim complete planned coverage, complete calibration validation, or project completion. Bootstrap remains dropped.
