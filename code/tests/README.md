# Portable delivery tests

The selected portable suite has 112 checks in eleven explicitly listed test files. It uses runtime-relative source imports and tiny fixtures under runtime_20261025/tests/fixtures. The three public resource-review fixtures retain their original bytes and native archive member names in PORTABLE_TEST_BUNDLE.json.

Run on EC2 from the extracted archive root with the recreated Python3.12 environment:

    bash runtime_20261025/tests/run_portable_tests.sh

Set LAMOST_TEST_PYTHON to select the Python executable. The runner sets numerical-library threads to one. The selected suite does not run research experiments or read real fitted models or scientific data; cold-storage fixtures are tiny synthetic dictionaries. Other historical/integration checks archived beside it may require the original runtime artifact layout. The current controller and cold batch wrappers are included as operational companion source; tests never start a scientific worker.

The verified existing-EC2 command uses frozen scientific packages first, followed by existing plotting support:

    LAMOST_TEST_PYTHON=/home/ubuntu/lamost_e1_migration_20261023/venv/bin/python PYTHONPATH=/home/ubuntu/lamost_e1_migration_20261023/venv/lib/python3.12/site-packages:/home/ubuntu/.local/lib/python3.12/site-packages:/usr/lib/python3/dist-packages bash runtime_20261025/tests/run_portable_tests.sh

For a separate reporting environment, install the frozen core dependencies and source/reporting_support_requirements_20261026.txt, then select that interpreter. Actual versions and import order are recorded in source/reporting_support_environment_20261026.json. Scientific workers continue with their unmodified frozen environment.
