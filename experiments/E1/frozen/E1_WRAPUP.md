# Experiment 1 wrap-up

Cutoff: 2026-10-24T08:02:32.571618+00:00 UTC. E1 recovery stopped early at the user's request before Experiment 2. No further E1 runs are authorized.

Frozen E1: 765/765 terminal; 674 successful, 81 failed, 10 unsupported. The 81 failures comprise 55 resource failures and 26 supervisor terminal failures whose manifests remained started. The frozen report is descriptive; bootstrap was dropped at the user's request.

Separate recovery at cutoff: 24 successful, 10 failed, 2 user-stopped in progress, 55 not attempted after the stop decision. These recovery outcomes used 600-second trials and 10 GiB headroom versus frozen E1's 180 seconds and 6 GiB, and must not be substituted into frozen E1.

The ARF min-leaf variant was staged but not run after the stop. It changes the method and would be a future sensitivity analysis, not a repair of the original unsupported ARF cells. The saved-pipeline finalizer's exact reproduction gate was not run; no finalizer outcomes are included.

Historical fitted models and test prediction arrays omitted from the compact transfer remain unavailable for those old cells. The seven documented auxiliary tuning-history discrepancies across 10K rep3 GMM, 30K rep2 CART and 30K rep3 linear SVM remain. Timing comparisons across hosts are hardware dependent. Means in the method/budget CSV are conditional on actual successful repetition counts.

Files: E1_frozen_cells_765.csv, E1_method_budget_summary_153.csv, E1_recovery_cutoff_91.csv, E1_learning_curves_all_budgets.html. The full validated report and raw artifacts are in the project directory included with the archive. Experiments 3-6 remain unauthorized.
