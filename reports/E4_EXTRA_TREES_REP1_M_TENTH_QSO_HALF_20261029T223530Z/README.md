# E4 extra-trees rep-1 result update

This dated increment records two validated rep-1 direct Extra Trees evaluations and selected-configuration provenance. The same-repetition direct control is included for transparent pairing. The full planned E4 matrix remains incomplete.

All comparisons are descriptive at matched repetition n=1 of 3; no inferential test or confidence interval is reported. Coverage is computed on the held-out test cohort using the saved calibration procedure.

| Condition | Balanced accuracy | Coverage | Mean set size | Difference from control (BA, coverage, set size) |
|---|---:|---:|---:|---|
| control | 0.769361 | 0.894940 | 1.529260 | reference control |
| M_tenth | 0.732477 | 0.896666 | 1.622788 | balanced_accuracy -0.036884; coverage +0.001726; set_size +0.093528 |
| QSO_half | 0.759014 | 0.891726 | 1.535884 | balanced_accuracy -0.010347; coverage -0.003214; set_size +0.006624 |

The paired-control table reports n=1 per condition; sample standard deviation is undefined. Individual per-class recall, coverage, and set-size values are in per_class_metrics.csv. This is not a full repetition-level estimate and should not be generalized across methods, targets, or severity levels.

No fitted pipeline, raw training cohort, or new inference is included. The NPZ release members are the saved validated test-outcome arrays. Exact artifact and validation hashes are in manifest.json.
