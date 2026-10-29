# Deadline snapshot metadata capture fix

This is a reporting and packaging repair. It does not change a scientific protocol or any experiment result.

The first deadline packaging attempt failed because the isolated report-builder runtime did not contain the frozen task manifest, scope amendment, scope application receipt, and report template. The failed attempt was preserved privately on EC2. The repaired runner copies those four immutable metadata inputs into its temporary runtime, records each canonical source path, byte size, and SHA-256, and checks source and copied hashes before and after report generation. The amendment is still bound to its canonical EC2 absolute path and original SHA; the frozen task-manifest hash and the 2,823-case denominator checks remain enforced. Registry rows and evaluation JSON inputs continue to come from one read-only SQLite snapshot with post-capture hash checks.

The runner now includes all 6,270 sanitized DAG rows in the captured registry while deriving scientific counts only from the 2,823 planned E3-E6 cases. Non-scientific helper rows use the same reviewed allowlist and do not enter scientific metrics.

Focused checks passed on EC2: Python compilation, the builder's pure refresh self-test, the timer's SQLite/privacy/case-accounting self-test, and two metadata-snapshot unit tests. The bounded retry produced an interim package with CRC verification; see the timestamped EC2 package receipt for the exact package hash and status. The package remains interim and does not claim project completion.

## Source provenance

| Destination | EC2 source | SHA-256 |
|---|---|---|
| code/reporting/build_deadline_report.py | runtime_20261025/reports/deadline_submission_20261029/build_deadline_report.py | 3bd7a6483bc8d3c59e323a5cd0eac952d615af16389c780535dbcc18a57b0c79 |
| code/reporting/deadline_snapshot_runner.py | runtime_20261025/staging/deadline_reporting_20261029/deadline_snapshot_runner.py | 320f3a2f0823582f5dca810ea50a95aa806d7a7e0553b22575207eec0d02389f |
| code/tests/test_deadline_metadata_snapshot.py | runtime_20261025/tests/test_deadline_metadata_snapshot.py | 2911d71f4c3ec91c24ecec7247b890390a36840ab4f9a2c8c164923f4c09223d |
| handoff/LAMOST_SUPERVISOR_REVIEW_PROMPT_20261029.md | reports_handoff_20261029/LAMOST_SUPERVISOR_REVIEW_PROMPT_20261029.md | fef38a24016a64c74a1a699925a55d4feb45c802cb11968b594c4c4fa2d5a3c2 |
| code/delivery_tools/copy_deadline_snapshot_20261029.ps1 | reports_handoff_20261029/copy_deadline_snapshot_20261029.ps1 | d260553bc1967627395f58066c39b43525eaa32bfc010685603685fb411f3234 |
