# LAMOST six-experiment detailed continuation report

Current observation: **2026-10-27T06:26:26.784910+05:30 Asia/Kolkata**, 2026-10-27T00:56:26.784910+00:00 UTC.

This is an interim execution report. The project is not complete. The current section supersedes older counts, source pins and engineering attestation claims in the historical appendix. Scientific results and original reports are preserved.

| Experiment | Planned evaluations | Successful/evaluated | Scientific failures | Unsupported/unavailable | Pending/active | Phase |
|---|---:|---:|---:|---:|---:|---|
| Frozen E1 | 765 | 674 | 81 | 10 | 0 | Frozen benchmark finalized |
| E2 primary | 150 | 108 | 0 | 42 | 0 | Reporting finalized, primary coverage incomplete |
| E2 classical reference | 120 | 120 | 0 | 0 | 0 | Separate exploratory reference set |
| E3 | 69 | 64 | 3 | 2 | 0 | Terminal accounting; final qualification pending |
| E4 | 1773 | 1381 | 48 | 3 | 341 | Scientific queue active |
| E5 | 960 | 644 | 27 | 23 | 266 | Scientific queue active |
| E6 | 21 | 12 | 0 | 9 | 0 | Terminal accounting; final qualification pending |

E1 stopped recovery remains separate: **24 successful retries, 10 retry failures, 2 user-stopped partial cells, 55 not attempted**. No recovery outcome is substituted into frozen E1.

## Current actual process and storage observation

Host DMI was verified as i-095641a281a4038b9; established hardware is c7i.4xlarge, 16 logical CPUs. The actual controller was verified: True. Current controller SHA-256: 3306a15b3d246b7b169880a063ce52032488df3e5bf46c2710d78cae2e85c564. There were 4 verified workers, 26.56 GiB MemAvailable and 46.86 GiB free disk. These values describe this observation only. Heartbeat age is not liveness evidence.

- e4/rep_1/fit/treatment/random_forest/A_tenth_generated_arf: fit, 10.0 GiB provisional admission reservation, 506.2 seconds total elapsed. Individual trials and final phases each retain their own 600-second cap.
- e4/rep_1/eval/direct/rbf_svm/G_half: eval, 3.0 GiB provisional admission reservation, 44.0 seconds total elapsed. Individual trials and final phases each retain their own 600-second cap.
- e4/rep_1/fit/direct/rbf_svm/G_tenth: fit, 3.0 GiB provisional admission reservation, 42.0 seconds total elapsed. Individual trials and final phases each retain their own 600-second cap.
- e4/rep_1/fit/direct/rbf_svm/K_half: fit, 3.0 GiB provisional admission reservation, 40.0 seconds total elapsed. Individual trials and final phases each retain their own 600-second cap.

Storage admission status: allowed_by_current_recorded_estimate; recorded free-minus-minimum margin 974601323 bytes. Tight storage constrains dispatch. ADMISSION_HOLD belongs to bounded archive operations when present; an old STORAGE_HOLD marker alone is not a live scheduling lock. No unique model, dataset, role or Harbor artifact is deleted to force progress.

## Execution and operational changes since the preceding report

The existing controller continues the one durable scientific queue under tmux, with a five-minute watchdog and atomic registry/checkpoint writes. It owns all scientific scheduling. No duplicate queue was launched. User authorization removed the static two-worker cap; observed peak concurrency reached eight actual workers earlier in this continuation. Current concurrency is admitted from actual CPU, memory and unspent commitments, reserving capacity for the operating system and Harbor. It is not fixed at eight.

Reviewed provisional admission reservations now cover matching never-attempted E4/E5 direct KNN fits/evaluations at 2 GiB, native-margin RBF-SVM at 3 GiB, and eligible ARF evaluations/generation at 2 GiB. Matching E4 ARF fitting retains 6 GiB provisional admission; recorded other RF profiles are preserved. ExtraTrees and large synthetic RF fitting retain 10 GiB. All have the same later-experiment scientific hard policy: 10 GiB per fitting worker, 600 seconds per tuning trial and final fit/generation/prediction phase, 30-second grace, capped native threads and 50,000-row prediction chunks. Provisional reservations can be promoted when measured memory requires it. They are not scientific limit reductions or resource-relaxed scientific retries.

The two admission deployments restarted only the verified controller after atomic installation under owned launch holds. Existing fitting workers continued; no scientific worker was signaled. Exact frozen plan, role identities, search counts/domains, seed handling, models and evaluation definitions stayed unchanged. The 19 frozen E1 Python files and E1 ledger were checked unchanged at deployment. E1/E2 fitting, stopped E1 recovery, small-class ARF variants, saved-pipeline recovery finalizer, full historical backup retrieval, bootstrap, infrastructure changes and Harbor modifications remain excluded.

Completed-model storage continues to use reversible joblib/XZ encoding. Each accepted model reconstructs the original compressed joblib bytes and verifies logical SHA/size/CRC separately from the encoded physical payload. Existing raw archive members remain readable. Codec-aware readers must remain installed after encoded commits. One rejected byte-shuffle probe was larger and is not used. Full backup retrieval is not resumed.

The latest recorded BUILDING archive snapshot is ROOT/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip, **18956446999 bytes**, SHA-256 **c988e87801a8470e0f3b464d352b3b412402d1b36a0218f14eea79dc57ddec7d**, 84 model groups including 4 encoded. Manifest SHA-256 10a51376ecdeb8ffd2406f6c6920c6fe9d19e45de1f37e92c071e9b56b0e1009. This is not the final full project archive; later valid storage commits change its checksum.

## Engineering validation and the attestation correction

The final installed-source engineering suite passed **347 tests and 36 subtests**, zero failures, under a 1 GiB process-tree guard. Wall time was 18.435 seconds; peak tree RSS 457,293,824 bytes. Source, tests, runner, guard, environment and test-input manifest were byte-identical before and after that execution.

Current formal receipt: runtime_20261025/reports/PORTABLE_TEST_PASS_ad0d182c9f6b41a459c69de38b2369b0b0fb4fd5371de9e54d575acd546078bb.json; SHA-256 d5a4a567a4be0ec8050d3d1ac8ab887a5b2c464ba1d4303c1bbb1f88d73f50c6. Immutable manifest SHA-256: b9273619e98107586dc48deddc1bfeedf6c1e1fe496fa6b3247776b7b4847ccb.

An earlier post-run evidence annotation changed the hashed test-input manifest after genuine 342/347 passes. That bookkeeping mismatch was preserved and disclosed. Exact original input preimages were recovered with matching hashes, the input manifest was cleaned, and one final strict immutable 347-test run re-established current attestation. No scientific cell was invalidated or refitted. Run-output evidence is now external to the immutable input manifest. A process-exit identity race in the engineering guard was separately fixed and covered by six focused fixtures without weakening PID/start-tick protection.

Correction evidence: reports/engineering_audits/TEST_MANIFEST_ATTESTATION_CORRECTION_20261027.json (SHA33772c0eb0e2cdbf3c36f68903dca45c737388a21dd26407f9e6b153333649ab). Public final proof: reports/engineering_audits/FINAL_IMMUTABLE_347_TEST_EVIDENCE_20261027.json (SHAe0a8a72ed63ed50bcfa2d951648eaf99f4eed2910063286c79a24db64220b782). Exact current source/test SHA index is preserved in reports/engineering_audits; historical candidates/preimages are retained separately. Raw process receipts stay outside the public archive.

These are engineering checks, not a substitute for global scientific artifact and conformal threshold qualification. The production-wide externally supervised calibration replay remains pending.

## Actual repetition denominators

| Experiment | Repetition | Planned evaluations | Successful | Failed | Unavailable | Pending/active |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 1 | 23 | 22 | 1 | 0 | 0 |
| E3 | 2 | 23 | 20 | 1 | 2 | 0 |
| E3 | 3 | 23 | 22 | 1 | 0 | 0 |
| E4 | 1 | 591 | 524 | 20 | 1 | 46 |
| E4 | 2 | 591 | 452 | 14 | 1 | 124 |
| E4 | 3 | 591 | 405 | 14 | 1 | 171 |
| E5 | 1 | 320 | 218 | 9 | 1 | 92 |
| E5 | 2 | 320 | 216 | 9 | 21 | 74 |
| E5 | 3 | 320 | 210 | 9 | 1 | 100 |
| E6 | 1 | 7 | 4 | 0 | 3 | 0 |
| E6 | 2 | 7 | 4 | 0 | 3 | 0 |
| E6 | 3 | 7 | 4 | 0 | 3 | 0 |

## Scientific designs, findings and limitations

The later plan was frozen at 2026-10-25T04:46:31.018995+00:00, with 6,270 dependency/evaluation tasks and 2,823 unique scientific evaluations. tasks.json SHA-256 is 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb. E3/E4/E5/E6 have 153/4110/1986/21 total tasks respectively; scientific evaluation counts are 69/1773/960/21. Fits and generation dependencies must not be counted as completed scientific comparisons.

All use the saved baseline and role memberships, six established photometric predictors and seven labels, three paired 100,000-row development repetitions with 80,000 fitting, 10,000 tuning and 10,000 calibration rows, and the same fixed 500,000-source test cohort. IDs, labels, spectra and audit fields are excluded from predictors. Preprocessing is learned only from permitted fitting rows. Tuning selects configurations/weights; calibration determines finite-sample 90% conformal thresholds; test evaluates frozen procedures. E1/E2 test outcomes had already been observed before the later plan freeze; this is not an untouched prospective project-wide test set.

E3 compares direct Bayes, synthetic-only and shared real-only learning for five generators and three downstream learners (logistic regression, random forest, histogram gradient boosting). Exactly 400,000 synthetic examples per valid generator/repetition are shared across learners, with deterministic approximately proportional integer label allocation. Fit/generation/training/calibration/inference costs and model provenance are separate. Its 69 terminal evaluations include three KDE timeouts and two unavailable downstream cases; descriptive route differences retain actual matched counts. No new E1 fit was created.

E4 uses unchanged control plus half-share and one-tenth-share conditions for every target class, nested target subsets/shared other-class permutations and reserved tuning/calibration IDs. All 17 direct methods are compared. Three downstream learners compare untreated, original-proportion weighting, random oversampling, SMOTE and five generator-restoration treatments. The generator sees only the altered fitting cohort. All count-based restoration methods use the same added target count/final histogram, restoring original target share; SMOTE has an explicit multiclass count map and neighbor rule min(5,n_target-1).

The saved E4 completed-block report is a historical snapshot with 1,278 successes, 910 comparison strata and 570 complete three-repetition strata, including all partial/zero denominators. Root independently verified 5,919 BA/coverage/set-size paired calculations. For the explicitly described QSO one-tenth/logistic block, untreated mean BA fell 0.064055 and target recall 0.489904 versus unchanged. Several restoration methods recovered approximately 0.058-0.064 BA versus untreated, while Chow-Liu recovered about 0.005082. This is conditional on that target/severity/learner and completed repetitions, not universal benefit. The ARF arm was unavailable in that snapshot. Later cells are not silently backfilled into those frozen descriptive tables.

E5 corrupts fitting rows only, with paired nested 5%,10%,20% affected-row masks. Feature noise changes one feature using the frozen clean-fit IQR/1.349 scale and documented fallbacks; missingness masks one feature and learns the median imputer from incomplete fitting data, without a primary indicator; label noise always changes selected labels uniformly to another class. Clean-selected pipeline-specific configurations are frozen and refitted without retuning; calibration/test remain clean. E3-style synthetic-only routes retain 400,000 examples.

The direct RF block is fully accounted at 30/30 successful evaluations, 27 matched corruption differences and 210 class rows. At20% affected rows, mean BA changes are feature noise -0.010556, missingness -0.005531 and label noise -0.017309 (n=3 each). Coverage changes are +0.000101,+0.000130,+0.000416, and set-size changes +0.029072,+0.020881,+0.242023 respectively. Figures/tables are saved and reviewed. These are direct-RF descriptive results, not full E5 conclusions. Direct KNN block analysis waits for all30 validated outcomes; no incomplete block is presented as complete.

E6 compares equal five-member posterior weights with tuning-selected global simplex weights using the predeclared equal vector, five vertices,1,000 seeded Dirichlet candidates and bounded top-ten pairwise refinement. Normalized common-class-order posteriors are required. KDE member evaluation is unavailable for each repetition, so all six primary ensemble cases are unavailable; 12 successful member references plus three unavailable member references account for21 cells. No learned weights, primary ensemble advantage or optional partial-member sensitivity is claimed.

The frozen E1/E2 provenance, reconstruction differences, low-precision class flags, four complete fidelity-correlation strata, seven auxiliary-history discrepancies and historical artifact gaps are detailed in the appendix. Some original saved fits were available for E2; many historical E1 pipelines and test-row prediction arrays remain missing. Do not infer either that all original models are missing or that the historical collection was restored.

## Remaining execution, validation and delivery

Continue the existing E4/E5 queue with current actual resource admission and lossless completed-model storage. Ordinary terminal timeout/failed-search/unsupported outcomes are not automatically retried. All queued/interrupted/invalid cases retain explicit distinct states and evidence. Do not force models to succeed.

After all planned later cells are terminal, run the externally supervised complete artifact audit and saved-calibration score/finite-sample-threshold replay, validate cache identity and alias coverage, then review the final numerical reports, paired denominators, costs, figures and all negative results. Do not assert conformal efficiency without achieved overall/per-class coverage. Bootstrap stays dropped; descriptive SD/repetition variability is not a confidence interval.

The final deliverables must contain frozen E1, separate stopped recovery, E2 original/reconstructed diagnostics, E3-E6 plans/results/provenance/models and required data, full case/availability ledgers, figures and reproduction/limitation instructions. Exclude credentials, Harbor material and private operational process receipts. Verify full and compact ZIP CRC, byte size and SHA-256; copy/hash-check the compact ZIP in the existing laptop handoff directory. The historical full E1 wrap-up and snapshot remain preserved. Only then stop exact project-owned workers/watchers and declare completion.

## Historical detailed report retained for audit

The following report was observed at2026-10-27 03:45IST and is preserved verbatim from LAMOST_CONTINUATION_REPORT_20261026T221548Z.md. Its counts, source pins,329-test current-status sentence and BUILDING archive checksum are historical and superseded above. No old liveness observation is a present claim.

# LAMOST six-experiment execution report
Observed UTC: 2026-10-26T22:15:48.551202+00:00. Asia/Kolkata: 2026-10-27T03:45:48.551202+05:30.
This is a dated interim execution report, not a final project completion claim.

| Experiment | Planned | Successful/evaluated | Failed | Unsupported/unavailable | Pending | Phase |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | Finalized frozen benchmark |
| E2 primary | 150 | 108 | 0 | 42 | 0 | Reporting finalized; coverage incomplete |
| E2 classical | 120 | 120 | 0 | 0 | 0 | Separate reference evaluations |
| E3 | 69 | 64 | 3 | 2 | 0 | Terminal outcomes; final validation pending |
| E4 | 1773 | 1277 | 42 | 3 | 451 | Queue active |
| E5 | 960 | 622 | 27 | 23 | 288 | Queue active |
| E6 | 21 | 12 | 0 | 9 | 0 | Terminal outcomes; final validation pending |

The E1 early-stopped recovery supplement is separate: 24 successful retries, 10 retry failures, two user-stopped partial cells and 55 not attempted after the user stop decision. It is not a completed recovery study. It never replaces frozen E1.

## Actual execution and resources
The connected instance DMI is i-095641a281a4038b9; previously reverified hardware is c7i.4xlarge, 16 logical CPUs. The existing controller is verified from its actual process identity and live source SHA b0aa426dbcea53ead73014b6c61bfbc5f7b175a6f2bb839e9c69421a7d1a966a. All registered running workers were matched to actual PID/start ticks and exact request identity. There were 3 verified model workers, 25.04 GiB available RAM and 48.92 GiB free disk at this observation. These are observations, not reserved resources or predictions.

Current workers:
- e4/rep_1/fit/direct/arf/K_tenth (6.0 GiB admission reservation; 1888.4 seconds total worker elapsed)
- e4/rep_1/fit/direct/arf/M_half (6.0 GiB admission reservation; 1439.1 seconds total worker elapsed)
- e4/rep_3/fit/treatment/random_forest/A_half_smote (5.0 GiB admission reservation; 902.4 seconds total worker elapsed)

Total fit-worker time includes multiple trials and final phases. It is not the 600-second individual scientific phase limit. Model science limits remain 10 GiB per worker, 600 seconds per tuning trial/final fit/generation/prediction phase, 30-second termination grace, one nested native thread and 50,000-row prediction chunks. Adaptive concurrency has no static two-worker cap; it admits only work supported by current CPU and RAM commitments while retaining six GiB for host/Harbor plus a two-GiB growth margin. Admission reservations are not new scientific hard limits. No Harbor process was altered.

No E1 or E2 fit/retry was started, no stopped E1 recovery queue was resumed, no bootstrap was added, and no AWS machine/storage/security change was made.

## Frozen E1 and accepted E2
Frozen E1 remains 765 terminal: 674 successful, 81 failed, 10 unsupported. The 81 failures comprise 55 resource failures and 26 supervisor-terminal cases whose manifests remained started. Actual successful repetition denominators remain in the frozen complete ledger and summaries; no conditional-on-success result is presented as universal feasibility.

The latest lightweight recheck verified all 19 original benchmark source hashes, the frozen ledger SHA and ten startup evidence documents. It did not rehash the large historical archive. The finalizer independently requires archive identity and ledger-member checks again.

E2 has 108/150 primary generator evaluations and 120/120 separate classical reference evaluations. All 42 missing primary ARF/KDE cases remain unavailable; they are not reclassified as new algorithm failures. There are 19 original and 89 reconstructed primary fits; across all 228 evaluated cases, 43 are original and 185 reconstructed. Reconstructed models use their own measured classification performance. Of 185 reconstruction gates, 154 matched and 31 differed in classification accuracy (maximum absolute balanced-accuracy difference 0.000031739351391335546). These differences remain disclosed rather than rounded away or written into E1.

E2 contains 1,596 class reports and 210 low-precision flags, with zero recorded integrity errors. Equal-class aggregation preserves flagged classes. Only four of thirty budget/repetition strata have all five primary families (Spearman values 0.7, 0.1, 0.3, 0.7); these are descriptive and do not support a general fidelity-classification relationship or significance claim. Available-only correlations and classical references are separate exploratory analyses.

Historical fitted E1 models and per-test-row arrays omitted from the compact migration remain missing. Seven auxiliary tuning-history discrepancies affect documented 10k GMM and 30k CART/linear-SVM files; exact original full affected histories remain unavailable. Existing verified completion metrics are not invalidated solely by those auxiliary-history limitations. No missing history is invented, and the abandoned full-backup retrieval remains stopped.

## E3 through E6 scientific state
The immutable later plan contains 6,270 dependency and evaluation tasks, with 2,823 unique scientific evaluation cases. Plan SHA-256: 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb; original freeze UTC 2026-10-25T04:46:31.018995+00:00. All eleven frozen scientific/controller source hashes were checked unchanged at this observation.

E3 has all 69 planned evaluations accounted for: 64 successful, three scientific failures and two unavailable dependencies. Success counts by repetition are 22, 20 and 22 of 23 planned. The three failures are KDE prediction timeouts under the recorded limit. Descriptive route comparisons and actual denominators are retained; final global artifact/conformal replay qualification is still pending.

E4 has 1277 successful evaluations across controls, all seven target classes, two imbalance severities and the predeclared direct/restoration treatments. Its pending work is mostly dependency fitting and downstream evaluations. No queued case is called a scientific failure.

E5 has 622 successful evaluations. Its completed direct-random-forest block has 30/30 valid evaluations (three clean controls plus 27 corruption cases), 27 paired differences and 210 per-class rows. At 20% affected fitting rows, mean balanced-accuracy changes versus matched clean RF are approximately -0.010556 for feature noise, -0.005531 for missingness and -0.017309 for label noise, each with three paired repetitions. These are direct-RF-only descriptive findings; they do not establish full E5 completion or universal corruption effects. Coverage and prediction-set-size changes accompany these figures. No bootstrap or unsupported significance language is used.

E6 has 21 terminal planned cases: twelve successful member references and nine unavailable cases. A KDE member evaluation is unavailable in each repetition, so both five-member primary ensembles are unavailable in all three repetitions. No successful primary ensemble, learned weights or ensemble benefit is claimed. Later ensemble availability does not repair frozen E1.

## Lossless storage and operational defect fixes actually completed
Reviewed production storage readers/writers, extracted-archive access, audit/export identity checks, calibration supervision and delivery cleanup were installed after 329 engineering tests and 26 subtests passed on EC2 under bounded resources. The exact test receipt matches current installed sources, manifest, test hashes and environment policy. Engineering fixtures are separate from scientific outcomes.

The installation did not restart or signal the controller or fitting workers. An initial receipt-publication KeyError occurred after correct source copying; it was resolved under archive leases with independently verified test-log hashes. Source/backups and incident evidence were preserved. A calibration-beacon timing race was deterministically reproduced and fixed by taking a fresh monotonic observation after reading the beacon, retaining strict PID/nonce/future-time and scientific-limit checks.

The first real reversible compressed-model transaction completed successfully. An independent read of the production archive reconstructed all 240,281,269 original compressed joblib bytes, with SHA-256 6ebb57bf9bcec539e7ab6b6ee784a78d78066b6d43bbea3d96ad2d693075d6ad, matching the recorded original exactly. The encoded payload is 146,306,320 bytes, saving 93,974,949 payload bytes (39.11%) for this one model. This is not a general capacity guarantee. No model deserialization, scientific fit or test inference was needed for this verification. Physical aliases were removed only after the verified commit.

The encoding keeps logical original byte size, SHA and CRC separate from physical encoded payload identity. Existing raw archive members remain readable. Extracted archive restoration decodes one requested model at a time and verifies original identity. Readers must remain codec-aware after an encoded member commits, even if future writes revert to raw. A separate byte-shuffle compression probe increased size by 6.56% and was rejected; it is not used in production.

The BUILDING archive snapshot is 18,514,112,715 bytes at ROOT/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip, SHA-256 1569d74adf823fb008f9c4a24125669ff5bddbadadb56ad6693ea8c7268a934b, with 81 stored model groups (1 encoded). This checksum identifies that observed building snapshot only; later commits legitimately change it. It is not the final full project delivery.

## Validation and completion still required
All scientific artifacts must pass the final full artifact audit. Saved calibration thresholds require externally supervised replay on saved calibration rows, exact finite-sample rank and score conventions, complete physical/alias coverage, and a fresh qualification receipt. The full production replay has not yet run. A previous single saved-logistic numerical check matched its threshold exactly but had invalid engineering supervision; it is not accepted as global qualification.

After E4/E5 terminal accounting, root must review report numerics, per-class outcomes, paired denominators, timings and figures. The final full archive and compact reports-and-tables archive must pass CRC, byte-size and SHA checks. Compact delivery must be copied/hash-verified on the laptop when accessible. Then only exact project-owned watchers/workers may be stopped; Harbor remains untouched.

The dataset/roles and the six predictors remain unchanged. E1/E2 test outcomes were already observed before the later plan freeze; no claim of an untouched prospective project-wide test set is made. Cross-experiment timing comparisons must acknowledge hardware and resource-policy differences. Missingness, failed difficult cases and success-conditioned comparisons remain explicit.

## Evidence and continuation
- Current machine-readable continuation: runtime_20261025/reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json.
- Independent encoded-model proof: runtime_20261025/reports/engineering_audits/FIRST_REAL_ENCODED_MODEL_VERIFIED_20261027.json; SHA-256 4e35d199e08134ec2de9ac7c8e37db61ac3c52706f209201d112af70d5ac61f2.
- Installed-code test pass receipt: runtime_20261025/reports/PORTABLE_TEST_PASS_b3377e1bda57b615a06eba269136dd2edd8b8996e7f1ce55d175edbb04b9d696.json; SHA-256 7282c10ed0475259ee911f3de6afef8fcfc0dce188a25b6150d7d9593e01c86c.
- Production storage status: runtime_20261025/reports/engineering_audits/LOSSLESS_STORAGE_PRODUCTION_STATUS_20261027.json; SHA-256 a5d5aab945b52fa1601d9e60c9de24069425a4eac9b43ed7629bae51b01aa275.
- Frozen E1/E2 lightweight recheck: runtime_20261025/reports/engineering_audits/FROZEN_E1_E2_LIGHTWEIGHT_RECHECK_20261027.json.
- Existing progress/reproduction docs: runtime_20261025/RUN_RESUME_REPRODUCE.md, AIRBAG_OPERATIONS.md and FINAL_COMPLETION_EVIDENCE_CHECKLIST.md.
- E5 direct RF report/tables/figures: runtime_20261025/reports/e5_direct_rf_block_20261027/.

Continue the existing EC2 controller; never launch a second scientific queue based on old heartbeat files. Read actual process identities and current indexes first. Do not reopen frozen E1/E2 fitting, bootstrap, stopped recovery or the abandoned backup effort. Do not declare the project complete from this interim report.

