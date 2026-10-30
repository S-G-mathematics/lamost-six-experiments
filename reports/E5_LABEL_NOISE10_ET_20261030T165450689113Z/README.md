# E5 rep-1 Extra Trees label-noise-10 result

Snapshot observed 2026-10-30T16:54:50.689113+00:00 UTC from a coherent read-only SQLite backup.

- Task: e5/rep_1/eval/direct/extra_trees/label_noise_10
- Status: validated terminal success
- Balanced accuracy: 0.7583523875674326
- Overall coverage: 0.895346
- Mean prediction-set size: 1.647708
- Test cohort: 500,000; calibration cohort: 10,000
- Saved evaluation JSON SHA-256: 235281d84c231cf70913bb6be9c0792f42772fad1f7d697bb4ad9dabc4f00353
- Validation JSON SHA-256: b0f30a001e2e681ead262d6a8b35fe42efc4972e3b63b63193fde7dde3a4ed3a
- Test-outcome NPZ SHA-256: 0701fba533213f4aae76b471fa2a445e5867d0f6aa53cb51e40ccb6bb4b2a37b

The exact test_outcomes.npz member is available in the verified GitHub release asset (https://github.com/S-G-mathematics/lamost-six-experiments/releases/download/results-2026-10-28/e5_rep1_label_noise10_et_20261030T165450Z.zip); asset SHA-256 is 23e620caa2c4369c3ed47a08bd6f7111a82bd61dea710a1d67096066266543b1 and downloaded ZIP member CRC-32 is c93d43e0. The registry records 2,823 planned E3-E6 scientific cases: 2,435 successful (including aliases), 127 recorded failures, 90 unavailable, 168 user-stopped, and 3 pending. See the dated complete outcome ledger at ../CURRENT_CASE_OUTCOME_LEDGER_20261030T165450689113Z/README.md.

The rep-1 label-noise-20 Extra Trees fit ended in a recorded scientific failure after exceeding the configured RSS limit; its dependent evaluation is unavailable. The partial fit artifact remains on EC2 and is not published. No fit was retried. The full E5 grid, global calibration replay, and final artifact validation remain pending. No fitted model is included in this result package.


The separate E4 nested-target identifier audit is available at [its metadata-only audit report](../engineering_audits/E4_NESTED_TARGET_ID_AUDIT_20261030.json) and [reproduction script](../engineering_audits/E4_NESTED_TARGET_ID_AUDIT_20261030.py). It checked the 42-target set and 126 other-class sets for nesting/overlap only; original within-target cohort ordering was not recovered.
