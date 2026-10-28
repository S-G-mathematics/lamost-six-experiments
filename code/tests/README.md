# Portable engineering qualification suite

The latest EC2 qualification contains 667 collected test cases across 84 test files. The exact runner, case list, and byte-hashed source/test manifest are included. The qualification receipt is at ../../reports/PORTABLE_TEST_PASS_72875f36da6833a441e30a4b21fe248591a65955dc7c5612bdb1c7f711283234.json; its fingerprint and input hashes are summarized in ../../metadata/PORTABLE_QUALIFICATION_667_SUMMARY.json.

The 667/667 result is an engineering qualification, not a scientific evaluation. It does not establish that an archive transaction completed CRC validation and does not mark the research project complete. The full EC2 migration/runtime layout and its specified Python 3.12 environment are needed to reproduce this exact qualification; this Git export is not claimed to be independently pytest-self-contained.

The runner is run_portable_tests.sh. The qualified case list is ../PORTABLE_COLLECTED_NODEIDS_667.txt. The prior 653, 596, and 587 case lists and receipts remain as historical qualification evidence.
