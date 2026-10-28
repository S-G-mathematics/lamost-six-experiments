# Reproducing this scoped integrity check

This is a preserved one-shot audit of the 25 successful physical E4 direct-ARF evaluations selected at 2026-10-27T11:21:04.581402+00:00. Its 45-case coverage snapshot has 28 successes (including three control aliases), two recorded evaluation timeouts and 15 pending cases. Later queue progress does not change this snapshot.

The initial invocation on the original EC2 was:

    /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python runtime_20261025/reports/e4_arf_saved_outcome_audit_20261027/audit_e4_arf_saved_outcomes.py

The driver deliberately refuses to overwrite an existing report. Do not remove the report or invoke its internal child mode directly. The exact driver, existing Auditor.evaluation_audit API, pinned guard and all selected input hashes are recorded in ROOT_REVIEW.json. The actual frozen-plan file SHA and its distinct canonical payload SHA are recorded in the audit report.

The original frozen input plan and raw guard/preflight evidence remain in runtime_20261025/logs/operational/e4_arf_saved_outcome_audit_20261027/ on EC2. They contain private operational state and are excluded from public delivery. The public report and root hash index retain the scientific case keys, model/outcome/dataset hashes, validation scope and sanitized resource measurements.

A fresh recheck must use a new isolated output directory, preserve this evidence, verify the recorded inputs and source versions, and apply the same existing validation API to these frozen 25 keys under the documented resource gate. The current one-shot driver is evidence of the original execution, rather than a resumable project controller. The main RUN_RESUME_REPRODUCE.md governs the overall project; inspect actual processes before operational resumption.

This check did not deserialize fitted models, run inference or independently replay calibration quantiles. It leaves the global audit cache unchanged and does not establish whole-E4 or six-experiment completion.
