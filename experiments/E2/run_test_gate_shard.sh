#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
exec /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/validate_reconstruction.py "$1" > /home/ubuntu/lamost_e1_migration_20261023/e2_20261024/test_gate_shard_"$1".log 2>&1
