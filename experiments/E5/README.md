# E5 - fitting-data corruption

E5 has 960 planned cases: 730 successful references (88 aliases), 50 failures, 79 unavailable and 101 user-stopped. Feature noise, label noise and missingness use planned rates 5%, 10%, 20%; learner, route and generator remain separate. Completed repetitions remain alongside selected single evaluations, so n varies.

The 864-row [clean/corrupted ledger](../../reports/E5_clean_corrupted_paired_metrics.csv) has paired availability by mechanism/rate (96 planned contrast rows per rate, not 96 unique evaluation cases): feature noise 69/96, 72/96, 76/96; label noise 76/96, 76/96, 75/96; missingness 66/96 at each rate. See the [condition-preserving summary](../../reports/descriptive_summaries_20261031/E5_clean_corrupted_pair_summaries.csv). Direct CART at 5% feature noise has corrupted-minus-clean BA -0.00749 (SD 0.00067; n=3), an exact stratum only.

The [realization table](../../reports/E5_corruption_realization_summary.csv), [source-class rates](../../reports/E5_label_noise_source_class_rates.csv) and [label transitions](../../reports/label_transition_counts.csv) retain affected-row evidence. Source-class rates use original fitting counts as denominators. No unavailable score is imputed and no universal robustness ranking is claimed.
