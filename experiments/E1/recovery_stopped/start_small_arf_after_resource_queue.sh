#!/usr/bin/env bash
if test -f /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json; then exit 0; fi
set -uo pipefail
while tmux has-session -t recovery_support_then_arf_queue 2>/dev/null; do sleep 30; done
cd /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_minclass_variant
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=benchmark/.deps
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u -m benchmark.experiments --experiment 1 --output /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_minclass_variant/pilot_results --baseline-dir /home/ubuntu/lamost_e1_migration_20261023/project/lamost_baseline --budgets 100 --repetitions 1 --rep-start 0 --methods arf --seed 271828 --trials 1 --trial-timeout 600 --memory-limit-gib 10 --resource-profile native8gib8cores --prediction-chunk 50000 > /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_minclass_variant/pilot.log 2>&1
if test -f /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_minclass_variant/pilot_results/e1/rep_1/n_100/arf/complete.json; then
  cd /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_minclass_variant
  /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/run_small_arf_queue.py > /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/small_arf_queue.log 2>&1
fi
