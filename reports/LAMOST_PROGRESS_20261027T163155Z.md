# LAMOST project progress — interim

Observed: 2026-10-27T22:01:55.134213+05:30 (Asia/Kolkata), 2026-10-27T16:31:55.134213+00:00 (UTC).
Host: existing EC2 instance `i-095641a281a4038b9`, accessed through `w7-ec2`.
This is an interim execution report. The six-experiment project and final delivery are not complete.

## Scientific cases

| Group | Planned | Successful/evaluated | Failed | Unsupported/unavailable | Pending or active |
|---|---:|---:|---:|---:|---:|
| Frozen E1 | 765 | 674 | 81 | 10 unsupported | 0 |
| E2 primary | 150 | 108 | 0 | 42 unavailable | 0 |
| E2 classical reference | 120 | 120 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1773 | 1489 | 71 | 3 | 210 |
| E5 | 960 | 652 | 50 | 30 | 228 |
| E6 | 21 | 12 | 0 | 9 | 0 |

E1 recovery remains a separate early-stopped supplement: 24 successful retries, 10 failed retries, 2 user-stopped partial cells and 55 not attempted. It is not substituted into frozen E1.

E3 and E6 have terminal case accounting, including unavailable comparisons. This does not mean every scientific question produced an evaluated result. E6 has all 15 selected member models, but three KDE direct-evaluation timeouts made three member-reference and six primary ensemble cells unavailable. No primary ensemble scores or optimized weights were obtained; no ensemble benefit is claimed.

## E4 and E5 repetitions

| Experiment | Rep | Successful | Failed | Unavailable | Pending or active |
|---|---:|---:|---:|---:|---:|
| E4 | 1 | 544 | 27 | 1 | 19 |
| E4 | 2 | 504 | 23 | 1 | 63 |
| E4 | 3 | 441 | 21 | 1 | 128 |
| E5 | 1 | 218 | 18 | 2 | 82 |
| E5 | 2 | 216 | 16 | 24 | 64 |
| E5 | 3 | 218 | 16 | 4 | 82 |

## Current execution

The observer verified the controller and 2 actual scientific workers at the observation timestamp. Their fitting tasks were:
- `e4/rep_1/fit/treatment/random_forest/K_tenth_ros`
- `e4/rep_3/fit/direct/arf/G_half`

There is no fixed two-worker cap. Three fits were verified concurrently earlier in this session; the controller admits additional workers only when current CPU, RAM commitments and storage allow them. The observed host had 26.91 GiB available RAM and 42.11 GiB free disk. No admission hold was present. The historical STORAGE_HOLD marker is not a liveness or scheduling claim; the current storage estimate allowed admission.

Scientific source files, memberships, task plan, E1 results and scientific limits remain unchanged. Scientific limits remain 600 seconds per tuning trial and final fit/generation/prediction phase, 10 GiB hard worker limits, fixed trial counts, one nested thread and 50,000-row prediction chunks. Total tuning duration can exceed 600 seconds because the timeout applies to each trial.

## Operational work completed in this session

- Verified and archived 16 completed RF model groups containing 1,821,076,954 original bytes. The bounded RAW archive operation completed in 462.566 seconds, with original-byte identity preserved.
- Recovered the subsequent interrupted legacy compression operation using the original pinned storage core. It had not committed; all source aliases were retained. Recovery verified the archive SHA, index and member payloads in 403.189 seconds. Its failed supervision record remains preserved.
- Paused the legacy compression schedule, which repeatedly reached its 600-second operational limit as the archive grew.
- Installed a reviewed RAW archive watcher using the existing bounded 1,800-second operational profile. It observes every five minutes and acts only below 2 GiB of current controller storage headroom. Each batch is limited to 2 GiB and 16 groups with a 1.5 GiB helper reservation. This changes no scientific timeout or fit policy.
- Verified the watcher's first scheduled decision at 16:30 UTC: idle because storage headroom was sufficient. This is a completed decision record, not evidence of an active process.
- Qualified and installed a minimal reporting/delivery update: 426 tests plus 51 subtests passed under the existing exit-race-aware guard in 19.575394 seconds, with 456,888,320 bytes sampled peak process-tree RSS, exit 0 and no termination signal. All 419 prior cases were retained. This is engineering validation, not the pending global scientific validation.
- Added explicit E3 disclosure for the missing real-only RF repetition 1 publication receipt. Existing model/configuration/fit/validation evidence and saved evaluation metrics remain; no receipt was fabricated.
- Added ownership-nonce removal to derived public archive JSON views and exact cleanup support for the new watcher command.
- Preserved the controller, all 11 frozen scientific sources, all 19 frozen E1 sources, task plan and freeze bytes. No controller restart or scientific worker signal was required.

The larger background-admission controller prototype remains staged, incomplete and deferred. It was not deployed.

## Archive and delivery state

The full overall archive is still BUILDING:

`/home/ubuntu/lamost_e1_migration_20261023/packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip`

Verified committed snapshot: 29,961,455,262 bytes, 166 cold-model members, SHA-256 `54a89bc4ed0d01ab6235be4fe3e8553ecf63194f7e4350f8ca85339160e010c3`.
This is not a final project archive. The hash came from the qualified storage transaction and subsequent original-core recovery verification; routine progress observations do not rehash the entire archive.

An older verified compact interim ZIP and the dated progress/supervisor Markdown files are on the laptop. Final full and compact delivery packages remain pending.

## Scientific limitations retained

Frozen E1's 81 failures remain separated into 55 resource failures and 26 supervisor-terminal cases whose manifests remained started; its 10 unsupported cases remain separate. Historical omitted E1 models and per-row predictions are not claimed restored. The seven auxiliary tuning-history discrepancies remain disclosed; missing complete histories were not fabricated.

E2 remains 108/150 primary evaluations plus 120/120 separate classical references. Preserve original/reconstructed provenance, 31 reconstruction balanced-accuracy differences and 210 low-precision class reports. Its four complete five-family correlation strata are descriptive, not evidence of a general relationship or significance. No further E1/E2 fitting or recovery is planned.

Bootstrap remains dropped. Repetition means, standard deviations and paired differences are descriptive. Timing is hardware/load dependent, and performance summaries remain conditional on actual successful cases.

## Remaining work

Continue E4/E5 from validated dependencies; preserve ordinary terminal failures without automatic scientific retries. After all 6,270 DAG tasks are terminal, run the full artifact and conformal-quantile replay gates, regenerate final tables/figures/reports, review the exact report candidate, verify full and compact ZIP CRC/SHA/size, deliver the compact ZIP, and shut down only exact project-owned workers/watchers. Leave Harbor untouched.

Authoritative resume state: `runtime_20261025/reports/LATEST_EXECUTION_CONTINUATION_NOTE_20261026.json`.
Current engineering fingerprint: `09646c124938164119fbc1e84dc31d5566c99ece118abdecb43f95461fb4a4d4`.
