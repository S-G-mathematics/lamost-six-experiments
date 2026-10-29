# Incremental evaluation audit

The incremental evaluation audit was generated at 2026-10-29T14:32:42.526797+00:00 UTC from registry snapshot 2026-10-29T12:39:37.262782+00:00 UTC. It contains 2400 validated successful outcome entries (2279 physical outcomes and 121 aliases), with 0 issues, 0 blocking review issues, and 18 diagnostic limitations. The empty issues CSV and the diagnostic limitations CSV are retained alongside the audit JSON.

The audit is evaluation-only. It verifies recorded evaluation artifacts and status; it does not recompute the conformal calibration quantile. Calibration-score replay and final project validation remain pending. This is not a claim that the full project is complete.

A later independent read-only SQLite transaction observed the following execution status at 2026-10-29T17:24:39.261170+00:00 UTC (6,270 task rows; 2,823 planned E3-E6 scientific cases):
- E3: 64 successful, 3 recorded scientific failures, 2 unavailable, 0 waiting, 0 user-stopped.
- E4: 1624 successful, 71 recorded scientific failures, 3 unavailable, 8 waiting, 67 user-stopped.
- E5: 700 successful, 50 recorded scientific failures, 78 unavailable, 31 waiting, 101 user-stopped.
- E6: 12 successful, 3 recorded scientific failures, 6 unavailable, 0 waiting, 0 user-stopped.
- Selected one-per-case evaluations: 6 successful and 39 still waiting at 2026-10-29T17:24:39.261170+00:00 UTC. The 168 user-stopped scientific rows remain separate.

The audit cutoff predates this status read, so its 2,400 entries should not be described as the later queue snapshot. No model files, data arrays, private process receipts, or operational logs are included in this dated audit directory.

Input SHA-256 values:
- INCREMENTAL_EVALUATION_AUDIT.json: 898ff93db1d5522ac6637ea6e3b3f2c6702d121b7590d4c696f93c1a3708145d
- INCREMENTAL_EVALUATION_ISSUES.csv: 705eedb2f4753d92e3972e671ae05bd5fb8427579275b33a2b0dc52be059464c
- INCREMENTAL_EVALUATION_DIAGNOSTICS.csv: 5365baf9e40087aa2a4cac7df3104b216119da9e202d16ed1b85d684e9547552
