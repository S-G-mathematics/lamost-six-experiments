# Latest project progress snapshot

Status snapshot observed at **2026-10-28T17:30:46.034919+00:00 UTC** from the EC2 runtime status file. The public projection omits process identities and commands. Two running tasks were recorded at this observation. A separate live-process check at 2026-10-28T17:28:29Z had verified three RF4 model workers; that earlier process observation is not treated as current liveness.

| Experiment | Planned | Successful | Scientific failures | Unsupported / unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 (55 resource; 26 supervisor-terminal manifests still started) | 10 unsupported | 0 |
| E1 recovery | 91 separate supplement | 24 | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | - |
| E2 classical references | 120 | 120 evaluated | - | 0 | - |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1,773 | 1,592 | 71 | 3 | 107 |
| E5 | 960 | 700 | 50 | 78 | 132 |
| E6 | 21 | 12 member-reference successes | 3 | 6 | 0 |

The 730-check native qualification concerns controller and admission tooling; it does not mean the scientific project is complete. The E4 repetition-3 random-forest treatment gate adds a 6 GiB admission reservation only. Worker RSS remains capped at 10 GiB and trial timeout remains 600 seconds. Qualification fingerprint: `954cd3dff7872266c8e1e15632c94a2d7cacaf74037687dda3af6bf0d1b97204`.

The delivered tables and figures remain bound to the earlier registry snapshot at **2026-10-28T17:00:39.712874Z**: 2,823 planned E3-E6 cases; 2,366 successful, 127 failed, 89 unavailable, and 241 waiting. The status snapshot above has 239 waiting cases. Figures were not relabeled to imply newer results. The report is interim; E6 calibration replay, full final report validation, and final archive validation remain pending.

E1 and E2 remain frozen. E2 retains 31 reconstruction accuracy differences, 210 low-precision class-report flags, and four complete five-family correlation strata. Historical E1 model and prediction artifacts remain omitted; seven auxiliary tuning-history discrepancies remain disclosed. No bootstrap or unsupported significance claims are used. Fitted models, FITS files, credentials, and private operational receipts are excluded from this repository.
