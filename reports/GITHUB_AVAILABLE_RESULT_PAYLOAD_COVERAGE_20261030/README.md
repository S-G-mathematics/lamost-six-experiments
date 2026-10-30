# GitHub Available Result Payload Coverage

Generated from local manifests and GitHub release asset metadata on 2026-10-30. This is a metadata-only artifact-coverage audit. It did not download or extract release payloads, read model/prediction contents, fit models, or evaluate cases.

## Verified release contents

The original results-2026-10-28 manifest lists 19 release assets and 4,455 .npz members (7,291,372,871 uncompressed bytes). The manifest has no .joblib, .pkl, .pickle, FITS, ONNX, or torch-model member and explicitly excludes fitted models. The current GitHub Release API reports all 19 expected assets present with exact manifest size and SHA-256 digest matches.

All 80 frozen E1 primary prediction arrays available from the retained-primary locator match a release member by relative path, SHA-256, and byte count. All 24 stopped-recovery prediction arrays available from its locator match as well. These are 80 of the 674 successful frozen E1 cells with retained model/prediction pairs. Frozen E1 also has 81 failures (55 resource, 26 supervisor-terminal) and 10 unsupported cells. The other 594 successful cells do not have a retained primary pair in this locator; historical E1 pipelines and prediction arrays remain subject to the known compact-migration omission caveat. The associated 80 primary and 24 recovery fitted models are in the protected E1 wrap-up archive, not in the GitHub release assets.

The released payload is not only runtime test outcomes. Its 2,205 runtime outcome arrays total 5,707,227,131 bytes; the remaining 2,250 files (1,584,145,740 bytes) comprise E1 predictions and role arrays, E2 fidelity samples/reference IDs, E5 corruption audits, historical outcomes, runtime role arrays, and E6 tuning posteriors. Category-level counts and bytes are in the JSON.

## Separate later outcome publication

The later Git catalog sync record describes a separate 104-member release asset and a 2,322-path current payload catalog. A separate four-file, 2,823-row current case-outcome status ledger is also recorded below. The current GitHub API size and digest match that asset's sync record. The 2,322-path catalog has 2,214 exact path+SHA-256+size matches with the base 4,455-file manifest. Its 108 non-base members are 104 entries in the separate current E4/E5 asset and four entries in a separate E5 delta asset. All 2,322 crosswalk paths are .npz; all 11 referenced assets are present in the current GitHub API with matching digest and size. The current release API digest and size match both additional assets. Do not add the full 2,322 catalog or its 104-member subset on top of the 4,455 base count. The four-file status ledger is not an array payload count. See the exact Git sync record, commit, catalog hashes, and asset metadata in the JSON.

## Evidence and limits

The JSON records SHA-256 values for the base release manifest and E1 source locators, the pinned E1 wrap archive identity, exact per-prediction path/hash/size matches, API metadata for all 19 base assets, and API metadata for the separate later asset. No release ZIP payloads were downloaded or CRC-tested during this audit. The original frozen E1 snapshot and wrap-up ZIPs remain unchanged on EC2.
