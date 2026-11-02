import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SRC))
import metadata_access_contract_v2 as contract


PRODUCER = "e3/rep_1/fit/synthetic/random_forest/gmm"
TRAIN = "e5/rep_1/generate/feature_noise_05/gmm"
FIT = "e5/rep_1/fit/synthetic/random_forest/feature_noise_05_gmm"
EVAL = "e5/rep_1/eval/synthetic/random_forest/feature_noise_05_gmm"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class V2ContractFixture:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime_20261025"
        self.source_dir = self.runtime / "source"
        self.manifests = self.runtime / "manifests"
        self.source_dir.mkdir(parents=True)
        self.manifests.mkdir()
        legacy = SRC / "metadata_only_contract.py"
        shutil.copy2(legacy, self.source_dir / legacy.name)
        shutil.copy2(SRC / "cold_storage_safety.py", self.source_dir / "cold_storage_safety.py")
        for rel in contract.PINNED_CODE:
            p = self.source_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("qualified fixture pin:" + rel)

        producer_dir = self.runtime / "artifacts" / PRODUCER
        train_dir = self.runtime / "artifacts" / TRAIN
        fit_dir = self.runtime / "artifacts" / FIT
        eval_dir = self.runtime / "artifacts" / EVAL
        for p in (producer_dir, train_dir, fit_dir, eval_dir):
            p.mkdir(parents=True, exist_ok=True)
        self.selection_path = producer_dir / "selection.json"
        self.selection_bytes = b'{"selected_params":{"n_estimators":7}}'
        self.selection_path.write_bytes(self.selection_bytes)
        self.npz_path = train_dir / "data.npz"
        self.npz_bytes = b"tiny fixture NPZ placeholder; not opened by contract"
        self.npz_path.write_bytes(self.npz_bytes)

        self.records = {
            PRODUCER: {
                "key": PRODUCER, "experiment": 3, "kind": "fit", "method": "gmm",
                "status": "validated_terminal", "outcome": "successful",
                "validation_state": "validated", "dependencies": [],
                "artifact_dir": str(producer_dir),
                "result": {"validation": {"files": {
                    "pipeline.joblib": "1" * 64,
                    "selection.json": sha(self.selection_bytes),
                }}},
            },
            TRAIN: {
                "key": TRAIN, "experiment": 5, "kind": "generate", "method": "gmm",
                "status": "validated_terminal", "outcome": "successful",
                "validation_state": "validated", "dependencies": [],
                "artifact_dir": str(train_dir),
                "result": {"validation": {"status": "validated", "files": {
                    "data.npz": sha(self.npz_bytes),
                }}},
            },
            FIT: {
                "key": FIT, "experiment": 5, "kind": "fit", "method": "random_forest",
                "route": "synthetic", "status": "waiting_for_dependency",
                "dependencies": [TRAIN, PRODUCER], "train_key": TRAIN,
                "selection_key": PRODUCER, "selection_mode": "fixed",
                "selection_policy": "frozen_clean_selected_params_no_retuning",
                "reuse_pipeline": None, "artifact_dir": str(fit_dir),
                "selection_source": str(self.selection_path),
            },
            EVAL: {
                "key": EVAL, "experiment": 5, "kind": "eval", "method": "random_forest",
                "route": "synthetic", "status": "waiting_for_dependency",
                "dependencies": [FIT], "fit_key": FIT, "reuse_pipeline": None,
                "artifact_dir": str(eval_dir),
            },
        }
        self.refresh_plan()

    def add_second_chain(self):
        train = "e5/rep_1/generate/feature_noise_10/gmm"
        fit = "e5/rep_1/fit/synthetic/random_forest/feature_noise_10_gmm"
        evaluation = "e5/rep_1/eval/synthetic/random_forest/feature_noise_10_gmm"
        train_dir = self.runtime / "artifacts" / train
        fit_dir = self.runtime / "artifacts" / fit
        eval_dir = self.runtime / "artifacts" / evaluation
        for directory in (train_dir, fit_dir, eval_dir):
            directory.mkdir(parents=True, exist_ok=True)
        data = b"second tiny fixture NPZ"
        (train_dir / "data.npz").write_bytes(data)
        self.records[train] = {
            "key": train, "experiment": 5, "kind": "generate", "method": "gmm",
            "status": "validated_terminal", "outcome": "successful",
            "validation_state": "validated", "dependencies": [],
            "artifact_dir": str(train_dir),
            "result": {"validation": {"status": "validated", "files": {"data.npz": sha(data)}}},
        }
        self.records[fit] = {
            "key": fit, "experiment": 5, "kind": "fit", "method": "random_forest",
            "route": "synthetic", "status": "waiting_for_dependency",
            "dependencies": [train, PRODUCER], "train_key": train,
            "selection_key": PRODUCER, "selection_mode": "fixed",
            "selection_policy": "frozen_clean_selected_params_no_retuning",
            "reuse_pipeline": None, "artifact_dir": str(fit_dir),
            "selection_source": str(self.selection_path),
        }
        self.records[evaluation] = {
            "key": evaluation, "experiment": 5, "kind": "eval", "method": "random_forest",
            "route": "synthetic", "status": "waiting_for_dependency",
            "dependencies": [fit], "fit_key": fit, "reuse_pipeline": None,
            "artifact_dir": str(eval_dir),
        }
        self.second_fit = fit
        self.second_eval = evaluation

    def refresh_plan(self):
        rows = []
        for task in self.records.values():
            stable = {k: v for k, v in task.items() if k not in contract._legacy._RUNTIME_FIELDS}
            rows.append(stable)
        plan_path = self.manifests / "tasks.json"
        raw = (json.dumps({"tasks": rows}, sort_keys=True, separators=(",", ":")) + "\n").encode()
        plan_path.write_bytes(raw)
        self.plan_sha = sha(raw)
        pins = {rel: sha((self.source_dir / rel).read_bytes()) for rel in contract.PINNED_CODE}
        freeze = {"plan_sha256": self.plan_sha, "source_sha256": pins}
        (self.manifests / "freeze.json").write_text(json.dumps(freeze, sort_keys=True))
        self.pin_override = pins

    def call(self):
        closure = set(contract._safety.consumer_closure(PRODUCER, self.records))
        with patch.object(contract, "FROZEN_TASKS_JSON_SHA256", self.plan_sha), \
             patch.object(contract, "PINNED_CODE", self.pin_override):
            return contract.build_contract(self.root, PRODUCER, self.records, closure)

    def close(self):
        self.temp.cleanup()


class MetadataAccessV2Tests(unittest.TestCase):
    def fixture(self):
        f = V2ContractFixture()
        self.addCleanup(f.close)
        return f

    def test_fixed_selection_fit_and_own_fit_evaluation_are_bound(self):
        f = self.fixture()
        proof = f.call()
        self.assertEqual(proof["policy"], contract.POLICY)
        self.assertEqual(proof["producer_task"], PRODUCER)
        self.assertEqual([x["task_key"] for x in proof["pending_metadata_fit_tasks"]], [FIT])
        self.assertEqual(proof["pending_own_fit_evaluations"][0]["fit_key"], FIT)
        self.assertTrue(f.selection_path.is_file())
        self.assertEqual(proof["pending_metadata_fit_tasks"][0]["data_npz_sha256"], sha(f.npz_bytes))
        self.assertEqual(f.npz_path.read_bytes(), f.npz_bytes)

    def test_waiting_running_and_terminal_transitions_keep_the_same_binding(self):
        f = self.fixture()
        waiting = f.call()
        fit = f.records[FIT]
        fit.update({
            "status": "running", "pid": 731, "process_start_ticks": "12345",
            "admission_reservation_bytes": 1 << 20,
            "admission_profile_id": "fixture-profile",
            "admission_resource_policy": {"fixture": True},
            "selection_source": str(f.selection_path),
        })
        running = f.call()
        self.assertEqual(waiting, running)
        fit.update({"status": "validated_terminal", "outcome": "successful",
                    "validation_state": "validated", "result": {"fixture": "fit complete"}})
        f.records[EVAL].update({"status": "validated_terminal", "outcome": "successful",
                                "validation_state": "validated", "result": {"fixture": "eval complete"}})
        terminal = f.call()
        self.assertEqual(waiting, terminal)

    def test_unavailable_dependency_terminal_consumer_remains_safe(self):
        f = self.fixture()
        f.records[EVAL].update({
            "status": "validated_terminal",
            "outcome": "unavailable_dependency",
            "validation_state": "validated_terminal_outcome",
        })
        proof = f.call()
        self.assertIn(EVAL, [x["task_key"] for x in proof["pending_own_fit_evaluations"]])
        self.assertEqual(proof["pending_own_fit_evaluations"][0]["fit_key"], FIT)

    def test_training_data_requires_success_validation_and_recorded_npz_sha(self):
        f = self.fixture()
        train = f.records[TRAIN]
        train["outcome"] = "failed"
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()
        train["outcome"] = "successful"
        train["result"]["validation"]["files"]["data.npz"] = "0" * 64
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()

    def test_recreated_identical_training_data_keeps_portable_contract(self):
        f = self.fixture()
        before = f.call()
        old_stat = f.npz_path.stat()
        replacement = f.npz_path.with_name("data.npz.replacement")
        replacement.write_bytes(f.npz_bytes)
        os.utime(replacement, ns=(old_stat.st_atime_ns + 1000000, old_stat.st_mtime_ns + 5000000))
        new_stat = replacement.stat()
        self.assertNotEqual((old_stat.st_dev, old_stat.st_ino), (new_stat.st_dev, new_stat.st_ino))
        os.replace(replacement, f.npz_path)
        after = f.call()
        self.assertEqual(before, after)

    def test_changed_training_data_bytes_fail_validated_sha(self):
        f = self.fixture()
        f.npz_path.write_bytes(f.npz_bytes + b"tampered")
        with self.assertRaises(ValueError):
            f.call()

    def test_training_data_path_must_be_present(self):
        f = self.fixture()
        f.npz_path.unlink()
        with self.assertRaises(ValueError):
            f.call()

    def test_terminal_unavailable_fit_without_data_is_not_an_active_reader(self):
        f = self.fixture()
        f.add_second_chain()
        f.records[TRAIN].update({
            "status": "validated_terminal", "outcome": "unavailable_dependency",
            "validation_state": "validated_terminal_outcome",
            "result": {"validation": {"status": "unavailable_dependency", "files": {}}},
        })
        f.npz_path.unlink()
        f.records[FIT].update({
            "status": "validated_terminal", "outcome": "unavailable_dependency",
            "validation_state": "validated_terminal_outcome",
        })
        f.records[EVAL].update({
            "status": "validated_terminal", "outcome": "unavailable_dependency",
            "validation_state": "validated_terminal_outcome",
        })
        f.refresh_plan()
        proof = f.call()
        self.assertEqual([x["task_key"] for x in proof["pending_metadata_fit_tasks"]], [f.second_fit])
        self.assertEqual([x["task_key"] for x in proof["pending_own_fit_evaluations"]], [f.second_eval])

    def test_reuse_pipeline_or_direct_model_reference_is_rejected(self):
        f = self.fixture()
        f.records[FIT]["reuse_pipeline"] = "/some/model/pipeline.joblib"
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()
        f.records[FIT]["reuse_pipeline"] = None
        f.records[FIT]["model_references"] = [PRODUCER]
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()

    def test_evaluation_cannot_read_the_producer_pipeline_directly(self):
        f = self.fixture()
        f.records[EVAL]["fit_key"] = PRODUCER
        f.records[EVAL]["dependencies"] = [PRODUCER]
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()

    def test_direct_model_reader_is_allowed_only_after_terminalization(self):
        f = self.fixture()
        f.records[EVAL].update({
            "status": "validated_terminal", "outcome": "successful",
            "validation_state": "validated", "fit_key": PRODUCER,
            "dependencies": [PRODUCER],
        })
        f.refresh_plan()
        proof = f.call()
        self.assertNotIn(EVAL, [x["task_key"] for x in proof["pending_own_fit_evaluations"]])

    def test_unknown_nonterminal_kind_is_rejected(self):
        f = self.fixture()
        f.records[EVAL]["kind"] = "generate"
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()

    def test_selection_key_must_be_exact_producer_and_fixed(self):
        f = self.fixture()
        f.records[FIT]["selection_key"] = "e3/rep_1/fit/synthetic/random_forest/other"
        f.refresh_plan()
        with self.assertRaises(contract._safety.UnsafePlan):
            f.call()
        f.records[FIT]["selection_key"] = PRODUCER
        f.records[FIT]["selection_mode"] = "tune"
        f.refresh_plan()
        with self.assertRaises(ValueError):
            f.call()

    def test_changed_selection_json_fails_its_validated_sha(self):
        f = self.fixture()
        f.selection_path.write_bytes(b'{"selected_params":{"n_estimators":99}}')
        with self.assertRaises(ValueError):
            f.call()

    def test_rf4_and_vanilla_worker_science_pin_mutation_fails(self):
        f = self.fixture()
        (f.source_dir / "parallel_rf" / "science.py").write_text("changed worker behavior")
        with self.assertRaises(ValueError):
            f.call()
        f2 = self.fixture()
        (f2.source_dir / "science.py").write_text("changed vanilla consumer behavior")
        with self.assertRaises(ValueError):
            f2.call()

    def test_operational_dispatcher_updates_do_not_change_consumer_contract(self):
        f = self.fixture()
        before = f.call()
        for rel in ("controller.py", "batch_plan.py", "cold_model_storage.py",
                    "commit_batch_child.py", "run_batch.py", "cold_auto_compaction.py"):
            (f.source_dir / rel).write_text("operational archive code changed:" + rel)
        self.assertEqual(before, f.call())

    def test_changed_registry_definition_fails_frozen_plan_binding(self):
        f = self.fixture()
        f.records[FIT]["route"] = "different-route"
        with self.assertRaises(ValueError):
            f.call()

    def test_contract_is_separate_from_legacy_v1_helper(self):
        source = SRC / "metadata_only_contract.py"
        self.assertEqual(sha(source.read_bytes()), contract.LEGACY_CONTRACT_SHA256)
        self.assertEqual(contract.LEGACY_PRODUCER, "e3/rep_2/fit/synthetic/random_forest/copula")


if __name__ == "__main__":
    unittest.main()
