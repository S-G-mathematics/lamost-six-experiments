# E5 Random Forest feature-noise 10% cases, rep 1

Registry snapshot: 2026-10-30T00:01:08.262991+00:00 (report generated 2026-10-30T00:01:20.055066+00:00). E5 has 960 planned scientific cases; current recorded outcomes are:
- successful: 704
- scientific_failure: 50
- unavailable_dependency: 78
- user_stopped: 101
- waiting_for_dependency: 27

The two validated cases below are paired only to the clean baseline from the same repetition, method, route, and generator. These are n=1 of 3 descriptive pairs; sample SD is undefined. They do not establish a general robustness effect. No bootstrap or significance testing was performed.

| Synthetic generator | Metric | Corrupted | Matching clean | Corrupted minus clean |
|---|---|---:|---:|---:|
| chow_liu | balanced accuracy | 0.596658 | 0.626125 | -0.029467 |
| chow_liu | coverage | 0.893508 | 0.896382 | -0.002874 |
| chow_liu | set size | 2.304134 | 2.216446 | +0.087688 |
| copula | balanced accuracy | 0.568656 | 0.595396 | -0.026740 |
| copula | coverage | 0.893296 | 0.891792 | +0.001504 |
| copula | set size | 2.357622 | 2.198152 | +0.159470 |

Per-class recall, coverage, and set-size differences and validated artifact identities are in the accompanying CSV/JSON files. The archived NPZ files contain saved test outcomes only; no fitted models are included.
