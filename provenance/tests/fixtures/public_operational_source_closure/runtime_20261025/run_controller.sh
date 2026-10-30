#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
exec /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u source/controller.py run >> logs/controller.log 2>&1
