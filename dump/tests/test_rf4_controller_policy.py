from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
if (BASE / "controller" / "source" / "controller.py").is_file():
    STAGE = BASE
    RUNTIME = STAGE.parents[1]
    CONTROLLER_PATH = STAGE / "controller" / "source" / "controller.py"
else:
    STAGE = BASE
    RUNTIME = STAGE
    CONTROLLER_PATH = RUNTIME / "source" / "controller.py"
SOURCE = RUNTIME / "source"
sys.path.insert(0, str(SOURCE))
_spec = importlib.util.spec_from_file_location("rf4_controller_fixture", CONTROLLER_PATH)
ctl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctl)

BASE_NAMES = (
    "controller.py", "worker.py", "science.py", "phase_worker.py", "cohorts.py",
    "ensemble.py", "ensemble_maintenance_patch.py", "e6_phase_supervisor.py",
    "svm_margin/science.py", "svm_margin/worker.py", "svm_margin/phase_worker.py",
    "admission_evidence.py",
)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class RF4ControllerAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_root = ctl.R
        self.old_defs = ctl.DEFINITIONS
        ctl.R = self.root
        ctl.DEFINITIONS = {}
        self.archive_context_patch=patch.object(ctl.archive_fit_admission,"inspect_runtime",return_value={"mode":"inactive"})
        self.archive_context_patch.start();self.addCleanup(self.archive_context_patch.stop)
        for name in BASE_NAMES + ctl.RF4_SOURCE_NAMES:
            p = self.root / "source" / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture:" + name + "\n")
        (self.root / "manifests").mkdir(exist_ok=True)

    def tearDown(self):
        ctl.R = self.old_root
        ctl.DEFINITIONS = self.old_defs
        self.tmp.cleanup()

    def candidate(self):
        return {
            "key": "e5/rep_1/fit/direct/random_forest",
            "experiment": 5,
            "kind": "fit",
            "method": "random_forest",
            "route": "direct",
            "rep": 1,
            "status": "planned",
            "attempts": [],
        }

    def qualify_policy(self):
        qualification = self.root / "reports" / "rf4_qualification.json"
        sources = {name: digest(self.root / "source" / name) for name in ctl.RF4_SOURCE_NAMES}
        qualification_sha = write_json(qualification, {
            "schema": "lamost-rf4-execution-qualification/1",
            "status": "passed",
            "source_sha256": sources,
            "controller_sha256": digest(CONTROLLER_PATH),
            "fit_n_jobs": 4,
            "prediction_n_jobs": 1,
            "native_threads": 1,
            "admission_reservation_gib": 10,
            "worker_memory_limit_gib": 10,
            "trial_timeout_seconds": 600,
            "phase_timeout_seconds": 600,
            "termination_grace_seconds": 30,
            "cpu_reservation_units": 4,
            "cpu_reserve_cores": 2,
            "harness": {
                "status": "passed",
                "source_sha256": sources,
                "harness_source_sha256": "a" * 64,
                "report_sha256": "b" * 64,
                "guard_log_sha256": "c" * 64,
                "guard_exit_code": 0,
                "models_are_synthetic_only": True,
                "fit_n_jobs": 4,
                "prediction_n_jobs": 1,
                "serialized_estimator_n_jobs": 1,
                "harness_guard": {
                    "wall_limit_seconds": 120,
                    "rss_limit_bytes": 1610612736,
                    "address_space_limit_bytes": 2147483648,
                    "peak_process_tree_rss_bytes": 100000000,
                    "wall_seconds": 1.25,
                    "exit_code": 0,
                },
            },
            "portable_suite": {
                "status": "passed",
                "exit_code": 0,
                "expected_test_count": 15,
                "passed_test_count": 15,
                "failed_test_count": 0,
                "bundle_fingerprint_sha256": "d" * 64,
            },
        })
        doc = {
            "schema": "lamost-later-rf4-execution-policy/1",
            "policy_id": ctl.RF4_EXECUTION_POLICY,
            "resource_profile_id": ctl.RF4_RESOURCE_PROFILE,
            "status": "qualified",
            "scope": {
                "experiments": [4, 5], "kind": "fit", "methods": ["random_forest"],
                "never_attempted": True, "reuse_pipeline": False,
            },
            "fit_n_jobs": 4,
            "prediction_n_jobs": 1,
            "native_threads": 1,
            "admission_reservation_gib": 10,
            "worker_memory_limit_gib": 10,
            "trial_timeout_seconds": 600,
            "phase_timeout_seconds": 600,
            "termination_grace_seconds": 30,
            "source_sha256": sources,
            "qualification": {
                "path": "reports/rf4_qualification.json",
                "sha256": qualification_sha,
            },
        }
        policy_path = self.root / ctl.RF4_POLICY_REL
        policy_sha = write_json(policy_path, doc)
        legacy = ctl.source_hashes()
        frozen_sources = dict(legacy)
        frozen_sources.update(sources)
        write_json(self.root / "manifests" / "freeze.json", {
            "rf4_execution_policy_sha256": policy_sha,
            "source_sha256": frozen_sources,
        })
        return doc

    def test_policy_absent_keeps_legacy_source_inventory_and_rf4_disabled(self):
        self.assertEqual(len(ctl.source_hashes()), 12)
        self.assertIsNone(ctl._rf4_policy())
        task = self.candidate()
        ctl.DEFINITIONS[task["key"]] = dict(task)
        self.assertIsNone(ctl._rf4_fit_eligible(task))
        self.assertEqual(ctl.candidate_cpu_reservation_units(task), 1)
        self.assertEqual(ctl.worker_script_for_task(task), self.root / "source" / "worker.py")

    def test_qualified_policy_binds_three_sources_and_enables_only_candidate(self):
        self.qualify_policy()
        self.assertEqual(len(ctl.source_hashes()), 15)
        task = self.candidate()
        ctl.DEFINITIONS[task["key"]] = dict(task)
        profile = ctl._rf4_fit_eligible(task)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["reservation_gib"], 10)
        self.assertEqual(profile["cpu_reservation_units"], 4)
        self.assertEqual(ctl.worker_reservation_bytes(task), 10 * ctl.GIB)
        self.assertEqual(ctl.candidate_cpu_reservation_units(task), 4)
        self.assertEqual(
            ctl.worker_script_for_task(task, ctl.RF4_EXECUTION_POLICY, ctl.RF4_RESOURCE_PROFILE),
            self.root / "source" / "parallel_rf" / "worker.py",
        )
        e4 = dict(task, key="e4/rep_2/fit/treatment/random_forest", experiment=4, rep=2)
        ctl.DEFINITIONS[e4["key"]] = {k: v for k, v in e4.items() if k not in {"status", "attempts"}}
        self.assertIsNotNone(ctl._rf4_fit_eligible(e4))

    def test_scope_and_attempt_mutations_are_excluded(self):
        self.qualify_policy()
        task = self.candidate()
        ctl.DEFINITIONS[task["key"]] = dict(task)
        for changed in (
            dict(task, experiment=3),
            dict(task, kind="eval"),
            dict(task, method="arf"),
            dict(task, reuse_pipeline=True),
            dict(task, attempts=[{"attempt_id": "historical"}]),
            dict(task, status="validated_terminal"),
            dict(task, admission_reservation_bytes=10 * ctl.GIB),
        ):
            self.assertIsNone(ctl._rf4_fit_eligible(changed))
            self.assertEqual(ctl.candidate_cpu_reservation_units(changed), 1)

    def test_declared_stale_policy_or_adapter_hash_fails_closed(self):
        self.qualify_policy()
        policy_path = self.root / ctl.RF4_POLICY_REL
        doc = json.loads(policy_path.read_text())
        doc["phase_timeout_seconds"] = 601
        policy_sha = write_json(policy_path, doc)
        freeze_path = self.root / "manifests" / "freeze.json"
        freeze = json.loads(freeze_path.read_text())
        freeze["rf4_execution_policy_sha256"] = policy_sha
        write_json(freeze_path, freeze)
        with self.assertRaises(RuntimeError):
            ctl._rf4_policy()
        self.qualify_policy()
        (self.root / "source" / ctl.RF4_SOURCE_NAMES[0]).write_text("changed adapter bytes\n")
        with self.assertRaises(RuntimeError):
            ctl._rf4_policy()

    def test_historical_cpu_and_memory_reservation_are_not_rewritten(self):
        self.qualify_policy()
        task = self.candidate()
        task["status"] = "running"
        task["attempts"] = [{
            "attempt_id": "old",
            "resource_profile": {"admission_reservation_bytes": 5 * ctl.GIB},
        }]
        task["admission_reservation_bytes"] = 5 * ctl.GIB
        ctl.DEFINITIONS[task["key"]] = dict(task)
        self.assertEqual(ctl.worker_reservation_bytes(task), 5 * ctl.GIB)
        self.assertEqual(ctl.worker_cpu_reservation_units(task), 1)
        self.assertEqual(ctl.candidate_cpu_reservation_units(task), 1)
        task["admission_resource_policy"] = {
            "execution_policy": ctl.RF4_EXECUTION_POLICY,
            "resource_profile": ctl.RF4_RESOURCE_PROFILE,
            "cpu_reservation_units": 1,
        }
        self.assertEqual(ctl.worker_reservation_bytes(task), 10 * ctl.GIB)
        self.assertEqual(ctl.worker_cpu_reservation_units(task), 4)
        self.assertEqual(ctl.candidate_cpu_reservation_units(task), 4)

    def test_weighted_cpu_capacity_preserves_legacy_units_and_charges_rf4_four(self):
        self.qualify_policy()
        legacy = {"key": "old", "attempts": []}
        rf4 = {
            "key": "rf4", "admission_resource_policy": {
                "execution_policy": ctl.RF4_EXECUTION_POLICY,
                "resource_profile": ctl.RF4_RESOURCE_PROFILE,
                "cpu_reservation_units": 4,
            },
        }
        occupied, capacity = ctl.cpu_admission_units([legacy, rf4], 16, 6, 2)
        self.assertEqual(occupied, 5)
        self.assertEqual(capacity, 9)
        self.assertEqual(occupied + 4, capacity)
        occupied_tight, capacity_tight = ctl.cpu_admission_units([legacy, rf4], 16, 5, 2)
        self.assertEqual(occupied_tight, 5)
        self.assertEqual(capacity_tight, 8)
        self.assertGreater(occupied_tight + 4, capacity_tight)
        self.assertEqual(ctl.cpu_admission_units([legacy, {"key": "old2"}], 16, 6, 2), (2, 6))

    def test_qualification_rejects_controller_source_mismatch(self):
        self.qualify_policy()
        qpath = self.root / "reports" / "rf4_qualification.json"
        qdoc = json.loads(qpath.read_text())
        qdoc["controller_sha256"] = "0" * 64
        qsha = write_json(qpath, qdoc)
        policy_path = self.root / ctl.RF4_POLICY_REL
        policy = json.loads(policy_path.read_text())
        policy["qualification"]["sha256"] = qsha
        policy_sha = write_json(policy_path, policy)
        freeze_path = self.root / "manifests" / "freeze.json"
        freeze = json.loads(freeze_path.read_text())
        freeze["rf4_execution_policy_sha256"] = policy_sha
        write_json(freeze_path, freeze)
        with self.assertRaises(RuntimeError):
            ctl._rf4_policy()

    def test_existing_malformed_freeze_fails_closed(self):
        (self.root / "manifests" / "freeze.json").write_text("{malformed")
        with self.assertRaises(RuntimeError):
            ctl._rf4_policy()

    def test_policy_cache_reuses_verified_bytes_and_invalidates_on_same_size_change(self):
        self.qualify_policy()
        first = ctl._rf4_policy()
        self.assertIsNotNone(first)
        self.assertIs(ctl._rf4_policy(), first)
        source = self.root / "source" / ctl.RF4_SOURCE_NAMES[0]
        original = source.read_bytes()
        source.write_bytes(original[:-1] + b"x")
        with self.assertRaises(RuntimeError):
            ctl._rf4_policy()

    def test_admit_writes_rf4_only_as_top_level_operational_metadata(self):
        self.qualify_policy()
        task = self.candidate()
        definition = {k: v for k, v in task.items() if k not in {"status", "attempts"}}
        ctl.DEFINITIONS[task["key"]] = definition
        db = ctl.connect()
        class Proc:
            pid = 12345
        try:
            from unittest.mock import patch
            with patch.object(ctl.subprocess, "Popen", return_value=Proc()) as popen, patch.object(ctl, "start_ticks", return_value="987"):
                ctl.admit(db, task)
            request = Path(task["request_path"])
            cfg = json.loads(request.read_text())
            self.assertEqual(cfg["execution_policy"], ctl.RF4_EXECUTION_POLICY)
            self.assertEqual(cfg["resource_profile"], ctl.RF4_RESOURCE_PROFILE)
            self.assertNotIn("execution_policy", cfg["task"])
            self.assertNotIn("resource_profile", cfg["task"])
            self.assertEqual(Path(popen.call_args.args[0][4]), self.root / "source" / "parallel_rf" / "worker.py")
            self.assertEqual(task["admission_reservation_bytes"], 10 * ctl.GIB)
            self.assertEqual(task["admission_profile_id"], ctl.RF4_RESOURCE_PROFILE)
            self.assertEqual(task["admission_resource_policy"]["cpu_reservation_units"], 4)
            self.assertEqual(task["attempts"][-1]["resource_profile"]["fit_n_jobs"], 4)
            task["status"] = "planned"
            task.pop("admission_profile_id")
            with patch.object(ctl.subprocess, "Popen", return_value=Proc()), patch.object(ctl, "start_ticks", return_value="988"):
                ctl.admit(db, task)
            resumed_cfg = json.loads(Path(task["request_path"]).read_text())
            self.assertEqual(resumed_cfg["execution_policy"], ctl.RF4_EXECUTION_POLICY)
            self.assertEqual(resumed_cfg["resource_profile"], ctl.RF4_RESOURCE_PROFILE)
            self.assertEqual(task["admission_profile_id"], ctl.RF4_RESOURCE_PROFILE)
            self.assertEqual(task["admission_reservation_bytes"], 10 * ctl.GIB)
            self.assertEqual(task["attempts"][-1]["resource_profile"]["cpu_reservation_units"], 4)
        finally:
            db.close()

    def test_rf4_request_metadata_requires_matching_policy_profile(self):
        self.qualify_policy()
        task = self.candidate()
        ctl.DEFINITIONS[task["key"]] = dict(task)
        self.assertEqual(
            ctl.worker_script_for_task(task, ctl.RF4_EXECUTION_POLICY, ctl.RF4_RESOURCE_PROFILE).name,
            "worker.py",
        )
        with self.assertRaises(RuntimeError):
            ctl.worker_script_for_task(task, ctl.RF4_EXECUTION_POLICY, "wrong-profile")

if __name__ == "__main__":
    unittest.main()
