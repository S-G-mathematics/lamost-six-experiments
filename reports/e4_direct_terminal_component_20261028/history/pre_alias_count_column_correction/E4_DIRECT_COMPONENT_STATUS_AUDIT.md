# E4 direct-component status snapshot

Observed 2026-10-27T21:30:31.116358+00:00 UTC (2026-10-28T03:00:31.116358+05:30 Asia/Kolkata).

The frozen plan contains 765 direct keys: 17 methods x 15 conditions x 3 repetitions. The registry snapshot contains the same exact key set.

- Validated terminal: 720
- Waiting for dependency: 45
- Other nonterminal states: 0

| Registry terminal outcome | Count |
|---|---:|
| alias: successful | 21 |
| alias: unavailable_dependency | 3 |
| eval: scientific_failure | 71 |
| eval: successful | 625 |

The component is NOT terminal. All current nonterminal cells are ExtraTrees direct evaluations (15 conditions x 3 repetitions), waiting on their matching ExtraTrees fit dependencies. They remain pending; they are not scientific failures.

The 24 planned control keys materialized as registry aliases: 21 have successful source outcomes and 3 are unavailable because the source E3 fit was unavailable. The alias source_key is retained in the cell CSV.

## Existing reports and limits

The existing E4 completed-block report is an older E4-wide snapshot. Existing kernel and KNN reports cover only their named methods. None is a current all-method terminal report. This status audit intentionally does not calculate predictive metrics, paired differences, conformal coverage/set size, or timing; those require validated saved evaluation outputs and a terminal component snapshot.

No model, pipeline, test features, or prediction arrays were loaded. The registry snapshot was produced through SQLite's read-only online backup and passes PRAGMA integrity_check.

Plan SHA-256: 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb  
Freeze SHA-256: {freeze_sha}  
Registry snapshot SHA-256: {report['registry_snapshot_sha256']}  
Status CSV SHA-256: {report['outputs']['cell_csv']['sha256']}  
Method table SHA-256: {report['outputs']['method_csv']['sha256']}  
Audit JSON SHA-256: {reportsha}  
