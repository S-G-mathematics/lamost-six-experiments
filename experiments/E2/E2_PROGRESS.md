# E2 progress and evidence limits

As of 2026-10-24T08:13:55.439405+00:00, E2 has 19 fidelity-complete primary selected fits and 24 separately labeled classical reference fits. All 301 class reports were valid. These are reused frozen E1 selected models: no E1 refit/re-tune and no recovery models.

The primary grid has 150 planned budget/repetition/method cells. Artifact audit: 19 ready, 89 otherwise successful E1 cells missing historical selected pipelines, 40 E1 failures without a pipeline, and 2 E1 failed cells with a staged pipeline that lack valid frozen classification outcomes. Missing pipelines are artifact gaps, not model failures.

Fidelity uses the six native predictors, SDMetrics 0.32.0 Quality Reports per class, and an equal average of all seven class scores. Real reference rows come only from frozen E1 calibration membership after model selection; each class has min(2000, available rows), with the same deterministic real IDs across methods at a budget/repetition. Generated samples use the frozen selected model and its original preprocessing. No test rows entered the fidelity reference frame. Column-shape and column-pair details and samples are saved per class.

No budget/repetition has all five primary methods available, so all 30 protocol five-family Spearman values are unavailable. Six strata have three available primary methods and an explicitly descriptive available-only rho. Do not pool budgets or claim a precise universal relationship. The four classical generators are a separate sensitivity set. Bootstrap was dropped at user request; TSTR belongs to E3 and was not run. Experiments 3-6 remain unauthorized.
