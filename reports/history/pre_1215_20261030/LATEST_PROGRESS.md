# Latest project progress

Observation: 2026-10-30T11:05:18Z UTC. Registry outcomes below remain from the latest coherent read-only snapshot at 2026-10-30T10:04:33.369017Z; storage was re-observed at 11:05:18Z after the 10:45-10:47Z cleanup. This is interim and does not mark the project complete.

## Current machine-readable ledger

The canonical current 2,823-row outcome/reason ledger is [reports/planned_case_ledger.csv](reports/planned_case_ledger.csv), mirrored by [PLANNED_CASE_OUTCOMES_2823.csv](reports/CURRENT_CASE_OUTCOME_LEDGER_20261030/PLANNED_CASE_OUTCOMES_2823.csv), captured 2026-10-30T10:04:33.369017+00:00. It records 2,425 successes including 12 E6 reference aliases, 127 failures, 89 unavailable, 168 user-stopped and 14 pending rows. The prior 05:19Z pre-scope public ledger is preserved byte-for-byte at [history/planned_case_ledger_20261030T051951Z.csv](reports/history/planned_case_ledger_20261030T051951Z.csv).

## Result coverage and current storage

See the [11:05 UTC result-asset and resource-approval update](handoff/LAMOST_RESULT_ASSET_AND_RESOURCE_APPROVAL_20261030T1105Z.md) and [GitHub asset coverage audit](reports/GITHUB_AVAILABLE_RESULT_PAYLOAD_COVERAGE_20261030/README.md). The audit confirms 2,322 exact-member-verified later outcome arrays (2,214 overlap the base release and 108 are unique additions), 80/674 frozen E1 primary prediction arrays, and 24/24 recovery prediction arrays. Fitted models are not in GitHub assets.

The 10:45-10:47Z cleanup retired 2,132 already-published result groups (5,601,906,688 allocated bytes). Free space was 19,182,096,384 bytes at 11:05:18Z, below the unchanged 21,474,836,480-byte standard floor by 2,292,740,096 bytes. The user approved a 6 GiB reserve with one fit while keeping the 10 GiB per-fit ceiling and 600-second phase cap; implementation and validation remain pending, the setting is not active, and no fit has started under it.

## Current E3-E6 scientific ledger

| Experiment | Planned cases | Successful | Recorded failures | Unavailable | User-stopped | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 717 | 50 | 78 | 101 | 14 |
| E6 | 21 | 12 E3-reference aliases | 3 | 6 | 0 | 0 |

The ledger accounts for 2,823 E3-E6 case rows. The E6 primary six have no successful ensemble results: three equal-weight cases ended in test-prediction timeouts and three learned-weight cases were unavailable through a shared posterior dependency. The 12 successful E6 rows are reused E3 member-reference evaluations; three KDE references are unavailable. No five-member ensemble performance or benefit claim is supported.

The prospective scope amendment selected 45 evaluations (14 E4, 31 E5) and marked 168 other scientific repetitions user-stopped. Existing terminal outcomes and all prior repetition results remain in the ledger; the original three-repetition plan was not rewritten.

## Frozen E1 and E2

E1 remains the frozen 765-case ledger: 674 successful, 81 recorded failures (55 resource outcomes and 26 supervisor-terminal outcomes), and 10 unsupported. Its stopped recovery supplement is separate and must not be merged into the original denominator.

E2 has 108/150 primary evaluations and 120/120 separate classical references; 42 primary cases are unavailable. The reconstruction report records 31 reconstruction-accuracy differences, 210 low-precision flags, and four complete correlation strata. These counts do not make E2 primary coverage complete.

## Storage and validation

The 1,499 previously retained E3-E6 payload groups were restored and passed byte and hard-link checks at 2026-10-30 09:04 UTC; the original retention index remains preserved as history and the promoted state reports no restore requirement. No payload retirement was performed in this checkpoint.

A read-only v2 retention plan at 08:45 UTC selected zero bytes because the catalog payload rows lacked remote-asset evidence fields that were present on their asset records. This is a metadata binding issue, not a conclusion that the outcomes are ineligible. The upper bound considered for project-only reclamation is below the existing 20 GiB storage floor, so storage admission remains blocked without changing policy. Current free space at this observation is 13,105,987,584 bytes.

Final calibration-quantile replay, full artifact validation, and final archive review remain pending. Bootstrap remains dropped. No fitted models, FITS products, raw datasets, private process receipts, or credentials are included in this repository update.

## Reports and handoff

- [Full experiment work report](handoff/LAMOST_ALL_EXPERIMENTS_WORK_REPORT_20261030.md)
- [Supervisor continuation prompt](handoff/LAMOST_SUPERVISOR_PROMPT_20261030.md)
- [Earlier detailed progress snapshot](reports/PROJECT_PROGRESS_20261030.md) (dated 2026-10-29; its status counts are historical)

This update adds current documentation and links only; it does not alter scientific metrics, figures, source code, or the existing interim results ZIP.
