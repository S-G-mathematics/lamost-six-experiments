import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1]
STAGED = RUNTIME / "source" / "controller.py"
sys.path.insert(0, str(RUNTIME / "source"))
spec = importlib.util.spec_from_file_location("admission_hold_staged_controller", STAGED)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

def run_fixture(tmp_path, initial_hold=False, hold_after_first_admit=False, hold_during_candidate=False):
    c.R = tmp_path
    c.STOP = False
    task = {"key": "fixture/fit", "kind": "fit", "method": "logistic", "status": "planned", "attempts": []}
    tasks = {task["key"]: task}
    counts = {"checked": 0, "emergency": 0, "candidate": 0, "admit": 0, "export": 0, "checkpoint": 0, "owner": 0}
    marker = tmp_path / "ADMISSION_HOLD.json"
    if initial_hold:
        marker.write_text('{"hold_new_admissions": true}\n')
    def admit(_db, _task):
        counts["admit"] += 1
        task["status"] = "running"
        if hold_after_first_admit and counts["admit"] == 1:
            marker.write_text('{"hold_new_admissions": true}\n')
    def candidate(*_args):
        counts["candidate"] += 1
        if hold_during_candidate and counts["candidate"] == 1:
            marker.write_text('{"hold_new_admissions": true}\n')
        return task if counts["candidate"] == 1 else None
    def stop_on_sleep(_seconds):
        c.STOP = True
    original_read_text = Path.read_text
    def fixture_read_text(path, *args, **kwargs):
        if str(path) == "/sys/devices/virtual/dmi/id/board_asset_tag":
            return "fixture-instance"
        return original_read_text(path, *args, **kwargs)
    def check_running(*_args): counts["checked"] += 1
    def emergency(*_args): counts["emergency"] += 1; return None
    def atomic(path, _obj):
        if Path(path).name == "owner.json": counts["owner"] += 1
    def export(*_args): counts["export"] += 1
    def checkpoint(*_args): counts["checkpoint"] += 1
    patches = [
        patch.object(c, "lock_project", return_value=object()),
        patch.object(c, "connect", return_value=object()),
        patch.object(c, "initialize", return_value=tasks),
        patch.object(c, "freeze", return_value={"plan_sha256": "fixture", "source_sha256": {}}),
        patch.object(c, "source_hashes", return_value={}),
        patch.object(c, "check_running", side_effect=check_running),
        patch.object(c, "ready_tasks", return_value=[task]),
        patch.object(c, "emergency_interrupt_one", side_effect=emergency),
        patch.object(c, "storage_allow", return_value=(True, 100 * c.GIB)),
        patch.object(c, "cpu_idle_cores", return_value=8.0),
        patch.object(c, "admission_candidate", side_effect=candidate),
        patch.object(c, "admit", side_effect=admit),
        patch.object(c, "load", return_value=tasks),
        patch.object(c, "atomic", side_effect=atomic),
        patch.object(c, "event", return_value=None),
        patch.object(c, "export", side_effect=export),
        patch.object(c, "human_checkpoint", side_effect=checkpoint),
        patch.object(c, "maybe_report", return_value=None),
        patch.object(c.signal, "signal", return_value=None),
        patch.object(c.os, "cpu_count", return_value=4),
        patch.object(c.time, "sleep", side_effect=stop_on_sleep),
        patch.object(Path, "read_text", fixture_read_text),
    ]
    from contextlib import ExitStack
    with ExitStack() as stack:
        for p in patches: stack.enter_context(p)
        c.run()
    return counts

def test_existing_hold_pauses_only_admission_and_preserves_guards(tmp_path):
    result = run_fixture(tmp_path, initial_hold=True)
    assert result["admit"] == 0 and result["candidate"] == 0
    assert result["checked"] >= 1 and result["emergency"] >= 1
    assert result["owner"] == 1 and result["export"] >= 1 and result["checkpoint"] >= 1

def test_no_hold_keeps_normal_admission(tmp_path):
    result = run_fixture(tmp_path)
    assert result["admit"] == 1 and result["candidate"] >= 1
    assert result["checked"] >= 1 and result["emergency"] >= 2
    assert result["owner"] == 1 and result["export"] >= 1 and result["checkpoint"] >= 1

def test_hold_after_first_admission_blocks_next_batch_admission(tmp_path):
    result = run_fixture(tmp_path, hold_after_first_admit=True)
    assert result["admit"] == 1 and result["candidate"] == 1
    assert result["checked"] >= 1 and result["emergency"] >= 2
    assert result["owner"] == 1 and result["export"] >= 1 and result["checkpoint"] >= 1

def test_hold_created_after_candidate_selection_blocks_admit(tmp_path):
    result = run_fixture(tmp_path, hold_during_candidate=True)
    assert result["candidate"] == 1 and result["admit"] == 0
    assert result["checked"] >= 1 and result["emergency"] >= 1
    assert result["owner"] == 1 and result["export"] >= 1 and result["checkpoint"] >= 1


def test_watchdog_remains_callable_with_admission_hold_present(tmp_path):
    c.R = tmp_path
    (tmp_path / "ADMISSION_HOLD.json").write_text('{"hold_new_admissions": true}\n')
    (tmp_path / "READY_TO_START.json").write_text('{}\n')
    (tmp_path / "owner.json").write_text('{"pid": 123, "process_start_ticks": "456"}\n')
    with patch.object(c, "alive", return_value=True) as alive, patch.object(c.subprocess, "run", side_effect=AssertionError("watchdog must not relaunch a live controller")):
        c.watchdog()
    alive.assert_called_once_with(123, "456", "controller.py")
