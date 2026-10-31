# E3 - direct, synthetic-only and real-only routes

E3 has 69 terminal cases: 64 successes, 3 scientific failures and 2 unavailable dependencies. Direct Bayes succeeded 3/3 for GMM, copula, ARF and Chow-Liu; KDE direct timed out in all 3. Successful direct Bayes mean BA / marginal coverage / set size: GMM 0.80555 / 0.89960 / 1.4870 (n=3); copula 0.57919 / 0.89758 / 2.3711 (n=3); ARF 0.64609 / 0.89693 / 2.2784 (n=3); Chow-Liu 0.61182 / 0.89871 / 2.5387 (n=3). KDE has no score.

For copula/random-forest, synthetic-minus-real BA is -0.17273 (sample SD 0.01258; n=3); see the full [condition summary](../../reports/descriptive_summaries_20261031/E3_dedicated_pair_summaries.csv). Other generator/learner strata differ.

The dedicated [135-row E3 pair ledger](../../reports/E3_CURRENT_MATCHED_PAIRS_20261030.csv) has 114 paired rows. The generic matched aggregate omits one valid rep-2 GMM/random-forest direct-minus-real pair (BA delta +0.0443761964) because its synthetic counterpart is unavailable. The dedicated ledger includes this pair and is the complete 114-pair E3 comparison set. See [reviewed report](../../reports/E3_FINAL_DESCRIPTIVE_REPORT.md) and [cell ledger](../../reports/E3_FINAL_CELL_LEDGER_69.csv).
