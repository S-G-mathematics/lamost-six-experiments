# Active code cutover snapshot

This delta exports the qualified active EC2 source modules and portable test closure after the 2026-10-28 cutover. The code/source directory maps to native EC2 runtime_20261025/source; code/tests maps to runtime_20261025/tests. This archival layout does not recreate the full EC2 runtime tree.

Changed active modules include controller, archive fit admission, finalizer, cold auto-compaction, commit batch child, and batch runner. Frozen E1 sources under code/E1_benchmark were not changed. Public fixtures were copied byte-for-byte after checking their JSON keys for private process and credential fields.

The portable qualification fingerprint is 5b78231f2d89ec012e9867fb12635549aaae33df14a51e94c23eeecc86737944. The PORTABLE_TEST_BUNDLE SHA-256 is a5ff284a4f6107b52b6122ba1b0776a65540eb09dbe5c817fddb55c85f632a3f. It records 579/579 engineering tests passed on EC2 under the native source closure. This does not claim the Git snapshot is independently pytest-self-contained. No new scientific fit, prediction, calibration, or test evaluation was run for this code delta.

The Git delivery excludes raw baseline data, generated training data, fitted pipelines, databases, credentials, and private operational process receipts. Scientific result arrays are linked separately in assets_not_bundled.csv.
