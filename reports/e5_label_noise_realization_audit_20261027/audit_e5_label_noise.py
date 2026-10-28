#!/usr/bin/env python3
"""Read-only, ID-aligned audit of the 9 E5 label-noise realizations."""
from __future__ import annotations
import os,resource
L=1<<30
resource.setrlimit(resource.RLIMIT_AS,(L,L))
for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[k]="1"
import csv,datetime,hashlib,importlib,json,math,sqlite3,sys
from pathlib import Path
import numpy as np
R=Path("/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025")
OUT=R/"reports/e5_label_noise_realization_audit_20261027";CSVOUT=R/"reports/E5_label_noise_source_class_rates.csv"
PLAN=R/"manifests/tasks.json";CM=R/"cache/cache_manifest.json"
INSTALL=R/"reports/engineering_audits/REPORTING_REQUIRED_OUTPUTS_INSTALLED_20261027.json"
REPORT_SHA="d7f8d302fad59310f4c101b27a23575a66012b612f376df79fb277b02915cf19"
INSTALL_SHA="8a7346ee66010a548a70e6542b3833cd84832a52056606af749cb1191f91f690"
PLAN_SHA="42784648ca1cad873f6910a1bc5e76d8c104edb4c9826b8aacd9cecfa18b71eb"
LABELS=["A","F","G","K","M","GALAXY","QSO"];FIELDS=["task_key","rep","planned_corruption_rate","realized_corruption_rate","source_class_id","source_class_label","original_source_class_count","affected_source_class_count","changed_label_count","realized_source_class_corruption_rate","rate_status"]
N={.05:4000,.10:8000,.20:16000};GIB=1024**3
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def idsha(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def arrsha(a):
 a=np.ascontiguousarray(a);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.view(np.uint8));return h.hexdigest()
def sid(v):
 if isinstance(v,np.generic):v=v.item()
 if isinstance(v,bytes):return v.decode("utf-8")
 return str(v)
def loadkeys(p,ks):
 with np.load(p,allow_pickle=False) as z:
  miss=[k for k in ks if k not in z.files]
  if miss:raise ValueError(str(p)+" missing "+str(miss))
  return {k:np.array(z[k],copy=True) for k in ks}
def available():
 for s in Path("/proc/meminfo").read_text().splitlines():
  if s.startswith("MemAvailable:"):return int(s.split()[1])*1024
 raise RuntimeError("MemAvailable missing")
def rss():
 d={}
 for s in Path("/proc/self/status").read_text().splitlines():
  if s.startswith(("VmRSS:","VmHWM:","VmSize:")):
   k,v=s.split(":",1);d[k.strip()]=int(v.split()[0])
 return d
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 if sha(R/"source/reporting.py")!=REPORT_SHA or sha(INSTALL)!=INSTALL_SHA or sha(PLAN)!=PLAN_SHA:raise ValueError("reporting/source/plan SHA gate failed")
 ins=json.loads(INSTALL.read_text())
 if (ins.get("reporting_source_sha256"),ins.get("plan_sha256"),ins.get("status"),ins.get("test_count"),ins.get("failures"))!=(REPORT_SHA,PLAN_SHA,"installed_actual_controller_unchanged",382,0):raise ValueError("installation receipt gate failed")
 cm=json.loads(CM.read_text())
 if cm.get("labels")!=LABELS:raise ValueError("cache-manifest class order mismatch")
 tasks0=json.loads(PLAN.read_text()).get("tasks",[])
 tasks=sorted([t for t in tasks0 if t.get("experiment")==5 and t.get("kind")=="e5_corruption" and t.get("mechanism")=="label_noise"],key=lambda t:(int(t["rep"]),float(t["rate"])))
 if len(tasks)!=9 or {(int(t["rep"]),float(t["rate"])) for t in tasks}!={(r,q) for r in (1,2,3) for q in (.05,.10,.20)}:raise ValueError("frozen plan lacks exact 3x3 label-noise grid")
 for r in (1,2,3):
  if len({int(t["seed"]) for t in tasks if int(t["rep"])==r})!=1:raise ValueError("mask seeds differ across rates")
 mem0=available()
 if mem0<9*GIB:raise MemoryError("available RAM below 9 GiB safety floor")
 sys.path.insert(0,str(R/"source"));reporting=importlib.import_module("reporting")
 if sha(R/"source/reporting.py")!=REPORT_SHA:raise ValueError("reporting source changed during import")
 db=sqlite3.connect("file:"+str(R/"registry.sqlite")+"?mode=ro",uri=True,timeout=10);db.execute("PRAGMA query_only=ON");db.row_factory=sqlite3.Row
 inputs={"tasks_manifest_sha256":sha(PLAN),"cache_manifest_sha256":sha(CM),"reporting_source_sha256":REPORT_SHA,"installation_receipt_sha256":INSTALL_SHA,"tasks":{}}
 rolecounts={};rolehashes={};nested={};cr=[];tr=[];cellchecks=[]
 for rep in (1,2,3):
  rolep=R/"cache/roles"/("rep_"+str(rep)+".npz");rel="roles/rep_"+str(rep)+".npz"
  rh=sha(rolep)
  if rh!=cm.get("cache_files",{}).get(rel):raise ValueError("role NPZ cache hash mismatch rep "+str(rep))
  rolehashes[str(rep)]=rh; expected=cm.get("roles",{}).get(str(rep),{})
  z=loadkeys(rolep,["y_fit","fit_ids","tuning_ids","calibration_ids"])
  y0=np.asarray(z["y_fit"],dtype=np.int64);ids0=np.asarray(z["fit_ids"]);tune=np.asarray(z["tuning_ids"]);cal=np.asarray(z["calibration_ids"])
  if y0.shape!=(80000,) or ids0.shape!=(80000,) or len(np.unique(ids0))!=80000 or np.any((y0<0)|(y0>=7)):raise ValueError("invalid original fitting role rep "+str(rep))
  keys0=[sid(x) for x in ids0.tolist()];ixmap={v:i for i,v in enumerate(keys0)};fitset=set(keys0)
  if len(ixmap)!=80000 or fitset.intersection(sid(x) for x in tune.tolist()) or fitset.intersection(sid(x) for x in cal.tolist()):raise ValueError("fit IDs duplicate/overlap other roles rep "+str(rep))
  counts=np.bincount(y0,minlength=7).astype(int).tolist()
  if counts!=expected.get("fit_counts") or idsha(ids0)!=expected.get("id_hashes",{}).get("fit_ids"):raise ValueError("original role labels/IDs disagree with cache manifest rep "+str(rep))
  if len(tune)!=10000 or len(cal)!=10000:raise ValueError("tune/calibration role sizes differ from frozen 10k")
  rolecounts[str(rep)]=counts; sets=[]
  for task in [t for t in tasks if int(t["rep"])==rep]:
   key=task["key"];rate=float(task["rate"]);mexp=N[rate]
   row=db.execute("SELECT record FROM tasks WHERE key=?",(key,)).fetchone()
   if not row:raise ValueError("missing registry record "+key)
   rec=json.loads(row["record"]);regsha=hashlib.sha256(row["record"].encode()).hexdigest()
   if (rec.get("status"),rec.get("outcome"),rec.get("validation_state"))!=("validated_terminal","successful","validated"):raise ValueError("not validated-success "+key)
   if any(rec.get(f)!=task.get(f) for f in ("key","experiment","rep","kind","mechanism","rate","seed")):raise ValueError("registry/frozen task mismatch "+key)
   art=R/"artifacts"/key;mp=art/"metadata.json";dp=art/"data.npz";ap=art/"audit.npz"
   if not all(p.is_file() for p in (mp,dp,ap)):raise FileNotFoundError("missing artifacts "+key)
   meta=json.loads(mp.read_text());res=rec.get("result") or {};val=res.get("validation") or {};wm=res.get("metadata") or {}
   if val.get("status")!="validated" or val.get("task_key")!=key:raise ValueError("artifact validation identity mismatch "+key)
   if val.get("files",{}).get("data.npz")!=sha(dp):raise ValueError("data.npz validation hash mismatch "+key)
   if meta.get("task_key")!=key:raise ValueError("metadata task key mismatch "+key)
   for f in ("rep","mechanism","rate","seed","fit_count","affected_count","realized_rate","changed_label_count","other_roles_touched","transition_counts"):
    if meta.get(f)!=wm.get(f):raise ValueError("registry metadata differs from metadata.json at "+key+"/"+f)
   if meta.get("other_roles_touched") is not False or meta.get("relabeling")!="uniform among other six labels":raise ValueError("other roles or relabel specification mismatch "+key)
   if int(meta.get("fit_count",-1))!=80000 or int(meta.get("affected_count",-1))!=mexp or int(meta.get("changed_label_count",-1))!=mexp or not math.isclose(float(meta.get("realized_rate",-1)),mexp/80000,abs_tol=1e-15):raise ValueError("realized corruption budget mismatch "+key)
   data=loadkeys(dp,["y","ids"]);dy=np.asarray(data["y"],dtype=np.int64);dids=np.asarray(data["ids"])
   if dy.shape!=(80000,) or dids.shape!=(80000,) or len(np.unique(dids))!=80000:raise ValueError("data label/ID shape or uniqueness mismatch "+key)
   dkeys=[sid(x) for x in dids.tolist()];dmap={v:i for i,v in enumerate(dkeys)}
   if len(dmap)!=80000 or set(dkeys)!=fitset:raise ValueError("corruption data does not contain exact original fit ID set "+key)
   if set(dkeys).intersection(sid(x) for x in tune.tolist()) or set(dkeys).intersection(sid(x) for x in cal.tolist()):raise ValueError("tune/cal IDs found in corruption data "+key)
   a=loadkeys(ap,["affected_row_indices","affected_ids","affected_mask","old_label","new_label","label_offset","transition_counts"])
   ix=np.asarray(a["affected_row_indices"],dtype=np.int64);aids=np.asarray(a["affected_ids"]);mask=np.asarray(a["affected_mask"],dtype=bool);old=np.asarray(a["old_label"],dtype=np.int64);new=np.asarray(a["new_label"],dtype=np.int64);off=np.asarray(a["label_offset"],dtype=np.int64);amat=np.asarray(a["transition_counts"],dtype=np.int64);mmat=np.asarray(meta["transition_counts"],dtype=np.int64)
   if ix.shape!=(mexp,) or len(set(ix.tolist()))!=mexp or np.any((ix<0)|(ix>=80000)) or mask.shape!=(80000,) or int(mask.sum())!=mexp or set(np.flatnonzero(mask).tolist())!=set(ix.tolist()):raise ValueError("affected row mask/index count mismatch "+key)
   aidkeys=[sid(x) for x in aids.tolist()]
   if len(aidkeys)!=mexp or len(set(aidkeys))!=mexp or not set(aidkeys)<=fitset or set(keys0[i] for i in ix.tolist())!=set(aidkeys):raise ValueError("affected ID/source index mismatch "+key)
   masked={keys0[i] for i in np.flatnonzero(mask)}
   if masked!=set(aidkeys):raise ValueError("affected ID mask mismatches after ID alignment "+key)
   oldid=np.asarray([y0[ixmap[k]] for k in aidkeys],dtype=np.int64)
   newid=np.asarray([dy[dmap[k]] for k in aidkeys],dtype=np.int64)
   if not np.array_equal(old,oldid) or not np.array_equal(new,newid):raise ValueError("old/new labels fail ID-aligned source check "+key)
   if np.any(old==new) or np.any((new<0)|(new>=7)) or np.any((off<1)|(off>6)) or not np.array_equal((old+off)%7,new):raise ValueError("selected labels not changed to one of other six "+key)
   affected=set(aidkeys);sets.append((rate,affected));orig_by_data=np.asarray([y0[ixmap[k]] for k in dkeys],dtype=np.int64)
   selected=np.fromiter((k in affected for k in dkeys),dtype=bool,count=80000)
   if not np.array_equal(dy[~selected],orig_by_data[~selected]):raise ValueError("unselected label changed "+key)
   new_by_id={k:int(v) for k,v in zip(aidkeys,new)}
   if any(int(dy[dmap[k]])!=new_by_id[k] for k in affected):raise ValueError("selected new label mismatch "+key)
   matrix=np.zeros((7,7),dtype=np.int64);np.add.at(matrix,(old,new),1)
   if matrix.shape!=(7,7) or int(matrix.sum())!=mexp or np.any(np.diag(matrix)!=0) or not np.array_equal(matrix,amat) or not np.array_equal(matrix,mmat):raise ValueError("reconstructed 7x7 transition counts differ from audit/metadata "+key)
   if arrsha(aids)!=meta.get("affected_ids_sha256"):raise ValueError("affected IDs content hash mismatch "+key)
   outflow=matrix.sum(1);inflow=matrix.sum(0);final=np.bincount(dy,minlength=7)
   expect_final=np.asarray(counts,dtype=np.int64)-outflow+inflow
   if int(final.sum())!=80000 or np.any(expect_final<0) or not np.array_equal(final,expect_final):raise ValueError("final class counts fail source outflow/destination inflow reconciliation "+key)
   cr.append({"task_key":key,"rep":rep,"mechanism":"label_noise","planned_rate":rate,"realized_rate":float(meta["realized_rate"])})
   for o in range(7):
    for n in range(7):tr.append({"task_key":key,"rep":rep,"mechanism":"label_noise","rate":rate,"old_class":o,"new_class":n,"transition_count":int(matrix[o,n])})
   inputs["tasks"][key]={"registry_record_sha256":regsha,"metadata_json_sha256":sha(mp),"data_npz_sha256":sha(dp),"audit_npz_sha256":sha(ap),"validated_data_npz_sha256":val["files"]["data.npz"],"role_npz_sha256":rh,"fit_ids_raw_sha256":idsha(ids0),"original_class_counts":counts,"final_class_counts":final.astype(int).tolist(),"mask_rows":mexp,"changed_rows":int(np.sum(old!=new)),"transition_sum":int(matrix.sum()),"transition_diagonal_sum":int(np.diag(matrix).sum()),"source_outflow":outflow.astype(int).tolist(),"destination_inflow":inflow.astype(int).tolist()}
   cellchecks.append({"task_key":key,"rep":rep,"rate":rate,"status":"validated_successful","fit_rows":80000,"affected_rows":mexp,"nested_id_count":len(affected),"all_selected_changed":True,"unselected_unchanged":True,"other_roles_touched":False,"transition_matrix_exact":True,"final_histogram_reconciled":True})
  sets.sort(key=lambda x:x[0])
  if len(sets)!=3 or not sets[0][1]<sets[1][1]<sets[2][1] or [len(x[1]) for x in sets]!=[4000,8000,16000]:raise ValueError("nested 5/10/20% affected IDs fail rep "+str(rep))
  nested[str(rep)]={"affected_ids_by_rate":{"0.05":4000,"0.1":8000,"0.2":16000},"strictly_nested":True}
  if sha(rolep)!=rolehashes[str(rep)]:raise ValueError("role cache changed during audit rep "+str(rep))
 db.close()
 rates=reporting._label_noise_source_class_rates(cr,tr,rolecounts)
 if len(rates)!=63:raise ValueError("live helper did not return 63 class-rate rows")
 trans={(x["task_key"],int(x["old_class"]),int(x["new_class"])):int(x["transition_count"]) for x in tr}
 for x in rates:
  key=x["task_key"];c=int(x["source_class_id"]);den=rolecounts[str(x["rep"])][c]
  changed=sum(trans[(key,c,j)] for j in range(7) if j!=c);affected=sum(trans[(key,c,j)] for j in range(7))
  if (x["original_source_class_count"],x["affected_source_class_count"],x["changed_label_count"])!=(den,affected,changed):raise ValueError("rate helper denominator/numerator mismatch "+key+"/class"+str(c))
  if den<=0 or x["rate_status"]!="available" or not math.isclose(float(x["realized_source_class_corruption_rate"]),changed/den,rel_tol=0,abs_tol=1e-15):raise ValueError("source class rate is not off-diagonal/full-source-support "+key+"/class"+str(c))
 mem1=available();ru=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
 if mem1<9*GIB or ru>512*1024 or resource.getrlimit(resource.RLIMIT_AS)[0]>L:raise MemoryError("RAM/RLIMIT gate failed before publishing")
 if any(sha(R/"cache/roles"/("rep_"+str(r)+".npz"))!=rolehashes[str(r)] for r in (1,2,3)):raise ValueError("role cache changed before CSV publication")
 temp=OUT/".rates.csv.tmp"
 if temp.exists():raise FileExistsError("unexpected previous temp CSV")
 reporting._write_csv(temp,rates,fields=FIELDS);body=temp.read_bytes();outsha=hashlib.sha256(body).hexdigest()
 if CSVOUT.exists():
  if CSVOUT.read_bytes()!=body:raise FileExistsError("canonical CSV exists with different bytes; refusing overwrite")
  temp.unlink();state="existing_identical_preserved"
 else:os.replace(temp,CSVOUT);state="created_atomically"
 report={"schema":"e5-label-noise-realization-rate-audit/1","status":"PASS","observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"planned_cells":9,"validated_successful_cells":9,"rates":3,"repetitions":3,"source_class_rows":len(rates),"expected_rows":63,"label_order":LABELS,"cells":cellchecks,"nested_masks":nested,"input_hashes":inputs,"role_integrity":{"role_cache_sha256_matches_cache_manifest":True,"fit_id_hashes_match_cache_manifest":True,"role_files_unchanged_during_audit":True,"fit_n_per_rep":80000,"fit_tune_cal_disjoint":True},"rate_definition":{"numerator":"off-diagonal transitions out of source class","denominator":"full original y_fit count for that source class","formula":"changed_label_count / original_source_class_count","affected_source_class_count_is_not_the_denominator":True},"transition_checks":{"actual_rows_reconstructed":True,"audit_metadata_matrices_match":True,"matrix_diagonals_zero":True,"all_selected_labels_change_to_another_six_class":True,"all_unselected_labels_unchanged":True,"final_counts_equal_original_minus_outflow_plus_inflow":True,"other_roles_touched_false":True},"reporting":{"source_sha256":REPORT_SHA,"install_receipt_sha256":INSTALL_SHA,"helper_used":"reporting._label_noise_source_class_rates","no_pair_membership_or_metric_data_changed":True},"output":{"path":str(CSVOUT),"state":state,"sha256":sha(CSVOUT),"bytes":CSVOUT.stat().st_size,"rows":len(rates),"fields":FIELDS},"resources":{"available_ram_start_bytes":mem0,"available_ram_end_bytes":mem1,"safety_floor_bytes":9*GIB,"max_address_space_bytes":resource.getrlimit(resource.RLIMIT_AS)[0],"max_rss_kib":ru,"numeric_threads":1,"nice":os.nice(0)},"limitations":["Only y labels, IDs, metadata, and specified audit arrays were loaded; X/test features, models/pipelines, predictions, fitting, inference, and calibration were untouched.","Global calibration-q replay remains pending; this audit makes no global-q claim."],"repro_script":"audit_e5_label_noise.py","repro_script_sha256":sha(Path(__file__))}
 auditpath=OUT/"E5_LABEL_NOISE_REALIZATION_AUDIT_20261027.json";tm=OUT/".audit.json.tmp"
 if tm.exists():raise FileExistsError("unexpected previous audit temp")
 tm.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
 with tm.open("rb") as f:os.fsync(f.fileno())
 os.replace(tm,auditpath)
 print(json.dumps({"status":"PASS","audit_json":str(auditpath),"audit_sha256":sha(auditpath),"canonical_csv":str(CSVOUT),"canonical_csv_sha256":sha(CSVOUT),"rows":len(rates),"validated_cells":len(cellchecks),"max_rss_kib":ru,"available_ram_start":mem0,"available_ram_end":mem1},indent=2))
if __name__=="__main__":main()
