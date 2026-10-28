#!/usr/bin/env python3
"""Build full condition-level descriptive appendices from paired CSVs only."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CLASS_LABELS={"0":"A","1":"F","2":"G","3":"K","4":"M","5":"GALAXY","6":"QSO"}
E4_PAIRS="E4_CONTROL_TREATMENT_PAIRED.csv"
E4_SUM="E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv"
E5_METRICS="E5_clean_corrupted_paired_metrics.csv"
E5_METRICS_SUM="E5_clean_corrupted_paired_metrics_summary.csv"
E5_CLASS="E5_per_class_paired_differences.csv"
E5_CLASS_SUM="E5_per_class_paired_summary.csv"

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def read_csv(path: Path) -> list[dict]:
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def number(value):
    if value is None or value=="": return None
    v=float(value)
    if not math.isfinite(v): raise ValueError(f"nonfinite numeric value: {value}")
    return v

def truth(value):
    return str(value).strip().lower() in {"true","1","yes"}

def key(row, fields):
    return tuple(str(row.get(f) or "") for f in fields)

def check_summary(raw, summary, key_fields, metrics, table_label):
    raw_groups=defaultdict(list)
    for row in raw: raw_groups[key(row,key_fields)].append(row)
    summary_by_key={}
    for row in summary:
        k=key(row,key_fields)
        if k in summary_by_key: raise ValueError(f"{table_label}: duplicate summary key {k}")
        summary_by_key[k]=row
    if set(raw_groups)!=set(summary_by_key):
        missing=sorted(set(raw_groups)-set(summary_by_key))[:3]
        extra=sorted(set(summary_by_key)-set(raw_groups))[:3]
        raise ValueError(f"{table_label}: summary key mismatch missing={missing} extra={extra}")
    for k,group in raw_groups.items():
        row=summary_by_key[k]
        if int(row.get("planned_repetitions") or 0)!=3: raise ValueError(f"{table_label}: planned repetitions != 3 for {k}")
        if int(row.get("rows") or 0)!=len(group): raise ValueError(f"{table_label}: raw row count mismatch for {k}")
        try: rep_numbers=[int(r.get("rep")) for r in group]
        except (TypeError,ValueError): raise ValueError(f"{table_label}: invalid repetition key for {k}")
        if sorted(rep_numbers)!=[1,2,3]:
            raise ValueError(f"{table_label}: each stratum must contain exactly one repetition 1, 2, and 3; got {rep_numbers} for {k}")
        available=sum(truth(r.get("paired_available")) for r in group)
        if int(row.get("available_repetitions") or 0)!=available: raise ValueError(f"{table_label}: availability mismatch for {k}")
        if int(row.get("unmatched_repetitions") or 0)!=3-available: raise ValueError(f"{table_label}: unmatched count mismatch for {k}")
        for metric,raw_field in metrics.items():
            vals=[number(r.get(raw_field)) for r in group if truth(r.get("paired_available")) and r.get(raw_field) not in (None,"")]
            nfield=metric+"_n"; meanfield=metric+"_mean"; sdfield=metric+"_sample_sd"
            if int(row.get(nfield) or 0)!=len(vals): raise ValueError(f"{table_label}: metric n mismatch {nfield} for {k}")
            mean=number(row.get(meanfield)); sd=number(row.get(sdfield))
            expected_mean=statistics.mean(vals) if vals else None
            expected_sd=statistics.stdev(vals) if len(vals)>1 else None
            if expected_mean is None:
                if mean is not None or sd is not None: raise ValueError(f"{table_label}: n=0 must have blank mean/SD for {k} {metric}")
            else:
                if mean is None or abs(mean-expected_mean)>1e-8: raise ValueError(f"{table_label}: mean mismatch for {k} {metric}")
                if expected_sd is None:
                    if sd is not None: raise ValueError(f"{table_label}: n=1 must have undefined SD for {k} {metric}")
                elif sd is None or abs(sd-expected_sd)>1e-8: raise ValueError(f"{table_label}: SD mismatch for {k} {metric}")
    return raw_groups,summary_by_key

def fmt(value, digits=4):
    v=number(value)
    return "-" if v is None else f"{v:+.{digits}f}"

def fmt_sd(value):
    v=number(value)
    return "undefined (n<2)" if v is None else f"{v:.4f}"

def fmt_target(value):
    s=str(value or "")
    return CLASS_LABELS.get(s,s or "-")

def section_table(lines, heading, rows, label_fields, metric_n, metric_mean, metric_sd, label_names):
    lines.extend(["",f"### {heading}","", "| "+" | ".join(label_names+["Matched n/3","Unmatched reps","Metric n","Mean paired delta","Sample SD"])+" |",
                  "|"+"|".join(["---"]* (len(label_names)+5))+"|"])
    for r in rows:
        labels=[fmt_target(r.get(k)) if k in {"target_class","class_id"} else (str(r.get(k) or "-")) for k in label_fields]
        lines.append("| "+" | ".join(labels+[f"{int(r.get('available_repetitions') or 0)}/3",str(int(r.get('unmatched_repetitions') or 0)),str(int(r.get(metric_n) or 0)),fmt(r.get(metric_mean)),fmt_sd(r.get(metric_sd))])+" |")

def build(reports: Path, output: Path) -> dict:
    reports=reports.resolve(); output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
    needed=[E4_PAIRS,E4_SUM,E5_METRICS,E5_METRICS_SUM,E5_CLASS,E5_CLASS_SUM,
            "per_repetition_metrics.csv","per_class_metrics.csv","experiment_outcome_coverage.csv",
            "planned_case_ledger.csv","costs.csv","cost_summary.csv","resource_failure_ledger.csv",
            "E4_class_histograms.csv","E5_corruption_realization_summary.csv","label_transition_counts.csv"]
    missing=[n for n in needed if not (reports/n).is_file()]
    if missing: raise FileNotFoundError(f"missing required report inputs: {missing}")
    e4=read_csv(reports/E4_PAIRS);e4s=read_csv(reports/E4_SUM)
    e5=read_csv(reports/E5_METRICS);e5s=read_csv(reports/E5_METRICS_SUM)
    e5c=read_csv(reports/E5_CLASS);e5cs=read_csv(reports/E5_CLASS_SUM)
    e4_metric_fields={
        "paired_balanced_accuracy_difference_a_minus_b":"paired_balanced_accuracy_difference_a_minus_b",
        "paired_coverage_difference_a_minus_b":"paired_coverage_difference_a_minus_b",
        "paired_set_size_difference_a_minus_b":"paired_set_size_difference_a_minus_b",
        "paired_target_class_recall_difference_a_minus_b":"paired_target_class_recall_difference_a_minus_b",
        "paired_target_class_coverage_difference_a_minus_b":"paired_target_class_coverage_difference_a_minus_b",
    }
    e5_metric_fields={
        "paired_balanced_accuracy_difference_a_minus_b":"paired_balanced_accuracy_difference_a_minus_b",
        "paired_coverage_difference_a_minus_b":"paired_coverage_difference_a_minus_b",
        "paired_set_size_difference_a_minus_b":"paired_set_size_difference_a_minus_b",
    }
    e5_class_fields={"recall_difference_a_minus_b":"recall_difference_a_minus_b","coverage_difference_a_minus_b":"coverage_difference_a_minus_b"}
    e4keys=("comparison","method","target_class","ratio","treatment")
    e5keys=("method","route","generator","mechanism","rate")
    e5ckeys=("method","route","generator","mechanism","rate","class_id")
    e4raw,e4summary=check_summary(e4,e4s,e4keys,e4_metric_fields,"E4")
    e5raw,e5summary=check_summary(e5,e5s,e5keys,e5_metric_fields,"E5 overall")
    e5craw,e5csummary=check_summary(e5c,e5cs,e5ckeys,e5_class_fields,"E5 per class")
    e4counts=Counter(r["comparison"] for r in e4s)
    expected={"altered_direct_minus_unchanged_control":238,"treatment_minus_untreated_altered":336,"treatment_minus_unchanged_control":336}
    if dict(e4counts)!=expected: raise ValueError(f"E4 planned comparison grid mismatch: {dict(e4counts)}")
    if len(e5s)!=288 or len(e5cs)!=2016 or len(e4s)!=910: raise ValueError("condition summary row count mismatch")
    if len(e5)!=864 or len(e5c)!=6048: raise ValueError("paired result row count mismatch")
    for row in e4+e5+e5c:
        if row.get("paired_available","") not in ("True","False","true","false","1","0",""):
            raise ValueError("invalid paired availability field")
    artifacts={
      "per_repetition_metrics.csv":"Per-repetition outcomes and successful denominators.",
      "per_class_metrics.csv":"Per-class recall, coverage, and set size by evaluated case.",
      E4_PAIRS:"All E4 repetition-level direct/treatment control contrasts, including unmatched rows.",
      E4_SUM:"E4 exact-condition paired means and sample SDs.",
      E5_METRICS:"All E5 overall corrupted-minus-clean repetition-level pairs.",
      E5_METRICS_SUM:"E5 exact-condition overall paired means and sample SDs.",
      E5_CLASS:"All E5 per-class recall/coverage repetition-level pairs.",
      E5_CLASS_SUM:"E5 exact-condition per-class paired means and sample SDs.",
      "planned_case_ledger.csv":"Every planned later-experiment case with its current state/reason.",
      "experiment_outcome_coverage.csv":"Planned, successful, failed, unavailable, and pending counts by scientific stratum.",
      "costs.csv":"Observed phase-level costs.",
      "cost_summary.csv":"Observed costs grouped by phase/status.",
      "resource_failure_ledger.csv":"Observed resource and phase failure evidence.",
      "E4_class_histograms.csv":"Exact E4 class-count/restoration ledgers.",
      "E5_corruption_realization_summary.csv":"Observed E5 corruption masks, rates, scales, and hashes.",
      "label_transition_counts.csv":"Observed E5 label-noise transitions."
    }
    hashes={name:sha(reports/name) for name in needed}
    obs=None; status_counts={}
    registry=reports.parent/"registry.json"
    if registry.exists():
        try:
            reg=json.loads(registry.read_text()); obs=reg.get("observed_utc")
            for rec in reg.get("tasks",[]):
                if not rec.get("scientific_case"): continue
                state=rec.get("outcome") if rec.get("status")=="validated_terminal" else rec.get("status")
                if isinstance(state,dict): state=state.get("status") or state.get("outcome") or rec.get("status")
                status_counts[str(state)]=status_counts.get(str(state),0)+1
        except Exception: obs=None; status_counts={}
    active=sum(status_counts.get(x,0) for x in ("planned","waiting_for_dependency","running","operationally_interrupted"))
    project_state="incomplete_or_active_snapshot" if active else "terminal_snapshot_requires_final_validation"
    lines=["# E4 condition-level paired findings","",f"Registry snapshot observation: {obs or 'not recorded'}. Later-experiment execution ledger state: {project_state} ({active} planned/waiting/running/interrupted cases). These are descriptive paired results from successful matched repetitions only.","",
           "Every planned comparison stratum is retained, including rows with zero matched repetitions. Delta direction is explicit in the comparison heading. Mean and sample SD use the available matched repetitions; SD is undefined when n < 2. No significance tests, bootstrap intervals, or across-stratum pooling are used. E4 restoration comparisons are condition-specific; set-size changes must be interpreted with corresponding coverage.","",
           "E4 direct methods compare altered fitting data against the unchanged control. Restoration treatments compare with both untreated altered fitting and the unchanged control.",""]
    specs=[
      ("altered_direct_minus_unchanged_control","Direct altered - unchanged control"),
      ("treatment_minus_untreated_altered","Restoration treatment - untreated altered"),
      ("treatment_minus_unchanged_control","Restoration treatment - unchanged control")]
    labels=("target_class","ratio","method","treatment")
    for comparison,title in specs:
        group=[r for r in e4s if r.get("comparison")==comparison]
        for metric,title_metric in (("paired_balanced_accuracy_difference_a_minus_b","Balanced accuracy"),
                                    ("paired_target_class_recall_difference_a_minus_b","Target-class recall"),
                                    ("paired_coverage_difference_a_minus_b","Overall coverage"),
                                    ("paired_target_class_coverage_difference_a_minus_b","Target-class coverage"),
                                    ("paired_set_size_difference_a_minus_b","Mean prediction-set size")):
            section_table(lines,f"{title} - {title_metric}",group,labels,metric+"_n",metric+"_mean",metric+"_sample_sd",
                          ["Target class","Severity ratio","Method/learner","Treatment"])
    lines.extend(["","## Reproduction and coverage references","",
                  "The tables below preserve individual repetitions, condition histograms, and terminal/unavailable states. They are part of the source report bundle; no case was removed because of its observed score."])
    for filename,description in artifacts.items(): lines.append(f"- [{filename}]({filename}): {description}")
    e4doc="\n".join(lines)+"\n"

    lines=["# E5 condition-level paired findings","",f"Registry snapshot observation: {obs or 'not recorded'}. Later-experiment execution ledger state: {project_state} ({active} planned/waiting/running/interrupted cases). Corrupted-minus-clean deltas use exact repetition, method, route, generator, mechanism, and rate matching.","",
           "Every planned condition stratum is retained, including zero-pair rows. Means and sample SDs are descriptive over successful matched repetitions; SD is undefined when n < 2. Per-class values are not pooled across classes. There are no significance tests, bootstrap intervals, or selected best conditions.",""]
    e5_specs=(("paired_balanced_accuracy_difference_a_minus_b","Balanced accuracy"),
              ("paired_coverage_difference_a_minus_b","Overall coverage"),
              ("paired_set_size_difference_a_minus_b","Mean prediction-set size"))
    e5_labels=("method","route","generator","mechanism","rate")
    for metric,title in e5_specs:
        section_table(lines,f"Overall {title} delta (corrupted - clean)",e5s,e5_labels,metric+"_n",metric+"_mean",metric+"_sample_sd",
                      ["Method","Route","Generator","Mechanism","Affected fit rate"])
    for metric,title in (("recall_difference_a_minus_b","Per-class recall"),("coverage_difference_a_minus_b","Per-class coverage")):
        section_table(lines,f"{title} delta (corrupted - clean)",e5cs,("method","route","generator","mechanism","rate","class_id"),
                      metric+"_n",metric+"_mean",metric+"_sample_sd",
                      ["Method","Route","Generator","Mechanism","Affected fit rate","Class"])
    lines.extend(["","## Reproduction and coverage references","",
                  "The per-repetition tables contain exact paired values, statuses, and recorded reasons. Failed and unavailable cases remain in the planned-case and outcome-coverage ledgers and are not assigned scores. Corruption realizations and costs are linked below."])
    for filename,description in artifacts.items(): lines.append(f"- [{filename}]({filename}): {description}")
    e5doc="\n".join(lines)+"\n"
    e4out=output/"E4_CONDITION_FINDINGS.md";e5out=output/"E5_CONDITION_FINDINGS.md"
    e4out.write_text(e4doc,encoding="utf-8");e5out.write_text(e5doc,encoding="utf-8")
    manifest={"status":"descriptive_appendices_built","project_state":project_state,"ledger_status_counts":status_counts,"created_from_existing_csvs_only":True,"registry_observed_utc":obs,
       "counts":{"E4_summary_strata":len(e4s),"E4_pair_rows":len(e4),"E4_comparison_strata":dict(e4counts),
                 "E5_overall_summary_strata":len(e5s),"E5_overall_pair_rows":len(e5),
                 "E5_class_summary_strata":len(e5cs),"E5_class_pair_rows":len(e5c)},
       "input_sha256":hashes,
       "outputs":{"E4_CONDITION_FINDINGS.md":sha(e4out),"E5_CONDITION_FINDINGS.md":sha(e5out)}}
    index=output/"CONDITION_FINDINGS_INDEX.md"
    index.write_text("# E4/E5 condition-level findings\n\nThese are separate descriptive appendices; no pooled cross-experiment estimate is formed.\n\n- [E4 condition findings](E4_CONDITION_FINDINGS.md)\n- [E5 condition findings](E5_CONDITION_FINDINGS.md)\n\nThe appendices include all planned condition strata from the bound registry snapshot. Pending cases remain blank and appear in linked availability ledgers.\n",encoding="utf-8")
    manifest["outputs"]["CONDITION_FINDINGS_INDEX.md"]=sha(index)
    mpath=output/"CONDITION_FINDINGS_MANIFEST.json";mpath.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest["manifest_sha256"]=sha(mpath)
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--reports-dir",required=True,type=Path)
    ap.add_argument("--output-dir",required=True,type=Path)
    args=ap.parse_args()
    print(json.dumps(build(args.reports_dir,args.output_dir),indent=2,sort_keys=True))

if __name__=="__main__":main()
