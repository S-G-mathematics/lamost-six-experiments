# LAMOST Project Progress and E6 Correction Status

Report created: 2026-10-27 18:31:59 UTC / 2026-10-28 00:01:59 IST
Project root: /home/ubuntu/lamost_e1_migration_20261023
Runtime: /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
EC2 identity observed: i-095641a281a4038b9

This is an interim status report. It does not claim that the six-experiment project, global calibration replay, final scientific report, or final archive is complete.

## Fresh execution observation

The observer ran on EC2 at 2026-10-27 18:31:24 UTC / 2026-10-28 00:01:24 IST. It read the current task registry and verified the controller and three fitting workers. There were no registry rows marked running without a verified process at that observation.

| Experiment | Planned | Successful | Scientific failures | Unsupported or unavailable | Waiting | Current state |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 unsupported | 0 | Frozen and terminal |
| E1 recovery supplement | 91 | 24 retry successes | 10 retry failures | 2 user-stopped; 55 not attempted | 0 | Stopped at user request |
| E2 primary | 150 | 108 evaluated | - | 42 unavailable | 0 | Incomplete coverage; reporting preserved |
| E2 classical references | 120 | 120 evaluated | - | 0 | 0 | Separate reference set |
| E3 | 69 | 64 | 3 | 2 unavailable dependencies | 0 | Terminal |
| E4 | 1,773 | 1,501 | 71 | 3 unavailable dependencies | 198 | Running |
| E5 | 960 | 652 | 50 | 30 unavailable dependencies | 228 | Running |
| E6 legacy ledger | 21 | 12 historical E3 member-reference evaluations | - | 9 legacy gate-unavailable outcomes | 0 | Superseded for primary E6 interpretation |
| E6-v2 correction | 6 primary ensemble tasks | 0 | 0 | 0 recorded | 6 not launched | Staged; qualification pending |

The E6 legacy row records the old dependency-gate state. It is not a valid statement that the corrected primary E6 ensembles were scientifically evaluated or that all 9 unavailable rows had missing models.

The resource observation at 18:31:22 UTC showed 26.55 GiB available RAM and 39.25 GiB free disk. The storage-admission observer allowed work under its recorded estimate, with approximately 1.93 GB headroom, while a STORAGE_HOLD.json marker was present. These are timestamped observations, not a promise of current headroom or scheduling permission. The three verified workers were E4 ARF fits for K tenth and M half conditions and an E4 generated-restoration random-forest fit for G half.

## Frozen E1 and E2

Frozen E1 remains 765/765 terminal: 674 successful, 81 failed, and 10 unsupported. The 81 failures comprise 55 resource failures and 26 supervisor-terminal cells whose manifests remained started. Unsupported cases remain separate from failures. No further E1 cells are authorized or needed.

The separate E1 recovery supplement stopped early at user request: 24 successful retries, 10 retry failures, 2 user-stopped partial cells, and 55 not attempted. Recovery outcomes do not replace or alter the frozen E1 ledger.

E2 has 108 of 150 primary generator evaluations. The other 42 cells remain unavailable because required model/evaluation dependencies are unavailable; E2 is not complete in primary coverage. Its separate classical reference set has 120/120 evaluations. Preserve the 31 original-versus-reconstructed accuracy differences, 210 low-precision class-report flags, and four complete five-family correlation strata. The four strata are descriptive only and do not support a general fidelity-performance claim or significance claim.

The auxiliary tuning-history caveats and omitted historical fitted-model/prediction artifacts remain documented provenance limitations. They do not invalidate the previously validated completion metrics. Do not claim that all historical pipelines were restored.

## E3-E5

E3 has 69/69 planned cases terminal: 64 successful, 3 scientific failures, and 2 unavailable dependencies.

At this observation E4 has 1,575 terminal cases and 198 waiting; E5 has 732 terminal cases and 228 waiting. Waiting means not yet terminal, not scientific failure. E4 has 1,501 successful cases, 71 scientific failures, and 3 unavailable dependencies. E5 has 652 successful cases, 50 scientific failures, and 30 unavailable dependencies. These are cell counts, not successful repetition counts for every method-condition stratum; use the per-case ledger for denominators.

No new E1 or E2 fitting was performed. E4/E5 remain active on the existing EC2. Timing comparisons are hardware- and shared-load-dependent.

## E6 correction and qualification

The former E6 dependency gate treated the E3 direct-evaluation availability as a prerequisite for each E6 ensemble. That gate prematurely recorded six primary ensemble cases unavailable. The twelve member-reference results are historical E3 evaluations, not E6 ensemble evaluations. The nine legacy unavailable outcomes and six primary cases therefore remain visible as superseded gate history; they must not be converted into E6 scientific failures or claimed as valid corrected ensemble outcomes.

An E6-v2 correction is staged but has not been deployed or launched. The revised staged finalizer now:
- skips E6-native calibration-record requirements only when no current E6-v2 tasks exist;
- requires complete native calibration evidence when current E6-v2 tasks are present, including terminal failed tasks;
- rejects a malformed authoritative registry rather than silently falling back to a public projection.

The candidate is at runtime_20261025/staging/e6_v2_reporting_20261027_revised/candidate/finalize_project.py (SHA256 ff22006425ed36314f57963959bd687be07d1c395a773e8fe6fcd5ac994589f8). The paired focused test file is alongside it (SHA256 97b50caf45df4c5a2c5c8aaade097a3af8d930bb3b00aacdf4ff108726165551). The latest change has not yet been run through the external full guard. An earlier external run reported 19 failures and 479 passes; root review requested the compatibility fixes above before another full guard. Do not describe the candidate as qualified or live.

No E6-v2 fitting or ensemble evaluation has started under the corrected design. Do not claim ensemble performance, tuning-best selection, or weight-search results.

## Remaining work and handoff

1. Root must complete the full qualification guard against the revised staged candidate and resolve any remaining regressions.
2. Only after qualification and adoption should the controller schedule the six corrected E6-v2 tasks, preserving the documented resource policy and no-duplicate-worker rules.
3. E4/E5 still have waiting planned cases. Continue to report each case as successful, scientific failure, unavailable dependency, or waiting from the current registry.
4. Complete and validate the project-wide calibration-q replay, final cross-experiment scientific report and figures, all planned-case accounting, and both delivery archives. The overall archive and laptop delivery are not complete.
5. Keep bootstrap dropped. Do not claim statistical significance, a universal winning method, or project completion from these interim counts.

## Reproduction and current-state commands

Connect using the existing approved host alias. From EC2, run:

    cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
    /usr/bin/python3 source/observe_progress.py --by-rep

The frozen E1/E2 reports and ledgers, current task registry, execution manifests, and E6-v2 staged candidate remain under the migration root. For any later handoff, use a fresh observer snapshot; the counts in this document are pinned to 2026-10-27 18:31:24 UTC.
