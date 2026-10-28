# Export curation

All legacy LAMOST_SUPERVISOR prompt, addendum, continuation, and handoff narrative files under reports/ were removed from this results-facing snapshot. They are operational chat handoffs, not scientific results or reproduction inputs. The original EC2 files and prior Git history remain preserved. The current point-in-time status is in LATEST_PROGRESS.md and metadata/current_execution_snapshot.json.

Historical raw portable-test and process-handoff receipts remain excluded. The current 730-case native qualification is represented by the privacy-curated summary at `provenance/qualification/QUALIFIED_730_PUBLIC_SUMMARY.json`, bound to the receipt and bundle SHA-256 values; process owner PIDs/start ticks are not included. The test bundle under `code/tests/` is preserved byte-for-byte as the enumerated qualification input.

The export contains scientific reports, tables, figures, source/configuration, selected provenance, and validation evidence. Raw process logs, private supervisor state, model files, raw source datasets, databases, credentials, and binary arrays are excluded. New E4 outcome arrays are published as verified release assets with validation and checksum metadata. Delta ZIP: /home/ubuntu/lamost_e1_migration_20261023/github_delta_results_20261028/e4_rep2_rf_validated_outcomes_delta.zip (7650932 bytes; SHA-256 d87f4aced90babbc9811447752f7b156a484290139bedf5cbfc023d09abbcfd3; CRC verified).

[Download the new E4 arrays](https://github.com/S-G-mathematics/lamost-six-experiments/releases/tag/results-2026-10-28). Use E4_DELTA_MANIFEST_20261028.json and E4_DELTA_SHA256SUMS_20261028.txt for mappings and checksums. All four remote asset hashes and sizes were verified.


The dated report refresh at `reports/INTERIM_REFRESH_20261028T170039Z/` contains descriptive CSVs and figures generated from a captured registry snapshot. Its portable `report_result.json` rewrites figure paths only; all scientific metrics/statuses remain bound to the original report result hash in the directory manifest. The root README and LATEST_PROGRESS are status-derived narratives; `metadata/current_execution_snapshot.json` is a sanitized projection and excludes process identities.
