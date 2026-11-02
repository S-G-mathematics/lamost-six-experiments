from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

STAGE = Path(__file__).resolve().parents[1]
RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME / "source"))
spec = importlib.util.spec_from_file_location("e6_review_controller", RUNTIME / "source" / "controller.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)

METHODS = ("gmm", "copula", "arf", "kde", "chow_liu")
E6_KEYS = [f"e6/rep_{rep}/ensemble/{mode}" for rep in (1, 2, 3) for mode in ("equal", "learned")]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fixture(tmp_path):
    root = tmp_path / "runtime"
    (root / "manifests").mkdir(parents=True)
    (root / "source").mkdir()
    (root / "source" / "build_plan.py").write_text("# fixture\n")
    reports = root / "reports"
    reports.mkdir()
    (reports / "E6_EXECUTION_TERMINAL.json").write_text(json.dumps({
        "planned": 21, "outcomes": {"successful": 12, "unavailable_dependency": 9}
    }))
    (reports / "E6_FINAL_CELL_LEDGER_21.csv").write_text("fixture ledger\n")
    (root / "manifests" / "E3_MANIFEST.json").write_text(json.dumps({"role_hashes": {}}))
    (root / "manifests" / "E6_MANIFEST.json").write_text(json.dumps({"fixture": True}))
    plan = []
    rows = []
    for key in E6_KEYS:
        rep = int(key.split("/")[1].split("_")[1])
        mode = key.rsplit("/", 1)[1]
        members = {m: f"e3/rep_{rep}/fit/generator/{m}" for m in METHODS}
        refs = {m: f"e3/rep_{rep}/eval/direct/{m}" for m in METHODS}
        task = {"key": key, "experiment": 6, "kind": "ensemble", "rep": rep,
                "mode": mode, "members": members, "member_evaluations": refs,
                "dependencies": sorted(set(members.values()))}
        plan.append(task)
        evidence = {m: {"fit_key": members[m], "method": m} for m in METHODS}
        rows.append({
            "task_key": key, "e6_protocol_version": "E6-v2",
            "original_task_definition_sha256": controller._canonical_sha256(task),
            "rep": rep, "mode": mode, "members": members, "member_evaluations": refs,
            "effective_dependencies": sorted(set(members.values())),
            "member_fit_evidence": evidence,
            "prior_status": "validated_terminal", "prior_outcome": "unavailable_dependency",
            "prior_attempt_count": 0, "prior_registry_record_sha256": "a" * 64,
        })
    for rep in (1, 2, 3):
        for method in METHODS:
            plan.append({"key": f"e3/rep_{rep}/eval/direct/{method}", "experiment": 3,
                         "kind": "alias", "rep": rep, "method": method, "dependencies": []})
    plan.extend([
        {"key": "e4/fixture", "experiment": 4, "kind": "eval", "dependencies": []},
        {"key": "e5/fixture", "experiment": 5, "kind": "eval", "dependencies": []},
    ])
    plan_path = root / "manifests" / "tasks.json"
    plan_path.write_text(json.dumps({"tasks": plan}, sort_keys=True))
    frozen_utc = "2026-10-25T04:46:31.018995+00:00"
    overlay = {
        "schema_version": "lamost-e6-execution-overlay/2",
        "protocol_version": "E6-v2",
        "source_plan_sha256": _sha(plan_path),
        "source_e6_manifest_sha256": _sha(root / "manifests" / "E6_MANIFEST.json"),
        "source_e3_manifest_sha256": _sha(root / "manifests" / "E3_MANIFEST.json"),
        "source_build_plan_sha256": _sha(root / "source" / "build_plan.py"),
        "original_plan_freeze_utc": frozen_utc,
        "tasks": rows,
    }
    overlay_path = root / "manifests" / controller.E6_OVERLAY_REL.split("/", 1)[1]
    overlay_path.write_text(json.dumps(overlay, sort_keys=True))
    return root, plan, overlay, frozen_utc, overlay_path


def _patch_fit_validation(monkeypatch):
    # This isolates the overlay schema/supersession transaction. Production fit
    # evidence is checked separately by _overlay_fit_evidence_valid.
    monkeypatch.setattr(controller, "_overlay_fit_evidence_valid", lambda *args: True)


def test_overlay_requires_exact_six_original_ensemble_definitions(tmp_path, monkeypatch):
    root, plan, overlay, _, _ = _fixture(tmp_path)
    _patch_fit_validation(monkeypatch)
    assert controller.validate_e6_execution_overlay(plan, overlay, root) == (True, "validated")
    bad = json.loads(json.dumps(overlay))
    bad["tasks"][0]["effective_dependencies"] = []
    assert controller.validate_e6_execution_overlay(plan, bad, root)[0] is False
    bad = json.loads(json.dumps(overlay))
    bad["tasks"].pop()
    assert controller.validate_e6_execution_overlay(plan, bad, root)[0] is False


def test_overlay_rejects_any_started_or_changed_prior_record(tmp_path, monkeypatch):
    root, plan, overlay, _, _ = _fixture(tmp_path)
    _patch_fit_validation(monkeypatch)
    bad = json.loads(json.dumps(overlay))
    bad["tasks"][0]["prior_attempt_count"] = 1
    assert controller.validate_e6_execution_overlay(plan, bad, root)[0] is False
    bad = json.loads(json.dumps(overlay))
    bad["tasks"][0]["member_evaluations"]["kde"] = "changed/reference"
    assert controller.validate_e6_execution_overlay(plan, bad, root)[0] is False


def test_apply_supersedes_exact_six_and_preserves_e3_e4_e5_rows(tmp_path, monkeypatch):
    root, plan, overlay, frozen_utc, overlay_path = _fixture(tmp_path)
    _patch_fit_validation(monkeypatch)
    controller.R = root
    controller.DEFINITIONS = {t["key"]: dict(t) for t in plan}
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE tasks(key TEXT PRIMARY KEY, record TEXT);
        CREATE TABLE events(timestamp TEXT, kind TEXT, record TEXT);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    initial = {}
    for task in plan:
        key = task["key"]
        if key.startswith("e6/"):
            row = next(x for x in overlay["tasks"] if x["task_key"] == key)
            record = {"key": key, "status": "validated_terminal", "outcome": "unavailable_dependency",
                      "validation_state": "validated_terminal", "attempts": [],
                      "reason": "historical E3 direct evaluation dependency"}
            row["prior_registry_record_sha256"] = controller._canonical_sha256(record)
        elif key.startswith("e3/rep_"):
            unavailable = key.endswith("/kde")
            record = {"key": key, "status": "validated_terminal",
                      "outcome": "unavailable_dependency" if unavailable else "successful",
                      "attempts": [{"id": "preserve-original-attempt"}]}
        else:
            record = {"key": key, "status": "successful", "outcome": "successful", "attempts": [{"id": "keep"}]}
        initial[key] = record
        connection.execute("INSERT INTO tasks(key,record) VALUES (?,?)", (key, json.dumps(record, sort_keys=True)))
    connection.commit()
    overlay["source_plan_sha256"] = _sha(root / "manifests" / "tasks.json")
    overlay["tasks"] = overlay["tasks"]
    overlay_path.write_text(json.dumps(overlay, sort_keys=True))
    overlay_sha = _sha(overlay_path)
    controller.E6_OVERLAY_REL = "manifests/E6_EXECUTION_OVERLAY_V2.json"
    frozen = {"e6_execution_overlay_sha256": overlay_sha, "frozen_utc": frozen_utc}
    # A changed current attempt must fail before any E6 row/event/report mutation.
    bad_key = E6_KEYS[0]
    changed = dict(initial[bad_key])
    changed["attempts"] = [{"attempt_id": "already-started"}]
    connection.execute("UPDATE tasks SET record=? WHERE key=?", (json.dumps(changed), bad_key))
    connection.commit()
    try:
        controller.apply_e6_v2_execution_overlay(connection, controller.load(connection), frozen)
    except RuntimeError as exc:
        assert "zero-attempt" in str(exc)
    else:
        raise AssertionError("overlay superseded a task after a scientific attempt started")
    assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert controller.load(connection)[bad_key] == changed
    connection.execute("UPDATE tasks SET record=? WHERE key=?", (json.dumps(initial[bad_key], sort_keys=True), bad_key))
    connection.commit()
    result = controller.apply_e6_v2_execution_overlay(connection, controller.load(connection), frozen)
    assert sum(1 for x in result.values() if x.get("e6_protocol_version") == "E6-v2") == 6
    assert connection.execute("SELECT COUNT(*) FROM events WHERE kind='e6_protocol_supersession'").fetchone()[0] == 6
    for key in E6_KEYS:
        row = result[key]
        assert row["status"] == "planned" and row["attempts"] == []
        event = json.loads(connection.execute("SELECT record FROM events WHERE kind='e6_protocol_supersession' AND record LIKE ?", (f"%{key}%",)).fetchone()[0])
        assert event["prior_task_record"] == initial[key]
    for key in ("e4/fixture", "e5/fixture"):
        assert result[key] == initial[key]
    e3_keys = [key for key in initial if key.startswith("e3/rep_")]
    assert len(e3_keys) == 15
    for key in e3_keys:
        assert result[key] == initial[key]
    history = root / "reports" / "history"
    archived = list(history.glob("e6_v1_availability_gate_*"))
    assert len(archived) == 1
    assert (archived[0] / "E6_EXECUTION_TERMINAL.json").is_file()
    assert (archived[0] / "E6_FINAL_CELL_LEDGER_21.csv").is_file()
    assert (archived[0] / "SUPERSESSION_MANIFEST.json").is_file()
    # Reapplying is idempotent and does not create a second supersession event.
    controller.apply_e6_v2_execution_overlay(connection, result, frozen)
    assert connection.execute("SELECT COUNT(*) FROM events WHERE kind='e6_protocol_supersession'").fetchone()[0] == 6
