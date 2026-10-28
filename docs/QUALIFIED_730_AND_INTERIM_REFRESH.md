# Qualified operations update and interim report snapshot

## Operations qualification

The 2026-10-28 native qualification records 730 passing cases, bundle fingerprint 954cd3dff7872266c8e1e15632c94a2d7cacaf74037687dda3af6bf0d1b97204, and qualification receipt SHA-256 4b7563bb6d8287c08a45d59cb34c5bedf7ed5297a9593f3bf004997dc05cfcf9. The public summary is in `provenance/qualification/QUALIFIED_730_PUBLIC_SUMMARY.json`; private owner process identities are omitted. The exact portable test bundle, its 730 node-ID collection, two new RF4 admission tests, and runner are under `code/tests/`.

The current source freeze contains 16 pinned files. The controller update is operational scheduling/admission code; no scientific experiment method or E1 source was changed. The new E4 repetition-3 random-forest treatment profile is a 6 GiB scheduler admission reservation. It does not change the scientific worker limit (10 GiB), tuning-trial timeout (600 seconds), or experiment protocol. The profile manifest and privacy-reviewed evidence are included. Qualification is engineering evidence, not an experiment result.

## Interim descriptive outputs

The report tables and 21 figures are in `reports/INTERIM_REFRESH_20261028T170039Z/`. E3-E6 outputs use registry observation 2026-10-28T17:00:39.712874+00:00 and account for 2,823 planned cases: 2,366 successful, 127 scientific failures, 89 unavailable, and 241 waiting. Three previously validated E1/E2 figures are preserved with the refreshed E3-E6 figures. A later status observation at 2026-10-28T17:21:42.173333+00:00 records E4 1592 successful / 107 waiting and E5 700 successful / 132 waiting; no fitting worker was active in that observation. The figures were not silently advanced beyond their bound registry snapshot.

This remains an interim research snapshot. E4/E5 have pending cells; E6 primary ensembles have no successful test result; full native calibration/q-replay and final project archive validation are not complete. Frozen E1/E2 results and their provenance caveats remain unchanged. No bootstrap or significance claims are added. The repository excludes fitted models, FITS files, credentials, and private operational receipts.
