# E3 real-only random forest: repetition 1 publication-record limitation

Observed on 26 October 2026. The selected model for e3/rep_1/fit/real/random_forest has no fit_publication.json. Its fitted pipeline, selected configuration, fit result and validation record remain present. The pipeline SHA agrees between the file, fit result and validation record; the selection SHA agrees with validation. The frozen task and recorded fit agree on their role references, selected configuration and 80,000 fitting rows.

This missing publication receipt is an artifact-provenance limitation. It does not by itself invalidate the recorded successful E3 evaluation. No receipt has been reconstructed and no E3 or E1 fit has been rerun.

The prospective 4 GiB admission estimate for E5 direct-RF evaluations requires a complete baseline publication record. Repetition 1 therefore retains the default 10 GiB admission profile. Its E5 evaluations are not marked scientifically unavailable by this scheduling gate. Repetitions 2 and 3 have their publication records.

The diagnostic is not a full independent selected-model audit. Final model and outcome validation remains required.

## Evidence

- Frozen plan SHA-256: 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb.
- Selected pipeline SHA-256: 0a6820000e4b4c4ecfa1ec7f4244ae69d31b2b59706407912c5fab9f05f8d19e.
- Selected-configuration SHA-256: 7cef620f39c9d16cd289057b8445526dc2b306de73a47d8bf3ad520e1bd2a425.
- Read-only diagnostic SHA-256: f51207900813606a33963a8411236446c37ba49fc7d15b1214cd142f4365ff70.

## Independent saved-fit audit follow-up

At 2026-10-26 03:59 UTC (09:29 Asia/Kolkata), an independent audit of this one saved fit passed with zero issues and zero diagnostics. It checked model identity, selected parameters and seeds, class counts and fitting IDs, and preprocessing against the permitted fitting rows. All checked source/model files remained unchanged. The audit performed no fitting, generation, prediction, calibration or test inference, and did not reconstruct fit_publication.json. It does not measure inference memory or replace the required final project-wide artifact audit.

Receipt: reports/engineering_audits/E3_REP1_REAL_RF_SELECTED_FIT_INDEPENDENT_AUDIT_20261026.json; SHA-256 c381ddc5683158a642d3fb447e1f72bec240a7420234e2147c3c51d2cc3bcf19.
