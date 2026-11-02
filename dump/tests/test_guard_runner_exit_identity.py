import importlib.util
import pathlib
import subprocess

SCRIPT = pathlib.Path(__file__).with_name("run_guarded_tests.py")
spec = importlib.util.spec_from_file_location("guarded_tests", SCRIPT)
guarded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guarded)


def _proc_tree(root, pid, state, include_rss):
    proc = root / str(pid)
    proc.mkdir(parents=True)
    tail = [state, "1", str(pid)] + ["0"] * 16 + ["987654"] + ["0"] * 5
    (proc / "stat").write_text(f"{pid} (fixture process) " + " ".join(tail))
    status = "Name:\tfixture\n"
    if include_rss:
        status += "VmRSS:\t0 kB\n"
    (proc / "status").write_text(status)


def test_zombie_without_rss_is_identity_verified_with_zero_rss(tmp_path):
    _proc_tree(tmp_path, 4321, "Z", False)
    assert guarded.proc_info(4321, tmp_path) == (1, 4321, "987654", 0)


def test_live_process_without_rss_is_unverified(tmp_path):
    _proc_tree(tmp_path, 4321, "S", False)
    assert guarded.proc_info(4321, tmp_path) is None


def test_confirmed_fast_exit_is_distinguished_from_live_child():
    exited = subprocess.Popen(["/bin/true"])
    assert guarded.confirm_process_exit(exited, 0.5) == 0

    live = subprocess.Popen(["/bin/sleep", "5"])
    try:
        assert guarded.confirm_process_exit(live, 0.01) is None
        assert live.poll() is None
    finally:
        if live.poll() is None:
            live.terminate()
        live.wait(timeout=1)


import json
import pytest


@pytest.mark.parametrize(
    "case, expected_exit, expected_reason",
    [
        ("missing_fast_exit", 0, None),
        ("changed_identity_even_if_exit_zero", 1, "child_identity_changed"),
        ("missing_but_still_live", 1, "child_identity_unverified_live"),
    ],
)
def test_main_exit_race_is_fail_closed(monkeypatch, capsys, case, expected_exit, expected_reason):
    class FakeProcess:
        pid = 4321

        def __init__(self):
            self.returncode = None
            self.wait_calls = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.wait_calls += 1
            if case == "missing_but_still_live":
                raise subprocess.TimeoutExpired("fixture", timeout)
            self.returncode = 0
            return 0

    proc = FakeProcess()
    monkeypatch.setattr(guarded.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(guarded.sys, "argv", ["run_guarded_tests.py", "--rss-bytes", "100000", "--wall-seconds", "5", "--grace-seconds", "0.01", "--", "fixture"])
    original = (1, 4321, "11", 0)
    if case == "changed_identity_even_if_exit_zero":
        observed = iter([original, (1, 999, "12", 0), (1, 999, "12", 0)])
    elif case == "missing_fast_exit":
        observed = iter([original, None, None])
    else:
        observed = iter([original, None, None])
    monkeypatch.setattr(guarded, "proc_info", lambda pid: next(observed))
    monkeypatch.setattr(guarded, "tree_rss", lambda pid: (0, {pid}, {pid: original}))
    def forbidden_signal(*args, **kwargs):
        raise AssertionError("unverified process must never be signaled")
    monkeypatch.setattr(guarded.os, "killpg", forbidden_signal)

    result = guarded.main()
    receipt = json.loads(capsys.readouterr().out)
    assert result == expected_exit
    assert receipt["reason"] == expected_reason
    if case == "missing_but_still_live":
        assert proc.wait_calls == 1

