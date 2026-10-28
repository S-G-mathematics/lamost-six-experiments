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
