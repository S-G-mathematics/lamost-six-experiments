# Operational update: 30 October 2026 11:02:13 IST

E5 remains717successful/50failed/78unavailable/101user-stopped/14pending. The corrected storage-tool wire-schema update is now installed and verified:830/830tests,0skips; full202source/108test/26resource-proof closure validated. The first installation was rolled back after a missing-resource-proof deployment check; evidence is preserved. The exact21MB E3 ARF pipeline was restored byte-for-byte from its verified archive to satisfy the existing native-file-only E6 startup check. No new scientific fits, evaluation retries or failure reclassifications occurred.

The actual controller was verified after restart at05:30:58 UTC, with no model worker active. Diskfree21051764736B remains below the20GiB admissionfloor. Cleanup is confined to LAMOST; sharedpip/uvcaches andHarbor are untouched. The14remainingcells are waiting, not scientific failures.

Four newly uncovered result arrays have been uploaded as the verified GitHub asset e5_rf_rep1_outcomes_delta_20261030T051951Z.zip (6221133B; SHA2566ca36b039cadeee89d4c6b9d268acef0c1daaed623eae1ea41b3b4b59cc77e8a). Thirteen other arrays in the17-key publication delta already have exact-SHA verified remote assets. The accompanying Git report/table commit is pending verification; this is not finalprojectdelivery.

## Previous dated observations

# Update: 30 October 2026, 10:38:13 IST

Observed EC2 state at 05:02 UTC:
| Experiment | Accounted / planned | Successful | Failed | Unsupported or unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765/765 | 674 | 81 | 10 | 0 | 0 |
| E2 primary | 150/150 | 108 evaluated | 0 new model failures | 42 unavailable | 0 | 0 |
| E3 | 69/69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1773/1773 | 1632 | 71 | 3 | 67 | 0 |
| E5 | 946/960 | 717 | 50 | 78 | 101 | 14 |
| E6 | 21/21 | 12 member-reference aliases | 3 | 6 | 0 | 0 |

E2 reporting has an incomplete primary evaluation grid; its separate classical references are120/120. E6 has zero successful primary five-member ensembles. All DAG tasks:6243 terminal,27 waiting. The user-directed repetition cut is preserved; queued omissions are not scientific failures.

The first real payload12 cold-storage operation completed successfully at04:54:21 UTC, saving514455927 logical-source-minus-payload bytes across7 fitted artifacts. BUILDING archive77623665563B SHA25610472c825e11645086d2628b1d46191d8644f2b7a608b86f4978fb3e8a46c2b8, transactionf99c8ae4e5554727abaf95495e8c864d committed/resolved and CRC checked through the pinned transaction. This remains an in-progress archive, not final delivery.

The actual controller2315601 remains alive but has no active scientific worker. Available disk21099048960B is375787520B below the20GiB safetyfloor. The latest user decision restricts cleanup to LAMOST: shared pip/uv caches and Harbor remain excluded. The completed bounded exact-duplicate audit found109305856B potential hardlink savings, insufficient to clear the floor; scientific artifacts were left unchanged. A separate historical E3 staging audit found only91566080B exclusively allocated there, also insufficient before retention overhead.

The fit-overlap wire-schema repair passed830/830 tests with0skips and105subtests, but is still staged pending root-reviewed deployment. Current live scientific code/resource policy has not been changed. All three final-ledger-derived E1 learning curves have passed root visual review.

Full native artifact validation, calibration replay, final report/review, final archives, remaining GitHub payload synchronization and laptop delivery remain outstanding.1499 E4 native array groups must first be restored by their retained-array guardian after science terminates. GitHub currently retains the verified950139c56055e44b463b70a434cdf4823cbac6aa snapshot; do not interpret latest717 as717 uploaded.

## Earlier progress report (historical)

# LAMOST six-experiment project progress

**Interim snapshot:** 2026-10-30 09:11:53 IST / 2026-10-30T03:41:53.192929+00:00. This report reflects a read-only, single-transaction snapshot of scientific case outcomes in the EC2 registry. The full six-experiment project is not complete; remaining selected cases, full calibration replay, artifact validation and verified final delivery are still outstanding.

## Scientific case status

| Experiment | Planned cases | Successful / evaluated | Recorded failures | Unsupported | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 |
| E2 primary | 150 | 108 evaluated | 0 new failures | 0 | 42 original-model dependencies unavailable | 0 | 0 scheduled |
| E2 classical references | 120 | 120 evaluated | 0 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 0 | 3 | 67 | 0 |
| E5 | 960 | 716 | 50 | 0 | 78 | 101 | 15 |
| E6 | 21 | 12 successful member-reference aliases | 3 | 0 | 6 | 0 | 0 |

For E3-E6, the 2,823 planned scientific cases are accounted for by these statuses: E3 69/69, E4 1,773/1,773, E5 945/960 terminal with 15 waiting, and E6 21/21. A waiting case is not terminal. The single-evaluation scope amendment selected 45 score-independent E4/E5 evaluation cases and marked 168 other pending repetitions user-stopped; it did not change the original three-repetition plan or erase previous outcomes. The remaining 15 waiting cases are E5 work.

E1's 81 recorded failures comprise 55 resource-policy failures and 26 supervisor-terminal cases whose cell manifests remained started. Its 10 unsupported cases are separate from failures. E1 recovery is a separate stopped supplement: 24 successful retries, 10 retry failures, 2 user-stopped partial cells and 55 not attempted. These recovery rows do not replace frozen E1 outcomes.

## Experiment-specific evidence

- **E1:** Frozen benchmark outcome remains 674/765 successful; no E1 refit was performed for this report. Historical migrated fitted models and per-test prediction arrays remain omitted, and seven auxiliary tuning-history discrepancies remain disclosed. The original run used its historical 180-second/6-GiB execution envelope; later experiments used separately recorded limits. Bootstrap remains dropped.
- **E2:** Primary coverage remains 108/150 with 42 unavailable original-model dependencies; classical references are a separate 120/120 group. Original-versus-reconstructed provenance still includes 31 balanced-accuracy differences, 210 low-precision class-report flags, and only four complete five-family correlation strata. Those correlations are descriptive, not evidence of a general fidelity relationship.
- **E3:** The corrected matched-pair table is reports/E3_CURRENT_MATCHED_PAIRS_20261030.csv: direct-vs-real 36/45, synthetic-vs-real 43/45, and direct-vs-synthetic 35/45 available matched pairs. The prior table omitted 37 valid pairs; zero previously populated balanced-accuracy deltas disagreed with the recomputation. The corrected report is reports/E3_E4_TERMINAL_FINDINGS_20261030.md. The E3 figure refresh is under reports/E3_FIGURE_REFRESH_20261030T021523Z/; shared real-only fits are reused. These are descriptive matched comparisons without bootstrap or significance claims.
- **E4:** All 1,773 planned rows are accounted for under the scope amendment, including 67 user-stopped repetitions. Metrics conditional on successful evaluations must be read with their actual matched denominators and unavailable rows.
- **E5:** 716 cases have successful saved evaluations, 50 recorded failures, 78 unavailable dependencies, 101 user-stopped repetitions, and 15 waiting cases. The latest three successful cases (numbers 714-716 in the success sequence) are retained on EC2 and were not yet included in the latest Git results snapshot. Do not infer that every successful result is already uploaded.
- **E6:** The 12 successful rows are reused E3 member-evaluation aliases, not new model-scoring runs. Three KDE member references are unavailable. The six primary ensemble outcomes contain three equal-weight test failures and three learned-weight unavailable dependencies: **0/6 successful ensemble test evaluations**. The E6-only figure refresh, based on the current 21-row registry slice, is reports/E6_FIGURE_REFRESH_20261030T030121Z/. It shows the 12/15 member references and zero successful ensembles. No ensemble performance or benefit is claimed.

Overall conformal coverage near the nominal 90% target does not guarantee 90% coverage for every class. Numeric conformal replay and final artifact validation have not been completed for the full project.

## Current code, storage and delivery

The qualified 827-test operational bundle is installed and published at commit 950139c56055e44b463b70a434cdf4823cbac6aa on main and results/snapshot-2026-10-28. It includes the codec payload profile and E6 figure-layout update; it does not change the scientific plan or recorded metrics. Its fixture suite and a 3.8-GB byte-exact payload probe passed, but **no production 12-GiB archive transaction has been completed**. The 12-GiB descriptor ceiling applies to explicitly tagged payloads; legacy untagged payloads retain the 2-GiB cap. A 5,400-second setting is a cap, not a measured completion time.

The last completed archive transaction recorded was 76,690,666,457 bytes; its SHA-256 is recorded in the existing archive receipt. That is a prior completed archive, not a digest of the current archive. At this report snapshot, free space was 21,212,930,048 bytes, 262,438,023 bytes below the 21,475,368,071-byte preflight threshold for the pending payload12 transaction. The retained E4 result-array guardian has 1,499 groups awaiting restoration per the latest operational status; the full artifact/calibration audit has not run. Current archive output is not yet committed as a final verified archive.

The Git working tree is temporarily retired after remote verification of commit 950139c56055e44b463b70a434cdf4823cbac6aa. runtime_20261025/GIT_WORKTREE_RESTORE_REQUIRED.json records that restoration is required before final publication; only the project-owned final-publisher schedule is paused. The latest three E5 results remain available on EC2 pending the next Git payload sync. No fitted models were published. The project cleanup remained confined to LAMOST; shared pip/uv caches and Harbor were not touched.

## Remaining work

1. Complete the 15 waiting E5 scientific cases under the recorded fixed policy; do not retry terminal scientific failures or unavailable comparisons.
2. Restore all temporarily retained result arrays and complete supervised artifact and calibration-quantile validation.
3. Regenerate the final reports, tables and figures from a coherent final registry snapshot, including all six experiments and honest matched denominators.
4. Verify final full and compact archive contents, CRCs, sizes and SHA-256 values; restore the Git working tree and publish all remaining validated results.
5. Stop only project-owned workers and watchers after the final verified delivery.
