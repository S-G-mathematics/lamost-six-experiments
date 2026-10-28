# Supervisor Handoff: Continue LAMOST on Existing EC2

Continue the six-experiment LAMOST project on the existing EC2 only. Do not restart from earlier counts or rerun completed work. Start by reading:

/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/reports/LAMOST_CURRENT_PROGRESS_AND_E6_CORRECTION_20261027T191454Z.md

Then take a fresh registry and actual-process snapshot using the existing approved SSH alias w7-ec2 and:

    cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
    /usr/bin/python3 source/observe_progress.py --by-rep

## State at the latest observation

At 2026-10-27 19:12:35 UTC / 2026-10-28 00:42:35 IST, the observer verified the controller and two E4 workers; it found no unverified-running registry rows. Counts were:

- Frozen E1: 674 success, 81 failure (55 resource, 26 supervisor-terminal whose manifests remained started), 10 unsupported; all 765 terminal.
- Stopped E1 recovery: 24 retry success, 10 retry failure, 2 user-stopped, 55 not attempted.
- E2 primary: 108/150 evaluated, 42 unavailable. Classical reference set: 120/120.
- E3: 64 success, 3 scientific failure, 2 unavailable; all 69 terminal.
- E4: 1,512 success, 71 scientific failure, 3 unavailable, 187 waiting.
- E5: 652 success, 50 scientific failure, 30 unavailable, 228 waiting.
- E6 historical E3 references: 12/15 successful, 3 unavailable; old six E6-v1 zero-attempt gate decisions remain superseded history.
- All six corrected E6-v2 tasks had one recorded attempt each, started 19:11:09-19:11:48 UTC, then became operationally_invalid before posterior generation with the common error: GMM feature order missing or mismatched. They have no valid outcome. Preserve these attempts as implementation-defect evidence; do not count as scientific failures or unavailable model results. Root verified there were no E6 workers at the snapshot.

## Authorization and frozen work

Continue the authorized E3-E6 project autonomously. Do not run further E1/E2 fits or mutate their ledgers. Keep recovery separate from frozen E1. Bootstrap remains dropped. Preserve E2's 31 reconstructed accuracy differences, 210 low-precision flags and four complete descriptive correlation strata; do not claim a general fidelity-performance relationship. Do not present the project as having an untouched prospective test set: E1/E2 test outcomes were already observed.

Use explicit cell statuses and actual repetition denominators. Waiting is not failure. Keep scientific failures, unsupported cells, unavailable dependencies, operational invalidity and pending cells separate. Do not increase fixed scientific resource/time limits to force completion.

## Current E6-v2 authority and next action

The amendment is formally published and deployed. Bind to these exact artifacts before proceeding:

- controller SHA256: b9465eb5ae73991abe7551dee7b8f131feefecc3dd3656917d019b76457aa7ca
- qualified freeze SHA256: 203e51bbc6f05d4a1795644abdd321ca6a196707d18811ab146914247a3b90c5
- overlay SHA256: 54540cfcff47d32878184f7b9ff0a061753cb3d61cabff290ca6c907d38aadce
- effective amendment receipt: runtime_20261025/manifests/E6_V2_EFFECTIVE_AMENDMENT_RECEIPT_20261028.json

The previous hard gate incorrectly required E3 direct evaluation results as E6 ensemble prerequisites. E6-v2 separates fit dependencies from member evaluation references. Keep the old six zero-attempt decisions in superseded history; the 15 member-reference rows are historical E3 results, not E6 ensemble scores.

Core is diagnosing the feature-order mismatch. Review the live model pipeline metadata and the published overlay/task contract. Fix the cause in the owned E6-v2 implementation path, preserving the source freeze, model identities, and protocol. Validate the proposed change and get the required review/qualification before adoption. Preserve all six operationally invalid attempts. Once the fix is qualified, supersede only those six implementation-defect attempts with explicit provenance and resume the same six planned E6-v2 cells once. Do not refit or retune E1/E2, do not expand the resource policy, and do not retry ordinary terminal scientific timeouts.

## Continue E4/E5 and finalization

Continue the remaining 187 E4 and 228 E5 waiting cases under the recorded controller policy. Coordinate shared-host resources with the actual current process inventory; do not disturb Harbor. Validate each completion incrementally.

Complete project-wide native calibration-q replay and conformal validation after valid models/evaluations exist. The E3 saved-results audit has useful quantified findings, but it flags missing prior-test-exposure disclosure in the E3 report; correct that in final reporting. Report predictive performance, resource feasibility, fidelity and artifact reproducibility separately. Include per-class coverage with marginal coverage and prediction-set size.

Then refresh the complete planned-denominator reports, availability ledgers, figures and cross-experiment synthesis. Create and verify the full EC2 archive and compact reports/tables/figures package; only then transfer the compact package to the established laptop directory. Record member manifest, ZIP CRC, byte size and SHA256. Do not claim project completion until all final gates and archive checks pass.

The qualified portable test receipt records 505 passing tests. Earlier prepublication tooling failures are operational history, not scientific outcomes. Preserve receipts and use a fresh observer snapshot for every later progress update.
