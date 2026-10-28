# Export provenance

This is a curated code-and-results snapshot. Original EC2 scientific files were not modified.

file_manifest.csv records source and destination SHA-256 hashes and byte sizes. They can differ: JSON is parsed and pretty-printed, CSV is reserialized, and recognized private process fields are removed from exported JSON and embedded supervision dictionaries in free-text reason fields. Scientific metrics, labels, counts, selected parameters, outcome statuses and failure explanations must retain their scientific meaning. The independent export audit checks semantic preservation.

Private fields removed include process IDs, command arguments, environment-variable maps, raw stdout/stderr, process inventories, private receipt paths and hold nonces. Aggregate timing/resource observations and scientific phase/failure reasons remain. The exact reason-text sanitizer is preserved in code/source/reason_text_curation.py.

Original E1 source, protocol and dependency specifications retain their source hashes. The complete frozen ledger remains separate from recovery outcomes. Source bytes and curated export bytes are distinct evidence; an export hash must never be substituted for the original frozen-source hash.

snapshot_manifest.json inventories delivered Git files, including generated documentation and metadata. file_manifest.csv maps copied source files only, so generated export documentation is not expected in it. The snapshot manifest does not contain its own hash; the Git commit identifies it.

Large result/role arrays are separate release assets with their own member inventory and checksums. Missing historical E1 model/prediction artifacts remain missing. No fitted model or FITS file is part of this Git delivery.
