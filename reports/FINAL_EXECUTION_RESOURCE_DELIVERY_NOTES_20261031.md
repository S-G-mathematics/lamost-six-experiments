# Final execution, validation and delivery notes

## Final E5 dispatch

All 6,270 planned DAG nodes are validated terminal. The 2,823 E3–E6 scientific cases comprise 2,438 successful references (including 12 reused E6 member references), 127 scientific failures, 90 unavailable dependencies, and 168 user-stopped cases. No planned case remains queued. E6 has zero successful primary ensemble test evaluations.

The final three nodes were E5 repetition 1 Extra Trees: the 10% missingness evaluation, and the 20% missingness fit and evaluation. The user explicitly directed completion despite the operational disk-output guard and allowed local D: execution. They were completed on the original EC2 using the unchanged frozen worker definitions and source, not by refitting E1/E2. There was one worker at a time; the 10 GiB process-tree cap, 600-second scientific phase limit, selected clean configuration, data roles, seeds, 50,000-row chunks and conformal rules remained unchanged.

This one-off dispatcher used the ordinary controller admission, resource and artifact-validation functions under the exclusive project lock. Its storage policy retained a 6 GiB actual working-space floor while deferring the additional per-task output estimate and future result-array restoration reservations. This was a separate operational amendment at the user's direction; it must not be described as identical to the previous storage policy. No ordinary scientific failure was retried.

## Result-array restoration

After scientific execution ended, 2,132 retired result-array inode groups (4,264 canonical/attempt paths, 5,595,808,572 payload bytes) were restored from the existing verified GitHub assets. The postexecution restoration used a separately recorded 3 GiB floor. Asset batching retained the global missing-payload reserve, exact whole-asset and member SHA-256/CRC checks, modes, atomic publication and hardlink checks. The approved parent-index row order was preserved.

Every restored group was independently rechecked before the original guardian was stopped. That guardian's old recovery loop could not accept an externally completed nonempty index; its historical error state was retained, and external restoration completion is evidenced separately. No incomplete restore was marked successful.

## Validation and information history

The installed publication bundle passed 863/863 engineering tests. Its fingerprint is 1e68ddc3d21dae8decadcc602dcfcd84e42f34bdf822df47c50bdb962c2a4f49. Private watchdog enable state, ownership nonces, credentials and private process/cleanup receipts are excluded from public delivery.

Engineering-test success and terminal scientific execution do not themselves certify the global artifact and calibration-replay audit. That audit is required separately; consult its final receipt and the final report's bound review proof for the actual outcome. Calibration replay recomputes the existing finite-sample threshold from saved permitted calibration rows and selected models. It is not bootstrap, retuning, another scientific fit or test-based model selection.

E1/E2 and earlier E3–E6 test outcomes had already been observed. The final report must state that information history. E1 remains frozen at 674 successful, 81 failed and 10 unsupported outcomes; the stopped recovery supplement stays separate. E2's primary grid remains 108/150 evaluated with 42 unavailable cases; its reconstruction differences, 210 low-precision class flags and four complete five-family correlation strata remain limitations.

## Delivery scope

The user's latest requested public delivery is one GitHub repository containing appropriate experiment code, detailed scientific logs, tables, figures, result metadata and available evaluation arrays. Fitted models/FITS, credentials and private operational receipts are excluded from GitHub. Model artifacts and the existing frozen/working archives are retained on EC2; the failed unselected partial has the documented lossless laptop backup.

The existing 81,921,411,531-byte working archive remains a BUILDING snapshot, not a validated final overall archive. Do not relabel it as final. Any final full-archive result must have a distinct actual verification receipt. A large laptop transfer was cancelled as operationally impractical; no successful full-copy claim is made. Public results delivery must not be confused with full historical model reproducibility or a completed private full archive.
