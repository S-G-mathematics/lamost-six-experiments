# Active code cutover snapshot

This delta exports the qualified active EC2 source modules, policy manifests, and portable test closure. The code/source directory maps to native EC2 runtime_20261025/source; code/tests maps to runtime_20261025/tests. This archival layout does not recreate the full EC2 runtime tree. Frozen E1 source files are unchanged.

The latest portable qualification fingerprint is 72875f36da6833a441e30a4b21fe248591a65955dc7c5612bdb1c7f711283234. Its exact bundle SHA-256 is e883ff20b254bc029765237864d7c29bc890e5b706762a32efa9b9180add9f48, with 667/667 engineering tests passed on EC2 at 2026-10-28T10:00:33.925387+00:00. The 653/596/587 receipts and node lists remain preserved as earlier qualification history; all 653 prior collected IDs appear in the 667 list. This engineering result adds no scientific evaluations, does not establish archive CRC completion, and does not claim that the Git snapshot is independently pytest-self-contained.

The Git delivery excludes raw baseline data, generated training data, fitted pipelines, databases, credentials, and private operational process receipts. Scientific result arrays are linked separately. Three validated result records since the prior Git snapshot are described in the E4/E5 incremental supplement; two unique test-outcome arrays are staged separately, with release upload still pending.
