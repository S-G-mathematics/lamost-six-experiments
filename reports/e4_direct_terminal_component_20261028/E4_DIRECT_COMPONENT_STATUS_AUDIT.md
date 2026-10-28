# E4 direct-component status snapshot

Observed 2026-10-27T21:30:31.116358+00:00 UTC (2026-10-28T03:00:31.116358+05:30 Asia/Kolkata).

The frozen plan contains 765 direct keys: 17 methods x 15 conditions x 3 repetitions. The read-only registry backup has the exact same key set.

- Validated terminal: 720
- Waiting for dependency: 45
- Other nonterminal states: 0

| Registry terminal outcome | Count |
|---|---:|
| eval: successful | 625 |
| eval: scientific_failure | 71 |
| alias: successful | 21 |
| alias: unavailable_dependency | 3 |

The component is NOT terminal. All 45 nonterminal cells are ExtraTrees direct evaluations (15 conditions x 3 repetitions), waiting on their matching ExtraTrees fit dependencies. They remain pending and are not scientific failures.

The 24 planned control keys materialized as registry aliases: 21 have successful source outcomes and 3 are unavailable because their source E3 fit was unavailable. Alias results are separated from scientific eval rows in the method table.

## Method status

| Method | Planned | Terminal | Successful eval | Successful alias | Scientific failure | Unavailable dependency | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|
| arf | 45 | 45 | 40 | 3 | 2 | 0 | 0 |
| cart | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| chow_liu | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| copula | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| extra_trees | 45 | 0 | 0 | 0 | 0 | 0 | 45 |
| gaussian_nb | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| gmm | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| hist_gb | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| kde | 45 | 45 | 0 | 0 | 42 | 3 | 0 |
| knn | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| lda | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| linear_svm | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| logistic | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| qda | 45 | 45 | 45 | 0 | 0 | 0 | 0 |
| random_forest | 45 | 45 | 42 | 3 | 0 | 0 | 0 |
| rbf_svm | 45 | 45 | 18 | 0 | 27 | 0 | 0 |
| shared_diagonal | 45 | 45 | 45 | 0 | 0 | 0 | 0 |

Existing E4 completed-block reporting is an older E4-wide snapshot; the kernel and KNN reports cover only their named methods. None is a current all-method terminal report.

This status audit does not recompute predictive metrics, target recalls, paired differences, conformal coverage/set size, or timing. Those belong in the full descriptive report after all direct cells are terminal. No model, pipeline, test feature, or prediction array was loaded.

The registry snapshot was made via SQLite read-only online backup and passed PRAGMA integrity_check.

Plan SHA-256: 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb  
Freeze SHA-256: 9994b586264f7b36c6355e051fac5ad2f17a3e4738dc2d4f7e036b9f08e96a00  
Registry snapshot SHA-256: 85cf44861851cf6e4b333b2d0d6abe415c5ef2679ac4b291a1e871857f181ce5  
Status CSV SHA-256: 1ca3160ca6038e40a8b242d4acd197080eecde5ab7b6f862465e0d54c7f4bfcb  
Method CSV SHA-256: 823b32ae56a292d3cfa61f6e66a55b41d3779a29eabf06a45417a695fc4ed6df  
Audit JSON SHA-256: ef7e068d0b318bc3b13db091cc7f5474cb2263ca76f37a53cd532c6e35d3da28  
Audit script SHA-256: 6408cc3641f92f7edd3c518488834e5f872f3c11dc3522a87ece94345ecddbd1  
Superseded method-summary SHA-256: b8d752f7ed627a6f8786ee67e1c903012525ec8a8b8c531a31e3702238c32746
