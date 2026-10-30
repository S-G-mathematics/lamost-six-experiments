# Successful evaluation artifact coverage (point-in-time)

Captured 2026-10-30T09:59:05.478433+00:00 from one read-only registry transaction. The index maps all 2,425 successful E3-E6 evaluation, alias, and ensemble records to per-task artifact metadata. It includes 121 successful aliases as separate task rows with their dependency task keys. It is not a completion claim for all 2,823 planned cases.

## The 28-count difference

The prior Git manifest counted 2,397 destinations whose names ended in evaluation.json. The current registry has 2,425 successful task records. Before this refresh, 2,376 of their evaluation source paths were already represented; 49 successful task source paths were missing. The 2,397 manifest count included 2,377 rows mapping to 2,376 distinct successful task sources (one duplicate mapping) and 20 unrelated evaluation-named destinations. Thus the net difference is 49 missing successful outputs minus 20 unrelated entries and one duplicate mapping, or 28. The full row mapping and artifact hashes are in the CSV and summary.

## Metadata added

This refresh adds 165 small per-cell JSON metadata files: 49 evaluation, 57 validation, 56 result, and 3 alias-reference records. Source and destination hashes are in ADDED_METADATA_FILES.csv. In 56 eval_result.json records, only the absolute project prefix in task.artifact_dir was changed to the project-relative runtime_20261025/... path; scientific fields remain identical. Their original source hashes are retained in the crosswalk.

## Scope

The planned denominator remains 2,823. The summary records current failures, unavailable, user-stopped and pending outcomes. No models, FITS files, raw training data, NumPy arrays, credentials, or private operational receipts were copied. The separate payload catalog remains the evidence for array release-member coverage.
