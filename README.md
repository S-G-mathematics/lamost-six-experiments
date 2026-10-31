# LAMOST DR10 six-experiment study

An experiment-wise record of seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

## Current saved outcome snapshot

Snapshot: 2026-10-31T01:05:34.402480Z. All 6,270 registry task rows are terminal. The original E3-E6 denominator remains 2,823 scientific cases: 2,438 successful evaluation references, 127 recorded scientific failures, 90 unavailable dependencies and 168 repetitions prospectively user-stopped under the approved scope amendment. The successful references include 12 E6 member aliases; none of the six primary E6 ensembles has a successful test evaluation.

| Experiment or set | Planned | Successful | Recorded failures | Unsupported | Unavailable | User-stopped | Not attempted | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 | 0 |
| E1 recovery supplement | 91 | 24 | 10 | 0 | 0 | 2 | 55 | 0 |
| E2 primary | 150 | 108 | 0 | 0 | 42 | 0 | 0 | 0 |
| E2 separate references | 120 | 120 | 0 | 0 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 | 0 | 0 |
| E4 | 1,773 | 1,632 (21 aliases) | 71 | 0 | 3 | 67 | 0 | 0 |
| E5 | 960 | 730 (88 aliases) | 50 | 0 | 79 | 101 | 0 | 0 |
| E6 | 21 | 12 member aliases; 0 primary | 3 | 0 | 6 | 0 | 0 | 0 |

E1 recovery is a separate stopped-early supplement; 55 rows were not attempted and are not pending. The E4/E5 amendment selected one further evaluation for 45 cases and stopped 168 other repetitions. Completed repetitions remain. The original three-repetition grid was not completed.

## Navigate

- [Results guide](docs/RESULTS_GUIDE.md): design, findings, denominators, paired comparisons and limits.
- [E1](experiments/E1/README.md) / [E2](experiments/E2/README.md) / [E3](experiments/E3/README.md) / [E4](experiments/E4/README.md) / [E5](experiments/E5/README.md) / [E6](experiments/E6/README.md)
- [Current case ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261031/PLANNED_CASE_OUTCOMES_2823.csv), [scientific log coverage](reports/SCIENTIFIC_LOG_COVERAGE_20261031.md), [success evaluation SHA crosswalk](reports/E3_E6_SUCCESS_EVALUATION_SHA_CROSSWALK_20261031.csv), and [evaluation-to-array crosswalk](reports/CURRENT_SUCCESS_ARRAY_CROSSWALK_20261031/README.md).
- [Aggregate tables and 18 figures](reports/AGGREGATE_SNAPSHOT_20261031T010534Z/README.md).
- [Reproducible summaries](reports/descriptive_summaries_20261031/README.md) and [analysis script](analysis/descriptive_summary.py).
- [Data availability](docs/DATA_AVAILABILITY.md), [result arrays](docs/RESULT_ARRAYS.md), and [documentation index](docs/README.md).

## Interpretation and validation

All comparisons are descriptive and preserve named experiment, method, route, target, severity and repetition strata. No bootstrap intervals or significance tests are reported. Non-successful cases have no imputed metrics; sample SD is undefined for n=1.

E1/E2 outcomes were observed before E3-E6, so the fixed test cohort is not prospective untouched-test validation. Global calibration-quantile replay and final artifact audit remain pending. Engineering-test passes and terminal registry states do not substitute for those checks. This is an interim scientific record, not a claim that every original planned experiment completed or that final validation passed.

## Reproduction and provenance

The public tree contains code, configuration, source-bound reports, result metadata and available prediction/evaluation arrays. Fitted models and private operational receipts are excluded. [Data availability](docs/DATA_AVAILABILITY.md) documents frozen baseline/role identity and public-clone reproduction limits. The EC2 engineering qualification is evidence for that EC2 environment, not a claim that the public clone can reproduce the full test closure.
