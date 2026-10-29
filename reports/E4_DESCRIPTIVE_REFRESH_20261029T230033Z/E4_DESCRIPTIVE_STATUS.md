# E4 descriptive results snapshot

**Interim E4 snapshot; not a final six-experiment report.** This refresh uses the current read-only SQLite task snapshot and saved validated evaluation JSONs only. No models were fitted or loaded; no test-outcome arrays were opened.

- Observation time: 2026-10-29T23:00:33.332757+00:00 (2026-10-30T04:30:33.332757+05:30, Asia/Kolkata).
- Immutable E4 planned ledger: 1,773 scientific-case rows.
- Validated successful evaluations with usable metrics: 1,631.
- Recorded scientific failures: 71; unavailable dependencies: 3; user-stopped cases: 67; pending: 1.
- These states account for all planned E4 rows; user-stopped and unavailable cases are not scientific failures.

## Scope and interpretation

The original plan SHA-256 is 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb. The user-authorized prospective repetition-scope amendment is applied and recorded at runtime_20261025/reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json (receipt SHA-256 855b45831958b9c2bc65534ad2bf5ea6eece569cb83336ed8935d210e6ccd536; amendment SHA-256 e11d77d793539517fccb4bfe6260d74fb4c8ba92960450706463d4e7cd2f57fb). It preserves prior terminal outcomes and marks unselected repetitions user-stopped; it does not replace earlier results or alter the original planned-case ledger. Private operational fields are not reproduced.

Metrics use successful rows with validated saved evaluation JSONs. The original three-repetition denominator remains in matched tables and figures. Means and sample SDs are descriptive and condition-specific. For n=1, sample SD is blank. There are no bootstrap intervals, significance tests, or cross-condition rankings.

## Outcome counts

| State | Cases |
|---|---:|
| Successful | 1631 |
| Scientific failure | 71 |
| Unavailable dependency | 3 |
| User-stopped | 67 |
| Pending | 1 |
| **Total planned E4 cases** | **1773** |

## Tables

E4_CURRENT_CELL_LEDGER.csv retains all 1,773 planned cases and their current status/outcome. E4_REPETITION_STATUS_COUNTS.csv shows repetition-specific accounting. E4_PER_REPETITION_METRICS.csv and E4_PER_CLASS_METRICS.csv contain successful-only overall and seven-class metrics. E4_CONDITION_DESCRIPTIVES.csv groups by exact method, route, condition, target, severity, and treatment; no unlike strata are pooled.

E4_CONTROL_TREATMENT_PAIRED.csv preserves case/control status and reasons for unmatched pairs. E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv reports matched n/3, paired means, and sample SD where defined by comparison, method, target, severity, and treatment. It includes direct altered-vs-unchanged and treatment-vs-untreated/unchanged comparisons, including target-class recall and coverage differences where available.

## Figures

- E4_restoration_effect_heatmaps.png
- E4_direct_method_effect_heatmaps.png

The restoration heatmap displays treatment-minus-untreated effects by target and learner. The direct-method heatmap displays altered-direct-minus-unchanged effects. Both retain planned conditions and show matched repetitions out of three; grey means no matched metric, not a zero effect.

## Limits

This is an E4 descriptive update only. Full project calibration-quantile replay and final artifact validation remain pending; E5 also has pending cases. The overall project is incomplete.
