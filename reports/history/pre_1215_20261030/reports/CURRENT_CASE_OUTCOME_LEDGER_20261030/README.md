# Current planned-case outcomes

Captured 2026-10-30T10:04:33.369017+00:00 from one read-only SQLite transaction. This is the current 2,823-row E3-E6 case status ledger, including a sanitized reason field and the case identity columns needed for review.

## Current counts

| Experiment | Planned | Successful | Recorded failures | Unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1,773 | 1,632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 717 | 50 | 78 | 101 | 14 |
| E6 | 21 | 12 aliases | 3 | 6 | 0 | 0 |
| Total | 2,823 | 2,425 including aliases | 127 | 89 | 168 | 14 |

The E6 primary ensemble test count is zero successful: three equal-weight test-prediction failures and three learned-weight unavailable outcomes. Its 12 successful rows are member-reference aliases. Failures, unavailable rows, user-stopped rows and pending rows are separate outcomes.

## Reason handling

The public reason field uses reason_text_curation.py. The helper changed 124 of 387 nonempty reason strings while preserving the scientific failure/unavailability meaning. A scan found no recognized process-receipt markers after curation. The raw reasons and attempt/process receipts are not included.

The earlier top-level reports/planned_case_ledger.csv is an older 2026-10-30T05:19:51Z snapshot that predates the applied stopped-scope status. It is preserved unchanged; use this dated ledger for the current point-in-time view. The planned denominator and original plan remain intact. This status snapshot does not assert final calibration audit or project completion.
