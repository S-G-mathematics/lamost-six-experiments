# Scientific result payload catalog

This sanitized metadata snapshot was derived from the versioned EC2 terminal-result catalog at the observed UTC time in catalog_summary_v2.json. It contains a 2,823-row planned E3-E6 case ledger and a 2,322-path scientific result payload inventory. All payload paths in this version have exact remotely verified member SHA-256, uncompressed size, and ZIP CRC evidence. E4 historical rows already marked restore-required remain flagged as such.

The new E4/E5 array asset is listed in new_104_asset_verification.json and its 104-member ledger. It was uploaded to the existing results-2026-10-28 GitHub release. The remote download SHA/size matched the GitHub API digest, ZIP CRC passed, and every member SHA/size/CRC matched its saved validation metadata. The local temporary ZIP was removed only after verification; the original native E4/E5 arrays remain preserved on EC2.

This is an interim snapshot, not a claim that all planned cases completed. At the catalog observation time E5 had 14 waiting evaluation rows. E6 had 12 successful reference aliases, 3 unavailable reference aliases, and no successful primary ensemble result among 6 primary rows. Historical E1 artifacts absent from EC2 were not reconstructed/restored. The delta contains test outcome arrays only: no fitted models, FITS, raw training data, private process receipts, or credentials.

The CSV/JSON files use canonical logical artifact paths relative to runtime_20261025. Absolute host paths, native inode/device metadata, process identifiers, private receipt paths, and signed URLs are omitted.
