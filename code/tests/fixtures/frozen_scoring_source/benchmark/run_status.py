#!/usr/bin/env python3
"""Report Experiment 1 checkpoint status; this utility never starts model work."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CLASS_NAMES = ["A", "F", "G", "K", "M", "GALAXY", "QSO"]
METRICS = ("balanced_accuracy", "set_size", "coverage")
MARKERS = {"complete.json", "manifest.json", "failure.json", "status.json"}
PILOT_NOTE = (
    "The first development pilot was invalid because of an integration bug. "
    "Its failures are not scientific method failures; pilot cells are kept "
    "visible and excluded from final metric aggregates."
)


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value, None
        return None, "JSON root is not an object"
    except Exception as exc:  # one damaged cell must not hide other status
        return None, f"{type(exc).__name__}: {exc}"


def number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def status_bucket(value: Any) -> str:
    value = str(value or "unknown").lower()
    if value in {"complete", "success", "succeeded", "finished"}:
        return "success"
    if value in {"failed", "failure", "error", "unreadable"}:
        return "failed"
    return "incomplete"


def cell_coordinates(relative: Path) -> tuple[int | None, int | None, str | None]:
    parts = relative.parts
    rep = budget = None
    method = None
    if "e1" not in parts:
        return rep, budget, method
    i = parts.index("e1") + 1
    for part in parts[i:]:
        match = re.fullmatch(r"rep_(\d+)", part)
        if match:
            rep = int(match.group(1))
        match = re.fullmatch(r"n_(\d+)", part)
        if match:
            budget = int(match.group(1))
        elif budget is not None and method is None and part not in MARKERS:
            method = part
            break
    return rep, budget, method


def read_cell_status(cell_dir: Path) -> tuple[str, dict[str, Any], str | None]:
    payloads: dict[str, dict[str, Any]] = {}
    errors = []
    for name in MARKERS:
        path = cell_dir / name
        if not path.is_file():
            continue
        data, error = read_json(path)
        if data is not None:
            payloads[name] = data
        elif error:
            errors.append(f"{name}: {error}")

    # A successful completion supersedes an older failure or started manifest
    # left by an interrupted/resumed attempt.
    if "complete.json" in payloads:
        payload = payloads["complete.json"]
        status = status_bucket(payload.get("status"))
    elif "failure.json" in payloads:
        payload = payloads["failure.json"]
        status = "failed"
    elif "status.json" in payloads:
        payload = payloads["status.json"]
        status = status_bucket(payload.get("status"))
    elif "manifest.json" in payloads:
        payload = payloads["manifest.json"]
        status = status_bucket(payload.get("status"))
    else:
        payload = {}
        status = "failed" if errors else "incomplete"
    reason = payload.get("error") or payload.get("reason")
    if reason is None and errors:
        reason = "; ".join(errors)
    return status, payload, str(reason) if reason is not None else None


def cell_metrics(payload: dict[str, Any]) -> dict[str, float | None]:
    test_metrics = payload.get("test_metrics")
    if not isinstance(test_metrics, dict):
        test_metrics = {}
    return {
        "balanced_accuracy": number(payload.get("balanced_accuracy",
                                                test_metrics.get("balanced_accuracy"))),
        "set_size": number(payload.get("set_size", payload.get("mean_prediction_set_size"))),
        "coverage": number(payload.get("coverage", payload.get("test_coverage"))),
    }


def find_config(cell_dir: Path, root: Path) -> tuple[dict[str, Any], str | None]:
    current = cell_dir
    while True:
        # The immutable supervisor plan is authoritative over per-child
        # invocation configs, which intentionally describe only one cell.
        for filename in ("master_run_config.json", "run_config.json"):
            config_path = current / filename
            if config_path.is_file():
                config, _ = read_json(config_path)
                if config is not None and config.get("experiment") == 1:
                    return config, config_path.relative_to(root).as_posix()
        if current == root or root not in current.parents:
            break
        current = current.parent
    return {}, None


def is_pilot(cell_dir: Path, root: Path, config: dict[str, Any]) -> bool:
    try:
        in_pilot_path = "pilot" in cell_dir.relative_to(root).parts
    except ValueError:
        in_pilot_path = False
    return bool(in_pilot_path or config.get("pilot_development_only", False))


def scan_cells(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    directories: set[Path] = set()
    for path in root.rglob("*"):
        if (path.is_file() and path.name in MARKERS
                and not any(part in {".deps", "__pycache__"} for part in path.parts)):
            relative = path.relative_to(root)
            if "e1" in relative.parts:
                directories.add(path.parent)

    state_path = root / "supervisor_state.json"
    supervisor_state, _ = read_json(state_path) if state_path.is_file() else (None, None)
    supervisor_cells = (supervisor_state or {}).get("cells", {})
    if not isinstance(supervisor_cells, dict):
        supervisor_cells = {}
    cells = []
    for cell_dir in sorted(directories):
        relative = cell_dir.relative_to(root)
        rep, budget, method = cell_coordinates(relative)
        if rep is None or budget is None or method is None:
            continue
        config, config_path = find_config(cell_dir, root)
        pilot = is_pilot(cell_dir, root, config)
        status, payload, reason = read_cell_status(cell_dir)
        sup_key = f"n_{budget}/rep_{rep}/{method}"
        sup = supervisor_cells.get(sup_key, {})
        sup_status = sup.get("status") if isinstance(sup, dict) else None
        # Completion artifact is authoritative. Otherwise a supervisor's
        # terminal failure must surface even while the child manifest remains
        # at its last atomically saved `started` state.
        if not (cell_dir / "complete.json").is_file() and sup_status in {"terminal_failure", "crashed"}:
            status = "failed"
            status_detail = sup_status
            reason = (reason + "; " if reason else "") + \
                f"supervisor={sup_status}, returncode={sup.get('returncode')}, timed_out={sup.get('timed_out')}"
        elif not (cell_dir / "complete.json").is_file() and sup_status == "interrupted" and status != "failed":
            status = "incomplete"
            status_detail = sup_status
            reason = (reason + "; " if reason else "") + "supervisor=interrupted"
        else:
            status_detail = payload.get("status", status)
        cells.append({
            "experiment": 1,
            "repetition": rep,
            "budget": budget,
            "method": method,
            "comparison": f"n_{budget}:{method}",
            "status": status,
            "status_detail": status_detail,
            "supervisor_status": sup_status,
            "pilot": pilot,
            "cell_path": relative.as_posix(),
            "expected_repetitions": config.get("repetitions", 5),
            "config_path": config_path,
            "reason": reason,
            "class_names": CLASS_NAMES,
            "metrics": cell_metrics(payload),
        })

    # When an Experiment 1 run config exists, count configured cells with no
    # artifacts as not started instead of silently omitting them.
    root_config, config_path = find_config(root, root)
    missing_paths = []
    if root_config:
        existing = {row["cell_path"] for row in cells}
        for rep in range(1, int(root_config.get("repetitions", 5)) + 1):
            for budget in root_config.get("budgets", []):
                for method in root_config.get("methods", []):
                    relative = Path("e1") / f"rep_{rep}" / f"n_{int(budget)}" / str(method)
                    if relative.as_posix() in existing:
                        continue
                    pilot = bool(root_config.get("pilot_development_only", False))
                    sup_key = f"n_{int(budget)}/rep_{rep}/{method}"
                    sup = supervisor_cells.get(sup_key, {})
                    sup_status = sup.get("status") if isinstance(sup, dict) else None
                    if sup_status in {"terminal_failure", "crashed"}:
                        cell_status = "failed"
                        detail = sup_status
                        reason = (f"supervisor={sup_status}, returncode={sup.get('returncode')}, "
                                  f"timed_out={sup.get('timed_out')}")
                    else:
                        cell_status = "incomplete"
                        detail = "not_started" if sup_status is None else sup_status
                        reason = "configured cell has no persisted status artifact"
                    cells.append({
                        "experiment": 1, "repetition": rep, "budget": int(budget),
                        "method": str(method), "comparison": f"n_{int(budget)}:{method}",
                        "status": cell_status, "status_detail": detail,
                        "supervisor_status": sup_status, "pilot": pilot,
                        "cell_path": relative.as_posix(),
                        "expected_repetitions": root_config.get("repetitions", 5),
                        "config_path": config_path,
                        "reason": reason,
                        "class_names": CLASS_NAMES,
                        "metrics": {metric: None for metric in METRICS},
                    })
                    missing_paths.append(relative.as_posix())
    cells.sort(key=lambda row: (row["budget"], row["method"], row["repetition"], row["cell_path"]))
    return cells, missing_paths


def aggregate(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        if cell["status"] == "success" and not cell["pilot"]:
            groups[(cell["budget"], cell["method"])].append(cell)
    rows = []
    for (budget, method), group in sorted(groups.items()):
        for metric in METRICS:
            values = [(cell["repetition"], cell["metrics"].get(metric)) for cell in group]
            values = [(rep, value) for rep, value in values if value is not None]
            # There is one expected cell per repetition/budget/method. Guard
            # against duplicate persisted copies instead of double-counting.
            by_rep: dict[int, list[float]] = defaultdict(list)
            for rep, value in values:
                by_rep[rep].append(float(value))
            included = []
            conflicts = []
            for rep, rep_values in sorted(by_rep.items()):
                if max(rep_values) - min(rep_values) > 1e-12:
                    conflicts.append(rep)
                    continue
                included.append((rep, rep_values[0]))
            if not included:
                continue
            numbers = [value for _, value in included]
            expected = max((cell["expected_repetitions"] or 0 for cell in group), default=0)
            rows.append({
                "experiment": 1, "budget": budget, "method": method,
                "comparison": f"n_{budget}:{method}", "metric": metric,
                "mean": statistics.fmean(numbers),
                "sample_sd": statistics.stdev(numbers) if len(numbers) > 1 else None,
                "actual_repetitions": len(numbers), "expected_repetitions": expected,
                "repetition_ids": [rep for rep, _ in included],
                "excluded_conflicting_repetitions": conflicts,
                "class_names": CLASS_NAMES,
            })
    return rows


CSV_FIELDS = ["record_type", "experiment", "budget", "method", "comparison", "metric",
              "repetition", "status", "status_detail", "supervisor_status", "pilot", "cell_path",
              "expected_repetitions", "actual_repetitions", "balanced_accuracy",
              "set_size", "coverage", "mean", "sample_sd", "reason", "class_names"]


def write_csv(path: Path, cells: list[dict[str, Any]], aggregates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for cell in cells:
            row = {field: cell.get(field) for field in CSV_FIELDS}
            row.update(cell.get("metrics", {}))
            row["record_type"] = "cell"
            row["class_names"] = "|".join(CLASS_NAMES)
            writer.writerow(row)
        for agg in aggregates:
            writer.writerow({"record_type": "aggregate", "experiment": 1,
                             "budget": agg["budget"], "method": agg["method"],
                             "comparison": agg["comparison"], "metric": agg["metric"],
                             "expected_repetitions": agg["expected_repetitions"],
                             "actual_repetitions": agg["actual_repetitions"],
                             "mean": agg["mean"], "sample_sd": agg["sample_sd"],
                             "class_names": "|".join(CLASS_NAMES)})


def build_report(results_dir: Path, baseline_dir: Path) -> dict[str, Any]:
    labels = {name: i for i, name in enumerate(CLASS_NAMES)}
    mapping_path = baseline_dir / "audit" / "label_mapping.json"
    if mapping_path.is_file():
        mapping, _ = read_json(mapping_path)
        if mapping and isinstance(mapping.get("label_to_id"), dict):
            labels = mapping["label_to_id"]
    cells, not_started = scan_cells(results_dir)
    aggregates = aggregate(cells)
    counts = Counter(row["status"] for row in cells)
    nonpilot = Counter(row["status"] for row in cells if not row["pilot"])
    pilot = Counter(row["status"] for row in cells if row["pilot"])
    return {
        "experiment": 1,
        "results_directory": str(results_dir),
        "class_names": CLASS_NAMES,
        "label_to_id": labels,
        "pilot_note": PILOT_NOTE,
        "count_definitions": {
            "success": "cell has a complete completion artifact or a complete manifest",
            "failed": "cell has a failure artifact or failed manifest/completion status",
            "incomplete": "cell is started, unavailable, unsupported, unreadable, unknown, or not started",
            "pilot_cells_are_separate": True,
        },
        "counts": {
            "all_cells": {"success": counts["success"], "failed": counts["failed"],
                          "incomplete": counts["incomplete"], "total": len(cells)},
            "nonpilot_cells": {"success": nonpilot["success"], "failed": nonpilot["failed"],
                               "incomplete": nonpilot["incomplete"], "total": sum(nonpilot.values())},
            "pilot_cells": {"success": pilot["success"], "failed": pilot["failed"],
                            "incomplete": pilot["incomplete"], "total": sum(pilot.values())},
            "configured_not_started": len(not_started),
        },
        "aggregates": aggregates,
        "cells": cells,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("benchmark/results"))
    parser.add_argument("--baseline-dir", type=Path, default=Path("lamost_baseline"))
    parser.add_argument("--json", dest="json_path", type=Path, default=None)
    parser.add_argument("--csv", dest="csv_path", type=Path, default=None)
    args = parser.parse_args(argv)
    results_dir = args.results.resolve()
    report = build_report(results_dir, args.baseline_dir)
    json_path = (args.json_path or results_dir / "run_status.json").resolve()
    csv_path = (args.csv_path or results_dir / "run_status.csv").resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(csv_path, report["cells"], report["aggregates"])
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "counts": report["counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
