#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/lamost_e1_migration_20261023/project
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=benchmark/.deps
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u -m benchmark.experiments --experiment 1 --output /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_1000_rep1/results --baseline-dir /home/ubuntu/lamost_e1_migration_20261023/project/lamost_baseline --budgets 1000 --repetitions 1 --rep-start 0 --methods arf --seed 271828 --trial-timeout 600 --memory-limit-gib 10 --resource-profile native8gib8cores --prediction-chunk 50000 > /home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/arf_1000_rep1/run.log 2>&1
