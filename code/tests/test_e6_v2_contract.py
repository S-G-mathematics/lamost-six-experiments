from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np

STAGE = Path(__file__).resolve().parents[1]
ENGINE = STAGE / "source"
PROJECT = STAGE / "source"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(PROJECT))

spec = importlib.util.spec_from_file_location("e6_review_ensemble", ENGINE / "ensemble.py")
ensemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ensemble)

MEMBERS = ("gmm", "copula", "arf", "kde", "chow_liu")


def _members():
    return {name: f"e3/rep_1/fit/generator/{name}" for name in MEMBERS}


def _failed_e3_refs():
    return {name: f"e3/rep_1/eval/direct/{name}" for name in MEMBERS}


def test_v2_ready_uses_five_fit_keys_even_when_e3_evaluation_refs_failed():
    task = {
        "e6_protocol_version": "E6-v2",
        "members": _members(),
        "member_evaluations": _failed_e3_refs(),
        "member_evaluation_dependency_observations": {
            key: {"status": "validated_terminal", "outcome": "scientific_failure",
                  "reason": "historical direct evaluation timeout"}
            for key in _failed_e3_refs().values()
        },
    }
    result = ensemble._member_evaluation_preflight(task)
    assert result["state"] == "ready"
    assert result["dependency_basis"] == "five_selected_fits"


def test_v2_missing_selected_fit_stays_unavailable():
    members = _members()
    del members["kde"]
    task = {"e6_protocol_version": "E6-v2", "members": members}
    result = ensemble._member_evaluation_preflight(task)
    assert result["state"] == "unavailable"
    assert "kde" in result["missing_members"]


def test_v1_keeps_historical_direct_evaluation_gate():
    refs = _failed_e3_refs()
    task = {
        "members": _members(),
        "member_evaluations": refs,
        "member_evaluation_dependency_observations": {
            key: {"status": "validated_terminal", "outcome": "scientific_failure"}
            for key in refs.values()
        },
    }
    result = ensemble._member_evaluation_preflight(task)
    assert result["state"] == "unavailable"


def test_posterior_accepts_only_finite_nonnegative_normalized_seven_class_rows():
    good = np.full((2, 7), 1.0 / 7.0)
    assert ensemble._posterior(good, "fixture").shape == (2, 7)
    for bad in (
        np.full((2, 6), 1.0 / 6.0),
        np.full((2, 7), 0.2),
        np.array([[1.1, -0.1, 0, 0, 0, 0, 0]], dtype=float),
        np.array([[np.nan, 0, 0, 0, 0, 0, 0]], dtype=float),
        np.array([1, 0, 0, 0, 0, 0, 0], dtype=float),
    ):
        try:
            ensemble._posterior(bad, "fixture")
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid posterior fixture: {bad!r}")


def test_finite_sample_conformal_quantile_and_member_metrics_match_protocol():
    from benchmark import evaluation
    # n_cal=9, alpha=.1 => k=ceil(10*.9)=9; largest nonconformity is selected.
    y_cal = np.arange(9, dtype=np.int64) % 7
    cal = np.full((9, 7), 0.01, dtype=float)
    cal[np.arange(9), y_cal] = 0.94
    q = evaluation.conformal_threshold(cal, y_cal, score_kind="probability", alpha=0.1)
    assert np.isclose(q, 0.06)
    y_test = np.arange(7, dtype=np.int64)
    test = np.eye(7, dtype=float)
    result = evaluation.conformal_evaluate(test, y_test, q, score_kind="probability")
    assert result["balanced_accuracy"] == 1.0
    assert result["coverage"] == 1.0
    assert result["set_size"] == 1.0
    assert result["per_class"][0]["n"] == 1


def test_member_comparison_payload_consumes_tuning_posteriors_for_tuning_best():
    # Contract fixture: test is deliberately worse for one member. The selected
    # tuning-best must come from tuning posteriors, never test outcomes.
    from benchmark import evaluation
    tune_scores = {m: np.eye(7, dtype=float) for m in MEMBERS}
    tune_scores["copula"] = np.roll(np.eye(7, dtype=float), 1, axis=1)
    cal_scores = {m: np.eye(7, dtype=float) for m in MEMBERS}
    test_scores = {m: np.eye(7, dtype=float) for m in MEMBERS}
    test_scores["gmm"] = np.roll(np.eye(7, dtype=float), 1, axis=1)
    y = np.arange(7, dtype=np.int64)
    result = ensemble._member_comparison_payload(
        task={"key": "e6/rep_1/ensemble/equal", "rep": 1},
        members=_members(),
        model_hashes={m: f"model-{m}" for m in MEMBERS},
        fit_hashes={m: "fit-ids" for m in MEMBERS},
        member_fit_evidence={m: {"role_membership_sha256": "roles", "selection_sha256": "selection", "fit_result_sha256": "fit-result", "validation_sha256": "validation", "selected_params_sha256": "params", "provenance_group": "e3_new_fit"} for m in MEMBERS},
        fingerprint={"input": "fixture"},
        tune_scores=tune_scores,
        tune_ids=np.arange(7),
        cal_ids=np.arange(10, 17),
        test_ids=np.arange(20, 27),
        phase_times={},
        cal_scores=cal_scores,
        test_scores=test_scores,
        y_tune=y,
        y_cal=y,
        y_test=y,
        weights=np.full(5, .2),
        mode="equal",
        weights_obj=None,
        ensemble_threshold=.06,
        ensemble_result=evaluation.conformal_evaluate(np.eye(7), y, .06),
        evaluator=evaluation,
        candidate_ledger_path=None,
        candidate_ledger_sha256=None,
        weights_frozen_utc="fixture",
    )
    assert result["tuning_best_member"] == "gmm"
    assert result["members"]["gmm"]["evaluation"]["balanced_accuracy"] < 1
    assert result["members"]["copula"]["evaluation"]["balanced_accuracy"] == 1
    assert result["weights_frozen_before_calibration_and_test"] is True

def test_v2_role_cohorts_have_exact_sizes_classes_unique_ids_and_no_overlap():
    # Small in-memory fixture at protocol row counts; no models or test inference.
    n_fit, n_other, n_test = 80000, 10000, 500000
    def labels(n):
        return np.arange(n, dtype=np.int64) % 7
    roles = {
        "X_fit": np.zeros((n_fit, 6), dtype=np.float32), "y_fit": labels(n_fit),
        "fit_ids": np.arange(n_fit, dtype=np.int64),
        "X_tune": np.zeros((n_other, 6), dtype=np.float32), "y_tune": labels(n_other),
        "tuning_ids": np.arange(n_fit, n_fit+n_other, dtype=np.int64),
        "X_cal": np.zeros((n_other, 6), dtype=np.float32), "y_cal": labels(n_other),
        "calibration_ids": np.arange(n_fit+n_other, n_fit+2*n_other, dtype=np.int64),
    }
    test = {
        "X": np.zeros((n_test, 6), dtype=np.float32), "y": labels(n_test),
        "ids": np.arange(n_fit+2*n_other, n_fit+2*n_other+n_test, dtype=np.int64),
    }
    assert ensemble._e6_v2_validate_roles(roles, test, 1) is None
    overlap = dict(roles)
    overlap["tuning_ids"] = roles["fit_ids"][:n_other]
    try:
        ensemble._e6_v2_validate_roles(overlap, test, 1)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("overlapping fitting/tuning identities were accepted")

def test_weight_freeze_is_written_before_calibration_and_test_phase_calls():
    source = (ENGINE / "ensemble.py").read_text()
    freeze = source.index("_json(out/'frozen_weights.json'")
    calibration = source.index("cal_scores=get_stage('cal'")
    test = source.index("test_scores=get_stage('test'")
    assert freeze < calibration < test


def test_shared_scientific_phase_failure_blocks_second_mode_and_recovery():
    import json
    from ensemble_maintenance_patch import E6PhaseFailure, E6CachedPhaseFailure
    fingerprint = {"fit": "same-five-models", "roles": "same-split"}
    shared = STAGE / "review_tmp_failure_cache"
    if shared.exists():
        import shutil
        shutil.rmtree(shared)
    calls = []
    def timeout_runner():
        calls.append("first")
        raise RuntimeError("prediction_timeout: {'reason': 'timeout', 'seconds': 600.0, 'peak_tree_rss_kib': 1234, 'exit_code': -15}")
    try:
        ensemble.run_phase_with_terminal_failure_cache(
            stage="tune", shared_dir=shared, fingerprint=fingerprint,
            mode="equal", task_key="e6/rep_1/ensemble/equal", runner=timeout_runner)
    except E6PhaseFailure:
        pass
    else:
        raise AssertionError("first evidenced timeout did not become a terminal phase failure")
    marker = shared / "tune.scientific_failure.json"
    record = json.loads(marker.read_text())
    assert record["failure_code"] == "prediction_timeout"
    def forbidden_runner():
        calls.append("must-not-run")
        raise AssertionError("cached phase failure repeated scientific work")
    try:
        ensemble.run_phase_with_terminal_failure_cache(
            stage="tune", shared_dir=shared, fingerprint=fingerprint,
            mode="learned", task_key="e6/rep_1/ensemble/learned", runner=forbidden_runner)
    except E6CachedPhaseFailure:
        pass
    else:
        raise AssertionError("paired mode did not reuse the exact shared terminal failure")
    try:
        ensemble.run_phase_with_terminal_failure_cache(
            stage="tune", shared_dir=shared, fingerprint=fingerprint,
            mode="equal", task_key="e6/rep_1/ensemble/equal", runner=forbidden_runner)
    except E6PhaseFailure:
        pass
    else:
        raise AssertionError("same-task recovery did not remain terminal")
    assert calls == ["first"]
    import shutil
    shutil.rmtree(shared)
