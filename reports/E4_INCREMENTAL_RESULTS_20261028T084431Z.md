# Incremental validated E4/E5 results

Status observer timestamp: 2026-10-28T08:44:31.946790+00:00 UTC (the status JSON is a point-in-time observer record; its active list is not an OS process audit).

At this snapshot E4 recorded 1553 successful, 71 failed, 3 unavailable and 146 waiting cases out of 1,773. E5 recorded 700 successful, 50 failed, 78 unavailable and 132 waiting out of 960. These are current ledger counts, not a claim of experiment completion.

Three new validated ledger records appeared after the prior Git status snapshot: two E4 evaluations and one E5 clean-control alias. The E5 alias points to the E4 rep-3 direct Extra Trees control; it does not represent a separate fit or prediction pass. Only two unique prediction-outcome arrays are added.

| Task | Kind | Repetition | Condition | Balanced accuracy | Overall coverage | Mean set size | Target K recall/coverage | Test/calibration n |
|---|---|---:|---|---:|---:|---:|---|---:|
| e4/rep_2/eval/treatment/random_forest/K_tenth_generated_chow_liu | eval | 2 | K_tenth_generated_chow_liu | 0.722728 | 0.897186 | 1.799406 | 0.366693 / 0.704437 | 500000 / 10000 |
| e4/rep_3/eval/direct/extra_trees/control | eval | 3 | control | 0.768093 | 0.906260 | 1.592300 | 0.752616 / 0.900174 | 500000 / 10000 |
| e5/rep_3/eval/direct/extra_trees/clean | alias | 3 | clean | 0.768093 | 0.906260 | 1.592300 | 0.752616 / 0.900174 | 500000 / 10000 |

The E4 RF restoration row is one repetition of the K tenth-share generated Chow-Liu condition; the E4 Extra Trees row is the unchanged direct control. The E5 clean Extra Trees row reuses that control outcome. These rows do not establish a paired treatment effect or a general benefit. E4/E5 complete summaries and figures are still snapshot products; this supplement only records these three incremental cases.

Portable engineering qualification: 596/596 passed on EC2. The earlier 587/587 receipt remains in the repository. This engineering result does not add scientific evaluations.

The outcome-array delta is staged at github_delta_results_20261028/e4_three_validated_cells_20261028T084431Z/e4_three_validated_outcomes_delta.zip; SHA-256 49d94bba6fc13f4d4f56b10332e0410701e5a3e3d247ec1db37df772388c54a5, size 3144012 bytes; ZIP CRC passed. It is uploaded to the existing results-2026-10-28 release with a manifest and checksum sidecar; remote bytes were downloaded and matched. Verification receipt: metadata/E4_DELTA_RELEASE_UPLOAD_VERIFICATION_20261028.json. No model or FITS files are included.

Input evaluation, validation and result JSONs are copied under provenance/artifacts and bound by the incremental CSVs and array manifest.
