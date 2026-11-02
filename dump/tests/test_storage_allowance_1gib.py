from pathlib import Path
import ast, hashlib, json, unittest

BASE = next(parent for parent in Path(__file__).resolve().parents if (parent / "runtime_20261025").is_dir())
GIB = 1024**3

class StorageAllowance1GiBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BASE / "runtime_20261025" / "source" / "controller.py"
        cls.policy_path = BASE / "operations" / "working_reserve_storage_1gib_20261031" / "WORKING_STORAGE_POLICY_20261031.json"
        cls.policy = json.loads(cls.policy_path.read_text())
        cls.tree = ast.parse(cls.source.read_text())
        cls.fn = next(n for n in cls.tree.body if isinstance(n, ast.FunctionDef) and n.name == "storage_required_bytes")
        env = {
            "GIB": GIB,
            "WORKING_STORAGE_POLICY": {
                "working_reserve_bytes": cls.policy["working_reserve_bytes"],
                "maximum_restore_bytes": cls.policy["maximum_restore_bytes"],
                "maximum_single_restore_asset_bytes": cls.policy["maximum_single_restore_asset_bytes"],
                "per_active_or_new_task_output_reserve_bytes": cls.policy["per_active_or_new_task_output_reserve_bytes"],
            },
        }
        exec(compile(ast.Module(body=[cls.fn], type_ignores=[]), str(cls.source), "exec"), env)
        cls.storage_required_bytes = staticmethod(env["storage_required_bytes"])

    def test_candidate_controller_and_policy_bind_each_other(self):
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.policy["controller_candidate_sha256"])
        bind = self.policy["freeze_binding_value"]
        self.assertEqual(bind["policy_id"], self.policy["policy_id"])
        self.assertEqual(bind["per_active_or_new_task_output_reserve_bytes"], GIB)
        assignments = [n for n in self.tree.body if isinstance(n, ast.Assign)]
        reserve = next(n for n in assignments if any(isinstance(t, ast.Name) and t.id == "STORAGE_DRAIN_OUTPUT_RESERVE_BYTES" for t in n.targets))
        self.assertIsInstance(reserve.value, ast.Name)
        self.assertEqual(reserve.value.id, "GIB")

    def test_zero_active_admission_reserves_one_gib(self):
        got = self.storage_required_bytes(self.policy["retention_restore_bytes"], self.policy["largest_restore_asset_bytes"], 0)
        self.assertEqual(got, self.policy["required_free_bytes_no_active_tasks"])
        self.assertEqual(got, 13_841_546_567)

    def test_one_active_task_plus_candidate_reserves_two_gib_total(self):
        got = self.storage_required_bytes(self.policy["retention_restore_bytes"], self.policy["largest_restore_asset_bytes"], 1)
        self.assertEqual(got, self.policy["required_free_bytes_one_active_task_before_next_admission"])
        self.assertEqual(got, 14_915_288_391)

    def test_restore_and_scientific_limits_remain_unchanged(self):
        self.assertEqual(self.policy["working_reserve_bytes"], 6 * GIB)
        self.assertEqual(self.policy["maximum_concurrent_fit_tasks"], 1)
        self.assertEqual(self.policy["maximum_restore_bytes"], 10 * GIB)
        self.assertEqual(self.policy["maximum_single_restore_asset_bytes"], GIB)
        limits = self.policy["unchanged_scientific_resource_limits"]
        self.assertEqual(limits["worker_hard_limit_bytes"], 10 * GIB)
        self.assertEqual(limits["trial_timeout_seconds"], 600)
        self.assertEqual(limits["phase_timeout_seconds"], 600)
        self.assertEqual(limits["termination_grace_seconds"], 30)

    def test_invalid_restore_budget_still_fails_closed(self):
        self.assertIsNone(self.storage_required_bytes(10 * GIB + 1, 1, 0))
        self.assertIsNone(self.storage_required_bytes(1, GIB + 1, 0))

if __name__ == "__main__":
    unittest.main()
