# LAMOST project descriptive report

Registry observation: 2026-10-27T21:10:01.322916+00:00

## New runtime coverage

Planned scientific cases in this registry: 2823; evaluated outcomes recorded: 2249.

| State | Count |
|---|---:|
| successful | 2249 |
| scientific_failure | 127 |
| unavailable_dependency | 41 |
| waiting_for_dependency | 406 |

Evidence tables include dataset/role inventory, exact E4 class histograms, E5 corruption realizations and label transitions, model-selection trials/provenance, calibration/test fallback completion flags, and E6 frozen weights plus the complete saved candidate ledger. Empty candidate and transition files retain their headers when no such artifacts exist. Synthetic example counts, restored counts and untouched real role counts remain distinct.

Results are descriptive and repetition matched. Means and sample standard deviations appear in the coverage table; no bootstrap intervals or significance claims are produced. A non-success is not treated as an evaluated score.

## E4 and E5 descriptive coverage

E4 currently has 1521 evaluated scientific cases in this registry snapshot; 2337/2730 planned control contrasts have both evaluations available. E4_CONTROL_TREATMENT_PAIRED.csv keeps direct altered-versus-unchanged and treatment-versus-untreated/unchanged contrasts separate by repetition, target, severity, and method; E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv gives condition-specific paired n, mean, and sample SD without pooling target/severity/method strata. Main effect heatmaps are separate from overview panels. See the outcome coverage and resource ledgers for failures and unavailable dependencies.
E5 currently has 652 evaluated scientific cases; 3969/6048 planned per-class corruption-versus-clean rows have both class metrics available. E5_clean_corrupted_paired_metrics_summary.csv and E5_per_class_paired_summary.csv provide condition-specific paired n, means, and sample SD for overall and class-level outcomes; their underlying row ledgers preserve method, route, generator, mechanism, rate, class, and repetition, and unmatched cases carry status/reason with blank differences. Main paired-delta heatmaps show all planned method/route/generator/rate cells, with unavailable cells grey. Contrasts are conditional on paired successful evaluations and do not support universal robustness claims.

## Frozen E1 and E2 integration

Frozen E1 validated report: /home/ubuntu/lamost_e1_migration_20261023/project/benchmark/results/e1_report_validated_no_bootstrap.json
765 planned cells; 674 successful, 81 failed (resource/supervisor-terminal categories), and 10 unsupported/model-support failures. The user-facing frozen ledger reports 81 failures plus 10 unsupported; source report evidence remains linked.

Stopped E1 recovery supplement: 2026-10-24T08:02:32.571618+00:00; recorded counts {'failed': 10, 'not_attempted_user_stopped': 55, 'successful_test_evaluation': 24, 'user_stopped': 2}; explicitly stopped early at user request. Source: /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json.


## Terminal worker RSS cutoff and dependent availability

E3 repetition 2 synthetic random_forest / gmm reached the recorded worker process-tree RSS limit (10737418240 bytes) and terminated at 2026-10-25T10:05:52.106714+00:00 with supervisor-measured peak 10759069696 bytes. The terminal event is tied to attempt cc289206965c476483ee5c2bf5e7894b and the matching checkpoint phase. Trial 8 was assigned and has a last-saved running state; its last observed elapsed time is 443.21060972096166 s and observed phase RSS 10159880 KiB. No trial score or completed duration is imputed. Completed trial records: 8 ({"duplicate_cached":2,"scientific_failure":2,"success":4}). Nominal tuning budget was 10; started 9 slots, completed 8 tuning records, and nominal slots not attempted: 9. Pipeline present: False. 1 dependent E3 and 10 dependent E5 evaluation cells are unavailable dependencies where applicable. Raw trial/checkpoint state was not modified. No OS-level OOM is inferred.
E3 repetition 2 synthetic random_forest / kde reached the recorded worker process-tree RSS limit (10737418240 bytes) and terminated at 2026-10-25T16:44:38.269668+00:00 with supervisor-measured peak 10761572352 bytes. The terminal event is tied to attempt 38f18b432a454e9b8dd1058ff1c708a0 and the matching checkpoint phase. Trial 5 was assigned and has a last-saved running state; its last observed elapsed time is 408.50018761097454 s and observed phase RSS 10203680 KiB. No trial score or completed duration is imputed. Completed trial records: 5 ({"scientific_failure":3,"success":2}). Nominal tuning budget was 10; started 6 slots, completed 5 tuning records, and nominal slots not attempted: 6, 7, 8, 9. Pipeline present: False. 1 dependent E3 and 10 dependent E5 evaluation cells are unavailable dependencies where applicable. Raw trial/checkpoint state was not modified. No OS-level OOM is inferred.
E2 report source: /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/E2_CURRENT_REPORT.md.
E2 primary: 108/150 evaluated; 42 unavailable. Separate classical references: 120/120 available. Complete five-family correlation strata: 4/30. Artifact audit: 228 evaluated cells, 1596 class reports, [] integrity errors; 210 low-precision class flags. Reconstruction fidelity gate: 154 exact and 31 with recorded accuracy difference; maximum absolute difference 3.1739351391335546e-05.
E2 final family ledger: 270 rows in /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/E2_all_generators_270.csv; primary coverage remains transparently incomplete.

## Figures

- E3_balanced_accuracy_route_comparison.png
- E3_coverage_route_comparison.png
- E3_set_size_route_comparison.png
- E4_balanced_accuracy_target_treatment.png
- E4_coverage_target_treatment.png
- E4_set_size_target_treatment.png
- E4_target_class_recall.png
- E5_balanced_accuracy_corruption_sweeps.png
- E5_coverage_corruption_sweeps.png
- E5_set_size_corruption_sweeps.png
- E6_balanced_accuracy_member_ensemble.png
- E6_coverage_member_ensemble.png
- E6_set_size_member_ensemble.png
- E4_restoration_effect_heatmaps.png
- E4_direct_method_effect_heatmaps.png
- E5_feature_noise_paired_BA_heatmaps.png
- E5_missingness_paired_BA_heatmaps.png
- E5_label_noise_paired_BA_heatmaps.png
- Prior validated figure: `project/learning_curves_through_300000.png`
- Prior validated figure: `e1_wrapup_20261024/E1_learning_curves_all_budgets.html`
- Prior validated figure: `e2_20261024/E2_combined_fidelity_vs_accuracy.html`

## Resource and timing results

Phase-level wall-clock and process-tree RSS observations are in `costs.csv`; grouped totals, means, sample SDs and actual successful phase counts are in `cost_summary.csv`. Fit search trials, final model fitting, generator fitting, 400k-row generation, downstream training, calibration and test inference are separate stages. E4 cohort construction and E5 corruption construction are reported as observed task wall time because their implementation executes synchronously and exposes no isolated phase RSS receipt. Reused pipelines show zero new model-training time and retain any reuse/load validation overhead separately; logical fit dependencies and provenance are recorded by key. Timings depend on this EC2 hardware, concurrent system load, process startup, I/O and library versions; observed RSS is a process-tree peak, not a portable algorithmic cost. Missing timings stay blank rather than being imputed as zero.

## Interpretation and limitations

Comparisons use only matching successful repetitions. Survivorship and dependency unavailability can limit interpretation. E1 and E2 outcomes were already observed before the later experiments; later evaluations are not prospective untouched-test evaluations. Frozen E1 outcomes remain separate from E1 recovery and experiment-specific models. Auxiliary tuning-history and omitted historical model/prediction caveats remain in the source E1/E2 reports.
