# Independent saved-table verification of E2

Observed UTC: 2026-10-25T12:59:33.755066+00:00

Saved E2 sources and the frozen E1 ledger remained byte-unchanged. The read-only check found 0 inconsistencies. It ran no fitting, generation, tuning, prediction, SDMetrics evaluation or bootstrap.

Primary coverage remains 108/150, with 42 unavailable. Classical references remain 120/120.

Cross-checks linked all 270 planned E2 rows to the frozen E1 ledger. All 43 original saved-fit accuracy scores match E1. Among 185 reconstructed-fit scores, 154 match original balanced accuracy exactly and 31 differ; maximum absolute difference is 3.1739351391335546e-05. Exact metric equality does not prove original model identity or identical per-row predictions.

All 1596 class reports form 228 complete seven-class equal-weight means. All 210 low-precision flags (diagnostic n < 20) were retained and verified, with no class dropped.

## Complete primary correlations

All correlations were recalculated within budget/repetition; there is no pooled correlation or significance claim. Only four of thirty strata have all five families. Those four also contain low-precision class reports.

| Budget | Repetition | Spearman rho |
|---|---:|---:|
| 3000 | 3 | 0.7 |
| 3000 | 5 | 0.09999999999999999 |
| 10000 | 1 | 0.3 |
| 10000 | 2 | 0.7 |

The other 26 strata retain separately labeled available-only exploratory correlations. The initial E2_spearman_within_budget_repetition.csv belongs to the earlier saved-fit-only stage; use the combined and within-stratum tables referenced by E2_CURRENT_REPORT.md for the final E2 analysis.

## Evidence and scope

- E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv: all 185 reconstructed-fit differences at saved numerical precision.
- E2_CORRELATIONS_INDEPENDENTLY_VERIFIED.csv: all 30 strata and primary/exploratory separation.
- engineering_audits/E2_saved_tables_independent_reaudit_20261025.json: source SHA-256s, counts and check results.
- Re-run on EC2 with the frozen venv: python source/audit_e2_saved_tables.py.

This check verifies saved numerical evidence. It does not restore omitted historical models/predictions, rerun the original diagnostics, or replace the full final scientific audit.
