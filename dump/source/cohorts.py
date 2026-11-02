"""E4 cohort/treatment and E5 fitting-only corruption transforms; no model fitting."""
from __future__ import annotations
import hashlib,json,math,os,tempfile
from pathlib import Path
import numpy as np
C=7
DEFAULTS={"E4":"implementation default: 80,000-row altered cohort, largest-remainder quotas, deterministic class prefixes",
"E5":"implementation default: 100,000-row development; nested 5%, 10%, 20% fitting-row masks"}

def _safe(k):
 import re
 k=str(k)
 if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",k) or any(x in {".",".."} for x in k.split("/")):
  raise ValueError("unsafe task key")
 return k
def _dig(a):
 a=np.ascontiguousarray(a); h=hashlib.sha256(); h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.view(np.uint8)); return h.hexdigest()
def _atomic_npz(p,**a):
 p.parent.mkdir(parents=True,exist_ok=True); fd,n=tempfile.mkstemp(dir=p.parent,suffix=".tmp"); os.close(fd)
 try:
  with open(n,"wb") as f: np.savez_compressed(f,**a); f.flush(); os.fsync(f.fileno())
  os.replace(n,p)
 finally:
  if os.path.exists(n): os.unlink(n)
def _json(p,d):
 p.parent.mkdir(parents=True,exist_ok=True); n=str(p)+f".tmp.{os.getpid()}"
 with open(n,"w") as f: json.dump(d,f,indent=2,sort_keys=True,allow_nan=False); f.flush(); os.fsync(f.fileno())
 os.replace(n,p)
def _role(rt,r):
 p=rt/"cache/roles"/f"rep_{r}.npz"
 if not p.exists(): raise FileNotFoundError(p)
 with np.load(p,allow_pickle=False) as z: d={k:z[k] for k in z.files}
 req=("X_fit","y_fit","fit_ids","X_tune","y_tune","tuning_ids","X_cal","y_cal","calibration_ids")
 if any(k not in d for k in req): raise ValueError(f"{p} missing role keys")
 for x,y,i in (("X_fit","y_fit","fit_ids"),("X_tune","y_tune","tuning_ids"),("X_cal","y_cal","calibration_ids")):
  if d[x].ndim!=2 or d[y].ndim!=1 or d[i].ndim!=1 or not(len(d[x])==len(d[y])==len(d[i])): raise ValueError("role shapes invalid")
 ids=np.concatenate([d["fit_ids"],d["tuning_ids"],d["calibration_ids"]])
 if len(np.unique(ids))!=len(ids): raise ValueError("fit/tune/cal IDs overlap")
 return d
def _dev(rt):
 a=[np.load(rt/"cache"/f"development_{x}.npy",mmap_mode="r",allow_pickle=False) for x in ("X","y","ids")]
 X,y,ids=a
 if X.ndim!=2 or y.ndim!=1 or ids.ndim!=1 or not(len(X)==len(y)==len(ids)): raise ValueError("development map shapes invalid")
 if np.any(ids[1:]<ids[:-1]) or len(np.unique(ids))!=len(ids): raise ValueError("development IDs must be unique and sorted")
 return X,y,ids
def _half(num,den): return (2*num+den)//(2*den)
def added_count(orig_n,N,n):
 den=N-orig_n; num=N*(orig_n-n)
 if N<=0 or not 0<=orig_n<N or n<0: raise ValueError("invalid shares")
 return 0 if num<=0 else _half(num,den)
def _largest(total,w):
 w=np.asarray(w,float)
 if np.any(w<0) or w.sum()<=0: raise ValueError("invalid quota weights")
 e=total*w/w.sum(); q=np.floor(e).astype(int); rem=total-int(q.sum())
 if rem: q[np.lexsort((np.arange(len(w)),-(e-q)))[:rem]]+=1
 return q
def _put(rt,task,kind,arrays,meta):
 arrays["X"]=np.asarray(arrays["X"],dtype=np.float64); arrays["y"]=np.asarray(arrays["y"],dtype=np.int64)
 if len(arrays["X"])!=len(arrays["y"]): raise ValueError("X/y length mismatch")
 root=(rt/"artifacts").resolve(); out=(root/_safe(task.get("key",task.get("task_key","")))).resolve()
 if root not in out.parents: raise ValueError("task key escapes artifact root")
 meta.update(task_key=_safe(task.get("key",task.get("task_key",""))),kind=kind)
 _atomic_npz(out/"data.npz",**arrays); _json(out/"metadata.json",meta)
 return {"status":"successful","artifact_path":str(out),"metadata":meta}
def _load_art(rt,k):
 root=(rt/"artifacts").resolve(); p=(root/_safe(k)).resolve()
 if root not in p.parents: raise ValueError("artifact key escapes artifact root")
 with np.load(p/"data.npz",allow_pickle=False) as z: d={x:z[x] for x in z.files}
 meta=p/"metadata.json"
 if meta.exists():
  with open(meta) as f: m=json.load(f)
 else:
  result=p/"result.json"
  m={}
  if result.exists():
   with open(result) as f: m=json.load(f)
 return p,d,m

def _e4(task,rt):
 r=int(task["rep"]); t=int(task["target_class"]); ratio=float(task["ratio"]); N=int(task.get("N",80000))
 if t not in range(C) or ratio not in (.5,.1) or N!=80000: raise ValueError("E4 expects class 0..6, ratio .5/.1, N=80000")
 role=_role(rt,r); Xd,yd,idd=_dev(rt); yf=np.asarray(role["y_fit"],int); fit=np.asarray(role["fit_ids"])
 if len(yf)!=N: raise ValueError(f"fit size {len(yf)} != {N}")
 fc=np.bincount(yf,minlength=C)
 if np.any(fc==0): raise ValueError("original fitting cohort missing class")
 # Exclude all tune/cal IDs. For each class, saved fitting IDs retain their saved order;
 # eligible additional IDs share a deterministic permutation across target/severity conditions.
 reserved=np.concatenate([role["tuning_ids"],role["calibration_ids"]])
 pos=np.searchsorted(idd,fit)
 if np.any(pos>=len(idd)) or not np.array_equal(idd[pos],fit) or not np.array_equal(yd[pos],yf): raise ValueError("fit IDs/labels disagree with development cache")
 target_n=int(math.floor(ratio*fc[t]+.5)); w=fc.astype(float); w[t]=0
 q=_largest(N-target_n,w); q[t]=target_n
 # Vectorized eligibility and one stable class grouping avoid a Python scan over the full pool per class.
 blocked=np.concatenate([reserved,fit])
 eligible=~np.isin(idd,blocked,assume_unique=False)
 extra_ids=np.asarray(idd[eligible]); extra_y=np.asarray(yd[eligible],dtype=np.int64)
 order=np.argsort(extra_y,kind="stable"); extra_ids=extra_ids[order]; extra_y=extra_y[order]
 bounds=np.searchsorted(extra_y,np.arange(C+1),side="left")
 seq=[]
 for c in range(C):
  orig=fit[yf==c]; rng=np.random.default_rng(int(task["seed"])+1000003*r+9176*c)
  ex=extra_ids[bounds[c]:bounds[c+1]]
  if len(ex): ex=ex[rng.permutation(len(ex))]
  s=np.concatenate([orig,ex])
  if q[c]>len(s): return {"status":"unsupported","reason":"insufficient eligible non-test rows","class":c,"need":int(q[c]),"available":len(s)}
  seq.append(s[:q[c]])
 ids=np.sort(np.concatenate(seq)); p=np.searchsorted(idd,ids)
 if np.any(p>=len(idd)) or not np.array_equal(idd[p],ids): raise ValueError("selected IDs unavailable")
 X=np.asarray(Xd[p],dtype=np.float64); y=np.asarray(yd[p],dtype=np.int64); counts=np.bincount(y,minlength=C)
 if not np.array_equal(counts,q): raise ValueError("realized cohort histogram differs from quotas")
 add=added_count(int(fc[t]),N,int(q[t]))
 meta=dict(rep=r,target_class=t,ratio=ratio,N=N,source_fit_counts=fc.tolist(),original_share=float(fc[t]/N),
  planned_counts=q.tolist(),realized_counts=counts.tolist(),restore_added_count=add,seed=int(task["seed"]),
  ids_sha256=_dig(ids),tune_calibration_reserved=True,per_class_prefix_sampling=True,defaults=DEFAULTS["E4"],
  sample_weight_included=False,weighting_policy="none; weights are produced only by explicit weighted treatment")
 return _put(rt,task,"e4_cohort",{"X":X,"y":y,"ids":ids},meta)

def _treatment(task,rt):
 bp,d,m=_load_art(rt,task["cohort_key"]); X=np.asarray(d["X"],float); y=np.asarray(d["y"],int); ids=d.get("ids")
 t=int(m["target_class"]); counts=np.bincount(y,minlength=C); orig=np.asarray(m["source_fit_counts"],float); tr=task["treatment"]
 if tr=="weighted":
  w=(orig/orig.sum())/(counts/counts.sum()); sw=w[y]; sw/=sw.mean()
  a={"X":X,"y":y,"sample_weight":sw}
  if ids is not None:a["ids"]=ids
  return _put(rt,task,"e4_treatment",a,{"parent":str(bp),"treatment":tr,"counts":counts.tolist(),"added_count":0,"sample_weight_mean":float(sw.mean())})
 add=int(m["restore_added_count"]); wanted=counts.copy(); wanted[t]+=add; rng=np.random.default_rng(int(task.get("seed",m["seed"])))
 if tr=="ros":
  idx=np.flatnonzero(y==t)
  if not len(idx): return {"status":"unsupported","reason":"target class absent"}
  extra=rng.choice(idx,size=add,replace=True) if add else np.empty(0,int)
  a={"X":np.concatenate([X,X[extra]]),"y":np.concatenate([y,y[extra]])}
  if ids is not None:a["ids"]=np.concatenate([ids,ids[extra]])
  return _put(rt,task,"e4_treatment",a,{"parent":str(bp),"treatment":tr,"added_count":add,"counts_before":counts.tolist(),"counts_after":np.bincount(a["y"],minlength=C).tolist(),"source_reuse":True})
 if tr=="smote":
  n=int(counts[t])
  if n<2:return {"status":"unsupported","reason":"SMOTE requires at least two target rows"}
  try:
   from sklearn.impute import SimpleImputer
   from sklearn.preprocessing import StandardScaler
   from imblearn.over_sampling import SMOTE
  except ImportError as e:return {"status":"unavailable_dependency","reason":str(e)}
  k=min(5,n-1); imp=SimpleImputer(strategy="median"); xi=imp.fit_transform(X); scaler=StandardScaler(); xs=scaler.fit_transform(xi)
  strategy={c:int(wanted[c]) for c in range(C) if wanted[c]>counts[c]}
  try: xr,yr=SMOTE(sampling_strategy=strategy,random_state=int(task.get("seed",m["seed"])),k_neighbors=k).fit_resample(xs,y)
  except ValueError as e:return {"status":"unsupported","reason":f"SMOTE rejected cohort: {e}","neighbors":k}
  new=len(yr)-len(y)
  if new!=add or not np.array_equal(np.bincount(yr,minlength=C),wanted):raise ValueError("SMOTE histogram/count mismatch")
  gen=scaler.inverse_transform(xr[len(y):]) if new else np.empty((0,X.shape[1]))
  a={"X":np.concatenate([X,gen]),"y":np.concatenate([y,yr[len(y):]])}
  if ids is not None: a["ids"]=np.concatenate([ids,np.asarray(["smote:"+_safe(task.get("key",task.get("task_key")))+":"+str(i) for i in range(new)])])
  return _put(rt,task,"e4_treatment",a,{"parent":str(bp),"treatment":tr,"added_count":new,"counts_before":counts.tolist(),"counts_after":np.bincount(a["y"],minlength=C).tolist(),"sampling_strategy":strategy,"neighbors":k,"imputer_scaler_fit_on_altered_fit_only":True,"native_units":True})
 raise ValueError("treatment must be weighted, ros, or smote")

def _append(task,rt):
 bp,b,bm=_load_art(rt,task["cohort_key"]); gp,g,gm=_load_art(rt,task["generated_key"])
 X=np.asarray(b["X"],float); y=np.asarray(b["y"],int); xg=np.asarray(g["X"],float); yg=np.asarray(g["y"],int); t=int(task.get("target_class",bm["target_class"])); add=int(bm["restore_added_count"])
 if xg.ndim!=2 or xg.shape[1]!=X.shape[1] or len(xg)!=len(yg) or len(xg)!=add or np.any(yg!=t):raise ValueError("generated append rows invalid")
 xo=np.concatenate([X,xg]); yo=np.concatenate([y,yg]); bef=np.bincount(y,minlength=C); aft=np.bincount(yo,minlength=C); want=bef.copy(); want[t]+=add
 if not np.array_equal(aft,want):raise ValueError("generated restoration histogram mismatch")
 a={"X":xo,"y":yo}
 if "ids" in b: a["ids"]=np.concatenate([b["ids"],np.asarray(["generated:"+_safe(task.get("key",task.get("task_key")))+":"+str(i) for i in range(add)])])
 return _put(rt,task,"e4_append",a,{"parent":str(bp),"generated_artifact":str(gp),"generator_metadata":gm,"target_class":t,"added_count":add,"counts_before":bef.tolist(),"counts_after":aft.tolist()})

def _e5(task,rt):
 r=int(task["rep"]); mech=str(task["mechanism"]); rate=float(task["rate"])
 if mech not in {"feature_noise","missingness","label_noise"} or rate not in (.05,.10,.20):raise ValueError("invalid E5 mechanism/rate")
 role=_role(rt,r); X0=np.asarray(role["X_fit"],dtype=np.float64); y0=np.asarray(role["y_fit"],dtype=np.int64); ids=role["fit_ids"]; n=len(y0)
 if n!=int(task.get("N",80000)):raise ValueError(f"E5 fitting size {n}, expected {task.get('N',80000)}")
 rng=np.random.default_rng(int(task["seed"])+1000003*r+{"feature_noise":11,"missingness":23,"label_noise":37}[mech])
 perm=rng.permutation(n); m=int(math.floor(rate*n+.5)); rows=perm[:m]; X=X0.copy(); y=y0.copy()
 audit={"affected_row_indices":rows,"affected_ids":ids[rows],"affected_mask":np.isin(np.arange(n),rows)}
 meta={"rep":r,"mechanism":mech,"rate":rate,"affected_count":m,"fit_count":n,"realized_rate":m/n,"seed":int(task["seed"]),
  "affected_ids_sha256":_dig(ids[rows]),"other_roles_touched":False,"defaults":DEFAULTS["E5"]}
 if mech=="feature_noise":
  feat_all=rng.integers(0,X.shape[1],size=n); scales=[]; fallbacks=[]
  for j in range(X.shape[1]):
   v=X0[:,j]; v=v[np.isfinite(v)]
   if not len(v):raise ValueError(f"feature {j} has no finite fitting values")
   s=float((np.percentile(v,75)-np.percentile(v,25))/1.349)
   if not np.isfinite(s) or s<=0:s=float(np.std(v,ddof=0)); fallbacks.append("std_ddof0")
   if not np.isfinite(s) or s<=0:s=1e-12; fallbacks.append("floor_1e-12")
   scales.append(s)
  scale=np.asarray(scales); delta_all=rng.normal(0,scale[feat_all]); feat=feat_all[rows]; delta=delta_all[rows]; X[rows,feat]+=delta
  audit.update(feature_index=feat,perturbation=delta,per_feature_scale=scale); meta.update(feature_scale=scale.tolist(),scale_fallbacks=fallbacks,noise="zero mean Gaussian, one uniform feature per affected row")
 elif mech=="missingness":
  feat_all=rng.integers(0,X.shape[1],size=n); feat=feat_all[rows]; X[rows,feat]=np.nan; audit["feature_index"]=feat
  meta.update(missing_cells=m,missing_indicator=False,imputer="median fit only on incomplete fitting data")
 else:
  off_all=rng.integers(1,C,size=n); off=off_all[rows]; old=y[rows].copy(); new=(old+off)%C
  if np.any(old==new):raise AssertionError("selected label did not change")
  y[rows]=new; trans=np.zeros((C,C),int); np.add.at(trans,(old,new),1)
  audit.update(old_label=old,new_label=new,label_offset=off,transition_counts=trans)
  meta.update(changed_label_count=int(np.sum(old!=new)),transition_counts=trans.tolist(),relabeling="uniform among other six labels")
 root=(rt/"artifacts").resolve(); out=(root/_safe(task.get("key",task.get("task_key")))).resolve()
 if root not in out.parents: raise ValueError("task key escapes artifact root")
 _atomic_npz(out/"data.npz",X=X,y=y,ids=ids); _atomic_npz(out/"audit.npz",**audit); _json(out/"metadata.json",dict(meta,task_key=_safe(task.get("key",task.get("task_key"))),kind="e5_corruption"))
 return {"status":"successful","artifact_path":str(out),"metadata":meta}
def execute(task,runtime):
 rt=Path(runtime).expanduser().resolve()
 if not rt.is_dir():raise FileNotFoundError(rt)
 kind=task.get("kind")
 return {"e4_cohort":_e4,"e4_treatment":_treatment,"e4_append":_append,"e5_corruption":_e5}.get(kind,lambda *_:(_ for _ in ()).throw(ValueError(f"unsupported task kind {kind!r}")))(task,rt)
