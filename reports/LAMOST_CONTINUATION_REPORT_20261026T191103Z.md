# LAMOST six-experiment execution report — 2026-10-27T00:41:03.740610+05:30

This is an interim execution report, not a completion certificate. Scientific work continues on the existing EC2 instance. E1 and E2 are frozen/finalized under their recorded limitations; no new E1/E2 fits were launched. E4 and E5 have outstanding cells. The complete project has not passed final validation or delivery.

## Actual observation and scientific coverage

Observation: 2026-10-27T00:41:03.740610+05:30 (Asia/Kolkata); 2026-10-26T19:11:03.740610+00:00 UTC. DMI instance identity: i-095641a281a4038b9. The controller and every listed worker were checked using actual process identity, process-start ticks, request key and attempt identity. A historical heartbeat is not evidence of liveness.

| Experiment | Planned outcomes | Successful/evaluated | Scientific failures | Unsupported/unavailable | Pending/active | Phase |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | Frozen report finalized; historical source/ledger checks last verified 26 Oct 22:06 IST |
| E2 primary | 150 | 108 evaluated | — | 42 unavailable | 0 | Reporting finalized with incomplete primary coverage |
| E2 classical references | 120 | 120 evaluated | 0 | 0 | 0 | Separate reference analysis |
| E3 | 69 | 64 | 3 | 2 | 0 | Scientific outcomes terminal; final global validation/delivery pending |
| E4 | 1773 | 1272 | 42 | 3 | 456 | Scientific queue active through sole controller |
| E5 | 960 | 622 | 27 | 23 | 288 | Scientific queue active through sole controller |
| E6 | 21 | 12 | 0 | 9 | 0 | Scientific outcomes terminal; final global validation/delivery pending |

E1's stopped recovery supplement remains separate: **24 successful retries, 10 failed retries, 2 user-stopped partial cells and 55 not attempted**. These outcomes never replace frozen E1. E1's 81 frozen failures distinguish 55 resource failures from 26 supervisor-terminal cells whose manifests remained started; the ten unsupported cases remain separate. E1/E2 historical numbers here are retained verified ledger/report facts, not newly observed model execution.

| Experiment | Repetition | Successful | Failed | Unavailable | Pending/active |
|---|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 |
| E4 | 1 | 467 | 14 | 1 | 109 |
| E4 | 2 | 428 | 14 | 1 | 148 |
| E4 | 3 | 377 | 14 | 1 | 199 |
| E5 | 1 | 208 | 9 | 1 | 102 |
| E5 | 2 | 206 | 9 | 21 | 84 |
| E5 | 3 | 208 | 9 | 1 | 102 |
| E6 | 1 | 4 | 0 | 3 | 0 |
| E6 | 2 | 4 | 0 | 3 | 0 |
| E6 | 3 | 4 | 0 | 3 | 0 |

The later-experiment immutable plan contains 6,270 dependency/helper/scientific tasks and 2,823 unique evaluation outcomes. Current DAG states: {"planned": 10, "running": 2, "validated_terminal": 4682, "waiting_for_dependency": 1576}. The scientific plan SHA-256 is 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb. Its original freeze date remains 2026-10-25T04:46:31.018995+00:00.

## What changed in this continuation

The exact deployed validation bundle passed **195 tests, zero failed, and 17 subtests**. It covers 23 runtime sources plus 19 exact frozen E1 source fixture copies and one validated E1 report fixture, across 20 explicit test files. Fixture copies are dependencies, not additional scientific runs. Root rechecked the production receipt acceptance gate against the current source/test/manifest/runner hashes without repeating the full suite.

Accepted test receipt: reports/PORTABLE_TEST_PASS_47544a81b16fc60489bac8a5f496a48fde06b10af9eb9586bdd4256bfb6b5e55.json, SHA-256 e5709dda23475ffabcb35043182e2e8dc3a5d29cc30f67ee4e1ccc8e8a59b4e9. Test manifest SHA-256 addbdee591fccdfb5f1938c13134b6805146baffef13b4ea349e4b1179ffe737.

The guarded test process exited zero, with 482,619,392 bytes peak measured process-tree RSS under its 1 GiB limit. Its wrapper initially misparsed the valid pytest summary and wrote a false-negative status. The accepted receipt is explicitly derived from the preserved unmodified log and external process/resource receipt. Earlier fixture failures and parser incidents remain preserved as private operational evidence. No scientific results were altered to obtain this pass.

Root verified every output hash in the completed E5 direct-RF block, read its numerical summaries and inspected all three EC2-generated figures for readable axes, legends, repetition denominators and nominal coverage labeling. A dated root review receipt is saved with the block. This is a completed descriptive subset, not a claim that E5 or global calibration validation is complete.

The controller uses the reviewed cross-experiment stage ordering and resource-gated ARF fit priority. It preserves each cell's method, tuning budget, seed, resource limits and task identity. This scheduling change permits ready E5 evaluations to run alongside E4 progress and prioritizes evidence-gated 6 GiB ARF admission when a heavy RF fit occupies the host. No ordinary scientific failure was retried.

The dispatch rollout had a checker incident: compiling an unchanged BOM-encoded source as decoded text failed. Existing model workers continued. The partial source rollout was repaired under nonce-owned admission/watchdog holds using byte compilation; unchanged source hashes were retained and the controller was reverified. Prior request-byte checks were reconstructed deterministically from retained pre-rollout metadata, not misrepresented as saved pre-rollout file hashes.

## E5 completed direct random-forest block

All **30/30** direct-RF cases validated: three clean controls and 27 corrupted fits/evaluations. There are 27 clean-paired differences, 210 per-class metric rows, 189 paired class rows and nine condition summaries, each with all three repetitions. Evaluation JSON hashes match their registry validation receipts. Balanced accuracy was recomputed from seven-class confusion matrices with 500,000 test rows; class order, 10,000 calibration rows, fitting memberships and clean-selected configurations were checked. No models were loaded, trained or inferred for this descriptive analysis.

| 20% affected fitting rows | Mean balanced-accuracy change vs paired clean | Mean overall-coverage change | Mean set-size change | Paired repetitions |
|---|---:|---:|---:|---:|
| Feature noise | -0.010556 | +0.000101 | +0.029072 | 3 |
| Missingness | -0.005531 | +0.000130 | +0.020881 | 3 |
| Label noise | -0.017309 | +0.000416 | +0.242023 | 3 |

These are descriptive means; individual repetitions and sample standard deviations are in the supplied tables. Label noise showed the largest direct-RF accuracy loss and set-size increase among these three 20% conditions. This is a finding for this route, cohort and corruption mechanism, not a universal restoration or astronomical-error claim. Coverage accompanies set size. No bootstrap or significance claims are made. Full supervised calibration-threshold replay remains pending.

Outputs: reports/e5_direct_rf_block_20261027/. Evidence manifest SHA-256 57981edc8399f5bfb558055fa3cb201c3e32758daec43d9fde4b21d8be984572. Thirty-case metrics CSV SHA-256 76e4075ab54f80a6ba41c52c00d6fe394ae72c9b7429193276412b63ab187ca5.

## Resource and persistence state

Free RAM: 27.43 GiB; free filesystem capacity: 51.2 GiB at the observation. These are instantaneous observations, not future capacity guarantees. Actual verified scientific workers:
- e4/rep_1/fit/treatment/random_forest/K_tenth_generated_gmm: reservation 10.0 GiB; elapsed 1305.9 seconds.
- e4/rep_1/fit/direct/arf/A_tenth: reservation 6.0 GiB; elapsed 500.6 seconds.

The user removed the static two-worker ceiling. The sole controller admits work using measured memory/CPU headroom, per-task reservations and growth protection. It reserves capacity for OS/Harbor and caps nested library threads. A low instantaneous RSS does not justify ignoring future worker growth. Scientific limits remain 10 GiB per worker and 600 seconds per trial/final-fit/generation/prediction phase, with recorded 30-second termination grace. A multi-trial fit can therefore exceed 600 seconds in total without violating its individual phase limits. Admission estimates such as 6 GiB do not change the 10 GiB scientific failure limit.

Three exact project-owned cron entries were observed: controller watchdog, master-index export and guarded cold-model compaction. They are not claims of worker liveness. Existing unrelated cron/processes are not changed. Historical STORAGE_HOLD.json is an observation marker; the controller uses fresh disk admission, and a nonce-owned ADMISSION_HOLD remains a real launch barrier.

The current BUILDING archive has 62 verified cold-model members and a recorded transaction size of 14074218520 bytes. Its recorded transaction SHA-256 is 0a24e49131ecc73dc716ce7e3ebb36961678caba690221413df84ccf195e9ec3. This is an unfinished archive, may grow after this observation, and is not the final full-project package. Each cold-store transaction verifies original logical model bytes and its archive before unlinking eligible fully-consumed RF copies. The current raw archive format is unchanged.

A separately staged reversible-codec feasibility probe achieved exact original-byte restoration for one selected model and passed ten small fixtures. It is not integrated into live cold storage or used by scientific runs; no general compression compatibility or capacity guarantee is claimed.

## Preserved scientific boundaries and limitations

- The established LAMOST DR10 v2 baseline has 2,330,835 source representatives, seven labels (A, F, G, K, M, GALAXY, QSO), six photometric predictors and the fixed 500,000-source test cohort. IDs, labels, spectral/audit metadata are not predictors. Memberships and fitting-only learned transformations remain explicit.
- E3–E6 use the frozen 100k development default and three paired repetitions with 80k fitting, 10k tuning and 10k calibration roles. Synthetic-only data have exactly 400k rows. Tuning does not use test outcomes; conformal calibration remains separate at nominal 90%.
- E1/E2 test outcomes were observed before later experiments. The project is not described as having an untouched prospective test set. Later plans were frozen before new evaluation.
- E2 remains 108/150 primary plus 120/120 classical references, with 42 primary artifact/unavailable cases. Original versus reconstructed provenance remains explicit. There are 31 reconstruction accuracy differences and 210 low-precision class-report flags. Only four complete five-family correlation strata support descriptive primary correlations; available-only correlations remain exploratory.
- Missing historical E1 fitted models and per-test-row predictions remain missing. Seven auxiliary tuning-history discrepancies and unavailable exact original histories remain disclosed. Validated completion metrics are not overwritten or fabricated.
- E3 is terminal with 64 successful, three scientific failures and two unavailable outcomes. Its two unavailable outcomes follow failed synthetic-RF dependencies; direct KDE evaluation failures remain explicit.
- E6 is terminal with 12 member-reference successes and nine unavailable outcomes. Required KDE member evaluations are unavailable, so the five-member equal and tuned ensembles are unavailable. No ensemble benefit or selected weights are invented.
- Later scientific failures remain distinct from dependency unavailability and operational incidents. Conditional-on-success findings and hardware/concurrency-dependent cost limitations remain explicit.
- The E3 synthetic-RF RSS provenance erratum remains attached: a prior audit field did not represent the maximum across failed tuning trials. Original evidence is retained; no smaller resource-policy claim replaces it.
- Bootstrap remains dropped. No E1 recovery, ARF sensitivity variant or abandoned full-backup/finalizer effort is restarted.

## Remaining work and resume instructions

Continue the sole verified EC2 controller through E4/E5. Preserve checkpoints, attempt identities, role/source/config hashes and ordinary terminal scientific failures. Do not manually launch competing workers or rerun E1/E2.

When all 6,270 tasks are validly terminal, the finalizer must pass complete artifact/identity checks and supervised calibration replay, regenerate and numerically/visually review the exact candidate reports, and package all available artifacts with an honest missing-artifact inventory. One prior calibration-only LR smoke reproduced its threshold exactly, but its custom engineering parent supervision was invalid; it does not qualify the full gate.

The final full archive must be saved under /home/ubuntu/lamost_e1_migration_20261023/packages with member manifest, CRC check, byte size and SHA-256. The compact reports/tables/figures/manifests package must be copied and hash-verified to the laptop when available. Stop only exact project-owned workers/watchdogs after successful completion. No final delivery package or PROJECT_COMPLETE assertion exists yet.

Read reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json and RUN_RESUME_REPRODUCE.md on the original EC2 runtime. Existing connection: ssh w7-ec2. Do not initialize the live controller from an extracted public archive; public registry projections are for reporting, not live scheduling.
