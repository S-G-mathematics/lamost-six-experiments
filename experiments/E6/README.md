# E6 - member-posterior ensembles

E6 has 21 terminal rows: six primary ensembles and 15 member references. The latter include 12 successful aliases to E3 direct member results and 3 unavailable KDE aliases. Aliases are not primary ensemble evaluations.

The six primary cases have zero successful test evaluations: three equal-weight cases ended in test-prediction failures and three learned-weight cases are unavailable through the shared posterior dependency. No primary ensemble BA, coverage or set-size metric exists.

Three learned simplex vectors and candidate ledgers are saved as tuning-only evidence. Candidate counts were 1,606, 1,558 and 1,606; weights were frozen before calibration and test. Across n=3 vectors, mean weight (sample SD): GMM 0.7743 (0.0449), copula 0.0416 (0.0167), ARF 0.0097 (0.0030), KDE 0.1074 (0.0561), Chow-Liu 0.0670 (0.0890). This is tuning-vector variation, not test benefit. See [vectors](../../reports/descriptive_summaries_20261031/E6_learned_weights_tuning_only.csv), [summary](../../reports/descriptive_summaries_20261031/E6_weight_stability_tuning_only.csv) and [candidate ledger](../../reports/E6_candidate_ledger.csv).

E6-v2 amended its execution rule after the first E3 KDE timeout. The six zero-attempt v1 gate outcomes remain superseded history; v2 was not the original frozen executable semantics. Global calibration replay and final artifact validation remain pending.
