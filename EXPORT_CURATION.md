# Export curation

## Scope amendment and current portable qualification refresh

The current coherent status report and all saved validated metrics are under reports/deadline_scope_snapshot_20261029T0910Z. CURRENT_CELL_LEDGER.csv accounts for all 2,823 E3-E6 planned scientific cases at that registry snapshot. The 793-test portable qualification source/test closure is mirrored under code/ and provenance/qualification_793; all source and test hashes were checked against the runtime bundle before copying.

Raw operational logs and evidence containing private process/supervision fields were excluded. Only their bundle-member path and expected SHA-256 are recorded in provenance/qualification_793/EXCLUDED_PORTABLE_SOURCE_MEMBERS.csv. The raw EC2 evidence is unchanged. The missing ET4 resource-disclosure test was restored byte-for-byte from the qualified staged copy; a correction receipt records that deployment.

This Git update excludes fitted models, FITS, raw baseline data, prediction arrays, credentials, private process/cleanup receipts, and Harbor material.
