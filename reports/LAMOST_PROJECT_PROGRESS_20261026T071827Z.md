# LAMOST six-experiment execution report — 26 October 2026, 12:48:27 IST

This is a current execution handoff and progress report. The complete project is not finished. E4/E5 still have planned work, and the final project-wide model/outcome audit, exact final figures, review gate and delivery archives remain pending.

## Verified host and authoritative state

All scientific work remains on the existing EC2 through approved SSH alias w7-ec2, migration root /home/ubuntu/lamost_e1_migration_20261023. The actual DMI identity is i-095641a281a4038b9; the controller is kernel-verified against its owner PID/start ticks and script. The host has16 logical CPUs and approximately30.81GiB RAM; current available RAM is 27.11GiB and free disk is 66.30GiB. These are observations at the timestamp above, not guarantees of future headroom. No infrastructure was provisioned or changed, and Harbor was not modified.

The live SQLite registry has6,270 execution/dependency tasks. It contains2,823 planned E3–E6 scientific evaluations. Fit dependencies, generated-data tasks and helper tasks do not count as completed scientific evaluations.

## Current six-experiment coverage

| Experiment | Planned cases | Successful/evaluated | Failed | Unsupported/unavailable | Pending/active | Phase |
|---|---:|---:|---:|---:|---:|---|
| E1 frozen | 765 | 674 | 81 | 10 | 0 | Frozen benchmark finalized; preserved |
| E2 primary | 150 | 108 | n/a | 42 | 0 | Reporting finalized with incomplete primary coverage |
| E2 classical references | 120 | 120 | 0 | 0 | 0 | Separate reference analysis |
| E3 | 69 | 64 | 3 | 2 | 0 | Execution terminal; final project audit/report pending |
| E4 | 1773 | 1192 | 42 | 3 | 536 | Executing dependency fits and evaluations |
| E5 | 960 | 613 | 27 | 23 | 297 | Executing dependency fits and evaluations |
| E6 | 21 | 12 | 0 | 9 | 0 | Execution terminal; final project audit/report pending |

The separate E1 recovery supplement remains stopped early at the user's request:24 successful retries,10 retry failures,2 user-stopped partials and55 not attempted. These91 records remain separate from frozen E1 and are not inserted into its results.

E2's108 primary paired evaluations comprise19 original saved fits and89 reconstructed fits. Its120 classical references are a separate analysis. The full E2 audit records228 evaluated cells,43 original/185 reconstructed fits overall,1,596 class reports,210 low-precision flags and zero recorded integrity errors. There are4 complete five-family strata out of30; the other26 do not replace the primary analysis. The31 reconstruction accuracy differences remain disclosed, maximum absolute balanced-accuracy difference3.1739351391335546e-5. No42-case resource-relaxed completion campaign was started.

## Actual repetition counts

Each row counts successful scientific evaluations within the repetition; it is not a claim that every method has three successful repetitions.

| Experiment | Repetition | Successful evaluations | Scientific failures | Unavailable | Pending/active |
|---|---:|---:|---:|---:|---:|
| E3 | 1 | 22 | 1 | 0 | 0 |
| E3 | 2 | 20 | 1 | 2 | 0 |
| E3 | 3 | 22 | 1 | 0 | 0 |
| E4 | 1 | 411 | 14 | 1 | 165 |
| E4 | 2 | 404 | 14 | 1 | 172 |
| E4 | 3 | 377 | 14 | 1 | 199 |
| E5 | 1 | 199 | 9 | 1 | 111 |
| E5 | 2 | 206 | 9 | 21 | 84 |
| E5 | 3 | 208 | 9 | 1 | 102 |
| E6 | 1 | 4 | 0 | 3 | 0 |
| E6 | 2 | 4 | 0 | 3 | 0 |
| E6 | 3 | 4 | 0 | 3 | 0 |

Final tables will show per-method/route/condition actual repetition counts and matched paired differences. Missing repetitions remain visible; conditional-on-success results will not be presented as complete-grid performance.

## Verified live work

| Verified actual worker | Kind | Admission reservation |
|---|---|---:|
| e4/rep_1/fit/treatment/random_forest/A_tenth_smote | fit | 5 GiB |

Every listed worker's actual PID/start ticks, script/request argument and frozen request definition were checked. Seeds, trial counts, search domains, roles and scientific task definitions are unchanged. The table describes this observation; it is not a persistent liveness promise.

The old two-worker cap has been removed. The controller uses measured CPU/RAM headroom, a CPU-derived ceiling of14 workers, one numerical-library thread per worker, a six-GiB host/Harbor reserve, two-GiB commitment-growth margin and eight-GiB admission floor. Current admissions reflect those constraints. The scientific hard worker limit remains10GiB; tuning trials and final-fit/generation/calibration/evaluation phases remain600 seconds, with30-second termination grace. These later-experiment settings differ from frozen E1's180-second/6GiB policy.

## Work completed in this continuation

1. Reconnected to the existing EC2, checked actual controller/worker identities, registry counts, RAM/disk and owned process inventory. A process inventory found no unknown/orphan runtime workers at its observation; later liveness continues to be checked against the kernel.
2. Re-read frozen E1's765-row CSV and matched all classifications and all674 saved metric triples against the validated report. Its81 failures remain55 resource failures plus26 supervisor-terminal cells with incomplete manifests; the10 support/unsupported cases remain distinct. E1CSV SHA-256: 52d056aa2dc98f3721fb88a611bb4fa76aba74562751afc87b263f478c78b456.
3. Rechecked E2's228-cell integrity record,42 missing-primary rows and1,596 class-report rows. E1/E2 fitting remained stopped; bootstrap remains dropped.
4. Completed the first real cold-model transaction and two bounded batches. Seventeen completed RF models are retained byte-for-byte in the building overall ZIP. Each producer and all transitive consumers were terminal; hardlink ownership, matching process absence, source hash, ZIP CRC/member hashes and durable manifest/journal state were verified before replacing native aliases. Fresh readers resolve every archived alias. No fit or test inference was used for archiving.
5. The current building archive is packages/LAMOST_ALL_EXPERIMENTS_BUILDING_20261026.zip, 1,217,009,037bytes, SHA-256 3bad81c5e43efd006bf4c16263314422d22f78f055b624e8dff3aa47471b6d1d. It is a verified17-model prefix, not the final overall delivery. ZIP_STORED preserves the original compressed joblib bytes and avoids a second final-package model copy; it does not itself reclaim net disk space.
6. Audited the repeated memory-reclaim transition. Two historical reclaim requests were3.2seconds apart before the first recovery record; exact simultaneous historical PID liveness was not retained. The controller now defers a further noncritical interruption while a currently verified parent or orphan phase remains within its existing30-second TERM grace. Under6GiB critical pressure, reclaim remains active. Existing host reserves and scientific limits were preserved.
7. Applied prospective, artifact/hash-gated admission estimates:6GiB for matching80k ARF E4 tuning/E5 fixed fits;5GiB for weighted80k RF;5GiB for permitted nonweighted RF restoration fits through84,310 rows. The weighted estimate conservatively uses5GiB although the raw audit recommended4. The old6GiB fallback remains capped at82,394 rows; missing/tampered extension evidence returns larger fits to the default. Prior attempts retain their recorded profiles; observed reservation overruns still promote to10GiB and pause admissions.
8. The controller handover signaled only the verified controller. Existing model workers were untouched, all previous terminal task results were preserved, and all preexisting request files retained their exact hashes. Frozen plan SHA remains 42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb. Current controller SHA is 13f914122345bd4f24fbed7b5ab0a4439a02ab869248f7b5db9cb1d8bda9889f; admission helper SHA is 44bdeef607dac4937a25c33b711d0f42375d6094845c83718e61ad0df7235e5b.
9. Extended the full-archive allowlist to include the third exact-byte public resource audit; unrelated staging/private process receipts remain excluded. The original raw audits were preserved.
10. Published and ran110 portable engineering checks in a relocated source/tests/fixture tree. All110 passed, including the controller grace/attempt-preservation checks and bounded archive planning. The first test attempt had108 passes and2 plotting-dependency failures; that evidence is preserved. The corrected test environment kept Python3.12.3/NumPy2.3.5/sklearn1.8.0/SciPy1.17.0/joblib1.5.3 first in import order and used existing Matplotlib3.11.2 support afterward. Scientific environment files were not changed. Exact support dependencies are saved in source/reporting_support_environment_20261026.json and reporting_support_requirements_20261026.txt.

## Scientific and provenance boundaries retained

Frozen E1 remains674 successful +81 failed +10 unsupported, with no new E1 fits, recovery queue restart, ARF min-leaf variant or saved-pipeline finalizer. The recovery study is stopped early, not fully completed. Historical E1 models/per-test-row prediction arrays omitted from compact migration remain unavailable unless already independently present; they have not been fabricated or silently refitted.

The seven documented auxiliary tuning-history discrepancies across10k GMM and30k CART/linear-SVM remain disclosed. Exact original complete auxiliary histories remain unavailable. Existing verified completion metrics are retained, with conditional-on-success and hardware-dependent timing limitations.

E2 original/reconstructed provenance, exact-match flags,31 mismatches and210 low-precision class flags are preserved. The four complete primary correlations are descriptive; no general fidelity–classification relationship or significance is claimed. Available-only/reference analyses remain separate.

E3–E6 use their frozen plans and information boundaries. Fitting/tuning/calibration/test roles remain distinct; IDs and audit metadata remain excluded from the six predictors. Existing E1/E2 test outcomes were already observed; later plans were frozen before their new test evaluations. No bootstrap, test-based selection, extra restoration/corruption arms or success-forcing scientific retries were added.

The72 later scientific-case failures currently recorded are direct KDE evaluation-phase timeouts: E3 three, E4 forty-two and E5 twenty-seven. Operational interruptions/checkpoint recoveries remain separate and do not count as these failures. E6's unavailable five-member comparisons remain unavailable; no fabricated ensemble weights or partial ensemble is presented as the primary five-member result.

## Remaining required work and durable continuation

Continue the single owned controller's E4/E5 queue; do not launch competing queues or duplicate workers. Pending cells are scientifically required, not optional variants. Actual progress/checkpoints remain on EC2; tmux, the ownership lock, five-minute watchdog and atomic master-index exports provide recovery independent of the chat window. Ordinary terminal timeouts/unsupported searches remain terminal; only evidenced operational interruptions may resume within the recorded limit.

After all planned cases are terminal, run the cold-aware full selected-model and outcome audits, regenerate the final condition/repetition tables and scientific figures once, inspect exact final figures and numerical claims, finalize the E1/E2/later/cross-experiment report and limitations, and pass the immutable candidate review gate.

Then complete the same building overall archive under packages with a member manifest, verified CRC/byte size/SHA-256, and create the small reports/tables/figures ZIP. Copy the small ZIP to the laptop handoff directory and verify its hash. Stop only project-owned workers/watchers after successful completion; preserve Harbor and all unique artifacts. No final project archive, final review pass or complete-project marker is claimed now.

Current proof: runtime_20261025/reports/engineering_audits/ACTUAL_PROGRESS_AND_NEW_PROFILES_20261026T071827Z.json; SHA-256 24d40c0193291026111b2a48d2b77071852f37d5918751294c4edf80e58e24b3.
