#!/usr/bin/env python3
"""Staged producer of an offline-safe E3 partial-selection projection."""
from __future__ import annotations
import argparse,csv,datetime,hashlib,importlib.util,json,re
from pathlib import Path
KEYS=("e3/rep_2/fit/synthetic/random_forest/gmm","e3/rep_2/fit/synthetic/random_forest/kde")
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
 h=hashlib.sha256()
 with Path(p).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def trial_row(tr):
 status=str(tr.get("status") or "unknown");sec=tr.get("seconds")
 if sec is None:
  m=re.search(r"['\"]seconds['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",str(tr.get("error","")))
  if m:sec=float(m.group(1))
 row={"status":status,"params":tr.get("params"),"seconds":float(sec) if sec is not None else None}
 score=tr.get("score",tr.get("value"))
 if score is not None:row["score"]=score
 if tr.get("error"):
  s=str(tr["error"]).lower()
  row["error_category"]="timeout" if "timeout" in s else ("resource_limit" if "memory" in s or "rss" in s else "recorded_error")
 return row
def build(runtime,output):
 runtime=Path(runtime).resolve();output=Path(output).resolve();exp=runtime/"source/export_e3_descriptive.py"
 spec=importlib.util.spec_from_file_location("e3_live_exporter",exp);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 registry=json.loads((runtime/"registry.json").read_text())
 cutoffs=list(csv.DictReader((runtime/"reports/terminal_trial_cutoffs.csv").open(encoding="utf-8")))
 costrows=list(csv.DictReader((runtime/"reports/costs.csv").open(encoding="utf-8")))
 receipt={"schema_version":"E3-validated-partial-history-projection/1","created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"producer_source_sha256":sha_file(Path(__file__)),"strict_live_gate_source_sha256":sha_file(exp),"provenance_basis":"Derived only after current strict raw-evidence verification on EC2. This curated projection is offline-use evidence; raw private phase receipts are excluded from the archive, so the raw gate is not independently rerunnable offline.","partials":{}}
 tasks={t["key"]:t for t in registry["tasks"]}
 for key in KEYS:
  task=tasks[key];matches=[c for c in cutoffs if c.get("task_key")==key]
  if len(matches)!=1:raise ValueError(f"expected one cutoff for {key}, got {len(matches)}")
  c=matches[0];summary=mod.verified_cutoff_trial_history(task,c,runtime)
  before=json.loads(c["source_file_sha256_before"]);after=json.loads(c["source_file_sha256_after"])
  if before!=after:raise ValueError("raw evidence hashes changed during strict gate")
  evidence=[{"runtime_relative_path":k,"source_sha256":v} for k,v in sorted(before.items())]
  selection=runtime/c["trial_history_path"]
  if sha_file(selection)!=summary["history_sha256"]:raise ValueError("selection hash differs from strict result")
  trials=json.loads(selection.read_text(encoding="utf-8")).get("trials",[])
  completed=[trial_row(t) for t in trials]
  engine_id=c.get("artifact_attempt_id")
  if not engine_id:raise ValueError("cutoff lacks exact engine attempt identity for "+key)
  slotcost={}
  for i,t in enumerate(completed):
   candidates=[r for r in costrows if r.get("task_key")==key and r.get("stage")=="tuning_trial" and r.get("logical_stage")=="synthetic_only_training" and r.get("trial_index")==str(i)]
   if t["status"]=="duplicate_cached":
    if candidates:raise ValueError(f"cached slot unexpectedly has a physical cost row: {key} trial {i}")
    t["physical_phase_seconds"]=None
    continue
   if len(candidates)!=1:raise ValueError(f"expected exactly one task/stage/trial cost row: {key} trial {i}, got {len(candidates)}")
   row=candidates[0]
   if row.get("attempt_id") not in ("",None,engine_id):raise ValueError(f"cost row attempt ID mismatch: {key} trial {i}")
   if row.get("phase_observation_status")!="observed" or row.get("phase_seconds") in ("",None):raise ValueError(f"cost row has no observed phase duration: {key} trial {i}")
   rel=f"artifacts/{key}/attempts/{engine_id}/phase_trial_{i}_result.json"
   if rel not in before:raise ValueError(f"cutoff lacks phase result hash for exact engine attempt: {key} trial {i}")
   phase_path=runtime/rel
   phase=json.loads(phase_path.read_text(encoding="utf-8"))
   if phase.get("phase")!=f"trial_{i}":raise ValueError(f"phase result/index mismatch: {key} trial {i}")
   if sha_file(phase_path)!=before[rel]:raise ValueError(f"phase result hash mismatch: {key} trial {i}")
   phase_seconds=float(phase["seconds"]);cost_seconds=float(row["phase_seconds"])
   if abs(phase_seconds-cost_seconds)>1e-8:raise ValueError(f"cost row duration mismatch against exact-attempt receipt: {key} trial {i}")
   if t.get("seconds") is not None and abs(float(t["seconds"])-phase_seconds)>1e-8:raise ValueError(f"selection duration mismatch against exact-attempt receipt: {key} trial {i}")
   t["physical_phase_seconds"]=phase_seconds
   t["physical_cost_source"]={"task_key":key,"cost_stage":"tuning_trial","logical_stage":"synthetic_only_training","trial_index":i,"engine_attempt_id":engine_id,"cost_row_attempt_id":row.get("attempt_id") or None,"phase_result_source_sha256":before[rel],"matching_cost_rows":1}
   slotcost[i]=phase_seconds
  cached=[float(t["seconds"]) for t in completed if t["status"]=="duplicate_cached" and t.get("seconds") is not None]
  physical=[float(t["seconds"]) for t in completed if t["status"]!="duplicate_cached" and t.get("seconds") is not None]
  missing=sum(1 for t in completed if t["status"]!="duplicate_cached" and t.get("seconds") is None)
  if len(physical)!=summary["physical_duration_n"] or missing!=summary["physical_duration_missing_n"]:raise ValueError("selection duration counts disagree with strict history accounting: "+key)
  if (sum(physical) if physical else None)!=summary["physical_seconds"]:raise ValueError("selection physical time disagrees with strict history accounting: "+key)
  cached_sum=sum(cached) if cached else None
  if (cached_sum is None)!=(summary["cached_elapsed_seconds"] is None) or (cached_sum is not None and abs(cached_sum-float(summary["cached_elapsed_seconds"]))>1e-8):raise ValueError("cached elapsed sum disagrees with strict history accounting: "+key)
  p={"controller_attempt_id":c["attempt_id"],"engine_attempt_id":c["artifact_attempt_id"],"selection_source_sha256":summary["history_sha256"],"raw_evidence_set_sha256":sha_bytes(canonical(evidence)),"raw_evidence_files":evidence,"completed_trial_indices":json.loads(c["completed_trial_indices"]),"completed_trials":completed,"completed_slot_n":summary["completed_slot_n"],"status_counts":json.loads(c["completed_trial_statuses"]),"physical_duration_n":summary["physical_duration_n"],"physical_duration_missing_n":summary["physical_duration_missing_n"],"physical_seconds":summary["physical_seconds"],"cached_slot_n":summary["cached_slot_n"],"cached_elapsed_seconds":summary["cached_elapsed_seconds"],"aborted_trial_index":summary["aborted_trial_index"],"aborted_last_observed_seconds":summary["aborted_trial_last_observed_seconds"],"unattempted_slot_indices":json.loads(c["unattempted_nominal_slot_indices"]),"unattempted_duration_seconds":None,"costs_csv_source_sha256":sha_file(runtime/"reports/costs.csv"),"accounting_note":"Physical subtotal excludes duplicate_cached slots and aborted elapsed observation; cached elapsed is copied cache metadata, not new physical fit time. Per-slot physical seconds are included only when observed in validated costs.csv. No duration is imputed for aborted or unattempted slots."}
  p["projection_sha256"]=sha_bytes(canonical(p));receipt["partials"][key]=p
 output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 return receipt
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--runtime",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();r=build(a.runtime,a.output);print(json.dumps({"output":a.output,"partial_count":len(r["partials"]),"sha256":sha_file(a.output)},sort_keys=True))
