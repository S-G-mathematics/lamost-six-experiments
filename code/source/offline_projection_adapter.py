"""Staged validation/adapter for archived E3 partial-selection projections."""
import csv,hashlib,json,re
from pathlib import Path
def _canonical(x):return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def _sha(b):return hashlib.sha256(b).hexdigest()
def sha_file(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def validate_partial(projection):
 p=dict(projection);declared=p.pop("projection_sha256",None)
 if not declared or _sha(_canonical(p))!=declared:raise ValueError("projection SHA-256 mismatch")
 if not p.get("selection_source_sha256") or not p.get("raw_evidence_set_sha256"):raise ValueError("source and raw-evidence hashes required")
 evidence=p.get("raw_evidence_files")
 if not isinstance(evidence,list) or not evidence:raise ValueError("raw evidence inventory missing")
 ev=[{"runtime_relative_path":x["runtime_relative_path"],"source_sha256":x["source_sha256"]} for x in evidence]
 if _sha(_canonical(ev))!=p["raw_evidence_set_sha256"]:raise ValueError("raw evidence-set SHA-256 mismatch")
 rows=p.get("completed_trials")
 if not isinstance(rows,list) or len(rows)!=int(p.get("completed_slot_n",-1)):raise ValueError("completed trial count mismatch")
 if p.get("completed_trial_indices")!=list(range(len(rows))):raise ValueError("completed indices not contiguous")
 counts={}
 for row in rows:counts[row["status"]]=counts.get(row["status"],0)+1
 if counts!=p.get("status_counts"):raise ValueError("trial status counts mismatch")
 if int(p.get("cached_slot_n",0))!=counts.get("duplicate_cached",0):raise ValueError("cached slot count mismatch")
 physical=[float(x["seconds"]) for x in rows if x["status"]!="duplicate_cached" and x.get("seconds") is not None]
 missing=sum(1 for x in rows if x["status"]!="duplicate_cached" and x.get("seconds") is None)
 if len(physical)!=int(p.get("physical_duration_n",-1)):raise ValueError("physical duration count mismatch")
 if missing!=int(p.get("physical_duration_missing_n",-1)):raise ValueError("physical missing-duration count mismatch")
 total=sum(physical) if physical else None
 if (total is None)!=(p.get("physical_seconds") is None) or (total is not None and abs(total-float(p["physical_seconds"]))>1e-7):raise ValueError("physical seconds mismatch")
 for row in rows:
  phase=row.get("physical_phase_seconds")
  sec=row.get("seconds")
  if row["status"]=="duplicate_cached" and phase is not None:raise ValueError("cached duration incorrectly counted as physical")
  if row["status"]!="duplicate_cached" and phase is not None and sec is not None and abs(float(phase)-float(sec))>1e-8:raise ValueError("per-slot physical receipt/selection duration mismatch")
 cached=[float(x["seconds"]) for x in rows if x["status"]=="duplicate_cached" and x.get("seconds") is not None]
 cached_sum=sum(cached) if cached else None
 if int(p.get("cached_slot_n",0))!=counts.get("duplicate_cached",0):raise ValueError("cached slot count mismatch")
 if (cached_sum is None)!=(p.get("cached_elapsed_seconds") is None) or (cached_sum is not None and abs(cached_sum-float(p["cached_elapsed_seconds"]))>1e-8):raise ValueError("cached elapsed sum mismatch")
 if p.get("unattempted_duration_seconds") is not None:raise ValueError("unattempted duration must remain unavailable")
 if p.get("aborted_trial_index") is None and p.get("aborted_last_observed_seconds") is not None:raise ValueError("aborted duration without aborted slot")
 p["projection_sha256"]=declared
 return p
def _selection_seconds(tr):
 v=tr.get("seconds")
 if v is not None:return float(v)
 m=re.search(r"['\"]seconds['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",str(tr.get("error","")))
 return float(m.group(1)) if m else None
def accounting_from_projection(projection,runtime,task,cutoff):
 p=validate_partial(projection);rt=Path(runtime).resolve()
 if not cutoff:raise ValueError("offline projection has no terminal cutoff metadata")
 attempts=task.get("attempts") or []
 if not attempts or attempts[-1].get("attempt_id")!=p["controller_attempt_id"] or cutoff.get("attempt_id")!=p["controller_attempt_id"]:
  raise ValueError("offline projection controller-attempt identity mismatch")
 if cutoff.get("artifact_attempt_id")!=p["engine_attempt_id"]:raise ValueError("offline projection engine-attempt identity mismatch")
 before=json.loads(cutoff.get("source_file_sha256_before") or "{}");after=json.loads(cutoff.get("source_file_sha256_after") or "{}")
 if not before or before!=after or cutoff.get("source_file_hashes_unchanged")!="True":raise ValueError("cutoff source hash maps are not stable")
 evidence=[{"runtime_relative_path":k,"source_sha256":v} for k,v in sorted(before.items())]
 if _sha(_canonical(evidence))!=p["raw_evidence_set_sha256"]:raise ValueError("projection evidence-set digest differs from cutoff")
 if p["selection_source_sha256"]!=before.get(cutoff.get("trial_history_path")):raise ValueError("selection source SHA differs from cutoff")
 if p["completed_trial_indices"]!=json.loads(cutoff.get("completed_trial_indices") or "[]"):raise ValueError("completed trial indices differ from cutoff")
 if p["status_counts"]!=json.loads(cutoff.get("completed_trial_statuses") or "{}"):raise ValueError("completed status counts differ from cutoff")
 aborted=cutoff.get("aborted_trial_index")
 cutoff_aborted=int(aborted) if aborted not in ("",None) else None
 if p["aborted_trial_index"]!=cutoff_aborted:raise ValueError("aborted trial index differs from cutoff")
 cutoff_aborted_seconds=cutoff.get("aborted_trial_last_observed_elapsed_seconds")
 if (cutoff_aborted_seconds in ("",None))!=(p.get("aborted_last_observed_seconds") is None):raise ValueError("aborted elapsed presence differs from cutoff")
 if cutoff_aborted_seconds not in ("",None) and abs(float(cutoff_aborted_seconds)-float(p["aborted_last_observed_seconds"]))>1e-8:raise ValueError("aborted elapsed value differs from cutoff")
 if p["unattempted_slot_indices"]!=json.loads(cutoff.get("unattempted_nominal_slot_indices") or "[]"):raise ValueError("unattempted slots differ from cutoff")
 costs_path=rt/"reports/costs.csv"
 if not costs_path.is_file() or sha_file(costs_path)!=p.get("costs_csv_source_sha256"):raise ValueError("costs.csv source hash differs from validated projection")
 with costs_path.open(newline="",encoding="utf-8") as f:cost_rows=list(csv.DictReader(f))
 for i,row in enumerate(p["completed_trials"]):
  matches=[x for x in cost_rows if x.get("task_key")==task.get("key") and x.get("stage")=="tuning_trial" and x.get("logical_stage")=="synthetic_only_training" and x.get("trial_index")==str(i)]
  if row["status"]=="duplicate_cached":
   if matches or row.get("physical_cost_source") is not None:raise ValueError(f"cached slot has a physical cost attribution at slot {i}")
   continue
  if len(matches)!=1:raise ValueError(f"expected one exact task/stage/trial cost row at slot {i}, got {len(matches)}")
  cost=matches[0];link=row.get("physical_cost_source") or {}
  if link.get("task_key")!=task.get("key") or link.get("trial_index")!=i or link.get("cost_stage")!="tuning_trial" or link.get("logical_stage")!="synthetic_only_training" or link.get("matching_cost_rows")!=1:raise ValueError(f"physical cost link metadata mismatch at slot {i}")
  if link.get("engine_attempt_id")!=p["engine_attempt_id"]:raise ValueError(f"physical cost engine-attempt mismatch at slot {i}")
  if cost.get("attempt_id") not in ("",None,p["engine_attempt_id"]) or link.get("cost_row_attempt_id") not in ("",None,cost.get("attempt_id") or None):raise ValueError(f"cost row attempt identity mismatch at slot {i}")
  result_rel=f"artifacts/{task['key']}/attempts/{p['engine_attempt_id']}/phase_trial_{i}_result.json"
  expected_phase_sha=before.get(result_rel)
  if not expected_phase_sha or link.get("phase_result_source_sha256")!=expected_phase_sha:raise ValueError(f"cost row lacks exact engine-attempt phase evidence at slot {i}")
  if cost.get("phase_observation_status")!="observed" or cost.get("phase_seconds") in ("",None) or row.get("physical_phase_seconds") is None or abs(float(cost["phase_seconds"])-float(row["physical_phase_seconds"]))>1e-8:raise ValueError(f"cost row seconds do not match exact-attempt phase evidence at slot {i}")
 manifest_path=rt/"scientific_attempt_archive_manifest.json"
 if not manifest_path.is_file():raise ValueError("curated scientific-attempt manifest missing")
 manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
 matches=[x for x in manifest.get("files",[]) if x.get("task_key")==task.get("key") and x.get("attempt_id")==p["engine_attempt_id"] and x.get("source_member","").endswith("/selection.json")]
 if len(matches)!=1 or matches[0].get("source_sha256")!=p["selection_source_sha256"]:raise ValueError("curated selection source hash not bound by archive manifest")
 member=matches[0].get("archive_member","")
 prefix="runtime_20261025/"
 if not member.startswith(prefix):raise ValueError("curated selection archive path has unexpected prefix")
 selection=(rt/member[len(prefix):]).resolve()
 try:selection.relative_to(rt)
 except ValueError:raise ValueError("curated selection path escaped runtime")
 if not selection.is_file():raise ValueError("curated selection history absent from archive fixture")
 curated=json.loads(selection.read_text(encoding="utf-8"));trials=curated.get("trials",[])
 if len(trials)!=len(p["completed_trials"]):raise ValueError("curated selection trial count differs from validated projection")
 for i,(src,dst) in enumerate(zip(trials,p["completed_trials"])):
  if src.get("status")!=dst.get("status") or src.get("params")!=dst.get("params"):raise ValueError(f"curated selection status/params mismatch at slot {i}")
  sec=_selection_seconds(src)
  if sec is not None and (dst.get("seconds") is None or abs(sec-float(dst["seconds"]))>1e-9):raise ValueError(f"curated selection duration mismatch at slot {i}")
  source_score=src.get("score",src.get("value"))
  if source_score is not None and (dst.get("score") is None or abs(float(source_score)-float(dst["score"]))>1e-12):raise ValueError(f"curated selection score mismatch at slot {i}")
 return {"state":"curated_projection_validated_offline","slot_n":p["completed_slot_n"],"completed_slot_n":p["completed_slot_n"],"physical_duration_n":p["physical_duration_n"],"physical_duration_missing_n":p["physical_duration_missing_n"],"physical_seconds":p["physical_seconds"],"cached_slot_n":p["cached_slot_n"],"cached_elapsed_seconds":p["cached_elapsed_seconds"],"history_sha256":p["selection_source_sha256"],"history_provenance":"derived_validated_projection_raw_gate_verified_before_archiving","aborted_trial_index":p["aborted_trial_index"],"aborted_trial_last_observed_seconds":p["aborted_last_observed_seconds"],"unattempted_slot_n":len(p["unattempted_slot_indices"]),"verified_cutoff_evidence_file_n":len(p["raw_evidence_files"]),"raw_gate_rerunnable_offline":False,"raw_evidence_set_sha256":p["raw_evidence_set_sha256"],"projection_sha256":p["projection_sha256"]}
