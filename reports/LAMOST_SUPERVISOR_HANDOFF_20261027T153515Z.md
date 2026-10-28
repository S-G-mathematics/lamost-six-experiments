# Supervisor handoff: LAMOST Experiments 1-6

**Prepared:** 2026-10-27 15:35:15 UTC / 21:05:15 Asia/Kolkata  
**EC2:** `i-095641a281a4038b9`, migration root `/home/ubuntu/lamost_e1_migration_20261023`

Please review the current evidence and point out any concrete scientific-accounting, provenance, or finalization issue that should change the remaining in-scope work. All six experiments are already authorized. This handoff is not a pause or approval gate: continue the active E4/E5 queue and subsequent validation without waiting for routine confirmation. Ask the user only if a concrete choice falls outside the recorded authorization.

## Verified state at this handoff

A fresh read-only observer ran at 15:35:15 UTC / 21:05:15 IST. It verified the controller and actual process identity. Live scientific coverage:

| Experiment | Planned | Successful | Failed | Unsupported | Unavailable | Waiting |
|---|---:|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | 0 |
| E1 recovery supplement, separate | 91 | 24 | 10 | 0 | 0 | 0 |
| E2 primary | 150 | 108 | 0 | 0 | 42 | 0 |
| E2 classical reference | 120 | 120 | 0 | 0 | 0 | 0 |
| E3 | 69 | 64 | 3 | 0 | 2 | 0 |
| E4 | 1,773 | 1,466 | 71 | 0 | 3 | 233 |
| E5 | 960 | 652 | 50 | 0 | 30 | 228 |
| E6 | 21 | 12 | 0 | 0 | 9 | 0 |

The exact repetition counts are in the dated progress report. E3 and E6 are terminal at this snapshot; E4/E5 are still progressing. E6's 15 member models are available, but three KDE evaluations timed out and the six five-member primary ensemble cells have no results. Do not claim ensemble performance.

E1 is frozen and must remain unchanged. Its 81 failures are 55 resource failures and 26 supervisor-terminal cells with `started` manifests; 10 other cells are unsupported. Its recovery supplement was stopped at the user's request: 24 successful retries, 10 failed retries, 2 user-stopped partials, 55 not attempted. Do not restart it or substitute recovery outcomes into E1.

E2 must remain reported as 108/150 primary cells plus a separate 120/120 classical reference set. Preserve the 42 unavailable ARF/KDE dependencies, 210 low-precision class reports, 31 reconstruction score differences, auxiliary tuning-history caveats, and the four descriptive complete-stratum correlations. There is no further E1/E2 fitting authorization.

E3/E6 have descriptive reports and a reviewed synthesis, but the global calibration-quantile replay and final full artifact audit are pending. E4/E5 final scientific reports and cross-experiment conclusions remain incomplete. Bootstrap stays dropped.

## Current operations and delivery

One direct E4 ARF fit was actual-process verified at the observer time. The host had 27.6 GiB available RAM and 40.89 GiB free disk. The storage admission estimate was in backoff by about 0.51 GB against its recorded minimum.

The raw archive operation `auto_storage_20261027T152955Z_31aa6da4` was actual-process verified as active under the bounded 1,800-second archive I/O profile. Its result is not yet verified. Keep the existing admission/storage holds until the responsible transaction/owner records a valid completion or recovery receipt. The prior `LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip` snapshot is explicitly not final and predates the active transaction.

The storage I/O profile's 419-case candidate gate is installed and qualified using the existing race-aware external guard: 419/419 passed, 18.27 seconds, peak sampled RSS 480,608,256 bytes. The failed native supervision attempt is preserved and is not counted as the pass. Engineering tests do not qualify scientific outputs.

The interim laptop ZIP is already verified (6,725,024 bytes, SHA-256 `ce601d1140b3e37d8f65952987c56af212ab08cab76f66ba3d9acf98348908f3`); it is not the final delivery. Do not wait on full-archive transfer before finishing independent scientific validation.

## Guidance requested

Please check for specific discrepancies or missing finalization gates in the evidence, and give any further guidance needed on choices not covered by the existing protocol or explicit authorization. Otherwise, continue without pausing: finish E4/E5, validate the complete project honestly, and produce the verified EC2 and laptop packages. Do not change frozen E1/E2, restart terminal failures, expand scientific limits, add bootstrap, provision infrastructure, or touch Harbor.


## Verified operational update: 21:10 IST / 15:40 UTC

The previously active bounded-1800 RAW archive operation completed successfully: 16 model groups containing 1,821,076,954 original bytes were archived in 462.566 seconds. Transaction `05e9531eaf9c41ef9a3087161100a5ce` is complete, and its exact admission hold was released automatically.

The BUILDING archive is now 29,961,455,262 bytes with 166 members. Its SHA-256 is `54a89bc4ed0d01ab6235be4fe3e8553ecf63194f7e4350f8ca85339160e010c3`. The qualified child freshly verified this hash under its exclusive lease. Root checked matching journal, manifest, ZIP index, file identity, alias removal and process-exit evidence without rereading 30 GB during resumed science. The review receipt is `reports/engineering_audits/FIRST_BOUNDED1800_RAW_ARCHIVE_VERIFIED_20261027.json`, SHA-256 `41a6c2730224d441601dda9f06b2af0758a115ea92b66559b5202806d940bd51`.

At 21:10 IST, actual process identities verified four scientific workers, including three fits. The former two-worker cap is not in use. E4 had 1,468 successes, 71 failures, 3 unavailable cells, 1 active evaluation and 230 waiting cells. E5 remained at 652 successes, 50 failures, 30 unavailable cells and 228 waiting cells. Other scientific counts in the 15:35 snapshot were unchanged. Available RAM was 27.88 GiB and free disk was 42.58 GiB. The historical STORAGE_HOLD marker persisted, but the fresh controller estimate allowed admission.

A change allowing archive maintenance to coexist with fitting is staged only. It requires review of the source amendment, process identity, locking and resource accounting before installation. It is not part of the running 419-test operational source. Final artifact and conformal-quantile replay validation, the final scientific report and final packages remain pending.
