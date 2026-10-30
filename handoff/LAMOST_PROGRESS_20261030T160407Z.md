# LAMOST six-experiment progress and delivery status

Observed 2026-10-30T16:04:07.488732+00:00 / 2026-10-30T21:34:07.488732+05:30.

This is an interim progress report. The scientific grid, calibration/artifact validation, final scientific review and delivery packages are not complete. Scientific work and engineering checks were performed on the existing EC2 instance i-095641a281a4038b9. The laptop receives documents only.

## Scientific accounting

| Experiment | Planned | Successful | Failed | Unavailable/unsupported | User-stopped | Pending | Phase |
|---|---:|---:|---:|---:|---:|---:|---|
| Frozen E1 | 765 | 674 | 81 | 10 | 0 | 0 | Frozen; no further E1 runs |
| E2 primary | 150 | 108 evaluated | — | 42 | 0 | 0 | Incomplete coverage; no more fitting |
| E2 classical references | 120 | 120 evaluated | — | 0 | 0 | 0 | Separate reference analysis |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 | Scientific outcomes terminal; final validation pending |
| E4 | 1773 | 1632 | 71 | 3 | 67 | 0 | Scientific outcomes terminal; final validation pending |
| E5 | 960 | 726 | 50 | 78 | 101 | 5 | Pending work blocked by disk admission |
| E6 | 21 | 12 member references | 3 | 6 | 0 | 0 | Scientific outcomes terminal; final validation pending |

The later-experiment ledger totals 2823 scientific cases: {'user_stopped': 168, 'waiting_for_dependency': 5, 'successful': 2434, 'unavailable_dependency': 89, 'scientific_failure': 127}. The execution DAG has 6261/6270 validated-terminal nodes. Four fits and five evaluations remain at this observation.

The stopped E1 recovery supplement is separate: 24 successful retries, 10 retry failures, 2 user-stopped partial cells and 55 not attempted (91 total). Do not substitute these outcomes into frozen E1.

E6 has zero successful primary ensemble tests. Its 12 successful rows are member-reference aliases. Three equal-ensemble test phases timed out; the corresponding learned-weight evaluations are unavailable because the shared test-posterior phase did not complete. Three KDE member-reference evaluations are also unavailable from failed E3 direct evaluations.

## Pending execution keys

- e5/rep_1/fit/direct/extra_trees/missingness_05
- e5/rep_1/eval/direct/extra_trees/missingness_05
- e5/rep_1/fit/direct/extra_trees/missingness_10
- e5/rep_1/eval/direct/extra_trees/missingness_10
- e5/rep_1/fit/direct/extra_trees/missingness_20
- e5/rep_1/eval/direct/extra_trees/missingness_20
- e5/rep_1/eval/direct/extra_trees/label_noise_10
- e5/rep_1/fit/direct/extra_trees/label_noise_20
- e5/rep_1/eval/direct/extra_trees/label_noise_20

## Work completed in this continuation

- Applied the explicit approval for a 6 GiB working-space reserve and one fitting worker. The 10 GiB memory cap, 600-second scientific limits, termination grace, scientific source definitions and frozen E1 settings remain unchanged. The admission calculation separately reserves retired-array restoration and output space.
- Resumed the previous E5 queue: nine additional paired evaluations completed and were published with validated metric JSON and exact result-array ZIP assets. E5 successes increased from 717 to 726.
- Retired 2,132 complete result-array inode groups only after exact GitHub asset/member verification; the guardian retains the finalization lock until restoration and validation. It must not be killed while restoration is required.
- Completed a bounded EC2 model-archive transaction for eight models: 1,035,533,204 logical source bytes became 662,467,764 payload bytes. Native aliases were removed only after exact-byte and CRC checks. No fitted model was uploaded to GitHub.
- Installed the reviewed narrow archive profile and its durable scheduled task, retaining lock, zero-scientific-worker, disk, cooldown and failure-backoff checks. The second bounded batch is active under tmux; its actual processes were verified after detaching.
- Fixed final package collection to include nine exact SHA-pinned public approval, policy, source and engineering-test dependencies, without private ownership, process, hold or cleanup receipts.
- Preserved unsuccessful engineering-test attempts, corrected stale fixtures and one final-review inventory integration gap, then passed the complete 835/835 engineering suite. The successful gate took 57.62 seconds with 622,206,976 bytes peak sampled process-tree RSS.
- Checked project-only cleanup candidates. The convenience CSV remains present; fixture deletion would recover little because of hard links; bytecode caches were retained. Shared pip/uv caches, Harbor and unrelated material were untouched.

## Publication and archive evidence

GitHub: https://github.com/S-G-mathematics/lamost-six-experiments . Both main and results/snapshot-2026-10-28 were independently verified at commit d76ff2b10347d813146e66e37ec5f6474f7ecf16. This contains current code, available results, all 109 portable test modules and the 835-case pass receipt; later documentation commits may follow. Models are excluded.

The latest verified committed identity of the working archive was:

- Path: /home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip
- Bytes: 78,286,136,851
- SHA-256: 470025871dbf7f563636b90c7b8cd8444f6c0d5af6a8789c28f954fd369a6ba5
- Transaction: 6b44bed2afb14fa4826635712c3f23e4
- Status: working archive under further maintenance; not the final project delivery. Its identity will change on subsequent committed batches.

Portable pass receipt: runtime_20261025/reports/PORTABLE_TEST_PASS_afd7bee2762ea7c024f1fc52ad2b496cde69c95d2e9e32dcaff74031553de438.json; SHA-256 402ee0857c698646860b0597a91f949a5021a26cdc2ccd7416f257e016407597.

## Limitations and completion gates

E2 retains its previously audited limitations: 108/150 primary evaluations, 120/120 classical references, 1,596 class reports, 210 low-precision class flags, 31 reconstruction accuracy differences and only four complete five-family correlation strata out of 30. Original and reconstructed fits remain separate provenance groups. No general or significant fidelity/classification relationship is claimed.

Preserve omitted historical E1 model/prediction artifacts and the seven auxiliary tuning-history discrepancies in the final report. Historical full reproducibility is not established. Timings are hardware- and resource-policy-dependent. Report actual successful repetition counts and matched available comparisons; all observed E1/E2 test information history must remain disclosed. Bootstrap remains dropped.

The current scientific bottleneck is disk admission and verified compression, not an absence of RAM. No E1/E2 fits or new ARF variants were started. Pending or interrupted work is not being relabeled as scientific failure.

Remaining gates: finish the five pending E5 evaluations under the recorded policy; restore retained arrays; perform supervised calibration replay and full artifact validation; generate/review the immutable report, tables and figures; verify full and compact archive CRC/size/SHA; deliver the compact ZIP to the laptop; publish final relevant code/results; stop project-owned workers/watchers without touching Harbor.

An extracted archive supports descriptive reproduction, not live controller resumption. See REPRODUCTION_SCOPE_STORAGE_CAMPAIGN_20261030.md and RUN_RESUME_REPRODUCE.md. An independent rerun needs a fresh execution root and operational campaign; private historical indexes must not be fabricated.
