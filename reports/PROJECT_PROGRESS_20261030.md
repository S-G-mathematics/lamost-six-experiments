# LAMOST six-experiment progress — 30 October 2026

Observed 2026-10-30 07:31 IST / 2026-10-30T02:01:04.669225+00:00. This is an interim report; the project is not yet complete. This snapshot supersedes the earlier 05:37 IST status and is based on a read-only SQLite registry snapshot.

| Experiment | Planned | Successful / evaluated | Failed | Unsupported / unavailable | User-stopped | Pending |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | 0 |
| E2 primary | 150 | 108 evaluated | 0 new failures | 42 unavailable | 0 | 0 scheduled |
| E2 references | 120 | 120 evaluated | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 | 0 |
| E4 | 1773 | 1632 | 71 | 3 | 67 | 0 |
| E5 | 960 | 713 | 50 | 78 | 101 | 18 |
| E6 | 21 | 12 member-reference aliases | 3 | 6 | 0 | 0 |

E4 is fully accounted under the repetition scope amendment. User-stopped cases were not evaluated and are not scientific failures. E6 has zero successful primary five-member ensembles; its twelve successful member aliases are not ensemble successes. Original plans and previous repetitions remain preserved.

## Recent results and publication

The final E4 QSO tenth-share / Extra Trees repetition-1 evaluation validated at 23:06:20 UTC: balanced accuracy 0.708357224521458, overall conformal coverage 0.896942, mean set size 1.55683. QSO recall was 0.5138150903294367 and QSO coverage 0.6657810839532412. It used 10,000 calibration and 500,000 test rows. Overall coverage near 90% does not imply coverage near 90% for each class.

E4's full 1773-cell ledger, paired and per-class tables, and two figures are in the GitHub snapshot reports/E4_DESCRIPTIVE_REFRESH_20261029T231928Z. Its last result-array ZIP passed CRC and downloaded size/SHA verification.

E5 repetition-1 synthetic Random Forest / Chow-Liu at 5% feature noise validated at 23:31:23 UTC. Balanced accuracy was 0.6107529048401739, coverage 0.896618 and mean set size 2.362494. Relative to the matched repetition-1 clean pipeline, the differences were -0.01537191345 in balanced accuracy, +0.000236 in coverage and +0.146048 in set size. This is one matched pair, n=1/3, with no repetition SD or significance claim. Its result ZIP was remotely verified: 1,597,798 bytes, SHA-256 56fff276a5f7d83bda4f339348f1dc0d78df5ee56d7ac8ff84a9348888e9ea47.

The matching copula synthetic Random Forest / 5% feature-noise case validated at 23:52:31 UTC: balanced accuracy 0.5736219548273466, coverage 0.892858 and mean set size 2.309316, again with 10,000 calibration and 500,000 test rows. These individual route outcomes do not establish universal generator or robustness rankings.

Relevant code and results are pushed to both main and results/snapshot-2026-10-28 at github.com/S-G-mathematics/lamost-six-experiments. Generic operational source commit: 8b02c32bc6bbc7fab1efb141045a47a79c6528f3. Latest verified results commit: e6b29ad4fdaabb4ea04cef2021d4556579c7277b. No fitted models were uploaded.

## Frozen evidence and limitations

Frozen E1 remains 765/765 terminal. Its validated report SHA-256 remains e96c21ec455ee614ce29d616170664bdd4de7290171042a1c8c4e7cde0aa1277. The 81 failures comprise 55 resource failures and 26 supervisor-terminal cases whose cell manifests remained started. The ten unsupported cases are separate.

E1 recovery remains an early-stopped supplement: 24 successful retries, 10 retry failures, 2 user-stopped partial cells and 55 not attempted. None replaces a frozen outcome.

E2 remains 108/150 in primary coverage, with 42 unavailable original-model dependencies and 120/120 classical references. Original/reconstructed provenance, the 31 reconstructed accuracy differences, 210 low-precision class flags and only four complete five-family correlation strata remain disclosed. No general or significant fidelity–classification relation is claimed from four strata.

Historical E1 pipelines and per-test-row predictions omitted from the compact migration remain omitted. The seven auxiliary tuning-history discrepancies and unavailable exact original histories remain disclosed; verified completion metrics are not overwritten. Conditional-on-success and hardware-dependent timing limitations remain. Bootstrap remains dropped.

## Current EC2 execution and storage status

The project remains on the established EC2 host and project tree. At the 02:01 UTC observation, a read-only process check found the controller and the archive-maintenance operation auto_storage_20261030T014501Z_635f7991 active, with zero specialized scientific worker processes. E4 has no pending cells under the applied repetition-scope amendment; E5 has 18 waiting evaluations. Do not interpret those waiting cells as terminal.

Available filesystem space was 21,874,196,480 bytes at 02:01 UTC. The latest completed model-archive transaction recorded by the supervisor was 74,945,518,462 bytes with SHA-256 e35cffc782e9440289004238126dbc97568bba0a3c9d43bacce6b251ef414edb; that is a completed prior transaction, not a digest of the current BUILDING archive. The current archive operation is still active, so the BUILDING archive is not the final validated archive.

The archive-retention workflow preserves model payloads in verified GitHub release assets while their EC2 copies await restoration. No models were added to Git. The finalizer must wait until all 6,270 planned DAG tasks are terminal, the controller and workers have exited, and required scientific arrays have been restored and validated. Full calibration-quantile replay and final artifact validation remain outstanding. Shared pip/uv caches and Harbor remain outside this project cleanup.

## Latest validated E5 batch

The latest report carries forward the previously validated 20% Copula feature-noise comparison and adds four newly validated repetition-1 synthetic Random Forest label-noise evaluations:

| Corruption | Balanced accuracy | Coverage | Mean set size | Change vs matching clean BA / coverage / size |
|---|---:|---:|---:|---|
| Copula feature noise, 20% | 0.573622 | 0.892858 | 2.309316 | -0.033536 / -0.000028 / +0.219412 |
| Copula label noise, 5% | 0.582086 | 0.893820 | 2.252508 | -0.013310 / +0.002028 / +0.054356 |
| ARF label noise, 10% | 0.653976 | 0.893378 | 2.017652 | -0.004178 / -0.002098 / +0.007390 |
| Chow-Liu label noise, 10% | 0.623227 | 0.897520 | 2.257902 | -0.002898 / +0.001138 / +0.041456 |
| Copula label noise, 10% | 0.577932 | 0.891124 | 2.277474 | -0.017464 / -0.000668 / +0.079322 |

These are matched to the exact repetition-1 clean pipeline with the same route and generator. Each comparison is n=1/3; sample SD is undefined and no significance or across-repetition conclusion is claimed. Each evaluation used 10,000 calibration rows and 500,000 test rows.

The four-case tables and validation records are in reports/E5_INCREMENTAL_VALIDATED_20261030T015616Z/. Their result-only ZIP is e5_incremental_validated_outcomes_20261030T015616Z.zip: 6,153,286 bytes, SHA-256 52fceef57aa380229100e27fc67d31cb5f67aef0936cce9cb61b983e0ee23007, CRC passed after download verification. The corresponding report and results commit is 00cf457a374be57c85b64b0d7b35f991ad552134 on both main and results/snapshot-2026-10-28.

## Remaining completion work

Finish the 18 waiting E5 evaluations under the fixed policy; restore temporarily retained arrays; run supervised artifact and conformal replay; finalize all reports, tables, figures and cross-experiment caveats; review the exact final candidate; verify full EC2 and compact delivery archives; publish final relevant code/results; and stop only project-owned workers/watchers after verified completion.
