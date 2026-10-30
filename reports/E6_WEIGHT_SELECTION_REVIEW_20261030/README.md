# E6 saved tuning-weight review

Observed 2026-10-30T09:36:25.110815+00:00. This is a metadata-only review. No models, posterior arrays, calibration replay, or test evaluations were read.

## Finding

The existing E6 interim report already provides all three learned simplex vectors, their candidate counts and selected candidate IDs, plus the three pairwise L1 and Euclidean distances. Each vector matches its selected candidate row in its saved candidate ledger. The frozen record and ledger agree on seed and member order, and each record states weights were frozen before calibration and test.

| Rep | Selected candidate | Candidates | Frozen weights (GMM, copula, ARF, KDE, Chow-Liu) |
|---:|---:|---:|---|
| 1 | 1050 | 1606 | [0.8179124100009786, 0.022277051133202976, 0.011824674884291713, 0.12143674541889833, 0.026549118562628423] |
| 2 | 1058 | 1558 | [0.7769258283413296, 0.051455934383179996, 0.011085969460894117, 0.15520731953403916, 0.005324948280557195] |
| 3 | 1261 | 1606 | [0.7281266536012706, 0.05096462702166241, 0.0062191491464014745, 0.045693054230705105, 0.1689965159999604] |

The existing stability table reports learned-vector pairwise distances: rep 1-2 L1 0.1258989147 / Euclidean 0.0642087990; rep 1-3 L1 0.3422699467 / Euclidean 0.1869338085; rep 2-3 L1 0.3273431354 / Euclidean 0.2029459119. These values match direct arithmetic on the three saved vectors. Equal-weight vectors are identical across reps (all five weights 0.2).

## Limits

Candidate counts were 1606, 1558, and 1606 under a bounded search (cap 2000), explicitly not a globally optimal search. The phase-cost CSV has a header but zero data rows, so tuning costs are not reported here. E6 has zero successful primary test evaluations; these tuning-only selections do not support ensemble performance or benefit claims. The earlier E6 interim report remains the source for the full E6 availability and phase-failure context.

The machine-readable receipt binds the reviewed inputs and each frozen-weight/candidate-ledger file by SHA-256.
