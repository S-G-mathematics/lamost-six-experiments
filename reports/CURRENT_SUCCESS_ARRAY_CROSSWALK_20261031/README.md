# Successful evaluation to result-array crosswalk

Generated 2026-10-31T02:14:21.768872+00:00. This is a metadata-only join. It does not open or hash any NPZ payload and does not load models or recompute evaluations.

## Coverage

- 2438 successful E3-E6 evaluation references map to 2317 distinct physical test_outcomes.npz arrays.
- 121 references are aliases. Each alias is resolved through its saved alias_source_key chain to a canonical physical payload; rows are not counted as duplicate arrays.
- Physical payloads: E3 64, E4 1611, E5 642. E6 contributes 12 member-reference aliases and no successful primary ensemble array.
- Every physical payload's validation.json names the same expected NPZ SHA-256 as the release-member descriptor. Its validation metadata file is also SHA-bound to its Git copy; older cases use the saved artifact-coverage binding and five latest E5 cases use their case-crosswalk sibling paths.
- All 15 referenced release assets matched current GitHub API SHA-256 digest and byte size. The published member descriptors include member SHA-256, byte size, and CRC32.
- 13 later arrays extend the dated original catalog: 8 in the rep-1 manifest, 1 separately verified rep-1 asset, and 4 in three later additive receipts.
- The old catalog's 18 historical/pre-support payload rows are excluded from the current successful-case mapping.

## Files

- [Case to physical payload crosswalk](SUCCESSFUL_CASES_TO_PHYSICAL_PAYLOAD.csv) has one row per successful evaluation reference and the exact array asset/member evidence.
- [Unique physical arrays](PHYSICAL_SUCCESSFUL_ARRAY_MEMBERS.csv) has one row per canonical current test-outcome array.
- [Machine-readable coverage receipt](COVERAGE.json) binds source evidence and the generated CSV hashes.

## Limits

The published release-asset API metadata was checked during this snapshot, but this step did not redownload all ZIP payloads. Existing member-level SHA/size/CRC evidence was reused from the exact-member catalog and dated publication receipts. E1 prediction arrays are reported separately; historical E1 fitted models and many E1 prediction arrays remain unavailable. The crosswalk does not finish global calibration replay or the final artifact audit, so it is not a final project validation.
