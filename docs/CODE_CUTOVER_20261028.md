# Active code cutover snapshot

This delta exports the qualified active EC2 source modules, policy manifests, and portable test closure. The code/source directory maps to native EC2 runtime_20261025/source; code/tests maps to runtime_20261025/tests. This archival layout does not recreate the full EC2 runtime tree. Frozen E1 source files are unchanged.

The current portable qualification fingerprint is 2fd590500002516fe9a1adef2afecafe5379a29281e1d74a3329dfa03871f057. The PORTABLE_TEST_BUNDLE SHA-256 is 3a5d88d3cbd3693c8dfadfebd41cb98b93e762a29d8a1c66323d95dd54bb4c09. It records 596/596 engineering tests passed on EC2. The 587/587 receipt and node list remain preserved as earlier qualification history. The current 596 node list records 596 unique collected tests; the bundle states 595 prior baseline entries retained and one additional test. This engineering result does not add scientific evaluations and does not claim the Git snapshot is independently pytest-self-contained.

The Git delivery excludes raw baseline data, generated training data, fitted pipelines, databases, credentials, and private operational process receipts. Scientific result arrays are linked separately. Three validated result records since the prior Git snapshot are described in the E4/E5 incremental supplement; two unique test-outcome arrays are staged separately, with release upload still pending.
