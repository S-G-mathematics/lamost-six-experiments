# LAMOST six-experiment progress update

**Snapshot:** 2026-10-27 15:35:15 UTC / 21:05:15 Asia/Kolkata  
**Host:** existing EC2 instance `i-095641a281a4038b9`  
**Source:** read-only `source/observe_progress.py --by-rep` observation plus current receipts and the latest execution continuation note. The observer verified the controller and process identity; it did not use heartbeat age.

## Current scientific coverage

The table reports scientific cases only. E3-E6 are the 2,823 later-experiment evaluation cells in the live plan. The 6,270 DAG tasks also include their dependencies.

| Experiment/group | Planned | Successful | Scientific failures | Unsupported | Unavailable dependency | Waiting | Active at snapshot |
|---|---:|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 | Complete; frozen |
| E1 recovery supplement | 91 | 24 | 10 | 0 | 0 | 0 | Separate; stopped by user |
| E2 primary | 150 | 108 | 0 | 0 | 42 | 0 | Reporting only; no new fits |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | 0 | Complete as separate reference set |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 | Terminal |
| E4 | 1,773 | 1,466 | 71 | 0 | 3 | 233 | One verified direct-ARF fit |
| E5 | 960 | 652 | 50 | 0 | 30 | 228 | No live task in the observer snapshot |
| E6 member/ensemble cells | 21 | 12 | 0 | 0 | 9 | 0 | Terminal |

The stopped E1 supplement's 24 successes and 10 retry failures are separate from the frozen E1 ledger. Its 2 partial cells are user-stopped and 55 queued cells are not attempted; none are scientific failures.

### Repetitions in the fresh observer snapshot

| Experiment | Rep | Successful | Failed | Unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 |
| E4 | 1 | 541 | 27 | 1 | 22 |
| E4 | 2 | 494 | 23 | 1 | 73 |
| E4 | 3 | 431 | 21 | 1 | 138 |
| E5 | 1 | 218 | 18 | 2 | 82 |
| E5 | 2 | 216 | 16 | 24 | 64 |
| E5 | 3 | 218 | 16 | 4 | 82 |
| E6 | 1 | 4 | 0 | 3 | 0 |
| E6 | 2 | 4 | 0 | 3 | 0 |
| E6 | 3 | 4 | 0 | 3 | 0 |

At 15:35:15 UTC, the observer verified one scientific worker: E4 repetition 3 direct ARF fit for GALAXY_tenth, using the recorded 6 GiB admission profile. There were no unverified running scientific records. This is a point-in-time observation, not a projection of completion time.

## E1 and E2

Frozen E1 remains 765/765 terminal: 674 successful, 81 failed, and 10 unsupported. The 81 failures remain separated as 55 resource failures and 26 supervisor-terminal cells whose manifests remained `started`. The E1 report retains actual successful repetition counts by method and budget, conditional-on-success summaries, and the hardware timing caveat. No more E1 fitting or recovery is planned.

E2 remains transparently incomplete in primary coverage: 108/150 primary cells evaluated; the 42 unavailable ARF/KDE cells depended on frozen E1 failures. The separate classical reference set is 120/120. Of 1,596 class Quality Reports, 210 retain low-precision flags. Across reconstructed fits, 31 balanced-accuracy differences from the frozen E1 records remain disclosed; each E2 classification score is paired with its own measured fit. Four of 30 complete five-family strata have descriptive within-stratum Spearman correlations (0.7, 0.1, 0.3, 0.7). They do not support a pooled or general fidelity-performance claim. The E2 integrity audit found zero errors in 228 evaluated cells.

The seven auxiliary tuning-history discrepancies and omitted historical model/prediction artifacts remain documented. They are not replaced with fabricated history. The full identity recheck recorded unchanged E1/E2 accepted evidence (receipt SHA `bfdd3fc9e9b0f1193c08294fb32adffbdd3442417c8017bb2164d3c4b0285753`).

## E3-E6

E3 has 64/69 successful evaluations. Three direct KDE evaluations timed out at the fixed 600-second limit; two downstream RF cells are unavailable dependencies. These are recorded outcomes, not retry requests.

E4 has 1,466/1,773 successful cases and 233 waiting on dependencies. E4's completed-block snapshot and per-cell artifacts are still not the final E4 report; global conformal-quantile replay is pending.

E5 has 652/960 successful cases and 228 waiting. A reviewed direct-RF block is complete at 30/30: at 20% corruption, descriptive mean balanced-accuracy losses were 0.010556 for feature noise, 0.017309 for label noise, and 0.005531 for missingness. These are a direct-RF subset, not a conclusion about all E5 routes. A separate audit validated all nine label-noise realizations against the original fit-role labels and nested affected masks.

E6 has 12/21 successful cells and 9 unavailable dependencies. All 15 selected member pipelines are present, but KDE's three direct evaluations timed out. The six primary ensemble cells therefore have no five-member ensemble result. E6 must not be described as an ensemble improvement study with measured ensemble scores.

## Current EC2 and storage state

At the observer snapshot, the host had 27.6 GiB available RAM and 40.89 GiB free disk. The storage admission estimate reported backoff: free bytes were 509,888,407 bytes below the recorded minimum. Both admission/storage marker files were present. This read-only report did not change them.

A raw archive batch `auto_storage_20261027T152955Z_31aa6da4` was verified active at 15:35 UTC under the bounded `storage-followup` archive I/O profile (1,800-second storage child limit). Its completion has not been verified; no success is claimed. The latest recorded archive snapshot was `packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip` at 25,760,173,359 bytes, but that snapshot predates the active batch and is not a final delivery archive.

The storage I/O profile update is installed and its qualified external portable gate passed 419/419 tests in 18.27 seconds, with 480,608,256 bytes peak sampled process-tree RSS. The earlier native supervision attempt remains recorded as failed supervision, not as a pass. The exact admission hold remains present; the report does not release it. This engineering gate is not scientific validation.

A compact interim report/table/figure ZIP already exists on the laptop, SHA-256 `ce601d1140b3e37d8f65952987c56af212ab08cab76f66ba3d9acf98348908f3`. It is explicitly interim and is not the final project package.

## Remaining work

- Continue the authorized E4/E5 DAG from validated dependencies, preserving all terminal failures and unavailable cases.
- Run the final full artifact/model and calibration replay gates when the queue reaches a safe terminal state; current evaluation audits do not substitute for those gates.
- Finish E4/E5 and cross-experiment scientific reports, figures, availability tables, and final candidate review.
- Finish and validate the full EC2 archive and compact final reports ZIP; verify laptop delivery.
- Stop project-owned workers/watchers only after completion, without touching Harbor.

Bootstrap remains dropped. E1/E2 outcomes remain frozen; later experiments use their own provenance. Timing is hardware/load dependent, and no significance or universal-method claim is inferred from descriptive repetitions.
