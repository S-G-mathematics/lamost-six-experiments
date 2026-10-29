# 764 qualification and current interim registry snapshot

Observed on the existing EC2 at 2026-10-29T02:10:44.392619+00:00 UTC. This is an interim publication and does not claim completion of the six-experiment project.

## Qualified source and test closure

The portable engineering qualification passed 764/764 tests. Fingerprint: 6bad0b705d58a0b7cb99762c24e83876416cc20f2451168440c3c2b09ffe8bcc. Receipt SHA-256: 9f61a40205f0c0631d791216a05a9e05e4f61b7f4b20e9451d17b7a23a717583. The qualified bundle resolves 171 source, test, and Python fixture files; exported versions are hash-matched to the live EC2 bundle. Qualification is software evidence, not scientific completion.

The public selection-receipt audit validated 578 canonical fallback bindings and excluded 27 records lacking fit_publication.json. It opened zero model payloads and zero cold-archive payloads. The audit JSON and reproduction script are in provenance/qualification_764/.

## Current E3-E6 scientific-case ledger

The current ledger has 2,823 planned cases from registry snapshot 2026-10-29T02:10:44.392619+00:00. These are case counts, not process counts.

| Experiment | Planned | Successful | Scientific failure | Unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1,773 | 1,605 | 71 | 3 | 94 |
| E5 | 960 | 700 | 50 | 78 | 132 |
| E6 | 21 | 12 member-reference aliases | 3 ensemble failures | 6 | 0 |

E6 has zero successful primary ensemble test evaluations. The 12 successful reference rows are aliases to member evaluations, not five-member ensemble outcomes.

Frozen E1 remains 765/765 terminal: 674 successful, 81 failures (55 resource failures and 26 supervisor-terminal cells whose manifests remained started), and 10 unsupported. The stopped E1 recovery supplement remains separate: 24 successes, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. E2 remains 108/150 primary evaluations plus 120/120 classical references; reconstruction differences, low-precision flags, and four complete five-family correlation strata remain disclosed.

Earlier aggregate tables and figures retain their documented historical analysis cutoff. Incremental validated result supplements remain separate and dated. No bootstrap or unsupported significance claims are included. Final calibration replay, cross-experiment validation, and the final archive remain pending. This Git repository excludes fitted models, FITS files, raw datasets, prediction-array payloads, credentials, private process receipts, and Harbor files.
