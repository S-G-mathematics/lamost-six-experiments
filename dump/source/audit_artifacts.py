"""Incremental, read-only validation for completed project artifacts.

Only validated-terminal successful registry entries are considered. This module never
changes registry/task state and never starts scientific work.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,sys,tempfile,zipfile,importlib.util,contextlib,uuid,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np

LABELS=("A","F","G","K","M","GALAXY","QSO")
LABEL_TO_CODE={v:i for i,v in enumerate(LABELS)}
VERSION="2.11-cold-zip-verified-artifact-io"
RESTORATION_MANIFEST_SHA256="97d89b0c744c870abfe6c6a487a907c597c9d47dbf034066e15b827dae1e1c81"
RESTORATION_MANIFEST_REL="manifests/incidents/e3_original_npz_container_restoration_20261025.json"
ORIGINAL_MIGRATION_ROOT=Path("/home/ubuntu/lamost_e1_migration_20261023")

def sha256_file(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def sha256_ids(ids): return hashlib.sha256(np.ascontiguousarray(ids).tobytes()).hexdigest()
def _safe_float(a): return np.asarray(a,dtype=np.float64)
def _scalar_text(value):
 a=np.asarray(value)
 if a.shape!=():raise ValueError("expected a scalar string")
 x=a.item()
 if isinstance(x,bytes):x=x.decode("utf-8")
 return str(x)
def _declared_score_kinds(pipe,meta,fit_doc):
 return [("pipeline",pipe.get("score_kind")),("pipeline_model",getattr(pipe.get("model"),"score_kind",None)),("registry_fit_result",meta.get("score_kind")),("artifact_fit_result",fit_doc.get("score_kind"))]
def _score_contract_checks(evaluation,npz,y,pred,bits,covered,size,ncal,calibration=None,require_scores=False,expected_fit_key=None):
 """Validate optional raw prediction scores without changing their interpretation."""
 issues=[]
 kind=evaluation.get("score_kind")
 scores=npz.get("scores")
 if kind is None:
  if scores is not None:issues.append(("score_kind_missing","raw scores exist but evaluation.json has no score_kind"))
  kind="probability"
 if kind not in {"probability","margin"}:
  issues.append(("score_kind_invalid",repr(kind)))
  return issues
 calibration_kind=evaluation.get("calibration_score_kind")
 if calibration_kind is not None and calibration_kind!=kind:
  issues.append(("calibration_score_kind_mismatch",f"evaluation={kind}; calibration={calibration_kind}"))
 if scores is None:
  if require_scores:issues.append(("scores_missing",f"score_kind={kind}; versioned SVM outcome requires saved native score matrix"))
  return issues
 if evaluation.get("score_kind") not in {"probability","margin"}:
  issues.append(("score_kind_missing","scores cannot be interpreted without explicit score_kind"))
 try:npz_kind=_scalar_text(npz.get("score_kind"))
 except Exception as e:npz_kind=None;issues.append(("npz_score_kind_invalid",e))
 if npz_kind!=kind:issues.append(("npz_score_kind_mismatch",f"evaluation={kind}; npz={npz_kind}"))
 if kind=="margin" and scores is not None:
  for field,expected in (("prediction_rule","argmax_class_score"),("nonconformity_rule","negative_margin")):
   if evaluation.get(field)!=expected:issues.append((field+"_mismatch",f"evaluation={evaluation.get(field)!r}; expected={expected}"))
   try:stored=_scalar_text(npz.get(field))
   except Exception as e:stored=None;issues.append(("npz_"+field+"_invalid",e))
   if stored!=expected:issues.append(("npz_"+field+"_mismatch",f"npz={stored!r}; expected={expected}"))
 order=np.asarray(npz.get("score_class_order",[]))
 if order.dtype!=np.int8 or order.shape!=(7,) or not np.array_equal(order,np.arange(7,dtype=np.int8)):
  issues.append(("score_class_order",f"dtype={order.dtype}; shape={order.shape}; values={order.tolist()}"))
 a=np.asarray(scores)
 if a.dtype!=np.float64:issues.append(("scores_dtype",f"expected float64, got {a.dtype}"))
 if a.shape!=(len(y),7):issues.append(("scores_shape",f"expected {(len(y),7)}, got {a.shape}"))
 if not np.isfinite(a).all():issues.append(("scores_nonfinite","raw score matrix contains NaN or infinity"))
 if a.shape!=(len(y),7) or not np.isfinite(a).all():return issues
 if kind=="probability":
  if np.any(a<0):issues.append(("probability_negative","probability scores contain negative values"))
  if not np.allclose(a.sum(axis=1),1.0,atol=1e-6,rtol=0):issues.append(("probability_rows_not_normalized","probability rows must sum to one"))
 # Margin values remain native and unnormalized. The declared nonconformity is -margin.
 threshold_value=npz.get("threshold")
 try:
  threshold_array=np.asarray(threshold_value,dtype=np.float64)
  if threshold_array.shape!=() or not np.isfinite(threshold_array):raise ValueError("threshold must be a finite scalar")
  threshold=float(threshold_array)
 except Exception as e:
  threshold=None;issues.append(("npz_threshold_invalid",e))
 eval_threshold=evaluation.get("threshold",evaluation.get("conformal_threshold"))
 try:
  if eval_threshold is None or threshold is None or not np.isclose(float(eval_threshold),threshold,rtol=0,atol=1e-10):issues.append(("threshold_mismatch",f"evaluation={eval_threshold}; npz={threshold}"))
 except Exception as e:issues.append(("threshold_invalid",e))
 if threshold is not None:
  if evaluation.get("threshold") is None and evaluation.get("conformal_threshold") is None:issues.append(("evaluation_threshold_missing","score matrix exists but no evaluation threshold is recorded"))
  pred_from_scores=np.argmax(a,axis=1)
  if not np.array_equal(pred_from_scores,np.asarray(pred,int)):issues.append(("scores_prediction_mismatch","saved y_pred is not argmax of the declared raw scores"))
  nonconformity=(1.0-a) if kind=="probability" else -a
  expected_sets=nonconformity<=threshold
  if not np.array_equal(expected_sets,np.asarray(bits,bool)):issues.append(("scores_set_mismatch",f"stored set mask disagrees with {kind} nonconformity rule"))
  expected_size=expected_sets.sum(axis=1)
  if not np.array_equal(expected_size,np.asarray(size,int)):issues.append(("scores_set_size_mismatch","set_size disagrees with score-derived sets"))
  if not np.array_equal(expected_sets[np.arange(len(y)),np.asarray(y,int)],np.asarray(covered,bool)):issues.append(("scores_coverage_mismatch","covered disagrees with score-derived sets"))
 if require_scores and kind=="margin":
  if evaluation.get("calibration_score_kind")!="margin":issues.append(("calibration_score_kind_missing","versioned margin evaluation must record calibration_score_kind='margin'"))
  if not isinstance(calibration,dict):issues.append(("calibration_json_missing","versioned margin-score outcome requires calibration.json"))
  if not isinstance(evaluation.get("pipeline_sha256"),str):issues.append(("evaluation_pipeline_sha_missing","versioned margin evaluation must identify the selected pipeline"))
 if isinstance(calibration,dict):
  ck=calibration.get("score_kind")
  if ck!=kind:issues.append(("calibration_score_kind_mismatch",f"evaluation={kind}; calibration.json={ck}"))
  if evaluation.get("calibration_score_kind") is not None and calibration.get("score_kind")!=evaluation.get("calibration_score_kind"):
   issues.append(("calibration_score_kind_mismatch","evaluation and calibration.json score kinds differ"))
  ct=calibration.get("threshold")
  try:
   if ct is None or threshold is None or not np.isclose(float(ct),threshold,rtol=0,atol=1e-10):issues.append(("calibration_threshold_mismatch",f"calibration={ct}; outcome={threshold}"))
  except Exception as e:issues.append(("calibration_threshold_invalid",e))
  if calibration.get("calibration_n") is None or int(calibration["calibration_n"])!=int(ncal):issues.append(("calibration_count_mismatch",f"calibration.json={calibration.get('calibration_n')}; role={ncal}"))
  expected=expected_fit_key or evaluation.get("fit_key")
  if require_scores and kind=="margin" and not calibration.get("fit_key"):issues.append(("calibration_fit_key_missing","calibration.json must identify its selected fit dependency"))
  if expected and calibration.get("fit_key")!=expected:issues.append(("calibration_fit_key_mismatch",f"expected={expected}; got={calibration.get('fit_key')}"))
  ep=evaluation.get("pipeline_sha256")
  cp=calibration.get("pipeline_sha256")
  if require_scores and kind=="margin" and not cp:issues.append(("calibration_pipeline_sha_missing","calibration.json must bind its selected pipeline"))
  if isinstance(ep,str) and cp!=ep:issues.append(("calibration_pipeline_sha_mismatch",f"evaluation={ep}; calibration={cp}"))
 return issues
def _eq(a,b,atol=1e-10,rtol=1e-10):
 try:return bool(np.allclose(np.asarray(a),np.asarray(b),atol=atol,rtol=rtol,equal_nan=True))
 except Exception:return False
def _typed_array_sha256(a):
 a=np.ascontiguousarray(a);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.view(np.uint8));return h.hexdigest()
def _label_code(v):
 if isinstance(v,(int,np.integer)): return int(v)
 s=str(v)
 if s in LABEL_TO_CODE:return LABEL_TO_CODE[s]
 raise ValueError(f"unknown class label {v!r}")
def _atomic_json(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
 with tmp.open("w") as f: json.dump(obj,f,indent=2,sort_keys=True,default=lambda x:x.item() if isinstance(x,np.generic) else str(x))
 os.replace(tmp,path)
def _atomic_csv(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f".tmp.{os.getpid()}")
 fields=("task_key","kind","check","severity","evidence")
 with tmp.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for r in rows:w.writerow({k:r.get(k,"") for k in fields})
 os.replace(tmp,path)
class Auditor:
 def __init__(self,runtime,cold_store=None,require_calibration_replay=False,replay_run_nonce=None,accepted_prior_receipts=None,extracted_cold_source=None):
  self.rt=Path(runtime).resolve(); self.project=self.rt.parent/"project"
  self.cold_store=cold_store
  self.extracted_cold_source=extracted_cold_source
  self.extracted_projection_sha256=getattr(extracted_cold_source,"projection_sha",None)
  self.extracted_projection_stat=None
  if extracted_cold_source is not None:
   projection_path=Path(getattr(extracted_cold_source,"projection_path",""))
   if not projection_path.is_file() or projection_path.is_symlink() or not self.extracted_projection_sha256:
    raise ValueError("extracted cold projection is not a pinned regular file")
   ps=projection_path.stat();self.extracted_projection_stat=(ps.st_dev,ps.st_ino,ps.st_size,ps.st_mtime_ns,ps.st_ctime_ns)
  self.require_calibration_replay=bool(require_calibration_replay)
  self.calibration_replay_physical=[]
  self.e6_member_calibration_records=[]
  self.e6_ensemble_calibration_records=[]
  self._e6_native_calibration_scores={}
  self._replay_proof_fit_keys=set()
  self.calibration_replay_phase_started_utc=None
  self.calibration_replay_run_id=replay_run_nonce or os.environ.get("LAMOST_CAL_REPLAY_RUN_NONCE") or uuid.uuid4().hex
  if not isinstance(self.calibration_replay_run_id,str) or not self.calibration_replay_run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in self.calibration_replay_run_id): raise ValueError("invalid calibration replay run nonce")
  self.calibration_replay_phase_ledger_path=self.rt/"logs"/"operational"/f"calibration_replay_phase_ledger_{self.calibration_replay_run_id}.jsonl"
  if self.require_calibration_replay and self.calibration_replay_phase_ledger_path.exists(): raise ValueError("calibration replay nonce already has a phase ledger")
  self.calibration_replay_phase_started_monotonic=None
  self.accepted_prior_receipts={}; self.accepted_prior_receipts_sha256=None
  if accepted_prior_receipts is not None:
   doc=json.loads(Path(accepted_prior_receipts).read_text()) if isinstance(accepted_prior_receipts,(str,Path)) else accepted_prior_receipts
   if not isinstance(doc,dict) or doc.get("schema_version")!="lamost-calibration-replay-accepted-prior-receipts/1" or not isinstance(doc.get("entries"),list): raise ValueError("accepted prior replay receipt index schema invalid")
   for row in doc["entries"]:
    if not isinstance(row,dict) or not isinstance(row.get("identity"),str) or not isinstance(row.get("receipt_sha256"),str) or len(row["receipt_sha256"])!=64: raise ValueError("accepted prior receipt entry invalid")
    if row["identity"] in self.accepted_prior_receipts: raise ValueError("duplicate identity in accepted prior receipt index")
    self.accepted_prior_receipts[row["identity"]]=row["receipt_sha256"]
   self.accepted_prior_receipts_sha256=hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(",",":")).encode()).hexdigest()
  self._frozen_source_record=None
  self.cold_members={}
  self._cold_session_depth=0
  if str(self.project) not in sys.path:sys.path.insert(0,str(self.project))
  self.cache_path=self.rt/"auditcache.json"; self.cache={"schema_version":1,"files":{},"tasks":{}}
  if self.cache_path.exists():
   try:self.cache=json.loads(self.cache_path.read_text())
   except Exception:self.cache={"schema_version":1,"files":{},"tasks":{}}
  self.file_memo={}
  self.issues=[]; self.diagnostics=[]; self.supersessions=[]; self.records=[]; self.restoration_manifest_sha256=None; self.restoration_manifest_source_sha256=None
 def issue(self,key,kind,check,evidence,severity="error"):
  self.issues.append({"task_key":key,"kind":kind,"check":check,"severity":severity,"evidence":str(evidence)[:2000]})
 def diagnostic(self,key,kind,check,evidence):
  self.diagnostics.append({"task_key":key,"kind":kind,"check":check,"severity":"nonblocking_diagnostic_limitation","evidence":str(evidence)[:2000]})
 def _refresh_cold_members(self):
  if self.cold_store is None:
   self.cold_members={};return
  manifest=json.loads(self.cold_store.manifest.read_text())
  if manifest.get("schema_version")!="lamost-cold-model-store/1" or not isinstance(manifest.get("members"),list):
   raise ValueError("cold model-store manifest schema invalid")
  members={}
  for row in manifest["members"]:
   logical=row.get("logical_path");aliases=row.get("aliases")
   if not isinstance(logical,str) or not isinstance(aliases,list) or not isinstance(row.get("sha256"),str):
    raise ValueError("cold member lacks canonical logical path, SHA, or aliases")
   names=[logical,*aliases]
   for name in names:
    if not isinstance(name,str) or not name or chr(92) in name:
     raise ValueError("cold member alias path invalid")
    prior=members.get(name)
    if prior is not None and prior!=row:
     raise ValueError("cold member alias is ambiguous across committed entries")
    members[name]=row
  self.cold_members=members
 def _ensure_cold_members(self):
  if self.cold_store is None:return
  if self._cold_session_depth:return
  with self.cold_store._read_lock():
   self._refresh_cold_members()
 def _assert_extracted_projection_stable(self):
  if self.extracted_cold_source is None:return
  path=Path(self.extracted_cold_source.projection_path)
  if path.is_symlink() or not path.is_file():raise ValueError("extracted cold membership projection disappeared or became a symlink")
  st=path.stat();identity=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
  if identity!=self.extracted_projection_stat:
   raise ValueError("extracted cold membership projection changed after resolver initialization")
 def _logical_artifact(self,p):
  try:
   rel=Path(p).resolve(strict=False).relative_to(self.rt.parent).as_posix()
  except (ValueError,OSError):return None
  if self.cold_store is not None:
   self._ensure_cold_members()
   if rel in self.cold_members:return rel
  if self.extracted_cold_source is not None and rel.startswith(f"{self.rt.name}/artifacts/"):
   self._assert_extracted_projection_stable()
   try:self.extracted_cold_source.member_for(rel);return rel
   except FileNotFoundError:pass
  return None
 def _artifact_backend(self,logical):
  if self.cold_store is not None and logical in self.cold_members:return self.cold_store
  if self.extracted_cold_source is not None:
   try:self.extracted_cold_source.member_for(logical);return self.extracted_cold_source
   except FileNotFoundError:pass
  return None
 def _artifact_expected_sha(self,logical,backend):
  row=self.cold_members.get(logical) if backend is self.cold_store else backend.member_for(logical)
  return row.get("sha256") if backend is self.cold_store else row.get("logical_sha256",row.get("member_sha256"))
 def _backend_stat(self,backend,logical,expected):
  if backend is self.cold_store:return backend.artifact_stat(logical,expected)
  stat_fn=getattr(backend,"artifact_stat",None) or backend.stat
  return stat_fn(logical,expected)
 def _backend_open(self,backend,logical,expected):
  if backend is self.cold_store:return backend.open_verified(logical,expected)
  return backend.open(logical,expected)
 def _cold_archive_identity(self):
  identities=[]
  for path in (self.cold_store.archive,self.cold_store.manifest):
   st=path.stat()
   identities.append((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns))
  return tuple(identities)
 def file_exists(self,p):
  p=Path(p);logical=self._logical_artifact(p)
  if logical is None:return p.is_file()
  backend=self._artifact_backend(logical);expected=self._artifact_expected_sha(logical,backend)
  if p.is_symlink():raise ValueError("logical artifact path is a symlink")
  if p.is_file():
   if sha256_file(p)==expected:return True
   if backend is self.cold_store:raise ValueError("physical cold artifact differs from validated logical SHA")
  try:self._backend_stat(backend,logical,expected);return True
  except FileNotFoundError:return False
 def file_hash(self,p,force=False):
  p=Path(p);logical=self._logical_artifact(p)
  try:st=p.stat()
  except FileNotFoundError:st=None
  k=str(p);old=self.cache.get("files",{}).get(k,{})
  if logical is not None:
   backend=self._artifact_backend(logical);expected=self._artifact_expected_sha(logical,backend)
   if p.is_symlink():raise ValueError("logical artifact path is a symlink")
   if st is not None and p.is_file():
    physical=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    got=sha256_file(p)
    if got==expected:
     if not force and old.get("sha256")==got and old.get("physical_identity")==physical and old.get("cold_logical_verified") is True:return got
     self.cache.setdefault("files",{})[k]={"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":got,"physical_identity":physical,"cold_logical_verified":True}
     return got
    if backend is self.cold_store:
     raise ValueError("physical cold artifact hash mismatch; refusing extracted fallback")
   try:info=self._backend_stat(backend,logical,expected)
   except FileNotFoundError:return None
   identity=info.get("cache_identity")
   if not force and old.get("cold_semantic_identity")==identity and old.get("sha256")==expected and old.get("cold_logical_verified") is True:
    return expected
   h=hashlib.sha256();n=0;crc=0
   with self._backend_open(backend,logical,expected) as f:
    for block in iter(lambda:f.read(8<<20),b""):
     h.update(block);n+=len(block);crc=zipfile.crc32(block,crc)
   got=h.hexdigest()
   if got!=expected or n!=int(info["size"]):raise ValueError("verified logical artifact SHA/size differs from registry identity")
   if info.get("logical_crc32") is not None and (crc&0xffffffff)!=int(info["logical_crc32"]):raise ValueError("verified logical artifact CRC differs from projection")
   self.cache.setdefault("files",{})[k]={"size":n,"mtime_ns":info.get("mtime_ns"),"sha256":got,"cold_semantic_identity":identity,"cold_logical_verified":True}
   return got
  if st is None:return None
  if not force and old.get("size")==st.st_size and old.get("mtime_ns")==st.st_mtime_ns and old.get("sha256"):
   return old["sha256"]
  h=sha256_file(p); self.cache.setdefault("files",{})[k]={"size":st.st_size,"mtime_ns":st.st_mtime_ns,"sha256":h}
  return h
 def open_artifact(self,p):
  p=Path(p);logical=self._logical_artifact(p)
  if logical is not None:
   backend=self._artifact_backend(logical);expected=self._artifact_expected_sha(logical,backend)
   if p.is_symlink():raise ValueError("logical artifact path is a symlink")
   if p.is_file():
    got=sha256_file(p)
    if got==expected:return p.open("rb")
    if backend is self.cold_store:raise ValueError("physical cold artifact hash mismatch; refusing extracted fallback")
   return self._backend_open(backend,logical,expected)
  return p.open("rb")
 def load_joblib(self,p):
  import joblib
  with self.open_artifact(p) as f:return joblib.load(f)
 def load_npz(self,p,keys=None):
  with self.open_artifact(p) as f:
   with np.load(f,allow_pickle=False) as z:
    names=z.files if keys is None else keys
    return {k:z[k] for k in names if k in z.files}
 def role(self,rep,keys=None):
  p=self.rt/"cache/roles"/f"rep_{int(rep)}.npz"
  return p,self.load_npz(p,keys)
 def task_art(self,task):
  # artifact_dir is display/provenance metadata and may use an archive-root prefix.
  # The task key is canonical: archive members are runtime_20261025/artifacts/<key>.
  key=task.get("key")
  if not isinstance(key,str) or not key or "\\" in key:
   raise ValueError("invalid task key for artifact path")
  parts=Path(key).parts
  if Path(key).is_absolute() or any(part in {"",".",".."} for part in parts):
   raise ValueError("task artifact key escapes runtime")
  root=self.rt.resolve();candidate=(root/"artifacts"/Path(*parts)).resolve()
  try:candidate.relative_to(root)
  except ValueError:raise ValueError("task artifact key escapes runtime")
  return candidate
 def _frozen_scoring_source(self,method):
  from benchmark import models_arf,models_basic,models_flexible
  module=models_arf if method=="arf" else (models_flexible if method in {"gmm","copula","kde","chow_liu"} else models_basic)
  source=Path(module.__file__).resolve(); observed=self.file_hash(source,force=True)
  frozen_report=self.project/"benchmark"/"results"/"e1_report_validated_no_bootstrap.json"
  if not frozen_report.is_file():raise ValueError("validated E1 source-hash record is unavailable")
  if self._frozen_source_record is None:
   report=json.loads(frozen_report.read_text());report_sha=self.file_hash(frozen_report,force=True)
   self._frozen_source_record=(report.get("effective_run_config",{}).get("benchmark_python_source_sha256",{}),report_sha)
  else:
   current=self.file_hash(frozen_report)
   if current!=self._frozen_source_record[1]:raise ValueError("validated E1 source-hash record changed during replay audit")
  expected=self._frozen_source_record[0].get(source.name)
  if not isinstance(expected,str) or observed!=expected:raise ValueError(f"scoring module differs from validated frozen source hash: {source.name}")
  return module,observed,self._frozen_source_record[1]
 def resolve_recorded_path(self,value):
  """Resolve an archive-recorded project path without trusting an old host root."""
  if not isinstance(value,(str,Path)) or not str(value):raise ValueError("empty recorded source path")
  raw=Path(value)
  if any(part==".." for part in raw.parts):raise ValueError("recorded source path contains traversal")
  archive_root=self.rt.parent.resolve()
  if raw.is_absolute():
   absolute=raw.resolve(strict=False)
   roots=(archive_root,ORIGINAL_MIGRATION_ROOT.resolve())
   for known_root in roots:
    try:relative=absolute.relative_to(known_root)
    except ValueError:continue
    candidate=(archive_root/relative).resolve(strict=False)
    try:candidate.relative_to(archive_root)
    except ValueError:raise ValueError("recorded source path escapes extracted project root")
    # Prefer the extracted copy even if the original EC2 path still exists.
    return candidate
   raise ValueError("absolute recorded source path is outside the supplied project and known migration root")
  candidate=(archive_root/raw).resolve(strict=False)
  try:candidate.relative_to(archive_root)
  except ValueError:raise ValueError("relative recorded source path escapes extracted project root")
  return candidate
 def source_arrays(self,task,bykey):
  tr=task.get("train_key")
  if tr:
   dep=bykey.get(tr)
   if dep is None:raise FileNotFoundError(f"train_key not found in registry: {tr}")
   p=self.task_art(dep)/"data.npz"; z=self.load_npz(p)
   X=_safe_float(z["X"]);y=np.asarray(z["y"],dtype=np.int64)
   ids=np.asarray(z["ids"]) if "ids" in z else np.arange(len(y),dtype=np.int64)
   return X,y,ids,[p]
  p,z=self.role(task["rep"])
  return _safe_float(z["X_fit"]),np.asarray(z["y_fit"],dtype=np.int64),np.asarray(z["fit_ids"]),[p]
 def _uses_tuning(self,t):
  mode=t.get("selection_mode")
  if mode=="tune":return True
  if mode=="fixed":return False
  return not t.get("selection_source") and not t.get("selection_key") and int(t.get("trials") or 0)>0
 def _check_optimizer_seed(self,t,selection):
  if self._uses_tuning(t) and t.get("optimizer_seed") is not None and selection.get("optimizer_seed")!=t.get("optimizer_seed"):
   self.issue(t["key"],"fit","optimizer_seed",f"task={t.get('optimizer_seed')}; selection={selection.get('optimizer_seed')}")
 def _fixed_selection_audit(self,t,bykey,params,selection,paths):
  key=t["key"];source_key=t.get("selection_key");source_ref=t.get("selection_source")
  if bool(source_key)==bool(source_ref):
   self.issue(key,"fit","fixed_selection_source_missing","fixed selection must declare exactly one selection_key or selection_source");return
  if selection is None:
   self.issue(key,"fit","fixed_selection_record_missing","fixed selection requires published selection.json")
  if source_key:
   src=bykey.get(source_key)
   if not src:
    self.issue(key,"fit","fixed_selection_key_missing",source_key);return
   if src.get("kind")!="fit" or src.get("status")!="validated_terminal" or src.get("outcome")!="successful" or src.get("method")!=t.get("method") or src.get("rep")!=t.get("rep"):
    self.issue(key,"fit","fixed_selection_key_invalid",f"source={source_key}; kind={src.get('kind')}; status={src.get('status')}; outcome={src.get('outcome')}; method={src.get('method')}; rep={src.get('rep')}")
   sout=self.task_art(src);sp=sout/"selection.json";pp=sout/"pipeline.joblib";paths.extend([sp,pp])
   if not sp.is_file():
    self.issue(key,"fit","fixed_selection_source_record_missing",sp);return
   try:ss=json.loads(sp.read_text());source_params=ss.get("selected_params",ss.get("params"))
   except Exception as e:self.issue(key,"fit","fixed_selection_source_record_read",e);return
   smeta=src.get("result",{}).get("result",{});registered_pipe=smeta.get("pipeline_sha256")
   if source_params is None or source_params!=smeta.get("params"):
    self.issue(key,"fit","fixed_selection_source_params",f"selection={source_params}; source_result={smeta.get('params')}")
   if params!=source_params:self.issue(key,"fit","fixed_selection_params",f"current={params}; source={source_params}")
   if selection is not None and selection.get("selected_params",selection.get("params"))!=source_params:
    self.issue(key,"fit","fixed_selection_record_params",f"current_selection={selection.get('selected_params',selection.get('params'))}; source={source_params}")
   observed_pipe=self.file_hash(pp) if pp.is_file() else None
   if not observed_pipe or not registered_pipe or observed_pipe!=registered_pipe:
    self.issue(key,"fit","fixed_selection_source_pipeline_hash",f"source_result={registered_pipe}; observed={observed_pipe}")
   return
  try:
   source_path=self.resolve_recorded_path(source_ref)
   source_selection=source_path/"selection.json" if source_path.is_dir() else source_path
  except Exception as e:
   self.issue(key,"fit","fixed_selection_source_path_invalid",e);return
  paths.append(source_selection)
  if not source_selection.is_file():
   self.issue(key,"fit","fixed_selection_source_record_missing",source_selection);return
  try:imported=json.loads(source_selection.read_text())
  except Exception as e:self.issue(key,"fit","fixed_selection_source_record_read",e);return
  imported_params=imported.get("selected_params",imported.get("params"))
  if imported_params is None or imported_params!=params:
   self.issue(key,"fit","fixed_selection_params",f"current={params}; imported={imported_params}")
  if selection is not None and selection.get("selected_params",selection.get("params"))!=imported_params:
   self.issue(key,"fit","fixed_selection_record_params",f"current_selection={selection.get('selected_params',selection.get('params'))}; imported={imported_params}")
  raw_source=imported.get("source_path");expected_sha=imported.get("source_sha256")
  if not raw_source or not isinstance(expected_sha,str) or not imported.get("provenance") or imported.get("source_status")!="complete":
   self.issue(key,"fit","fixed_selection_source_metadata_missing","imported selection lacks source_path/source_sha256/provenance/complete status");return
  try:source_file=self.resolve_recorded_path(raw_source)
  except Exception as e:self.issue(key,"fit","fixed_selection_frozen_path_invalid",e);return
  paths.append(source_file)
  observed_sha=self.file_hash(source_file) if source_file.is_file() else None
  if observed_sha!=expected_sha:
   self.issue(key,"fit","fixed_selection_frozen_hash",f"recorded={expected_sha}; observed={observed_sha}; path={source_file}");return
  try:complete=json.loads(source_file.read_text())
  except Exception as e:self.issue(key,"fit","fixed_selection_frozen_read",e);return
  original_params=complete.get("selected_params",complete.get("params"))
  if complete.get("status")!="complete":self.issue(key,"fit","fixed_selection_frozen_status",complete.get("status"))
  if original_params is None or original_params!=imported_params or original_params!=params:
   self.issue(key,"fit","fixed_selection_frozen_params",f"original={original_params}; imported={imported_params}; current={params}")
  if imported.get("source_tuning_balanced_accuracy") is not None and complete.get("best_tuning_balanced_accuracy") is not None and not np.isclose(float(imported["source_tuning_balanced_accuracy"]),float(complete["best_tuning_balanced_accuracy"]),rtol=0,atol=1e-12):
   self.issue(key,"fit","fixed_selection_source_score",f"imported={imported.get('source_tuning_balanced_accuracy')}; original={complete.get('best_tuning_balanced_accuracy')}")
 def fit_audit(self,t,bykey):
  key=t["key"]; out=self.task_art(t); p=out/"pipeline.joblib"
  if not self.file_exists(p): self.issue(key,"fit","pipeline_missing",p);return [p]
  try:
   import joblib
   pipe=self.load_joblib(p)
  except Exception as e:self.issue(key,"fit","pipeline_load",e);return [p]
  paths=[p]
  for name in ("selection.json","fit_result.json"):
   q=out/name
   if q.exists():paths.append(q)
  try:X,y,ids,src=self.source_arrays(t,bykey);paths+=src
  except Exception as e:self.issue(key,"fit","training_source",e);return paths
  if X.ndim!=2 or X.shape[1]!=6 or len(X)!=len(y) or np.isinf(X).any():
   self.issue(key,"fit","training_shape_or_infinity",f"shape={X.shape}, labels={y.shape}, inf={bool(np.isinf(X).any())}")
  actual=np.bincount(y,minlength=7).astype(int).tolist()
  meta=t.get("result",{}).get("result",{})
  fit_doc={};fit_doc_path=out/"fit_result.json"
  if fit_doc_path.is_file():
   try:
    fit_doc=json.loads(fit_doc_path.read_text())
    fit_doc=fit_doc.get("result",fit_doc) if isinstance(fit_doc,dict) else {}
   except Exception as e:self.issue(key,"fit","fit_result_read",e)
  method=str(t.get("method") or meta.get("method") or "")
  declared=_declared_score_kinds(pipe,meta,fit_doc)
  expected_kind="margin" if method in {"linear_svm","rbf_svm"} else "probability"
  for source,declared_kind in declared:
   if declared_kind is not None and declared_kind not in {"probability","margin"}:self.issue(key,"fit","score_kind_invalid",f"{source}={declared_kind}")
   elif declared_kind is not None and declared_kind!=expected_kind:self.issue(key,"fit","score_kind_method_mismatch",f"method={method}; {source}={declared_kind}; expected={expected_kind}")
  if int(t.get("experiment") or 0)>=4 and method in {"linear_svm","rbf_svm"} and not any(v=="margin" for _,v in declared):
   self.issue(key,"fit","score_kind_missing","versioned SVM fit must declare native margin output in fit metadata")
  if pipe.get("class_counts")!=actual:self.issue(key,"fit","pipeline_class_counts",f"pipeline={pipe.get('class_counts')}; observed={actual}")
  if meta.get("class_counts")!=actual:self.issue(key,"fit","result_class_counts",f"result={meta.get('class_counts')}; observed={actual}")
  stored_rows=pipe.get("training_rows",meta.get("training_rows"))
  if stored_rows is not None and int(stored_rows)!=len(y):self.issue(key,"fit","training_rows",f"pipeline={pipe.get('training_rows')}; result={meta.get('training_rows')}; observed={len(y)}")
  got=sha256_ids(ids)
  if pipe.get("training_ids_sha256")!=got:self.issue(key,"fit","training_ids_hash",f"pipeline={pipe.get('training_ids_sha256')}; exact={got}")
  if meta.get("training_ids_sha256") and meta["training_ids_sha256"]!=got:self.issue(key,"fit","result_training_ids_hash",f"result={meta['training_ids_sha256']}; exact={got}")
  if meta.get("source_sha256"):
   source_ref=(meta.get("source") or (t.get("source_metadata") or {}).get("path")) if meta.get("reused") else (src[0] if src else None)
   if source_ref:
    try:source_path=self.resolve_recorded_path(source_ref)
    except ValueError as e:
     source_path=None;self.issue(key,"fit","source_path_invalid",e)
    if source_path is not None:
     observed_source=self.file_hash(source_path)
     if observed_source!=meta.get("source_sha256"):self.issue(key,"fit","source_hash",f"result={meta.get('source_sha256')}; source={observed_source}; path={source_path}")
  if meta.get("pipeline_sha256") and self.file_hash(p)!=meta.get("pipeline_sha256"):self.issue(key,"fit","pipeline_hash",f"result={meta.get('pipeline_sha256')}; actual={self.file_hash(p)}")
  if pipe.get("seed")!=meta.get("seed"):self.issue(key,"fit","pipeline_seed",f"pipeline={pipe.get('seed')}; result={meta.get('seed')}")
  if t.get("seed") is not None and pipe.get("seed")!=t.get("seed"):self.issue(key,"fit","task_seed",f"task={t.get('seed')}; pipeline={pipe.get('seed')}")
  params=pipe.get("params")
  if params!=meta.get("params"):self.issue(key,"fit","selected_params",f"pipeline={params}; result={meta.get('params')}")
  sel=out/"selection.json"
  if sel.exists():
   try:
    s=json.loads(sel.read_text())
    if s.get("selected_params")!=params:self.issue(key,"fit","selection_params",f"selection={s.get('selected_params')}; pipeline={params}")
    if t.get("selection_mode")=="fixed":self._fixed_selection_audit(t,bykey,params,s,paths)
    else:self._check_optimizer_seed(t,s)
   except Exception as e:self.issue(key,"fit","selection_read",e)
  elif t.get("selection_mode")=="fixed":
   self._fixed_selection_audit(t,bykey,params,None,paths)
  elif meta.get("reused"):
   sm=t.get("source_metadata") or {}
   if sm.get("selected_params_match") is False:self.issue(key,"fit","source_selected_params","source metadata records selected_params_match=false")
   source_ref=meta.get("source") or sm.get("path")
   try:srcpipe=self.resolve_recorded_path(source_ref) if source_ref else None
   except ValueError as e:
    srcpipe=None;self.issue(key,"fit","source_path_invalid",e)
   if srcpipe and self.file_exists(srcpipe):
    try:
     original=self.load_joblib(srcpipe)
     if original.get("params")!=params:self.issue(key,"fit","source_params",f"source={original.get('params')}; pipeline={params}")
     if original.get("seed")!=pipe.get("seed"):self.issue(key,"fit","source_seed",f"source={original.get('seed')}; pipeline={pipe.get('seed')}")
     if meta.get("source_sha256") and self.file_hash(srcpipe)!=meta.get("source_sha256"):self.issue(key,"fit","source_pipeline_hash","source pipeline hash differs from fit result")
     paths.append(srcpipe)
    except Exception as e:self.issue(key,"fit","source_pipeline_load",e)
   elif sm.get("selected_params_match") is not True:self.issue(key,"fit","source_pipeline_unavailable",str(srcpipe or source_ref or "missing source pipeline path"))
  elif self._uses_tuning(t) and t.get("optimizer_seed") is not None:
   self.issue(key,"fit","selection_missing",f"tuning task has optimizer_seed={t.get('optimizer_seed')} but no selection.json")
  # Recompute preprocessing from the exact permitted raw training source only.
  try:
   from sklearn.impute import SimpleImputer
   from sklearn.preprocessing import StandardScaler
   imp=pipe["imputer"];sc=pipe["scaler"]
   if np.isnan(X).all(axis=0).any():self.issue(key,"fit","all_missing_training_feature","one or more columns entirely NaN")
   expected_imp=SimpleImputer(strategy="median",keep_empty_features=True).fit(X).statistics_
   if not _eq(imp.statistics_,expected_imp):self.issue(key,"fit","imputer_statistics",f"observed={imp.statistics_.tolist()}; recomputed={expected_imp.tolist()}")
   Xi=SimpleImputer(strategy="median",keep_empty_features=True).fit(X).transform(X)
   expected_sc=StandardScaler().fit(Xi)
   if not _eq(sc.mean_,expected_sc.mean_):self.issue(key,"fit","scaler_mean","stored scaler mean differs from raw fitting rows")
   if not _eq(sc.scale_,expected_sc.scale_):self.issue(key,"fit","scaler_scale","stored scaler scale differs from raw fitting rows")
  except Exception as e:self.issue(key,"fit","preprocessing_check",e)
  if self.require_calibration_replay and key not in self._replay_proof_fit_keys:
   self._replay_fit_calibrations(t,bykey,pipe,p)
  return paths
 def _restore_replay_cache_for_fit(self,fit_task,bykey):
  """Verify immutable q proof without loading the pipeline or rescoring X_cal."""
  import calibration_replay as cr
  fitkey=fit_task["key"]
  if any(x.get("kind")=="ensemble" and int(x.get("experiment") or 0)==6 and x.get("e6_protocol_version")=="E6-v2"
         and x.get("status")=="validated_terminal" and x.get("outcome")=="successful"
         and fitkey in (x.get("members") or {}).values() for x in bykey.values()):
   # No accepted-prior native E6-member replay index exists yet, so do not let
   # a legacy eval-only cache proof skip fresh E6 calibration scoring.
   return False
  evals=[x for x in bykey.values() if x.get("kind")=="eval" and x.get("fit_key")==fitkey
         and int(x.get("experiment") or 0) in {3,4,5,6} and x.get("status")=="validated_terminal" and x.get("outcome")=="successful"]
  if not evals:return True
  try:
   pipeline_path=self.task_art(fit_task)/"pipeline.joblib"; pipeline_sha=self.file_hash(pipeline_path,force=True)
   role_path,role=self.role(fit_task["rep"],["X_cal","y_cal","calibration_ids"])
   role_logical=role_path.resolve().relative_to(self.rt).as_posix()
   pipeline_logical=pipeline_path.resolve().relative_to(self.rt).as_posix()
   X=np.asarray(role["X_cal"],dtype=np.float64); y=np.asarray(role["y_cal"],dtype=np.int64); ids=np.asarray(role["calibration_ids"])
   if len(X)!=len(y) or len(ids)!=len(y):return False
   role_sha=self.file_hash(role_path,force=True); method=str(fit_task.get("method") or "")
   module,source_sha,frozen_source_report_sha=self._frozen_scoring_source(method)
   if method in {"gmm","copula","kde","chow_liu"}: class_contract="frozen models_flexible._FlexibleModel class_models indexed 0..6"
   elif method=="arf": class_contract="frozen ARFDensityModel CLASS_IDS order"
   elif method in {"gaussian_nb","shared_diagonal","lda","qda"}: class_contract="frozen GaussianDensityModel CLASS_IDS order"
   else: class_contract="frozen ClassifierModel estimator.classes_"
   fit_counts=fit_task.get("result",{}).get("result",{}).get("class_counts")
   if not isinstance(fit_counts,list) or len(fit_counts)!=7:return False
   deps_base={"numpy":np.__version__,"scoring_module_sha256":source_sha,"frozen_source_report_sha256":frozen_source_report_sha,
      "class_order_contract":class_contract,"fit_class_counts":fit_counts}
   try:
    import sklearn,joblib,scipy
    deps_base.update({"scikit_learn":sklearn.__version__,"joblib":joblib.__version__,"scipy":scipy.__version__})
   except Exception:return False
   helper_path=Path(__file__).with_name("calibration_replay.py"); helper_sha=cr.file_sha(helper_path)
   pending=[]
   for ev in evals:
    evpath=self.task_art(ev)/"evaluation.json"
    if not evpath.is_file():return False
    saved=json.loads(evpath.read_text()); kind=saved.get("score_kind")
    if kind not in {"probability","margin"}:return False
    eval_sha=self.file_hash(evpath,force=True); calpath=self.task_art(ev)/"calibration.json"; caldoc=None;calsha=None
    if calpath.is_file():calsha=self.file_hash(calpath,force=True);caldoc=json.loads(calpath.read_text())
    ident,idoc=cr.make_identity(pipeline_sha256=pipeline_sha,role_file_sha256=role_sha,ids=ids,X=X,y=y,kind=kind,
       helper_sha256=helper_sha,dependencies={**deps_base,"source_evaluation_sha256":eval_sha,"calibration_json_sha256":calsha})
    prior_receipt_sha=self.accepted_prior_receipts.get(ident)
    if not prior_receipt_sha:return False
    path=self.rt/"artifacts"/"calibration_replay"/ident
    if not path.is_dir():return False
    replay=cr.load_replay(path,ident); md=replay["metadata"]
    if any(md.get(k)!=v for k,v in {**idoc,"task_key":ev["key"],"fit_key":fitkey,"role_path":role_logical,
       "pipeline_path":pipeline_logical,"source_evaluation_sha256":eval_sha,"calibration_json_sha256":calsha,"scoring_module_sha256":source_sha,
       "frozen_source_report_sha256":frozen_source_report_sha,
       "class_order_source":class_contract}.items()):return False
    derived={"threshold":md["threshold"],"calibration_n":md["calibration_n"],"rank_k":md["rank_k"],
       "score_kind":md["score_kind"],"nonconformity_rule":md["nonconformity_rule"],"nonconformity":replay["nonconformity"]}
    reasons=cr.compare(saved,derived,fitkey,pipeline_sha,require_rule=(kind=="margin"))
    if caldoc is not None:reasons += ["calibration.json:"+z for z in cr.compare(caldoc,derived,fitkey,pipeline_sha)]
    meta_path=path/"metadata.json";vec_path=path/"nonconformity.npz"
    pending.append({"fit_key":fitkey,"pipeline_sha256":pipeline_sha,"task_key":ev["key"],"status":"mismatch" if reasons else "validated",
       "supervision_mode":"cache_reuse","prior_receipt_sha256":prior_receipt_sha,
       "role_file_sha256":role_sha,"calibration_ids_sha256":cr.typed_sha(ids),"X_cal_sha256":cr.typed_sha(X),"y_cal_sha256":cr.typed_sha(y),
       "score_kind":kind,"nonconformity_rule":derived["nonconformity_rule"],"alpha":.1,"class_order":list(range(7)),
       "class_order_source":class_contract,"scoring_module_sha256":source_sha,"frozen_source_report_sha256":frozen_source_report_sha,"saved_threshold":saved.get("threshold"),
       "recomputed_threshold":derived["threshold"],"calibration_n":len(y),"rank_k":derived["rank_k"],"identity":ident,
       "metadata_path":str(meta_path.relative_to(self.rt)),"nonconformity_path":str(vec_path.relative_to(self.rt)),
       "metadata_sha256":self.file_hash(meta_path,force=True),"nonconformity_file_sha256":self.file_hash(vec_path,force=True),
       "nonconformity_sha256":cr.typed_sha(replay["nonconformity"]),"reasons":reasons})
   self.calibration_replay_physical.extend(pending)
   self._replay_proof_fit_keys.add(fitkey)
   phase_id=uuid.uuid4().hex
   prior={x["task_key"]:x["prior_receipt_sha256"] for x in pending}
   self._append_calibration_phase_event(phase_id,"start","cache_reuse",fitkey,[x["key"] for x in evals],prior_receipts=prior)
   self._append_calibration_phase_event(phase_id,"finish","cache_reuse",fitkey,[x["key"] for x in evals],prior_receipts=prior)
   return True
  except Exception:return False
 def _replay_fit_calibrations(self,fit_task,bykey,pipe,pipeline_path):
  """Recompute calibration q from clean calibration rows; never reads test X."""
  import calibration_replay as cr
  fitkey=fit_task["key"]; out=self.rt/"artifacts"/"calibration_replay"
  evals=[x for x in bykey.values() if x.get("kind")=="eval" and x.get("fit_key")==fitkey
         and int(x.get("experiment") or 0) in {3,4,5,6}
         and x.get("status")=="validated_terminal" and x.get("outcome")=="successful"]
  e6_tasks=[x for x in bykey.values() if x.get("kind")=="ensemble" and int(x.get("experiment") or 0)==6
       and x.get("e6_protocol_version")=="E6-v2" and x.get("status")=="validated_terminal"
       and x.get("outcome")=="successful" and fitkey in (x.get("members") or {}).values()]
  if not evals and not e6_tasks:return
  self.calibration_replay_phase_started_utc=datetime.now(timezone.utc).isoformat()
  phase_id=uuid.uuid4().hex; phase_tasks=sorted({x["key"] for x in evals+e6_tasks})
  self._append_calibration_phase_event(phase_id,"start","replayed",fitkey,phase_tasks)
  self._write_calibration_replay_progress(fitkey,phase_tasks[0])
  rowbase={"fit_key":fitkey,"pipeline_sha256":self.file_hash(pipeline_path,force=True)}
  try:
   role_path,role=self.role(fit_task["rep"],["X_cal","y_cal","calibration_ids"])
   role_logical=role_path.resolve().relative_to(self.rt).as_posix()
   pipeline_logical=pipeline_path.resolve().relative_to(self.rt).as_posix()
   Xcal=np.asarray(role["X_cal"],dtype=np.float64); ycal=np.asarray(role["y_cal"],dtype=np.int64)
   ids=np.asarray(role["calibration_ids"])
   if len(Xcal)!=len(ycal) or len(ids)!=len(ycal):raise ValueError("calibration role shape mismatch")
   fit_counts=np.asarray(pipe.get("class_counts",[]),dtype=np.int64)
   registry_fit=fit_task.get("result",{}).get("result",{}).get("class_counts")
   if fit_counts.shape!=(7,) or np.any(fit_counts<0) or fit_counts.sum()!=int(pipe.get("training_rows",-1)):
    raise ValueError("selected pipeline lacks verified seven-class fitting counts")
   if registry_fit is None or not np.array_equal(fit_counts,np.asarray(registry_fit,dtype=np.int64)):
    raise ValueError("registry and selected pipeline fitting class counts differ")
   model=pipe["model"]; kind=getattr(model,"score_kind","probability")
   if kind not in {"probability","margin"}:raise ValueError("unsupported model score_kind")
   method=str(fit_task.get("method") or "")
   module,source_hash,frozen_source_report_sha=self._frozen_scoring_source(method)
   classes=getattr(model,"classes_",None)
   if classes is None and getattr(model,"estimator",None) is not None:classes=getattr(model.estimator,"classes_",None)
   if classes is not None and not np.array_equal(np.asarray(classes),np.arange(7)):
    raise ValueError("model class order is not 0..6")
   if method in {"gmm","copula","kde","chow_liu"}:
    cls=getattr(module,"_FlexibleModel",None)
    if cls is None or not isinstance(model,cls):raise ValueError("fitted model type does not match frozen flexible-model source")
    if getattr(model,"method",None)!=method:raise ValueError("frozen flexible model method differs from registry")
    if not isinstance(getattr(model,"class_models",None),list) or len(model.class_models)!=7 or np.asarray(getattr(model,"priors",[])).shape!=(7,):raise ValueError("frozen flexible model lacks seven class-indexed columns")
    if not np.allclose(np.asarray(model.priors,dtype=float),fit_counts/fit_counts.sum(),atol=1e-12,rtol=0):raise ValueError("flexible model priors differ from verified fit class counts")
    if any((model.class_models[c] is not None)!=(fit_counts[c]>0) for c in range(7)):raise ValueError("flexible model class slots disagree with fit class counts")
    class_order_source="frozen models_flexible._FlexibleModel class_models indexed 0..6"
   elif method=="arf":
    cls=getattr(module,"ARFDensityModel",None)
    if cls is None or not isinstance(model,cls):raise ValueError("fitted model type does not match frozen ARF source")
    if len(getattr(model,"models_",[]))!=7 or np.asarray(getattr(model,"priors_",[])).shape!=(7,):
     raise ValueError("frozen ARF model lacks seven class-indexed estimators")
    if not np.allclose(np.asarray(model.priors_,dtype=float),fit_counts/fit_counts.sum(),atol=1e-12,rtol=0):raise ValueError("ARF priors differ from verified fit class counts")
    class_order_source="frozen ARFDensityModel CLASS_IDS order"
   elif method in {"gaussian_nb","shared_diagonal","lda","qda"}:
    cls=getattr(module,"GaussianDensityModel",None)
    if cls is None or not isinstance(model,cls):raise ValueError("fitted model type does not match frozen GaussianDensityModel source")
    if getattr(model,"method",None)!=method:raise ValueError("frozen Gaussian model method differs from registry")
    if np.asarray(getattr(model,"means_",[])).shape[0]!=7 or np.asarray(getattr(model,"priors_",[])).shape!=(7,):
     raise ValueError("frozen GaussianDensityModel lacks seven class-indexed columns")
    if not np.allclose(np.asarray(model.priors_,dtype=float),fit_counts/fit_counts.sum(),atol=1e-12,rtol=0):raise ValueError("Gaussian model priors differ from verified fit class counts")
    class_order_source="frozen GaussianDensityModel CLASS_IDS order"
   else:
    cls=getattr(module,"ClassifierModel",None)
    if cls is None or not isinstance(model,cls):raise ValueError("fitted classifier type does not match frozen ClassifierModel source")
    if not np.array_equal(np.asarray(getattr(model.estimator,"classes_",[])),np.arange(7)):
     raise ValueError("frozen classifier estimator classes_ are not 0..6")
    class_order_source="frozen ClassifierModel estimator.classes_"
   Xt=pipe["scaler"].transform(pipe["imputer"].transform(Xcal)); parts=[]
   for i in range(0,len(Xt),50000):
    block=Xt[i:i+50000]
    if hasattr(model,"score_matrix"): score=np.asarray(model.score_matrix(block),dtype=np.float64)
    elif kind=="probability" and hasattr(model,"predict_proba"): score=np.asarray(model.predict_proba(block),dtype=np.float64)
    else: raise ValueError("selected model has no declared score interface")
    if score.shape!=(len(block),7):raise ValueError("score output does not have seven classes")
    parts.append(score)
   scores=np.concatenate(parts,axis=0)
   derived=cr.derive(scores,ycal,kind)
   role_sha=self.file_hash(role_path,force=True); pipeline_sha=rowbase["pipeline_sha256"]
   if e6_tasks:
    from e6_v2_validation import persist_native_nonconformity
    native_identity_payload={"fit_key":fitkey,"pipeline_sha256":pipeline_sha,"role_file_sha256":role_sha,
       "calibration_ids_sha256":cr.typed_sha(ids),"X_cal_sha256":cr.typed_sha(Xcal),"y_cal_sha256":cr.typed_sha(ycal),
       "score_kind":kind,"nonconformity_rule":derived["nonconformity_rule"],"alpha":.1,"class_order":list(range(7)),
       "class_order_source":class_order_source,"scoring_module_sha256":source_hash,
       "frozen_source_report_sha256":frozen_source_report_sha,"calibration_replay_helper_sha256":cr.file_sha(Path(__file__).with_name("calibration_replay.py"))}
    native_proof=persist_native_nonconformity(self.rt,native_identity_payload,derived["nonconformity"],
       {"threshold":derived["threshold"],"rank_k":derived["rank_k"],"score_kind":kind,
        "nonconformity_rule":derived["nonconformity_rule"],"alpha":.1,"class_order":list(range(7)),
        "fit_key":fitkey,"pipeline_sha256":pipeline_sha,"role_file_sha256":role_sha,
        "calibration_ids_sha256":cr.typed_sha(ids),"X_cal_sha256":cr.typed_sha(Xcal),"y_cal_sha256":cr.typed_sha(ycal),
        "scoring_module_sha256":source_hash,"frozen_source_report_sha256":frozen_source_report_sha})
    self._e6_native_calibration_scores[fitkey]={"scores":np.asarray(scores,dtype=np.float64),"y":ycal.copy(),
       "pipeline_sha256":pipeline_sha,"role_file_sha256":role_sha,"calibration_ids_sha256":cr.typed_sha(ids),
       "X_cal_sha256":cr.typed_sha(Xcal),"y_cal_sha256":cr.typed_sha(ycal),"score_kind":kind,
       "class_order":list(range(7)),"class_order_source":class_order_source,"native_proof":native_proof}
    for e6task in e6_tasks:
     members=e6task.get("members",{}); member=next((n for n,k in members.items() if k==fitkey),None)
     expected=e6task.get("member_fit_evidence",{}).get(member,{}) if member else {}
     art=self.task_art(e6task); comparison_path=art/"member_comparisons.json"; evaluation_path=art/"evaluation.json"
     row={"task_key":e6task["key"],"fit_key":fitkey,"member":member,"status":"unavailable",
       "supervision_mode":"native_calibration_replay","pipeline_sha256":pipeline_sha,
       "role_file_sha256":role_sha,"calibration_ids_sha256":cr.typed_sha(ids),
       "X_cal_sha256":cr.typed_sha(Xcal),"y_cal_sha256":cr.typed_sha(ycal),
       "calibration_n":len(ycal),"score_kind":kind,"nonconformity_rule":derived["nonconformity_rule"],
       "alpha":.1,"class_order":list(range(7)),"class_order_source":class_order_source,
       "native_threshold":derived["threshold"],"native_nonconformity_sha256":cr.typed_sha(derived["nonconformity"]),
       "native_replay_identity":native_proof["identity"],"native_replay_metadata_path":native_proof["metadata_path"],
       "native_replay_metadata_sha256":native_proof["metadata_sha256"],"native_replay_vector_path":native_proof["nonconformity_path"],
       "native_replay_vector_file_sha256":native_proof["nonconformity_file_sha256"],
       "native_replay_vector_sha256":native_proof["nonconformity_sha256"],"rank_k":native_proof["rank_k"],
       "fit_ids_sha256":expected.get("fit_ids_sha256"),"role_membership_sha256":expected.get("role_membership_sha256"),
       "selected_params_sha256":expected.get("selected_params_sha256"),"provenance_group":expected.get("provenance_group"),
       "comparison_path":"member_comparisons.json","comparison_sha256":None,"reasons":[]}
     try:
      if member not in {"gmm","copula","arf","kde","chow_liu"}:raise ValueError("fit is not a named E6 member")
      comparison=json.loads(comparison_path.read_text());evdoc=json.loads(evaluation_path.read_text())
      member_row=comparison["members"][member]
      if comparison.get("protocol_version")!="E6-v2" or comparison.get("comparison_source_task_key")!=e6task["key"]:raise ValueError("E6 comparison task/version mismatch")
      if member_row.get("fit_key")!=fitkey or member_row.get("pipeline_sha256")!=pipeline_sha:raise ValueError("E6 member fit/pipeline identity mismatch")
      if member_row.get("role_membership_sha256")!=expected.get("role_membership_sha256") or member_row.get("selection_sha256")!=expected.get("selection_sha256") or member_row.get("fit_result_sha256")!=expected.get("fit_result_sha256") or member_row.get("validation_sha256")!=expected.get("validation_sha256"):raise ValueError("E6 member fit evidence mismatch")
      if member_row.get("score_kind")!=kind or member_row.get("alpha")!=.1 or member_row.get("calibration_n")!=len(ycal):raise ValueError("E6 member score/calibration contract mismatch")
      if not math.isclose(float(member_row.get("calibration_threshold")),float(derived["threshold"]),rel_tol=0,abs_tol=1e-10):raise ValueError("E6 saved member threshold differs from fresh native calibration score")
      if evdoc.get("member_comparisons_sha256")!=self.file_hash(comparison_path,force=True):raise ValueError("E6 comparison file SHA mismatch")
      row.update({"status":"validated","comparison_sha256":evdoc["member_comparisons_sha256"],"reasons":[]})
     except Exception as exc:row["status"]="mismatch";row["reasons"]=[f"{type(exc).__name__}: {exc}"]
     self.e6_member_calibration_records.append(row)
   helper_path=Path(__file__).with_name("calibration_replay.py")
   deps={"numpy":np.__version__,"scoring_module_sha256":source_hash,"frozen_source_report_sha256":frozen_source_report_sha,
         "class_order_contract":class_order_source,
         "fit_class_counts":fit_counts.astype(int).tolist()}
   try:
    import sklearn,joblib,scipy
    deps.update({"scikit_learn":sklearn.__version__,"joblib":joblib.__version__,"scipy":scipy.__version__})
   except Exception as exc:raise ValueError(f"required scoring dependency version unavailable: {type(exc).__name__}: {exc}")
   for ev in evals:
    evpath=self.task_art(ev)/"evaluation.json"
    try:
     eval_sha=self.file_hash(evpath,force=True); saved=json.loads(evpath.read_text()); reasons=cr.compare(saved,derived,fitkey,pipeline_sha,require_rule=(kind=="margin"))
     calpath=self.task_art(ev)/"calibration.json"; caldoc=None; calsha=None
     if calpath.is_file():
      calsha=self.file_hash(calpath,force=True); caldoc=json.loads(calpath.read_text())
      reasons += ["calibration.json:"+x for x in cr.compare(caldoc,derived,fitkey,pipeline_sha)]
     ident,idoc=cr.make_identity(pipeline_sha256=pipeline_sha,role_file_sha256=role_sha,ids=ids,X=Xcal,y=ycal,
       kind=kind,helper_sha256=cr.file_sha(helper_path),dependencies={**deps,"source_evaluation_sha256":eval_sha,"calibration_json_sha256":calsha})
     md={**idoc,"task_key":ev["key"],"fit_key":fitkey,"role_path":role_logical,"pipeline_path":pipeline_logical,
         "source_evaluation_sha256":eval_sha,"calibration_json_sha256":calsha,"scoring_module_sha256":source_hash,
         "frozen_source_report_sha256":frozen_source_report_sha,"class_order_source":class_order_source,
         "threshold_comparison_reasons":reasons}
     dest=cr.save_replay(out,ident,derived,md)
     meta_path=dest/"metadata.json"; vec_path=dest/"nonconformity.npz"
     row={**rowbase,"task_key":ev["key"],"status":"mismatch" if reasons else "validated","supervision_mode":"replayed",
       "role_file_sha256":role_sha,"calibration_ids_sha256":cr.typed_sha(ids),"X_cal_sha256":cr.typed_sha(Xcal),
       "y_cal_sha256":cr.typed_sha(ycal),"score_kind":kind,"nonconformity_rule":derived["nonconformity_rule"],
       "alpha":.1,"class_order":list(range(7)),"class_order_source":class_order_source,"scoring_module_sha256":source_hash,
       "frozen_source_report_sha256":frozen_source_report_sha,"saved_threshold":saved.get("threshold"),
       "recomputed_threshold":derived["threshold"],"calibration_n":len(ycal),"rank_k":derived["rank_k"],
       "identity":ident,"metadata_path":str(meta_path.relative_to(self.rt)),"nonconformity_path":str(vec_path.relative_to(self.rt)),
       "metadata_sha256":self.file_hash(meta_path,force=True),"nonconformity_file_sha256":self.file_hash(vec_path,force=True),
       "nonconformity_sha256":cr.typed_sha(derived["nonconformity"]),"reasons":reasons}
     self.calibration_replay_physical.append(row)
    except Exception as e:
     self.calibration_replay_physical.append({**rowbase,"task_key":ev["key"],"status":"unavailable","reasons":[f"{type(e).__name__}: {e}"]})
    self._write_calibration_replay_progress(fitkey,ev["key"])
  except Exception as e:
   for ev in evals:self.calibration_replay_physical.append({**rowbase,"task_key":ev["key"],"status":"unavailable","reasons":[f"{type(e).__name__}: {e}"]})
   self._write_calibration_replay_progress(fitkey,None)
  finally:
   self._append_calibration_phase_event(phase_id,"finish","replayed",fitkey,phase_tasks)
   self._write_calibration_replay_progress(None,None,state="idle")
 def _append_calibration_phase_event(self,phase_id,event,mode,fit_key,task_keys,prior_receipts=None):
  path=self.calibration_replay_phase_ledger_path;path.parent.mkdir(parents=True,exist_ok=True)
  ticks=None
  try:
   stat=Path(f"/proc/{os.getpid()}/stat").read_text();tail=stat[stat.rfind(")")+1:].split();ticks=int(tail[19])
  except Exception:pass
  row={"schema_version":"lamost-calibration-replay-phase-ledger/1","run_nonce":self.calibration_replay_run_id,
   "phase_id":phase_id,"event":event,"mode":mode,"phase":"calibration_score_replay" if mode=="replayed" else "cache_reuse",
   "fit_key":fit_key,"task_keys":list(task_keys),"prior_receipts":prior_receipts or {},"pid":os.getpid(),
   "process_start_ticks":ticks,"monotonic":time.monotonic(),"utc":datetime.now(timezone.utc).isoformat()}
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
  try:os.write(fd,(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n").encode());os.fsync(fd)
  finally:os.close(fd)
 def _write_calibration_replay_progress(self,current_fit=None,current_task=None,state="running"):
  running=state=="running"
  if running and self.calibration_replay_phase_started_monotonic is None:
   self.calibration_replay_phase_started_monotonic=time.monotonic()
   if self.calibration_replay_phase_started_utc is None:self.calibration_replay_phase_started_utc=datetime.now(timezone.utc).isoformat()
  if not running:self.calibration_replay_phase_started_monotonic=None;self.calibration_replay_phase_started_utc=None
  counts={s:sum(x.get("status")==s for x in self.calibration_replay_physical) for s in ("validated","mismatch","unavailable")}
  _atomic_json(self.rt/"reports"/"CALIBRATION_REPLAY_PROGRESS.json",{"schema_version":"lamost-calibration-replay-progress/1",
   "generated_utc":datetime.now(timezone.utc).isoformat(),"run_nonce":self.calibration_replay_run_id,"state":"running" if running else "idle",
   "phase":"calibration_score_replay" if running else "idle","phase_started_utc":self.calibration_replay_phase_started_utc if running else None,
   "current_fit_key":current_fit if running else None,"current_task_key":current_task if running else None,"physical_counts":counts,
   "completed_physical_rows":len(self.calibration_replay_physical),"note":"progress only; process liveness requires external PID/start-tick verification"})
  beacon_path=self.rt/"logs"/"operational"/"calibration_replay_supervisor_beacon.json"
  ticks=None
  try:
   stat=Path(f"/proc/{os.getpid()}/stat").read_text();tail=stat[stat.rfind(")")+1:].split();ticks=int(tail[19])
  except Exception:pass
  _atomic_json(beacon_path,{"schema_version":"lamost-calibration-replay-private-beacon/1","run_nonce":self.calibration_replay_run_id,
   "pid":os.getpid(),"process_start_ticks":ticks,"phase_process_monotonic":time.monotonic(),
   "state":"running" if running else "idle","phase":"calibration_score_replay" if running else "idle",
   "phase_started_monotonic":self.calibration_replay_phase_started_monotonic,"phase_started_utc":self.calibration_replay_phase_started_utc,
   "current_fit_key":current_fit if running else None,"current_task_key":current_task if running else None,
   "updated_utc":datetime.now(timezone.utc).isoformat()})
 def generate_audit(self,t,bykey):
  key=t["key"];out=self.task_art(t);p=out/"data.npz";paths=[p]
  if not p.exists():self.issue(key,"generate","data_missing",p);return paths
  try:z=self.load_npz(p);X=_safe_float(z["X"]);y=np.asarray(z["y"],int)
  except Exception as e:self.issue(key,"generate","data_load",e);return paths
  if X.ndim!=2 or X.shape[1]!=6 or len(X)!=len(y) or np.isinf(X).any():self.issue(key,"generate","shape_or_infinity",f"X={X.shape},y={y.shape},inf={np.isinf(X).any()}")
  counts=np.bincount(y,minlength=7).astype(int); result=t.get("result",{}).get("result",{})
  if result.get("n_rows")!=len(y):self.issue(key,"generate","result_rows",f"record={result.get('n_rows')}; actual={len(y)}")
  if result.get("class_counts")!=counts.tolist():self.issue(key,"generate","result_counts",f"record={result.get('class_counts')}; actual={counts.tolist()}")
  if t.get("target_class") is not None:
   c=_label_code(t["target_class"]);cohortkey=next((x for x in t.get("dependencies",[]) if x in bykey and bykey[x].get("kind")=="e4_cohort"),None)
   add=None
   if cohortkey:
    cp=self.task_art(bykey[cohortkey]);mp=cp/"metadata.json"
    if mp.exists():
     paths.append(mp);md=json.loads(mp.read_text());add=md.get("added_count",md.get("restoration_added_count",md.get("restore_added_count")))
   if add is None:self.issue(key,"generate","restore_count_unavailable",f"target-class generation has no added count; cohort dependency={cohortkey}")
   elif len(y)!=int(add) or not np.all(y==c):self.issue(key,"generate","restore_count_or_class",f"actual rows={len(y)}, expected={add}, class={c}, histogram={counts.tolist()}")
   return paths
  fitkey=next((x for x in t.get("dependencies",[]) if x in bykey and bykey[x].get("kind")=="fit"),None)
  if fitkey:
   fit=bykey[fitkey];fp=self.task_art(fit)/"pipeline.joblib";paths.append(fp)
   try:
    import joblib
    pipe=self.load_joblib(fp);fc=np.asarray(pipe["class_counts"],int);n=int(5*int(pipe.get("training_rows",fc.sum())))
    # E3 fixed generation budget is exactly 5 x fitting rows.
    wanted=np.floor(fc*(n/fc.sum())).astype(int)
    for i in np.argsort(-(fc*n/fc.sum()-wanted),kind="stable")[:n-int(wanted.sum())]:wanted[i]+=1
    if len(y)!=n or not np.array_equal(counts,wanted):self.issue(key,"generate","fivefold_counts",f"rows={len(y)} expected={n}; counts={counts.tolist()} expected={wanted.tolist()}")
   except Exception as e:self.issue(key,"generate","generator_fit_dependency",e)
  return paths
 def e4_cohort_audit(self,t,bykey):
  key=t["key"];out=self.task_art(t); p=out/"data.npz";mp=out/"metadata.json";paths=[p,mp]
  if not p.exists() or not mp.exists():self.issue(key,"e4_cohort","artifact_missing",f"{p} / {mp}");return paths
  try:
   z=self.load_npz(p);md=json.loads(mp.read_text());y=np.asarray(z["y"],int);ids=np.asarray(z["ids"]);c=_label_code(t["target_class"]);r=float(t["ratio"])
   if "sample_weight" in z:self.issue(key,"e4_cohort","untreated_cohort_sample_weight","untreated E4 cohort must not serialize per-row weights")
   if md.get("sample_weight_included") is not False:self.issue(key,"e4_cohort","untreated_cohort_weight_metadata",f"sample_weight_included={md.get('sample_weight_included')!r}; expected false")
   rolep,role=self.role(t["rep"]);paths.append(rolep)
   reserved=np.concatenate([role["tuning_ids"],role["calibration_ids"]])
   if np.isin(ids,reserved).any():self.issue(key,"e4_cohort","reserved_id_overlap","cohort contains tuning/calibration IDs")
   counts=np.bincount(y,minlength=7)
   if md.get("target_class") not in (c,t["target_class"]):self.issue(key,"e4_cohort","metadata_target",md.get("target_class"))
   if len(y)!=80000 or int(counts[c])!=int(math.floor(r*np.count_nonzero(role["y_fit"]==c)+.5)):self.issue(key,"e4_cohort","target_quota",f"n={len(y)} target={counts[c]} ratio={r}")
   if not np.array_equal(counts,np.asarray(md.get("realized_counts",[]))):self.issue(key,"e4_cohort","metadata_histogram",f"observed={counts.tolist()} metadata={md.get('realized_counts')}")
  except Exception as e:self.issue(key,"e4_cohort","validation_error",e)
  return paths
 def treatment_audit(self,t,bykey):
  key=t["key"];out=self.task_art(t);p=out/"data.npz";paths=[p]
  ck=t.get("cohort_key")
  if not p.exists() or ck not in bykey:self.issue(key,"e4_treatment","dependency_or_data_missing",f"{p}; cohort={ck}");return paths
  cp=self.task_art(bykey[ck]);cm=cp/"metadata.json";cd=cp/"data.npz";paths.extend([cm,cd])
  try:
   base=self.load_npz(cd);z=self.load_npz(p);bm=json.loads(cm.read_text());y=np.asarray(z["y"],int);yb=np.asarray(base["y"],int);c=_label_code(t["target_class"]);tr=t.get("treatment");add=int(bm.get("added_count",bm.get("restoration_added_count",bm.get("restore_added_count",0))))
   got=np.bincount(y,minlength=7);expected=np.bincount(yb,minlength=7)
   if tr in ("weighted",):
    sw=np.asarray(z.get("sample_weight",[]),dtype=float)
    if len(sw)!=len(y) or not np.isfinite(sw).all() or np.any(sw<=0) or not np.isclose(sw.mean(),1.0,atol=1e-10,rtol=1e-10):
     self.issue(key,"e4_treatment","weight_vector","weighted treatment requires finite positive per-row weights with mean one")
    elif len(orig:=np.asarray(bm.get("source_fit_counts",[]),dtype=float))==7 and np.all(expected>0):
     classw=(orig/orig.sum())/(expected/expected.sum());wantw=classw[yb];wantw/=wantw.mean()
     if np.std(sw)<=1e-12:self.issue(key,"e4_treatment","weight_uniform","E4 weighted arm must retain its nonuniform class-restoration weights")
     if not _eq(sw,wantw):self.issue(key,"e4_treatment","weight_values","sample weights do not match original/altered class proportions normalized to mean one")
   elif tr=="random_oversample" or tr=="ros" or (tr and str(tr).startswith("generated_")) or tr=="smote":
    if "sample_weight" in z:self.issue(key,"e4_treatment","nonweighted_treatment_sample_weight",f"{tr} treatment must not serialize sample_weight")
    expected[c]+=add
   else:self.issue(key,"e4_treatment","unknown_treatment",tr)
   if not np.array_equal(got,expected):self.issue(key,"e4_treatment","final_histogram",f"treatment={tr}; observed={got.tolist()}; expected={expected.tolist()}")
   if tr and str(tr).startswith("generated_"):
    gk=t.get("generated_key");gt=bykey.get(gk) if gk else None
    if gt is None:self.issue(key,"e4_treatment","generated_dependency_missing",gk)
    else:
     gp=self.task_art(gt)/"data.npz";paths.append(gp)
     if not gp.exists():self.issue(key,"e4_treatment","generated_data_missing",gp)
     else:
      gz=self.load_npz(gp);gy=np.asarray(gz["y"],int);gc=np.asarray(gz["X"],float)
      if len(gy)!=add or not np.all(gy==c):self.issue(key,"e4_treatment","generated_count_or_class",f"n={len(gy)} expected={add}; target={c}; actual_counts={np.bincount(gy,minlength=7).tolist()}")
      if len(z["X"])!=len(base["X"])+len(gc) or not np.array_equal(z["y"][:len(yb)],yb) or not np.array_equal(z["X"][:len(yb)],base["X"],equal_nan=True):
       self.issue(key,"e4_treatment","generated_base_preservation","restored table does not retain the altered cohort unchanged as its first N rows")
   if np.isinf(z["X"]).any():self.issue(key,"e4_treatment","infinity","treatment X contains infinity")
  except Exception as e:self.issue(key,"e4_treatment","validation_error",e)
  return paths
 def e4_append_audit(self,t,bykey):
  # A generated restoration append is defined by one altered cohort and one
  # class-conditional generator artifact. It is not an e4_treatment alias.
  key=t["key"];out=self.task_art(t);p=out/"data.npz";mp=out/"metadata.json";paths=[p,mp]
  ck=t.get("cohort_key");gk=t.get("generated_key");deps=t.get("dependencies",[])
  if not p.is_file() or not mp.is_file():
   self.issue(key,"e4_append","artifact_missing",f"{p}; {mp}");return paths
  if not ck or not gk or deps!=[ck,gk]:
   self.issue(key,"e4_append","dependency_schema",f"expected ordered [cohort_key, generated_key]; fields=({ck},{gk}); dependencies={deps}")
  cohort=bykey.get(ck);generated=bykey.get(gk)
  if cohort is None or cohort.get("kind")!="e4_cohort":
   self.issue(key,"e4_append","cohort_dependency_invalid",ck)
  if generated is None or generated.get("kind")!="generate":
   self.issue(key,"e4_append","generated_dependency_invalid",gk)
  if cohort is None or generated is None:return paths
  if cohort.get("status")!="validated_terminal" or cohort.get("outcome")!="successful":
   self.issue(key,"e4_append","cohort_dependency_not_validated",f"status={cohort.get('status')}; outcome={cohort.get('outcome')}")
  if generated.get("status")!="validated_terminal" or generated.get("outcome")!="successful":
   self.issue(key,"e4_append","generator_dependency_not_validated",f"status={generated.get('status')}; outcome={generated.get('outcome')}")
  if t.get("rep")!=cohort.get("rep") or t.get("target_class")!=cohort.get("target_class") or t.get("ratio")!=cohort.get("ratio"):
   self.issue(key,"e4_append","cohort_task_identity",f"append rep/class/ratio={(t.get('rep'),t.get('target_class'),t.get('ratio'))}; cohort={(cohort.get('rep'),cohort.get('target_class'),cohort.get('ratio'))}")
  if generated.get("cohort_key")!=ck or generated.get("target_class")!=t.get("target_class") or generated.get("generator")!=t.get("generator") or generated.get("rep")!=t.get("rep"):
   self.issue(key,"e4_append","generator_task_identity",f"generated cohort/class/method/rep={(generated.get('cohort_key'),generated.get('target_class'),generated.get('generator'),generated.get('rep'))}")
  gd=[x for x in generated.get("dependencies",[]) if x in bykey and bykey[x].get("kind")=="fit"]
  gf=bykey.get(gd[0]) if len(gd)==1 else None
  if len(gd)!=1 or gf is None or gf.get("status")!="validated_terminal" or gf.get("outcome")!="successful" or gf.get("method")!=generated.get("generator") or gf.get("rep")!=generated.get("rep") or gf.get("train_key")!=ck:
   self.issue(key,"e4_append","generator_fit_dependency",f"fit_dependencies={gd}; fit_record={None if gf is None else {x:gf.get(x) for x in ('status','outcome','method','rep','train_key')}}")
  cp=self.task_art(cohort);gp=self.task_art(generated);cd=cp/"data.npz";cm=cp/"metadata.json";gdata=gp/"data.npz"
  paths.extend([cd,cm,gdata,self.rt/"cache/roles"/f"rep_{t.get('rep')}.npz",self.rt/"cache/test.npz",self.rt/"cache/development_X.npy",self.rt/"cache/development_y.npy",self.rt/"cache/development_ids.npy"])
  try:
   a=self.load_npz(p);b=self.load_npz(cd);g=self.load_npz(gdata);bm=json.loads(cm.read_text());am=json.loads(mp.read_text())
   required={"X","y","ids"}
   if required-set(a):self.issue(key,"e4_append","append_arrays_missing",str(required-set(a)))
   if required-set(b):self.issue(key,"e4_append","cohort_arrays_missing",str(required-set(b)))
   if {"X","y"}-set(g):self.issue(key,"e4_append","generator_arrays_missing",str({"X","y"}-set(g)))
   if required-set(a) or required-set(b) or {"X","y"}-set(g):return paths
   X=np.asarray(a["X"]);y=np.asarray(a["y"],dtype=np.int64);ids=np.asarray(a["ids"])
   Xb=np.asarray(b["X"]);yb=np.asarray(b["y"],dtype=np.int64);idsb=np.asarray(b["ids"])
   Xg=np.asarray(g["X"]);yg=np.asarray(g["y"],dtype=np.int64)
   c=_label_code(t.get("target_class",bm.get("target_class")));N=int(bm.get("N",len(yb)));ratio=float(t.get("ratio") or bm.get("ratio"))
   counts_before=np.bincount(yb,minlength=7);counts_after=np.bincount(y,minlength=7);gc=np.bincount(yg,minlength=7)
   orig=np.asarray(bm.get("source_fit_counts",[]),dtype=np.int64)
   if Xb.ndim!=2 or Xb.shape[1]!=6 or X.ndim!=2 or X.shape[1]!=6 or Xg.ndim!=2 or Xg.shape[1]!=6 or len(Xb)!=len(yb) or len(X)!=len(y) or len(Xg)!=len(yg):
    self.issue(key,"e4_append","array_shapes",f"cohort={Xb.shape}/{yb.shape}; generated={Xg.shape}/{yg.shape}; append={X.shape}/{y.shape}")
   if np.isinf(Xb).any() or np.isinf(X).any():self.issue(key,"e4_append","infinity","base cohort or append features contain infinity")
   if not np.isfinite(Xg).all():self.issue(key,"e4_append","generated_nonfinite","generated feature rows must be fully finite")
   if "sample_weight" in a:self.issue(key,"e4_append","append_sample_weight","generated append must not serialize sample_weight")
   if "ids" in g:self.issue(key,"e4_append","generated_ids_unexpected","class-conditional generator output must not carry real IDs")
   if not np.array_equal(y[:len(yb)],yb):self.issue(key,"e4_append","cohort_label_prefix","append does not preserve the altered cohort labels in order")
   if not np.array_equal(X[:len(Xb)],Xb,equal_nan=True):self.issue(key,"e4_append","cohort_feature_prefix","append does not preserve the altered cohort features in order")
   if len(y)!=len(yb)+len(yg):self.issue(key,"e4_append","append_length",f"append={len(y)} cohort={len(yb)} generated={len(yg)}")
   elif not np.array_equal(y[len(yb):],yg):self.issue(key,"e4_append","generated_label_suffix","append label suffix does not match generated labels in order")
   if len(X)==len(Xb)+len(Xg) and not np.array_equal(X[len(Xb):],Xg,equal_nan=True):self.issue(key,"e4_append","generated_feature_suffix","append feature suffix does not match generated rows in order")
   if len(yg)!=int(bm.get("restore_added_count",-1)) or len(yg)!=len(Xg) or np.any(yg!=c):
    self.issue(key,"e4_append","generated_target_count_or_class",f"rows={len(yg)} expected={bm.get('restore_added_count')}; target={c}; counts={gc.tolist()}")
   if np.any((yb<0)|(yb>6)) or np.any((yg<0)|(yg>6)) or np.any((y<0)|(y>6)):self.issue(key,"e4_append","labels_out_of_range","class outside 0..6")
   if len(orig)!=7 or np.any(orig<0) or int(orig.sum())!=N:
    self.issue(key,"e4_append","cohort_source_counts","source_fit_counts must have seven counts summing to cohort N")
   else:
    target_before=int(counts_before[c]);den=N-int(orig[c]);num=N*(int(orig[c])-target_before)
    expected_add=0 if num<=0 else (2*num+den)//(2*den) if den>0 else -1
    if int(bm.get("target_class",-1))!=c or int(bm.get("N",-1))!=N:self.issue(key,"e4_append","cohort_metadata_identity",f"target={bm.get('target_class')}; N={bm.get('N')}; expected target={c}, N={N}")
    if len(yb)!=N or not np.array_equal(counts_before,np.asarray(bm.get("realized_counts",[]),dtype=np.int64)):
     self.issue(key,"e4_append","cohort_metadata_histogram",f"actual={counts_before.tolist()}; N={N}; metadata={bm.get('realized_counts')}")
    if _typed_array_sha256(idsb)!=bm.get("ids_sha256"):self.issue(key,"e4_append","cohort_id_hash",f"metadata={bm.get('ids_sha256')}; actual={_typed_array_sha256(idsb)}")
    if target_before!=int(math.floor(ratio*int(orig[c])+0.5)):self.issue(key,"e4_append","cohort_target_quota",f"target_count={target_before}; source_count={int(orig[c])}; ratio={ratio}")
    if int(bm.get("restore_added_count",-1))!=int(expected_add):self.issue(key,"e4_append","restore_added_count_formula",f"metadata={bm.get('restore_added_count')}; formula={expected_add}")
   if len(idsb)!=len(yb) or len(ids)!=len(y):self.issue(key,"e4_append","id_shapes",f"cohort_ids={len(idsb)} cohort_rows={len(yb)} append_ids={len(ids)} append_rows={len(y)}")
   elif len(y)==len(yb)+len(yg):
    expected_syn=np.asarray([f"generated:{key}:{i}" for i in range(len(yg))])
    expected_ids=np.concatenate([idsb.astype(str),expected_syn])
    if not np.array_equal(ids.astype(str),expected_ids):self.issue(key,"e4_append","synthetic_id_construction","append IDs must preserve real cohort IDs and deterministic generated:<task-key>:<row-index> suffix")
    if len(np.unique(ids.astype(str)))!=len(ids):self.issue(key,"e4_append","append_id_uniqueness","append IDs are not unique")
    if set(ids.astype(str)[len(yb):].tolist()) & set(idsb.astype(str).tolist()):self.issue(key,"e4_append","synthetic_id_real_collision","synthetic IDs collide with real cohort identities")
   # Confirm cohort rows are development-source rows and never tune/calibration/test rows.
   rolep,role=self.role(t["rep"]);fit_ids=np.asarray(role["fit_ids"]);tune_ids=np.asarray(role["tuning_ids"]);cal_ids=np.asarray(role["calibration_ids"])
   source_fit_counts=np.bincount(np.asarray(role["y_fit"],dtype=np.int64),minlength=7)
   if len(orig)==7 and not np.array_equal(source_fit_counts,orig):self.issue(key,"e4_append","source_fit_counts_vs_role",f"cohort metadata={orig.tolist()}; role={source_fit_counts.tolist()}")
   testids=np.asarray(self.load_npz(self.rt/"cache/test.npz",["ids"])["ids"])
   if len(np.unique(idsb))!=len(idsb) or (len(idsb)>1 and np.any(idsb[1:]<idsb[:-1])):self.issue(key,"e4_append","cohort_id_order_or_duplicates","cohort source IDs must be unique and sorted")
   if np.isin(idsb,np.concatenate([tune_ids,cal_ids,testids])).any():self.issue(key,"e4_append","cohort_reserved_id_overlap","cohort includes tuning, calibration, or test IDs")
   if np.isin(idsb,testids).any():self.issue(key,"e4_append","cohort_test_id_overlap","cohort includes test IDs")
   # Verify each cohort ID maps to the exact saved development X/y row.
   devx=np.load(self.rt/"cache/development_X.npy",mmap_mode="r",allow_pickle=False);devy=np.load(self.rt/"cache/development_y.npy",mmap_mode="r",allow_pickle=False);devi=np.load(self.rt/"cache/development_ids.npy",mmap_mode="r",allow_pickle=False)
   if len(devi)<1 or (len(devi)>1 and np.any(devi[1:]<devi[:-1])):self.issue(key,"e4_append","development_id_index","development IDs must be sorted for source membership lookup")
   else:
    positions=np.searchsorted(devi,idsb);exists=(positions<len(devi))
    exists[exists]&=devi[positions[exists]]==idsb[exists]
    if not np.all(exists):self.issue(key,"e4_append","cohort_id_not_in_development",f"missing={int((~exists).sum())}")
    else:
     if not np.array_equal(devy[positions].astype(np.int64),yb):self.issue(key,"e4_append","cohort_source_labels","cohort labels differ from the corresponding development rows")
     if not np.array_equal(devx[positions],Xb,equal_nan=True):self.issue(key,"e4_append","cohort_source_features","cohort features differ from the corresponding development rows")
   # Ensure exact restored histogram; compare to ROS/SMOTE only when their independent outputs are validated.
   expected=counts_before.copy();expected[c]+=int(bm.get("restore_added_count",0))
   if not np.array_equal(counts_after,expected):self.issue(key,"e4_append","final_histogram",f"append={counts_after.tolist()}; cohort+target append={expected.tolist()}")
   if am.get("kind")!="e4_append" or am.get("task_key")!=key or int(am.get("target_class",-1))!=c or int(am.get("added_count",-1))!=len(yg):
    self.issue(key,"e4_append","append_metadata_identity",f"metadata kind/key/target/add={(am.get('kind'),am.get('task_key'),am.get('target_class'),am.get('added_count'))}")
   if not np.array_equal(np.asarray(am.get("counts_before",[]),dtype=np.int64),counts_before):self.issue(key,"e4_append","append_metadata_counts_before",f"metadata={am.get('counts_before')}; actual={counts_before.tolist()}")
   if not np.array_equal(np.asarray(am.get("counts_after",[]),dtype=np.int64),counts_after):self.issue(key,"e4_append","append_metadata_counts_after",f"metadata={am.get('counts_after')}; actual={counts_after.tolist()}")
   gresult=generated.get("result",{}).get("result",{})
   if gresult.get("n_rows") is not None and int(gresult["n_rows"])!=len(yg):self.issue(key,"e4_append","generator_result_rows",f"result={gresult.get('n_rows')}; data={len(yg)}")
   if gresult.get("class_counts") is not None and not np.array_equal(np.asarray(gresult["class_counts"],dtype=np.int64),gc):self.issue(key,"e4_append","generator_result_counts",f"result={gresult.get('class_counts')}; data={gc.tolist()}")
   # Compare final class histogram with independently materialized ROS and SMOTE arms when available.
   treatments=[x for x in bykey.values() if x.get("kind")=="e4_treatment" and x.get("cohort_key")==ck and x.get("treatment") in {"ros","smote"}]
   for treatment in ("ros","smote"):
    matching=[x for x in treatments if x.get("treatment")==treatment]
    if len(matching)!=1:self.issue(key,"e4_append","restoration_treatment_plan",f"expected one {treatment} task for {ck}; found={len(matching)}");continue
    tr=matching[0]
    if tr.get("status")=="validated_terminal" and tr.get("outcome")=="successful":
     tp=self.task_art(tr)/"data.npz";paths.append(tp)
     if not tp.is_file():self.issue(key,"e4_append","restoration_treatment_artifact_missing",tp);continue
     tz=self.load_npz(tp,["y"]);tcounts=np.bincount(np.asarray(tz["y"],dtype=np.int64),minlength=7)
     if not np.array_equal(tcounts,counts_after):self.issue(key,"e4_append","restoration_treatment_histogram",f"{treatment}={tcounts.tolist()}; append={counts_after.tolist()}")
   # Bind each input/output payload to its terminal artifact validation record.
   for rec,artifact,name,artifact_kind in ((cohort,cd,"cohort", "cohort"),(generated,gdata,"generator","generate"),(t,p,"append","append")):
    observed=self.file_hash(artifact);recorded=rec.get("result",{}).get("validation",{}).get("files",{}).get("data.npz")
    if recorded!=observed:self.issue(key,"e4_append",name+"_artifact_hash",f"registry validation={recorded}; actual={observed}")
   gresult=generated.get("result",{}).get("result",{})
   if gresult.get("data_sha256") and self.file_hash(gdata)!=gresult.get("data_sha256"):self.issue(key,"e4_append","generator_result_hash",f"result={gresult.get('data_sha256')}; actual={self.file_hash(gdata)}")
  except Exception as e:self.issue(key,"e4_append","validation_error",e)
  return paths
 def e5_audit(self,t,bykey):
  key=t["key"];out=self.task_art(t);p=out/"data.npz";ap=out/"audit.npz";paths=[p,ap]
  if not p.exists() or not ap.exists():self.issue(key,"e5_corruption","artifact_missing",f"{p}; {ap}");return paths
  try:
   rolep,role=self.role(t["rep"]);paths.append(rolep);raw=np.asarray(role["X_fit"],float);y0=np.asarray(role["y_fit"],int);ids=role["fit_ids"]
   z=self.load_npz(p);a=self.load_npz(ap);X=np.asarray(z["X"],float);y=np.asarray(z["y"],int)
   if np.isinf(X).any():self.issue(key,"e5_corruption","infinity","corrupted X contains infinity")
   if not np.array_equal(z.get("ids"),ids):self.issue(key,"e5_corruption","fit_ids","corruption changed fitting row identities")
   rows=np.asarray(a["affected_row_indices"],int);n=len(y0);want=int(math.floor(float(t["rate"])*n+.5))
   if len(rows)!=want:self.issue(key,"e5_corruption","mask_count",f"n={len(rows)} expected={want}")
   if not np.array_equal(np.sort(rows),np.sort(np.unique(rows))):self.issue(key,"e5_corruption","mask_duplicate_rows","affected rows are duplicated")
   if not np.array_equal(a.get("affected_ids"),ids[rows]):self.issue(key,"e5_corruption","audit_ids","audit IDs differ from fitting rows")
   expected_mask=np.zeros(n,dtype=bool);expected_mask[rows]=True
   if "affected_mask" in a and not np.array_equal(a["affected_mask"],expected_mask):self.issue(key,"e5_corruption","audit_mask","stored mask disagrees with affected row indices")
   mech=t["mechanism"]
   if mech=="label_noise":
    changed=np.flatnonzero(y!=y0)
    if set(changed.tolist())!=set(rows.tolist()) or not np.array_equal(X,raw,equal_nan=True):self.issue(key,"e5_corruption","label_noise_exact_changes",f"changed labels={len(changed)} mask={len(rows)}")
    if len(a.get("new_label",[]))!=want or np.any(a["new_label"]==a["old_label"]) or not np.array_equal(y[rows],a.get("new_label")) or not np.array_equal(y0[rows],a.get("old_label")):self.issue(key,"e5_corruption","label_noise_changes","selected labels not exactly recorded as changed")
   elif mech=="feature_noise":
    changed=np.argwhere(~np.isclose(X,raw,rtol=0,atol=0,equal_nan=True))
    feat=np.asarray(a["feature_index"],int)
    if len(feat)!=want or len(a.get("perturbation",[]))!=want:self.issue(key,"e5_corruption","feature_noise_audit_rows","audit length mismatch")
    expected={(int(r),int(f)) for r,f in zip(rows,feat)}
    if set(map(tuple,changed.tolist()))!=expected:self.issue(key,"e5_corruption","feature_noise_exact_cells",f"changed={len(changed)} expected={len(expected)}")
    if len(feat)==want and len(a.get("perturbation",[]))==want:
     expected_vals=np.asarray([raw[r,f]+delta for r,f,delta in zip(rows,feat,a["perturbation"])])
     actual_vals=X[rows,feat]
     if not np.allclose(actual_vals,expected_vals,rtol=0,atol=1e-12,equal_nan=True):self.issue(key,"e5_corruption","feature_noise_values","stored perturbations do not reconstruct altered cells")
    if not np.array_equal(y,y0):self.issue(key,"e5_corruption","feature_noise_labels","labels changed")
   elif mech=="missingness":
    new_missing=np.argwhere(np.isnan(X)&~np.isnan(raw)); same=(X==raw)|(np.isnan(X)&np.isnan(raw)); unexpected=np.argwhere(~same&~(np.isnan(X)&~np.isnan(raw)))
    feat=np.asarray(a["feature_index"],int);expected={(int(r),int(f)) for r,f in zip(rows,feat)}
    if set(map(tuple,new_missing.tolist()))!=expected or len(unexpected):self.issue(key,"e5_corruption","missingness_exact_cells",f"new_missing={len(new_missing)} expected={len(expected)} other_changes={len(unexpected)}")
    if not np.array_equal(y,y0):self.issue(key,"e5_corruption","missingness_labels","labels changed")
   else:self.issue(key,"e5_corruption","unknown_mechanism",mech)
  except Exception as e:self.issue(key,"e5_corruption","validation_error",e)
  return paths
 def _metrics_doc(self,o):
  if not isinstance(o,dict):return {}
  if isinstance(o.get("evaluation"),dict):return o["evaluation"]
  if isinstance(o.get("result"),dict):return o["result"].get("evaluation",o["result"])
  return o
 def _metric_equal(self,a,b,k):
  if k not in a or k not in b:return False
  if k=="confusion_matrix":return np.array_equal(np.asarray(a[k]),np.asarray(b[k]))
  if k in {"balanced_accuracy","set_size","coverage","threshold","conformal_threshold"}:
   try:return bool(np.isclose(float(a[k]),float(b[k]),rtol=0,atol=1e-10))
   except Exception:return False
  return a[k]==b[k]
 def _eval_metrics(self,key,m,reg,y,pred,bits,cov,size,ncal):
  n=len(y);cf=np.bincount(y.astype(int)*7+pred.astype(int),minlength=49).reshape(7,7)
  d=cf.sum(1);rec=np.divide(np.diag(cf),d,out=np.zeros(7,float),where=d>0)
  vals={"confusion_matrix":cf,"balanced_accuracy":float(rec.mean()),"coverage":float(cov.mean()),"set_size":float(size.mean()),"test_n":n,"calibration_n":ncal}
  for k,v in vals.items():
   g=m.get(k)
   if k=="confusion_matrix":ok=np.array_equal(np.asarray(g),v)
   elif k in ("test_n","calibration_n"):ok=g is not None and int(g)==v
   else:
    try:ok=bool(np.isclose(float(g),v,rtol=0,atol=1e-10))
    except Exception:ok=False
   if not ok:self.issue(key,"eval",k,f"stored={g}; recomputed={v.tolist() if isinstance(v,np.ndarray) else v}")
  pc=m.get("per_class")
  if not isinstance(pc,dict) or any(str(c) not in pc and c not in pc for c in range(7)):self.issue(key,"eval","per_class_schema",f"keys={list(pc) if isinstance(pc,dict) else type(pc).__name__}")
  else:
   for c in range(7):
    ix=y==c;e=pc.get(str(c),pc.get(c,{}));cnt=int(ix.sum())
    vals={"n":cnt,"recall":float(np.mean(pred[ix]==c)) if cnt else None,"coverage":float(np.mean(cov[ix])) if cnt else None,"set_size":float(np.mean(size[ix])) if cnt else None}
    for k,v in vals.items():
     g=e.get(k)
     try:ok=(g is None if v is None else int(g)==v if k=="n" else bool(np.isclose(float(g),v,rtol=0,atol=1e-10)))
     except Exception:ok=False
     if not ok:self.issue(key,"eval",f"class_{c}_{k}",f"stored={g}; actual={v}")
  for k in ("balanced_accuracy","coverage","set_size","confusion_matrix","per_class","calibration_n","test_n","threshold","conformal_threshold","score_kind"):
   if reg is not None and (k in m or k in reg) and not self._metric_equal(m,reg,k):self.issue(key,"eval",f"registry_{k}",f"evaluation={m.get(k)}; registry={reg.get(k)}")
 def _safe_archive_member(self,value):
  if not isinstance(value,str) or not value or "\\" in value:raise ValueError("invalid archive member path")
  raw=Path(value)
  if raw.is_absolute() or any(part in {"",".",".."} for part in raw.parts) or (raw.parts and ":" in raw.parts[0]):raise ValueError("unsafe archive member path")
  archive_root=self.rt.parent.resolve();candidate=(archive_root/raw).resolve(strict=False)
  try:candidate.relative_to(archive_root)
  except ValueError:raise ValueError("archive member escapes extraction root")
  return candidate
 def _archive_manifest_binds(self,path,payload_sha):
  archive_root=self.rt.parent.resolve();manifest_path=archive_root/"archive_member_manifest.json"
  if not manifest_path.is_file():return False,"archive member manifest missing"
  try:
   doc=json.loads(manifest_path.read_text());rel=Path(path).resolve().relative_to(archive_root).as_posix()
   if doc.get("schema_version")!="lamost-member-manifest/1":return False,"archive member manifest schema mismatch"
   rows=[x for x in doc.get("unique_physical_members",[]) if x.get("path")==rel]
   if len(rows)!=1:return False,"curated provenance member not uniquely listed in archive member manifest"
   row=rows[0]
   if row.get("sha256")!=payload_sha or int(row.get("bytes",-1))!=Path(path).stat().st_size:return False,"curated provenance payload SHA/size differs from archive member manifest"
   return True,None
  except Exception as e:return False,f"archive member manifest invalid: {e}"
 def _load_restoration_manifest(self):
  path=self.rt/RESTORATION_MANIFEST_REL;actual=self.file_hash(path,force=True);self.restoration_manifest_sha256=actual
  if not path.exists():return {},False,"manifest missing"
  try:doc=json.loads(path.read_text())
  except Exception as e:return {},False,f"manifest JSON invalid: {e}"
  curated=doc.get("schema_version")=="lamost-e3-npz-restoration-provenance/curated-1"
  if not curated:
   # Preserve the live raw-manifest SHA gate exactly.
   if actual!=RESTORATION_MANIFEST_SHA256:return {},False,f"manifest SHA mismatch expected={RESTORATION_MANIFEST_SHA256} actual={actual}"
   self.restoration_manifest_source_sha256=actual
   entries=doc.get("files",[]);bykey={x.get("task_key"):x for x in entries if x.get("task_key")}
   allowed={f"e3/rep_{r}/eval/direct/{m}" for r in (1,2,3) for m in ("chow_liu","copula","gmm")};errors=[]
   if doc.get("scope")!="nine direct generative route NPZ containers only" or len(entries)!=9 or set(bykey)!=allowed:errors.append("manifest scope/task coverage mismatch")
   for k in ("fit_predict_calibrate_generate_performed","models_loaded","live_artifacts_modified"):
    if doc.get(k) is not False:errors.append(f"manifest {k} must be false")
   return bykey,not errors,"; ".join(errors) if errors else None
  source_sha=doc.get("source_manifest_sha256");self.restoration_manifest_source_sha256=source_sha
  if source_sha!=RESTORATION_MANIFEST_SHA256:return {},False,f"curated manifest source SHA mismatch expected={RESTORATION_MANIFEST_SHA256} actual={source_sha}"
  bound,why=self._archive_manifest_binds(path,actual)
  if not bound:return {},False,why
  entries=doc.get("files",[]);allowed={f"e3/rep_{r}/eval/direct/{m}" for r in (1,2,3) for m in ("chow_liu","copula","gmm")};bykey={x.get("task_key"):x for x in entries if x.get("task_key")};errors=[]
  if doc.get("experiment")!="E3" or doc.get("scope")!="nine direct generative route NPZ containers only" or len(entries)!=9 or set(bykey)!=allowed:errors.append("curated manifest scope/task coverage mismatch")
  for k in ("fit_predict_calibrate_generate_performed","models_loaded","live_artifacts_modified"):
   if doc.get(k) is not False:errors.append(f"curated manifest {k} must be false")
  if errors:return {},False,"; ".join(errors)
  normalized={}
  for key,item in bykey.items():
   try:
    if item.get("classification")!="byte-exact original container available for isolated publication; live artifact unchanged":raise ValueError("unexpected curated restoration classification")
    current=self._safe_archive_member(item.get("current_member"));restored=self._safe_archive_member(item.get("restored_member"));candidate=self._safe_archive_member(item.get("source_candidate_member"));support=self._safe_archive_member(item.get("support_baseline_member"))
    task_art=(self.rt/"artifacts"/Path(*key.split("/"))).resolve()
    expected_current=task_art/"test_outcomes.npz";expected_candidate=task_art/"diagnostic_baseline"/"test_outcomes_before_support_diagnostics.npz";expected_support=task_art/"support_diagnostic_baseline.json"
    expected_restored=(self.rt/"artifacts"/"_restored_original_e3_containers"/Path(*key.split("/"))).resolve()/"test_outcomes.original.npz"
    if current!=expected_current.resolve() or candidate!=expected_candidate.resolve() or support!=expected_support.resolve() or restored!=expected_restored.resolve():raise ValueError("curated archive member does not map to canonical E3 artifact path")
    for field in ("current_sha256","restored_sha256","source_candidate_sha256","support_baseline_sha256"):
     value=item.get(field)
     if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):raise ValueError(f"invalid curated {field}")
    av=item.get("array_validation")
    if not isinstance(av,dict):raise ValueError("curated array validation missing")
    normalized[key]={"task_key":key,"current_path":str(current),"current_sha256":item["current_sha256"],"restored_path":str(restored),"restored_sha256":item["restored_sha256"],"old_expected_sha256":item["restored_sha256"],"initial_worker_result_artifact_sha256":item["restored_sha256"],"source_candidate_path":str(candidate),"source_candidate_sha256":item["source_candidate_sha256"],"support_diagnostic_baseline_path":str(support),"support_diagnostic_baseline_sha256":item["support_baseline_sha256"],"array_validation":av,"classification":item["classification"],"_curated_source_manifest_sha256":source_sha,"_curated_payload_sha256":actual}
   except Exception as e:errors.append(f"{key}: {e}")
  return normalized,not errors,"; ".join(errors) if errors else None

 def _verify_restoration_entry(self,t,item,current_eval,manifest_sha,manifest_valid):
  key=t["key"];err=[];out=self.task_art(t);cur=out/"test_outcomes.npz"
  def bad(x):err.append(str(x))
  curated=bool(item.get("_curated_source_manifest_sha256"))
  if not manifest_valid:bad(f"untrusted restoration manifest: {manifest_sha}")
  if item.get("task_key")!=key or Path(item.get("current_path","")).resolve()!=cur.resolve():bad("task/current path mismatch")
  old=Path(item.get("restored_path",""));cand=Path(item.get("source_candidate_path",""));sup=Path(item.get("support_diagnostic_baseline_path",""))
  ir=Path(item.get("initial_worker_result_path",""));iq=Path(item.get("initial_request_path",""))
  paths=[cur,old,cand,sup] if curated else [cur,old,cand,sup,ir,iq]; hs={str(p):self.file_hash(p,force=True) for p in paths}
  cs=hs[str(cur)];oh=item.get("old_expected_sha256")
  if cs!=item.get("current_sha256"):bad("current NPZ SHA differs from manifest")
  if hs[str(old)]!=item.get("restored_sha256") or hs[str(old)]!=oh or oh!=item.get("initial_worker_result_artifact_sha256"):bad("restored/initial expected SHA chain mismatch")
  if hs[str(cand)]!=item.get("source_candidate_sha256") or hs[str(cand)]!=oh:bad("diagnostic baseline candidate SHA mismatch")
  if hs[str(sup)]!=item.get("support_diagnostic_baseline_sha256"):bad("support diagnostic JSON SHA mismatch")
  if curated:
   if item.get("_curated_source_manifest_sha256")!=RESTORATION_MANIFEST_SHA256:bad("curated source-manifest pin mismatch")
   if item.get("_curated_payload_sha256")!=manifest_sha:bad("curated payload SHA mismatch")
   try:
    sj=json.loads(sup.read_text())
    if sj.get("outcomes_sha256")!=oh:bad("support baseline outcome SHA mismatch")
    source_path=self.resolve_recorded_path(sj.get("outcomes_path"))
    if source_path.resolve()!=cand.resolve():bad("support baseline source reference mismatch")
   except Exception as e:bad(f"curated support baseline JSON invalid: {e}")
  else:
   if hs[str(ir)]!=item.get("initial_worker_result_file_sha256") or hs[str(iq)]!=item.get("initial_request_file_sha256"):bad("initial worker/request receipt SHA mismatch")
   att=next((a for a in t.get("attempts",[]) if a.get("attempt_id")==item.get("initial_attempt_id")),None)
   if not att or Path(att.get("result_path","")).resolve()!=ir.resolve() or Path(att.get("request_path","")).resolve()!=iq.resolve():bad("initial receipt paths/attempt ID differ from registry")
   try:
    iw=json.loads(ir.read_text());req=json.loads(iq.read_text());sj=json.loads(sup.read_text())
    if iw.get("artifact_sha256")!=oh or iw.get("controller_attempt_id")!=item.get("initial_attempt_id") or iw.get("key")!=key:bad("initial worker receipt content mismatch")
    rq=req.get("task",req)
    if rq.get("key",rq.get("task_key"))!=key:bad("initial request task mismatch")
    if sj.get("outcomes_sha256")!=oh or Path(sj.get("outcomes_path","")).resolve()!=cand.resolve():bad("support baseline source reference mismatch")
    om=self._metrics_doc(iw)
    for k in ("balanced_accuracy","coverage","set_size","confusion_matrix","per_class","test_n","calibration_n","threshold","score_kind"):
     if k not in om or k not in current_eval or not self._metric_equal({"v":om.get(k)},{"v":current_eval.get(k)},"v"):bad(f"initial/current metric mismatch: {k}")
   except Exception as e:bad(f"initial receipt JSON invalid: {e}")
  latest=Path(t.get("result_path","")) if t.get("result_path") else None
  if not curated and (not latest or not latest.exists()):bad("latest worker receipt missing")
  elif not curated:
   paths.append(latest);self.file_hash(latest,force=True)
   try:
    lw=json.loads(latest.read_text())
    if lw.get("artifact_sha256")!=cs or lw.get("key")!=key or t.get("result",{}).get("artifact_sha256")!=cs:bad("latest worker/registry artifact SHA mismatch")
   except Exception as e:bad(f"latest worker receipt invalid: {e}")
  val=out/"validation.json";paths.append(val);self.file_hash(val,force=True)
  try:
   vf=json.loads(val.read_text()).get("files",{})
   if vf.get("test_outcomes.npz")!=cs:bad("current validation receipt SHA mismatch")
  except Exception as e:bad(f"current validation receipt invalid: {e}")
  try:
   with zipfile.ZipFile(old) as z:
    if z.testzip() is not None:bad("restored NPZ CRC invalid")
   with zipfile.ZipFile(cur) as z:
    if z.testzip() is not None:bad("current NPZ CRC invalid")
   with np.load(old,allow_pickle=False) as a,np.load(cur,allow_pickle=False) as b:
    oldnames=list(a.files);newnames=list(b.files);expected=["sample_id","y_pred","set_mask","covered","set_size"]
    av=item.get("array_validation",{})
    if oldnames!=expected or newnames!=expected+["fallback_mask"]:bad("unexpected NPZ member names/order")
    if av.get("original_members")!=oldnames or av.get("current_members")!=newnames or av.get("fallback_mask_omitted_only") is not True:bad("manifest member evidence mismatch")
    if oldnames==expected and newnames==expected+["fallback_mask"]:
     for n in expected:
      x=a[n];y=b[n];cl=next((z for z in av.get("arrays",[]) if z.get("name")==n),{})
      if x.dtype!=y.dtype or x.shape!=y.shape or not np.array_equal(x,y):bad(f"core array mismatch: {n}")
      if cl.get("dtype")!=str(x.dtype) or cl.get("shape")!=list(x.shape) or cl.get("values_exact") is not True:bad(f"manifest array claim mismatch: {n}")
     fb=b["fallback_mask"]
     if fb.dtype!=np.dtype(bool) or fb.shape!=(len(b["sample_id"]),) or av.get("fallback_mask_shape")!=list(fb.shape):bad("added fallback mask shape/dtype mismatch")
     if av.get("fallback_true_count")!=int(np.count_nonzero(fb)):bad("added fallback mask true-count mismatch")
    if av.get("old_zip_crc")!="ok" or av.get("current_zip_crc")!="ok" or av.get("member_order_preserved") is not True:bad("manifest CRC/order flags mismatch")
  except Exception as e:bad(f"NPZ comparison/CRC error: {e}")
  info={"task_key":key,"initial_attempt_id":item.get("initial_attempt_id"),"initial_worker_result_artifact_sha256":oh,"current_artifact_sha256":cs,
   "restored_original_sha256":hs[str(old)],"source_candidate_sha256":hs[str(cand)],"support_diagnostic_baseline_sha256":hs[str(sup)],
   "initial_worker_result_file_sha256":None if curated else hs[str(ir)],"restoration_manifest_sha256":manifest_sha,"restoration_manifest_source_sha256":item.get("_curated_source_manifest_sha256",manifest_sha),"restoration_manifest_payload_sha256":item.get("_curated_payload_sha256",manifest_sha),"provenance_mode":"curated_archive" if curated else "raw_live","curated_receipts_omitted":curated,"restored_path":str(old),
   "source_candidate_path":str(cand),"support_diagnostic_baseline_path":str(sup),"disposition":"validated_supersession_only_fallback_mask_added","errors":err}
  return not err,info,paths

 def _eval_hashes(self,t,out,files,paths,alias=False,validated_original_container_sha=None):
  key=t["key"];kind="alias" if alias else "eval";expected=t.get("result",{}).get("validation",{}).get("files",{});vp=out/"validation.json";paths.append(vp);cur={}
  if vp.exists():
   try:cur=json.loads(vp.read_text()).get("files",{})
   except Exception as e:self.issue(key,kind,"validation_json_read",e)
  else:self.issue(key,kind,"validation_json_missing",vp)
  if not expected:self.issue(key,kind,"initial_hashes_missing","registry result.validation.files is empty")
  for nm,p in files.items():
   paths.append(p);h=self.file_hash(p);old=expected.get(nm);v=cur.get(nm)
   if old is None:self.issue(key,kind,"initial_hash_missing",nm)
   elif old!=h and not (nm=="test_outcomes.npz" and validated_original_container_sha==old):self.issue(key,kind,"initial_hash_mismatch",f"{nm}: recorded={old}; current={h}")
   if v is None:self.issue(key,kind,"validation_hash_missing",nm)
   elif v!=h:self.issue(key,kind,"validation_hash_mismatch",f"{nm}: validation={v}; current={h}")
  return paths
 def _svm_alias_score_audit(self,t,out,source_out,m,paths):
  """Validate copied SVM alias evidence and its local calibration identity."""
  key=t["key"];files={"evaluation.json":out/"evaluation.json"}
  checks={"test_outcomes.npz":("source_test_outcomes_npz_sha256","alias_test_outcomes_npz_sha256"),"calibration.json":("source_calibration_json_sha256","alias_calibration_json_sha256")}
  ref_path=out/"artifact_ref.json";paths.append(ref_path)
  try:ref=json.loads(ref_path.read_text())
  except Exception as e:
   self.issue(key,"alias","artifact_ref_read",e);ref={}
  if ref.get("source_key")!=t.get("source_key"):
   self.issue(key,"alias","artifact_ref_source_key",f"expected={t.get('source_key')}; got={ref.get('source_key')}")
  for name,(source_field,alias_field) in checks.items():
   dst=out/name;src=source_out/name;paths.extend([dst,src]);files[name]=dst
   if not dst.is_file() or not src.is_file():
    self.issue(key,"alias","svm_alias_artifact_missing",name);continue
   sh=self.file_hash(src);dh=self.file_hash(dst)
   if sh!=dh:self.issue(key,"alias","svm_alias_copy_mismatch",f"{name}: source={sh}; alias={dh}")
   if ref.get(source_field)!=sh:self.issue(key,"alias","artifact_ref_source_hash",f"{name}: recorded={ref.get(source_field)}; actual={sh}")
   if ref.get(alias_field)!=dh:self.issue(key,"alias","artifact_ref_alias_hash",f"{name}: recorded={ref.get(alias_field)}; actual={dh}")
  op=out/"test_outcomes.npz";cp=out/"calibration.json"
  if op.is_file() and cp.is_file():
   try:
    cm=json.loads(cp.read_text());z=self.load_npz(op,["sample_id","y_pred","set_mask","covered","set_size","scores","score_kind","score_class_order","threshold","prediction_rule","nonconformity_rule"])
    _,role=self.role(t["rep"],["y_cal"]);y=np.asarray(self.load_npz(self.rt/"cache/test.npz",["y"])["y"],dtype=int)
    pred=np.asarray(z["y_pred"],dtype=int);mask=np.asarray(z["set_mask"],dtype=np.uint8).reshape(-1);bits=((mask[:,None]>>np.arange(7,dtype=np.uint8))&1).astype(bool)
    cov=np.asarray(z["covered"],dtype=bool);size=np.asarray(z["set_size"],dtype=int)
    for check,evidence in _score_contract_checks(m,z,y,pred,bits,cov,size,len(role["y_cal"]),cm,True,m.get("fit_key")):
     self.issue(key,"alias",check,evidence)
   except Exception as e:self.issue(key,"alias","svm_alias_score_read",e)
  return files
 def evaluation_audit(self,t,bykey,validset,alias=False,restoration=None,restoration_manifest_sha=None,restoration_manifest_valid=False):
  issue_start=len(self.issues)
  key=t["key"];kind="alias" if alias else "eval";out=self.task_art(t);ep=out/"evaluation.json";paths=[ep]
  if not ep.exists():self.issue(key,kind,"evaluation_json_missing",ep);return paths,{"task_key":key,"kind":kind,"physical_outcome":not alias,"status":"invalid"}
  try:m=json.loads(ep.read_text())
  except Exception as e:self.issue(key,kind,"evaluation_json_read",e);return paths,{"task_key":key,"kind":kind,"physical_outcome":not alias,"status":"invalid"}
  if alias:
   sk=t.get("source_key");src=bykey.get(sk)
   if not src or sk not in validset or src.get("kind") not in {"eval","ensemble","alias"}:self.issue(key,kind,"source_unavailable",sk)
   else:
    sep=self.task_art(src)/"evaluation.json";paths.append(sep)
    if not sep.exists():self.issue(key,kind,"source_evaluation_missing",sep)
    else:
     sm=json.loads(sep.read_text());drop={"task_key","experiment","repetition","compute_reused","reused_from"}
     if {k:v for k,v in m.items() if k not in drop}!={k:v for k,v in sm.items() if k not in drop}:self.issue(key,kind,"alias_metrics_mismatch",f"alias differs from {sk}")
     ref=out/"artifact_ref.json";paths.append(ref)
     if not ref.exists():self.issue(key,kind,"artifact_ref_missing",ref)
     else:
      rr=json.loads(ref.read_text())
      if rr.get("source_key")!=sk or rr.get("source_evaluation_sha256")!=self.file_hash(sep):self.issue(key,kind,"artifact_ref_mismatch",str(rr))
     method=str(t.get("method") or "")
     svm_alias=int(t.get("experiment") or 0)>=4 and method in {"linear_svm","rbf_svm"}
     alias_files={"evaluation.json":ep}
     if svm_alias:alias_files=self._svm_alias_score_audit(t,out,self.task_art(src),m,paths)
    physical=src;seen={key}
    while physical and physical.get("kind")=="alias":
     nxt=physical.get("source_key")
     if nxt in seen:self.issue(key,kind,"alias_cycle",nxt);physical=None;break
     seen.add(nxt);physical=bykey.get(nxt)
    if physical and physical.get("kind") in {"eval","ensemble"}:
     paths.append(self.task_art(physical)/"test_outcomes.npz")
     self._eval_hashes(t,out,alias_files,paths,True)
     return paths,{"task_key":key,"kind":"alias","physical_outcome":False,"canonical_source_key":physical["key"],"status":"resolved"}
   self._eval_hashes(t,out,locals().get("alias_files",{"evaluation.json":ep}),paths,True)
   return paths,{"task_key":key,"kind":"alias","physical_outcome":False,"canonical_source_key":sk,"status":"checked"}
  op=out/"test_outcomes.npz";tp=self.rt/"cache/test.npz";cmp=self.rt/"cache/cache_manifest.json";paths += [op,tp,cmp]
  cm=json.loads(cmp.read_text());want=cm.get("cache_files",{}).get("test.npz");actual=self.file_hash(tp)
  if want and actual!=want:self.issue(key,kind,"fixed_test_hash",f"manifest={want}; current={actual}")
  test=self.load_npz(tp,["ids","y"]);ids=np.asarray(test["ids"]);y=np.asarray(test["y"],int)
  if list(cm.get("labels",LABELS))!=list(LABELS):self.issue(key,kind,"class_order",str(cm.get("labels")))
  if "class_order" in m and list(m["class_order"]) not in (list(range(7)),list(LABELS)):self.issue(key,kind,"class_order",str(m["class_order"]))
  rp,role=self.role(t["rep"],["y_cal","fit_ids","calibration_ids"]);paths.append(rp);ncal=len(role["y_cal"])
  z=self.load_npz(op,["sample_id","y_pred","set_mask","covered","set_size","fallback_mask","scores","score_kind","score_class_order","threshold","prediction_rule","nonconformity_rule"]);required={"sample_id","y_pred","set_mask","covered","set_size"}
  if required-set(z):self.issue(key,kind,"outcome_arrays_missing",str(required-set(z)));return paths,{"task_key":key,"kind":t["kind"],"physical_outcome":True,"status":"invalid"}
  sid=np.asarray(z["sample_id"]);pred=np.asarray(z["y_pred"],int);mask=np.asarray(z["set_mask"],np.uint8).reshape(-1);cov=np.asarray(z["covered"],bool);size=np.asarray(z["set_size"],int);n=len(y)
  if not np.array_equal(sid,ids):self.issue(key,kind,"test_id_order",f"exact={np.array_equal(sid,ids)}")
  if any(a.shape!=(n,) for a in (sid,pred,mask,cov,size)):self.issue(key,kind,"outcome_shapes",str([sid.shape,pred.shape,mask.shape,cov.shape,size.shape]))
  if np.any((pred<0)|(pred>6)) or np.any((y<0)|(y>6)):self.issue(key,kind,"labels_out_of_order","class outside 0..6")
  if np.any(mask&np.uint8(128)):self.issue(key,kind,"mask_high_bit","bit 7 outside seven classes is set")
  bits=((mask[:,None]>>np.arange(7,dtype=np.uint8))&1).astype(bool)
  if not np.array_equal(size,bits.sum(1)):self.issue(key,kind,"mask_size","saved sizes differ from bitmask")
  if not np.array_equal(cov,bits[np.arange(n),y]):self.issue(key,kind,"mask_coverage","covered differs from true-label bit")
  calibration_doc=None;calibration_path=out/"calibration.json"
  if calibration_path.is_file():
   paths.append(calibration_path)
   try:calibration_doc=json.loads(calibration_path.read_text())
   except Exception as e:self.issue(key,kind,"calibration_json_read",e)
  try:require_scores=int(t.get("experiment") or 0)>=4 and str(t.get("method") or "") in {"linear_svm","rbf_svm"}
  except Exception:require_scores=False
  for check,evidence in _score_contract_checks(m,z,y,pred,bits,cov,size,ncal,calibration_doc,require_scores,t.get("fit_key")):
   self.issue(key,kind,check,evidence)
  fb=z.get("fallback_mask")
  fallback_missing = t.get("kind")=="eval" and fb is None
  if fb is not None:
   fb=np.asarray(fb,bool)
   if fb.shape!=(n,):self.issue(key,kind,"fallback_shape",str(fb.shape))
   elif "test_fallback_count" in m and int(fb.sum())!=int(m["test_fallback_count"]):self.issue(key,kind,"fallback_count",f"{fb.sum()} != {m['test_fallback_count']}")
   if fb.shape==(n,) and "test_fallback_per_class" in m:
    for c in range(7):
     q=m["test_fallback_per_class"].get(str(c),m["test_fallback_per_class"].get(c,{}))
     if q and int(q.get("fallback_count",-1))!=int(np.sum(fb&(y==c))):self.issue(key,kind,"fallback_per_class",str(c))
  if m.get("test_ids_sha256") and m["test_ids_sha256"]!=sha256_ids(ids):self.issue(key,kind,"test_ids_sha256",m["test_ids_sha256"])
  if "y_true" in z and not np.array_equal(np.asarray(z["y_true"],int),y):self.issue(key,kind,"stored_true_labels","ensemble y_true differs from fixed test label order")
  if m.get("calibration_ids_sha256") and m["calibration_ids_sha256"]!=sha256_ids(role["calibration_ids"]):self.issue(key,kind,"calibration_ids_sha256",m["calibration_ids_sha256"])
  if m.get("fit_ids_sha256") and m["fit_ids_sha256"]!=sha256_ids(role["fit_ids"]):self.issue(key,kind,"fit_ids_sha256",m["fit_ids_sha256"])
  if isinstance(m.get("training_role_hashes"),dict):
   for member,obj in m["training_role_hashes"].items():
    if obj.get("fit_ids_sha256")!=sha256_ids(role["fit_ids"]):self.issue(key,kind,"member_fit_ids_sha256",member)
  if isinstance(m.get("pipeline_sha256"),dict):
   for fk in m.get("source_fit_keys",[]):
    ft=bykey.get(fk);fp=self.task_art(ft)/"pipeline.joblib" if ft else None
    if not ft or ft.get("status")!="validated_terminal" or ft.get("outcome")!="successful":self.issue(key,kind,"ensemble_fit_source_unvalidated",fk)
    elif self.file_exists(fp) and m["pipeline_sha256"].get(ft.get("method"))!=self.file_hash(fp):self.issue(key,kind,"ensemble_pipeline_sha",fk)
  self._eval_metrics(key,m,self._metrics_doc(t.get("result",{})),y,pred,bits,cov,size,ncal)
  e6_saved_validation=None
  if t.get("e6_protocol_version")=="E6-v2":
   try:
    from e6_v2_validation import validate_e6_v2_saved_outputs
    e6_saved_validation=validate_e6_v2_saved_outputs(self.rt,t,m,z)
    paths.extend(Path(x) for x in e6_saved_validation.get("evidence_paths",[]))
    for item in e6_saved_validation.get("issues",[]):self.issue(key,kind,item.get("check","e6_v2_saved_comparison_invalid"),item.get("evidence","validation failed"))
   except Exception as exc:
    e6_saved_validation={"status":"invalid","validation_basis":"saved_cache_arithmetic","issues":[{"check":"e6_v2_saved_comparison_exception","evidence":f"{type(exc).__name__}: {exc}"}]}
    self.issue(key,kind,"e6_v2_saved_comparison_exception",exc)
  latest=Path(t["result_path"]) if t.get("result_path") else None
  extras=[out/"eval_result.json",latest]
  def compare_worker(doc,q,check_hash=True):
   rm=self._metrics_doc(doc)
   for k in ("balanced_accuracy","coverage","set_size","confusion_matrix","per_class","test_n","calibration_n","threshold","score_kind"):
    if k in m and k in rm:
     a,b=m[k],rm[k]
     same=(np.array_equal(np.asarray(a),np.asarray(b)) if k=="confusion_matrix" else (bool(np.isclose(float(a),float(b),atol=1e-10,rtol=0)) if k in {"balanced_accuracy","coverage","set_size","threshold"} else a==b))
     if not same:self.issue(key,kind,f"worker_{k}",f"evaluation={a}; worker={b}")
   if check_hash and doc.get("artifact_sha256") and doc["artifact_sha256"]!=self.file_hash(op):
    self.issue(key,kind,"worker_outcome_hash",f"recorded={doc['artifact_sha256']}; current={self.file_hash(op)}; record={q}")
  for q in extras:
   if not q or not q.exists():continue
   paths.append(q)
   try:compare_worker(json.loads(q.read_text()),q)
   except Exception as e:self.issue(key,kind,"worker_record_read",f"{q}: {e}")
  # A superseded first result is accepted only after independently checking its retained
  # exact original container, initial receipt, current receipt, CRCs, and every shared array.
  restoration_ok=False; restoration_info=None
  if restoration is not None:
   restoration_ok,restoration_info,proof_paths=self._verify_restoration_entry(t,restoration,m,restoration_manifest_sha,restoration_manifest_valid)
   paths.extend(proof_paths)
   if restoration_ok:self.supersessions.append(restoration_info)
   else:self.issue(key,kind,"original_container_supersession_proof_failed","; ".join(restoration_info["errors"]),severity="review")
  # Historical attempts may be superseded only by verified exact original-container proof.
  latest_res=str(latest.resolve()) if latest else None
  for att in t.get("attempts",[]):
   q=Path(att["result_path"]) if att.get("result_path") else None
   if not q or not q.exists() or str(q.resolve())==latest_res:continue
   paths.append(q)
   try:
    doc=json.loads(q.read_text());oldhash=doc.get("artifact_sha256");curhash=self.file_hash(op)
    if oldhash and oldhash!=curhash:
     before=len(self.issues);compare_worker(doc,q,check_hash=False);newissues=self.issues[before:]
     metric_issues=[x["check"] for x in newissues]
     proven=(restoration_ok and restoration is not None and att.get("attempt_id")==restoration.get("initial_attempt_id"))
     if not proven or metric_issues:
      self.issue(key,kind,"superseded_attempt_hash_mismatch",
       f"attempt={att.get('attempt_id')}; recorded_npz_sha256={oldhash}; current_npz_sha256={curhash}; core_metric_mismatches={metric_issues}; restoration_proof_valid={proven}; no disposition applied",
       severity="review")
   except Exception as e:self.issue(key,kind,"historical_worker_record_read",f"{q}: {e}")
  fitkey=t.get("fit_key")
  if fitkey:
   ft=bykey.get(fitkey);fp=self.task_art(ft)/"pipeline.joblib" if ft else None
   if not ft or fitkey not in validset:self.issue(key,kind,"fit_source_unvalidated",fitkey)
   elif self.file_exists(fp):
    paths.append(fp)
    if m.get("pipeline_sha256") and m["pipeline_sha256"]!=self.file_hash(fp):self.issue(key,kind,"pipeline_hash",f"stored={m['pipeline_sha256']}; actual={self.file_hash(fp)}")
  self._eval_hashes(t,out,{"test_outcomes.npz":op,"evaluation.json":ep},paths,validated_original_container_sha=restoration.get("old_expected_sha256") if restoration_ok else None)
  if fallback_missing:
   new_issues=self.issues[issue_start:]
   hash_checks={"initial_hash_mismatch","validation_hash_mismatch","worker_outcome_hash","initial_hash_missing","validation_hash_missing","validation_json_missing","initial_hashes_missing"}
   metric_checks={"balanced_accuracy","coverage","set_size","confusion_matrix","test_n","calibration_n","per_class_schema"}
   metric_checks.update(f"class_{c}_{m}" for c in range(7) for m in ("n","recall","coverage","set_size"))
   metric_checks.update(f"registry_{m}" for m in ("balanced_accuracy","coverage","set_size","confusion_matrix","per_class","calibration_n","test_n","threshold","conformal_threshold","score_kind"))
   metric_checks.update(f"worker_{m}" for m in ("balanced_accuracy","coverage","set_size","confusion_matrix","per_class","test_n","calibration_n","threshold","score_kind"))
   blockers=[x for x in new_issues if x["check"] in hash_checks|metric_checks]
   if blockers:
    self.issue(key,kind,"fallback_missing","fallback_mask absent; integrity/metric evidence has unresolved blocking checks, so diagnostic status cannot be established")
   else:
    self.diagnostic(key,kind,"fallback_unknown","fallback_mask was not saved; fallback behavior is unknown and not rowwise verified. No values were imputed.")
  record={"task_key":key,"kind":t["kind"],"physical_outcome":True,"status":"checked","test_n":n,"calibration_n":ncal,"outcome_path":str(op)}
  if e6_saved_validation is not None:record["e6_v2_saved_cache_validation"]=e6_saved_validation
  return paths,record

 def run(self,evaluation_only=False):
  if evaluation_only and self.require_calibration_replay: raise ValueError("--require-calibration-replay cannot be combined with --evaluation-only")
  if self.cold_store is None:return self._run_snapshot(evaluation_only)
  # Keep one shared read lease for the entire audit snapshot. The writer cannot append
  # between manifest alias-map refresh and per-artifact verification.
  with self.cold_store._read_lock():
   self._refresh_cold_members()
   self._cold_session_depth+=1
   try:return self._run_snapshot(evaluation_only)
   finally:self._cold_session_depth-=1
 def _run_snapshot(self,evaluation_only=False):
  rp=self.rt/"registry.json"; snapshot_bytes=rp.read_bytes();registry=json.loads(snapshot_bytes);registry_sha=hashlib.sha256(snapshot_bytes).hexdigest();tasks=registry.get("tasks",[])
  bykey={t["key"]:t for t in tasks if t.get("key")}
  restoration_entries,restoration_manifest_valid,restoration_error=self._load_restoration_manifest()
  valid=[t for t in tasks if t.get("status")=="validated_terminal" and t.get("outcome")=="successful"]
  for t in valid:
   kind=t.get("kind")
   eval_kinds={"eval","ensemble","alias"}
   if evaluation_only:
    if kind not in eval_kinds:continue
   elif kind not in {"fit","generate","e4_cohort","e4_treatment","e4_append","e5_corruption"}|eval_kinds:continue
   key=t["key"]; prior=self.cache.get("tasks",{}).get(key,{})
   paths=[]
   restoration=restoration_entries.get(key)
   if restoration is not None:
    paths.append(self.rt/RESTORATION_MANIFEST_REL)
    for field in ("restored_path","source_candidate_path","support_diagnostic_baseline_path","initial_worker_result_path","initial_request_path"):
     if restoration.get(field):paths.append(Path(restoration[field]))
   if kind in eval_kinds:
    out=self.task_art(t);paths=[out/"evaluation.json",out/"validation.json"]
    if kind in {"eval","ensemble"}:
     paths += [out/"test_outcomes.npz",self.rt/"cache/test.npz",self.rt/"cache/cache_manifest.json",self.rt/"cache/roles"/f"rep_{t.get('rep')}.npz"]
     if t.get("result_path"):paths.append(Path(t["result_path"]))
     paths += [Path(a["result_path"]) for a in t.get("attempts",[]) if a.get("result_path")]
     if kind=="eval" and t.get("fit_key") in bykey:paths.append(self.task_art(bykey[t["fit_key"]])/"pipeline.joblib")
     if kind=="ensemble" and t.get("e6_protocol_version")=="E6-v2":
      paths.append(out/"member_comparisons.json")
      try:
       edoc=json.loads((out/"evaluation.json").read_text());sig=edoc.get("posterior_cache_key")
       if isinstance(sig,str) and len(sig)==24 and all(c in "0123456789abcdef" for c in sig):
        shared=self.rt/"cache"/"e6_posteriors"/f"rep_{int(t.get('rep'))}"/sig
        for stage in ("tune","cal","test"):paths.extend([shared/(stage+".npz"),shared/(stage+".receipt.json")])
       if edoc.get("member_comparisons_path")=="member_comparisons.json":
        md=json.loads((out/"member_comparisons.json").read_text())
        ledger=md.get("candidate_ledger_path")
        if isinstance(ledger,str) and ledger and Path(ledger).name==ledger:paths.append(out/ledger)
       tuning=out/"tuning_posteriors.npz"
       if tuning.is_file():paths.append(tuning)
      except Exception:pass
    else:
     if (out/"artifact_ref.json").exists():paths.append(out/"artifact_ref.json")
     src=bykey.get(t.get("source_key"))
     if src:
      so=self.task_art(src);paths.append(so/"evaluation.json")
      physical=src;seen={t["key"]}
      while physical and physical.get("kind")=="alias":
       nxt=physical.get("source_key")
       if nxt in seen:break
       seen.add(nxt);physical=bykey.get(nxt)
      if physical and physical.get("kind") in {"eval","ensemble"}:paths.append(self.task_art(physical)/"test_outcomes.npz")
   # Gather core files including dependencies so cache invalidates when source evidence changes.
   if kind=="fit":
    paths=self.fit_inputs(t,bykey)
   elif kind not in eval_kinds:
    paths=[self.task_art(t)/("pipeline.joblib" if kind=="fit" else "data.npz")]
    if kind in {"e4_cohort","e5_corruption"}:
     paths.append(self.rt/"cache/roles"/f"rep_{t.get('rep')}.npz")
    if kind in {"e4_cohort","e4_treatment","e4_append","e5_corruption"}:
     paths += [self.task_art(t)/x for x in ("metadata.json","audit.npz")]
    paths += [self.task_art(bykey[d])/f for d in t.get("dependencies",[]) if d in bykey for f in ("data.npz","pipeline.joblib","metadata.json","audit.npz")]
    if kind=="e4_append":
     paths += [self.rt/"cache/roles"/f"rep_{t.get('rep')}.npz",self.rt/"cache/test.npz",self.rt/"cache/development_X.npy",self.rt/"cache/development_y.npy",self.rt/"cache/development_ids.npy"]
     ck=t.get("cohort_key")
     paths += [self.task_art(x)/"data.npz" for x in tasks if x.get("kind")=="e4_treatment" and x.get("cohort_key")==ck and x.get("treatment") in {"ros","smote"} and x.get("status")=="validated_terminal" and x.get("outcome")=="successful"]
   # Hash files via persistent size/mtime/SHA memo; registry record text catches task-level changes.
   if restoration is not None:
    for pth in paths:self.file_hash(pth,force=True)
   hashes={str(Path(p)):self.file_hash(p) for p in paths if p and self.file_exists(p)}
   signature=hashlib.sha256(json.dumps(self.task_signature_payload(t,bykey,hashes),sort_keys=True,default=str).encode()).hexdigest()
   replay_proof=False
   if self.require_calibration_replay and kind=="fit":
    replay_proof=self._restore_replay_cache_for_fit(t,bykey)
    if replay_proof:
     self._replay_proof_fit_keys.add(key);self._write_calibration_replay_progress(None,None,state="idle")
   cache_hit=prior.get("signature")==signature and (not self.require_calibration_replay or kind!="fit" or replay_proof)
   if cache_hit:
    findings=prior.get("issues",[]);diagnostics=prior.get("diagnostics",[]);supersessions=prior.get("supersessions",[])
    self.issues.extend(findings);self.diagnostics.extend(diagnostics);self.supersessions.extend(supersessions);self.records.append({"task_key":key,"kind":kind,"status":"cached","issue_count":len(findings)});continue
   before=len(self.issues); record=None
   try:
    if kind=="fit":paths=self.fit_audit(t,bykey)
    elif kind=="generate":paths=self.generate_audit(t,bykey)
    elif kind=="e4_cohort":paths=self.e4_cohort_audit(t,bykey)
    elif kind=="e4_treatment":paths=self.treatment_audit(t,bykey)
    elif kind=="e4_append":paths=self.e4_append_audit(t,bykey)
    elif kind=="e5_corruption":paths=self.e5_audit(t,bykey)
    elif kind in {"eval","ensemble","alias"}:paths,record=self.evaluation_audit(t,bykey,{x["key"] for x in valid},alias=(kind=="alias"),restoration=restoration,restoration_manifest_sha=self.restoration_manifest_sha256,restoration_manifest_valid=restoration_manifest_valid)
   except Exception as e:self.issue(key,kind,"auditor_exception",e)
   findings=self.issues[before:]
   diagnostics=[x for x in self.diagnostics if x.get("task_key")==key]
   supersessions=[x for x in self.supersessions if x.get("task_key")==key]
   # Store the canonical pre-audit signature (artifact + all declared dependency inputs).
   # If an input changed while the check ran, the next invocation observes its new SHA.
   self.cache.setdefault("tasks",{})[key]={"signature":signature,"issues":findings,"diagnostics":diagnostics,"supersessions":supersessions,"validated_utc":datetime.now(timezone.utc).isoformat()}
   entry={"task_key":key,"kind":kind,"status":"audited","issue_count":len(findings)}
   if kind in {"eval","ensemble","alias"} and record:entry.update(record)
   self.records.append(entry)
  # E4 nested target cohorts across severity; E5 exact row-mask nesting across rates.
  if not evaluation_only:self.cross_checks(valid,bykey)
  _atomic_json(self.cache_path,self.cache)
  ev_valid=[x for x in valid if x.get("kind") in {"eval","ensemble","alias"}]
  ev_physical=[x for x in ev_valid if x.get("kind") in {"eval","ensemble"}]
  ev_alias=[x for x in ev_valid if x.get("kind")=="alias"]
  report={"generated_utc":datetime.now(timezone.utc).isoformat(),"registry_observed_utc":registry.get("observed_utc"),
   "registry_snapshot_sha256":registry_sha,"registry_snapshot_note":"Audits only validated-terminal successful entries from this atomic registry snapshot; later queue progress is outside this snapshot.",
   "auditor_version":VERSION,"mode":"evaluation_only" if evaluation_only else "full",
   "calibration_replay_required":self.require_calibration_replay,
   "validated_successful_registry_entries":len(valid),"validated_successful_outcome_entries":len(ev_valid),
   "physical_outcome_entries":len(ev_physical),"alias_entries":len(ev_alias),
   "threshold_quantile_recomputed":False,"threshold_note":"Stored threshold is integrity-checked through recorded metrics; conformal quantile is not recomputed because calibration scores are not saved.",
   "audited_entries":len(self.records),"issue_count":len(self.issues),"blocking_review_issue_count":sum(1 for x in self.issues if x.get("severity")=="review"),
   "diagnostic_limitations_count":len(self.diagnostics),"validated_supersession_count":len(self.supersessions),
   "restoration_manifest_sha256":self.restoration_manifest_sha256,"restoration_manifest_source_sha256":self.restoration_manifest_source_sha256,"restoration_manifest_payload_sha256":self.restoration_manifest_sha256,"validated_supersessions":self.supersessions,"issues_by_severity":{},
   "records":self.records,"issues":self.issues,"diagnostic_limitations":self.diagnostics}
  for i in self.issues:report["issues_by_severity"][i["severity"]]=report["issues_by_severity"].get(i["severity"],0)+1
  reports=self.rt/"reports"
  if self.require_calibration_replay and not evaluation_only:
   import calibration_replay as cr
   required=[x for x in valid if int(x.get("experiment") or 0) in {3,4,5,6} and x.get("kind") in {"eval","ensemble","alias"}]
   seen={x.get("task_key") for x in self.calibration_replay_physical}
   physical=[x for x in required if x.get("kind") in {"eval","ensemble"}
      and not (x.get("kind")=="ensemble" and x.get("e6_protocol_version")=="E6-v2")]
   e6_required=[x for x in required if x.get("kind")=="ensemble" and x.get("e6_protocol_version")=="E6-v2"]
   rows=list(self.calibration_replay_physical)
   for ev in physical:
    if ev["key"] not in seen: rows.append({"task_key":ev["key"],"fit_key":ev.get("fit_key"),"status":"unavailable","reasons":["no physical calibration replay result"]})
   physical_rows=[x for x in rows if x.get("task_key") in {t["key"] for t in physical}]
   physical_by={x.get("task_key"):x for x in physical_rows}
   alias_rows=[]
   for al in (x for x in required if x.get("kind")=="alias"):
    source=bykey.get(al.get("source_key")); trail=[]; visited=set()
    while source and source.get("kind")=="alias" and source.get("key") not in visited:
     visited.add(source.get("key"));trail.append(source["key"]);source=bykey.get(source.get("source_key"))
    physical_source=source.get("key") if source and source.get("kind") in {"eval","ensemble"} else None
    pr=physical_by.get(physical_source); status="unavailable"; reasons=[]; match=False
    role_ok=score_ok=rule_ok=class_ok=alpha_ok=False;class_order_basis=None
    try:
     adoc=json.loads((self.task_art(al)/"evaluation.json").read_text())
     pdoc=json.loads((self.task_art(source)/"evaluation.json").read_text()) if source else None
     role_path,arole=self.role(al.get("rep"),["X_cal","y_cal","calibration_ids"])
     checks=cr.validate_alias(adoc,pdoc,pr,self.file_hash(role_path,force=True),cr.typed_sha(arole["calibration_ids"]),
       cr.typed_sha(arole["X_cal"]),cr.typed_sha(arole["y_cal"]))
     role_ok=checks["calibration_role"];score_ok=checks["score_kind"];rule_ok=checks["nonconformity_rule"]
     class_ok=checks["class_order"];class_order_basis=checks["class_order_basis"];alpha_ok=checks["alpha"];match=checks["match"]
     if pr and pr.get("status")=="validated" and match: status="inherited"
     elif pr and pr.get("status")=="validated": status="mismatch";reasons=["alias threshold, role, score/rule, class order, or alpha differs from physical source"]
     else: reasons=["physical source replay is unavailable or mismatched"]
    except Exception as e: reasons=[f"{type(e).__name__}: {e}"]
    alias_rows.append({"task_key":al["key"],"source_key":al.get("source_key"),"physical_source_key":physical_source,
      "status":status,"source_identity":pr.get("identity") if pr else None,"threshold_match":bool(match),
      "calibration_role_match":bool(role_ok),"score_kind_match":bool(score_ok),
      "nonconformity_rule_match":bool(rule_ok),"class_order_match":bool(class_ok),
      "class_order_basis":class_order_basis,"alpha_match":bool(alpha_ok),
      "inherited_from_physical":status=="inherited","reasons":reasons})
   self.e6_ensemble_calibration_records=[]
   for et in e6_required:
    key=et["key"]; mode=et.get("mode"); members=et.get("members",{}); art=self.task_art(et)
    row={"task_key":key,"mode":mode,"status":"unavailable","validation_basis":"fresh_native_calibration_scores",
         "member_order":["gmm","copula","arf","kde","chow_liu"],"members":[],"reasons":[]}
    try:
     evdoc=json.loads((art/"evaluation.json").read_text()); cmpath=art/"member_comparisons.json"; cmp=json.loads(cmpath.read_text())
     if evdoc.get("member_comparisons_sha256")!=self.file_hash(cmpath,force=True):raise ValueError("E6 comparison SHA mismatch")
     if cmp.get("weights_frozen_before_calibration_and_test") is not True:raise ValueError("E6 weights were not recorded frozen before calibration/test")
     order=row["member_order"]; scores=[]; member_records=[]
     if set(members)!=set(order):raise ValueError("E6 task member mapping incomplete")
     for name in order:
      fitkey=members[name]; native=self._e6_native_calibration_scores.get(fitkey)
      mr=next((r for r in self.e6_member_calibration_records if r.get("task_key")==key and r.get("member")==name),None)
      if not native or not mr or mr.get("status")!="validated":raise ValueError(f"native member calibration evidence unavailable/mismatched: {name}")
      if native["score_kind"]!="probability" or native["class_order"]!=list(range(7)):raise ValueError(f"native member score/class contract invalid: {name}")
      scores.append(native["scores"]);member_records.append({"member":name,"fit_key":fitkey,"record_status":mr["status"],
       "pipeline_sha256":native["pipeline_sha256"],"role_file_sha256":native["role_file_sha256"],
       "calibration_ids_sha256":native["calibration_ids_sha256"],"X_cal_sha256":native["X_cal_sha256"],
       "y_cal_sha256":native["y_cal_sha256"],"native_threshold":mr.get("native_threshold"),
       "comparison_sha256":mr.get("comparison_sha256"),"native_nonconformity_sha256":mr.get("native_nonconformity_sha256"),
       "native_replay_identity":mr.get("native_replay_identity"),"native_replay_metadata_path":mr.get("native_replay_metadata_path"),
       "native_replay_metadata_sha256":mr.get("native_replay_metadata_sha256"),"native_replay_vector_path":mr.get("native_replay_vector_path"),
       "native_replay_vector_file_sha256":mr.get("native_replay_vector_file_sha256"),"native_replay_vector_sha256":mr.get("native_replay_vector_sha256"),
       "rank_k":mr.get("rank_k"),"fit_ids_sha256":mr.get("fit_ids_sha256"),"role_membership_sha256":mr.get("role_membership_sha256"),
       "selected_params_sha256":mr.get("selected_params_sha256"),"provenance_group":mr.get("provenance_group")})
     if not all(np.array_equal(self._e6_native_calibration_scores[members[n]]["y"],self._e6_native_calibration_scores[members[order[0]]]["y"]) for n in order):
      raise ValueError("native member calibration role labels differ")
     weights=np.asarray(cmp.get("selected_weights"),dtype=np.float64)
     if weights.shape!=(5,) or not np.isfinite(weights).all() or np.any(weights<0) or not np.isclose(weights.sum(),1,atol=1e-10,rtol=0):raise ValueError("E6 selected weights invalid")
     mixture=sum(weights[i]*scores[i] for i in range(5)); yy=self._e6_native_calibration_scores[members[order[0]]]["y"]
     derived=cr.derive(mixture,yy,"probability",alpha=.1); saved=cmp.get("ensemble_threshold"); primary=evdoc.get("conformal_threshold")
     if saved is None or primary is None or not math.isclose(float(saved),derived["threshold"],rel_tol=0,abs_tol=1e-10) or not math.isclose(float(primary),derived["threshold"],rel_tol=0,abs_tol=1e-10):
      raise ValueError("ensemble threshold differs from fresh native calibration mixture")
     row.update({"status":"validated","members":member_records,"weights":weights.tolist(),"alpha":.1,
       "calibration_n":len(yy),"native_threshold":derived["threshold"],"saved_threshold":float(saved),
       "primary_threshold":float(primary),"posterior_cache_key":evdoc.get("posterior_cache_key"),
       "comparison_sha256":evdoc.get("member_comparisons_sha256"),"reasons":[]})
    except Exception as exc:
     row["status"]="mismatch" if row.get("members") else "unavailable";row["reasons"]=[f"{type(exc).__name__}: {exc}"]
    self.e6_ensemble_calibration_records.append(row)
   e6_member_required=len(e6_required)*5
   e6_members_valid=sum(r.get("status")=="validated" for r in self.e6_member_calibration_records if r.get("task_key") in {x["key"] for x in e6_required})
   e6_ensembles_valid=sum(r.get("status")=="validated" for r in self.e6_ensemble_calibration_records)
   e6_coverage_complete=(len(self.e6_member_calibration_records)==e6_member_required and e6_members_valid==e6_member_required
       and len(self.e6_ensemble_calibration_records)==len(e6_required) and e6_ensembles_valid==len(e6_required))
   summary=cr.summarize(physical_rows,alias_rows)
   summary["required_e6_ensembles"]=len(e6_required);summary["validated_e6_ensembles"]=e6_ensembles_valid
   summary["required_e6_member_calibration_records"]=e6_member_required;summary["validated_e6_member_calibration_records"]=e6_members_valid
   summary["e6_native_calibration_replay_complete"]=bool(e6_coverage_complete)
   report["threshold_quantile_recomputed"]=bool(summary["complete"] and e6_coverage_complete)
   report["threshold_note"]=("Independent calibration replay validated every required physical outcome and alias." if summary["complete"] else
       "Calibration replay was requested but at least one required physical outcome or alias is unavailable or mismatched; no complete q-validation claim is made.")
   ledger_sha=sha256_file(self.calibration_replay_phase_ledger_path) if self.calibration_replay_phase_ledger_path.is_file() else hashlib.sha256(b"").hexdigest()
   calreport={"schema_version":"lamost-calibration-replay-audit/1","generated_utc":datetime.now(timezone.utc).isoformat(),
     "registry_snapshot_sha256":registry_sha,"replay_run_nonce":self.calibration_replay_run_id,
     "phase_ledger_path":str(self.calibration_replay_phase_ledger_path.relative_to(self.rt)),"phase_ledger_sha256":ledger_sha,
     "accepted_prior_receipts_index_sha256":self.accepted_prior_receipts_sha256,
     **summary,"q_replay_coverage_complete":bool(summary["complete"] and e6_coverage_complete),
     "e6_member_calibration_records":self.e6_member_calibration_records,
     "e6_ensemble_calibration_records":self.e6_ensemble_calibration_records,
     "complete":False,"complete_requires_external_supervision_receipt":True,"records":[*physical_rows,*alias_rows],
     "policy":{"alpha":.1,"class_order":list(range(7)),"quantile":"k=ceil((n+1)*(1-alpha)); q=numpy.partition(nonconformity,k-1)[k-1]; q=infinity if k>n",
       "supervision":{"wall_seconds":600,"rss_limit_bytes":10*1024**3,"enforced_by_auditor":False,
         "external_supervision_required":True,"external_supervision_status":"not_verified_by_auditor",
         "external_receipt_path":"reports/CALIBRATION_REPLAY_SUPERVISION.json"},
       "replay_reads_test_rows":False,"pipeline_reused_without_fork":True}}
   _atomic_json(reports/"CALIBRATION_REPLAY_AUDIT.json",calreport)
  if evaluation_only:
   _atomic_json(reports/"INCREMENTAL_EVALUATION_AUDIT.json",report)
   _atomic_csv(reports/"INCREMENTAL_EVALUATION_ISSUES.csv",self.issues)
   _atomic_csv(reports/"INCREMENTAL_EVALUATION_DIAGNOSTICS.csv",self.diagnostics)
   if self.supersessions:
    _atomic_json(reports/"engineering_audits"/"e3_original_container_supersession_validation.json",{
     "generated_utc":report["generated_utc"],"auditor_version":VERSION,"restoration_manifest_sha256":self.restoration_manifest_sha256,
     "validated_supersession_count":len(self.supersessions),"validated_supersessions":self.supersessions,
     "no_original_worker_or_registry_records_modified":True})
  else:
   _atomic_json(reports/"INCREMENTAL_ARTIFACT_AUDIT.json",report)
   _atomic_csv(reports/"INCREMENTAL_ARTIFACT_ISSUES.csv",self.issues)
   _atomic_csv(reports/"INCREMENTAL_ARTIFACT_DIAGNOSTICS.csv",self.diagnostics)
  return report
 def task_signature_payload(self,t,bykey,hashes):
  source_key=t.get("selection_key")
  dependency=None
  if source_key:
   src=bykey.get(source_key)
   dependency={"key":source_key,"present":src is not None}
   if src is not None:
    dependency.update({"status":src.get("status"),"outcome":src.get("outcome"),"method":src.get("method"),"rep":src.get("rep"),"result_metadata":src.get("result",{})})
  append_dependencies=[]
  if t.get("kind")=="e4_append":
   keys=list(t.get("dependencies",[]))
   for depkey in list(keys):
    dep=bykey.get(depkey)
    if dep and dep.get("kind")=="generate":keys.extend(dep.get("dependencies",[]))
   for x in bykey.values():
    if x.get("kind")=="e4_treatment" and x.get("cohort_key")==t.get("cohort_key") and x.get("treatment") in {"ros","smote"}:keys.append(x.get("key"))
   keys=list(dict.fromkeys(x for x in keys if x))
   for depkey in keys:
    dep=bykey.get(depkey)
    append_dependencies.append({"key":depkey,"present":dep is not None,"status":dep.get("status") if dep else None,"outcome":dep.get("outcome") if dep else None,"kind":dep.get("kind") if dep else None,"method":dep.get("method") if dep else None,"rep":dep.get("rep") if dep else None,"result_metadata":dep.get("result",{}) if dep else None})
  result={"record":t,"selection_dependency":dependency,"append_dependency_records":append_dependencies,"hashes":hashes,"version":VERSION}
  if self.require_calibration_replay and t.get("kind")=="fit":result["calibration_replay_required"]=True
  return result
 def fit_inputs(self,t,bykey):
  out=self.task_art(t); paths=[out/"pipeline.joblib",out/"selection.json",out/"fit_result.json"]
  if t.get("train_key") in bykey:paths.append(self.task_art(bykey[t["train_key"]])/"data.npz")
  else:paths.append(self.rt/"cache/roles"/f"rep_{t.get('rep')}.npz")
  if t.get("selection_source"):
   try:
    source=self.resolve_recorded_path(t["selection_source"])
    source_sel=source/"selection.json" if source.is_dir() else source
    paths.append(source_sel)
    if source_sel.is_file():
     imported=json.loads(source_sel.read_text())
     if imported.get("source_path"):paths.append(self.resolve_recorded_path(imported["source_path"]))
   except Exception:pass
  if t.get("selection_key") in bykey:
   srcout=self.task_art(bykey[t["selection_key"]]);paths.extend([srcout/"selection.json",srcout/"pipeline.joblib"])
  meta=t.get("result",{}).get("result",{})
  if meta.get("reused"):
   source=meta.get("source") or (t.get("source_metadata") or {}).get("path")
   if source:paths.append(self.resolve_recorded_path(source))
  if self.require_calibration_replay:
   method=str(t.get("method") or "")
   from benchmark import models_arf,models_basic,models_flexible
   module=models_arf if method=="arf" else (models_flexible if method in {"gmm","copula","kde","chow_liu"} else models_basic)
   paths.append(Path(module.__file__).resolve())
   paths.append(self.project/"benchmark"/"results"/"e1_report_validated_no_bootstrap.json")
   paths.append(Path(__file__).with_name("calibration_replay.py"))
   for ev in bykey.values():
    if ev.get("kind")=="eval" and ev.get("fit_key")==t.get("key") and int(ev.get("experiment") or 0) in {3,4,5,6}:
     eo=self.task_art(ev);paths.extend([eo/"evaluation.json",eo/"calibration.json"])
  return paths
 def cross_checks(self,valid,bykey):
  # Revisit cross-condition groups only when all corresponding outputs are terminal-success.
  groups={}
  for t in valid:
   if t.get("kind")=="e4_cohort":
    groups.setdefault(("e4",t.get("rep"),str(t.get("target_class"))),[]).append(t)
   if t.get("kind")=="e5_corruption":
    groups.setdefault(("e5",t.get("rep"),t.get("mechanism")),[]).append(t)
  tgroups={}
  for t in valid:
   if t.get("kind")=="e4_treatment":
    g=(t.get("rep"),str(t.get("target_class")),float(t.get("ratio") or 0),str(t.get("treatment")))
    tgroups.setdefault(g,[]).append(t)
  for g,ts in tgroups.items():
   if len(ts)<2:continue
   try:
    digests={self.file_hash(self.task_art(t)/"data.npz") for t in ts}
    if len(digests)>1:self.issue(ts[0]["key"],"e4_treatment","learner_dataset_sharing",f"same treatment condition has different data.npz hashes across learners: {[(t['key'],self.file_hash(self.task_art(t)/'data.npz')) for t in ts]}")
   except Exception as e:self.issue(ts[0]["key"],"e4_treatment","learner_dataset_sharing_check",e)
  for g,ts in groups.items():
   if g[0]=="e4":
    half=next((x for x in ts if float(x.get("ratio") or 0)==.5),None);tenth=next((x for x in ts if float(x.get("ratio") or 0)==.1),None)
    if not half or not tenth:continue
    try:
     a=self.load_npz(self.task_art(half)["/data.npz"] if False else self.task_art(half)/"data.npz")
     b=self.load_npz(self.task_art(tenth)/"data.npz");c=_label_code(half["target_class"])
     if not set(b["ids"][b["y"]==c].tolist()).issubset(set(a["ids"][a["y"]==c].tolist())):
      self.issue(tenth["key"],"e4_cohort","target_nestedness","tenth-share target IDs are not a subset of half-share target IDs")
    except Exception as e:self.issue(tenth["key"],"e4_cohort","nestedness_check",e)
   else:
    byrate={float(x["rate"]):x for x in ts}
    if not all(r in byrate for r in (.05,.10,.20)):continue
    try:
     sets=[]
     for rate in (.05,.10,.20):
      z=self.load_npz(self.task_art(byrate[rate])/"audit.npz");sets.append(set(np.asarray(z["affected_row_indices"],int).tolist()))
     if not sets[0]<=sets[1]<=sets[2]:self.issue(byrate[.20]["key"],"e5_corruption","mask_nestedness","affected-row masks are not nested across rates")
    except Exception as e:self.issue(byrate[.20]["key"],"e5_corruption","mask_nestedness_check",e)

def resolve_cold_store(runtime):
 runtime=Path(runtime).resolve();manifest=runtime/"manifests"/"cold_model_store_manifest.json"
 if not manifest.is_file():return None
 module_path=runtime/"source"/"cold_model_storage.py"
 if not module_path.is_file():raise RuntimeError(f"cold model manifest exists but deployed sibling resolver is missing: {module_path}")
 spec=importlib.util.spec_from_file_location("lamost_deployed_cold_model_storage",module_path)
 if spec is None or spec.loader is None:raise RuntimeError(f"cannot load deployed cold model resolver: {module_path}")
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 cls=getattr(module,"ColdModelStore",None)
 if cls is None or not hasattr(cls,"from_runtime"):raise RuntimeError("deployed cold model resolver lacks ColdModelStore.from_runtime")
 return cls.from_runtime(runtime.parent,runtime,manifest_path=manifest)

def resolve_extracted_cold_source(runtime):
 runtime=Path(runtime).resolve();root=runtime.parent
 projection=runtime/"manifests"/"cold_archived_artifact_members.json"
 if not projection.is_file():return None
 source=runtime/"source"/"extracted_cold_source.py"
 codec_path=runtime/"source"/"reversible_joblib_codec.py"
 if not source.is_file() or not codec_path.is_file():
  raise RuntimeError("extracted cold resolver or pinned codec module is missing")
 temp_root=runtime/"cache"
 if not temp_root.is_dir() or temp_root.is_symlink():
  raise RuntimeError("extracted cold resolver requires an existing safe runtime/cache temp root")
 try:
  import joblib.compressor
  compressor=Path(joblib.compressor.__file__).resolve(strict=True)
 except Exception as e:
  raise RuntimeError("pinned joblib compressor source is unavailable") from e
 spec=importlib.util.spec_from_file_location("lamost_extracted_cold_source",source)
 if spec is None or spec.loader is None:raise RuntimeError("cannot load extracted cold-source resolver")
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 cls=getattr(module,"ExtractedColdSource",None)
 if cls is None:raise RuntimeError("extracted cold-source resolver lacks ExtractedColdSource")
 return cls(root,runtime,temp_root,codec_path,compressor,projection)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--runtime",default="/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025");ap.add_argument("--evaluation-only",action="store_true");ap.add_argument("--require-calibration-replay",action="store_true");ap.add_argument("--replay-run-nonce");ap.add_argument("--accepted-prior-replay-receipts");args=ap.parse_args()
 if args.evaluation_only and args.require_calibration_replay:raise SystemExit("--require-calibration-replay cannot be combined with --evaluation-only")
 replay_nonce=args.replay_run_nonce or os.environ.get("LAMOST_CAL_REPLAY_RUN_NONCE")
 if args.require_calibration_replay and not replay_nonce:raise SystemExit("supervised calibration replay requires parent-injected --replay-run-nonce")
 if args.evaluation_only:
  try:avail=next(int(line.split()[1])*1024 for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))
  except Exception:avail=0
  if avail<12*1024**3:raise SystemExit(f"evaluation-only audit refused: MemAvailable={avail} bytes < 12 GiB")
 try:
  cold_store=resolve_cold_store(args.runtime)
  extracted_cold_source=resolve_extracted_cold_source(args.runtime)
 except Exception as e:raise SystemExit(f"cold model resolver initialization failed: {type(e).__name__}: {e}")
 report=Auditor(args.runtime,cold_store=cold_store,require_calibration_replay=args.require_calibration_replay,
   replay_run_nonce=replay_nonce,accepted_prior_receipts=args.accepted_prior_replay_receipts,
   extracted_cold_source=extracted_cold_source).run(evaluation_only=args.evaluation_only)
 print(json.dumps({k:report.get(k) for k in ("generated_utc","validated_successful_registry_entries","validated_successful_outcome_entries","physical_outcome_entries","alias_entries","audited_entries","issue_count","blocking_review_issue_count","diagnostic_limitations_count","validated_supersession_count","issues_by_severity","mode")},indent=2))
if __name__=="__main__":main()
