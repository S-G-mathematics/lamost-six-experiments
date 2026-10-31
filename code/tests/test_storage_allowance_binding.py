import ast
import hashlib
import json
import pathlib
import shutil
import tempfile
import unittest

BASE = next(parent for parent in pathlib.Path(__file__).resolve().parents if (parent / "runtime_20261025").is_dir())
ACTUAL_PROJECT = next(parent for parent in BASE.parents if (parent / "operations/terminal_result_retention_v2_20261030/guardian/retention_index.json").is_file())
RUNTIME = BASE / "runtime_20261025"
CONTROLLER = RUNTIME / "source" / "controller.py"
BASELINE = RUNTIME / "source" / "controller.py.baseline_b668"
POLICY_REL = pathlib.Path("operations/working_reserve_storage_1gib_20261031/WORKING_STORAGE_POLICY_20261031.json")
POLICY_SOURCE = BASE / POLICY_REL
INDEX_REL = pathlib.Path("operations/terminal_result_retention_v2_20261030/guardian/retention_index.json")
PROTECTED = (
    "_et4_fit_eligible", "_rf4_fit_eligible", "candidate_cpu_reservation_units",
    "worker_request_definition", "worker_reservation_bytes", "worker_resource_class",
    "worker_script_for_task",
)

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def function_hashes(path):
    tree = ast.parse(path.read_text())
    found = {n.name: hashlib.sha256(ast.dump(n, include_attributes=False).encode()).hexdigest()
             for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {name: found[name] for name in PROTECTED}

def load_candidate_functions(controller_path, runtime_path):
    tree = ast.parse(controller_path.read_text())
    wanted = {"GIB", "STORAGE_DRAIN_OUTPUT_RESERVE_BYTES", "WORKING_STORAGE_POLICY"}
    assigns = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in node.targets):
            assigns.append(node)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    env = {"pathlib": pathlib, "hashlib": hashlib, "json": json,
           "R": runtime_path, "__file__": str(controller_path), "sha": sha}
    exec(compile(ast.Module(body=assigns, type_ignores=[]), str(controller_path), "exec"), env)
    selected = [functions[name] for name in (
        "storage_required_bytes", "retention_restore_budget",
        "retention_budget_matches_policy", "_storage_expected_campaign")]
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(controller_path), "exec"), env)
    return env

class StorageAllowanceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="storage-allowance-1gib-")
        self.project = pathlib.Path(self.temp.name)
        self.runtime = self.project / "runtime_20261025"
        (self.runtime / "source").mkdir(parents=True)
        shutil.copyfile(CONTROLLER, self.runtime / "source" / "controller.py")
        policy_path = self.project / POLICY_REL
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(POLICY_SOURCE, policy_path)
        index_path = self.project / INDEX_REL
        index_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ACTUAL_PROJECT / INDEX_REL, index_path)
        self.policy_path = policy_path
        self.env = load_candidate_functions(self.runtime / "source" / "controller.py", self.runtime)
        self.policy = json.loads(policy_path.read_text())
        self.frozen = {
            "storage_admission_policy": self.env["WORKING_STORAGE_POLICY"],
            "storage_admission_amendment": {
                "schema": "lamost-controller-operational-source-amendment/1",
                "candidate_controller_sha256": sha(self.runtime / "source" / "controller.py"),
                "policy_path": POLICY_REL.as_posix(),
                "policy_sha256": sha(policy_path),
            },
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_real_expected_campaign_and_retention_index_binding_pass(self):
        campaign = self.env["_storage_expected_campaign"](self.frozen)
        self.assertEqual(campaign, self.policy)
        budget = self.env["retention_restore_budget"](self.project / INDEX_REL)
        self.assertTrue(self.env["retention_budget_matches_policy"](budget, campaign))
        self.assertEqual(budget["row_count"], 2132)
        self.assertEqual(budget["restore_bytes"], 5_595_808_572)
        self.assertEqual(budget["largest_asset_bytes"], 729_545_227)

    def test_policy_byte_tamper_or_freeze_mismatch_fails_closed(self):
        data = json.loads(self.policy_path.read_text())
        data["per_active_or_new_task_output_reserve_bytes"] = 2 * 1024**3
        self.policy_path.write_text(json.dumps(data, sort_keys=True))
        self.assertIsNone(self.env["_storage_expected_campaign"](self.frozen))
        self.policy_path.write_text(json.dumps(self.policy, sort_keys=True, indent=2) + "\n")
        wrong = dict(self.frozen)
        wrong["storage_admission_policy"] = dict(self.frozen["storage_admission_policy"])
        wrong["storage_admission_policy"]["per_active_or_new_task_output_reserve_bytes"] *= 2
        self.assertIsNone(self.env["_storage_expected_campaign"](wrong))

    def test_scientific_dispatch_and_worker_ast_is_unchanged(self):
        self.assertEqual(function_hashes(CONTROLLER), function_hashes(BASELINE))

    def test_policy_path_traversal_fails_closed(self):
        bad = dict(self.frozen)
        bad["storage_admission_amendment"] = dict(self.frozen["storage_admission_amendment"])
        bad["storage_admission_amendment"]["policy_path"] = "../outside.json"
        self.assertIsNone(self.env["_storage_expected_campaign"](bad))

    def test_candidate_controller_byte_change_fails_closed(self):
        candidate = self.runtime / "source" / "controller.py"
        candidate.write_bytes(candidate.read_bytes() + b"\\n# unreviewed change\\n")
        self.assertIsNone(self.env["_storage_expected_campaign"](self.frozen))

    def test_index_content_change_breaks_campaign_budget_binding(self):
        index = self.project / INDEX_REL
        index.write_bytes(index.read_bytes() + b"\n")
        budget = self.env["retention_restore_budget"](index)
        self.assertIsNotNone(budget)
        self.assertFalse(self.env["retention_budget_matches_policy"](budget, self.policy))

    def test_malformed_index_fails_closed(self):
        index = self.project / INDEX_REL
        index.write_text("{")
        self.assertIsNone(self.env["retention_restore_budget"](index))

    def test_missing_amendment_fails_closed(self):
        self.assertIsNone(self.env["_storage_expected_campaign"]({"storage_admission_policy": self.env["WORKING_STORAGE_POLICY"]}))

if __name__ == "__main__":
    unittest.main()
