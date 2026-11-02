import hashlib
import importlib.util
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
CONTROLLER_PATH = HERE.parent / 'source' / 'controller.py'
stub = types.ModuleType("admission_evidence")
with mock.patch.dict(sys.modules, {"admission_evidence": stub}):
    spec = importlib.util.spec_from_file_location("e6_controller_for_overlay_tests", CONTROLLER_PATH)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)

METHODS = ("gmm", "copula", "arf", "kde", "chow_liu")
FEATURES = ["mag_ps_g", "mag_ps_r", "mag_ps_i", "mag_ps_z", "mag_ps_y", "gaia_g_mean_mag"]
COUNTS = [10000, 12000, 13000, 11000, 9000, 12000, 13000]
FIT_IDS = {1: "a" * 64, 2: "b" * 64, 3: "c" * 64}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value):
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def prepare_runtime(root):
    manifests = root / "manifests"
    artifacts = root / "artifacts"
    for name, content in {
        "E6_MANIFEST.json": {"protocol": "E6"},
        "build_plan.py": "fixture build plan\n",
    }.items():
        p = manifests / name if name.endswith(".json") else root / "source" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".json"):
            write_json(p, content)
        else:
            p.write_text(content, encoding="utf-8")

    role_hashes = {}
    for rep in (1, 2, 3):
        role_hashes[str(rep)] = {
            "source_sha256": str(rep) * 64,
            "id_hashes": {"fit_ids": FIT_IDS[rep]},
        }
    e3_manifest = {
        "features": FEATURES,
        "label_order": ["A", "F", "G", "K", "M", "GALAXY", "QSO"],
        "role_hashes": role_hashes,
    }
    write_json(manifests / "E3_MANIFEST.json", e3_manifest)

    plan = []
    fit_definitions = {}
    for rep in (1, 2, 3):
        members = {method: f"e3/rep_{rep}/fit/{method}" for method in METHODS}
        refs = {method: f"e3/rep_{rep}/eval/direct/{method}" for method in METHODS}
        for method, fit_key in members.items():
            fit_definitions[fit_key] = {
                "key": fit_key, "experiment": 3, "kind": "fit", "rep": rep, "method": method,
                **({"reuse_pipeline": "fixture-reconstructed-source"} if method in {"gmm", "copula", "chow_liu"} else {}),
            }
        for mode in ("equal", "learned"):
            key = f"e6/rep_{rep}/ensemble/{mode}"
            plan.append({
                "key": key, "experiment": 6, "kind": "ensemble", "rep": rep, "mode": mode,
                "condition": mode, "members": members, "member_evaluations": refs,
                "dependencies": list(members.values()), "scientific_case": True,
            })
    plan.extend(fit_definitions.values())
    write_json(manifests / "tasks.json", {"tasks": plan})

    for rep in (1, 2, 3):
        for method in METHODS:
            fit_key = f"e3/rep_{rep}/fit/{method}"
            d = artifacts / fit_key
            d.mkdir(parents=True, exist_ok=True)
            pipeline = d / "pipeline.joblib"
            pipeline.write_bytes(f"fixture pipeline {fit_key}".encode())
            pipeline_sha = sha_bytes(pipeline.read_bytes())
            selected = {"fixture_parameter": method}
            selection_path = d / "selection.json"
            write_json(selection_path, {"selected_params": selected})
            selection_sha = sha_bytes(selection_path.read_bytes())
            validation_path = d / "validation.json"
            write_json(validation_path, {
                "status": "validated", "task_key": fit_key, "bootstrap": False,
                "files": {"pipeline.joblib": pipeline_sha, "selection.json": selection_sha},
            })
            validation_sha = sha_bytes(validation_path.read_bytes())
            fit_result_path = d / "fit_result.json"
            write_json(fit_result_path, {
                "status": "successful", "artifact_sha256": pipeline_sha,
                "task": {"key": fit_key},
                "result": {"class_counts": COUNTS, "training_ids_sha256": FIT_IDS[rep], "params": selected},
            })
            fit_result_sha = sha_bytes(fit_result_path.read_bytes())

    reports = root / "reports"
    write_json(reports / "E6_EXECUTION_TERMINAL.json", {
        "planned": 21, "outcomes": {"successful": 12, "unavailable_dependency": 9},
        "observed_utc": "2026-10-25T17:13:21.075231+00:00",
    })
    for name in (
        "E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv", "E6_ENSEMBLE_MEMBER_PAIRED.csv",
        "E6_FINAL_CELL_LEDGER_21.csv", "E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json",
        "E6_FINAL_DESCRIPTIVE_REPORT.md", "E6_MEMBER_PER_REPETITION.csv",
        "E6_candidate_ledger.csv", "E6_weights.csv", "E6_balanced_accuracy_member_ensemble.png",
        "E6_coverage_member_ensemble.png", "E6_set_size_member_ensemble.png",
    ):
        p = reports / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(("fixture:" + name).encode())
    plan_sha = sha_bytes((manifests / "tasks.json").read_bytes())
    plan_by = {task["key"]: task for task in plan}
    overlay_tasks = []
    old_registry = {}
    for rep in (1, 2, 3):
        members = {method: f"e3/rep_{rep}/fit/{method}" for method in METHODS}
        refs = {method: f"e3/rep_{rep}/eval/direct/{method}" for method in METHODS}
        evidence = {}
        for method, fit_key in members.items():
            d = artifacts / fit_key
            fit = json.loads((d / "fit_result.json").read_text())
            selection = json.loads((d / "selection.json").read_text())
            validation = json.loads((d / "validation.json").read_text())
            evidence[method] = {
                "fit_key": fit_key,
                "pipeline_sha256": fit["artifact_sha256"],
                "selection_sha256": sha_bytes((d / "selection.json").read_bytes()),
                "fit_result_sha256": sha_bytes((d / "fit_result.json").read_bytes()),
                "validation_sha256": sha_bytes((d / "validation.json").read_bytes()),
                "role_membership_sha256": role_hashes[str(rep)]["source_sha256"],
                "training_ids_sha256": FIT_IDS[rep],
                "training_rows": sum(COUNTS),
                "method": method,
                "class_order": list(range(7)),
                "feature_order": FEATURES,
                "provenance_group": "e2_reconstructed" if method in {"gmm", "copula", "chow_liu"} else "e3_new_fit",
                "selected_params_sha256": canonical_sha(selection["selected_params"]),
                "class_counts": COUNTS,
            }
        for mode in ("equal", "learned"):
            key = f"e6/rep_{rep}/ensemble/{mode}"
            definition = plan_by[key]
            old = {
                **definition, "status": "validated_terminal", "outcome": "unavailable_dependency",
                "reason": refs["kde"] + ": scientific_failure", "attempts": [],
                "validation_state": "validated_terminal_outcome",
            }
            old_registry[key] = old
            overlay_tasks.append({
                "task_key": key,
                "original_task_definition_sha256": canonical_sha(definition),
                "rep": rep, "mode": mode,
                "members": members, "member_evaluations": refs,
                "effective_dependencies": sorted(members.values()),
                "e6_protocol_version": "E6-v2", "member_fit_evidence": evidence,
                "prior_registry_record_sha256": canonical_sha(old),
                "prior_status": "validated_terminal", "prior_outcome": "unavailable_dependency",
                "prior_attempt_count": 0,
            })
    overlay = {
        "schema_version": "lamost-e6-execution-overlay/2",
        "protocol_version": "E6-v2",
        "source_plan_sha256": plan_sha,
        "source_e6_manifest_sha256": controller.sha(manifests / "E6_MANIFEST.json"),
        "source_e3_manifest_sha256": controller.sha(manifests / "E3_MANIFEST.json"),
        "source_build_plan_sha256": controller.sha(root / "source" / "build_plan.py"),
        "original_plan_freeze_utc": "2026-10-25T04:46:31.018995+00:00",
        "feature_order": FEATURES,
        "label_order": e3_manifest["label_order"],
        "tasks": overlay_tasks,
    }
    write_json(manifests / "E6_EXECUTION_OVERLAY_V2.json", overlay)
    return plan, overlay, old_registry


class FailingConnection:
    def __init__(self, db, fail_key):
        self.db = db
        self.fail_key = fail_key
        self.failed = False

    def execute(self, sql, params=()):
        if sql.startswith("INSERT OR REPLACE INTO tasks") and params and params[0] == self.fail_key and not self.failed:
            self.failed = True
            raise sqlite3.OperationalError("fixture injected row-write failure")
        return self.db.execute(sql, params)

    def commit(self):
        return self.db.commit()

    def rollback(self):
        return self.db.rollback()


def make_db(old_registry):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE tasks(key TEXT PRIMARY KEY, record TEXT NOT NULL)")
    db.execute("CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, kind TEXT, record TEXT)")
    db.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    for key, value in old_registry.items():
        db.execute("INSERT INTO tasks VALUES (?,?)", (key, json.dumps(value, sort_keys=True)))
    db.commit()
    return db


class E6OverlayControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="e6-overlay-")
        self.root = Path(self.temp.name)
        self.old_root = controller.R
        controller.R = self.root
        self.plan, self.overlay, self.old_registry = prepare_runtime(self.root)

    def tearDown(self):
        controller.R = self.old_root
        self.temp.cleanup()

    def test_v1_keeps_evaluation_gate_v2_uses_only_five_fit_dependencies(self):
        task = next(x for x in self.plan if x["key"] == "e6/rep_1/ensemble/equal")
        v1 = controller.effective_dependencies(task)
        self.assertEqual(set(v1), set(task["dependencies"]) | set(task["member_evaluations"].values()))
        v2 = dict(task, e6_protocol_version="E6-v2")
        self.assertEqual(controller.effective_dependencies(v2), task["dependencies"])

    def test_overlay_binds_six_original_definitions_and_fifteen_fit_provenances(self):
        ok, reason = controller.validate_e6_execution_overlay(self.plan, self.overlay, self.root)
        self.assertTrue(ok, reason)
        self.assertEqual(len(self.overlay["tasks"]), 6)
        self.assertEqual(sum(len(x["member_fit_evidence"]) for x in self.overlay["tasks"]), 30)
        for row in self.overlay["tasks"]:
            self.assertEqual(row["prior_attempt_count"], 0)
            self.assertEqual(len(row["effective_dependencies"]), 5)
            self.assertEqual(set(row["member_evaluations"].values()), {f"e3/rep_{row['rep']}/eval/direct/{m}" for m in METHODS})

    def test_overlay_rejects_modified_role_or_fit_result_hash(self):
        changed = json.loads(json.dumps(self.overlay))
        changed["tasks"][0]["member_fit_evidence"]["kde"]["role_membership_sha256"] = "f" * 64
        ok, reason = controller.validate_e6_execution_overlay(self.plan, changed, self.root)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("overlay_fit_evidence_"))
        changed = json.loads(json.dumps(self.overlay))
        changed["tasks"][0]["member_fit_evidence"]["gmm"]["fit_result_sha256"] = "0" * 64
        ok, reason = controller.validate_e6_execution_overlay(self.plan, changed, self.root)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("overlay_fit_evidence_"))

    def test_migration_supersedes_six_rows_atomically_and_is_idempotent(self):
        db = make_db(self.old_registry)
        plan_doc = json.loads((self.root / "manifests" / "tasks.json").read_text())
        plan_sha = controller.sha(self.root / "manifests" / "tasks.json")
        overlay_path = self.root / controller.E6_OVERLAY_REL
        write_json(overlay_path, self.overlay)
        frozen = {"e6_execution_overlay_sha256": controller.sha(overlay_path),
                  "frozen_utc": self.overlay["original_plan_freeze_utc"],
                  "plan_sha256": plan_sha}
        controller.DEFINITIONS = {t["key"]: dict(t) for t in self.plan}
        tasks = controller.apply_e6_v2_execution_overlay(db, {k: v for k, v in self.old_registry.items()}, frozen)
        self.assertEqual(len([t for t in tasks.values() if t.get("e6_protocol_version") == "E6-v2"]), 6)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='e6_protocol_supersession'").fetchone()[0], 6)
        self.assertFalse((self.root / "reports" / "E6_EXECUTION_TERMINAL.json").exists())
        history = self.root / "reports" / "history" / ("e6_v1_availability_gate_" + controller.E6_OVERLAY_SHA256[:16])
        self.assertTrue((history / "E6_EXECUTION_TERMINAL.json").is_file())
        self.assertTrue((history / "E6_FINAL_CELL_LEDGER_21.csv").is_file())
        self.assertTrue((history / "SUPERSESSION_MANIFEST.json").is_file())
        for key, task in tasks.items():
            self.assertEqual(task["status"], "planned")
            self.assertEqual(task["attempts"], [])
            self.assertEqual(task["supersedes_protocol_record"]["prior_outcome"], "unavailable_dependency")
            event = db.execute("SELECT record FROM events WHERE kind='e6_protocol_supersession' AND record LIKE ?", ("%" + key + "%",)).fetchone()
            self.assertIsNotNone(event)
            saved = json.loads(event[0])["prior_task_record"]
            self.assertEqual(canonical_sha(saved), canonical_sha(self.old_registry[key]))
        controller.apply_e6_v2_execution_overlay(db, tasks, frozen)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='e6_protocol_supersession'").fetchone()[0], 6)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM meta WHERE key='e6_v2_report_supersession_sha256'").fetchone()[0], 1)

    def test_injected_row_failure_rolls_back_all_six_supersessions(self):
        db = make_db(self.old_registry)
        overlay_path = self.root / controller.E6_OVERLAY_REL
        write_json(overlay_path, self.overlay)
        frozen = {"e6_execution_overlay_sha256": controller.sha(overlay_path),
                  "frozen_utc": self.overlay["original_plan_freeze_utc"]}
        controller.DEFINITIONS = {t["key"]: dict(t) for t in self.plan}
        failing = FailingConnection(db, "e6/rep_2/ensemble/equal")
        with self.assertRaises(sqlite3.OperationalError):
            controller.apply_e6_v2_execution_overlay(failing, self.old_registry, frozen)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='e6_protocol_supersession'").fetchone()[0], 0)
        self.assertTrue((self.root / "reports" / "E6_EXECUTION_TERMINAL.json").exists())
        self.assertFalse((self.root / "reports" / "history").exists())
        for key, expected in self.old_registry.items():
            active = json.loads(db.execute("SELECT record FROM tasks WHERE key=?", (key,)).fetchone()[0])
            self.assertEqual(canonical_sha(active), canonical_sha(expected))


if __name__ == "__main__":
    unittest.main()
