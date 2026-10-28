"""Small temporary artifact fixtures; these are not benchmark results."""
import json
import numpy as np

from benchmark.report_e1 import build_report
from benchmark.evaluation import bootstrap_outcomes


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_summarizer_reports_run_metrics_and_matched_differences(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "run_config.json", {"experiment": 1, "repetitions": 2, "pilot_development_only": False})
    values = {
        (1, "gmm"): (.8, 2.0, .9),
        (1, "logistic"): (.7, 3.0, .91),
        (2, "gmm"): (.82, 2.2, .89),
    }
    for (rep, method), (ba, size, coverage) in values.items():
        cell = root / f"e1/rep_{rep}/n_3000/{method}"
        complete = {"status": "complete", "balanced_accuracy": ba, "set_size": size,
                    "coverage": coverage, "per_class": {str(i): {"recall": ba, "coverage": coverage}
                                                            for i in range(7)}}
        _write_json(cell / "complete.json", complete)
    report = build_report(root)
    assert report["cell_counts"] == {"successful_test_evaluation": 3}
    gmm = next(x for x in report["method_budget_summaries"] if x["method"] == "gmm")
    assert gmm["successful_repetitions"] == 2
    assert gmm["metrics"]["balanced_accuracy"]["mean"] == .81
    comparison = report["paired_comparisons"][0]
    assert comparison["method_a"] == "gmm"
    assert comparison["method_b"] == "logistic"
    assert comparison["differences"]["balanced_accuracy"]["per_repetition"] == [
        {"repetition": 1, "difference": .10000000000000009}]
    assert report["bootstrap"] is None  # full test bootstrap is opt-in


def test_pilot_failures_are_not_reported_as_scientific_failures(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "run_config.json", {"experiment": 1, "repetitions": 1,
                                              "pilot_development_only": True})
    failed = root / "e1/rep_1/n_100/cart"
    _write_json(failed / "manifest.json", {"status": "failed", "error": "TypeError: API signature mismatch"})
    completed = root / "e1/rep_1/n_100/gmm"
    _write_json(completed / "complete.json", {"status": "complete", "balanced_accuracy": None,
                                                "set_size": None, "coverage": None})
    report = build_report(root)
    classes = {x["method"]: x["classification"] for x in report["cells"]}
    assert classes["cart"] == "pilot_integration_or_runtime_failure"
    assert classes["gmm"] == "pilot_completed_no_test_evaluation"
    assert "scientific_model_or_support_failure" not in classes.values()


def test_nonpilot_failures_keep_scientific_and_integration_categories_distinct(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "run_config.json", {"experiment": 1, "repetitions": 1,
                                              "pilot_development_only": False})
    for method, error in (("gmm", "ValueError: unsupported: fitting role lacks one or more classes"),
                          ("lda", "TypeError: API constructor mismatch")):
        cell = root / f"e1/rep_1/n_100/{method}"
        _write_json(cell / "manifest.json", {"status": "failed", "error": error})
    report = build_report(root)
    classes = {x["method"]: x["classification"] for x in report["cells"]}
    assert classes == {"gmm": "scientific_model_or_support_failure", "lda": "integration_failure"}


def test_run_config_grid_counts_cells_that_never_created_artifacts(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "run_config.json", {"experiment": 1, "repetitions": 2,
        "budgets": [100], "methods": ["gmm", "cart"], "pilot_development_only": False})
    _write_json(root / "e1/rep_1/n_100/gmm/complete.json", {
        "status": "complete", "balanced_accuracy": .7, "set_size": 2., "coverage": .9})
    report = build_report(root)
    assert report["cell_counts"] == {
        "not_started_or_no_cell_artifact": 3,
        "successful_test_evaluation": 1,
    }


def test_master_run_config_controls_expected_grid_over_child_config(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "master_run_config.json", {"experiment": 1, "repetitions": 2,
        "budgets": [100, 300], "methods": ["gmm", "cart"], "trials_override": 3,
        "pilot_development_only": True})
    # Child config represents only the last one-cell supervisor invocation.
    _write_json(root / "run_config.json", {"experiment": 1, "repetitions": 1,
        "budgets": [100], "methods": ["gmm"], "pilot_development_only": True})
    _write_json(root / "e1/rep_1/n_100/gmm/complete.json", {"status": "complete"})
    report = build_report(root)
    assert report["grid_config_source"] == "master_run_config.json"
    assert report["effective_run_config"]["trials_override"] == 3
    assert report["cell_counts"] == {
        "not_started_or_no_cell_artifact": 7,
        "pilot_completed_no_test_evaluation": 1,
    }


def test_failure_classification_reads_trial_errors_and_supervisor_markers(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "master_run_config.json", {"experiment": 1, "repetitions": 1,
        "budgets": [300], "methods": ["arf", "lda", "gmm"], "pilot_development_only": False})
    _write_json(root / "e1/rep_1/n_300/arf/manifest.json", {
        "status": "failed", "error": "RuntimeError: all hyperparameter trials failed",
        "trials": [{"number": 0, "status": "failed",
                    "error": "ValueError: ARF min_leaf 5 exceeds class support 3"}]})
    _write_json(root / "e1/rep_1/n_300/lda/manifest.json", {
        "status": "failed", "error": "RuntimeError: all hyperparameter trials failed",
        "trials": [{"number": 0, "status": "failed", "error": "TypeError: API constructor mismatch"},
                    {"number": 1, "status": "failed", "error": "ValueError: unsupported tiny support"}]})
    _write_json(root / "e1/rep_1/n_300/gmm/manifest.json", {
        "status": "failed", "error": "worker did not finish", "phase_timeout": True})
    report = build_report(root)
    by_method = {x["method"]: x for x in report["cells"]}
    assert by_method["arf"]["classification"] == "scientific_model_or_support_failure"
    assert by_method["arf"]["failure_evidence_categories"] == ["scientific_model_or_support_failure"]
    assert by_method["lda"]["classification"] == "integration_failure"
    assert set(by_method["lda"]["failure_evidence_categories"]) == {
        "integration_failure", "scientific_model_or_support_failure"}
    assert by_method["gmm"]["classification"] == "resource_failure"


def test_pilot_trial_errors_never_count_as_scientific_evidence(tmp_path):
    root = tmp_path / "results"
    _write_json(root / "master_run_config.json", {"experiment": 1, "repetitions": 1,
        "budgets": [100], "methods": ["arf"], "pilot_development_only": True})
    _write_json(root / "e1/rep_1/n_100/arf/manifest.json", {
        "status": "failed", "error": "RuntimeError: all trials failed",
        "trials": [{"number": 0, "error": "ValueError: unsupported fitting support"}]})
    report = build_report(root)
    cell = report["cells"][0]
    assert cell["classification"] == "pilot_integration_or_runtime_failure"
    assert cell["failure_evidence_categories"] == ["pilot_failure_evidence"]


def test_compressed_bootstrap_preserves_exact_paired_row_outcomes():
    # Implementation-only fixture: two methods have exactly the same correct/
    # incorrect row pattern but choose different wrong labels. A paired row
    # bootstrap must therefore give a zero balanced-accuracy difference.
    y = np.repeat(np.arange(7), 2)
    a = y.copy()
    b = y.copy()
    for c in range(7):
        a[2 * c + 1] = (c + 1) % 7
        b[2 * c + 1] = (c + 2) % 7
    outcomes = {
        "a": {"predictions": a, "covered": np.ones(len(y), bool), "set_sizes": np.ones(len(y), np.uint8)},
        "b": {"predictions": b, "covered": np.ones(len(y), bool), "set_sizes": np.ones(len(y), np.uint8)},
    }
    result = bootstrap_outcomes(y, outcomes, n_boot=50, seed=17)
    paired = result["paired_differences"]["balanced_accuracy"]["a - b"]
    assert paired["estimate"] == 0
    assert paired["ci"] == [0, 0]
