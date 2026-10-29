# Qualified ET4 and archive profile update

Observed/deployed UTC: 2026-10-29T06:31:00+00:00. This is an operational source update, not a new scientific result.

The current portable candidate passed 776 tests (3 warnings and 85 subtests) in the bounded qualification recorded at 2026-10-29T06:21:55.258318+00:00. The live source map contains 19 scientific/runtime source files; the installed archive policy has an 11-file source map. The policy sets a 4 GiB maximum batch, 8 GiB encoded temporary-output bound, 5,400-second archive child wall limit, 5,460-second wrapper limit, one native helper thread, and the documented host/reserve constraints. These are qualified resource/admission bounds. Production codec throughput and scientific speedup remain unmeasured.

At the 06:31 UTC status observation, the archive handoff was paused, no scientific workers were active, and E4/E5 had 220 planned cases waiting (88 E4, 132 E5). The latest consolidated scientific tables and figures in this repository remain tied to the 05:02 UTC snapshot; no later result is claimed here.

Provenance discrepancy: the source/test SHA index lists tests/test_codec_overlap_controller_harness.py at b244302b1f743076adc0244544dff71216b0adca3c6724e7da387ec13b98f714, while the qualified portable test bundle lists the current file at 71c4a2ad53f2eeadab067819f3cf8eff8f829a7caf08a68c445f3103ecbb6c36. The pass receipt binds the tested bundle. The Git source copy uses the qualified bundle portable SHA; the original index is preserved unchanged.

Raw logs, private process receipts, models/FITS, datasets, and prediction arrays are excluded. E1/E2 remain frozen; recovery stays separate; the project remains interim and incomplete.
