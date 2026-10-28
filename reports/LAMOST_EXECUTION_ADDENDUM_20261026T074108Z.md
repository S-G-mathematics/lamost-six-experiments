# LAMOST current execution addendum

Observed: **2026-10-26T13:11:08.683187+05:30**. This supplements [LAMOST_PROJECT_PROGRESS_20261026T071827Z.md](LAMOST_PROJECT_PROGRESS_20261026T071827Z.md), which contains the detailed12:48IST report. The project is still active and incomplete.

| Experiment | Successful / evaluated | Failed | Unsupported / unavailable | Pending / active |
|---|---:|---:|---:|---:|
| E1 frozen |674|81|10|0|
| E2 primary |108|—|42|0|
| E2 references |120|0|0|0|
| E3 |64|3|2|0|
| E4 |1194|42|3|534|
| E5 |613|27|23|297|
| E6 |12|0|9|0|

E3/E6 have terminal execution ledgers; their final project-wide validation/reporting remains pending. E6 has12 valid member evaluations and0/6 primary ensemble outputs; nine member/ensemble cases are unavailable. E2 primary evaluated coverage remains108/150, separately from120/120 classical references.

The separate stopped E1 supplement remains24 successful retries,10 failed retries,2 user-stopped partials and55 not attempted. It is not a completed recovery study.

## Actual current workers

- e4/rep_1/fit/treatment/random_forest/F_half_generated_chow_liu — fit, 10GiB admission reservation.
- e4/rep_1/fit/treatment/random_forest/A_tenth_weighted — fit, 5GiB admission reservation.

The controller and listed worker PID/start-tick/script/request identities were checked against the kernel. No running registry record failed that identity check at this observation. Current available RAM: 25.52GiB; disk free: 65.36GiB; holds: []. These measurements are timestamped observations.

Three simultaneous fitting workers were verified earlier at12:39IST after the prospective-profile update. Current concurrency follows measured memory commitments; there is no fixedtwo-worker cap. The CPU-derived ceiling remains14, with one nested numerical thread, six-GiB host/Harbor reserve, two-GiB commitment-growth margin and eight-GiB admission floor. Hard10GiB and600-second scientific phase/trial limits are unchanged.

## Controller correction after the detailed report

A further cleanup edge case was found after the first guard update. The tree could already have exited, but its task remained marked running until the next controller cleanup pass. Its unused reservation could then cause another unnecessary interruption.

The applied v2 guard treats a recorded termination awaiting registry cleanup as bounded cleanup-state debt for at most30seconds when RAM is above the existing6GiB critical floor. It does **not** assert that the process remains alive. Actual process checks remain required for signaling, watchdog recovery and liveness reporting. Critical pressure below6GiB still permits reclaim.

The verified handover signaled only the controller and preserved all existing worker requests and terminal results. Current controller SHA-256:

    44dc08e2f6af9bc6acb237b4b85827612e5c69055d197b5af960008d803b1514

Current admission-helper SHA-256:

    44bdeef607dac4937a25c33b711d0f42375d6094845c83718e61ad0df7235e5b

Applied v2 receipt: reports/engineering_audits/RECLAIM_CLEANUP_GRACE_V2_APPLIED_20261026.json; SHA-256 38d9ed3b1513c06b62a6c5a8bfa146ed6fd4c59141bcb3dcbde162cb986759dc.

The source is already applied. Re-running the deployment script is not a resume action.

## Verification and delivery state

All112 selected portable engineering checks passed in a relocated source/tests/fixtures tree after the v2 update, plus77 staged regression checks and three subtests. The checks cover cleanup state, critical pressure, frozen request preservation, prospective resource evidence, archived aliases, reporting and packaging. They do not run scientific fits or use real fitted models.

The environment used the frozen Python3.12.3/NumPy2.3.5/sklearn1.8.0/SciPy1.17.0/joblib1.5.3 first in import order, followed by recorded existing plotting support. The scientific environment was not changed. See tests/README.md and source/reporting_support_environment_20261026.json. A prior engineering attempt's two missing-Matplotlib failures are preserved separately from scientific outcomes.

The building overall ZIP remains a verified17-model prefix:

- EC2 path: /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip
- Bytes: 1,217,009,037
- SHA-256: 3bad81c5e43efd006bf4c16263314422d22f78f055b624e8dff3aa47471b6d1d
- Three completed journaled transactions; exact model bytes and alias resolution verified.
- This is not the completed overall archive. No final review pass or project-complete marker is claimed.

The three exact-byte public resource audits are included by the final archive collector. Historical private process/cleanup receipts remain retained on EC2 and excluded from public packaging.

A lightweight read-only observer now aggregates task JSON inside SQLite instead of materializing all6,270 nested records in Python. Use:

    /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/source/observe_progress.py --by-rep

Current DAG states: {"planned": 10, "running": 2, "validated_terminal": 4516, "waiting_for_dependency": 1742}.
Current operationally invalid tasks: [].

## Continue from here

Keep the single owned controller executing E4/E5 and validate real progress. Do not launch duplicate queues or infer liveness from heartbeat files. No E1/E2 fitting, stopped-recovery restart or bootstrap is authorized. Later ordinary terminal failures remain terminal.

After execution is terminal, complete the full cold-aware selected-model/outcome audit, final per-repetition/condition tables and figures, numerical/visual review of the exact candidate, cross-experiment report, full/compact archive CRC and SHA verification, laptop compact delivery and clean project-owned shutdown. Keep all documented E1/E2 provenance caveats and the separate recovery supplement. Preserve Harbor and the existing EC2 infrastructure.

The current full project plan and immutable scientific DAG remain unchanged. Completion has not been claimed.
