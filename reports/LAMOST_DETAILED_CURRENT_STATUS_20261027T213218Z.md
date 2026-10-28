# LAMOST Current Work Status and Continuation Record

Created: 2026-10-27 21:32:18 UTC / 2026-10-28 03:02:18 IST
Fresh observer: 2026-10-27 21:29:56 UTC / 2026-10-28 02:59:56 IST
EC2 instance: i-095641a281a4038b9
Migration root: /home/ubuntu/lamost_e1_migration_20261023
Runtime: /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025

This is an interim work report. The project is not complete. It does not claim final project-wide calibration validation, final scientific synthesis, final archive delivery, or laptop transfer.

## Current registry and process observation

The observer read the current registry and verified the controller and two workers. It reported one registry task as running but could not verify its process identity. Do not infer that it is live from its status alone. The two verified workers were E5 direct ARF fits for label-noise 5% and 20%. The third row, E5 rep 1 histogram-gradient-boosting synthetic evaluation under ARF label-noise 10%, remains running-unverified at this observation; refresh process identity before treating it as active or recovering it.

The observer reported 27.51 GiB available RAM and 39.13 GiB free disk. The storage estimator allowed work under its current recorded estimate with about 2.67 GB headroom while STORAGE_HOLD.json was present. These are point-in-time shared-host measurements, not a fresh promise of resources or an instruction to bypass controller admission.

| Experiment | Planned | Successful | Scientific failures | Unsupported or unavailable | Running or unverified | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | 0 |
| E1 stopped recovery supplement | 91 | 24 retry successes | 10 retry failures | 2 user-stopped; 55 not attempted | 0 | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | 0 | 0 |
| E2 classical references | 120 | 120 | - | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 unavailable dependencies | 0 | 0 |
| E4 | 1,773 | 1,524 | 71 | 3 unavailable dependencies | 0 | 175 |
| E5 | 960 | 657 | 50 | 34 unavailable dependencies | 1 running-unverified | 218 |
| E6 historical E3 reference aliases | 15 | 12 | 0 | 3 unavailable | 0 | 0 |
| E6 primary ensembles | 6 | 0 | 3 | 3 unavailable dependencies | 0 | 0 |

### Per-repetition status

| Experiment | Rep | Successful | Scientific failures | Unavailable | Running-unverified | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 | 0 |
| E4 | 1 | 548 | 27 | 1 | 0 | 15 |
| E4 | 2 | 510 | 23 | 1 | 0 | 57 |
| E4 | 3 | 466 | 21 | 1 | 0 | 103 |
| E5 | 1 | 223 | 18 | 6 | 1 | 72 |
| E5 | 2 | 216 | 16 | 24 | 0 | 64 |
| E5 | 3 | 218 | 16 | 4 | 0 | 82 |
| E6 | 1 | 4 historical refs | 1 primary failure | 2 primary unavailable | 0 | 0 |
| E6 | 2 | 4 historical refs | 1 primary failure | 2 primary unavailable | 0 | 0 |
| E6 | 3 | 4 historical refs | 1 primary failure | 2 primary unavailable | 0 | 0 |

## Frozen E1 and E2

Frozen E1 remains 765/765 terminal: 674 successful, 81 failed, and 10 unsupported. The 81 failures comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained marked started. Unsupported cases are not failures. The frozen E1 execution policy was a 6-GiB process limit and 180-second trial timeout; historical profile labels such as native 8 GiB/8 cores do not replace those actual frozen runner settings.

The E1 recovery supplement is separate and stopped at user request: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. It is not a completed recovery campaign and none of its results replace frozen E1.

E2 primary coverage remains 108/150, with 42 unavailable. Its separate classical reference set remains 120/120. Preserve the 31 original-versus-reconstructed accuracy differences, 210 low-precision class-report flags, and four complete five-family correlation strata. The four strata are descriptive only; do not infer a general fidelity-performance relationship or significance. No new E1/E2 fit is authorized.

Provenance limitations remain: the compact migration omitted some historical fitted classifiers and per-test-row prediction arrays, and the seven auxiliary tuning-history discrepancies remain documented. Some original fitted pipelines are present; do not say they are all missing or all recovered. The fixed test cohort was already observed in E1/E2/E3, so it is not an untouched prospective test set.

## E3 completed outcomes and numerical audit

E3 is terminal: 64 successful, 3 scientific failures, and 2 unavailable dependencies across 69 planned cells. Route coverage is direct 12/15, synthetic 43/45, and real-only 9/9.

The saved independent audit reports:

- Direct GMM: n=3, mean balanced accuracy 0.8056, marginal coverage 0.8996, mean set size 1.487.
- Direct KDE: 0/3 completed evaluations; all three direct evaluations reached the fixed 600-second test-evaluation timeout without scores.
- Paired synthetic-minus-real balanced-accuracy effects vary: GMM histogram gradient boosting +0.0149 (n=3), GMM random forest +0.0109 (n=2), and Chow-Liu logistic regression -0.1645 (n=3). These are descriptive paired differences, not significance or a universal ranking.
- Chow-Liu synthetic logistic had mean marginal coverage 0.8984, but class-A coverage averaged 0.0255 and class-A recall was zero in all three repetitions, with 28,207 class-A examples per repetition. Marginal coverage does not guarantee classwise coverage.

The E3 independent audit also flags that the current E3 descriptive report does not disclose prior test exposure. Correct that in the final cross-experiment report. The audit is reports/engineering_audits/E3_INDEPENDENT_SAVED_RESULTS_AUDIT_20261027T183300Z.json, SHA256 c35ff6e4c1241692879547648d50ffe2eed2f348b3ac37d5bd72998c78f4f835.

## E4 and E5 progress

E4 currently has 1,524 successful, 71 scientific failures, 3 unavailable dependencies, and 175 waiting cases. A focused current-registry audit of the direct route yields 720/765 terminal cases: 646 successful, 71 failed, and 3 unavailable. The remaining 45 direct-route cases are all Extra Trees and remain waiting; do not call the direct-route component complete.

Reviewed direct-method subanalyses do not complete E4 as a whole. E4 direct KNN has its own reviewed 45-cell report. The direct-kernel block has separate availability and conditional performance files; its outcomes must retain their own denominators and failure reasons.

E5 currently has 657 successful, 50 scientific failures, 34 unavailable dependencies, 218 waiting, and one row marked running-unverified. Per-repetition counts are in the table above. Do not label the unverified row live without matching actual process identity, and do not convert waiting work into failure. The running-unverified case is not included in the experiment's terminal total.

A prospective RF4 admission profile has been qualified and deployed: four fit trials, one prediction trial, one native thread, a 10-GiB hard cap/reservation, and the existing 600-second phase limits. This profile is prospective only. The current observer did not show an RF4-profile worker, so do not claim a scientific RF4 dispatch or attribute any results to the profile.

## E6-v2 current results and operational history

E6 currently has 21 terminal entries: 15 historical member-reference aliases and 6 corrected primary ensemble tasks.

- Historical E3 reference aliases: 12 successful, 3 unavailable. The unavailable rows are KDE direct-evaluation references. These are E3 source evaluations, not new E6 member scoring.
- E6 primary ensemble tasks: 0 successful, 3 scientific failures, 3 unavailable dependencies. In each repetition, the equal-weight task had a test-prediction timeout in the shared test-posterior phase; the learned-weight task was unavailable because it depended on that same terminal shared phase. The learned task did not repeat the failed same-policy test-posterior phase.
- All six tasks retain frozen tuning weights; the three learned tasks retain candidate ledgers. These are tuning-only artifacts. There is no valid E6 ensemble test score, member-comparison artifact, tuning-best test comparison, or five-member benefit result.
- The six original E6-v1 zero-attempt dependency-gate decisions remain preserved as superseded history. They are separate from the six later feature-order operationally-invalid attempts, which were preserved and superseded by the corrected execution. Neither set is a scientific model failure.

The E6-v2 correction and permanent idempotent restart fix are now qualified and adopted. The actual activation receipt reports that the existing E6 terminal marker survived restart, four same-attempt workers were preserved, zero registry rows were directly mutated, zero scientific retries occurred during adoption, and the owned hold was released only after verified adoption. The latest E6 phase progress file is reports/E6_LATEST_ACTUAL_PHASE_PROGRESS_20261028.json. E6 results above remain valid terminal outcomes under the fixed policy; do not restart their ordinary test-posterior timeouts or enlarge limits.

## Qualification, source freeze, and archive state

- Current controller source: source/controller.py, SHA256 68b081487afd8f7572362d33601b276b245150d9bca587aca5bf3b9cace75c10.
- Current source freeze: manifests/freeze.json, SHA256 9994b586264f7b36c6355e051fac5ad2f17a3e4738dc2d4f7e036b9f08e96a00.
- Effective feature-order fix receipt: manifests/E6_FEATURE_ORDER_FIX_EFFECTIVE_RECEIPT_20261028.json, SHA256 d6ac763609c4b817e469007780d07f12e218defe50b85ce43df877f7cfd75455.
- Permanent restart activation receipt: reports/engineering_audits/E6_IDEMPOTENT_RESUME_EFFECTIVE_ACTIVATION_20261028.json, SHA256 b32d48294c6a7282335c6ccd3cb97ccd88e78cae352cf2e49a1714619af468ed.
- Portable qualification receipt: reports/PORTABLE_TEST_PASS_d41709ee13be6da6b9c828ff4692d7ef9e9f803b0537188d55dff1c9ee1dc7ce.json, SHA256 2a746d5a53965e27a75b28fd28a14c7a057bf7069c58728d0549389162197753. It records 531 passing portable tests; the qualified test bundle records 51 subtests in addition. Bundle fingerprint: d41709ee13be6da6b9c828ff4692d7ef9e9f803b0537188d55dff1c9ee1dc7ce.
- Latest continuation note: reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json, SHA256 8477076ea82839966e626db0e456408ec37c8b53ad57c36ff4d0984171539f2a. Its counts are older than the fresh observer in this report.
- Current registry snapshot: registry.json, SHA256 02dd1de5ac6926a25654813ab41e55abcfea97f0cdabb7c55647f55b1ac511a6.
- Cold model-store metadata manifest: manifests/cold_model_store_manifest.json, SHA256 97a5389228cda94f4c7ad1b2677425296e4b091b3ed2fe60a00468200bf8bf16. Digest-cache optimization remains deferred; the cold core remains unchanged and historical encoded proofs are preserved.
- A prior cold-archive metadata review records the BUILDING archive at packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip, 36,326,545,195 bytes, SHA256 473884978fe405657515ffa1b8f99a1ed8e68867d2491def86ebd73994ebc57b. This is not the final overall delivery archive. The full archive's prior CRC/SHA evidence is historical and was not rerun for this report.

The current report does not claim global calibration-q replay or final calibration validation. The final cross-experiment scientific report, final archive validation, compact laptop package, transfer, and final cleanup remain pending. Bootstrap remains dropped. Timing comparisons remain hardware- and shared-load-dependent; storage maintenance overlapped existing scientific fits, but no timeout is attributed to I/O without direct evidence.

## Next execution and handoff

1. Continue the authorized E4/E5 queue under the currently deployed controller; first recheck the running-unverified E5 row using exact process identity. Do not stop or duplicate workers based on heartbeat age.
2. Finish the 175 waiting E4 and 218 waiting E5 cases, including the 45 waiting direct Extra Trees cells. Preserve all terminal failure/unavailable outcomes.
3. Do not retry E6's ordinary fixed-policy test-posterior failures or relaunch completed E6 rows. Validate existing phase/evaluation records and preserve tuning-only artifacts.
4. Complete the global calibration-q replay, conformal and information-history validation, then regenerate final descriptive tables/figures from validated results.
5. Build the final full archive and compact laptop package only after source and output coverage is current. Verify each member manifest, ZIP CRC, byte size, and SHA256. Do not present the BUILDING archive as final.
6. Stop only project-owned processes after all authorized cases are accounted for; leave Harbor untouched.

Refresh the observer before new status claims:

    cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
    /usr/bin/python3 source/observe_progress.py --by-rep

