# E4 ARF saved-outcome audit

On EC2, run from the migration root with the frozen venv: /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python runtime_20261025/reports/e4_arf_saved_outcome_audit_20261027/audit_e4_arf_saved_outcomes.py

This re-snapshots current E4 direct-ARF tasks and refuses if the selected terminal scope, source, selected raw models, or resource admission differs. It calls only Auditor.evaluation_audit and never writes the global audit cache.
