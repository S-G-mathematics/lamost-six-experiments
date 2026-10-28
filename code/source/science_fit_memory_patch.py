#!/usr/bin/env python3
"""Prepare-only fit-memory patch; apply only after the controller confirms quiescence."""
from __future__ import annotations
import argparse, hashlib, os, shutil, subprocess, sys, tempfile, uuid
from pathlib import Path

HERE=Path(__file__).resolve().parent
TARGET=HERE/"science.py"
EXPECTED_BASE_SHA="845a4477c55a6d9dfb9ce14ae2f34e68db25fac3501715ac7aaf895b7dfd5a00"

OLD_FIT_BLOCK='''    model=mod.make_model(method,params,seed,n_jobs=1)
    t=time.monotonic(); _train_model(model,Xt,y,sw); duration=time.monotonic()-t
    pipeline={"model":model,"imputer":imputer,"scaler":scaler,"params":params,"seed":seed,"method":method,
      "training_ids_sha256":hashlib.sha256(np.ascontiguousarray(ids).tobytes()).hexdigest(),
      "training_X_sha256":hashlib.sha256(np.ascontiguousarray(X).tobytes()).hexdigest(),
      "training_y_sha256":hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest(),
      "feature_order":["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"],
      "training_rows":len(y),"class_counts":counts.tolist(),"train_path":str(task.get("train_path","role_cache"))}
    temp_pipeline=out/"pipeline.joblib.tmp"
    joblib.dump(pipeline,temp_pipeline,compress=3)
    os.replace(temp_pipeline,out/"pipeline.joblib")
    check=joblib.load(out/"pipeline.joblib")
    if check["model"].__class__!=model.__class__: raise ValueError("pipeline reload validation failed")
    source_path=Path(task["train_path"]) if task.get("train_path") else Path(runtime)/"cache"/"roles"/f"rep_{int(task['rep'])}.npz"
    return {"status":"success","params":params,"seed":seed,"training_rows":len(y),"class_counts":counts.tolist(),"fit_seconds":duration,"pipeline_sha256":_sha(out/"pipeline.joblib"),"training_ids_sha256":pipeline["training_ids_sha256"],"source_sha256":_sha(source_path)}
'''
NEW_FIT_BLOCK='''    model=mod.make_model(method,params,seed,n_jobs=1)
    fit_started=time.monotonic()
    _train_model(model,Xt,y,sw)
    duration=time.monotonic()-fit_started
    model_type=f"{type(model).__module__}.{type(model).__qualname__}"
    fit_result={"status":"success","params":params,"seed":seed,"training_rows":len(y),
      "class_counts":counts.tolist(),"fit_seconds":duration,
      "training_ids_sha256":hashlib.sha256(np.ascontiguousarray(ids).tobytes()).hexdigest(),
      "training_X_sha256":hashlib.sha256(np.ascontiguousarray(X).tobytes()).hexdigest(),
      "training_y_sha256":hashlib.sha256(np.ascontiguousarray(y).tobytes()).hexdigest()}
    pipeline={"model":model,"imputer":imputer,"scaler":scaler,"params":params,"seed":seed,"method":method,
      "training_ids_sha256":fit_result["training_ids_sha256"],
      "training_X_sha256":fit_result["training_X_sha256"],
      "training_y_sha256":fit_result["training_y_sha256"],
      "feature_order":["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"],
      "training_rows":len(y),"class_counts":counts.tolist(),"train_path":str(task.get("train_path","role_cache"))}
    _json(out/"fit_progress.json",{"stage":"fitted","recorded_at":_now(),"fit_result":fit_result,
      "expected_model_type":model_type,"params":params,"seed":seed})
    temp_pipeline=out/("pipeline.joblib."+uuid.uuid4().hex+".tmp")
    joblib.dump(pipeline,temp_pipeline,compress=3)
    os.replace(temp_pipeline,out/"pipeline.joblib")
    fit_result["pipeline_sha256"]=_sha(out/"pipeline.joblib")
    _json(out/"fit_progress.json",{"stage":"pipeline_serialized","recorded_at":_now(),"fit_result":fit_result,
      "expected_model_type":model_type,"params":params,"seed":seed})
    # The serialized candidate is complete. Release the fitted in-memory forest and
    # large fitting arrays before loading the artifact for its one-copy validation.
    del pipeline,model,Xt,X,y,ids,sw
    import gc
    gc.collect()
    check=joblib.load(out/"pipeline.joblib")
    required={"model","imputer","scaler","params","seed","method","training_ids_sha256",
      "training_X_sha256","training_y_sha256","feature_order","training_rows","class_counts"}
    missing=sorted(required-set(check))
    observed_type=f"{type(check['model']).__module__}.{type(check['model']).__qualname__}"
    if missing: raise ValueError(f"pipeline reload validation missing fields: {missing}")
    if observed_type!=model_type: raise ValueError(f"pipeline reload validation model type mismatch: {observed_type} != {model_type}")
    if check["params"]!=params or int(check["seed"])!=seed: raise ValueError("pipeline reload validation params/seed mismatch")
    if int(check["training_rows"])!=fit_result["training_rows"] or check["class_counts"]!=fit_result["class_counts"]:
        raise ValueError("pipeline reload validation training metadata mismatch")
    del check
    gc.collect()
    _json(out/"fit_progress.json",{"stage":"pipeline_validated","recorded_at":_now(),"fit_result":fit_result,
      "expected_model_type":model_type,"params":params,"seed":seed})
    source_path=Path(task["train_path"]) if task.get("train_path") else Path(runtime)/"cache"/"roles"/f"rep_{int(task['rep'])}.npz"
    fit_result["source_sha256"]=_sha(source_path)
    return fit_result
'''
OLD_PUBLICATION='''            _atomic_copy(attempt/"pipeline.joblib",out/"pipeline.joblib",prefer_link=True)
'''
NEW_PUBLICATION='''            _atomic_copy(attempt/"pipeline.joblib",out/"pipeline.joblib",prefer_link=True)
            _json(attempt/"fit_publication.json",{"stage":"validated_publication","attempt_id":aid,
              "task_sha256":taskhash,"pipeline_sha256":_sha(out/"pipeline.joblib"),
              "published_path":str(out/"pipeline.joblib"),"recorded_at":_now()})
            _json(out/"fit_publication.json",{"stage":"validated_publication","attempt_id":aid,
              "task_sha256":taskhash,"pipeline_sha256":_sha(out/"pipeline.joblib"),
              "published_path":str(out/"pipeline.joblib"),"recorded_at":_now()})
'''

ENGINEERING_TEST='''import importlib.util, json, sys
from pathlib import Path
import numpy as np
import joblib

SRC=Path(__file__).resolve().parents[1]/"source"
sys.path.insert(0,str(SRC))
import science as patched

spec=importlib.util.spec_from_file_location("science_baseline",SRC/"science_baseline.py")
baseline=importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)

def test_fit_memory_patch_preserves_tiny_rf_model_predictions_and_records_stages(tmp_path,monkeypatch):
    rng=np.random.default_rng(4005)
    runtime=tmp_path/"runtime"; roles=runtime/"cache"/"roles"; roles.mkdir(parents=True)
    xs=[]; ys=[]; ids=[]
    for c in range(7):
        xs.append(rng.normal(loc=c*.7,scale=.5,size=(12,6)))
        ys.extend([c]*12); ids.extend(range(c*12,(c+1)*12))
    X=np.vstack(xs); y=np.asarray(ys,dtype=np.int8); ids=np.asarray(ids,dtype=np.int64)
    np.savez(roles/"rep_0.npz",X_fit=X,y_fit=y,fit_ids=ids,
      X_tune=X,y_tune=y,tuning_ids=ids,X_cal=X,y_cal=y,calibration_ids=ids)
    params={"n_estimators":8,"max_depth":4,"min_samples_leaf":1,"max_features":"sqrt"}
    task={"key":"memory-fixture/random_forest","kind":"fit","experiment":"fixture","rep":0,
      "method":"random_forest","seed":112,"params":params}
    baseline_out=tmp_path/"baseline"; baseline_out.mkdir()
    base_result=baseline.worker({"runtime":str(runtime),"task":task,"phase":"final_fit","out":str(baseline_out),"params":params})
    selection=tmp_path/"selection.json"; selection.write_text(json.dumps({"selected_params":params}))
    def tiny_phase(runtime_arg,task_arg,phase,out,params=None,**kwargs):
        return patched.worker({"runtime":str(runtime_arg),"task":task_arg,"phase":phase,"out":str(out),"params":params})
    monkeypatch.setattr(patched,"_run_phase",tiny_phase)
    new_result=patched.execute({**task,"selection_source":str(selection)},runtime)
    assert new_result["status"]=="successful",new_result
    base=joblib.load(baseline_out/"pipeline.joblib")
    new=joblib.load(runtime/"artifacts"/"memory-fixture"/"random_forest"/"pipeline.joblib")
    assert base["params"]==new["params"]==params and base["seed"]==new["seed"]==112
    assert base["model"].__class__ is new["model"].__class__
    assert base["training_ids_sha256"]==new["training_ids_sha256"]
    assert base["training_X_sha256"]==new["training_X_sha256"]
    assert base["training_y_sha256"]==new["training_y_sha256"]
    assert np.array_equal(base["imputer"].statistics_,new["imputer"].statistics_)
    assert np.array_equal(base["scaler"].mean_,new["scaler"].mean_)
    assert np.array_equal(base["scaler"].scale_,new["scaler"].scale_)
    p0=baseline._scores(base["model"],base["scaler"].transform(base["imputer"].transform(X)))
    p1=patched._scores(new["model"],new["scaler"].transform(new["imputer"].transform(X)))
    assert np.array_equal(p0,p1)
    progress=json.loads((runtime/"artifacts"/"memory-fixture"/"random_forest"/"attempts"/new_result["attempt_id"]/"fit_progress.json").read_text())
    assert progress["stage"]=="pipeline_validated"
    publication=json.loads((runtime/"artifacts"/"memory-fixture"/"random_forest"/"fit_publication.json").read_text())
    assert publication["stage"]=="validated_publication"
'''

def sha_bytes(data): return hashlib.sha256(data).hexdigest()
def apply_to_text(text):
    if sha_bytes(text.encode())!=EXPECTED_BASE_SHA:
        raise RuntimeError("active science.py is not the reviewed support-diagnostics base "+EXPECTED_BASE_SHA)
    if text.count(OLD_FIT_BLOCK)!=1: raise RuntimeError("expected one fitted-pipeline validation block")
    text=text.replace(OLD_FIT_BLOCK,NEW_FIT_BLOCK)
    if text.count(OLD_PUBLICATION)!=1: raise RuntimeError("expected one final pipeline publication call")
    text=text.replace(OLD_PUBLICATION,NEW_PUBLICATION)
    compile(text,"science.py","exec")
    return text

def run_selftest(original):
    patched=apply_to_text(original)
    with tempfile.TemporaryDirectory(prefix="lamost-fit-memory-patch-") as td:
        root=Path(td); source=root/"source"; tests=root/"tests"; source.mkdir(); tests.mkdir()
        (source/"science.py").write_text(patched)
        (source/"science_baseline.py").write_text(original)
        shutil.copy2(HERE/"phase_worker.py",source/"phase_worker.py")
        shutil.copy2(HERE.parent/"tests"/"test_science.py",tests/"test_science.py")
        (tests/"test_fit_memory_patch.py").write_text(ENGINEERING_TEST)
        env=os.environ.copy(); env["PYTHONPATH"]=str(source)+os.pathsep+env.get("PYTHONPATH","")
        proc=subprocess.run([sys.executable,"-m","pytest","-q",str(tests)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if proc.returncode: raise RuntimeError("temporary engine tests failed:\\n"+proc.stdout)
        return patched,proc.stdout.strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--apply",action="store_true",help="only after worker and controller quiescence")
    args=parser.parse_args()
    original=TARGET.read_text()
    if args.self_test:
        patched,output=run_selftest(original); print(output)
        print("temporary tiny-RF comparison passed; before="+sha_bytes(original.encode())+"; after="+sha_bytes(patched.encode()))
        return
    updated=apply_to_text(original)
    if not args.apply:
        print("dry run; before="+sha_bytes(original.encode())+"; proposed after="+sha_bytes(updated.encode()))
        print("No active source changed.")
        return
    backup=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".pre-fit-memory")
    backup.write_text(original)
    temp=TARGET.with_name(TARGET.name+"."+uuid.uuid4().hex+".tmp")
    temp.write_text(updated); os.replace(temp,TARGET)
    print(f"applied after quiescence; backup={backup}; before={sha_bytes(original.encode())}; after={sha_bytes(updated.encode())}")

if __name__=="__main__": main()
