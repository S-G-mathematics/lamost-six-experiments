#!/usr/bin/env bash
set -euo pipefail
cd /home/ubuntu/lamost_e1_migration_20261023/project
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/run_e2_fidelity.py --all-reference > /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/reference_run.log 2>&1
