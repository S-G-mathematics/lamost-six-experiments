"""Staged archive helper for later-experiment scientific trial history.

This module never loads serialized models or traverses arbitrary artifact trees.
It collects only explicit non-success fit attempts and JSON scientific history;
private phase receipts are converted to a small allowlisted projection.
"""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path,PurePosixPath

NON_SUCCESS={
 "scientific_failure","unsupported","unavailable_dependency","operationally_interrupted",
 "operationally_invalid","user_stopped","failed","failure","invalid","cancelled",
}
ATTEMPT_INPUT_RE=re.compile(r"^phase_trial_[0-9]+\.json$")
ATTEMPT_RESULT_RE=re.compile(r"^phase_trial_([0-9]+)_result\.json$")
ATTEMPT_ID_RE=re.compile(r"^[A-Za-z0-9_-]{1,128}$")
TASK_KEY_RE=re.compile(r"^e[3-6]/[A-Za-z0-9_./-]+$")

def _sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
 return h.hexdigest()

def _task_outcome(task):
 x=task.get("outcome")
 if isinstance(x,dict): return x.get("status") or x.get("outcome") or ""
 return x or task.get("status") or ""

def _needs_history(task):
 values={str(_task_outcome(task)).lower(),str(task.get("status") or "").lower(),str(task.get("validation_state") or "").lower()}
 if values & NON_SUCCESS:return True
 for a in task.get("attempts") or []:
  if isinstance(a,dict) and str(a.get("status") or a.get("outcome") or "").lower() in NON_SUCCESS:return True
 return False

def _safe_key(key):
 if not isinstance(key,str) or not TASK_KEY_RE.fullmatch(key):raise ValueError("unsafe task key in scientific attempt collector")
 p=PurePosixPath(key)
 if p.is_absolute() or any(part in ("",".","..") for part in p.parts) or "\\\\" in key:raise ValueError("task key traversal rejected")
 if not p.parts or p.parts[0] not in {"e3","e4","e5","e6"}:raise ValueError("collector is limited to experiments E3-E6")
 return p

def _artifact_dir(runtime,key,task):
 rt=Path(runtime).resolve();expected=(rt/"artifacts"/Path(*PurePosixPath(key).parts)).resolve()
 try:expected.relative_to((rt/"artifacts").resolve())
 except ValueError as e:raise ValueError("task artifact escaped runtime artifacts") from e
 raw=task.get("artifact_dir")
 if raw:
  p=Path(raw)
  if not p.is_absolute():p=(rt.parent/p).resolve() if str(p).startswith("runtime_20261025/") else (rt/p).resolve()
  else:p=p.resolve()
  if p!=expected:raise ValueError("registry artifact_dir does not match task-key native path")
 return expected

def _read_doc(path):
 try:return json.loads(path.read_text(encoding="utf-8"))
 except (UnicodeDecodeError,json.JSONDecodeError) as e:raise ValueError("scientific attempt JSON is malformed: "+str(path)) from e

def _phase_projection(path,task_key,attempt_id,entry_type,sanitizer,expected_source_sha256=None):
 source_bytes=path.read_bytes();src_sha=hashlib.sha256(source_bytes).hexdigest()
 if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,src_sha):raise ValueError("reviewed phase source hash mismatch: "+str(path))
 try:raw=json.loads(source_bytes.decode("utf-8"))
 except (UnicodeDecodeError,json.JSONDecodeError) as e:raise ValueError("scientific attempt JSON is malformed: "+str(path)) from e
 match=ATTEMPT_RESULT_RE.fullmatch(path.name)
 phase=str(raw.get("phase") or (f"trial_{match.group(1)}" if match else "unknown"))
 keep=("phase","seconds","peak_tree_rss_kib","exit_code","reason","finished_at","status","score")
 observation={k:raw[k] for k in keep if k in raw}
 if "reason" in observation and sanitizer:observation["reason"]=sanitizer(observation["reason"])
 obj={"schema_version":"scientific-attempt-phase-observation/1","task_key":task_key,"attempt_id":attempt_id,"trial_index":int(match.group(1)) if match else None,"source_file":path.name,"source_sha256":src_sha,"observation":observation,"curation_note":"Derived scientific timing/outcome projection. Original phase receipt remains on EC2; process IDs, process groups, output streams, request/result paths, and state payload were excluded."}
 member=f"runtime_20261025/artifacts/{task_key}/attempts/{attempt_id}/scientific/{path.stem}_observation.json"
 ent=entry_type((json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode(),member,"curated_scientific_attempt_phase_observation")
 return ent,{"source_member":f"runtime_20261025/artifacts/{task_key}/attempts/{attempt_id}/{path.name}","archive_member":member,"source_sha256":src_sha,"curation_mode":"derived_scientific_projection","category":"curated_scientific_attempt_phase_observation"}

def collect_scientific_attempt_entries(root,runtime,tasks,archive_json_entry,entry_type,sanitizer=None,expected_source_sha256=None):
 """Return (Entry list, manifest bytes). No unlisted attempt file is read or included."""
 root=Path(root).resolve();rt=Path(runtime).resolve();entries=[];records=[];omissions=[]
 for task in sorted((t for t in tasks if isinstance(t,dict) and t.get("kind")=="fit"),key=lambda x:str(x.get("key",""))):
  key=str(task.get("key") or "");relkey=_safe_key(key);art=_artifact_dir(rt,key,task)
  if not art.is_dir():continue
  attempts=art/"attempts"
  if attempts.is_symlink() or not attempts.exists():continue
  for ad in sorted(attempts.iterdir(),key=lambda p:p.name):
   if ad.is_symlink() or not ad.is_dir():raise ValueError("attempt directory symlink or non-directory rejected")
   aid=ad.name
   if not ATTEMPT_ID_RE.fullmatch(aid):raise ValueError("unsafe attempt identity rejected")
   try:ad.resolve().relative_to(attempts.resolve())
   except ValueError as e:raise ValueError("attempt directory traversal rejected") from e
   # Candidate names are explicit; model binaries, state files, logs, study DBs, and
   # raw phase receipts are never copied by this list.
   candidates=[]
   for child in sorted(ad.iterdir(),key=lambda p:p.name):
    if child.is_symlink():raise ValueError("symlink in selected scientific attempt directory rejected")
    if not child.is_file():continue
    if child.name in {"selection.json","attempt.json"} or ATTEMPT_INPUT_RE.fullmatch(child.name):
     candidates.append((child,"privacy_curated_source_json"))
    elif ATTEMPT_RESULT_RE.fullmatch(child.name):
     candidates.append((child,"phase_result_projection"))
    elif child.name.lower().endswith((".sqlite",".sqlite3",".db",".db3")):
     omissions.append({"task_key":key,"attempt_id":aid,"source_member":f"runtime_20261025/artifacts/{key}/attempts/{aid}/{child.name}","bytes":child.stat().st_size,"reason":"study/container not audited for embedded operational receipts; retained unchanged on EC2"})
   for path,mode in candidates:
    try:path.resolve().relative_to(ad.resolve())
    except ValueError as e:raise ValueError("candidate path escaped attempt directory") from e
    if mode=="phase_result_projection":
     ent,rec=_phase_projection(path,key,aid,entry_type,sanitizer,expected_source_sha256)
    else:
     member=f"runtime_20261025/artifacts/{key}/attempts/{aid}/{path.name}"
     source_sha=_sha(path)
     if expected_source_sha256 and expected_source_sha256.get(str(path.resolve())) not in (None,source_sha):raise ValueError("reviewed source hash mismatch: "+str(path))
     bound_hashes=dict(expected_source_sha256 or {});bound_hashes[str(path.resolve())]=source_sha
     ent=archive_json_entry(path,member,"scientific_attempt_"+path.name.removesuffix(".json"),root,bound_hashes)
     rec={"source_member":member,"archive_member":member,"source_sha256":source_sha,"curation_mode":"existing_archive_json_entry_privacy_view","category":"scientific_attempt_"+path.name.removesuffix(".json")}
    entries.append(ent);records.append({"task_key":key,"task_outcome":_task_outcome(task),"attempt_id":aid,**rec})
 manifest={"schema_version":"lamost-scientific-attempt-archive-manifest/1","scope":"E3-E6 fit attempt scientific histories, including prior recovered/invalid attempts","included_file_count":len(records),"files":records,"omitted_uninspected_study_containers":omissions,"selection_policy":{"included":["selection.json","attempt.json","phase_trial_N.json input descriptors","derived projections from phase_trial_N_result.json"],"excluded":["models and fitted pipelines","phase state JSON","stdout/stderr logs","raw phase receipts","study/sampler databases unless separately reviewed and proven free of process receipts"]},"timestamp_note":"No observation timestamp is generated here; caller should add actual packaging UTC in final archive metadata."}
 return entries,(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
