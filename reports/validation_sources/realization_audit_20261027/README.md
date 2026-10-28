# E4/E5 saved-realization validation

The guarded audit checked all 42 altered E4 cohorts and all 18 feature-noise/missingness E5 realizations. It found zero issues in the stated invariants. It loaded no fitted model, made no predictions and changed no scientific data or queue.

Qualification: ../../engineering_audits/E4_E5_REALIZATION_GAP_GUARDED_QUALIFICATION_20261027.json
Actual result: ../../engineering_audits/realization_guarded_20261027T172000Z/E4_E5_REALIZATION_GAP_AUDIT_20261027T172001Z.json

The bounded execution used 1 GiB address-space and sampled process-tree RSS limits, a 120-second wall/CPU limit, one native thread and nice 19. It completed in 8.434 seconds at 172,523,520 bytes peak sampled RSS, exit 0, without termination. The detailed report lists input/artifact hashes, role-cache hashes before/after, scope and limitations.

An earlier unguarded preliminary checker compared permutation-ordered row indices with sorted mask positions, causing 18 false positives, then failed while rendering Markdown. Its raw receipt and qualification-status companion are preserved. They are not a scientific failure count or a valid dataset-integrity disposition. The corrected checker compares mask membership independently while preserving row/feature/perturbation alignment, and the subsequent guarded audit supersedes that preliminary checker attempt.

This does not validate model training, predictions, calibration thresholds or all E4/E5 results. Those remain subject to final artifact and native-calibration audits. Stored E4 IDs support membership nesting checks; historical within-class permutation order is not independently recovered by this audit.
