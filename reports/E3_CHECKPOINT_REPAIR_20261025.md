# E3 selected-model checkpoint repair

Recorded UTC: 2026-10-25T07:37:30.815696+00:00

## Evidence and cause

The selected copula/synthetic/random-forest model for repetition 1 completed fitting and saved its pipeline. The subsequent final-fit process reached the 10 GiB RSS limit at 520.654 seconds. The selected tuning trial had already succeeded at a 4,178,128 KiB peak. The saved pipeline timestamp precedes termination by eleven seconds.

Code inspection found that the final-fit process retained the trained forest while loading another complete copy for validation. The exact stack at termination was not sampled. A separate single-copy check of the saved pipeline passed under the unchanged 10 GiB and 600-second limits: 7,583,592 KiB peak RSS in 16.489 seconds. It verified the selected parameters, seed, 400,000 fitting examples, class order/counts, training IDs/X/y hashes, six features and fitting-only preprocessing. No model fit, prediction or scoring was performed by that check.

The pipeline SHA-256 before and after validation and publication is 0ff121fa7af641e1dc1169bb2426147da03326eb2d2162c8906740840ef58c1e.

## Repair and retained evidence

The engine releases the original in-memory fitted object and fitting arrays before reload validation. It also records fitting/serialization/validation progress before publishing. Parameters, tuning domains, trial counts, seeds, roles, score conventions, resource limits and frozen E1 sources did not change.

The existing exact selected pipeline was recovered without retraining or retuning. All ten original tuning slots and the original source study database were preserved. The invalid post-save validation event is retained as operational overhead, separate from scientific resource-feasibility failures.

The GMM/synthetic/random-forest search was interrupted for maintenance after its first completed trial. Trial 0 genuinely reached the RSS cap during fitting and remains a scientific policy failure. Pending trial 1 resumed with its original number and identical parameters. No completed trial was repeated and no replacement trial was added.

A missing duplicate class-count/training summary in the checkpoint-resume result was completed from the independently validated pipeline and source data. The original summary and correction receipt are retained. Actual model/prediction bytes did not change. The original final training-only duration was not recorded before termination; it remains unknown rather than being inferred from total phase time.

## Validation and remaining work

All 24 runtime tests passed after the patch. A separate tiny-fixture comparison verified unchanged fitted predictions, parameters, seeds and preprocessing. The incremental artifact audit at 2026-10-25T07:35:07.882137+00:00 checked 45 fit/generation artifacts with 0 issues.

The controller resumed durably, with at most two fitting workers. This incident resolution is not completion of E3 or of the six-experiment project. Read current status and actual process identities before resuming; do not infer liveness from this document.
