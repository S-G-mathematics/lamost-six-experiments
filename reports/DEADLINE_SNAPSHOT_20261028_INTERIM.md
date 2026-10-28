# LAMOST six-experiment deadline snapshot (interim)

Observed status: 2026-10-28T16:36:51.126740+00:00 UTC (2026-10-28T22:06:51.126740+05:30 IST). This is a point-in-time snapshot, not final project completion. Registry counts do not prove worker liveness.

| Experiment | Planned | Successful | Failure | Unsupported/unavailable | Pending |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 |
| E1 recovery, separate | 91 | 24 | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 | - | 42 unavailable | - |
| E2 classical references | 120 | 120 | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 unavailable | 0 |
| E4 | 1773 | 1587 | 71 | 3 unavailable | 112 |
| E5 | 960 | 700 | 50 | 78 unavailable | 132 |
| E6 | 21 | 12 ledger successes including member references | 3 | 6 | 0 |

Full detail is in the [status CSV](DEADLINE_SNAPSHOT_20261028_INTERIM_STATUS.csv). E6 member-reference successes are not ensemble test results.

## Findings and limits

- **E1:** Frozen ledger remains 674 successful, 81 failed, 10 unsupported. The 81 failures comprise 55 resource failures and 26 supervisor-terminal cells with manifests still marked started. The recovery supplement is separate and stopped early: 24 successful retries, 10 retry failures, 2 user-stopped partials, 55 not attempted. No recovery outcome replaces frozen E1. Timing depends on hardware and shared load.
- **E2:** Primary coverage is 108/150; 42 cells unavailable due to unavailable frozen E1 model dependencies. Classical references are separate at 120/120. Integrity audit: 228 evaluated cells, 1,596 class reports, zero errors. Preserve all 31 reconstruction accuracy differences and 210 low-precision flags. Four complete primary correlation strata are descriptive only; they do not support a general fidelity/performance claim.
- **E3:** 64 successful, 3 failed, 2 unavailable of 69. Detailed route results and caveats are linked from [E3](experiments/E3/README.md).
- **E4:** 1587 successful, 71 failed, 3 unavailable, 112 waiting of 1,773. The latest increment adds 14 validated rep-3 RF treatment outcomes and per-class metrics; these are not paired effects. Their arrays are separately released at [the results release](https://github.com/S-G-mathematics/lamost-six-experiments/releases/tag/results-2026-10-28).
- **E5:** 700 successful, 50 failed, 78 unavailable, 132 waiting of 960. No new E5 results in this increment.
- **E6:** 12 historical member-reference successes; 3 failures; 6 unavailable. Zero successful primary ensemble test outcomes; no ensemble benefit claim.

No bootstrap was used. Predictive performance, resource feasibility, statistical fidelity, and artifact reproducibility remain separate. Full-project calibration-q replay and cross-experiment validation are pending.

## Included material and reproduction

This compact snapshot contains the current 717-qualified code/tests, experiment manifests/configuration summaries, reports, tables, and existing scientific figures. Recent E4 outcome arrays are linked in the release asset. It excludes fitted models, FITS, raw baseline data, and private operational receipts.

The committed 717-qualified source set does not include subsequent staged, unqualified admission or replication changes. This ZIP is not the full EC2 scientific archive. The overall final report and archive-wide CRC verification remain pending.

The project goal remains active; this is a deadline snapshot, not project completion.
