# E5 label-noise realization audit

The validated data-only audit covers 9 planned label-noise realizations (3 repetitions x 5%, 10%, and 20% affected fitting rows) and 63 source-class rows (9 realizations x 7 classes). The CSV records original full fitting-class counts, affected/changed row counts, and realized source-class corruption rates. Nested masks passed for all three repetitions, with affected-ID counts 4,000, 8,000, and 16,000 at the three rates. The audited fitting role has 80,000 rows; fit/tune/calibration memberships are disjoint and their hashes match the role-cache manifest.

This verifies corruption-mask realization/provenance only. It is not a classification evaluation, and it does not complete E5. No model, prediction, fitting, inference, or calibration work was performed in this audit. Global calibration-q replay remains pending.

Source CSV SHA-256: e9cb09996954185b59c9f5a827c6d3f9bc717c20e16f4dc24fd0e6ee81207c93. Audit JSON SHA-256: 2889a768f551844c6dfaec3d11b99332d1bcc1f0126ec60e03c824e4bc5070b3.
