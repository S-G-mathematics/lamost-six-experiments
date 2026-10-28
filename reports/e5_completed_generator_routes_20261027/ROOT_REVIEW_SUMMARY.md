# Root review of the completed E5 generator-route subset

The 270-case subset is reviewed: 90 direct evaluations and 180 synthetic-only evaluations for GMM, Gaussian copula and Chow-Liu with logistic regression and HistGB, including clean controls. All planned cells in this subset succeeded. All paired summaries use three repetitions.

The independent table review passed 56,029 checks covering 270 saved aggregate evaluation JSONs, confusion matrices and class aggregates; 180 route comparisons (162 corrupted); 1,134 class comparisons; 54 route and 378 class summaries; 486 calibration/inference supervision receipts; and 693 unique dependency cost keys. The three final figures passed direct visual review. See ROOT_TABLE_REVIEW.json and ROOT_FIGURE_REVIEW.json.

This receipt supersedes the draft report/manifest's statement that root review was pending. It does not validate fitted model internals or independently reconstruct calibration quantiles. Full E5 (960 planned cells), global calibration replay, overall report review and final delivery remain incomplete.

The saved phase receipts contain private process evidence and remain on the original EC2. The delivered cost CSV contains relevant scalar measurements, source paths and hashes. The full regeneration script requires the original EC2 registry and private receipts; render_figures_only.py regenerates these figures from the provided CSV. A curated public scientific archive does not recreate private operational state. Task spans exclude pre-admission queue waiting and do not fully account for earlier invalid/interrupted attempts. No bootstrap or significance claims are made.
