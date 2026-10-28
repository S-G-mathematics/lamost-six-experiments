# Compact LAMOST Progress Snapshot

Created: 2026-10-27 20:49:33 UTC / 2026-10-28 02:19:33 IST
Counts are from the EC2 observer at 2026-10-27 20:47:52 UTC. Host i-095641a281a4038b9.

| Experiment | Planned | Successful | Scientific failures | Unsupported/unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 |
| E1 recovery supplement | 91 | 24 retry successes | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | 0 |
| E2 classical references | 120 | 120 | - | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 unavailable dependencies | 0 |
| E4 | 1,773 | 1,520 | 71 | 3 unavailable dependencies | 179 |
| E5 | 960 | 652 | 50 | 30 unavailable dependencies | 228 |
| E6 historical E3 references | 15 | 12 | 0 | 3 unavailable | 0 |
| E6-v2 primary ensembles | 6 | 0 valid test evaluations | 3 | 3 | 0 |

E1 remains frozen. Its 81 failures are 55 resource failures plus 26 supervisor-terminal cells with manifests still marked started; 10 unsupported cases are separate. Recovery remains separate and stopped at user request. No new E1/E2 fitting is needed or authorized.

E2 remains incomplete at 108/150 primary evaluations. Preserve its 31 original/reconstructed accuracy differences, 210 low-precision class-report flags, and four descriptive complete five-family correlations. Do not use those four strata to claim a general relationship or significance.

E3 is terminal at 64 successful, 3 failed, and 2 unavailable. Validated audit findings include direct GMM mean BA 0.8056, marginal coverage 0.8996, set size 1.487 (n=3); direct KDE 0/3 after 600-second evaluation timeouts; and Chow-Liu synthetic logistic class-A recall of zero in all three repetitions despite mean marginal coverage 0.8984. The E3 report still needs explicit prior-test-exposure disclosure.

E4 and E5 continue on the existing EC2. Waiting cases are pending, not failures. Current observer verified two E4 workers and controller identity. Available RAM was 27.46 GiB, free disk 39.62 GiB, and a STORAGE_HOLD.json marker was present while the storage estimate allowed work. These are point-in-time shared-host readings.

E6-v2 has 3 equal-weight test prediction timeouts and 3 learned-mode unavailable outcomes because the same repetition's shared test-posterior phase had terminally failed. Frozen tuning weights remain for all six tasks; learned candidate ledgers remain for three. There are no valid E6 test scores or ensemble-benefit findings. The 15 member-reference rows remain historical E3 references, not E6 results.

The six earlier E6-v1 zero-attempt gate outcomes remain superseded history. The published E6-v2 correction is deployed. Earlier operationally-invalid feature-order attempts were preserved and have since been superseded by the corrected E6-v2 executions; do not mix those attempts into scientific failure counts.

Still pending: global calibration-q replay, complete E4/E5 accounting and reporting, corrected E3 information-history disclosure, full cross-experiment report, verified full archive, compact laptop package, and final cleanup of project-owned processes. Bootstrap remains dropped. The full project is not complete.

Detailed E6 table and source receipt: runtime_20261025/reports/E6_CURRENT_DESCRIPTIVE_INTERIM_20261027T204752Z.md and runtime_20261025/reports/E6_V2_INTERIM_20261027T204752Z/.
Current registry/observer command: cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025 && /usr/bin/python3 source/observe_progress.py --by-rep

