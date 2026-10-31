# Data availability and reproduction limits

## Scope

This public repository contains source code, saved scientific results, tables, figures and provenance. It does not include fitted classifier/model binaries, FITS files, or the baseline parquet payloads. The baseline file manifest and runtime role-cache manifest are published as identity metadata; those manifests do not contain the corresponding full data payloads. Role-membership/result arrays that are present in the results release are separately indexed in [RESULT_ARRAYS.md](RESULT_ARRAYS.md).

These exclusions describe the curated delivery snapshot. They are not a general repository rule, and this document does not attribute a blanket no-raw-data requirement to the user. No scientific payload was added by this documentation update.

## Frozen baseline identity on EC2

The baseline source root on EC2 is:

/home/ubuntu/lamost_e1_migration_20261023/project/lamost_baseline/

Its manifest.json inventories 43 files and has SHA-256 17b279bcdd5465df7e7c8c053c0657062da87070a0747399cfa776c163845a43. The public copy is [provenance/baseline_identity/manifest.json](../provenance/baseline_identity/manifest.json). The complete manifest gives relative path, byte size and SHA-256 for every listed baseline artifact. Selected identities:

| Relative path beneath baseline root | Bytes | SHA-256 |
|---|---:|---|
| data/baseline.parquet | 47,924,598 | 626873b20c4cbd8c99e66477111bbcd7a5212de500ac148338e8c5731c08dd39 |
| data/metadata.parquet | 145,299,047 | 5b689abdbd3a287e481aec8b95de2043aedb7c8f773e616d1719af721a6cca16 |
| data/source_candidates.parquet | 85,909,681 | b5be8370f32043465e36e0d5a56b2b09dba21536dfa9eb7c22f38d5c2e4ad099 |
| data/reference_standardized.parquet | 35,395,273 | 63ee1cbcf97a33dbeae0c95857f47d8ade299df97eddeff38999ea949c45262b |
| data/splits.parquet | 4,538,888 | 0a96395a1cd5495818988d07a5a18e36572eb66cad61e326ad52bdebbc7f98da |
| audit/row_disposition.parquet | 92,488,899 | 36fb519542d86cff64164d07707e46d4ecb3799f45194d9f10bf39becabac659 |
| audit/source_entity_membership.parquet | 25,511,477 | 7e447f6043829f2ddfd82b3ece3e9e49fdc98257958967ee8111617289cda9de |

The baseline payloads remain at the EC2 path above; they are not downloaded by cloning this repository. provenance/qualification_863/source_inputs/cache/cache_manifest.json is an exact 3,090-byte copy of the runtime cache manifest (SHA-256 bbcc195e0564066d541fbd483896935d7471e8893e6db34ca6184dfe90ee9720). It records six features, seven class labels, 1,830,835 development rows, 500,000 test rows, the baseline manifest hash and role-source hashes. It is metadata, not a substitute for cache payloads.

## Runtime role arrays and frozen E1 split provenance

The three current runtime role arrays are on EC2 at the paths below and are also represented in the separate results release. Hashes were measured on native files; release download/member checks are described in [RESULT_ARRAYS.md](RESULT_ARRAYS.md) and its manifests.

| Rep | EC2 runtime role path | Bytes | SHA-256 | Frozen E1 role-membership source path | Source SHA-256 |
|---:|---|---:|---|---|---|
| 1 | /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/cache/roles/rep_1.npz | 2,715,469 | 7bd1b5df13a4639dbffc7960d1403494d80655fc1b36f05604eda7a1773563de | /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1/rep_1/n_100000/role_membership.npz | e3ef78cddd5c23acebe8ff1a8fe8760e653da194cceebd45c5051416b329d334 |
| 2 | /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/cache/roles/rep_2.npz | 2,716,744 | 336faab22e3bb100ce56bf15ed713385f81fa8e3e6b781d13e5d77987b0239fc | /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1/rep_2/n_100000/role_membership.npz | 30f7d5d361a6563309f102f0d9ab9c676c630eee30f314bd49b64785b6ab4efc |
| 3 | /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/cache/roles/rep_3.npz | 2,717,200 | c149e76882c6c978d1fa1fd2cbe4dd98374c6cdfc716331e73f6f7f9998f46e7 | /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1/rep_3/n_100000/role_membership.npz | 1bc8859b0fee37c49ba92661e83a635c63564705968d294b61f19e55adacf63e |

The frozen E1 role-membership source files referenced by the cache manifest are at /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1/rep_<rep>/n_100000/role_membership.npz; per-repetition source SHA-256 values are in the published cache manifest. Do not equate these source hashes with runtime_20261025/cache/roles/rep_<rep>.npz hashes.

## What the public 863-test evidence means

The exact 863/863 portable engineering-suite pass is an EC2 result, bound by [the pass receipt](../provenance/qualification_863/PORTABLE_TEST_PASS.json) and [the source closure](../provenance/qualification_863/SOURCE_TEST_PUBLIC_PROOF_CLOSURE.json). The portable bundle lists 212 source inputs; 190 are mirrored in this repository. The cache manifest is included. The remaining 22 inputs are test/operational log bodies listed below, with source SHA-256 values in the closure JSON. Consequently, the public clone is not self-contained for rerunning that exact 863-test suite. The EC2 qualification is engineering evidence only; it does not establish scientific completion, full artifact validity, or successful global calibration/quantile replay.

A bounded content scan of these exact log inputs found process/argv/nonce markers in several collection logs. The log bodies are therefore kept out of the public clone as operational/test evidence. None of the 22 excluded paths is scientific Python method code, a scientific trial CSV/JSONL, or a baseline configuration file:

- runtime_20261025/logs/operational/terminal_portable_tests_326f91512a62469ca1919ba6a81332ec.log
- runtime_20261025/reports/engineering_audits/CODEC4_COLLECT_ONLY_776_20261029.log
- runtime_20261025/reports/engineering_audits/CODEC4_FOCUSED_21_FRESHNESS_CLOCK_20261030.log
- runtime_20261025/reports/engineering_audits/CODEC_FOCUSED_25_FRESHNESS_CLOCK_20261030.log
- runtime_20261025/reports/engineering_audits/CODEC_FOCUSED_25_REAPER_BINDING_20261030.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_ADMISSION_HARNESS_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_ADMISSION_HARNESS_SELECTION_COMPAT_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_COLLECT_759_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_COLLECT_FINAL_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_COLLECT_ONLY_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_FOCUSED21_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_CODEC_FOCUSED21_SELECTION_COMPAT_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_RAW_CODEC_FOCUSED39_20261029.log
- runtime_20261025/reports/engineering_audits/CURRENT_RAW_FOCUSED_SOURCE_REFRESH_20261029.log
- runtime_20261025/reports/engineering_audits/E1_PRIMARY_LOCATOR_COLLECT_ONLY_805_20261030.log
- runtime_20261025/reports/engineering_audits/E1_PRIMARY_LOCATOR_COLLECT_ONLY_806_20261030.log
- runtime_20261025/reports/engineering_audits/E1_PRIMARY_LOCATOR_COLLECT_ONLY_807_20261030.log
- runtime_20261025/reports/engineering_audits/E1_PRIMARY_LOCATOR_STRICT_PREFIX_FOCUSED_9_20261030.log
- runtime_20261025/reports/engineering_audits/SELECTION_COMPAT_COLLECTION_20261029.log
- runtime_20261025/reports/engineering_audits/archive_native_fit_overlap_D_qualification_20261028/controller_harness_7.log
- runtime_20261025/reports/engineering_audits/archive_native_fit_overlap_D_qualification_20261028/suite_15.log
- runtime_20261025/reports/engineering_audits/selection_fallback_focused_tests_20261029.log

## Reproduction checklist and limits

For descriptive regeneration from published result tables and arrays:

1. Start from the result and provenance links in the top-level [README](../README.md), including the 2,823-row case ledger, 2,438-reference evaluation SHA crosswalk and scientific log-coverage report.
2. Verify each downloaded release archive against SHA256SUMS.txt; check ZIP CRC and member hashes against the release manifest before extracting to a new, empty directory.
3. Preserve experiment manifests, source/configuration hashes, class order (A, F, G, K, M, GALAXY, QSO), seed, and fit/tune/calibration/test roles. Use [the E1 protocol and dependency record](../code/E1_benchmark/Experiment_1_Setup_and_Readiness.txt), [frozen manifests](../provenance/manifests/), and [the baseline identity manifest](../provenance/baseline_identity/manifest.json).
4. A fresh independent run needs the exact baseline inputs and role assignments identified above plus the recorded code and dependencies. Those baseline payloads are EC2-local and are not reconstructed by the public clone. The 863 engineering pass does not supply them.
5. Do not rerun frozen E1 or the stopped recovery study to fill historical gaps. Saved E1/E2 test outcomes predate the later project plan. Historical E1 fitted models remain absent; 80 of 674 successful frozen-E1 prediction arrays and 24 recovery prediction arrays are in the release.

Final artifact review and global calibration/quantile replay remain pending. The current E3-E6 case snapshot has all 2,823 planned cases terminal (2,438 successful references including 12 E6 member aliases, 127 recorded failures, 90 unavailable, 168 user-stopped); E6 has zero successful primary ensemble test results. This is a dated scientific ledger status, not a claim that the overall project is complete.
