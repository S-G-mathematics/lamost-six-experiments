#!/usr/bin/env python3
"""Rebuild descriptive, non-inferential summaries from published CSVs only.

Run from any directory: python3 analysis/descriptive_summary.py
Inputs are committed CSV evidence; no database, model, NPZ, predictions, or inference is read.
All groupings retain experiment-specific condition keys; rows are never pooled across strata.
"""
from __future__ import annotations
import csv, math, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = REPORTS / "descriptive_summaries_20261031"
OUT.mkdir(parents=True, exist_ok=True)

def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def stats(values):
    xs = [x for x in values if x is not None]
    n = len(xs)
    return {"n": n, "mean": statistics.mean(xs) if n else "",
            "sample_sd": statistics.stdev(xs) if n > 1 else "",
            "min": min(xs) if n else "", "max": max(xs) if n else ""}

def group_rows(rows, keys):
    out = defaultdict(list)
    for r in rows:
        out[tuple(r.get(k, "") for k in keys)].append(r)
    return out

def paired_summary(source, output, keys, metrics, available=None):
    grouped = group_rows(source, keys)
    result = []
    for key, rows in sorted(grouped.items(), key=lambda x: tuple(str(y) for y in x[0])):
        base = dict(zip(keys, key))
        for metric in metrics:
            vals = [num(r.get(metric)) for r in rows]
            s = stats(vals)
            valid = [x for x in vals if x is not None]
            base_row = dict(base)
            base_row.update({"metric": metric, "n_pairs": s["n"], "mean_difference": s["mean"],
                             "sample_sd": s["sample_sd"], "min_difference": s["min"],
                             "max_difference": s["max"], "higher_a": sum(x > 0 for x in valid),
                             "ties": sum(x == 0 for x in valid), "lower_a": sum(x < 0 for x in valid)})
            if available:
                base_row["rows_in_stratum"] = len(rows)
                base_row["available_pairs"] = sum(r.get(available) == "True" for r in rows)
                base_row["unavailable_pairs"] = len(rows) - base_row["available_pairs"]
            result.append(base_row)
    fields = keys + ["metric", "n_pairs", "mean_difference", "sample_sd", "min_difference",
                     "max_difference", "higher_a", "ties", "lower_a"]
    if available:
        fields += ["rows_in_stratum", "available_pairs", "unavailable_pairs"]
    write_csv(OUT / output, result, fields)
    return result

# Per-repetition metric distributions, retaining all named design axes.
rep = read_csv(REPORTS / "per_repetition_metrics.csv")
design = ["experiment", "method", "route", "condition", "target_class", "ratio",
          "treatment", "mechanism", "rate", "generator", "mode"]
metric_fields = ["balanced_accuracy", "coverage", "set_size"]
metric_rows = []
for key, rows in sorted(group_rows(rep, design).items(), key=lambda x: tuple(str(y) for y in x[0])):
    common = dict(zip(design, key))
    for metric in metric_fields:
        s = stats([num(r.get(metric)) for r in rows])
        metric_rows.append({**common, "metric": metric, **s})
write_csv(OUT / "successful_metric_distributions.csv", metric_rows,
          design + ["metric", "n", "mean", "sample_sd", "min", "max"])

# Main matched table uses its published pairing definition. Sign is arm_a minus arm_b;
# higher_a/lower_a are arithmetic direction only, not a universal benefit score.
paired = read_csv(REPORTS / "matched_paired_differences.csv")
pair_metrics = ["paired_balanced_accuracy_difference_a_minus_b",
                "paired_coverage_difference_a_minus_b", "paired_set_size_difference_a_minus_b"]
matched_summary = paired_summary(
    paired, "matched_pair_summaries.csv",
    ["experiment", "condition", "arm_a", "arm_b"], pair_metrics)

# E3 has a separate source-bound 135-row comparison ledger, including the direct-vs-real
# comparison omitted from the generic 755-row matched file in one unavailable synthetic cell.
e3path = REPORTS / "E3_CURRENT_MATCHED_PAIRS_20261030.csv"
if e3path.exists():
    e3 = read_csv(e3path)
    e3paired = [r for r in e3 if r.get("pair_status") == "paired"]
    e3summary = paired_summary(
        e3paired, "E3_dedicated_pair_summaries.csv",
        ["comparison", "generator", "learner"],
        ["balanced_accuracy_difference_candidate_minus_baseline",
         "coverage_difference_candidate_minus_baseline",
         "set_size_difference_candidate_minus_baseline"])
    status = defaultdict(int)
    for r in e3: status[r.get("pair_status", "")] += 1
    write_csv(OUT / "E3_dedicated_pair_ledger_status.csv",
              [{"pair_status": k, "rows": v} for k, v in sorted(status.items())],
              ["pair_status", "rows"])

# E4 treatment/control effects: only rows explicitly marked paired enter difference summaries.
e4 = read_csv(REPORTS / "E4_CONTROL_TREATMENT_PAIRED.csv")
e4_available = [r for r in e4 if r.get("paired_available") == "True"]
e4_summary = paired_summary(
    e4_available, "E4_treatment_control_pair_summaries.csv",
    ["treatment", "comparison", "method", "target_class", "ratio", "condition"],
    ["paired_balanced_accuracy_difference_a_minus_b",
     "paired_coverage_difference_a_minus_b", "paired_set_size_difference_a_minus_b",
     "paired_target_class_recall_difference_a_minus_b",
     "paired_target_class_coverage_difference_a_minus_b"])
e4_status = defaultdict(lambda: {"rows": 0, "available": 0})
for r in e4:
    x = e4_status[(r.get("treatment", ""), r.get("comparison", ""))]
    x["rows"] += 1
    x["available"] += r.get("paired_available") == "True"
write_csv(OUT / "E4_pair_availability.csv",
          [{"treatment": k[0], "comparison": k[1], **v, "unavailable": v["rows"]-v["available"]}
           for k, v in sorted(e4_status.items())],
          ["treatment", "comparison", "rows", "available", "unavailable"])

# E5 clean-vs-corrupted summaries keep generator, mechanism, rate, route and learner distinct.
e5 = read_csv(REPORTS / "E5_clean_corrupted_paired_metrics.csv")
e5_available = [r for r in e5 if r.get("paired_available") == "True"]
e5_summary = paired_summary(
    e5_available, "E5_clean_corrupted_pair_summaries.csv",
    ["method", "route", "generator", "mechanism", "rate"],
    ["paired_balanced_accuracy_difference_a_minus_b",
     "paired_coverage_difference_a_minus_b", "paired_set_size_difference_a_minus_b"])
e5_status = defaultdict(lambda: {"rows": 0, "available": 0})
for r in e5:
    x = e5_status[(r.get("mechanism", ""), r.get("rate", ""))]
    x["rows"] += 1
    x["available"] += r.get("paired_available") == "True"
write_csv(OUT / "E5_pair_availability.csv",
          [{"mechanism": k[0], "rate": k[1], **v, "unavailable": v["rows"]-v["available"]}
           for k, v in sorted(e5_status.items())],
          ["mechanism", "rate", "rows", "available", "unavailable"])

# Per-class distributions, preserving the seven-class identity and exact condition.
classes = read_csv(REPORTS / "per_class_metrics.csv")
class_design = ["experiment", "method", "route", "condition", "target_class", "ratio",
                "treatment", "mechanism", "rate", "generator", "mode", "class_id"]
class_out = []
for key, rows in sorted(group_rows(classes, class_design).items(), key=lambda x: tuple(str(y) for y in x[0])):
    common = dict(zip(class_design, key))
    for metric in ["recall", "coverage", "set_size"]:
        s = stats([num(r.get(metric)) for r in rows])
        class_out.append({**common, "metric": metric, **s})
write_csv(OUT / "per_class_metric_distributions.csv", class_out,
          class_design + ["metric", "n", "mean", "sample_sd", "min", "max"])

# E6 has no successful primary test evaluations. This output is tuning-selection description only.
e6 = read_csv(REPORTS / "E6_weights.csv")
candidate_rows = read_csv(REPORTS / "E6_candidate_ledger.csv")
selected_candidate = {r.get("rep"): r for r in candidate_rows
                      if r.get("mode") == "learned" and r.get("selected") == "True"}
learned = [r for r in e6 if r.get("mode") == "learned"]
weight_names = ["weight_gmm", "weight_copula", "weight_arf", "weight_kde", "weight_chow_liu"]
e6_rows = []
for r in learned:
    row = {k: r.get(k, "") for k in ["rep", "status", "candidate_count", "selected_candidate",
                                      "frozen_before_calibration_and_test", "member_order"]}
    chosen = selected_candidate.get(r.get("rep"), {})
    row["selected_candidate_tuning_balanced_accuracy"] = chosen.get("balanced_accuracy", "")
    row["weight_vector_json"] = r.get("weights", "")
    for w in weight_names: row[w] = r.get(w, "")
    e6_rows.append(row)
write_csv(OUT / "E6_learned_weights_tuning_only.csv", e6_rows,
          ["rep", "status", "candidate_count", "selected_candidate",
           "selected_candidate_tuning_balanced_accuracy", "frozen_before_calibration_and_test",
           "member_order", "weight_vector_json"] + weight_names)
weight_summary = []
for w in weight_names:
    s = stats([num(r.get(w)) for r in learned])
    weight_summary.append({"member_weight": w.removeprefix("weight_"), **s})
write_csv(OUT / "E6_weight_stability_tuning_only.csv", weight_summary,
          ["member_weight", "n", "mean", "sample_sd", "min", "max"])

# Compact provenance of inputs and outputs for reproducibility.
import hashlib
def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()
inputs = [REPORTS / n for n in [
    "per_repetition_metrics.csv", "per_class_metrics.csv", "matched_paired_differences.csv",
    "E4_CONTROL_TREATMENT_PAIRED.csv", "E5_clean_corrupted_paired_metrics.csv",
    "E6_weights.csv", "E6_candidate_ledger.csv",
    "E3_CURRENT_MATCHED_PAIRS_20261030.csv"] if (REPORTS/n).exists()]
inputs.append(ROOT / "analysis/descriptive_summary.py")
manifest = []
for p in inputs:
    manifest.append({"kind":"input","path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":sha(p)})
for p in sorted(OUT.glob("*.csv")):
    if p.name == "MANIFEST.csv":
        continue
    manifest.append({"kind":"output","path":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":sha(p)})
write_csv(OUT / "MANIFEST.csv", manifest, ["kind","path","bytes","sha256"])
print(f"wrote {len(manifest)-len(inputs)} descriptive CSVs; inputs={len(inputs)}; output={OUT.relative_to(ROOT)}")
print(f"rows: rep={len(rep)} paired={len(paired)} E3pairs={len(e3) if e3path.exists() else 0} E4pairs={len(e4)} E5pairs={len(e5)} class={len(classes)}")
