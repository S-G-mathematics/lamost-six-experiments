# Interim result-asset coverage and resource approval update

**Status observation:** 2026-10-30 11:05:18 UTC. The latest coherent E3-E6 case ledger remains the 10:04:33 UTC read-only snapshot; this update does not regenerate that ledger or any scientific metrics. The project remains incomplete.

## Result and release coverage

The metadata-only [GitHub asset coverage audit](../reports/GITHUB_AVAILABLE_RESULT_PAYLOAD_COVERAGE_20261030/README.md) verifies GitHub API size and digest matches for the 19 base release assets and the separate later assets. Its JSON contains the per-asset evidence and source hashes.

The original result release manifest has 4,455 NPZ members and no fitted-model or FITS members. The audit confirms exact path, SHA-256, and size matches for 80 frozen E1 primary prediction arrays and all 24 stopped-recovery prediction arrays. That is 80 of 674 successful frozen E1 cells with retained model/prediction pairs; the other 594 successful cells do not have retained primary pairs in the referenced locator. The corresponding fitted models are not in the GitHub release. The E1 recovery remains a separate supplement and does not change the frozen 765-case ledger.

The separate current E3-E6 outcome catalog has 2,322 test-outcome array paths. All 2,322 have exact archive-member SHA-256, size, and CRC evidence. Of those, 2,214 match members in the base release; 108 are distinct additions across the 104-member current E4/E5 asset and the four-member E5 delta asset. The 2,322 catalog is a path inventory with overlap and is not added to the 4,455-member base count. Its 2,823-row status ledger is also separate from payload counts.

The successful-task artifact crosswalk covers 2,425 successful rows, including aliases mapped to canonical artifacts, and the repository contains the 165 metadata records added during reconciliation. The Git tree contains no fitted-model, FITS, or NPZ/NPY binaries. No fitted models, FITS products, or raw training datasets are being published.

The Git copy of the audit README corrects one stray line break splitting the word results; source and exported hashes are recorded in file_manifest.csv, and the EC2 source file was not changed.

## Experiment status and limits

The public 2,823-row case ledger remains linked in [LATEST_PROGRESS.md](../LATEST_PROGRESS.md). Its last coherent snapshot records E3 64/69 successful; E4 1,632/1,773 successful with 67 user-stopped; E5 717/960 successful with 14 pending, 50 failures, 78 unavailable and 101 user-stopped; and E6 with 12 successful E3-reference aliases, zero successful primary ensemble evaluations, 3 primary failures and 3 primary unavailable cases. Full calibration-quantile replay and final artifact validation remain pending.

## Storage and approved reserve

After the 10:45-10:47 UTC LAMOST-only cleanup, available space was 19,182,096,384 bytes at 11:05:18 UTC. The unchanged 20 GiB standard floor is 21,474,836,480 bytes, leaving a 2,292,740,096-byte gap. The prior cleanup retired 2,132 already-published payload groups (5,601,906,688 allocated bytes); a 628,975,775-byte verified download cache was evicted separately and is not counted again.

The user has approved considering a 6 GiB working reserve with one concurrent fit, while retaining the 10 GiB per-fit ceiling and 600-second phase limit. Implementation and validation are still in progress; the 6 GiB reserve is not active, the standard floor has not been replaced, and no fit has started under the proposed setting. No scientific resource or retry policy has been changed in this update.
