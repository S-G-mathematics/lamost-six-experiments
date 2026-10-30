# E1 frozen learning curves (descriptive)

Generated UTC: 20261030T043040Z

These figures plot the frozen E1 method-by-budget summary for all 17 methods and all 9 budgets. The source summary has 153 rows and binds to the frozen 765-cell ledger.

## Outcome accounting

Across the 765 planned cells there are 674 successful, 81 failed, and 10 unsupported outcomes. Those categories remain separate. Each method-budget point has five planned repetitions. Curves show the mean among successful repetitions only. Point annotations show n/5 wherever fewer than five repetitions succeeded. A zero-success point is omitted and leaves a line gap; it is never plotted as zero. Error bars are sample standard deviation (ddof=1) only when n >= 2. For n=1, SD is undefined and no error bar is drawn.

The three plotted outcomes are balanced accuracy, conformal coverage, and mean prediction set size. The dashed 0.90 line is the nominal coverage target; it is a reference, not a significance or calibration claim. No bootstrap, confidence interval, hypothesis test, or new model selection was performed.

## Frozen run context and cost limits

The frozen E1 configuration records Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0], NumPy 2.3.5, Linux platform Linux-7.0.0-1014-aws-x86_64-with-glibc2.39, a 6.0 GiB memory limit, 180 second trial timeout, and model_n_jobs=1. This figure render used the saved summary CSV only; it did not read models, predictions, role arrays, or rerun fits. The summary has no per-cell elapsed-time/cost fields, so these plots do not estimate compute cost. Resource and hardware behavior should be interpreted under the frozen E1 run metadata, not compared as if it used the later E3-E6 execution policy.

## Reproduction

From this directory, run:

    /usr/bin/python3 render_e1_frozen_curves.py

The renderer reads only E1_method_budget_summary_153.csv. E1_frozen_cells_765.csv is included as the ledger binding. The existing E1 heatmap and historical HTML are preserved separately.

## Source bindings

- Method-budget summary SHA-256: eab93af663cd170fb7c3d1c572fdb4be2f9faa97c961f9f8d1b86dedcfb133da
- Frozen 765-cell ledger SHA-256: 52d056aa2dc98f3721fb88a611bb4fa76aba74562751afc87b263f478c78b456
- Frozen master run config SHA-256: be5cdaf82de78e83cfcddb91858fb2eab2329bb793e7f5d0fe67d35c4aff9815
- Frozen environment record SHA-256: 4ceccd8b2b7833f524aab5e3af029d4c7e1b911ebd9e6fef83abe14a05a0e8ff
