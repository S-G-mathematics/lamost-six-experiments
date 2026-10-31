# Reproducible descriptive summaries

Run python3 analysis/descriptive_summary.py at repository root. The script reads published CSVs only, not models, arrays, datasets, databases or operational receipts.

All groupings retain experiment-specific design axes. Paired-difference sign is arithmetic: higher_a means A minus B is positive, not universally preferable. Sample SD is blank for n<2. E3's dedicated pair ledger has 114 paired rows; the generic 755-row matched aggregate has 113 E3 rows and 642 E5 rows. The E3 difference is a legacy omission corrected by the dedicated ledger. The generic file has no E4 contrast rows. E4 contrasts require its dedicated table.

- successful_metric_distributions.csv: BA, coverage and set size by full condition.
- matched_pair_summaries.csv: exact-key summary of generic matched pairs.
- E3_dedicated_pair_summaries.csv and E3_dedicated_pair_ledger_status.csv: dedicated E3 pair ledger.
- E4_treatment_control_pair_summaries.csv and E4_pair_availability.csv: E4 condition effects and missingness.
- E5_clean_corrupted_pair_summaries.csv and E5_pair_availability.csv: E5 condition effects and missingness.
- per_class_metric_distributions.csv: class recall, coverage and set size by exact condition.
- E6_learned_weights_tuning_only.csv and E6_weight_stability_tuning_only.csv: saved tuning-only vectors; zero successful primary ensemble tests.
- MANIFEST.csv: source/output byte counts and SHA-256; the manifest does not hash itself.
