from __future__ import annotations
import hashlib, json, math, os
from pathlib import Path
import numpy as np

MEMBERS=("gmm","copula","arf","kde","chow_liu")
SCHEMA="lamost-e6-member-comparisons/1"
SCORE_RULE="native normalized seven-class posterior; argmax prediction; probability nonconformity 1-p_true"
QUANTILE_RULE="finite-sample split-conformal: k=ceil((n_cal+1)*(1-alpha)); kth calibration nonconformity order statistic"

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def array_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def typed_array_sha(a):
    a=np.ascontiguousarray(a); h=hashlib.sha256()
    h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.view(np.uint8))
    return h.hexdigest()

def _close(a,b):
    try: return bool(np.isclose(float(a),float(b),rtol=0,atol=1e-10))
    except Exception: return False

def _metrics(scores,y,q):
    y=np.asarray(y,dtype=np.int64); s=np.asarray(scores,dtype=np.float64)
    if s.shape!=(len(y),7) or not np.isfinite(s).all(): raise ValueError("invalid posterior matrix")
    if np.any(s<0) or not np.allclose(s.sum(axis=1),1.,atol=1e-6,rtol=0): raise ValueError("posterior rows are not normalized probabilities")
    pred=np.argmax(s,axis=1).astype(np.int8)
    sets=(1.-s)<=float(q)
    sizes=sets.sum(axis=1).astype(np.int64)
    covered=sets[np.arange(len(y)),y]
    per={}
    for c in range(7):
        ix=y==c
        per[str(c)]={"n":int(ix.sum()),
          "recall":float(np.mean(pred[ix]==c)) if ix.any() else None,
          "coverage":float(np.mean(covered[ix])) if ix.any() else None,
          "set_size":float(np.mean(sizes[ix])) if ix.any() else None}
    if any(v["n"]==0 for v in per.values()): raise ValueError("test fixture/data lacks a class")
    return {"balanced_accuracy":float(np.mean([per[str(c)]["recall"] for c in range(7)])),
      "coverage":float(covered.mean()),"set_size":float(sizes.mean()),"per_class":per,
      "confusion_matrix":np.bincount(y*7+pred,minlength=49).reshape(7,7).tolist(),
      "predictions":pred,"sets":sets,"covered":covered,"set_sizes":sizes}

def _q(scores,y,alpha=.1):
    s=np.asarray(scores,dtype=np.float64); y=np.asarray(y,dtype=np.int64)
    if s.shape!=(len(y),7) or not np.isfinite(s).all() or np.any(s<0) or not np.allclose(s.sum(1),1.,atol=1e-6,rtol=0):
        raise ValueError("invalid calibration posterior")
    v=1.-s[np.arange(len(y)),y]
    k=int(math.ceil((len(y)+1)*(1-float(alpha))))
    if k>len(y): return float("inf")
    return float(np.partition(v,k-1)[k-1])

def _verify_cache(shared,stage,fingerprint):
    path=shared/(stage+".npz"); rp=shared/(stage+".receipt.json")
    if not path.is_file() or not rp.is_file(): raise ValueError(f"missing {stage} cache or receipt")
    rec=json.loads(rp.read_text())
    sig=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()[:24]
    fs=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with np.load(path,allow_pickle=False) as z:
        scores={m:np.asarray(z[m]) for m in MEMBERS}
    n=rec.get("row_count")
    if rec.get("schema_version")!="lamost-e6-posterior-cache-receipt/1" or rec.get("stage")!=stage:
        raise ValueError(f"{stage} receipt schema/stage mismatch")
    if rec.get("fingerprint")!=fingerprint or rec.get("fingerprint_sha256")!=fs:
        raise ValueError(f"{stage} receipt fingerprint mismatch")
    if rec.get("posterior_file_sha256")!=sha_file(path) or rec.get("member_order")!=list(MEMBERS):
        raise ValueError(f"{stage} receipt file/member identity mismatch")
    if rec.get("posterior_sha256")!={m:array_sha(scores[m]) for m in MEMBERS}:
        raise ValueError(f"{stage} receipt posterior array hash mismatch")
    if any(a.dtype!=np.float64 or a.shape!=(int(n),7) or not np.isfinite(a).all()
           or np.any(a<0) or not np.allclose(a.sum(1),1.,atol=1e-6,rtol=0) for a in scores.values()):
        raise ValueError(f"{stage} posterior shape/type/value invalid")
    return scores,sha_file(path),sha_file(rp)


def validation_input_paths(runtime,task):
    rt=Path(runtime).resolve(); out=rt/"artifacts"/str(task.get("key",""))
    paths=[out/"evaluation.json",out/"member_comparisons.json",out/"test_outcomes.npz",out/"tuning_posteriors.npz",
           rt/"cache"/"roles"/f"rep_{int(task.get('rep',0))}.npz",rt/"cache"/"test.npz"]
    try:
        ev=json.loads((out/"evaluation.json").read_text()); sig=ev.get("posterior_cache_key")
        if isinstance(sig,str) and len(sig)==24 and all(c in "0123456789abcdef" for c in sig):
            shared=rt/"cache"/"e6_posteriors"/f"rep_{int(task.get('rep',0))}"/sig
            for stage in ("tune","cal","test"): paths.extend([shared/(stage+".npz"),shared/(stage+".receipt.json")])
        side=json.loads((out/"member_comparisons.json").read_text())
        ledger=side.get("candidate_ledger_path")
        if isinstance(ledger,str) and ledger and Path(ledger).name==ledger: paths.append(out/ledger)
    except Exception: pass
    return [p for p in paths if p.is_file()]


def persist_native_nonconformity(runtime,identity_payload,vector,metadata):
    """Persist independently scored calibration nonconformities; never overwrites differing evidence."""
    rt=Path(runtime).resolve()
    identity=hashlib.sha256(json.dumps(identity_payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    dest=rt/"artifacts"/"calibration_replay"/"e6_member_native"/identity
    npz=dest/"nonconformity.npz"; meta=dest/"metadata.json"
    v=np.asarray(vector,dtype=np.float64)
    if v.ndim!=1 or not len(v) or not np.isfinite(v).all(): raise ValueError("native E6 nonconformity vector invalid")
    payload={"schema_version":"lamost-e6-native-member-calibration/1","identity":identity,
      "identity_payload":identity_payload,"nonconformity_sha256":typed_array_sha(v),
      "calibration_n":len(v),"threshold":float(metadata["threshold"]),
      "rank_k":int(metadata["rank_k"]),"score_kind":metadata["score_kind"],
      "nonconformity_rule":metadata["nonconformity_rule"],"alpha":float(metadata["alpha"]),
      "class_order":list(metadata["class_order"]),**metadata}
    if dest.exists():
        if not npz.is_file() or not meta.is_file(): raise ValueError("partial existing native E6 replay evidence")
        saved=json.loads(meta.read_text())
        payload["nonconformity_file_sha256"]=sha_file(npz)
        with np.load(npz,allow_pickle=False) as z: old=np.asarray(z["nonconformity"],dtype=np.float64)
        if saved!=payload or not np.array_equal(old,v): raise ValueError("existing native E6 replay evidence differs")
    else:
        dest.mkdir(parents=True,exist_ok=False)
        tmp=npz.with_name(npz.name+".tmp")
        with tmp.open("wb") as f:
            np.savez_compressed(f,nonconformity=v);f.flush();os.fsync(f.fileno())
        os.replace(tmp,npz)
        payload["nonconformity_file_sha256"]=sha_file(npz)
        atomic=meta.with_name(meta.name+".tmp")
        with atomic.open("w") as f:
            f.write(json.dumps(payload,sort_keys=True,indent=2)+"\n");f.flush();os.fsync(f.fileno())
        os.replace(atomic,meta)
    return {"identity":identity,"metadata_path":npz.parent.joinpath("metadata.json").relative_to(rt).as_posix(),
      "metadata_sha256":sha_file(meta),"nonconformity_path":npz.relative_to(rt).as_posix(),
      "nonconformity_file_sha256":sha_file(npz),"nonconformity_sha256":typed_array_sha(v),
      "calibration_n":len(v),"threshold":float(metadata["threshold"]),"rank_k":int(metadata["rank_k"])}

def validate_e6_v2_saved_outputs(runtime,task,evaluation,outcomes,*,expected_fit_rows=80000,expected_tune_rows=10000,expected_cal_rows=10000,expected_test_rows=500000):
    """Validate E6-v2 saved posterior-cache arithmetic; never loads a model or predicts."""
    rt=Path(runtime).resolve(); key=task.get("key")
    errors=[]; details={"status":"invalid","validation_basis":"saved_cache_arithmetic","evidence_paths":[str(p) for p in validation_input_paths(rt,task)]}
    def bad(code,msg): errors.append((code,str(msg)))
    try:
        if task.get("kind")!="ensemble" or str(task.get("experiment")) not in {"6"}: raise ValueError("not an E6 ensemble")
        if task.get("e6_protocol_version")!="E6-v2" or evaluation.get("e6_protocol_version")!="E6-v2": raise ValueError("E6-v2 marker missing")
        rep=int(task["rep"]); out=rt/"artifacts"/key
        if evaluation.get("member_comparisons_path")!="member_comparisons.json": raise ValueError("member comparison path is not canonical relative member")
        side=out/"member_comparisons.json"
        if not side.is_file() or sha_file(side)!=evaluation.get("member_comparisons_sha256"): raise ValueError("member comparison file SHA mismatch")
        doc=json.loads(side.read_text())
        if doc.get("schema_version")!=SCHEMA or doc.get("protocol_version")!="E6-v2": raise ValueError("member comparison schema/version mismatch")
        if doc.get("comparison_source_task_key")!=key or int(doc.get("rep",-1))!=rep or doc.get("mode")!=task.get("mode"): raise ValueError("member comparison task identity mismatch")
        if doc.get("member_order")!=list(MEMBERS) or set(doc.get("members",{}))!=set(MEMBERS): raise ValueError("member order/set mismatch")
        if doc.get("score_rule")!=SCORE_RULE or doc.get("quantile_rule")!=QUANTILE_RULE: raise ValueError("score/quantile convention mismatch")
        if doc.get("weights_frozen_before_calibration_and_test") is not True or not doc.get("weights_frozen_utc"): raise ValueError("weights freeze record missing")
        weights=np.asarray(doc.get("selected_weights"),dtype=np.float64)
        if weights.shape!=(5,) or not np.isfinite(weights).all() or np.any(weights<0) or not np.isclose(weights.sum(),1.,atol=1e-10,rtol=0): raise ValueError("selected weights invalid")
        if task.get("mode")=="equal" and not np.allclose(weights,np.full(5,.2),atol=1e-12,rtol=0): raise ValueError("equal-mode weights differ from 0.2")
        if not np.allclose(weights,np.asarray(evaluation.get("weights"),dtype=np.float64),atol=1e-12,rtol=0): raise ValueError("evaluation weights differ from frozen comparison weights")
        members=task.get("members",{})
        if set(members)!=set(MEMBERS): raise ValueError("task does not declare exactly five fits")
        if doc.get("posterior_fingerprint") is None: raise ValueError("posterior fingerprint missing")
        fp=doc["posterior_fingerprint"]
        cache_sig=hashlib.sha256(json.dumps(fp,sort_keys=True).encode()).hexdigest()[:24]
        if evaluation.get("posterior_cache_key")!=cache_sig: raise ValueError("posterior cache key differs from fingerprint")
        # Verify the exact saved roles/test identity used by the E6 fingerprint.
        role_path=rt/"cache"/"roles"/f"rep_{rep}.npz"; test_path=rt/"cache"/"test.npz"
        if not role_path.is_file() or not test_path.is_file(): raise ValueError("role/test cache missing")
        with np.load(role_path,allow_pickle=False) as z: role={k:np.asarray(z[k]) for k in ("X_tune","y_tune","X_cal","y_cal","fit_ids","tuning_ids","calibration_ids")}
        with np.load(test_path,allow_pickle=False) as z: test={k:np.asarray(z[k]) for k in ("X","y","ids")}
        ycal=np.asarray(role["y_cal"],dtype=np.int64); ytest=np.asarray(test["y"],dtype=np.int64)
        id_checks={
          "fit_ids_sha256":array_sha(role["fit_ids"]),"tuning_ids_sha256":array_sha(role["tuning_ids"]),
          "calibration_ids_sha256":array_sha(role["calibration_ids"]),"test_ids_sha256":array_sha(test["ids"]),
          "X_tune_sha256":array_sha(role["X_tune"]),"X_cal_sha256":array_sha(role["X_cal"]),
          "X_test_sha256":array_sha(test["X"]),"y_tune_sha256":array_sha(role["y_tune"]),
          "y_cal_sha256":array_sha(role["y_cal"]),"y_test_sha256":array_sha(test["y"])}
        for name,value in id_checks.items():
            if fp.get(name)!=value: raise ValueError(f"posterior fingerprint role/test mismatch: {name}")
        for name,value in id_checks.items():
            if name.endswith("_ids_sha256") and doc.get(name)!=value: raise ValueError(f"member role/test identity mismatch: {name}")
            if name in {"fit_ids_sha256","tuning_ids_sha256","calibration_ids_sha256","test_ids_sha256"} and evaluation.get(name)!=value:
                raise ValueError(f"evaluation role/test identity mismatch: {name}")
        if len(set(map(str,role["fit_ids"])))!=len(role["fit_ids"]) or len(set(map(str,role["tuning_ids"])))!=len(role["tuning_ids"]) or len(set(map(str,role["calibration_ids"])))!=len(role["calibration_ids"]): raise ValueError("duplicate role identities")
        if set(map(str,role["fit_ids"])) & set(map(str,role["tuning_ids"])) or set(map(str,role["fit_ids"])) & set(map(str,role["calibration_ids"])) or set(map(str,role["tuning_ids"])) & set(map(str,role["calibration_ids"])) or set(map(str,role["fit_ids"])) & set(map(str,test["ids"])) or set(map(str,role["tuning_ids"])) & set(map(str,test["ids"])) or set(map(str,role["calibration_ids"])) & set(map(str,test["ids"])): raise ValueError("fit/tune/cal/test identities overlap")
        if len(role["fit_ids"])!=int(expected_fit_rows) or len(role["X_tune"])!=int(expected_tune_rows) or len(role["X_cal"])!=int(expected_cal_rows) or len(test["X"])!=int(expected_test_rows): raise ValueError("role/test row counts differ from E6 plan")
        # All member model and role hashes must agree with both task and evaluation.
        ev_pipes=evaluation.get("pipeline_sha256",{})
        for m in MEMBERS:
            row=doc["members"][m]; fitkey=members[m]
            if row.get("fit_key")!=fitkey or row.get("pipeline_sha256")!=fp.get("pipeline_sha256",{}).get(m) or row.get("pipeline_sha256")!=ev_pipes.get(m):
                raise ValueError(f"{m} fit/pipeline identity mismatch")
            exp=task.get("member_fit_evidence",{}).get(m,{})
            for fld in ("fit_ids_sha256","role_membership_sha256","selection_sha256","fit_result_sha256","validation_sha256","selected_params_sha256","provenance_group"):
                if row.get(fld)!=exp.get(fld): raise ValueError(f"{m} fit evidence mismatch: {fld}")
            if row.get("score_kind")!="probability" or float(row.get("alpha",-1))!=.1 or int(row.get("calibration_n",-1))!=int(expected_cal_rows) or int(row.get("test_n",-1))!=int(expected_test_rows): raise ValueError(f"{m} evaluation contract mismatch")
        shared=rt/"cache"/"e6_posteriors"/f"rep_{rep}"/cache_sig
        tune,tune_sha,tune_receipt_sha=_verify_cache(shared,"tune",fp)
        cal,cal_sha,cal_receipt_sha=_verify_cache(shared,"cal",fp)
        ts,test_cache_sha,test_receipt_sha=_verify_cache(shared,"test",fp)
        # Recompute tune-only best member, individual q, test metrics, and weighted ensemble.
        tune_ba={}
        tune_pred={m:np.argmax(tune[m],axis=1) for m in MEMBERS}
        yt=np.asarray(role["y_tune"],dtype=np.int64)
        for m in MEMBERS:
            recalls=[float(np.mean(tune_pred[m][yt==c]==c)) for c in range(7)]
            tune_ba[m]=float(np.mean(recalls))
        best=min(MEMBERS,key=lambda m:(-tune_ba[m],MEMBERS.index(m)))
        if doc.get("tuning_best_member")!=best or not _close(doc.get("tuning_best_balanced_accuracy"),tune_ba[best]): raise ValueError("tuning-only best-member evidence mismatch")
        tuning_file=out/"tuning_posteriors.npz"
        if not tuning_file.is_file(): raise ValueError("tuning posterior evidence missing")
        with np.load(tuning_file,allow_pickle=False) as tz:
            if not np.array_equal(np.asarray(tz["y_tune"]),yt) or not np.array_equal(np.asarray(tz["tuning_ids"]),role["tuning_ids"]): raise ValueError("saved tuning labels/IDs differ from role cache")
            for m in MEMBERS:
                if not np.array_equal(np.asarray(tz[m+"_posterior"]),tune[m]): raise ValueError(f"saved tuning posterior differs from receipt-bound {m} cache")
        if doc.get("candidate_ledger_path"):
            ledger=out/doc["candidate_ledger_path"]
            if not ledger.is_file() or sha_file(ledger)!=doc.get("candidate_ledger_sha256"): raise ValueError("candidate ledger path/SHA mismatch")
        for m in MEMBERS:
            q=_q(cal[m],ycal,.1)
            row=doc["members"][m]
            if not _close(row.get("calibration_threshold"),q): raise ValueError(f"{m} calibration threshold differs from saved calibration posterior")
            actual=_metrics(ts[m],ytest,q)
            saved=row.get("evaluation",{})
            for metric in ("balanced_accuracy","coverage","set_size"):
                if not _close(saved.get(metric),actual[metric]): raise ValueError(f"{m} saved test {metric} differs from posterior-derived value")
            if saved.get("per_class")!=actual["per_class"]: 
                for c in range(7):
                    for metric in ("n","recall","coverage","set_size"):
                        if not _close(saved.get("per_class",{}).get(str(c),{}).get(metric),actual["per_class"][str(c)][metric]): raise ValueError(f"{m} class {c} {metric} mismatch")
            if saved.get("confusion_matrix") is not None and saved.get("confusion_matrix")!=actual["confusion_matrix"]: raise ValueError(f"{m} confusion matrix mismatch")
        calmix=sum(weights[i]*cal[m] for i,m in enumerate(MEMBERS))
        ensemble_q=_q(calmix,ycal,.1)
        if not _close(evaluation.get("conformal_threshold"),ensemble_q) or not _close(doc.get("ensemble_threshold"),ensemble_q): raise ValueError("ensemble threshold differs from saved calibration posterior mixture")
        testmix=sum(weights[i]*ts[m] for i,m in enumerate(MEMBERS))
        actual_ensemble=_metrics(testmix,ytest,ensemble_q)
        for metric in ("balanced_accuracy","coverage","set_size"):
            if not _close(doc.get("ensemble_evaluation",{}).get(metric),actual_ensemble[metric]) or not _close(evaluation.get(metric),actual_ensemble[metric]):
                raise ValueError(f"ensemble {metric} differs from saved posterior mixture")
        if doc.get("ensemble_evaluation",{}).get("per_class")!=actual_ensemble["per_class"]:
            raise ValueError("ensemble per-class metrics differ from posterior mixture")
        if doc.get("ensemble_confusion_matrix")!=actual_ensemble["confusion_matrix"]: raise ValueError("ensemble confusion matrix mismatch")
        if "sample_id" in outcomes and not np.array_equal(np.asarray(outcomes["sample_id"]),test["ids"]): raise ValueError("ensemble saved test IDs mismatch")
        if "y_true" in outcomes and not np.array_equal(np.asarray(outcomes["y_true"],dtype=int),ytest): raise ValueError("ensemble saved true labels mismatch")
        if not np.array_equal(np.asarray(outcomes["y_pred"],dtype=int),actual_ensemble["predictions"]): raise ValueError("ensemble saved y_pred mismatch")
        packed=np.asarray(outcomes["set_mask"],dtype=np.uint8).reshape(-1)
        bits=((packed[:,None]>>np.arange(7,dtype=np.uint8))&1).astype(bool)
        if not np.array_equal(bits,actual_ensemble["sets"]): raise ValueError("ensemble test set mask mismatch")
        if not np.array_equal(np.asarray(outcomes["covered"],dtype=bool),actual_ensemble["covered"]) or not np.array_equal(np.asarray(outcomes["set_size"],dtype=int),actual_ensemble["set_sizes"]):
            raise ValueError("ensemble coverage/set-size arrays mismatch")
        details.update({"status":"validated","posterior_cache_key":cache_sig,"cache_files":{"tune":tune_sha,"cal":cal_sha,"test":test_cache_sha},
           "receipt_files":{"tune":tune_receipt_sha,"cal":cal_receipt_sha,"test":test_receipt_sha},
           "member_count":5,"member_q_recomputed_from_saved_calibration_scores":5,"member_test_metrics_recomputed_from_saved_test_posteriors":5,
           "ensemble_q_and_metrics_recomputed_from_saved_scores":True})
    except Exception as exc:
        bad("e6_v2_saved_comparison_invalid",f"{type(exc).__name__}: {exc}")
    details["issues"]=[{"check":c,"evidence":e} for c,e in errors]
    if errors: details["status"]="invalid"
    return details
