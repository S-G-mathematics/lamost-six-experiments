#!/usr/bin/env bash
if test -f /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json; then exit 0; fi
set -euo pipefail
while tmux has-session -t recovery_nonarf_queue 2>/dev/null; do sleep 60; done
exec /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/run_nonarf_finalizer_queue.py > /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/nonarf_finalizer_queue.log 2>&1
