#!/usr/bin/env python3
"""Read-only validation of a saved final-fit pipeline; performs no fit or prediction."""
from __future__ import annotations
import argparse, hashlib, json, os
from pathlib import Path
import numpy as np
import joblib

FEATURE_ORDER=["mag_ps_g","mag_ps_r","mag_ps_i","mag_ps_z","mag_ps_y","gaia_g_mean_mag"]

def file_sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def array_sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def report_check(checks,name,ok,observed=None,expected=None,detail=None):
    checks.append({"name":name,"status":"pass" if ok else "mismatch","observed":observed,"expected":expected,"detail":detail})
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pipeline",required=True)
    ap.add_argument("--task-json",required=True,help="task record or phase config containing task")
    ap.add_argument("--train-npz",required=True)
    ap.add_argument("--selection-json",required=True)
    ap.add_argument("--output-json",required=True)
    args=ap.parse_args()
    path=Path(args.pipeline); task_obj=json.loads(Path(args.task_json).read_text())
    task=task_obj.get("task",task_obj)
    selection=json.loads(Path(args.selection_json).read_text())
    selected=selection.get("selected_params",selection.get("params"))
    with np.load(args.train_npz,allow_pickle=False) as z:
        X=np.asarray(z["X"],dtype=np.float64); y=np.asarray(z["y"],dtype=np.int64)
        ids=np.asarray(z["ids"]) if "ids" in z else np.arange(len(y),dtype=np.int64)
        sample_weight=np.asarray(z["sample_weight"],dtype=np.float64) if "sample_weight" in z else None
    pipe=joblib.load(path)
    checks=[]
    report_check(checks,"pipeline_file_sha256",True,file_sha(path),None)
    report_check(checks,"selection_params",pipe.get("params")==selected,pipe.get("params"),selected)
    report_check(checks,"final_seed",int(pipe.get("seed",-1))==int(task.get("seed",-2)),pipe.get("seed"),task.get("seed"))
    report_check(checks,"method",pipe.get("method")==task.get("method"),pipe.get("method"),task.get("method"))
    report_check(checks,"training_rows",pipe.get("training_rows")==len(y),pipe.get("training_rows"),len(y))
    report_check(checks,"class_counts",pipe.get("class_counts")==np.bincount(y,minlength=7).tolist(),pipe.get("class_counts"),np.bincount(y,minlength=7).tolist())
    id_hash=array_sha(ids); x_hash=array_sha(X); y_hash=array_sha(y)
    report_check(checks,"training_ids_sha256",pipe.get("training_ids_sha256")==id_hash,pipe.get("training_ids_sha256"),id_hash)
    if pipe.get("training_X_sha256") is None:
        checks.append({"name":"training_X_sha256","status":"unrecorded","observed":None,"expected":x_hash,"detail":"content binding is not recorded in this historical pipeline"})
    else:
        report_check(checks,"training_X_sha256",pipe.get("training_X_sha256")==x_hash,pipe.get("training_X_sha256"),x_hash)
    if pipe.get("training_y_sha256") is None:
        checks.append({"name":"training_y_sha256","status":"unrecorded","observed":None,"expected":y_hash,"detail":"content binding is not recorded in this historical pipeline"})
    else:
        report_check(checks,"training_y_sha256",pipe.get("training_y_sha256")==y_hash,pipe.get("training_y_sha256"),y_hash)
    if pipe.get("feature_order") is not None:
        report_check(checks,"feature_order",pipe["feature_order"]==FEATURE_ORDER,pipe["feature_order"],FEATURE_ORDER)
    else:
        checks.append({"name":"feature_order","status":"unrecorded","observed":None,"expected":FEATURE_ORDER})
    expected_train=task.get("train_path")
    if expected_train is not None:
        observed_path=pipe.get("train_path")
        same_path=(Path(observed_path).resolve()==Path(expected_train).resolve()) if observed_path else False
        report_check(checks,"train_path",same_path,observed_path,expected_train)
    # Recompute only deterministic preprocessing summaries from the exact saved fit NPZ; no estimator fit/inference.
    median=np.nanmedian(X,axis=0)
    imputer=pipe["imputer"]; scaler=pipe["scaler"]
    report_check(checks,"median_imputer",np.allclose(imputer.statistics_,median,rtol=1e-8,atol=1e-10,equal_nan=True),imputer.statistics_.tolist(),median.tolist())
    Ximp=np.where(np.isnan(X),median[None,:],X)
    means=Ximp.mean(axis=0); scales=Ximp.std(axis=0,ddof=0); scales[scales==0]=1.0
    report_check(checks,"standard_scaler_mean",np.allclose(scaler.mean_,means,rtol=1e-8,atol=1e-10),scaler.mean_.tolist(),means.tolist())
    report_check(checks,"standard_scaler_scale",np.allclose(scaler.scale_,scales,rtol=1e-8,atol=1e-10),scaler.scale_.tolist(),scales.tolist())
    model=pipe["model"]; estimator=getattr(model,"estimator",None)
    if estimator is not None and task.get("method")=="random_forest":
        checks.extend([
          {"name":"forest_n_estimators","status":"pass" if estimator.n_estimators==selected["n_estimators"] else "mismatch","observed":estimator.n_estimators,"expected":selected["n_estimators"]},
          {"name":"forest_max_depth","status":"pass" if estimator.max_depth==selected["max_depth"] else "mismatch","observed":estimator.max_depth,"expected":selected["max_depth"]},
          {"name":"forest_min_samples_leaf","status":"pass" if estimator.min_samples_leaf==selected["min_samples_leaf"] else "mismatch","observed":estimator.min_samples_leaf,"expected":selected["min_samples_leaf"]},
          {"name":"forest_max_features","status":"pass" if estimator.max_features==selected["max_features"] else "mismatch","observed":estimator.max_features,"expected":selected["max_features"]},
          {"name":"forest_random_state","status":"pass" if estimator.random_state==int(task["seed"]) else "mismatch","observed":estimator.random_state,"expected":int(task["seed"])},
          {"name":"forest_classes_order","status":"pass" if np.array_equal(np.asarray(estimator.classes_),np.arange(7)) else "mismatch","observed":np.asarray(estimator.classes_).tolist(),"expected":list(range(7))},
          {"name":"forest_fitted_estimators","status":"pass" if len(estimator.estimators_)==selected["n_estimators"] else "mismatch","observed":len(estimator.estimators_),"expected":selected["n_estimators"]},
          {"name":"forest_n_features_in","status":"pass" if estimator.n_features_in_==6 else "mismatch","observed":estimator.n_features_in_,"expected":6},
        ])
    else:
        checks.append({"name":"estimator_configuration","status":"unavailable","observed":type(model).__name__,"expected":task.get("method")})
    statuses=[x["status"] for x in checks]
    result={"pipeline":str(path),"pipeline_sha256":file_sha(path),"train_npz":str(Path(args.train_npz)),
      "train_npz_sha256":file_sha(args.train_npz),"task":task,"selected_params":selected,
      "training_rows":len(y),"class_counts":np.bincount(y,minlength=7).tolist(),
      "training_ids_sha256":id_hash,"training_X_sha256":x_hash,"training_y_sha256":y_hash,
      "sample_weight_present":sample_weight is not None,"checks":checks,
      "validation_status":"validated" if all(s=="pass" for s in statuses) else ("mismatch" if "mismatch" in statuses else "incomplete_provenance"),
      "scope":"metadata and deterministic preprocessing verification only; no fit, prediction, or scoring"}
    Path(args.output_json).write_text(json.dumps(result,sort_keys=True,indent=2,default=str))
    print(json.dumps({"validation_status":result["validation_status"],"failed":[c["name"] for c in checks if c["status"]=="mismatch"],"unrecorded":[c["name"] for c in checks if c["status"]=="unrecorded"]},indent=2))
    if result["validation_status"]=="mismatch": raise SystemExit(2)
if __name__=="__main__": main()
