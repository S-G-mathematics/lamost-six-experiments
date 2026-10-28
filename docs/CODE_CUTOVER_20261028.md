# Active code cutover snapshot

This delta exports the qualified active EC2 source modules, policy manifests, and portable test closure. The code/source directory maps to native EC2 runtime_20261025/source; code/tests maps to runtime_20261025/tests. This archival layout does not recreate the full EC2 runtime tree. Frozen E1 source files are unchanged.

The latest portable qualification fingerprint is b537362afbfc5823e593479c549f12118e7e14099f06ab3265c1d5af8420b900. Its exact bundle SHA-256 is 81df8fba5bfc4af03824c49e92a9a6db70b7749611a008713b56d1457c13019f, with 653/653 engineering tests passed on EC2 at 2026-10-28 09:01:38 UTC. The 596/596 and 587/587 receipts and node lists remain preserved as earlier qualification history. The 653 node list contains the prior 596 IDs plus 57 new IDs. This engineering result adds no scientific evaluations, does not establish archive CRC completion, and does not claim that the Git snapshot is independently pytest-self-contained.

The Git delivery excludes raw baseline data, generated training data, fitted pipelines, databases, credentials, and private operational process receipts. Scientific result arrays are linked separately. Three validated result records since the prior Git snapshot are described in the E4/E5 incremental supplement; two unique test-outcome arrays are staged separately, with release upload still pending.
