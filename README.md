# LAMOST DR10: six-experiment research project

Code, saved results, figures and provenance for seven-class classification using Pan-STARRS g, r, i, z, y and Gaia G photometry.

## Current scientific snapshot

The current saved aggregate report is dated 2026-10-31T01:05:34.402480Z. All 6,270 registry task rows are terminal. The original 2,823 E3-E6 case denominator remains intact: 2,438 successful references, 127 recorded failures, 90 unavailable dependencies, 168 prospectively user-stopped repetitions, and zero pending. The 2,438 references include 12 E6 member-reference aliases; E6 has zero successful primary ensemble test evaluations.

| Experiment or set | Planned | Successful | Recorded failures | Unsupported | Unavailable | User-stopped | Not attempted | Pending |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | 0 | 0 |
| E1 recovery supplement (separate) | 91 | 24 | 10 | 0 | 0 | 2 | 55 | 0 |
| E2 primary | 150 | 108 | 0 | 0 | 42 | 0 | 0 | 0 |
| E2 separate references | 120 | 120 | 0 | 0 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 | 0 | 0 |
| E4 | 1,773 | 1,632 (21 aliases) | 71 | 0 | 3 | 67 | 0 | 0 |
| E5 | 960 | 730 (88 aliases) | 50 | 0 | 79 | 101 | 0 | 0 |
| E6 | 21 | 12 member aliases; 0 primary | 3 | 0 | 6 | 0 | 0 | 0 |

The E1 recovery supplement remains separate from the frozen E1 ledger; its 55 not-attempted cases are not pending. E1/E2 outcomes were observed before the later project plan; no bootstrap or refit is claimed. The E4/E5 amendment retained 45 cases and stopped 168 other repetitions; the original full three-repetition grid is not complete. Comparisons are descriptive and conditional on successful evaluations.

## Experiment reports and tables

- [E1 frozen benchmark](experiments/E1/README.md): 674/765 successes, 81 recorded failures and 10 unsupported cells. Figure: [budget summary](reports/frozen_e1_e2_figures/E1_frozen_all_budget_summary.png). Historical fitted models remain absent. Prediction arrays are available for 80/674 frozen E1 successes; the separate recovery supplement has 24/24 arrays.
- [E1 recovery supplement](reports/COMPLETED_E1_E2_E3_E6_SYNTHESIS_20261027.md): separate early-stop outcomes and limitations.
- [E2 generator fidelity](experiments/E2/README.md): 108/150 primary evaluations and 120/120 separate references; 31 reconstruction accuracy differences, 210 low-precision flags and four complete correlation strata. See the [availability and strata figure](reports/frozen_e1_e2_figures/E2_primary_availability_and_strata.png).
- [E3 direct and generator routes](experiments/E3/README.md).
- [E4 imbalance and target restoration](experiments/E4/README.md).
- [E5 fitting-data corruption](experiments/E5/README.md).
- [E6 posterior ensembles](experiments/E6/README.md): twelve member-reference aliases, no successful primary ensemble evaluation.
- [Current case ledger](reports/CURRENT_CASE_OUTCOME_LEDGER_20261031/PLANNED_CASE_OUTCOMES_2823.csv), [all-success evaluation SHA crosswalk](reports/E3_E6_SUCCESS_EVALUATION_SHA_CROSSWALK_20261031.csv), [evaluation-to-array release crosswalk](reports/CURRENT_SUCCESS_ARRAY_CROSSWALK_20261031/README.md), and [scientific log coverage audit](reports/SCIENTIFIC_LOG_COVERAGE_20261031.md).
- [Current aggregate tables and 18 E3-E6 figures](reports/AGGREGATE_SNAPSHOT_20261031T010534Z/README.md). The snapshot includes per-repetition and per-class metrics, case and failure ledgers, matched-pair summaries, evidence tables and phase costs. It is descriptive, not a calibration or final artifact validation.

## Data, source qualification and reproduction

- [Data availability, baseline/role hashes and reproduction requirements](docs/DATA_AVAILABILITY.md).
- [Result-array release inventory and verification steps](docs/RESULT_ARRAYS.md).
- [E1 protocol and dependency specification](code/E1_benchmark/Experiment_1_Setup_and_Readiness.txt); [frozen manifests/configuration](provenance/manifests/); [baseline identity manifest](provenance/baseline_identity/manifest.json).
- The 863/863 portable engineering suite passed on EC2. Its source closure mirrors 190 of 212 source inputs; 22 operational/test log bodies remain excluded. This is not a claim that a public clone can reproduce all 863 tests or that scientific results are complete. See [pass receipt](provenance/qualification_863/PORTABLE_TEST_PASS.json) and [source closure](provenance/qualification_863/SOURCE_TEST_PUBLIC_PROOF_CLOSURE.json).
- [Final execution/resource/delivery note](reports/FINAL_EXECUTION_RESOURCE_DELIVERY_NOTES_20261031.md) records completed terminal execution and delivery boundaries.

The global calibration/quantile replay and full artifact audit are still in progress. No final project validation or full final archive is claimed here.

The prior landing-page narrative and older report snapshot remain in Git history at [commit 540291f9](https://github.com/S-G-mathematics/lamost-six-experiments/blob/540291f9d686400092ae226bea3cc0f897a2947c/README.md). Historical component reports and source snapshots remain in their dated paths.
