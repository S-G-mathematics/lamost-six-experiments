import subprocess
import sys
from pathlib import Path
base = Path(__file__).resolve().parents[1]
cmd = [sys.executable, "-m", "pytest", "-q",
       str(base / "tests" / "test_storage_allowance_1gib.py"),
       str(base / "tests" / "test_storage_allowance_binding.py")]
raise SystemExit(subprocess.call(cmd, cwd=base))
