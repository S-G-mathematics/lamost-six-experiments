from __future__ import annotations
import argparse, csv, hashlib, json, math, os, time
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

LABELS=("A","F","G","K","M","GALAXY","QSO")
RATES=(0.05,0.10,0.20)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)

def atomic_json(path,obj):
    tmp=Path(str(path)+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def require(ok,msg,issues):
    if not bool(ok): issues.append(msg)

def role_arrays(path):
    with np.load(path,allow_pickle=False) as z:
        return {k:z[k].copy() for k in ("X_fit","y_fit","fit_ids","tuning_ids","calibration_ids")}

def expected_cache_hash(manifest,rel):
    for key,value in manifest.get("cache_files",{}).items():
        if key==rel or key.endswith("/"+rel):
            return value.get("sha256") if isinstance(value,dict) else value
    return None

def mask_membership_matches(indices,mask):
    """Order-independent membership check; keep indices unsorted for aligned audits."""
    return (len(np.unique(indices))==len(indices) and
            np.array_equal(np.sort(np.asarray(indices,dtype=np.int64)),
                           np.flatnonzero(np.asarray(mask,dtype=bool))))

def feature_perturbations_match(X0,X,indices,feature_index,perturbations):
    """Compare aligned row/feature/perturbation tuples without sorting any tuple member."""
    idx=np.asarray(indices,dtype=np.int64); feat=np.asarray(feature_index,dtype=np.int64)
    delta=np.asarray(perturbations)
    return (len(idx)==len(feat)==len(delta) and
            np.array_equal(X[idx,feat],X0[idx,feat]+delta,equal_nan=True))

def audit_e4(rt,tasks,dev_ids,test_ids,roles,issues):
    before=len(issues)
    cohort=[t for t in tasks if t.get("kind")=="e4_cohort"]
    require(len(cohort)==42,f"planned E4 altered cohort count {len(cohort)}; expected 42",issues)
    paired={}
    rows=[]
    for task in cohort:
        key=task["key"];rep=int(task["rep"]);target=int(task["target_class"]);ratio=float(task["ratio"])
        role=roles[rep];fit_ids=role["fit_ids"];yfit=role["y_fit"]
        data=rt/task["artifact_dir"]/"data.npz";meta_path=rt/task["artifact_dir"]/"metadata.json"
        try:
            meta=read_json(meta_path)
            with np.load(data,allow_pickle=False) as z:
                y=np.asarray(z["y"],dtype=np.int64);ids=np.asarray(z["ids"])
            original=np.bincount(np.asarray(yfit,dtype=np.int64),minlength=7)
            actual=np.bincount(y,minlength=7)
            expected_target=int(math.floor(ratio*int(original[target])+0.5))
            require(len(ids)==len(y)==80000,f"{key}: row/ID count is not 80000",issues)
            require(len(np.unique(ids))==len(ids),f"{key}: IDs are not unique",issues)
            require(np.array_equal(actual,np.asarray(meta["planned_counts"])),f"{key}: actual histogram differs from planned counts",issues)
            require(actual[target]==expected_target,f"{key}: target quota differs from rounded target share",issues)
            require(np.array_equal(original,np.asarray(meta["source_fit_counts"])),f"{key}: source fit histogram differs from metadata",issues)
            require((meta.get("rep")==rep and meta.get("target_class")==target and
                     float(meta.get("ratio"))==ratio and int(meta.get("N"))==80000),
                    f"{key}: metadata identity mismatch",issues)
            require(meta.get("sample_weight_included") is False,f"{key}: unexpected cohort sample_weight",issues)
            ot=int(np.intersect1d(ids,role["tuning_ids"]).size)
            oc=int(np.intersect1d(ids,role["calibration_ids"]).size)
            ox=int(np.intersect1d(ids,test_ids).size)
            require(ot==oc==ox==0,f"{key}: cohort overlaps tune/calibration/test roles",issues)
            pos=np.searchsorted(dev_ids,ids);valid=pos<len(dev_ids)
            in_dev=bool(np.all(valid) and np.array_equal(dev_ids[pos[valid]],ids[valid]))
            require(in_dev,f"{key}: IDs absent from non-test development pool",issues)
            paired.setdefault((rep,target),{})[ratio]={
                "ids":ids,"labels":y,"original_target_ids":fit_ids[yfit==target]
            }
            rows.append({"key":key,"rep":rep,"target_class":LABELS[target],"ratio":ratio,
                         "row_count":len(y),"class_counts":actual.tolist(),
                         "target_original_count":int(original[target]),"target_count":int(actual[target]),
                         "tune_overlap":ot,"calibration_overlap":oc,"test_overlap":ox,
                         "development_pool_membership":in_dev,"data_sha256":sha(data),
                         "metadata_sha256":sha(meta_path)})
        except Exception as exc:
            issues.append(f"{key}: {type(exc).__name__}: {exc}")
    pair_rows=[]
    for (rep,target),levels in sorted(paired.items()):
        if .5 not in levels or .1 not in levels:
            issues.append(f"E4 rep{rep}/{LABELS[target]}: missing half/tenth pair")
            continue
        half=levels[.5];tenth=levels[.1]
        hids,hy=half["ids"],half["labels"];tids,ty=tenth["ids"],tenth["labels"]
        half_target=set(hids[hy==target].tolist());tenth_target=set(tids[ty==target].tolist())
        original_target=set(half["original_target_ids"].tolist())
        target_nested=tenth_target.issubset(half_target)
        target_from_original=half_target.issubset(original_target) and tenth_target.issubset(original_target)
        require(target_nested,f"E4 rep{rep}/{LABELS[target]}: tenth target IDs are not subset of half",issues)
        require(target_from_original,f"E4 rep{rep}/{LABELS[target]}: reduced target IDs are not from original fit target",issues)
        others=[]
        for cls in range(7):
            if cls==target: continue
            hs=set(hids[hy==cls].tolist());ts=set(tids[ty==cls].tolist())
            ok=hs.issubset(ts)
            require(ok,f"E4 rep{rep} target {LABELS[target]}: class {LABELS[cls]} IDs not nested",issues)
            others.append({"class":LABELS[cls],"half_subset_tenth":ok,
                           "half_count":len(hs),"tenth_count":len(ts)})
        pair_rows.append({"rep":rep,"target_class":LABELS[target],
                          "target_tenth_subset_half":target_nested,
                          "reduced_target_ids_from_original_fit_target":target_from_original,
                          "other_class_membership_nested":all(x["half_subset_tenth"] for x in others),
                          "other_classes":others})
    return {"planned":len(cohort),"checked":len(rows),"cohorts":rows,
            "pair_checks":pair_rows,"issue_count":len(issues)-before,
            "limitation":"IDs are sorted in each saved cohort; set membership is verified but historical within-class order is not recoverable."}

def recompute_scales(X):
    vals=[];methods=[]
    for col in range(6):
        x=X[:,col];x=x[np.isfinite(x)]
        if not len(x): raise ValueError(f"no finite fit values for feature {col}")
        s=float((np.percentile(x,75)-np.percentile(x,25))/1.349);method="IQR/1.349"
        if not np.isfinite(s) or s<=0:
            s=float(np.std(x,ddof=0));method="std_ddof0"
        if not np.isfinite(s) or s<=0:
            s=1e-12;method="floor_1e-12"
        vals.append(s);methods.append(method)
    return np.asarray(vals),methods

def audit_e5(rt,tasks,roles,issues):
    before=len(issues)
    selected=[t for t in tasks if t.get("kind")=="e5_corruption" and t.get("mechanism") in ("feature_noise","missingness")]
    require(len(selected)==18,f"planned E5 feature/missingness cell count {len(selected)}; expected 18",issues)
    taskmap={t["key"]:t for t in selected}
    summary_path=rt/"reports/E5_corruption_realization_summary.csv"
    with summary_path.open(newline="",encoding="utf-8") as f:
        summary={row["task_key"]:row for row in csv.DictReader(f)}
    cells=[];nesting=[]
    for rep in (1,2,3):
        role=roles[rep];clean_X=role["X_fit"];clean_y=role["y_fit"];clean_ids=role["fit_ids"]
        scales,scale_methods=recompute_scales(clean_X)
        for mechanism in ("feature_noise","missingness"):
            rate_ids={}
            for rate,suffix in ((.05,"05"),(.10,"10"),(.20,"20")):
                key=f"e5/rep_{rep}/corruption/{mechanism}_{suffix}"
                task=taskmap.get(key);summary_row=summary.get(key)
                if task is None or summary_row is None:
                    issues.append(f"{key}: missing task or realization summary")
                    continue
                try:
                    base=rt/task["artifact_dir"];dp=base/"data.npz";ap=base/"audit.npz";mp=base/"metadata.json"
                    meta=read_json(mp)
                    with np.load(dp,allow_pickle=False) as z:
                        X=np.asarray(z["X"]);y=np.asarray(z["y"]);ids=np.asarray(z["ids"])
                    with np.load(ap,allow_pickle=False) as z:
                        audit={name:z[name].copy() for name in z.files}
                    n=len(y);expected=int(math.floor(rate*n+0.5))
                    indices=np.asarray(audit["affected_row_indices"],dtype=np.int64)
                    mask=np.asarray(audit["affected_mask"],dtype=bool)
                    affected_ids=np.asarray(audit["affected_ids"])
                    # Compare membership independent of index ordering. Retain original index order below,
                    # because feature_index/perturbation arrays align with that permutation order.
                    mask_ok=mask_membership_matches(indices,mask)
                    require(mask_ok,f"{key}: affected-row index set differs from mask",issues)
                    require(len(indices)==expected and int(meta.get("affected_count",-1))==expected and
                            int(meta.get("fit_count",-1))==80000,f"{key}: expected affected/fitting row counts mismatch",issues)
                    require(X.shape==(80000,6) and np.array_equal(ids,clean_ids),f"{key}: output shape or fit ID order mismatch",issues)
                    require(np.array_equal(affected_ids,clean_ids[indices]),f"{key}: affected IDs do not align to recorded row order",issues)
                    require(np.array_equal(y,clean_y),f"{key}: non-label corruption changed labels",issues)
                    require(meta.get("other_roles_touched") is False and summary_row.get("other_roles_touched")=="False",
                            f"{key}: metadata indicates another role was touched",issues)
                    require(np.array_equal(X[~mask],clean_X[~mask],equal_nan=True),f"{key}: unselected rows changed",issues)
                    features=np.asarray(audit["feature_index"],dtype=np.int64)
                    require(features.shape==(expected,) and np.all((features>=0)&(features<6)),
                            f"{key}: selected-feature vector invalid",issues)
                    keep=np.ones((expected,6),dtype=bool);keep[np.arange(expected),features]=False
                    require(np.array_equal(X[indices][keep],clean_X[indices][keep],equal_nan=True),
                            f"{key}: cells outside selected features changed",issues)
                    new_missing=None
                    if mechanism=="feature_noise":
                        perturb=np.asarray(audit["perturbation"])
                        pair_ok=feature_perturbations_match(clean_X,X,indices,features,perturb)
                        require(pair_ok,f"{key}: row-feature-perturbation tuple fails to reproduce cells",issues)
                        require(perturb.shape==(expected,),f"{key}: perturbation length mismatch",issues)
                        require(np.allclose(np.asarray(audit["per_feature_scale"],float),scales,rtol=0,atol=1e-12),
                                f"{key}: saved feature scales differ from clean-fit recomputation",issues)
                        require(np.allclose(np.asarray(meta["feature_scale"],float),scales,rtol=0,atol=1e-12),
                                f"{key}: metadata feature scales differ from clean-fit recomputation",issues)
                    else:
                        require(bool(np.all(np.isnan(X[indices,features]))),f"{key}: selected cells not missing",issues)
                        require(meta.get("missing_indicator") is False,f"{key}: missingness indicator policy mismatch",issues)
                        new_missing=int(np.isfinite(clean_X[indices,features]).sum())
                    require(float(summary_row.get("realized_rate"))==rate and
                            int(summary_row.get("affected_count",-1))==expected,
                            f"{key}: summary rate/count mismatch",issues)
                    rate_ids[rate]=affected_ids.copy()
                    cells.append({"key":key,"rep":rep,"mechanism":mechanism,"rate":rate,
                                  "affected_count":expected,"data_sha256":sha(dp),"audit_sha256":sha(ap),
                                  "metadata_sha256":sha(mp),"affected_ids_sha256":hashlib.sha256(
                                      np.ascontiguousarray(affected_ids).view(np.uint8)).hexdigest(),
                                  "feature_index_counts":np.bincount(features,minlength=6).tolist(),
                                  "clean_fit_scale_methods":scale_methods if mechanism=="feature_noise" else None,
                                  "newly_missing_selected_cells":new_missing})
                except Exception as exc:
                    issues.append(f"{key}: {type(exc).__name__}: {exc}")
            if len(rate_ids)==3:
                a,b,c=(set(rate_ids[r].tolist()) for r in RATES)
                ab=a.issubset(b);bc=b.issubset(c)
                require(ab and bc,f"E5 rep{rep} {mechanism}: actual affected IDs not nested across rates",issues)
                nesting.append({"rep":rep,"mechanism":mechanism,"n05":len(a),"n10":len(b),"n20":len(c),
                                "nested05in10":ab,"nested10in20":bc})
    return {"planned":18,"checked":len(cells),"cells":cells,"mask_nesting":nesting,
            "issue_count":len(issues)-before}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--runtime",default="/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025")
    parser.add_argument("--outdir")
    args=parser.parse_args();rt=Path(args.runtime).resolve()
    out=Path(args.outdir).resolve() if args.outdir else rt/"reports/engineering_audits"
    out.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path=out/f"E4_E5_REALIZATION_GAP_AUDIT_{stamp}.json"
    md_path=out/f"E4_E5_REALIZATION_GAP_AUDIT_{stamp}.md"
    if json_path.exists() or md_path.exists(): raise SystemExit("refusing to overwrite existing reports")
    issues=[]
    tasks_path=rt/"manifests/tasks.json";source_path=rt/"source/cohorts.py";manifest_path=rt/"cache/cache_manifest.json"
    tasks_doc=read_json(tasks_path);tasks=tasks_doc["tasks"];plan_sha=sha(tasks_path);source_sha=sha(source_path)
    cache_manifest=read_json(manifest_path);cache_sha=sha(manifest_path)
    roles={};role_hashes={}
    for rep in (1,2,3):
        path=rt/"cache"/"roles"/f"rep_{rep}.npz";rel=f"roles/rep_{rep}.npz"
        before=sha(path);expected=expected_cache_hash(cache_manifest,rel)
        if expected and before!=expected: issues.append(f"rep{rep}: role-cache file hash differs from cache manifest")
        role_hashes[str(rep)]={"path":str(path),"before_sha256":before,"manifest_sha256":expected}
        roles[rep]=role_arrays(path)
    dev_ids=np.load(rt/"cache/development_ids.npy",mmap_mode="r")
    test_path=rt/"cache/test.npz";test_before=sha(test_path)
    with np.load(test_path,allow_pickle=False) as z:test_ids=z["ids"].copy()
    started=time.monotonic()
    e4=audit_e4(rt,tasks,dev_ids,test_ids,roles,issues)
    del dev_ids,test_ids
    e5=audit_e5(rt,tasks,roles,issues)
    elapsed=time.monotonic()-started
    post={"tasks_sha256":sha(tasks_path),"cohorts_source_sha256":sha(source_path),
          "cache_manifest_sha256":sha(manifest_path),"test_npz_sha256":sha(test_path)}
    if post["tasks_sha256"]!=plan_sha:issues.append("tasks.json changed during audit")
    if post["cohorts_source_sha256"]!=source_sha:issues.append("cohorts.py changed during audit")
    if post["cache_manifest_sha256"]!=cache_sha:issues.append("cache manifest changed during audit")
    if post["test_npz_sha256"]!=test_before:issues.append("test cache changed during audit")
    for rep,record in role_hashes.items():
        record["after_sha256"]=sha(record["path"])
        if record["after_sha256"]!=record["before_sha256"]:issues.append(f"rep{rep}: role cache changed during audit")
    result={"schema":"lamost-e4-e5-realization-gap-audit/2",
            "observed_utc":datetime.now(timezone.utc).isoformat(),
            "status":"PASS" if not issues else "ISSUES_FOUND",
            "scope":"Read-only realization checks for E4 altered cohorts and E5 feature-noise/missingness only.",
            "resource":{"expected_external_limits":"1 GiB address-space, 120 seconds, nice 19, native threads 1",
                        "elapsed_seconds":elapsed},
            "input_hashes":{"tasks_sha256":plan_sha,"cohorts_source_sha256":source_sha,
                            "cache_manifest_sha256":cache_sha,"test_npz_sha256_before":test_before,
                            "post_audit_identities":post,"role_cache_hashes":role_hashes},
            "E4":e4,"E5_feature_noise_missingness":e5,"issues":issues,
            "reused_prior_audits":{"E4_treatments_and_appends":"E4_RESTORATION_INPUT_SNAPSHOT_AUDIT_20261026.json; E4_APPEND_SCHEMA_CORRECTED_REAUDIT_20261026.json",
                                   "E5_label_noise":"E5_LABEL_NOISE_REALIZATION_AUDIT_20261027.json"},
            "limitations":["E4 stored IDs are sorted; membership nesting is checked but original within-class ordering cannot be reconstructed.",
                           "No model, training-configuration, prediction, calibration, or test outcome validation is performed."]}
    atomic_json(json_path,result)
    md=(f"# E4/E5 realization gap audit\n\nObserved {result['observed_utc']} UTC; status **{result['status']}**.\n\n"
        f"- E4 cohorts: {e4['checked']}/42, paired membership groups: {len(e4['pair_checks'])}, issues: {e4['issue_count']}.\n"
        f"- E5 feature-noise/missingness cells: {e5['checked']}/18, nested sweeps: {len(e5['mask_nesting'])}, issues: {e5['issue_count']}.\n"
        f"- Elapsed {elapsed:.2f}s. Input/artifact hashes are in {json_path.name}.\n"
        "- Prior E4 treatment/append and E5 label-noise audits were referenced, not repeated.\n"
        "- No fitting, models, inference, predictions, calibration, or queue changes.\n")
    md_path.write_text(md,encoding="utf-8")
    print(json.dumps({"json":str(json_path),"json_sha256":sha(json_path),
                      "markdown":str(md_path),"markdown_sha256":sha(md_path),
                      "status":result["status"],"E4_checked":e4["checked"],
                      "E5_checked":e5["checked"],"issue_count":len(issues),
                      "elapsed_seconds":elapsed},indent=2))
if __name__=="__main__":main()
