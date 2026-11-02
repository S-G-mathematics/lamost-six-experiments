import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
LIVE_SOURCE = ROOT / "runtime_20261025" / "source"
ET_SOURCE = HERE / "source" / "parallel_extra_trees"
ET_NAMES = (
    "parallel_extra_trees/worker.py",
    "parallel_extra_trees/phase_worker.py",
    "parallel_extra_trees/science.py",
)
POLICY_REL = "manifests/EXTRA_TREES4_EXECUTION_POLICY_20261029.json"
QUAL_REL = "reports/engineering_audits/EXTRA_TREES4_EXECUTION_QUALIFICATION_20261029.json"
TASK = {
    "key": "e4/rep_1/fit/direct/extra_trees/control",
    "experiment": 4,
    "rep": 1,
    "kind": "fit",
    "method": "extra_trees",
    "route": "direct",
    "status": "planned",
    "attempts": [],
    "reuse_pipeline": False,
    "admission_reservation_bytes": None,
    "seed": 271828,
    "trials": 10,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ET4ControllerContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="et4-controller-contract-")
        self.runtime = Path(self.temp.name) / "runtime_20261025"
        (self.runtime / "source").mkdir(parents=True)
        (self.runtime / "manifests").mkdir()
        (self.runtime / "reports/engineering_audits").mkdir(parents=True)
        for rel in ET_NAMES:
            target = self.runtime / "source" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HERE / "source" / rel, target)
        shutil.copy2(HERE / "source/controller.py", self.runtime / "source/controller.py")
        (self.runtime / "tests").mkdir()
        shutil.copy2(HERE / "tests/test_extra_trees4_engineering.py",
                     self.runtime / "tests/test_extra_trees4_engineering.py")
        shutil.copy2(HERE / "tests/test_extra_trees4_controller_contract.py",
                     self.runtime / "tests/test_extra_trees4_controller_contract.py")
        self.sources = {rel: sha(self.runtime / "source" / rel) for rel in ET_NAMES}
        self.controller_sha = sha(self.runtime / "source/controller.py")
        self.receipt_rel = "reports/engineering_audits/synthetic_portable_receipt.json"
        self.receipt = {
            "schema": "lamost-terminal-portable-tests/1",
            "status": "passed",
            "bundle_fingerprint_sha256": "b" * 64,
            "expected_test_count": 1,
            "passed_test_count": 1,
            "failed_test_count": 0,
        }
        receipt_path = self.runtime / self.receipt_rel
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(self.receipt, sort_keys=True) + "\n")
        self.qualification = {
            "schema": "lamost-et4-execution-qualification/1",
            "status": "passed",
            "source_sha256": dict(self.sources),
            "controller_sha256": self.controller_sha,
            "execution": {
                "fit_n_jobs": 4, "prediction_n_jobs": 1, "serialized_estimator_n_jobs": 1,
                "native_threads": 1, "admission_reservation_gib": 10,
                "worker_memory_limit_gib": 10, "trial_timeout_seconds": 600,
                "phase_timeout_seconds": 600, "termination_grace_seconds": 30,
                "cpu_reservation_units": 4,
            },
            "controller_contract": {
                "status": "passed",
                "test_path": "tests/test_extra_trees4_controller_contract.py",
                "test_sha256": sha(HERE / "tests/test_extra_trees4_controller_contract.py"),
                "test_count": 3,
                "exit_code": 0,
                "synthetic_runtime_only": True,
                "scientific_fits_started": 0,
            },
            "synthetic_thread_equivalence": {
                "status": "passed",
                "test_path": "tests/test_extra_trees4_engineering.py",
                "test_sha256": sha(self.runtime / "tests/test_extra_trees4_engineering.py"),
                "test_count": 3,
                "exit_code": 0,
                "models_are_synthetic_only": True,
                "scientific_fits_started": 0,
                "tree_structures_identical_single_vs_four": True,
                "validation_scores_identical_single_vs_four": True,
                "same_selected_candidate_single_vs_four": True,
                "serialized_estimator_n_jobs": 1,
                "prediction_probabilities_identical_single_vs_four": True,
            },
        }
        qpath = self.runtime / QUAL_REL
        qpath.parent.mkdir(parents=True, exist_ok=True)
        qpath.write_text(json.dumps(self.qualification, sort_keys=True) + "\n")
        self.policy = {
            "schema": "lamost-later-et4-execution-policy/1",
            "policy_id": "et4-fit_n_jobs4-v1",
            "resource_profile_id": "et-fit_n_jobs4",
            "status": "qualified",
            "scope": {
                "experiments": [4, 5], "kind": "fit",
                "methods": ["extra_trees"], "never_attempted": True,
                "reuse_pipeline": False,
            },
            "fit_n_jobs": 4, "prediction_n_jobs": 1, "native_threads": 1,
            "admission_reservation_gib": 10, "worker_memory_limit_gib": 10,
            "trial_timeout_seconds": 600, "phase_timeout_seconds": 600,
            "termination_grace_seconds": 30, "cpu_reservation_units": 4,
            "source_sha256": dict(self.sources),
            "qualification": {"path": QUAL_REL, "sha256": sha(qpath)},
        }
        self.policy_path = self.runtime / POLICY_REL
        self.write_policy_and_freeze()
        self.module = self.load_controller()

    def tearDown(self):
        self.temp.cleanup()

    def write_policy_and_freeze(self):
        self.policy_path.write_text(json.dumps(self.policy, sort_keys=True) + "\n")
        freeze = {
            "source_sha256": {
                **self.sources,
                "controller.py": self.controller_sha,
            },
            "et4_execution_policy_sha256": sha(self.policy_path),
        }
        (self.runtime / "manifests/freeze.json").write_text(json.dumps(freeze) + "\n")

    def load_controller(self):
        sys.path.insert(0, str(LIVE_SOURCE))
        try:
            spec = importlib.util.spec_from_file_location(
                "et4_candidate_controller_fixture",
                self.runtime / "source/controller.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(str(LIVE_SOURCE))
        module.R = self.runtime
        module.DEFINITIONS = {TASK["key"]: dict(TASK)}
        return module

    def test_valid_policy_allows_only_pristine_e4_e5_et_fits_and_uses_et_worker(self):
        policy = self.module._et4_policy()
        self.assertEqual(policy["source_sha256"], self.sources)
        eligible = self.module._et4_fit_eligible(dict(TASK))
        self.assertEqual(eligible["reservation_gib"], 10)
        self.assertEqual(eligible["cpu_reservation_units"], 4)
        self.assertEqual(eligible["execution_policy"], "et4-fit_n_jobs4-v1")
        self.assertEqual(
            self.module.worker_script_for_task(
                dict(TASK), "et4-fit_n_jobs4-v1", "et-fit_n_jobs4"
            ),
            self.runtime / "source/parallel_extra_trees/worker.py",
        )
        self.assertEqual(
            self.module._execution_worker_profile_fields(self.module.ET4_PROFILE_ID),
            {"execution_policy": "et4-fit_n_jobs4-v1", "resource_profile": "et-fit_n_jobs4"},
        )
        self.assertEqual(self.module._execution_worker_profile_fields("adaptive-default"), {})
        self.assertEqual(self.module.worker_reservation_bytes(dict(TASK)), 10 * self.module.GIB)
        self.assertEqual(self.module.candidate_cpu_reservation_units(dict(TASK)), 4)
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "experiment": 3}))
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "method": "random_forest"}))
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "kind": "eval"}))
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "status": "running"}))
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "attempts": [{"attempt_id": "old"}]}))
        self.assertIsNone(self.module._et4_fit_eligible({**TASK, "reuse_pipeline": "x/pipeline.joblib"}))

    def test_manifest_source_timeout_and_focused_receipt_mismatches_fail_closed(self):
        source = self.runtime / "source/parallel_extra_trees/science.py"
        original = source.read_bytes()
        source.write_bytes(original + b"\n# tamper\n")
        with self.assertRaises(RuntimeError):
            self.module._et4_policy()
        source.write_bytes(original)
        self.policy["phase_timeout_seconds"] = 601
        self.write_policy_and_freeze()
        with self.assertRaises(RuntimeError):
            self.module._et4_policy()
        self.policy["phase_timeout_seconds"] = 600
        self.qualification["execution"]["phase_timeout_seconds"] = 601
        qpath = self.runtime / QUAL_REL
        qpath.write_text(json.dumps(self.qualification, sort_keys=True) + "\n")
        self.policy["qualification"]["sha256"] = sha(qpath)
        self.write_policy_and_freeze()
        with self.assertRaises(RuntimeError):
            self.module._et4_policy()
        self.qualification["execution"]["phase_timeout_seconds"] = 600
        qpath.write_text(json.dumps(self.qualification, sort_keys=True) + "\n")
        self.policy["qualification"]["sha256"] = sha(qpath)
        self.write_policy_and_freeze()
        self.qualification["controller_contract"]["status"] = "not_run"
        qpath.write_text(json.dumps(self.qualification, sort_keys=True) + "\n")
        self.policy["qualification"]["sha256"] = sha(qpath)
        self.write_policy_and_freeze()
        with self.assertRaises(RuntimeError):
            self.module._et4_policy()

    def test_unqualified_policy_and_bad_identity_are_not_dispatched(self):
        self.policy["status"] = "draft_unqualified"
        self.write_policy_and_freeze()
        with self.assertRaises(RuntimeError):
            self.module.worker_script_for_task(
                dict(TASK), "et4-fit_n_jobs4-v1", "et-fit_n_jobs4"
            )
        active = {
            **TASK,
            "adaptive_policy_revision": self.module.ADAPTIVE_REVISION,
            "pid": 12345,
            "process_start_ticks": "67890",
            "request_path": str(self.runtime / "attempts/et4/request.json"),
            "attempts": [{"attempt_id": "attempt-a"}],
        }
        req = Path(active["request_path"])
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text(json.dumps({
            "task": dict(TASK),
            "attempt_id": "attempt-a",
            "result_path": str(self.runtime / "attempts/et4/result.json"),
            "dispatch_policy_id": self.module.DISPATCH_POLICY_ID,
            "execution_policy": "et4-fit_n_jobs4-v1",
            "resource_profile": "et-fit_n_jobs4",
        }))
        old_policy = self.policy["status"]
        self.policy["status"] = "qualified"
        self.write_policy_and_freeze()
        fake_argv = (str(self.runtime / "source/parallel_extra_trees/worker.py") + "\0"
                     + str(req) + "\0").encode()
        original_read = Path.read_bytes
        def read_bytes(path):
            if str(path) == "/proc/12345/cmdline":
                return fake_argv
            return original_read(path)
        with mock.patch.object(self.module, "alive", side_effect=lambda pid, ticks, needle="worker.py": pid == 12345 and ticks == "67890"):
            with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes):
                self.assertTrue(self.module.verified_adaptive_worker(active))
                self.assertFalse(self.module.verified_adaptive_worker({**active, "process_start_ticks": "wrong"}))
                self.assertFalse(self.module.verified_adaptive_worker({**active, "request_path": str(self.runtime / "other.json")}))
        self.policy["status"] = old_policy


if __name__ == "__main__":
    unittest.main()
