# Portable engineering qualification suite

The current EC2 qualification contains 653 collected test cases across 81 test files. The exact runner, case list, and byte-hashed source/test manifest are included. The qualification receipt is at ../../reports/PORTABLE_TEST_PASS_b537362afbfc5823e593479c549f12118e7e14099f06ab3265c1d5af8420b900.json; its fingerprint and input hashes are summarized in ../../metadata/PORTABLE_QUALIFICATION_653_SUMMARY.json.

The 653/653 result is an engineering qualification, not a scientific evaluation. It does not establish that the active archive transaction completed CRC validation and does not mark the research project complete. The full EC2 migration/runtime layout and its specified Python 3.12 environment are needed to reproduce this exact qualification; this Git export is not claimed to be independently pytest-self-contained.

The runner is run_portable_tests.sh. The qualified case list is ../PORTABLE_COLLECTED_NODEIDS_653.txt. The prior 596 case list and receipt remain as historical qualification evidence.
