# Supervisor resume prompt

You are resuming the already-authorized LAMOST six-experiment project on the existing EC2 instance. Continue autonomously; do not ask for routine permission to move between experiments. Do not claim the project is complete until the frozen E1/E2 caveats, E3-E6 results, calibration validation, final reports, and verified archives are all handled.

Start by checking current EC2 state. This prompt records a fresh observer at 2026-10-28 02:05:52 UTC / 07:35:52 IST, but all process and storage state can change. Use the approved SSH alias w7-ec2 and run the read-only observer:

    ssh w7-ec2 'cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025 && ../venv/bin/python source/observe_progress.py --by-rep'

At that observation the controller was verified, with SHA-256 d34bf3db889ee7c642cf28d079cbeb32f27fb772584163f497e78499a994d5ac, freeze SHA-256 07e8a2abfcd7ad0e7348c880f845e39f9ce4e88de0e2957d317d224f72ac2b2b, 6,270 registry tasks, no verified or unverified model workers, 28.75 GiB available RAM, 34.65 GiB free disk, and both storage/admission holds. The fresh storage estimate was backoff: free space was 3,108,928,496 bytes below the current controller minimum. Do not clear either hold manually.

The last process-specific archive observation available here is root's 02:04 UTC verification of auto_storage_20261028T015304Z_dbcc142b: wrapper and child identities verified, child observed creating a backup, with no scientific fit active. The 02:05:52 observer does not verify storage-process liveness. Recheck actual argv, start ticks, UID, request, hold binding, and successful transaction receipt before relying on it. Do not start a second archive writer or controller. A prior prewrite wrapper stopped at a stale source-pin check before archive or scientific mutation; the corrected pin was qualified. Preserve that as an operational incident only.

## Frozen status to preserve

- E1 frozen: 765/765 terminal, 674 successful, 81 failed (55 resource, 26 supervisor-terminal whose manifests remained started), and 10 unsupported. Never rerun or overwrite E1.
- E1 recovery supplement: 24 successful, 10 failures, 2 user-stopped partial cells, 55 not attempted. Preserve separately and do not call the study complete.
- E2: primary 108/150 evaluated, 42 primary cases unavailable; classical references 120/120 evaluated. Across both groups there are 228 evaluated cells and 1,596 class reports, zero integrity errors, 210 low-precision class flags, 31 original/reconstructed accuracy differences, and 4 complete five-family correlation strata. Keep E2 explicitly incomplete in primary coverage and preserve reconstructed provenance.
- E3: 69 terminal; 64 successful, 3 scientific failures, 2 unavailable dependencies.
- E4: 1,533 successful, 71 scientific failures, 3 unavailable dependencies, 166 waiting of 1,773 planned.
- E5: 697 successful, 50 scientific failures, 78 unavailable dependencies, 135 waiting of 960 planned.
- E6: 21 ledger cases; 12 successful historical member references, 3 unavailable references, and 6 primary ensemble cases with 0 successful test evaluations, 3 timeouts, and 3 unavailable dependent modes. The earlier feature-order attempts are preserved as operationally invalid/superseded. Do not count those as additional scientific failures.
- The independent E6 tuning audit validated all six saved tuning-mode artifacts and candidate ledgers. It is tuning-only; it produced no test metrics and no successful ensemble claim.

The 02:05:52 per-repetition counts and all details are in LAMOST_INTERIM_STATUS_20261028T020500Z.md in this directory. Re-observe before making decisions or reporting current values.

## Resume the authorized scientific work

The root controller owns the registry and queues. Do not run duplicate controllers, manual workers, or extra model fits. The latest estimate reports 296 fit cases and 301 evaluation cases remaining across E4/E5, including three aliases; current observer reports 166 E4 and 135 E5 waiting. Wait for the current verified archive operation to finish successfully and the controller storage estimate to permit new admissions, then let the existing controller resume planned cases. Maintain at most two fitting workers, preserve the later-experiment default 10 GiB / 600-second policy and any qualified narrowly scoped task-specific admission profile, preserve frozen search budgets, and do not retry ordinary terminal failures. E1 remains under its separate frozen 6 GiB / 180-second policy. If the raw storage/archive operation fails or is ambiguous, preserve evidence and keep science admissions blocked until the storage owner resolves it.

The archive baseline before the in-flight operation was 37,889,733,875 bytes with SHA-256 prefix 5ec1fb. It is an intermediate BUILDING archive, not final delivery. The 8 GiB / 64-group packing policy is staged only; do not activate it or change scientific resource caps without the recorded qualification and freeze process.

Do not restart E1 recovery, start more E2 generation/evaluation work, run bootstrap, expand ARF/KDE resources, or substitute recovered fits into frozen E1/E2. E3-E6 remain authorized under their recorded designs. Keep all failures and unavailable dependencies visible. Do not infer any model timeout was caused by archive I/O without direct evidence.

## Reporting, validation, and delivery still required

1. Finish waiting E4/E5 planned work through the existing controller. Validate every completed artifact, keep successful repetitions and terminal failures distinct, and do not call queued rows failures.
2. Finish valid E6-v2 work where fixed dependencies/policies permit. Preserve the three terminal test timeouts and dependent unavailable cases unless a separately justified implementation defect is evidenced. The tuning audit is not a reason to rerun test inference.
3. Complete global calibration-q replay validation for all included successful evaluations before final conformal claims.
4. Refresh final planned-denominator tables and figures, per-class metrics, class histograms/corruption realizations, paired comparisons with matched actual repetitions, costs, resource feasibility, unavailability reasons, and E1/E2/E3/E6 findings. Keep primary and exploratory analyses separate. Bootstrap is dropped; do not add confidence intervals, significance claims, or universal method claims.
5. Preserve limitations: compact migration omitted historical fitted pipelines and per-test-row predictions (some original fit artifacts remain available); seven auxiliary tuning-history discrepancies remain; E3 real-only RF rep 1 lacks fit_publication.json though its selected fit and scientific outcome remain supported. Do not fabricate historical artifacts.
6. Apply and validate the staged finalizer collection-history correction before packaging. The existing large BUILDING archive is not a completed archive.
7. Produce one verified full EC2 archive under the existing packages directory and one compact reports/tables/figures ZIP. Include manifests and exact CRC, byte size, and SHA-256. Copy the compact ZIP only to the established laptop handoff directory after verification.
8. Stop project-owned workers and watchers cleanly when the full project is complete. Leave Harbor untouched.

No full project completion claim is justified now. The current missing work is finite and explicitly authorized. Ask for supervisor review or additional directions only after preserving this state and continuing all independent authorized work; do not frame routine continuation as needing permission.
