# Working-storage source qualification 844

Observation: 2026-10-30T18:05:16.313172+00:00 UTC (portable qualification receipt); current registry status checked separately at 2026-10-30T18:22:37.090314+00:00 UTC.

## Qualified source and policy

Portable engineering qualification passed 844/844 planned cases with 105 subtests. Bundle fingerprint: 9e291822f6033540fcdcff17d1242474985dfd7f10584d10638c5bf84c13c26d; bundle SHA-256: 2ed0d180beafc0e59478be86cd9bc639b7b112e8da1e9d13569b67bf88b14474. The raw pass receipt is referenced by SHA-256 in the public summary, with process identity fields omitted. This is a code and test qualification result, not a claim of scientific completion.

The installed working-storage policy is working-reserve-6gib-one-fit-v1: 6 GiB working reserve, at most one concurrent fit, 10 GiB per-worker hard memory limit, 600-second trial and phase timeouts, 30-second termination grace, and one nested thread. Full archive verification remains a separate finalization step. These limits were not raised or relaxed by the source update.

The approved member-verification reuse in cold_model_storage.py can skip a redundant prior-member payload read only when the prior-commit proof validates exactly. Metadata/alias checks still run, new payload round trips remain fully checked, and missing or invalid proof falls back to full streaming verification. The adoption report explicitly says production cache-reuse speedup has not yet been measured.

## Source delta

The exact live code changes in this qualification are:

| Module | SHA-256 |
|---|---|
| cold_model_storage.py | 48fb2a2c52acdeb0a15fe36419676dbadc99d0ebdb46a3121e527471ffc45c57 |
| cold_auto_compaction.py | 998f1872bc353272de559944bf399ee5ec8b328dcacd6ecd02d1f7afc2cec373 |
| commit_batch_child.py | 1391c1a1e6690dcd5030c1ef9ad131f3d639b294986eea29fc3f872ec66676f5 |
| run_batch.py | aad668a8a28064b24f48942aa589daa42cb1f5c1106d25b5fb1d76f7bae63497 |

The focused member-cache test is code/tests/test_member_payload_verification_cache.py (SHA-256 0a949f69019bd0a92d7b37cc9de8c402f0d0b22c9c4aab6784bef5cc1acf36ff). The 844-case portable bundle also binds the exact source/test closure and runner. The controller, admission helper, frozen scientific case plan, experiment inputs, and scientific limits are unchanged in this source amendment.

## Evidence and limits

- [Portable qualification summary](../reports/engineering_audits/PORTABLE_TEST_PASS_9e291822f6033540fcdcff17d1242474985dfd7f10584d10638c5bf84c13c26d_PUBLIC_SUMMARY.json) cites the original pass-receipt SHA without copying its process-identity fields.
- [Member-cache adoption report](../reports/engineering_audits/STORAGE_MEMBER_VERIFICATION_CACHE_ADOPTION_20261030.json) documents the current-source archive pass observation and states that production cache-reuse speedup is not yet measured.
- [Working-storage policy](../provenance/manifests/WORKING_STORAGE_POLICY_20261030.json), [source amendment](../provenance/manifests/WORKING_STORAGE_OPERATIONAL_SOURCE_AMENDMENT_20261030.json), [frozen manifest](../provenance/manifests/freeze.json), and [narrow-profile qualification](../reports/engineering_audits/ARCHIVE_NATIVE_CODEC12_NARROW_QUALIFICATION_20261030.json) retain exact source hashes.
- Public source history under [storage_member_cache_20261030](../provenance/validation_sources/storage_member_cache_20261030/) retains the pre-amendment modules, freeze, and bundle for comparison.

The registry snapshot at 18:22 UTC remained 2,435 successful (including aliases), 127 recorded failures, 90 unavailable, 168 user-stopped, and 3 pending among 2,823 planned E3-E6 cases. E6 still has zero successful primary ensemble test evaluations. The storage qualification changes no scientific outcomes. Final calibration replay, complete artifact validation, and final project archive delivery remain pending.
