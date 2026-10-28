# LAMOST six-experiment project progress

Snapshot: 2026-10-27 18:11:16 Asia/Kolkata (12:41:16 UTC), from the one-shot read-only observer on the existing EC2 instance i-095641a281a4038b9. The observer matched the controller identity, all three registered running workers to their actual process start ticks, and found no unverified running registry entries. It reported 26.41 GiB available RAM and 43.04 GiB free disk. These are timestamped observations, not guarantees about later process state.

All six experiments remain authorized. E1 is frozen; the E1 recovery supplement is stopped. E2 reporting retains its incomplete primary grid; remaining scientific execution is in E4 and E5. E3 and E6 have terminal case accounting, with global validation pending. No bootstrap is included.

## Planned and observed outcomes

Counts below use the frozen E1 ledger, accepted E2 tables, and the fresh runtime observer for E3-E6. For E3-E6, each repetition is shown as successful / scientific failure / unavailable dependency / waiting.

| Experiment | Planned | Successful | Failed | Unsupported or unavailable | Pending | Per-repetition outcomes |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | Frozen ledger; report has budget/method breakdown |
| E2 primary | 150 | 108 | 0 | 42 unavailable | 0 | Five-repetition primary coverage is 108/150; no new fits |
| E3 | 69 | 64 | 3 | 2 | 0 | R1 22/1/0/0; R2 20/1/2/0; R3 22/1/0/0 |
| E4 | 1,773 | 1,460 | 71 | 3 | 239 | R1 541/27/1/22; R2 494/23/1/73; R3 425/21/1/144 |
| E5 | 960 | 652 | 50 | 30 | 228 | R1 218/18/2/82; R2 216/16/24/64; R3 218/16/4/82 |
| E6 | 21 | 12 | 0 | 9 | 0 | Each repetition: 4/0/3/0 |

E2 also has a separate 120/120 successful classical-reference evaluation set. E2 is not complete in primary coverage: its 42 unavailable primary cases are retained as such. The accepted reconstruction group remains explicitly labeled; 31 reconstruction accuracy differences are disclosed, 210 low-precision class flags are retained, and only four of 30 strata have complete five-family correlations. Those four are descriptive; they do not establish a general fidelity-performance relationship.

E6's 15 selected member pipelines are available. Three direct KDE evaluation timeouts are evaluation outcomes, not missing model artifacts. The six primary ensemble attempts remain at zero. E3 and E6 terminal counts do not mean full cross-experiment artifact or calibration validation has passed.

## E1 and recovery provenance

Frozen E1 remains 765/765 terminal: 674 successful, 81 failed, and 10 unsupported. Its original 19 source files and ledger were rechecked unchanged. The early-stopped recovery supplement remains separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. No recovery outcomes are substituted into frozen E1.

## E2 limits

The accepted E2 primary grid is 108/150 evaluated, with 42 unavailable because the corresponding frozen E1 ARF/KDE fits failed and provide no selected successful model. These are not additional E2 algorithm failures. The classical reference set is 120/120. Original-versus-reconstructed provenance and the 31 accuracy differences are retained. The 210 low-precision diagnostics remain flagged. Available-only analyses are separate from the incomplete primary five-family analysis.

## E3-E6 progress

- E3: 64 successes, 3 scientific failures, and 2 unavailable dependencies across 69 planned cells. No later experiment repairs E1/E2 outcomes.
- E4: 1,460 successful, 71 failed, 3 unavailable, and 239 waiting across 1,773 planned scientific cases. Current work includes E4 direct ARF fits and random-forest treatment fits; their process identities were verified at the snapshot.
- E5: 652 successful, 50 failed, 30 unavailable, and 228 waiting across 960 scientific cases. The 228 are pending evaluation cases, distinct from upstream task counts. The nine label-noise realization cells were metadata/label validated; their 63-row source-class rate table uses full original class support. The fixed-selection audit passed all 617 currently successful E5 fit dependencies with zero metadata issues. E5 per-class set-size pairing checks cover only the saved completed blocks.
- E6: 12 successful and 9 unavailable across 21 planned cells. Member availability and evaluation availability are reported separately.

Failures, unavailable dependencies, and pending cells remain distinct; terminal failures are not retried just to increase completion counts.

## Storage, holds, and delivery

The post-commit storage optimization has an engineering-only proof: 405 tests passed in 21.8 seconds, with no scientific fits, worker signals, or controller restart. It preserves the earlier 397-test receipt and leaves scientific limits unchanged. Its proof explicitly says the first new real storage transaction after the optimization has not yet been observed; no storage speedup is claimed.

A prior completed storage transaction had a post-commit wrapper timeout. Its later recovery receipt verifies the archive SHA, ZIP index, aliases, and exact logical model bytes, then releases the stale hold. The original timed-out operation remains labeled operationally interrupted and was not relabeled successful. No scientific result changed.

At the fresh 18:11 snapshot, both ADMISSION_HOLD.json and STORAGE_HOLD.json markers were present. The recorded storage admission check was in backoff: free space was about 137 MB below the controller's then-current conservative estimate. Three verified scientific workers were still running. Marker presence is not a liveness claim; the observer's process checks are the evidence for those three workers: E4 rep 3 direct ARF F_half (1,438 s elapsed), E4 rep 3 direct ARF F_tenth (486 s), and E4 rep 2 random-forest treatment F_half_generated_kde (384 s).

The full archive is still BUILDING, not final delivery: packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip was last recorded at 25,760,173,359 bytes with 132 members and 52 encoded model members. Exact final unique additions remain unknown. A prior storage inventory found hard-link alias uncertainty; it did not authorize artifact deletion. Packaging preflight computes exact additions and fails closed if free space is insufficient; it does not make a second full copy of the existing archive.

The existing compact interim delivery is already on the laptop and verified:
- D:/LAMOST_Overall_EC2_Handoff_20261023/LAMOST_INTERIM_REPORTS_TABLES_FIGURES_20261027T084413Z_V5_REVIEWED.zip
- 6,725,024 bytes; SHA-256 ce601d1140b3e37d8f65952987c56af212ab08cab76f66ba3d9acf98348908f3
- This is interim, not the final project package.

## Validation and finalization still required

Global calibration-q replay has not run. The installed calibration gate is not a replay result. Global scientific artifact validation is also pending; prior scoped audits do not replace the required terminal full audit. The automatic finalizer is configured to run after all 6,270 task records are validated-terminal, but final report review, final small package, and final archive validation remain outstanding.

The latest saved admission observation in the continuation note and the fresh observer are separate observations. Do not infer later liveness from either. Continue using the actual controller and process identities.

## Scientific provenance retained

The 81 frozen E1 failures include 55 resource failures and 26 supervisor-terminal cells whose manifests remained recorded as started; those manifests do not indicate live workers. The 10 unsupported cases remain separate. Historical E1 fitted pipelines and per-test-row prediction arrays omitted from the compact migration remain unavailable unless explicitly documented as selectively restored; no claim of full historical reconstruction is made. Seven auxiliary tuning-history discrepancies in the documented 10k GMM and 30k CART/linear-SVM cells remain disclosed. Exact original complete histories are unavailable for those affected study/CSV files; this does not by itself invalidate previously verified completion metrics.

E2 original and reconstructed groups remain separate: primary 19 original and 89 reconstructed evaluations; across primary plus references, 43 original and 185 reconstructed. The 31 nonexact reconstructed accuracy differences remain disclosed, with maximum absolute difference about 3.174e-5. Later models have experiment-specific provenance and never repair E1. E3-E6 retain the prospective 10 GiB/600-second phase and trial policy; frozen E1 used 6 GiB/180-second trial limits, so timing/resource comparisons need the recorded hardware and policy caveats. No bootstrap confidence intervals or significance claims are added.

## Evidence references

- Latest continuation note: reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json, SHA-256 43264ffbf4d84e6d02e468a36d768877ba5dab2f9ce5dc9553b5d3b5a86ebf21.
- New 405-test post-commit proof: reports/engineering_audits/COLD_POSTCOMMIT_405_PUBLIC_PROOF_20261027.json, SHA-256 8b80736b8c9cd934f54ba663065dd06a68816d6b8c2e40dc76df9ed9a039d1c1.
- Completed cold-transaction hold recovery: reports/engineering_audits/COMPLETED_COLD_TRANSACTION_HOLD_RECOVERY_20261027.json, SHA-256 a62c2847a0fd4d7c2f37ce50da6f043d59d5bf6ad80e0c92a554385e56b75f51.
- E5 fixed-selection metadata audit: reports/engineering_audits/E5_FIXED_SELECTION_METADATA_AUDIT_20261027.json, SHA-256 86dbaee5e27424342139c8f7003a0ba6e3094b3b4911df844ad822258417d3aa.
- Critical-dependency audit: reports/engineering_audits/REMAINING_CRITICAL_DEPENDENCIES_20261027.json, SHA-256 0980da19f20329096f6b4e07e2267d94bedd6d35ed030bcfced04299a1554e72.
- Final archive feasibility review: reports/engineering_audits/FINAL_ARCHIVE_STORAGE_FEASIBILITY_20261027.json, SHA-256 b013672525e0341cea8283e6727d6c0c50ca01774404d7ff48ea8d304f0e3e11.
