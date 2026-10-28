# LAMOST Six-Experiment Interim Progress and E6-v2 Correction

Report created: 2026-10-27 19:14:54 UTC / 2026-10-28 00:44:54 IST
Fresh EC2 observation: 2026-10-27 19:12:35 UTC / 2026-10-28 00:42:35 IST
Host: i-095641a281a4038b9
Migration root: /home/ubuntu/lamost_e1_migration_20261023
Runtime: /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025

This is an interim record. The project-wide calibration replay, final scientific report, final archive, and laptop delivery are still incomplete.

## Current execution snapshot

The fresh observer verified the controller and two live workers. It found no registry rows marked running without a verified process.

| Group | Planned | Successful/evaluated | Scientific failures | Unsupported/unavailable | Operationally invalid | Waiting |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | 0 |
| E1 stopped recovery supplement | 91 | 24 retry successes | 10 retry failures | 2 user-stopped; 55 not attempted | 0 | 0 |
| E2 primary generator analysis | 150 | 108 | - | 42 unavailable | 0 | 0 |
| E2 classical reference set | 120 | 120 | - | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 unavailable dependencies | 0 | 0 |
| E4 | 1,773 | 1,512 | 71 | 3 unavailable dependencies | 0 | 187 |
| E5 | 960 | 652 | 50 | 30 unavailable dependencies | 0 | 228 |
| E6 historical E3 member references | 15 | 12 | 0 | 3 unavailable | 0 | 0 |
| E6-v1 primary gate records | 6 | 0 | 0 | 6 old gate-unavailable outcomes | 0 | 0 |
| E6-v2 corrected primary records | 6 | 0 valid evaluations | 0 scientific failures | 0 scientific unavailability | 6 operationally invalid | 0 waiting |

For E6-v2, the fresh registry shows one recorded attempt identity for each of the six tasks, all operationally invalid, with no outcome and pending validation. Root verified that these attempts started from 19:11:09 to 19:11:48 UTC and all failed before posterior generation with the same pre-science error: E6-v2 GMM feature order missing or mismatched. No E6 workers were active in the 19:12 observer. These are implementation-defect attempts, not scientific failures or unavailable model outcomes. Preserve them; after the qualified fix, supersede only these six invalid attempts once. Do not call them zero-attempt records: the earlier six E6-v1 gate decisions were zero-attempt and remain separate.

The two verified workers were E4 fits: direct ARF for M tenth and treatment random forest for M tenth ROS. The observer reported 26.86 GiB available RAM and 40.15 GiB free disk. A STORAGE_HOLD.json marker existed; the current storage estimator allowed work with about 2.39 GB headroom. These are point-in-time readings and do not override current controller admission decisions.

### Per-repetition coverage

| Experiment | Rep | Successful | Scientific failures | Unavailable dependencies | Waiting |
|---|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 |
| E4 | 1 | 546 | 27 | 1 | 17 |
| E4 | 2 | 509 | 23 | 1 | 58 |
| E4 | 3 | 457 | 21 | 1 | 112 |
| E5 | 1 | 218 | 18 | 2 | 82 |
| E5 | 2 | 216 | 16 | 24 | 64 |
| E5 | 3 | 218 | 16 | 4 | 82 |

Waiting is not a scientific failure. Experiment-wide counts are not substitutes for per-condition successful repetition denominators.

## E1 and E2 remain frozen

Frozen E1 is 765/765 terminal: 674 successful, 81 failed, and 10 unsupported. The 81 failures include 55 resource failures and 26 supervisor-terminal cells whose manifests remained marked started. The 10 unsupported cases remain separate. No further E1 runs are authorized.

The stopped E1 recovery supplement remains separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted after the user's stop decision. It is not a completed recovery campaign and none of its results replace frozen E1.

E2 remains incomplete in primary coverage at 108/150, with 42 unavailable dependencies. Its separate classical reference set is 120/120. Preserve the 31 original-versus-reconstructed accuracy differences, 210 low-precision class-report flags, and four complete five-family correlation strata. Those four strata are descriptive and do not establish a general fidelity-classification relationship or statistical significance. Do not refit E1/E2 to fill unavailable cells.

Historical E1 fitted-model and per-test-row prediction omissions, plus the seven auxiliary tuning-history discrepancies, remain provenance limitations. Some original fits are available; do not say all historical pipelines are missing or all have been restored. Bootstrap remains dropped.

## E3 validated findings and report caveat

The saved E3 independent audit validates 69 terminal evaluation cells: 64 successful, 3 scientific failures, and 2 unavailable dependencies. Route coverage is direct 12/15, synthetic 43/45, and real-only 9/9. These denominators matter; successful-only summaries are conditional on completion.

Examples from the validated audit, with actual paired denominators:

- Direct GMM: n=3, mean balanced accuracy 0.8056, marginal coverage 0.8996, mean prediction-set size 1.487.
- Direct KDE: 0/3 completed evaluations; all three hit the fixed 600-second evaluation limit without saved scores.
- Synthetic-minus-real balanced-accuracy differences vary by generator and learner: GMM histogram gradient boosting +0.0149 (n=3), GMM random forest +0.0109 (n=2), Chow-Liu logistic regression -0.1645 (n=3). These are descriptive paired effects, not significance tests or universal rankings.
- Chow-Liu synthetic logistic regression had mean marginal coverage 0.8984 but mean class-A coverage 0.0255 and class-A recall 0 in all three repetitions (28,207 class-A test examples per repetition). Nominal marginal coverage does not ensure classwise coverage.

The E3 audit also found that its current descriptive report does not disclose prior test exposure. E1/E2 test outcomes were already observed, so the final report must state that information history and must not describe all later analyses as prospective untouched tests.

The audit records nine reused E2-reconstructed generator fits and six new E3 fits; all 15 successful generated datasets contain 400,000 rows. Two synthetic random-forest evaluation dependencies were unavailable after fixed 10-GiB fitting policy failures. Keep resource feasibility distinct from model predictive performance.

## E6 correction: published amendment, current operational error

E6-v2 has been formally published and deployed to the existing controller. The qualified freeze receipt records:
- controller source SHA256 b9465eb5ae73991abe7551dee7b8f131feefecc3dd3656917d019b76457aa7ca;
- qualified freeze SHA256 203e51bbc6f05d4a1795644abdd321ca6a196707d18811ab146914247a3b90c5;
- E6-v2 overlay SHA256 54540cfcff47d32878184f7b9ff0a061753cb3d61cabff290ca6c907d38aadce;
- effective amendment receipt manifests/E6_V2_EFFECTIVE_AMENDMENT_RECEIPT_20261028.json, SHA256 f20a442eed028171586ed5ad518fd95054c5051289408da5b331f95d2345e972;
- portable qualification receipt reports/PORTABLE_TEST_PASS_19d8010b15776ff1a1dde6622ee75425503773ea703803806e22c7352960d1f1.json, SHA256 1aad79f62de8502cf23fa8069225ca6d596c80a0c234357e1fd678bf7e3366bf, recording 505 passing tests.

The amendment preserves the original plan/freeze history, does not change E1/E2, and records that no generator refits were started by the amendment. It corrects the old E6 gate by separating five model-fit dependencies from E3 direct-evaluation reference outcomes. The six old zero-attempt gate-unavailable decisions remain preserved as superseded history. The 15 member-reference rows remain historical E3 results: 12 successful and 3 unavailable, including the KDE direct-evaluation timeout cases.

The six corrected primary E6-v2 tasks were published but each has one operationally invalid pre-posterior attempt caused by the GMM feature-order validator. Core is diagnosing the model pipeline metadata contract. Repair the defect under the qualified amendment, preserve each invalid attempt, then supersede only these six affected attempts once. Do not refit or retune E1/E2, do not expand E6 resource limits, and do not retry ordinary scientific timeout failures. After repair, validate the six overlay keys and task tags against the frozen overlay and require valid per-task provenance before launching any E6 posterior work. There are no valid E6-v2 performance outcomes, tuning-best comparisons, or ensemble weight findings yet.

Earlier prepublication integration/qualification tooling errors were operational and did not create scientific scores. An earlier attempted external guard had 19 failures and 479 passes; the subsequent qualified portable bundle records 505 passing tests. Keep these separate from experiment outcomes.

## Maintenance and resource provenance

A bounded cleanup reclaimed about 4.086 GB by removing only verified duplicate engineering virtual environments. The primary scientific environment was retained and source/test fingerprints were reported unchanged. A raw 1,800-second storage watcher was qualified with a 360-second cooldown and helper-based process identity checks. These are operational maintenance actions, not scientific results. Archive maintenance overlapped already-running science in earlier observations; do not attribute any timeout to that overlap without evidence. Timing is hardware- and shared-load-dependent.

## Remaining completion work

1. Repair the E6-v2 GMM feature-order metadata/preflight mismatch. Preserve the six operationally invalid attempts and evidence; supersede only those affected attempts after the fix is qualified.
2. Verify corrected E6-v2 fixed-policy phases and account for all six primary ensemble cases, including any scientific timeout, unsupported, or unavailable result. Do not retry ordinary terminal scientific failures or expand limits.
3. Finish the 187 waiting E4 and 228 waiting E5 planned cases, validating outputs incrementally and retaining all failures and unavailability states.
4. Complete project-wide calibration-q replay and conformal validation, then refresh final per-experiment and cross-experiment tables and figures. Include the E3 prior-test-exposure disclosure.
5. Build and verify the full EC2 archive and compact laptop package only after source/result coverage is current. No final archive or laptop transfer is claimed here.
6. Stop only project-owned workers and watchers cleanly after all authorized work is terminal; leave Harbor untouched.

## Reproduction and handoff paths

- Current progress command: cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025 && /usr/bin/python3 source/observe_progress.py --by-rep
- Current registry: runtime_20261025/registry.json
- Current controller source: runtime_20261025/source/controller.py
- Qualified freeze and overlay: runtime_20261025/manifests/freeze.json and runtime_20261025/manifests/E6_EXECUTION_OVERLAY_V2.json
- Effective E6 amendment receipt: runtime_20261025/manifests/E6_V2_EFFECTIVE_AMENDMENT_RECEIPT_20261028.json
- E3 validated report: runtime_20261025/reports/E3_FINAL_DESCRIPTIVE_REPORT.md
- E3 independent saved-results audit: runtime_20261025/reports/engineering_audits/E3_INDEPENDENT_SAVED_RESULTS_AUDIT_20261027T183300Z.json

The report is an interim, evidence-bound snapshot, not a completion claim. Refresh the observer and actual process verifier before making further status claims.
