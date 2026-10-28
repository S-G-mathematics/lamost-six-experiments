# Active code cutover snapshot

This delta exports the qualified active EC2 source modules and portable test closure after the 2026-10-28 archive-I/O cutover. Active code also includes the verified cold model store, finalization-safety fix, coalesced archive digest path, and three archive child wrappers. The code/source directory maps to native EC2 runtime_20261025/source; code/tests maps to runtime_20261025/tests. This archival layout does not recreate the full EC2 runtime tree.

Changed active modules include controller, archive fit admission, finalizer, cold auto-compaction, commit batch child, and batch runner. Frozen E1 sources under code/E1_benchmark were not changed. Public fixtures were copied byte-for-byte after checking their JSON keys for private process and credential fields.

The portable qualification fingerprint is 69673ee4e0e2b4ec788262702314e6c058abd36f09c863342aa26a77e925a199. The PORTABLE_TEST_BUNDLE SHA-256 is 27f651fbb10850f372407789e62d1674f12c0c45abd925f54983cab0276c1131. It records 587/587 engineering tests passed (the preserved 579-test closure plus 8 new tests) on EC2 under the native source closure. This does not claim the Git snapshot is independently pytest-self-contained. No new scientific fit, prediction, calibration, or test evaluation was run for this code delta.

The Git delivery excludes raw baseline data, generated training data, fitted pipelines, databases, credentials, and private operational process receipts. Scientific result arrays are linked separately in assets_not_bundled.csv.
