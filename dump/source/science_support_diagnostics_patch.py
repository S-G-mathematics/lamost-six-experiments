#!/usr/bin/env python3
"""Prepare-only support-diagnostics patch. Apply after maintenance patch is installed and workers are quiescent."""
from __future__ import annotations
import argparse, hashlib, importlib.util, os, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

HERE=Path(__file__).resolve().parent
TARGET=HERE/"science.py"
PRE_MAINT_SHA="0bcdd10b401fa7483464e4e41789d4d8fde6c3339f3af4613b9f36d4c4d7e7ad"
POST_MAINT_SHA="b27f03366bc3fde6b55682c950d12d30c8d9bc194c8a544e286e9c78522bd7ce"

OLD_CHUNKS='''def _chunks(model,X,size=50000):
    out=[]
    for i in range(0,len(X),size): out.append(_scores(model,X[i:i+size]))
    return np.concatenate(out,axis=0)
'''
NEW_CHUNKS=OLD_CHUNKS+'''def _chunks_with_support(model,X,size=50000):
    """Return unchanged score rows and the model's per-row invalid-support flags."""
    score_parts=[]; flag_parts=[]
    for i in range(0,len(X),size):
        block=X[i:i+size]
        scores=_scores(model,block)
        flags=getattr(model,"fallback_mask",None)
        if flags is None:
            flags=np.zeros(len(block),dtype=bool)
        else:
            flags=np.asarray(flags,dtype=bool)
            if flags.shape!=(len(block),):
                raise ValueError("model fallback_mask must have one bool per scored row")
        score_parts.append(scores); flag_parts.append(flags)
    if not score_parts: return np.empty((0,CLASSES),dtype=np.float64),np.empty(0,dtype=bool)
    return np.concatenate(score_parts,axis=0),np.concatenate(flag_parts,axis=0)
'''
OLD_CAL='''    scores=_chunks(model,pipe["scaler"].transform(pipe["imputer"].transform(Xcal)))
    threshold=conformal_threshold(scores,ycal,getattr(model,"score_kind","probability"),.1)
    return {"status":"success","threshold":float(threshold),"score_kind":getattr(model,"score_kind","probability"),"calibration_n":len(ycal),"fit_key":task["fit_key"],"pipeline_sha256":_sha(resolve_fit(runtime,task["fit_key"]))}
'''
NEW_CAL='''    scores,fallback=_chunks_with_support(model,pipe["scaler"].transform(pipe["imputer"].transform(Xcal)))
    threshold=conformal_threshold(scores,ycal,getattr(model,"score_kind","probability"),.1)
    return {"status":"success","threshold":float(threshold),"score_kind":getattr(model,"score_kind","probability"),"calibration_n":len(ycal),"calibration_fallback_count":int(fallback.sum()),"fit_key":task["fit_key"],"pipeline_sha256":_sha(resolve_fit(runtime,task["fit_key"]))}
'''
OLD_EVAL='''    chosen_threshold=payload.get("params",{}).get("threshold",payload.get("threshold"))
    if chosen_threshold is None:
        cal=_chunks(model,sc.transform(imp.transform(Xcal)))
        chosen_threshold=conformal_threshold(cal,ycal,getattr(model,"score_kind","probability"),.1)
    threshold=float(chosen_threshold)
    scores=_chunks(model,sc.transform(imp.transform(X)))
    ev=conformal_evaluate(scores,y,threshold,getattr(model,"score_kind","probability"))
    tmp=out/"test_outcomes.npz.tmp"
    with open(tmp,"wb") as f: np.savez_compressed(f,sample_id=ids,y_pred=ev["predictions"],set_mask=np.packbits(ev["sets"],axis=1,bitorder="little")[:,0],covered=ev["covered"],set_size=ev["set_sizes"])
'''
NEW_EVAL='''    phase_params=payload.get("params",{})
    chosen_threshold=phase_params.get("threshold",payload.get("threshold"))
    calibration_fallback_count=phase_params.get("calibration_fallback_count")
    if chosen_threshold is None:
        cal,cal_fallback=_chunks_with_support(model,sc.transform(imp.transform(Xcal)))
        chosen_threshold=conformal_threshold(cal,ycal,getattr(model,"score_kind","probability"),.1)
        calibration_fallback_count=int(cal_fallback.sum())
    if calibration_fallback_count is None: calibration_fallback_count=0
    threshold=float(chosen_threshold)
    scores,fallback=_chunks_with_support(model,sc.transform(imp.transform(X)))
    ev=conformal_evaluate(scores,y,threshold,getattr(model,"score_kind","probability"))
    per_class_fallback={int(c):{"n":int(np.sum(y==c)),"fallback_count":int(np.sum(fallback & (y==c)))} for c in range(CLASSES)}
    tmp=out/"test_outcomes.npz.tmp"
    with open(tmp,"wb") as f: np.savez_compressed(f,sample_id=ids,y_pred=ev["predictions"],set_mask=np.packbits(ev["sets"],axis=1,bitorder="little")[:,0],covered=ev["covered"],set_size=ev["set_sizes"],fallback_mask=fallback)
'''
OLD_EVAL_FIELDS='''    result.update({"confusion_matrix":confusion_matrix(y,ev["predictions"],labels=np.arange(7)).tolist(),"calibration_n":len(ycal),"test_n":len(y),"threshold":float(threshold),"score_kind":getattr(model,"score_kind","probability"),"fit_key":task["fit_key"],"pipeline_sha256":_sha(fit)})
'''
NEW_EVAL_FIELDS='''    result.update({"confusion_matrix":confusion_matrix(y,ev["predictions"],labels=np.arange(7)).tolist(),"calibration_n":len(ycal),"calibration_fallback_count":int(calibration_fallback_count),"test_n":len(y),"test_fallback_count":int(fallback.sum()),"test_fallback_per_class":per_class_fallback,"threshold":float(threshold),"score_kind":getattr(model,"score_kind","probability"),"fit_key":task["fit_key"],"pipeline_sha256":_sha(fit)})
'''
OLD_PASS_CAL='''            res=_run_phase(runtime,task,"evaluate",attempt,params={"threshold":calibration["threshold"]})
'''
NEW_PASS_CAL='''            res=_run_phase(runtime,task,"evaluate",attempt,params={"threshold":calibration["threshold"],"calibration_fallback_count":calibration.get("calibration_fallback_count",0)})
'''
OLD_PIPELINE='''    pipeline={"model":model,"imputer":imputer,"scaler":scaler,"params":params,"seed":seed,"method":method,
      "training_ids_sha256":hashlib.sha256(np.ascontiguousarray(ids).tobytes()).hexdigest(),
      "training_rows":len(y),"class_counts":counts.tolist(),"train_path":str(task.get("train_path","role_cache"))}
'''
NEW_PIPELINE='''    pipeline={"model":model,"imputer":imputer,"scaler":scaler,"params":params,"seed":seed,"method":method,
      "training_ids_sha256":hashlib.sha256(np.ascontiguousarray(ids).tobytes()).hexdigest(),
      "training_X_sha256":hashlib.sha256(np.ascontiguousarray(X).tobytes()).hexdigest(),
      "training_y_sha256":hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest(),
      "feature_order":["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"],
      "training_rows":len(y),"class_counts":counts.tolist(),"train_path":str(task.get("train_path","role_cache"))}
'''

SUPPORT_TEST='''import numpy as np
import science

class PosteriorWithFallback:
    score_kind="probability"
    def __init__(self): self.fallback_mask=None
    def score_matrix(self,X):
        labels=X[:,1].astype(int)
        self.fallback_mask=(X[:,0]<0)
        p=np.full((len(X),7),0.01,dtype=np.float64)
        p[np.arange(len(X)),labels]=0.94
        return p

def test_chunk_support_is_diagnostic_and_does_not_change_scores_or_conformal():
    model=PosteriorWithFallback()
    X=np.zeros((14,6),dtype=np.float64)
    X[:,1]=np.arange(14)%7
    X[[1,4,9],0]=-1
    y=X[:,1].astype(np.int64)
    expected_scores=science._chunks(model,X,size=3)
    science._project("support-fixture")
    scores,flags=science._chunks_with_support(model,X,size=3)
    assert np.array_equal(scores,expected_scores)
    assert flags.dtype==np.bool_ and int(flags.sum())==3
    from benchmark.evaluation import conformal_threshold,conformal_evaluate
    threshold_before=conformal_threshold(expected_scores,y,"probability",.1)
    threshold_after=conformal_threshold(scores,y,"probability",.1)
    result_before=conformal_evaluate(expected_scores,y,threshold_before,"probability")
    result_after=conformal_evaluate(scores,y,threshold_after,"probability")
    assert threshold_after==threshold_before
    assert result_after["balanced_accuracy"]==result_before["balanced_accuracy"]
    assert result_after["coverage"]==result_before["coverage"]
    assert result_after["set_size"]==result_before["set_size"]
'''

def _hash(text): return hashlib.sha256(text.encode()).hexdigest()

def _maintenance_base(text):
    if _hash(text)==POST_MAINT_SHA: return text
    if _hash(text)!=PRE_MAINT_SHA: raise RuntimeError("active science.py is neither the known pre-maintenance nor post-maintenance version")
    spec=importlib.util.spec_from_file_location("lamost_maintenance_patch",HERE/"science_maintenance_patch.py")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    base=mod.apply_to_text(text)
    if _hash(base)!=POST_MAINT_SHA: raise RuntimeError("maintenance patch output hash mismatch")
    return base

def apply_to_text(text):
    if _hash(text)!=POST_MAINT_SHA:
        raise RuntimeError("diagnostics patch requires the verified maintenance science.py SHA "+POST_MAINT_SHA)
    pairs=[
      (OLD_CHUNKS,NEW_CHUNKS,1,"support-preserving chunk scorer"),
      (OLD_CAL,NEW_CAL,1,"calibration support count"),
      (OLD_EVAL,NEW_EVAL,1,"test support mask/count"),
      (OLD_EVAL_FIELDS,NEW_EVAL_FIELDS,1,"support result fields"),
      (OLD_PASS_CAL,NEW_PASS_CAL,1,"calibration-to-evaluation handoff"),
      (OLD_PIPELINE,NEW_PIPELINE,1,"pipeline feature/data provenance"),
    ]
    for old,new,n,label in pairs:
        count=text.count(old)
        if count!=n: raise RuntimeError(f"{label}: expected {n} exact match, found {count}")
        text=text.replace(old,new)
    compile(text,"science.py","exec")
    return text

def _run_tests(clone,patched):
    source=clone/"source"; tests=clone/"tests"; source.mkdir(parents=True); tests.mkdir()
    (source/"science.py").write_text(patched)
    shutil.copy2(HERE/"phase_worker.py",source/"phase_worker.py")
    shutil.copy2(HERE.parent/"tests"/"test_science.py",tests/"test_science.py")
    (tests/"test_support_diagnostics.py").write_text(SUPPORT_TEST)
    env=os.environ.copy(); env["PYTHONPATH"]=str(source)+os.pathsep+env.get("PYTHONPATH","")
    proc=subprocess.run([sys.executable,"-m","pytest","-q",str(tests)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if proc.returncode: raise RuntimeError("temporary clone tests failed:\n"+proc.stdout)
    return proc.stdout.strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--apply",action="store_true",help="modify science.py after worker quiescence and verified maintenance patch")
    args=parser.parse_args()
    original=TARGET.read_text()
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix="lamost-support-diagnostics-") as td:
            clone=Path(td); base=_maintenance_base(original); patched=apply_to_text(base)
            output=_run_tests(clone,patched)
            print(output)
            print("temporary cloned-module support diagnostics self-test passed")
        return
    if args.apply:
        if _hash(original)!=POST_MAINT_SHA:
            raise SystemExit("refusing active edit: maintenance patch must be applied first and workers must be quiescent")
        updated=apply_to_text(original)
        backup=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".pre-support-diagnostics")
        backup.write_text(original)
        temp=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".tmp")
        temp.write_text(updated); os.replace(temp,TARGET)
        print(f"applied after maintenance; backup={backup}; before={POST_MAINT_SHA}; after={_hash(updated)}")
        return
    base=_maintenance_base(original)
    updated=apply_to_text(base)
    print(f"dry run; active SHA={_hash(original)}; post-maintenance SHA={POST_MAINT_SHA}; proposed support-patched SHA={_hash(updated)}")

if __name__=="__main__": main()
