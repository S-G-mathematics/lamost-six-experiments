# Current source hash proof

Observed 2026-10-27T10:45:46.228976+05:30 (Asia/Kolkata). All 19 original benchmark Python source files match the hashes in the validated frozen E1 effective run configuration. All 11 current runtime source files match `runtime/manifests/freeze.json`. The live controller identity was verified by the read-only observer; controller SHA-256 `964e3099ce9b39661519a67943a4db2126632b512ba0e7952c25a71cc10ae903`.

This verifies source bytes and manifests. It does not rehash the historical full backup archive or recover omitted fitted models.
