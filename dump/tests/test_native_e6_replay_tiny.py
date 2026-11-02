from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "source"

sys.path.insert(0, str(VALIDATION))

import importlib.util
from unittest import mock

def _load_calibration_replay():
    spec = importlib.util.spec_from_file_location("fixture_calibration_replay_e6", ROOT / "source" / "calibration_replay.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

_audit_spec = importlib.util.spec_from_file_location("e6_staged_audit_artifacts", VALIDATION / "audit_artifacts.py")
audit_artifacts = importlib.util.module_from_spec(_audit_spec)
_audit_spec.loader.exec_module(audit_artifacts)


class Identity:
    def transform(self, x):
        return np.asarray(x)


class FakeFlexibleModel:
    method = "gmm"
    score_kind = "probability"
    class_models = [object() for _ in range(7)]
    priors = np.full(7, 1 / 7)

    def __init__(self):
        self.calls = 0

    def score_matrix(self, x):
        self.calls += 1
        x = np.asarray(x)
        y = x[:, 0].astype(int)
        scores = np.full((len(y), 7), 0.2 / 6, dtype=float)
        scores[np.arange(len(y)), y] = 0.8
        return scores


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _task(key, mode, fitkey, evidence):
    return {
        "key": key, "experiment": 6, "kind": "ensemble", "e6_protocol_version": "E6-v2",
        "rep": 1, "mode": mode, "members": {"gmm": fitkey},
        "member_fit_evidence": {"gmm": evidence},
        "status": "validated_terminal", "outcome": "successful",
    }


def test_native_q_replay_scores_only_calibration_once_for_shared_ensemble_consumers(tmp_path, monkeypatch):
    cr = _load_calibration_replay()
    derive = cr.derive
    monkeypatch.setattr(cr, "file_sha", lambda path: _sha(ROOT / "source" / "calibration_replay.py"))
    rt = tmp_path
    fitkey = "e3/rep_1/fit/generator/gmm"
    fitdir = rt / "artifacts" / fitkey
    fitdir.mkdir(parents=True)
    pipeline = fitdir / "pipeline.joblib"
    pipeline.write_bytes(b"fixture pipeline identity only; never deserialized")
    role_dir = rt / "cache" / "roles"
    role_dir.mkdir(parents=True)
    ycal = np.arange(14, dtype=np.int64) % 7
    Xcal = np.zeros((14, 6), dtype=float)
    Xcal[:, 0] = ycal
    ids = np.arange(100, 114, dtype=np.int64)
    role_path = role_dir / "rep_1.npz"
    np.savez_compressed(role_path, X_cal=Xcal, y_cal=ycal, calibration_ids=ids)

    model = FakeFlexibleModel()
    fit_counts = [1] * 7
    pipe = {
        "model": model, "imputer": Identity(), "scaler": Identity(),
        "class_counts": fit_counts, "training_rows": sum(fit_counts),
    }
    frozen_module = types.SimpleNamespace(_FlexibleModel=FakeFlexibleModel)
    auditor = audit_artifacts.Auditor(rt, require_calibration_replay=True, replay_run_nonce="tiny-e6-native")
    auditor._frozen_scoring_source = lambda method: (frozen_module, "frozen-score-source-sha", "frozen-e1-report-sha")
    auditor._write_calibration_replay_progress = lambda *args, **kwargs: None

    fit_task = {
        "key": fitkey, "rep": 1, "method": "gmm",
        "result": {"result": {"class_counts": fit_counts}},
    }
    evidence = {
        "fit_ids_sha256": hashlib.sha256(np.arange(7, dtype=np.int64).tobytes()).hexdigest(),
        "role_membership_sha256": "role-membership-sha",
        "selection_sha256": "selection-sha",
        "fit_result_sha256": "fit-result-sha",
        "validation_sha256": "validation-sha",
        "selected_params_sha256": "selected-params-sha",
        "provenance_group": "e3_new_fit",
    }
    tasks = [
        _task("e6/rep_1/ensemble/equal", "equal", fitkey, evidence),
        _task("e6/rep_1/ensemble/learned", "learned", fitkey, evidence),
    ]
    for task in tasks:
        out = rt / "artifacts" / task["key"]
        out.mkdir(parents=True)
        q = derive(FakeFlexibleModel().score_matrix(Xcal), ycal, "probability")["threshold"]
        comp = {
            "protocol_version": "E6-v2", "comparison_source_task_key": task["key"],
            "members": {"gmm": {
                "fit_key": fitkey, "pipeline_sha256": _sha(pipeline),
                "role_membership_sha256": evidence["role_membership_sha256"],
                "selection_sha256": evidence["selection_sha256"],
                "fit_result_sha256": evidence["fit_result_sha256"],
                "validation_sha256": evidence["validation_sha256"],
                "score_kind": "probability", "alpha": .1,
                "calibration_n": len(ycal), "calibration_threshold": q,
            }},
        }
        comp_path = out / "member_comparisons.json"
        comp_path.write_text(json.dumps(comp, sort_keys=True))
        (out / "evaluation.json").write_text(json.dumps({"member_comparisons_sha256": _sha(comp_path)}))

    eval_task = {"key": "e3/rep_1/eval/direct/gmm", "experiment": 3, "kind": "eval",
                 "rep": 1, "fit_key": fitkey, "status": "validated_terminal", "outcome": "successful"}
    eval_out = rt / "artifacts" / eval_task["key"]
    eval_out.mkdir(parents=True)
    (eval_out / "evaluation.json").write_text(json.dumps({
        "threshold": .2, "calibration_n": len(ycal), "score_kind": "probability",
        "fit_key": fitkey, "pipeline_sha256": _sha(pipeline),
    }))
    bykey = {t["key"]: t for t in [fit_task, eval_task, *tasks]}
    with mock.patch.dict(sys.modules, {"calibration_replay": cr}):
        auditor._replay_fit_calibrations(fit_task, bykey, pipe, pipeline)

    assert model.calls == 1, auditor.calibration_replay_physical
    assert hasattr(auditor, "e6_member_calibration_records"), list(auditor.__dict__)
    assert all(r["status"] == "validated" for r in auditor.e6_member_calibration_records)
    assert len(auditor._e6_native_calibration_scores[fitkey]["scores"]) == len(ycal)
    assert not (rt / "cache" / "e6_posteriors").exists()
    events = [json.loads(line) for line in auditor.calibration_replay_phase_ledger_path.read_text().splitlines()]
    expected_consumers = sorted([eval_task["key"], *(t["key"] for t in tasks)])
    assert [(r["event"], r["task_keys"]) for r in events] == [
        ("start", expected_consumers),
        ("finish", expected_consumers),
    ]


def test_native_q_replay_rejects_saved_threshold_that_differs_from_fresh_model_score(tmp_path, monkeypatch):
    # Exact implementation path is exercised above; here corrupt the saved q and
    # confirm the native replay records a mismatch rather than trusting the sidecar.
    cr = _load_calibration_replay()
    derive = cr.derive
    monkeypatch.setattr(cr, "file_sha", lambda path: _sha(ROOT / "source" / "calibration_replay.py"))
    rt = tmp_path
    fitkey = "e3/rep_1/fit/generator/gmm"
    fitdir = rt / "artifacts" / fitkey
    fitdir.mkdir(parents=True)
    pipeline = fitdir / "pipeline.joblib"
    pipeline.write_bytes(b"fixture pipeline identity only")
    role_dir = rt / "cache" / "roles"; role_dir.mkdir(parents=True)
    ycal = np.arange(14, dtype=np.int64) % 7
    Xcal = np.zeros((14, 6), dtype=float); Xcal[:, 0] = ycal
    ids = np.arange(14, dtype=np.int64)
    np.savez_compressed(role_dir / "rep_1.npz", X_cal=Xcal, y_cal=ycal, calibration_ids=ids)
    model = FakeFlexibleModel()
    counts = [1] * 7
    pipe = {"model": model, "imputer": Identity(), "scaler": Identity(), "class_counts": counts, "training_rows": 7}
    auditor = audit_artifacts.Auditor(rt, require_calibration_replay=True, replay_run_nonce="tiny-e6-native-badq")
    auditor._frozen_scoring_source = lambda method: (types.SimpleNamespace(_FlexibleModel=FakeFlexibleModel), "score-sha", "report-sha")
    auditor._write_calibration_replay_progress = lambda *args, **kwargs: None
    evidence = {"fit_ids_sha256": "fitids", "role_membership_sha256": "role", "selection_sha256": "sel",
                "fit_result_sha256": "fit", "validation_sha256": "val", "selected_params_sha256": "params",
                "provenance_group": "e3_new_fit"}
    task = _task("e6/rep_1/ensemble/equal", "equal", fitkey, evidence)
    out = rt / "artifacts" / task["key"]; out.mkdir(parents=True)
    good_q = derive(FakeFlexibleModel().score_matrix(Xcal), ycal, "probability")["threshold"]
    comp = {"protocol_version": "E6-v2", "comparison_source_task_key": task["key"],
            "members": {"gmm": {"fit_key": fitkey, "pipeline_sha256": _sha(pipeline),
             "role_membership_sha256": "role", "selection_sha256": "sel", "fit_result_sha256": "fit",
             "validation_sha256": "val", "score_kind": "probability", "alpha": .1,
             "calibration_n": len(ycal), "calibration_threshold": good_q + .02}}}
    cp = out / "member_comparisons.json"; cp.write_text(json.dumps(comp, sort_keys=True))
    (out / "evaluation.json").write_text(json.dumps({"member_comparisons_sha256": _sha(cp)}))
    fit_task = {"key": fitkey, "rep": 1, "method": "gmm", "result": {"result": {"class_counts": counts}}}
    with mock.patch.dict(sys.modules, {"calibration_replay": cr}):
        auditor._replay_fit_calibrations(fit_task, {fitkey: fit_task, task["key"]: task}, pipe, pipeline)
    row = auditor.e6_member_calibration_records[0]
    assert model.calls == 1, auditor.calibration_replay_physical
    assert row["status"] == "mismatch"
    assert any("fresh native calibration score" in x for x in row["reasons"])
