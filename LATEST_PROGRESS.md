# LAMOST six-experiment project: current progress

Observed 2026-10-31T01:34:20Z UTC from one read-only SQLite transaction. Interim snapshot, not a final report.

- Registry: 6,270/6,270 task rows are validated terminal.
- E1 frozen: 674 successful, 81 recorded failures (55 resource plus 26 supervisor-terminal manifests still started), 10 unsupported / 765. Separate recovery: 24 successful, 10 failed, 2 user-stopped, 55 not attempted.
- E2: 108/150 primary evaluations; 120/120 separate references; 31 reconstruction accuracy differences, 210 low-precision flags and 4 complete correlation strata.
- E3: 64 successful, 3 failures, 2 unavailable / 69.
- E4: 1,632 successful including 21 aliases, 71 failures, 3 unavailable, 67 stopped / 1,773.
- E5: 730 successful including 88 aliases, 50 failures, 79 unavailable, 101 stopped / 960.
- E6: 12 successful member aliases, 3 failures, 6 unavailable / 21; zero successful primary ensemble test results.
- E3-E6: 2,438 successful references, 127 failures, 90 unavailable, 168 user-stopped, zero pending / 2,823.

See the [current case ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261031/PLANNED_CASE_OUTCOMES_2823.csv), [success evaluation SHA crosswalk](reports/E3_E6_SUCCESS_EVALUATION_SHA_CROSSWALK_20261031.csv), and [scientific log coverage audit](reports/SCIENTIFIC_LOG_COVERAGE_20261031.md). Current 863/863 portable qualification is engineering/fixture-only. Final artifact review and global calibration/quantile replay remain pending. Historical E1 fitted models are omitted; 80/674 successful frozen E1 prediction arrays are available.
