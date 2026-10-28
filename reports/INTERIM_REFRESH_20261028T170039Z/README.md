# LAMOST six-experiment interim report refresh

Registry snapshot: 2026-10-28T17:00:39.712874+00:00 (original source registry SHA-256 886a59020d3282fa171bd2b21da7f768cf5865b85625671fd383f04bf1af0e75). This is a staged descriptive refresh, not a final scientific report or a completed project archive. It does not include fitted models or FITS files. No fitting, model loading, test inference, or E1/E2 reruns were performed.

The report covers all 2,823 planned E3-E6 scientific cases in the captured registry. Evaluated means a validated successful evaluation; other states remain distinct.

| Outcome state | Cases |
|---|---:|
| scientific_failure | 127 |
| successful | 2366 |
| unavailable_dependency | 89 |
| waiting_for_dependency | 241 |
| Planned total | 2823 |
| Evaluated successful cases | 2366 |

All 18 refreshed E3-E6 figures exist and are stored under figures/. They are generated from the same captured registry and validated evaluation artifacts; paired comparisons retain actual matched repetitions and missing cases remain represented in tables and heatmaps. Three unchanged, previously validated E1/E2 figures are included alongside them. Tables are under tables/ and include planned-case availability, repetition/per-class metrics, matched E4 controls, E5 corruption contrasts, costs, and evidence/provenance summaries.

Frozen E1 is preserved separately at 765/765 (674 successful, 81 failed, 10 unsupported). Its stopped recovery supplement remains separate (24 successful retries, 10 failed, 2 user-stopped, 55 not attempted). E2 remains 108/150 primary evaluations plus 120/120 classical references; its reconstruction provenance and limitations remain in the existing E2 report.

This snapshot is not final: cases may be waiting, E6/native calibration and independent q-replay requirements are not certified complete, and the all-project finalizer has not validated a final report/archive. No bootstrap or significance claims are added. Historical model/prediction omissions and hardware-dependent timing limitations remain applicable.

The report result is a portable derived view whose figure paths are relative names; the original generated report result is preserved in the staging runtime. The staging registry remaps attempt evidence paths into its metadata mirror; task keys and outcomes are preserved. Original registry SHA-256: 886a59020d3282fa171bd2b21da7f768cf5865b85625671fd383f04bf1af0e75; staged registry SHA-256: ddab55efb84a88f59df72b9eba26bb6a3b70d7409e9ae2eeda3536aeeba27dbc.
