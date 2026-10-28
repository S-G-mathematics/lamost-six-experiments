"""Read-only Experiment 1 result summarizer and optional paired bootstrap."""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def _number(value):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _text_failure_category(message):
    msg = str(message or "").lower()
    if any(s in msg for s in ("modulenotfound", "importerror", "attributeerror", "typeerror",
                               "missing required", "api signature", "constructor", "not installed")):
        return "integration_failure"
    if any(s in msg for s in ("timeout", "timed out", "memory", "out of memory", "oom")):
        return "resource_failure"
    if any(s in msg for s in ("unsupported", "lacks one or more classes", "invalid density",
                               "singular", "no fitting support", "invalid support",
                               "insufficient support", "exceeds class", "minimum leaf")):
        return "scientific_model_or_support_failure"
    return "unclassified_failure"


def _failure_evidence(message, record):
    evidence = []
    trial_errors = [(i, trial) for i, trial in enumerate(record.get("trials", []) or [])
                    if isinstance(trial, dict) and trial.get("error")]
    explicit_resource = bool(record.get("phase_timeout") or record.get("resource_limit_failure") or
                             str(record.get("status", "")).lower() in
                             {"phase_timeout", "resource_limit_failure", "resource_failure"})
    message_category = _text_failure_category(message)
    if message and (message_category != "unclassified_failure" or (not trial_errors and not explicit_resource)):
        evidence.append({"source": "cell_error", "message": str(message),
                         "category": message_category})
    for i, trial in trial_errors:
        detail = str(trial["error"])
        evidence.append({"source": f"trial_{trial.get('number', i)}_error", "message": detail,
                         "category": _text_failure_category(detail)})
    if explicit_resource:
        marker = record.get("phase_timeout") or record.get("resource_limit_failure") or record.get("status")
        evidence.append({"source": "supervisor_marker", "message": str(marker), "category": "resource_failure"})
    return evidence


def _failure_category(message, pilot=False, record=None):
    record = record or {}
    if pilot:
        return "pilot_integration_or_runtime_failure"
    status = str(record.get("status", "")).lower()
    if (status in {"phase_timeout", "resource_limit_failure", "resource_failure"} or
            record.get("phase_timeout") or record.get("resource_limit_failure")):
        return "resource_failure"
    evidence = _failure_evidence(message, record)
    categories = {x["category"] for x in evidence}
    # A concrete API/type mismatch blocks a scientific interpretation even if
    # other candidates also failed for a support constraint.
    if "integration_failure" in categories:
        return "integration_failure"
    if "resource_failure" in categories:
        return "resource_failure"
    if "scientific_model_or_support_failure" in categories:
        return "scientific_model_or_support_failure"
    return "unclassified_failure"


def _get_metric(record, name):
    if name == "balanced_accuracy":
        return _number(record.get("balanced_accuracy", (record.get("test_metrics") or {}).get("balanced_accuracy")))
    if name == "set_size":
        return _number(record.get("set_size", record.get("mean_prediction_set_size")))
    if name == "coverage":
        return _number(record.get("coverage", record.get("test_coverage")))
    return None


def _mean_sd(values):
    xs = [float(x) for x in values if _number(x) is not None]
    if not xs:
        return {"n": 0, "mean": None, "sample_sd": None}
    return {"n": len(xs), "mean": statistics.fmean(xs),
            "sample_sd": statistics.stdev(xs) if len(xs) > 1 else None}


def _scan_cells(results_dir: Path, pilot: bool, run_config=None, expected_repetitions=None):
    cells = []
    e1 = results_dir / "e1"
    if not e1.exists():
        return cells
    directories = sorted(p for p in e1.glob("rep_*/n_*/*") if p.is_dir())
    for cell in directories:
        parts = cell.parts
        try:
            i = parts.index("e1")
            identity = {"repetition": int(parts[i + 1].removeprefix("rep_")),
                        "budget": int(parts[i + 2].removeprefix("n_")), "method": parts[i + 3]}
        except (ValueError, IndexError):
            continue
        done_path, manifest_path = cell / "complete.json", cell / "manifest.json"
        done = json.loads(done_path.read_text()) if done_path.exists() else None
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        status = (done or manifest).get("status", "incomplete")
        result = {**identity, "path": cell.as_posix(), "status": status,
                  "complete_file": done_path.exists(), "manifest_file": manifest_path.exists()}
        if status == "complete":
            if pilot:
                result["classification"] = "pilot_completed_no_test_evaluation"
                result["metrics"] = {m: None for m in ("balanced_accuracy", "set_size", "coverage")}
            else:
                metrics = {m: _get_metric(done, m) for m in ("balanced_accuracy", "set_size", "coverage")}
                if all(v is not None for v in metrics.values()):
                    result["classification"] = "successful_test_evaluation"
                    result["metrics"] = metrics
                    result["per_class"] = done.get("per_class", (done.get("test_metrics") or {}).get("per_class", {}))
                elif done.get("pilot") or (pilot and not (cell / "test_predictions.npz").exists()):
                    result["classification"] = "pilot_completed_no_test_evaluation"
                    result["metrics"] = {m: None for m in ("balanced_accuracy", "set_size", "coverage")}
                else:
                    result["classification"] = "invalid_or_incomplete_result_artifact"
                    result["metrics"] = metrics
        elif status in {"started", "incomplete", ""}:
            result["classification"] = "incomplete_or_interrupted"
            result["error"] = (done or manifest).get("error")
        elif status == "unavailable":
            result["classification"] = "unavailable_cell"
            result["error"] = (done or manifest).get("error")
        else:
            message = done.get("error") if done else manifest.get("error")
            result["error"] = message
            failure_record = done or manifest
            result["classification"] = _failure_category(message, pilot=pilot, record=failure_record)
            evidence = _failure_evidence(message, failure_record)
            if pilot:
                evidence = [{**item, "category": "pilot_failure_evidence"} for item in evidence]
            result["failure_evidence_categories"] = sorted({x["category"] for x in evidence})
            result["failure_evidence"] = evidence
        cells.append(result)
    config = run_config or {}
    methods = config.get("methods") or []
    budgets = config.get("budgets") or []
    repetitions = int(expected_repetitions or config.get("repetitions", 0))
    existing = {(c["repetition"], c["budget"], c["method"]) for c in cells}
    for rep, budget, method in itertools.product(range(1, repetitions + 1), budgets, methods):
        identity = (rep, int(budget), str(method))
        if identity in existing:
            continue
        cells.append({"repetition": rep, "budget": int(budget), "method": str(method),
                      "path": (e1 / f"rep_{rep}" / f"n_{int(budget)}" / str(method)).as_posix(),
                      "status": "missing", "complete_file": False, "manifest_file": False,
                      "classification": "not_started_or_no_cell_artifact", "error": None})
    cells.sort(key=lambda c: (c["budget"], c["repetition"], c["method"]))
    return cells


def _summaries(cells, expected_repetitions):
    successful = [c for c in cells if c["classification"] == "successful_test_evaluation"]
    by_method_budget = defaultdict(list)
    for cell in successful:
        by_method_budget[(cell["method"], cell["budget"])].append(cell)
    summaries = []
    for (method, budget), runs in sorted(by_method_budget.items(), key=lambda x: (x[0][1], x[0][0])):
        metrics = {}
        for metric in ("balanced_accuracy", "set_size", "coverage"):
            metrics[metric] = _mean_sd([r["metrics"][metric] for r in runs])
        summaries.append({"method": method, "budget": budget, "successful_repetitions": len(runs),
                          "expected_repetitions": expected_repetitions,
                          "missing_repetitions": max(0, expected_repetitions - len(runs)),
                          "metrics": metrics,
                          "per_repetition": [{"repetition": r["repetition"], **r["metrics"]} for r in sorted(runs, key=lambda r:r["repetition"])]})
    paired = defaultdict(lambda: defaultdict(list))
    grouped = defaultdict(list)
    for cell in successful:
        grouped[(cell["budget"], cell["repetition"])].append(cell)
    for (budget, repetition), runs in grouped.items():
        runs = sorted(runs, key=lambda r: r["method"])
        for left, right in itertools.combinations(runs, 2):
            key = (budget, left["method"], right["method"])
            for metric in ("balanced_accuracy", "set_size", "coverage"):
                paired[key][metric].append({"repetition": repetition,
                    "difference": left["metrics"][metric] - right["metrics"][metric]})
    comparisons = []
    for (budget, left, right), metrics_data in sorted(paired.items()):
        metric_summary = {}
        for metric, observations in metrics_data.items():
            stats = _mean_sd([x["difference"] for x in observations])
            metric_summary[metric] = {**stats, "per_repetition": observations}
        comparisons.append({"budget": budget, "method_a": left, "method_b": right,
                            "difference_direction": "method_a - method_b",
                            "paired_repetitions": len(next(iter(metrics_data.values()), [])),
                            "expected_repetitions": expected_repetitions,
                            "missing_pairs": max(0, expected_repetitions - len(next(iter(metrics_data.values()), []))),
                            "differences": metric_summary})
    return summaries, comparisons


def _bootstrap_saved(results_dir, baseline_dir, cells, repetitions, n_boot, seed):
    """Optional bootstrap; loads test labels only when explicitly requested."""
    from benchmark.engine import load_data, validate_manifest
    from benchmark.evaluation import bootstrap_outcomes
    validate_manifest(baseline_dir)
    frame, split_col = load_data(baseline_dir)
    by_id = frame.set_index("sample_id", drop=False)
    expected_test_ids = None
    output = {}
    budgets = sorted({c["budget"] for c in cells if c["classification"] == "successful_test_evaluation"})
    for budget in budgets:
        combined = {}
        y_reference = None
        for cell in cells:
            if cell["budget"] != budget or cell["classification"] != "successful_test_evaluation":
                continue
            path = Path(cell["path"]) / "test_predictions.npz"
            if not path.exists():
                continue
            import numpy as np
            with np.load(path, allow_pickle=False) as pred:
                if "sample_id" not in pred or "prediction_sets" not in pred:
                    continue
                sample_ids = pred["sample_id"].copy()
                y_pred = pred["y_pred"].astype(np.int8, copy=False)
                sets = pred["prediction_sets"].astype(bool)
            if expected_test_ids is None:
                expected_test_ids = sample_ids
            elif not np.array_equal(expected_test_ids, sample_ids):
                raise ValueError("paired bootstrap requires identical test sample IDs and order across E1 cells")
            y = by_id.loc[sample_ids, "label_id"].to_numpy(dtype=np.int64)
            if y_reference is None:
                y_reference = y
            elif not np.array_equal(y_reference, y):
                raise ValueError("paired bootstrap test labels/order changed across E1 cells")
            if sets.shape != (len(y), 7):
                continue
            combined[f"rep_{cell['repetition']}:{cell['method']}"] = {
                "predictions": y_pred, "covered": sets[np.arange(len(y)), y],
                "set_sizes": sets.sum(axis=1).astype(np.uint8)}
        if combined and y_reference is not None:
            boot = bootstrap_outcomes(y_reference, combined, n_boot=n_boot,
                                      seed=seed + int(budget), confidence=.95)
            # Keep only comparisons within the same repetition; cross-repetition
            # method differences are not meaningful paired estimands.
            boot["paired_differences"] = {
                metric: {key: value for key, value in pairs.items()
                         if key.split(" - ")[0].split(":", 1)[0] == key.split(" - ")[1].split(":", 1)[0]}
                for metric, pairs in boot["paired_differences"].items()}
            output[str(budget)] = boot
    return output


def build_report(results_dir="benchmark/results", expected_repetitions=None,
                 bootstrap=False, baseline_dir="lamost_baseline", n_boot=1000, seed=271828):
    results_dir = Path(results_dir)
    config_path = results_dir / "run_config.json"
    master_path = results_dir / "master_run_config.json"
    run_config = json.loads(config_path.read_text()) if config_path.exists() else {}
    master_config = json.loads(master_path.read_text()) if master_path.exists() else {}
    # A supervisor's master config describes the planned full grid; child
    # run_config files are overwritten by each one-cell process invocation.
    effective_config = master_config or run_config
    pilot = bool(effective_config.get("pilot_development_only", effective_config.get("pilot", False)))
    reps = int(expected_repetitions or effective_config.get("repetitions", 5))
    cells = _scan_cells(results_dir, pilot, effective_config, reps)
    summaries, comparisons = _summaries(cells, reps)
    statuses = Counter(c["classification"] for c in cells)
    report = {"experiment": 1, "source_results_dir": results_dir.as_posix(),
              "run_config": run_config, "master_run_config": master_config or None,
              "grid_config_source": "master_run_config.json" if master_config else "run_config.json",
              "effective_run_config": effective_config, "pilot_mode": pilot,
              "status": "no_e1_cells_found" if not cells else "summarized",
              "cell_counts": dict(sorted(statuses.items())), "cells": cells,
              "method_budget_summaries": summaries, "paired_comparisons": comparisons,
              "uncertainty_note": "run-level means and sample SD reflect observed repetitions; paired differences use matched repetition and budget",
              "bootstrap": None}
    if bootstrap:
        report["bootstrap"] = _bootstrap_saved(results_dir, baseline_dir, cells, reps, n_boot, seed)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize saved Experiment 1 outcomes without fitting models.")
    parser.add_argument("--results", type=Path, default=Path("benchmark/results"))
    parser.add_argument("--output", type=Path, default=None,
                        help="JSON report path (default: RESULTS/e1_report.json)")
    parser.add_argument("--expected-repetitions", type=int, default=None)
    parser.add_argument("--bootstrap", action="store_true",
                        help="opt in to paired resampling of saved test predictions (potentially costly)")
    parser.add_argument("--baseline", type=Path, default=Path("lamost_baseline"))
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=271828)
    args = parser.parse_args(argv)
    report = build_report(args.results, args.expected_repetitions, args.bootstrap,
                          args.baseline, args.bootstrap_replicates, args.seed)
    destination = args.output or (args.results / "e1_report.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps({"status": report["status"], "cell_counts": report["cell_counts"],
                      "report": destination.as_posix()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
