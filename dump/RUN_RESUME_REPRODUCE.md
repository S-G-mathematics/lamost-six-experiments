# LAMOST runtime: airbag recovery and reproduction

**Archive safety:** An extracted archive is a read-only scientific reproduction snapshot. Its registry.json and public_registry.json files are sanitized terminal report projections, not the controller database. Do not initialize, watchdog, or resume the controller from an extracted archive, and do not rerun terminal cells from it. Descriptive report regeneration is supported from the extraction root. Operational resume applies only to the original EC2 project directory with its retained SQLite state, verified ownership lock, and live-process checks.

All scientific execution uses the existing EC2 and its established venv. Frozen E1 source is read-only. Primary entrypoint: source/controller.py. Read manifests/authorization_and_decisions.json, manifests/freeze.json, manifests/tasks.json, status.json and registry.json first.

Primary controller: tmux session lamost-project. Five-minute watchdog: the user crontab entry tagged LAMOST_PROJECT_AIRBAG. User lingering is disabled, so tmux/cron were selected without changing security settings; installed user-systemd definitions are retained as operational alternatives, not the active launcher. Actual PID/start-ticks and ownership lock determine liveness; heartbeat age alone does not. Controller uses one SQLite writer, atomic JSON exports, adaptive CPU/RAM-aware worker trees after the explicit user concurrency amendment (initially at most two), bounded science limits and phase checkpoints. Scientific failures are not retried. Operationally invalid outputs require reviewed code repair with preserved evidence before resubmission.

Resume: verify host i-095641a281a4038b9, source/plan hashes, actual live processes and lock. Then invoke the controller watchdog once using the established venv, or start tmux session lamost-project with /bin/bash runtime_20261025/run_controller.sh only after verifying no matching controller is alive. Do not launch separate workers manually. The controller adopts verified running requests and validates saved outcomes before resuming interrupted work. A code-hash hold requires an explicit reviewed freeze amendment; do not blindly remove it.

Progress: venv/bin/python source/controller.py status (use full venv path in migrationroot). Final artifacts include compact per-row prediction outcomes; set_mask packs labels0..6 into the lowest seven bits of uint8. Saved models retain preprocessing,selectedparameters,seeds anddataidentity. Source/cache/manifests are needed for reproduction. In the full archive, runtime files keep native paths under `runtime_20261025/source`, `runtime_20261025/tests`, `runtime_20261025/cache`, and `runtime_20261025/artifacts`; extracting and running `restore_archive_aliases.py` restores only content-deduplicated aliases and requires no directory rename map. No bootstrap is used. Allplots and reports are descriptive, with actual successful denominators.

Historical E1 models/predictions absent from the compact handoff are still absent unless explicitly identified as E2reconstructions. The stopped E1recovery supplement is notprimaryE1. The approved newE3-E6policy10GiB/600s differs from E1 6GiB/180s. Harbor is unrelated and must notbe touched.

## Internal report review checkpoint

The finalizer pauses at `REPORT_READY_FOR_AUDIT.json` for the root agent's internal scientific review. See `FINAL_REVIEW_RUNBOOK.md` for prepare, refresh, and receipt commands. This is not a user approval step.


## Regenerate descriptive report from the full archive

From the extracted archive root, first run `python3 restore_archive_aliases.py`. The full archive includes `runtime_20261025/registry.json`, a privacy-curated terminal report projection, plus `public_registry.json`; this is not the original live controller registry or SQLite database. Runtime `source`, `tests`, `cache`, and `artifacts` retain their native paths. On EC2, run `/usr/bin/python3 runtime_20261025/source/report_cli.py` from the extraction root to regenerate descriptive report tables. This uses saved outcomes and artifacts and does not fit, generate, or evaluate models.


The included final report and validated `costs.csv`/`cost_summary.csv` are historical observations. Private phase-supervision receipts and phase JSON were excluded or curated; regenerating the descriptive report may not reconstruct every historical phase cost byte-for-byte. Preserve the supplied validated reports and tables. If regenerating, work on an extraction copy.


E3 original NPZ container restoration and serialization-validation evidence is supplied as allowlisted, privacy-curated provenance with source SHA-256 values. The nine NPZ entries retain current/restored hashes, core-array and CRC comparisons, and the fallback-mask-only difference; the related serialization incident retains scientific resource/validation facts. Private request/result/process receipts are excluded. Restored original containers are stored under `runtime_20261025/artifacts/_restored_original_e3_containers/`.

Current concurrency: see manifests/concurrency_user_authorization_20261025.json and freeze.json resource_policy_history. The user removed the static two-worker cap. New adaptive workers use nice +10; the scheduler preserves six GiB for OS/Harbor, two CPU cores of measured headroom, bounded memory reservations/growth protection, and unchanged 10 GiB/600-second scientific limits. Never relabel old attempts as using the new policy.


## Prospective E4 direct Random Forest admission estimate (26 October IST)

The source plan, E1/E2 results and scientific engine are unchanged. At2026-10-25T19:38:09Z the controller alone was handed over to the reviewed scheduling implementation; allfive verified preexisting model workers remained live, with no worker signals.

The operational admission profile e4-direct-rf-80k-admission-4gib-20261026 reserves4GiB only for never-attempted E4 direct Random Forest fitting cells among the42 declared altered80k-row cohorts, with exact repetition/condition/cohort-key checks. It does not apply to synthetic, weighted, oversampled/SMOTE, generated-restoration or otherwise unmatched fitting routes. Existing attempts retain their historical reservation. Newly assigned reservations and profile IDs are persisted outside scientific task/request definitions in each registry attempt resource profile; checkpoint recovery preserves the profile and any promotion.

This estimate is NOT a lower memory limit. The scientific process-tree aggregateRSS cap stays10GiB; trial/phase timeout600seconds; one nested native thread;50k prediction chunks;30second termination grace. Default heavy reservation10GiB, light2GiB, host/Harbor6GiB reserve,8GiB admission pause,2GiB commitment-growth margin, measuredCPU admission and guard remain. Charged PSS (capped by RSS) is bracket-sampled for admission/promotion; observed growth can promote to10GiB. Ordinary scientific terminal failures are not retried under an expanded policy.

Evidence: three complete E3 realRF repetitions and one E4 altered-cohort RF fit had phaseRSS maxima about1.97GiB (2,020.7MiB). The4GiB estimate is provisional, not a worst-case bound; separately measured parent-side validation memory is unavailable. Do not silently generalize it to other workloads.

Read manifests/freeze.json admission_reservation_history, reports/engineering_audits/E4_DIRECT_RF_ADMISSION_EVIDENCE_20261026.md, and E4_RF_ADMISSION_PROFILE_APPLIED_20261026.json for source/evidence hashes and scope. Confirm a new worker's actual process identity plus persisted attempt profile before claiming that it is using the4GiB reservation. Do not restart an existing worker to obtain the new profile.


## Current prospective admission profiles: 26 October 2026, 06:30 IST

These are scheduling reservations for new, never-attempted tasks, not new scientific memory limits. Exact eligibility is enforced by source/admission_evidence.py. Existing attempts keep their recorded profile. The immutable task plan, scientific engines, frozen E1 source, and original experiment freeze timestamp are unchanged.

| Eligible workload | Provisional reservation | Boundary |
|---|---:|---|
| E4/E5 direct GMM, copula, Chow-Liu fit | 2 GiB | Validated matching 80,000 x 6 cohort and fixed/tuning selection policy |
| E4 direct RF fit/evaluation | 4 GiB | Matching validated altered 80k cohort; evaluations require the matching published selected fit |
| E5 direct RF fit | 4 GiB | Matching 80k corruption cohort; same-repetition E3 real-RF selected200-tree config; no retuning |
| E4 nonweighted downstream RF treatment fit | 6 GiB | Validated restored training artifact with80,000-82,394 rows and six features; weighted/larger/400k synthetic RF excluded |
| E5 GMM, copula, Chow-Liu, KDE generation | 2 GiB | Exactly400,000 output rows; validated matching selected generator, actual80k training labels/class counts and clean-selection provenance |
| Other heavy work, including ARF fitting/generation, ExtraTrees, KNN, RBF-SVM and unproven sizes | 10 GiB | Existing default policy retained |

A downstream RF trained on a small restored dataset can qualify for the6GiB RF profile even if ARF generated its restoration rows; the ARF fitting/generation worker itself remains at10GiB. All hard worker limits remain10GiB aggregate process-tree RSS,600seconds per tuning trial/fit/generation/calibration/prediction phase,30seconds grace, one native library thread and50k prediction chunks. The scheduler retains6GiB OS/Harbor reserve,2GiB growth margin,8GiB admission floor and measuredCPU headroom; growth beyond a provisional estimate promotes the worker reservation to10GiB. Ordinary terminal failures are never retried to obtain a new profile.

Provenance: manifests/freeze.json admission_reservation_history; reports/engineering_audits/BOUNDED_80K_GENERATOR_2GIB_ADMISSION_APPLIED_20261026.json; RF_AND_E5_GENERATION_ADMISSION_APPLIED_20261026.json; RF_FIT_ADMISSION_EVIDENCE_20261026.json; E5_GENERATION_ADMISSION_EVIDENCE_20261026.json. The RF/treatment/generation estimates remain provisional and their phase-versus-parent memory limitations are disclosed in those records. Historical lower RSS observations in earlier sections are dated evidence, not current worst-case bounds.

Storage work is staged only. No model has been compacted or moved into an archive backend. Do not run staged FUSE or cold-ZIP prototypes on real artifacts without the remaining source, dependency, process, recovery, validation and packaging gates. The final project archive and completion review remain pending.


## Admission and case-index updates recorded on 26 October 2026

The scientific E3-E6 limits remain 10 GiB aggregate process-tree RSS, 600 seconds per tuning trial/final-fit/generation/calibration/prediction phase, and the documented termination grace. Admission reservations estimate concurrent memory commitments; they are not altered scientific limits, guarantees, or a reason to rerun a terminal case.

- Never-attempted, fully matched E5 direct RF evaluations can use the recorded provisional 4 GiB inference admission profile. Exact baseline/source pipeline and role/test/cache identities are checked. The missing E3 rep-1 baseline publication receipt excludes that repetition from this narrower profile; its E5 evaluations retain the default 10 GiB reservation and remain schedulable.
- Never-attempted E4 nonweighted RF treatment evaluations in the validated small-input envelope can use the recorded provisional 6 GiB inference admission profile. These inference tasks are eligible for light-job packing; fitting stays in the heavy lane.
- Never-attempted E4 nonweighted RF treatment fits already satisfying the previous 6 GiB artifact gates can use a provisional 5 GiB reservation only within 80,611-82,394 rows and the recorded ROS/SMOTE/generated-GMM/copula/Chow-Liu scope. The pinned review covers 25 completed fits, 202 executed tuning phases and 25 selected final-fit phases; the largest recorded phase peak was 3,907,392 KiB. This finite observed evidence is not a worst-case guarantee. Other treatment/fitting scopes retain their previous 6 GiB or default 10 GiB reservation.
- Existing attempts retain their recorded profiles. Any observed overrun of a provisional reservation promotes that worker's reservation to 10 GiB and pauses additional admissions for remeasurement. CPU/native-thread limits, host/Harbor reserves and emergency memory guards remain active. Scientific accuracy was not used to choose these admission estimates.

The companion overall scientific case index has 3,858 main rows: 765 frozen E1, 150 E2 primary, 120 E2 classical references and 2,823 E3-E6 outcomes. The 91 stopped E1-recovery rows remain a separate group, giving 3,949 total index rows. Execution dependencies are separate: the controller DAG has 6,270 tasks. Do not confuse successful fit dependencies with successful scientific evaluations.

The data-only index builder is source/build_overall_case_index.py. It accepts --root, --runtime and a NEW --output version directory under reports/overall_case_index; it publishes an atomic CURRENT.json pointer. Counts are read from a coherent read-only SQLite snapshot and live workers require kernel PID/start-tick/entry-point/request identity proof. A lagging JSON export is diagnostic only. Refresh after terminal execution before final review; never treat an old index or heartbeat as a liveness observation.

A newly performed one-model independent audit passed for E3 real-only RF repetition 1 with no issues. It did not recreate the missing historical fit_publication.json or execute predictions. The exact scope and receipt are recorded in reports/E3_RF_REP1_PUBLICATION_LIMITATION.md. This is not a substitute for the required final project-wide model and outcome audit.


## Installed delivery tooling and measured-resource follow-up

All eleven validated cold-reader/reporting source ports are installed in runtime/source, including the complete condition-findings builder and finalizer integration. They load from sibling installed source files rather than a staging-code fallback. Portable delivery engineering tests are in runtime/tests; from an extracted archive root on EC2, select the recreated Python environment with LAMOST_TEST_PYTHON and run:
    
    bash runtime_20261025/tests/run_portable_tests.sh

This explicit bash invocation also works when ZIP extraction does not restore executable mode bits. The original86 relocated tests use tiny existing synthetic joblib fixtures and two public resource-review JSON fixtures; they do not run research experiments or use fitted research models.

The later 5 GiB RF-fit scope amendment also includes RF trained on KDE-restored data for A_half, GALAXY_half/tenth and QSO_half/tenth across paired repetitions 1-3, with the same 80,611-82,394-row, never-attempted, frozen-domain and input-hash gates. The pinned 25-fit review already contains five such RF/KDE-data cases. This is not a change to the KDE generator/classifier algorithm, and no terminal KDE timeout is retried. Existing attempts retain their previous profile; out-of-envelope cases keep the older reservation.

A read-only shared-host review recommended keeping the existing six-GiB host/Harbor reserve, two-GiB commitment growth margin and eight-GiB admission floor. No reserve reduction was applied. Measured headroom, not idle CPU alone, limits current concurrency. A historical top-process sample or absence of running Docker containers is not a guarantee about future Harbor demand.

Two RF fits received checkpoint-preserving headroom interruptions at 2026-10-26 05:39 UTC. One later finished successfully; the other recovery worker was kernel-verified live at 05:51 UTC. Their scientific task definitions, model seeds and nominal trial budgets were identical across attempts; old workers were absent. Each had one operational recovery. These are not scientific failures and do not authorize retrying ordinary terminal timeouts.

At 2026-10-26 06:15:25 UTC, the first actual 58,703,060-byte completed E4 RF model was retained byte-for-byte in packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip. The transaction e533e75765cd49d792db66c0e2514d54 completed its journal, SHA/CRC and durable manifest verification before replacing its three native hardlinks; a fresh ColdModelStore resolved all three aliases to the original SHA c49d88a0e75c0a80370c1e74defeb1b7d81497f3f7e37f8da0bd2b6bef92c211. The first-prefix ZIP size was 58,703,498 bytes and SHA 441a0801749ed2192370c9f17d9aaefbbc7f31da75e1a129630737ef0db47793; later validated appends will change whole-archive size/hash. See reports/engineering_audits/FIRST_COLD_RF_MODEL_COMMITTED_20261026.json. This BUILDING prefix is not the completed overall delivery. Use the installed cold-aware artifact readers; do not refit a terminal case because its native model path has moved into the verified ZIP. Preserve the journal and resolve any pending transaction before another append. ZIP_STORED moves original compressed model bytes and avoids a second final-package copy; it does not itself reclaim net disk space.


## Latest applied controller and archive progress — 2026-10-26T12:48:27.083844+05:30

The controller resource-profile/grace amendment is already applied; do not rerun its deployment script. Current controller 13f914122345bd4f24fbed7b5ab0a4439a02ab869248f7b5db9cb1d8bda9889f and helper 44bdeef607dac4937a25c33b711d0f42375d6094845c83718e61ad0df7235e5b. New matching80k ARF fits reserve6GiB, weighted80k RF5GiB, and permitted nonweighted RF5GiB through84,310rows with the third pinned audit. Existing attempts keep their recorded reservations. Host6+growth2/floor8/hard10/600-second limits and scientific task plan remain unchanged.

The BUILDING ZIP now has17 RF models after three complete transactions; current prefix size1,217,009,037bytes and SHA3bad81c5e43efd006bf4c16263314422d22f78f055b624e8dff3aa47471b6d1d. The installed one-shot run_batch.py/commit_batch_child.py pins were updated to the current controller; there is no automatic compaction daemon. Archive all models only after checking complete consumer closure and actual process absence.

All110 selected portable engineering checks passed using frozen scientific dependencies first in import order and existing plotting support afterward. See tests/README.md and source/reporting_support_environment_20261026.json for the exact command and environment. The original isolated venv alone lacks Matplotlib; scientific worker files remain unchanged.

Fresh detailed snapshot: LAMOST_PROJECT_PROGRESS_20261026T071827Z.md. Keep executing E4/E5 and all final validation/reporting/delivery requirements. This is not project completion.


## Applied cleanup-state guardv2 — 2026-10-26T13:11:08.683187+05:30

Currentcontroller 44dc08e2f6af9bc6acb237b4b85827612e5c69055d197b5af960008d803b1514. RecordedTERMgrace nowalso covers fully exited tasktrees waiting for the nextregistrycleanup pass. It makes no livenessclaim; all actualtarget/watchdogidentity checks remain. Criticalfloor6GiB,host6+growth2/floor8,hard10GiB/time600 and all scientificdefinitions stay unchanged.112relocatedportablechecks passed. Do notrerun either already-applied controllerhandover. Latestaddendum LAMOST_EXECUTION_ADDENDUM_20261026T074108Z.md; use lightweight source/observe_progress.py --by-rep for currentstate.


## Continuation 20261026T162307Z

Current SQL/process observation is in reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json. Weighted-mean metadata gate helper755719 is applied; frozen plan/scientific settings are unchanged. The cold auto-compactor sourcebaf85 is installed with exact5-minute LAMOST_COLD_STORAGE_AIRBAG cron; delivery cleanup12e927 removes only its exact owned entry alongside existing2owned entries. First scheduled run16:20UTC backed off for helper memory; no wrapper launched. Do not infer archive work from cron existence. Inspect actual driver result, nonce, PIDticks and transaction journal/manifest before claiming commit. Native model custody/archive3.36GB prefix is retained, not a final package. Calibration threshold replay remains staged and has not run. Do not complete project until required independentq proof, full artifact audit, final numerical/figure review, full/smallZIP CRC/SHA, laptopdeliveryverification and exactowned shutdown pass.


## Calibration validation installation 2026-10-26

Five reviewed source modules installed, receipt reports/engineering_audits/CALIBRATION_VALIDATION_GATE_INSTALLED_20261026.json (SHA2a8353376694b90066784e2dd62cc1db9562c3016c61113f2ae7c18968386b75). Controller/worker/science source hashes unchanged. The immutable rawq audit remains complete:false; finalization requires externalnonce/process/600second/10GiB sampledRSS proof plus separatequalification and fullcasecoverage. Rawprivatephaseledger remains EC2-only; publicarchive preserveslocator/hash andsanitizedphaseproof. Freshcalibration-only replay reproduction instructions: reports/CALIBRATION_REPLAY_REPRODUCTION.md. One nativeLRrep1q smoke matchedexactly0.78201672186566, n10000,k9001; its customparent hitexitidentityrace aftersuccessfulchild, so supervisionisexplicitlyinvalid andnotglobalqualification. Preserveoriginalevidence under runs/calibration_lr_engineering_20261026T164226Z. Productsupervisor nowhandlesexit-race withdeterministictest. Historical145testreceipt isbeforethisvalidatorinstallation; do notclaimitcoversnewcode. Core18andguard62fixturespassed; combinedportablecurrentbundle/fullrun stillpending. A final-report Python environment amendment isbeingstaged toreplace systemNumPy withscientificvenv-first precedence, withplottingdepsaftervenv.


## Current validated engineering and interim output checkpoint — 2026-10-27T00:39:04.779308+05:30

The deployed exact-source portable bundle passed 195 tests, zero failures, and 17 subtests under the recorded external guard. The production portable-receipt gate was rechecked against current source/test/manifest/runner hashes; the accepted receipt is reports/PORTABLE_TEST_PASS_47544a81b16fc60489bac8a5f496a48fde06b10af9eb9586bdd4256bfb6b5e55.json (SHA-256 e5709dda23475ffabcb35043182e2e8dc3a5d29cc30f67ee4e1ccc8e8a59b4e9). Original wrapper parser false negatives and earlier fixture failures remain preserved as private operational evidence. This does not replace full production calibration replay, full numerical candidate review, or final archive validation.

E5 direct random forest has a complete, separately reviewed 30-case block with 27 clean-paired corruption comparisons, all three repetitions and all nine conditions. See reports/e5_direct_rf_block_20261027/ and ROOT_FIGURE_REVIEW_20261027.json. The rest of E5 and E4 remain in progress. Do not mark project complete from this checkpoint. The latest continuation JSON contains fresh process-verified counts and cold-archive observations.


## Reviewed lossless model storage and replay guard — 2026-10-27T03:28:03.200769+05:30

The installed exact-source engineering bundle passed329tests and26subtests. See reports/PORTABLE_TEST_PASS_b3377e1bda57b615a06eba269136dd2edd8b8996e7f1ce55d175edbb04b9d696.json (SHA-256 7282c10ed0475259ee911f3de6afef8fcfc0dce188a25b6150d7d9593e01c86c). Scientificfit sources, frozenplan/E1 and model resource limits are unchanged; the controller and scientific workers were not restarted. Full scientific calibration replay and final delivery remain pending.

Completed eligible RF models may use reversible XZ storage of their raw zlib payload. Original joblib SHA/bytes/CRC remain logical identity, with physical encoded SHA/bytes/CRC and pinned recipe stored separately. The opt-in cold cron uses reversible-xz-v1, one inode group and at most1GiBsourceperbatch; storagechild600s/896MiBAS/1GiBsampledRSS are operational bounds, separate from10GiB/600sscientificpolicy. Actual reads reconstruct and verify exact original bytes. Rawlegacyentries remain supported. Never revert to raw-only readers after any encoded entry commits.

Archive-only access uses public member projection and on-demand bounded decoding; defaultrestorer skips persistent encoded expansion. Recreate Python3.12.3 withzlibcompile/runtime1.3 and joblib1.5.3 compressor source SHA1830d526678e06a7ed73ab4c903ba9af2a231e193f8c857c5ab3683224f14dd4 plus scientificdependencylock. Avenvdoesnotchangeitslinkedzlib; incompatibleversionsfailclosed. Atoyarchive fresh-subprocess smoke passed; this is not full scientific report/calibration qualification.

Current actual first-byte-checkstate is in logs/operational/codec_first_20261026T215446Z_d2ef0797/state.json. The 329-test proof corrected archivepayloadlookup, recipeprojection, nativebadfilefallback, beacon observationclock, exact-owned cleanup, and source-scanner falsepositive. Failed engineeringattemptsremainprivateevidence. No statisticalbootstrap was added.


## Verified production update 2026-10-27T03:45:48.551202+05:30
329 tests plus26subtests passed and exact installed hashes match. First real encoded archive model independently reconstructed original SHA 6ebb57bf9bcec539e7ab6b6ee784a78d78066b6d43bbea3d96ad2d693075d6ad; saved93,974,949 bytes for this model. See reports/engineering_audits/FIRST_REAL_ENCODED_MODEL_VERIFIED_20261027.json. Full scientific calibration replay and final project delivery remain pending. Never revert to raw-only readers after encoded commit.


## Live scheduling amendment: 2026-10-27T04:42:07.455473+05:30
The controller-only graceful restart installed the reviewed ARF scheduling profiles. No fitting worker was signalled. Current controller source SHA is bf17eb7983080c35b70a6460c3c9a11a0e855097bce8d0ec0044757e4f5dea7f; admission source SHA is 8c532f99c6c18998321141d4c52f7eaa92ea53bc5d78a6ecc11aae9492992504. All original frozen E1 Python files and the 6270-task plan remain unchanged.

The new profiles apply prospectively to never-attempted validated models only: E4 direct ARF evaluation with a pipeline at most34,000,000 bytes; E4 ARF target-only restoration up to45,955 rows; E5 ARF all-class generation exactly400,000 rows. Each uses a provisional2GiB scheduling reservation. E5 support is an indirect analogy to E3, not a directly measured E5 maximum. The common hard scientific policy remains10GiB/600seconds per phase,30seconds termination grace, one native thread and50,000-row prediction chunks. Dynamic promotion to10GiB remains active when a profile exceeds its reservation. ARF fitting reservations remain6GiB; all existing attempts keep their prior profiles. There is no static two-worker cap; CPU/RAM commitments and host/Harbor reserves control admission.

The exact installed engineering suite passed342 tests and30subtests. Receipt: reports/PORTABLE_TEST_PASS_f34ee8f7a68c0d876c72d1d3f8771b72b22771f2b83de6c1a565d42b01951e8e.json, SHA-256 0b98fd702c61d0940832e3e13687d5f0a8a13e5ce027856f9bb2268b7bea1cec. Its fingerprint matches current installed sources/tests/proofs. The engineering guard now distinguishes a verified normal child exit from a changed or unverified live process; missing RSS is accepted only for an exiting/zombie process with preserved stat identity. The failed earlier collection remains preserved privately; it was not a scientific failure.

Actual use was independently verified after detaching: four live model workers, including e4/rep_1/eval/direct/arf/A_tenth under the new2GiB reservation. Its scientific task fields match the frozen plan; only the artifact directory is materialized from runtime-relative to the exact runtime-absolute path. See reports/engineering_audits/FIRST_ACTUAL_ARF_2G_PROFILE_OBSERVED_20261027.json. Started is not completed.

The resource-audit narrative erratum retains the original pinned audit bytes: K_tenth used5 tuning trials (3successes,2trialfailures), followed by a successful final fit. Its recorded trial peak remains4,451,628KiB. This does not modify scientific results, trial policy or profile evidence maxima.

Full scientific artifact/calibration replay qualification, E4/E5 terminal accounting and final archive/delivery remain pending. Keep codec-aware readers after an encoded model commit. No further E1/E2 fits, bootstrap, stopped E1 recovery or abandoned backup retrieval is authorized by this amendment.


## Current continuation correction: 2026-10-27T06:26:26.784910+05:30

Current controller3306a15b and admissionf6fa21b5 implement the reviewed ARF evaluation/generation, KNN2GiB and RBF3GiB provisional admission profiles; ExtraTrees remains10GiB. These reservations do not alter the scientific10GiB/600s hard policy, seeds, roles, trials or frozen plan. No E1/E2 fitting/recovery or bootstrap is authorized. Current exact engineering proof is PORTABLE_TEST_PASS_ad0d182c9f6b41a459c69de38b2369b0b0fb4fd5371de9e54d575acd546078bb.json:347tests+36subtests passed, manifestb9273619 unchanged before/after. Post-run evidence belongs outside the immutable test-input manifest. See reports/engineering_audits/TEST_MANIFEST_ATTESTATION_CORRECTION_20261027.json and FINAL_IMMUTABLE_347_TEST_EVIDENCE_20261027.json. This is engineering qualification only; production-wide saved calibration-threshold replay remains pending. Continue actual process/identity checks and storage-aware scheduling; never retry ordinary terminal scientific timeouts. BUILDING archive metadata is mutable and not final delivery. Read LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json for timestamped current counts, real workers and archive snapshot.


## Installed RF admission update: 2026-10-27T08:03:04.550712+05:30

The reviewed E4 generated-restoration RF admission estimate is installed. Only never-attempted matching tasks with validated, review-bound append provenance and at most125,934 training rows may use6GiB; larger, missing or mismatched cases retain their prior reservation. Existing attempts keep their recorded policy. The scientific10GiB hard limit,600-second per-trial/per-phase limit,30-second grace, one native thread,50k prediction chunks and dynamic promotion are unchanged. Controller SHA=38c1c3a1302088a773c4328ca8d7e08db9179c33bf4a4d030e480a09ac1c059c. Current exact engineering qualification is362tests+41subtests, immutable manifestb83dce2cbddcaa87e628007052110e74bd8365a1eade37837a797524ad7d6a04, passreceiptce11f81fe73268d912453f2c10df46e749db785207aeaf54448602d9cbfdfb9c. The earlier fixture-path failure and output-parser correction are preserved separately; zero scientific cases were affected. Full production-wide saved-calibration replay remains pending. Read the latest machine continuation and installed receipt before using old source pins. Never edit the test-input manifest to append post-run evidence. Keep codec-aware readers after any encoded archive commit.


## ARF dependency scheduling update: 2026-10-27T10:31:00.039560+05:30

The reviewed controller now prioritizes a dependency-ready direct E4/E5 ARF fit using its existing 6 GiB admission profile when none is active. It waits for naturally completed jobs to release memory before admitting more fits that would consume that space. Non-fit sinks remain eligible. No worker is preempted, no two-worker cap is introduced, and the existing hard memory/time limits, CPU guards, host reserve, growth margin, seeds, trials and scientific source remain unchanged. Current dispatch policy is cross-exp-stage-and-arf6-ready-lane-20261027-v1. Current engineering proof is 371 tests plus 41 subtests, immutable manifest 7ab8c68f7a0b19aa63ffa434b0c6e19bdff5633ca537aee6e87c633377754aac, pass receipt 78e8b8938fa925538c3412f4f9cbb5497a1b53e57b667372e0269622ebca765f. Earlier metadata-expectation failure and resource backoff are preserved; they affected zero scientific cells. Full project calibration-q replay remains pending. Read the latest machine continuation for actual worker identities and fresh counts.


## Operational admission update, 27 October 2026 11:11 IST

The current installed controller SHA-256 is ea35d3cf151be71152d9c830f366bf204cec2c28ab0e972fb15714a4b00aca6c.
New admissions require the existing 2 GiB growth margin plus a 1 GiB admission-only safety buffer. The existing reclaim rule remains host reserve 6 GiB plus unspent worker commitments plus 2 GiB growth margin. This reduces near-boundary admission/reclaim churn; it does not guarantee protection from larger external changes. The dynamic worker ceiling remains CPU/resource-derived, with no fixed two-worker cap.

The exact installed engineering bundle passed 376 tests and 41 subtests in one full execution, with a 479,252,480-byte sampled process-tree peak and a 20.179-second guarded wall time. Manifest 0111a322e6b3ef32edc44866971acd425397e9aac7c6d89db9dc9fa3b4dcaf4a and assembly 658e7613cb629f296773291e652d78c81648fb91f6f9fd54c23c043b8fcbba46 remained unchanged. The original external output writer misparsed pytest's summary; its original receipt is preserved, and a separate hash-bound derivation records the correct 376 passes. No test rerun or input-manifest annotation occurred. The earlier 371-test proof is historical.

See reports/engineering_audits/ADMISSION_MEMORY_HYSTERESIS_INSTALLED_20261027.json, FINAL_ADMISSION_HYSTERESIS_376_TEST_EVIDENCE_20261027.json, FINAL_ADMISSION_HYSTERESIS_376_SOURCE_TEST_SHA_INDEX_20261027.json and HYSTERESIS_TEST_OUTPUT_PARSER_RESOLUTION_20261027.json. Raw process and lease evidence remains private under EC2 logs/operational.

Frozen scientific tasks, model definitions, memberships, trials, 10 GiB hard process policy, 600-second trial/phase limits, 30-second grace and one nested thread remain unchanged. Existing scientific workers were not signalled by the deployment. E1/E2 fitting and stopped recovery remain closed. Bootstrap remains dropped.

The full scientific artifact audit and saved-calibration-q replay are still required after execution. Engineering tests do not qualify scientific results. Current counts and any capped operational-interruption dependencies must be read from the current SQLite registry and an actual process observation. Never classify a queued or operationally interrupted fit as an ordinary scientific failure. Do not reset automatic recovery caps repeatedly.


### Manual operational transition correction, 27 October 2026

The first status-only manual requeue of E4 rep3 direct RBF K_half and E5 rep1 direct RBF missingness_05 retained pre-existing emergency-stop flags. This made their fourth attempts operationally invalid; no scientific evaluation result was produced. Evidence and checkpoints were retained. A single corrected transition removes exactly the transient emergency/forced/orphan fields that ordinary uncapped recovery clears, resets PID fields after exact absence checks, and preserves automatic recovery count2, all attempt history, selected settings, seeds and trial budgets. Four metadata invariant checks passed; this is separate from the immutable376-test bundle, whose sources/manifest remain unchanged.

See engineering_audits/STALE_GUARD_MANUAL_TRANSITION_CORRECTION_20261027.json and CORRECTED_OPERATIONAL_RESUMPTIONS_OBSERVATION_20261027.json under reports. K_half resumes the same RUNNINGOptuna trial0 within five total slots. E5 restarts its same clean-selected fixed finalfit with zero tuning trials; it has no Optuna checkpoint. Do not represent either as an ordinary scientific-failure retry. Do not grant another exception after a genuine interruption of the corrected valid resumption.

Final reporting must distinguish operationally invalid/interrupted overhead from scientific trial/finalfit/generation/calibration/inference costs. State whether reported costs include that operational overhead; do not claim full campaign costs from selected-fit phase measurements alone.


## Required E5 reporting extension, 27 October 2026

The installed report-only source reporting.py has SHA-256 d7f8d302fad59310f4c101b27a23575a66012b612f376df79fb277b02915cf19.
It adds corrupted/clean/paired per-class set-size values and set_size_difference_a_minus_b with per-class paired n/mean/sampleSD. Existing matching/recall/coverage and scientific model configurations remain unchanged.
It also emits E5_label_noise_source_class_rates.csv, expected63rows from9label-noise cells times7classes. The stored transition matrix counts affected rows only; its row sums are NOT original class supports. The rate denominator is the full original y_fit support from the matching frozen role cache; numerator is changed outgoing transitions. Zero or unavailable source support is explicitly flagged, never silently replaced by a rate.

Current exact installed proof:382tests+41subtests passed with unchanged source/test/input hashes; 51source records,38test files,10resource proofs. This is distinct from scientific cell completion/globalcalibration-q validation. Full-run resourcepreflight passed; the earlier collect-only resource_gate_completeFalse remains disclosed in the immutablemanifest. Formal receipt is reports/PORTABLE_TEST_PASS_1e92a243f891eb1673f818e90e7332ce1293dd0a5cc1d53820c92af44ab404df.json. Sanitized public proof/sourceindex: reports/engineering_audits/REPORTING_GAPS_382_PUBLIC_PROOF.json and REPORTING_GAPS_382_SOURCE_TEST_SHA_INDEX.json. Reporting publication did not restart the controller or signal scientific workers.

Final completion review must inspect the actual63-row rate CSV and its independent realization audit, not merely file existence. Verify full original-class denominators and affected-only transition accounting. Verify actual E5 per-class paired set-size fields and summaries are populated wherever both validated source class metrics are available, with correct repetition pairing and explicit unavailable/missing states; do not accept empty extra columns as fulfillment.

The complete E4 direct-kernel descriptive block has90planned outcomes: RBF18successful/27evaluate-timeout; KDE42evaluate-timeouts/3unavailable controlaliases. All90selected model references exist; there are no successfulRBFcontrols and zero of84planned altered/control pairs are matched. The reviewed report/figures/tables are under reports/e4_direct_kernel_block_20261027. Root table and figure reviews passed; globalartifact/calibration-q validation remains required.


### Actual E5 export validation and interim delivery

The nine saved label-noise realizations passed an independent read-only audit:63source-class rate rows, exact4,000/8,000/16,000selected fitting rows per severity, nested affected-ID sets, allselectedlabels changed and allunselectedlabels preserved, matching affected-only7x7transition matrices, and unchanged original role files. Canonical rate CSV SHA-256: e9cb09996954185b59c9f5a827c6d3f9bc717c20e16f4dc24fd0e6ee81207c93. Audit: reports/e5_label_noise_realization_audit_20261027/E5_LABEL_NOISE_REALIZATION_AUDIT_20261027.json, SHA2889a768f551844c6dfaec3d11b99332d1bcc1f0126ec60e03c824e4bc5070b3.

The new generic per-class set-size pairing/summary outputs were cross-checked against the independently reviewed completed KNN/RF blocks:378paired class rows and126summary groups, alln=3, zero identity/recall/coverage/set-size/mean/sampleSD/n mismatches. Scoped QA: reports/e5_setsize_pairing_realdata_check_20261027/QA.json, SHA7021592f5e8c3c2f071184caace32aba416fe349095b3d7970c80a471342e857. This checks those completed blocks, not the full pending E5grid or savedcalibration-q replay.

The reviewed interim ZIP and readable progress/supervisor documents were copied to the existing laptop handoff directory and byte-size/SHA verified. ZIP: packages/LAMOST_INTERIM_REPORTS_TABLES_FIGURES_20261027T084413Z_V5_REVIEWED.zip,6,725,024bytes, SHAce601d1140b3e37d8f65952987c56af212ab08cab76f66ba3d9acf98348908f3,141entries with CRC and allpayloadSHA/size checks. This is NOT the full completed-project archive. Delivery receipt: reports/engineering_audits/INTERIM_REVIEWED_V5_LAPTOP_DELIVERY_VERIFIED_20261027.json. The readable snapshot is dated14:14IST; current counts must still come from the registry and exact actual-process observation.


## Validation-only finalization update 2026-10-27 (397 checks)

The current installed portable bundle passes 397 tests plus 41 subtests. Its exact tested manifest is 9a7dcfae88030299b8e6d4988aada1350114c5f7974e4b156b6fb27be8c65f42 and was unchanged during execution. Formal current receipt: reports/PORTABLE_TEST_PASS_632502832b11cfba4796934bd77845ba0a8621a32c559428d038d986cb5ab9ce.json. Install evidence: reports/engineering_audits/FINALIZER_LABEL_RATE_AND_STARTUP_GATE_INSTALLED_20261027.json; sanitized publication link: FINALIZER_LABEL_RATE_STARTUP_397_PUBLICATION_LINK_20261027.json alongside it.

Only the finalizer and validation supervisor changed; the 11 frozen execution source files, 19 frozen E1 Python files, task plan, scientific configurations and limits remain unchanged. The finalizer requires the actual 63-row E5 label-noise table, repetition/rate/class identities, full-original-support denominators, exact 80k/4k/8k/16k arithmetic and reporter count. The validation supervisor waits at most two seconds (20ms polling) for startup PID/start-tick/UID, expected executable/script/runtime/flags, and process-group identity. It never signals an unverified PID, and the scientific 600-second/10-GiB policy is unchanged. No controller restart or scientific-worker signal occurred.

The first 389-case run (387 passed, two failures) remains preserved: one new-required-artifact fixture gap and one startup-identity sampling failure consistent with an exec-start race. The final 397-run includes all old 382 node IDs, an extended environment fixture retaining its old assertions, seven new label-rate tests and eight startup tests. The final input assembly was written before test start and remained unchanged. The full receipt retains its failed embedded metadata-smoke attempt due to a missing helper path; a separate bounded actual-CSV smoke passed all63 rows. Do not edit these receipts or describe the original smoke as passed. Publication of the already-qualified bundle is complete; never rerun its deployment scripts or unchanged suite.

New reviewed descriptive outputs: E5_FIXED_SELECTION_METADATA_ROOT_REVIEW_20261027.json checks 617 successful E5 fits' metadata/configuration/seed inheritance (7,146 root checks); COMPLETED_SYNTHESIS_ROOT_REVIEW_20261027.json checks E1/E2/E3/E6 synthesis denominators and saved means (240 checks); reports/e5_completed_generator_routes_20261027/ROOT_REVIEWED_RECEIPT.json covers a270-case subset, 56,029 numeric checks and direct visual review of three final figures. These do not substitute for full fitted-model internals or calibration-q replay. The E5 subset includes GMM/copula/Chow-Liu direct Bayes versus synthetic-only logistic/HistGB; every reported paired mean uses three repetitions. Its phase-cost raw process receipts remain private on the original EC2; delivered cost CSVs preserve relevant scalars and source hashes, and the figure-only helper uses supplied CSVs.

E4/E5 remain active. All overall completion checklist items remain unproven until every scientific case is terminal, complete artifact/calibration-q validation passes, the exact final scientific report and figures are reviewed, both delivery packages are verified, laptop delivery is verified or honestly blocked, and owned cleanup completes. Bootstrap and E1/E2 fitting remain prohibited.


The existing terminal hook was rechecked after the 397-check installation. Once all6,270 task records are validly terminal, the controller launches run_finalizer.sh under the named lamost-finalize tmux session; its existing watchdog can recover that launch after verified controller absence. The finalizer ownership lock and audit/report fingerprints still apply. Inspect actual processes before any manual invocation; do not add a competing watcher or duplicate calibration replay. Full calibration-q validation has not started yet.


## Scoped saved-outcome validation, 27 October 2026

The existing Auditor.evaluation_audit API independently checked 25 successful physical E4 direct-ARF outcome artifacts (12.5 million saved test-row outcomes) with zero integrity issues or diagnostic limitations. The frozen 11:21 UTC scope has 45 planned cases: 28 successes including three control aliases, two recorded 600-second evaluation timeouts and 15 pending cases. The aliases/failures/pending rows are coverage accounting, outside this array-audit scope. All25 selected raw pipeline hashes remained unchanged (439,644,047 bytes total). The guarded child pass took3.921 seconds and peaked at80,596,992 bytes under512MiB/120s limits. No model was deserialized, refitted or used for new inference, and no conformal quantile was replayed.

Evidence: reports/e4_arf_saved_outcome_audit_20261027/E4_ARF_SAVED_OUTCOME_AUDIT_20261027.json (913656cab7acdbc86e79f15d89e29f1f058426d2a4ca564585dcd4bf8aee8ad7), ROOT_REVIEW.json (7139ae9718ff4f054bfb63a5ea0a0171db7ff0e9197550faaf11da6e4b0cdaea;167 checks/107 input hashes) and REPRODUCE.md. An initial root review used incorrect canonical-payload key names; that false-positive review is retained separately. The corrected digest matches the unchanged input plan, code and original audit report. Private guard/preflight inputs stay on the original EC2; public delivery retains sanitized hashes and scope.

The official whole-project evaluation-only CLI would first verify about29.3GB of cold logical model bytes under a shared reader lease; its prior run took296 seconds. It was not launched during active fitting/storage compaction. The scoped ARF check accessed raw models only and left auditcache.json unchanged. Full selected-model internals and independent calibration-q validation remain required at terminal finalization. Do not rerun unchanged audits simply to produce a newer timestamp.

The remaining-dependency audit found no graph deadlock. E5's228 pending evaluation/alias cases also have225 pending fits and27 generation tasks upstream. Keep the established10GiB ExtraTrees admission; three clean-control dependencies unlock27 E5 corruption fits/evaluations when resources permit. No scientific policy or scheduler change was made.


## 27 October 2026: completed cold-transaction admission hold recovered

At 2026-10-27T17:26:47.218675+05:30, the controller and actual workers were checked again. A storage child exceeded its 600-second operational limit after transaction d751df9ba4ae4ae3860054be25b3bd58 had completed. The original interrupted receipt and missing child receipt are preserved. Root acquired driver, batch, finalizer and cold-store leases, verified no old child/batch/finalizer or nonterminal journal, freshly checked the 25,366,421,589-byte archive SHA-256 and ZIP index, and verified the new model physical payload, exact restored logical bytes and all aliases. Only the matching stale hold was moved to retained private evidence. No scientific attempt was retried or result changed. Recovery took 79.49 seconds and completed 11:55:03 UTC (17:25:03 IST).

Receipt: reports/engineering_audits/COMPLETED_COLD_TRANSACTION_HOLD_RECOVERY_20261027.json (SHA-256 a62c2847a0fd4d7c2f37ce50da6f043d59d5bf6ad80e0c92a554385e56b75f51). Scientific work resumed automatically. Do not rerun the one-shot recovery or fabricate a successful original child receipt. A minimal operational prevention fix is being staged; the current live source and 397-test proof remain unchanged. Full project completion, calibration-q audit and final delivery remain pending.


## 27 October 2026: storage receipt optimization installed, 405 checks pass

All 397 previous test IDs plus eight new storage checks passed once in 21.765 seconds under native 60-second/1GiB supervision (peak test tree 444,190,720 bytes; parent 43,659,264). Manifest 091a53a598101f1dd7811b809b5a3bfb2547c924c4b2ae274b877fe8cdfcb5f5 was frozen before execution and unchanged. The three operational sources and pin cascade were installed with durable rollback backups, actual process/lock checks and atomic writes. Existing scientific fits continued. The 11 frozen later-experiment sources, 19 E1 Python files, E1 ledger/config/dependency lock, core codec and 600-second storage limits remain unchanged.

Current proof: reports/PORTABLE_TEST_PASS_d357aa86a8b5d073ad59bec41b12d7865f4d42eb094a315c510bb603cdd1745a.json (SHA-256 5cd3df718d6348325471550aa3812c3b74ab89e281e480cf9e01b0cdc1b0a11e). Public proof: reports/engineering_audits/COLD_POSTCOMMIT_405_PUBLIC_PROOF_20261027.json (SHA-256 8b80736b8c9cd934f54ba663065dd06a68816d6b8c2e40dc76df9ed9a039d1c1). Legacy397 proof and raw evidence are retained. New main path keeps one fresh archive SHA/ZIP index check, reuses verified core transaction proofs and writes its receipt under the store lease. Legacy helpers remain byte-identical. First new real transaction still needs observation; no speedup is claimed from fixtures alone. Do not rerun the already committed installer or unchanged full suite. Full artifact/calibration-q audit and final project packages remain pending.


First actual updated storage transaction passed: auto_storage_20261027T124001Z_ede4efdc, transaction 7bb05375781c4ec9be4e14b9de91d935, finished 2026-10-27T12:49:11.967275+00:00. New main-path receipt saved atomically; original hold released; original child absent. Runtime 543.16 seconds within unchanged600-second storage policy, peak child tree 243167232 bytes. Logical model 189065909 bytes retained as 129510408 encoded payload bytes. Core exact logical proof, fresh child archive SHA/index, alias metadata and final supervision receipts agree. No controlled speedup claim; no repeated model decode or full archive hash was needed for this root metadata review. Receipt reports/engineering_audits/FIRST_REAL_POSTCOMMIT_OPTIMIZATION_VERIFIED_20261027.json SHA-256 a8ec8f65f30ac09892f940d949ffcef2ba21b4b46798f78dbbe9c1951891ce4b. Earlier public405proof/MDsnapshot first-transaction=false flags are historical snapshots, superseded by this actual receipt.


## 27 October: storage candidate provenance filter, 414 tests, bulk raw archive

A13:00UTC compaction attempt failed before transaction creation because an E5 fixed-refit model lacked an attempt-level selection.json duplicate. Root freshly verified unchanged26GBarchiveSHA, alljournals terminal and no oldstorage processes, retained the hold while repairing planning, then installed a metadata-only publication filter (414/414checks; all405old IDs retained;20.522s;452,145,152B peak treeRSS). Knowninvalid groups remainRAW; errors are not recast as scientificfailures and no receipt was fabricated. Unexpected validation/I/O errors stillfailclosed. Old405proof retained. The exact13:00hold was released only after installation/proof verification.

First repaired raw-profile operation auto_storage_20261027T142000Z_47fe823a archived16provenance-valid groups (2,145,983,557sourcebytes) in339.87supervised seconds, within existing600s/2GiB/16group profile. It excluded27raw groups with incomplete attempt-selection receipts; they remainavailable. This existing raw-writingprofile is separate from the unchanged normal reversible-XZcodec cron. It advances the sameBUILDING ZIP, avoids a secondarchivecopy, and reduced remaining conservative packing demand by exactly2,145,983,557bytes after the300-second estimate refresh. Actual model fitting resumed. This is not a controlledspeedup or physicalcompression claim.

Current proof reports/PORTABLE_TEST_PASS_e57304314d9b2d91fa66e2415dd1bde0fbf993550eb6c513bac3340be3e65d0b.json SHA-256 7d02b7c0ebd9ebf5df7cecfc7a4ff60982d143b135af766131385a07eb0955e7. Public414proof reports/engineering_audits/STORAGE_PROVENANCE_FILTER_414_PUBLIC_PROOF_20261027.json SHA-256 50c92a5b9e1071ee7463281289373832ac024e840b1b6f5456cacdeb7c8f832a. First real rawbatch reports/engineering_audits/FIRST_FILTERED_RAW_ARCHIVE_BATCH_VERIFIED_20261027.json SHA-256 a557bc91501ea7115f18fb7d351ee349d1055660418c55df93eae852ad8b4314. The existing617-fitE5selection audit covered canonical configs, not availability of every attempt-level duplicate receipt. Full global artifact/qvalidation remainspending. Oneadditional existing rawprofile operation was admitted and actually started14:33UTC; checkits realprocess and finalreceipt before further claims. Background-helper concurrency prototype is STAGEDONLY/deferred, based on older405sources and MUSTbe rebased to current414beforeanyfuturework; controller/freeze/scientific sources unchanged.


## IO419 update 2026-10-27T21:04:56.815214+05:30

Installed qualified419 operational sources; native supervisor failed normal-exit identity observation, retained as failed. The unchanged419 suite then passed under existing race-aware bounded guard (419tests+51subtests,18.266661s,exit0). Pass fingerprint f0ab9ac8539da718b3198f67bde3b35f5a041f642a3f6f5a4bad7939955171f4. Prior failed600s RAW append safely rolledback by pinned core; source aliases retained. Exact maintenance hold released after install. First bounded1800 RAW archival operation auto_storage_20261027T152955Z_31aa6da4 verified actual driver/wrapper/child. This is running, not a completed archive. Scientific source/settings remain unchanged; no extra scientific retry. Full scientific/q/report/archive validation remains pending.


## First bounded1800 RAW archive verified 2026-10-27T21:10:00.162570+05:30

Operation auto_storage_20261027T152955Z_31aa6da4 returned0 and committed16groups/1,821,076,954sourcebytes in462.566s; creatorjournal05e9531eaf9c41ef9a3087161100a5ce complete, holdreleased. BUILDINGarchive29,961,455,262bytes/166members SHA25654a89bc4ed0d01ab6235be4fe3e8553ecf63194f7e4350f8ca85339160e010c3. Rootreceipt FIRST_BOUNDED1800_RAW_ARCHIVE_VERIFIED_20261027.json binds qualifiedchildfreshSHA,journal,manifest,index,stat,removedaliases; rootdidnot redundantlyrehash30GBwhilequeueactive. Actual4scienceworkers/3fits observed; E4success1468 with231pendingoractive, E5success652with228pending. Archiveisnotfinal.


## Operational update: 426-check installation, 27 October 2026

All 419 prior engineering cases and seven new cases passed under the existing bounded guard: 426 tests plus 51 subtests, 19.575394 seconds, 456,888,320 bytes sampled peak process-tree RSS, exit 0, and no termination signal. These are engineering checks; global scientific validation is still pending.

The current bundle fingerprint is `09646c124938164119fbc1e84dc31d5566c99ece118abdecb43f95461fb4a4d4`. Its installed pass SHA-256 is `2fb79cf6c22c217a5a4e516d6bc3fc2a473ef6bb0bd48f9efa212906744b0b6a`. The installation receipt is `reports/engineering_audits/RAW_IO_CLEANUP_DISCLOSURE_426_INSTALLED_20261027.json`.

Only two operational source files changed. The finalizer adds the E3 missing-publication disclosure and removes ownership nonces from derived archive views. The delivery cleanup guard recognizes the exact bounded-1800 RAW archive cron command. The 11 scientific sources, 19 frozen E1 sources, task plan and freeze bytes remain unchanged. The controller was not restarted, and no scientific workers were signaled.

The failed codec operation at 15:40 UTC was recovered using the original pinned core in 403.189 seconds. Its pre-commit transaction was rolled back, all source aliases were retained, and the archive SHA, index and member payloads were verified. The exact maintenance hold was then released. Its interrupted supervision receipt remains a failure record; no scientific outcome was changed.

The legacy codec schedule remains paused. The installed five-minute RAW archive watcher uses the already reviewed 1,800-second storage profile, with at most 2 GiB and 16 groups per batch and a 1.5 GiB helper reservation. It acts only when the controller's current storage headroom is below 2 GiB. Actual process identities, locks and journals prevent duplicate operations. An interruption retains its hold and journal for review; it does not trigger an automatic resource extension. See `reports/engineering_audits/RAW_IO_ARCHIVE_WATCHER_INSTALLED_20261027.json`.

The controller and master-index watchdogs remain enabled. The background-admission prototype is deferred and unqualified; do not deploy it. Final artifact validation, conformal-quantile replay, report review, verified packages and delivery remain pending.

E6-v2 live amendment (observed 2026-10-27T19:08:24.564645+00:00): source map12 and controller b9465eb5... are now deployed; exact six gate supersessions preserved, 505 portable checks passed under 1GiB/60s. Read manifests/E6_V2_EFFECTIVE_AMENDMENT_RECEIPT_20261028.json and the current continuation JSON. Original prepared freeze metadata is immutable; effective status is bound by the receipt. Raw bounded1800 watcher is restored with360s transaction cooldown. E6 planned is not evidence of a running posterior phase. Broken staged deployment attempts are preserved as operational incidents; do not re-execute them.


2026-10-28 continuation update (observation 2026-10-28T02:22:21.108272+05:30): source freeze 0dddaafa343e751459d92978e8c23277978af3058c9cb7e0ce5f3dcbaf97e8fd and qualified portable509 remain live. E6 legacy-feature-provenance fix passed all15 saved-pipeline identity checks and509 tests; six invalid engineering attempts preserved and superseded once. E6 primary now0/6 successful,3 scientific test-posterior timeouts at600s and3 unavailable dependencies from shared failed phase;15 comparison aliases12 successful/3 unavailable. E4/E5 remain active. RF4 and archive digest-cache optimizations are staged and NOT yet deployed. See latest continuation JSON and timestamped E6 interim report; do not re-run terminal failures or call final project complete.

## Latest 28 October continuation index

Read AIRBAG_CONTINUATION_20261028.md and reports/PROJECT_CONTINUATION_CHECKPOINT_20261028.json, then re-read the live registry and process inventory. The717 bundle is deployed; the pristine-admit fix and rep3 RAM-estimate supplement remain staged until a new complete qualification.
