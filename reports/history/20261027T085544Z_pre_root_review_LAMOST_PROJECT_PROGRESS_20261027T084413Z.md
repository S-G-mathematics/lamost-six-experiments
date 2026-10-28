# LAMOST six-experiment interim progress - 2026-10-27T14:14:13.065601+05:30

This is a dated interim snapshot, not a final project report or completion claim. Scientific work and packaging remain on the existing EC2. Counts below are read from a fresh, read-only registry observation at the timestamp above. Active workers are counted only after the observer verifies the worker-root process identity; phase children are not counted as separate workers. No process identifiers are included.

EC2 instance: i-095641a281a4038b9. Controller identity verified; controller SHA-256 ea35d3cf151be71152d9c830f366bf204cec2c28ab0e972fb15714a4b00aca6c. At observation: 26.68 GiB available RAM, 44.9 GiB free disk, and 4 worker-root processes identity verified. These are point-in-time observations.

## Project case status

| Experiment | Planned scientific cases | Successful/evaluated | Scientific failures | Unsupported/unavailable | Waiting/planned | Running scientific cases |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 |
| E2 primary | 150 | 108 | 0 | 42 | 0 | 0 |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1773 | 1426 | 71 | 3 | 272 | 1 |
| E5 | 960 | 652 | 50 | 30 | 228 | 0 |
| E6 | 21 | 12 | 0 | 9 | 0 | 0 |

E3-E6 cover 2,823 planned scientific evaluations. Fit, generation, and helper tasks are not evaluation cases. `waiting/planned` is nonterminal; `unavailable` is a dependency/evaluation status, not a model failure. The three identity-verified worker processes need not correspond to three running scientific evaluation rows.

## Frozen E1 and finalized E2

Frozen E1 remains unchanged at 765/765 terminal: 674 successful evaluations, 81 failed cells (55 resource failures and 26 supervisor-terminal failures whose manifests remained started), and 10 unsupported cases. The 10 unsupported cases are distinct from the 81 failures. The early-stopped recovery supplement remains separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. Recovery outcomes are not substituted into frozen E1.

E2 has 108/150 primary evaluations (19 original saved-fit and 89 reconstructed-fit) and 42 unavailable dependencies; its separate classical references are 120/120. E2 reports 31 reconstruction accuracy differences, 210 low-precision flags, and 4 complete five-family strata out of 30. The class-report/integrity audit records 1,596 class reports and zero integrity errors across 228 evaluated cells. E2 primary coverage remains incomplete; no global correlation or significance claim is made.

## E3-E6 current state

E3 is terminal: 64/69 successful, 3 scientific failures, 2 unavailable dependencies. E4 has 1,426 successful, 71 scientific failures, 3 unavailable, 272 waiting/planned, and 1 running case. E5 has 652 successful, 50 scientific failures, 30 unavailable, and 228 waiting/planned. E6 is terminal with 12 successful member-reference evaluations and 9 unavailable cases; its six primary ensemble cases were not attempted because a required member evaluation reference was unavailable.

### Root-reviewed E4 direct-kernel block

The completed 90-cell block has 18 successful RBF-SVM evaluations, 27 RBF-SVM evaluate-phase timeouts, 42 KDE evaluate-phase timeouts, and 3 KDE clean-control aliases unavailable through their upstream E3 KDE evaluation dependency. Selected model references are available for all 90 cells. There are zero matched altered-minus-control pairs because no RBF-SVM control evaluation succeeded; KDE produced no valid block evaluation metric. The block table arithmetic and three figures passed root review. Its compact review summary and full report/tables/figures are included below; the raw resource gate and operational receipts are excluded.

### E5 label-noise realization audit

The current data-only audit validates 9 corruption masks across 3 repetitions and rates 5%, 10%, and 20%, with 63 full-source-class denominator rows. All three repetition mask sequences are nested, and the fit/tune/calibration role-cache checks passed. This verifies corruption realization only, not E5 classification performance or E5 completion.

### E6 selected models and unavailable primary ensembles

All 15 selected generator model pipelines are available. Twelve direct member evaluations are validated; the three unavailable member references are KDE because each E3 direct KDE full-test evaluation timed out at the fixed 600-second evaluation limit. E3 KDE fitting and generation succeeded, so these are not missing models. The declared-member gate prevented all six primary E6 equal/learned ensembles from being attempted. No E6 ensemble scores, weights, or benefit claim exist.

## Current engineering proof and source identity

The current reporting implementation receipt records 382 engineering tests and 41 subtests passed; these are engineering checks, not scientific evaluation cases. The source/test index covers 51 source records and 38 test files. The installed-reporting receipt states no scientific fits were started by that reporting installation and marks global calibration replay and project completion false. Current frozen E1/runtime source hashes are independently recorded in the adjacent source proof.

## Limits and next work

Global calibration-q replay, remaining E4/E5 evaluation work, complete artifact/provenance audit, and final project report/archive remain pending. No bootstrap was performed. E1/E2 and reported E3-E6 test outcomes have been observed, so remaining evaluations are not described as an untouched prospective test. Omitted historical E1 fitted models and per-test-row predictions remain an artifact limitation. Timing depends on host and resource policy. The v1-v3 interim packages are preserved; older snapshots and the prior 371-test evidence are labeled historical in this v4 archive. This compact ZIP is not the full reproducibility archive.
