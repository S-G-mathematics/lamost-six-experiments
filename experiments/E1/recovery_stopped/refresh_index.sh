#!/usr/bin/env bash
if test -f /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json; then exit 0; fi
set -euo pipefail
while tmux has-session -t recovery_nonarf_queue 2>/dev/null || tmux has-session -t recovery_support_then_arf_queue 2>/dev/null || tmux has-session -t recovery_small_arf_standby 2>/dev/null || tmux has-session -t recovery_nonarf_finalizer_standby 2>/dev/null; do
  /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/build_recovery_index.py >> /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/index_refresh.log 2>&1
  sleep 120
done
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/build_recovery_index.py >> /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/index_refresh.log 2>&1
