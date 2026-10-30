import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import safe_watchdog as wd


class SafeWatchdogDecisionTests(unittest.TestCase):
    def setUp(self):
        self.deployment = {
            "phase": "watchdog_ready",
            "qualification_status": "qualified",
            "hold_document": {"nonce": "owned-nonce"},
            "installed_controller_sha256": "controller-hash",
            "freeze_sha256": "freeze-hash",
            "run_script_sha256": "run-hash",
            "storage_policy_id": wd.POLICY,
        }
        self.enable = {
            "schema_version": "lamost-safe-watchdog-enable/1",
            "enabled": True,
            "hold_nonce": "owned-nonce",
            "controller_sha256": "controller-hash",
            "freeze_sha256": "freeze-hash",
            "run_script_sha256": "run-hash",
            "storage_policy_id": wd.POLICY,
            "max_recoveries": 2,
        }
        self.hold = {
            "nonce": "owned-nonce",
            "owner_operation": "user_approved_working_storage_policy_20261030",
        }
        self.freeze = {
            "source_sha256": {"controller.py": "controller-hash"},
            "storage_admission_policy": dict(wd.STORAGE),
            "resource_policy": dict(wd.SCIENCE),
        }
        self.holds = {"ADMISSION_HOLD": False, "CODE_CHANGE_HOLD": False}
        self.processes = {"controllers": [], "workers": [], "unknown_controllers": [], "storage": []}
        self.pending = {"total": 2, "status_counts": {"validated_terminal": 1, "waiting_for_dependency": 1}}
        self.counter = {"schema_version": 1, "recovery_count": 0, "history": []}

    def call(self, **kw):
        args = {
            "d": self.deployment, "e": self.enable, "h": self.hold, "f": self.freeze,
            "source_sha": "controller-hash", "freeze_sha": "freeze-hash", "run_sha": "run-hash",
            "holds": self.holds, "proc": self.processes, "reg": self.pending,
            "count": self.counter, "owner_free": True, "tmux": False,
        }
        args.update(kw)
        return wd.decide(**args)

    def test_known_controller_is_noop(self):
        self.processes["controllers"] = [{"verified": True}]
        self.assertEqual(self.call()["action"], "noop_controller_verified")

    def test_unknown_controller_blocks_restart(self):
        self.processes["unknown_controllers"] = [{"uid": 1000, "ticks": "8"}]
        self.assertEqual(self.call()["action"], "backoff")

    def test_orphan_phase_worker_blocks_restart(self):
        self.processes["workers"] = [{"uid": 1000, "ticks": "9", "kind": "phase"}]
        self.assertEqual(self.call()["action"], "backoff")

    def test_unknown_worker_module_is_recognized(self):
        proc = {"argv": ["python", "-m", "source.phase_worker"],
                "cwd": wd.R, "uid": 1000, "ticks": "11"}
        self.assertTrue(wd.unknown_worker(proc))

    def test_source_holds_block_restart(self):
        self.holds["ADMISSION_HOLD"] = True
        self.assertEqual(self.call()["action"], "backoff")
        self.holds["ADMISSION_HOLD"] = False
        self.holds["CODE_CHANGE_HOLD"] = True
        self.assertEqual(self.call()["action"], "backoff")

    def test_wrong_run_script_hash_blocks_restart(self):
        self.assertEqual(self.call(run_sha="wrong-run-script")["action"], "backoff")
        self.deployment["run_script_sha256"] = "wrong-run-script"
        self.enable["run_script_sha256"] = "wrong-run-script"
        self.assertEqual(self.call()["action"], "backoff")

    def test_unknown_registry_status_blocks_restart(self):
        self.pending["status_counts"] = {"validated_terminal": 1, "mystery_state": 1}
        self.assertEqual(self.call()["action"], "backoff")

    def test_wrong_controller_hash_blocks_restart(self):
        self.assertEqual(self.call(source_sha="wrong-hash")["action"], "backoff")

    def test_two_recoveries_is_hard_limit(self):
        self.counter["recovery_count"] = 2
        self.assertEqual(self.call()["action"], "backoff")

    def test_malformed_enable_or_registry_blocks_restart(self):
        self.enable = {"enabled": True}
        self.assertEqual(self.call()["action"], "backoff")
        self.setUp()
        self.pending["status_counts"] = {"waiting_for_dependency": "one"}
        self.assertEqual(self.call()["action"], "backoff")

    def test_malformed_deployment_state_fails_closed(self):
        self.deployment["hold_document"] = "malformed"
        self.assertEqual(self.call()["action"], "backoff")
        self.setUp()
        self.freeze["source_sha256"] = "malformed"
        self.assertEqual(self.call()["action"], "backoff")

    def test_malformed_persisted_counter_fails_closed(self):
        with __import__("tempfile").TemporaryDirectory() as td:
            p = pathlib.Path(td) / "state.json"
            p.write_text('{"schema_version": 1, "recovery_count": "one", "history": []}')
            with self.assertRaises(wd.Backoff):
                wd.counter(p)

    def test_all_terminal_does_not_restart_models(self):
        terminal = {"total": 2, "status_counts": {"validated_terminal": 2}}
        self.assertEqual(self.call(reg=terminal)["action"], "all_terminal_no_model_restart")

    def test_pending_registry_selects_single_controller_recovery(self):
        self.assertEqual(self.call()["action"], "launch_controller")

    def test_existing_tmux_session_blocks_duplicate(self):
        self.assertEqual(self.call(tmux=True)["action"], "backoff")


if __name__ == "__main__":
    unittest.main()

