#!/bin/bash
set -euo pipefail
BASE=/home/ubuntu/lamost_e1_migration_20261023/e2_20261024
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
while tmux has-session -t e2_test_gate0 2>/dev/null || tmux has-session -t e2_test_gate1 2>/dev/null || tmux has-session -t e2_fidelity_reconstructed 2>/dev/null; do sleep 20; done
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python -u "$BASE/run_reconstruction_fidelity.py" >> "$BASE/reconstruction_fidelity.log" 2>&1
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python "$BASE/summarize_reconstruction.py" > "$BASE/reconstruction_finalizer.log" 2>&1
/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python "$BASE/summarize_e2_combined.py" >> "$BASE/reconstruction_finalizer.log" 2>&1
