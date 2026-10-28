# E5 set-size paired-table metadata QA

A read-only independent cross-check at 2026-10-27T08:46:05Z passed against saved CSV outputs and registry metadata. It found 378 paired rows and 126 condition summaries; all summary groups have n=3. There were zero mismatches in pair identity, recall, coverage, set size, means, sample SDs, or n. The reporting source hash remained unchanged across the check (d7f8d302fad59310f4c101b27a23575a66012b612f376df79fb277b02915cf19).

No models, NPZ files, prediction arrays, fitting, inference, or calibration were accessed. This confirms the paired-table reporting values only; it does not establish full E5 grid completion or global calibration-q replay.

QA JSON SHA-256: 7021592f5e8c3c2f071184caace32aba416fe349095b3d7970c80a471342e857. Paired rows CSV SHA-256: 4c71ffb7255c246485df542ca233ec7c30b4dddba3b6bf96c1ef120014966bc3. Summary CSV SHA-256: e51ee8922e9ea3581587a948243a56bcbd3571b0f1986cae5d17ffbf9a97656b.
