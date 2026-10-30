#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
cd /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025
exec /home/ubuntu/lamost_e1_migration_20261023/venv/bin/python /home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/source/cold_auto_compaction.py --storage-codec-policy reversible-xz-v1-payload12 --archive-io-profile bounded-5400-codec4gib64-payload12
