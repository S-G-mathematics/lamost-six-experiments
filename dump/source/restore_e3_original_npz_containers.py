#!/usr/bin/env python3
"""Restore only byte-exact original E3 NPZ containers into an isolated supplement."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

ROOT=Path("/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025")
AUDIT=ROOT/"reports"/"INCREMENTAL_EVALUATION_AUDIT.json"
ISSUES=ROOT/"reports"/"INCREMENTAL_EVALUATION_ISSUES.csv"
REGISTRY=ROOT/"registry.json"
OUTPUT=ROOT/"artifacts"/"_restored_original_e3_containers"
MANIFEST=ROOT/"manifests"/"incidents"/"e3_original_npz_container_restoration_20261025.json"
RECEIPT=ROOT/"logs"/"operational"/"e3_original_npz_container_restoration_20261025.json"
OMIT={"attempt_id","worker_pid","started_at","observed_at","observed_utc","artifact_dir","controller_pid","status","attempts","attempt_number","queue_state","controller_state"}

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): h.update(block)
    return h.hexdigest()
def atomic_copy_new(src,dst):
    dst=Path(dst); dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():
        raise FileExistsError(f"refusing to overwrite existing restored artifact: {dst}")
    tmp=dst.with_name(dst.name+"."+os.urandom(8).hex()+".tmp")
    shutil.copy2(src,tmp)
    os.replace(tmp,dst)
def parse_hash(evidence,name):
    for part in evidence.split("; "):
        if part.startswith(name+"="): return part[len(name)+1:]
    raise ValueError(f"audit evidence lacks {name}")
def member_audit(old_path,current_path):
    with zipfile.ZipFile(old_path) as z:
        bad=z.testzip()
        if bad is not None: raise ValueError(f"old candidate CRC failure at {bad}")
        old_zip_names=[n[:-4] if n.endswith(".npy") else n for n in z.namelist()]
    with zipfile.ZipFile(current_path) as z:
        bad=z.testzip()
        if bad is not None: raise ValueError(f"current NPZ CRC failure at {bad}")
        current_zip_names=[n[:-4] if n.endswith(".npy") else n for n in z.namelist()]
    with np.load(old_path,allow_pickle=False) as old,np.load(current_path,allow_pickle=False) as current:
        old_names=list(old.files); current_names=list(current.files)
        if "fallback_mask" not in current_names: raise ValueError("current diagnostics NPZ has no fallback_mask")
        expected_current=[n for n in current_names if n!="fallback_mask"]
        if old_names!=expected_current: raise ValueError(f"member name/order mismatch old={old_names}, expected current minus fallback={expected_current}")
        if old_zip_names!=old_names or current_zip_names!=current_names: raise ValueError("ZIP member order differs from NumPy NPZ member order")
        details=[]
        for name in old_names:
            a=old[name]; b=current[name]
            if a.dtype!=b.dtype or a.shape!=b.shape: raise ValueError(f"{name}: dtype/shape mismatch {a.dtype}/{a.shape} != {b.dtype}/{b.shape}")
            equal=np.array_equal(a,b,equal_nan=True) if np.issubdtype(a.dtype,np.inexact) else np.array_equal(a,b)
            if not equal: raise ValueError(f"{name}: array values differ")
            details.append({"name":name,"dtype":str(a.dtype),"shape":list(a.shape),"values_exact":True})
        fallback=current["fallback_mask"]
        if fallback.shape!=(len(current["sample_id"]),): raise ValueError("fallback_mask must have one element per row")
        return {"member_order_preserved":True,"original_members":old_names,"current_members":current_names,
          "fallback_mask_omitted_only":True,"arrays":details,"fallback_mask_shape":list(fallback.shape),
          "fallback_true_count":int(np.asarray(fallback,dtype=bool).sum()),
          "old_zip_crc":"ok","current_zip_crc":"ok"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--verify-only",action="store_true",help="verify all candidates and records without publishing outputs")
    args=ap.parse_args()
    audit=json.loads(AUDIT.read_text()); registry=json.loads(REGISTRY.read_text())
    if not ISSUES.is_file(): raise FileNotFoundError(f"authoritative issue CSV missing: {ISSUES}")
    issue_rows=list(csv.DictReader(ISSUES.open()))
    csv_by_key={r["task_key"]:r for r in issue_rows if r.get("check")=="superseded_attempt_hash_mismatch"}
    issues={i["task_key"]:i for i in audit["issues"] if i.get("check")=="superseded_attempt_hash_mismatch"}
    if len(issues)!=9: raise ValueError(f"expected nine audit issues, observed {len(issues)}")
    if set(csv_by_key)!=set(issues): raise ValueError("JSON and CSV issue keys differ")
    task_rows={r["key"]:r for r in registry["tasks"]}
    now=datetime.now(timezone.utc).isoformat()
    records=[]
    if not args.verify_only: OUTPUT.mkdir(parents=True,exist_ok=True)
    for key,issue in sorted(issues.items()):
        csvrow=csv_by_key[key]
        expected=parse_hash(issue["evidence"],"recorded_npz_sha256")
        expected_csv=parse_hash(csvrow["evidence"],"recorded_npz_sha256")
        if expected!=expected_csv: raise ValueError(f"{key}: audit JSON and CSV expected hashes differ")
        current_expected=parse_hash(issue["evidence"],"current_npz_sha256")
        row=task_rows[key]
        artifact_dir=Path(row["artifact_dir"])
        current=artifact_dir/"test_outcomes.npz"
        baseline_record=artifact_dir/"support_diagnostic_baseline.json"
        if not current.is_file() or not baseline_record.is_file(): raise FileNotFoundError(f"{key}: required current/source diagnostic record absent")
        meta=json.loads(baseline_record.read_text())
        if meta.get("previous_controller_attempt_id")!=parse_hash(issue["evidence"],"attempt"):
            raise ValueError(f"{key}: diagnostic baseline points to another original attempt")
        candidate=Path(meta["outcomes_path"])
        if not candidate.is_file(): raise FileNotFoundError(f"{key}: retained original container absent: {candidate}")
        candidate_sha=sha(candidate); current_sha=sha(current)
        if candidate_sha!=expected: raise ValueError(f"{key}: retained candidate SHA mismatch: {candidate_sha} != {expected}")
        if current_sha!=current_expected: raise ValueError(f"{key}: live current SHA changed since audit: {current_sha} != {current_expected}")
        if meta.get("outcomes_sha256")!=expected: raise ValueError(f"{key}: source support record hash disagrees with audit")
        attempts=row.get("attempts",[])
        initial=[a for a in attempts if a.get("attempt_id")==meta["previous_controller_attempt_id"]]
        if len(initial)!=1 or initial[0].get("reason")!="initial planned attempt": raise ValueError(f"{key}: initial worker attempt not uniquely identified")
        request=Path(initial[0]["request_path"]); worker_result=Path(initial[0]["result_path"])
        if not request.is_file() or not worker_result.is_file(): raise FileNotFoundError(f"{key}: initial request/worker result missing")
        req_obj=json.loads(request.read_text()); result_obj=json.loads(worker_result.read_text())
        if result_obj.get("key")!=key or result_obj.get("status")!="successful": raise ValueError(f"{key}: initial worker record does not describe a successful matching task")
        if result_obj.get("artifact_sha256")!=expected: raise ValueError(f"{key}: initial worker record artifact hash does not match audit")
        if result_obj.get("controller_attempt_id")!=meta["previous_controller_attempt_id"]: raise ValueError(f"{key}: worker record attempt ID mismatch")
        arrays=member_audit(candidate,current)
        dest=OUTPUT/key/"test_outcomes.original.npz"
        if args.verify_only:
            restored_sha=candidate_sha
        else:
            atomic_copy_new(candidate,dest)
            restored_sha=sha(dest)
            if restored_sha!=expected: raise ValueError(f"{key}: published exact-copy SHA mismatch")
            with zipfile.ZipFile(dest) as z:
                if z.testzip() is not None: raise ValueError(f"{key}: published CRC check failed")
        records.append({"task_key":key,"old_expected_sha256":expected,"current_sha256":current_sha,
          "restored_sha256":restored_sha,"restored_path":str(dest),"source_candidate_path":str(candidate),
          "source_candidate_sha256":candidate_sha,"current_path":str(current),"initial_attempt_id":meta["previous_controller_attempt_id"],
          "initial_request_path":str(request),"initial_request_file_sha256":sha(request),
          "initial_worker_result_path":str(worker_result),"initial_worker_result_file_sha256":sha(worker_result),
          "initial_worker_result_artifact_sha256":result_obj["artifact_sha256"],"initial_worker_request_task_key":req_obj.get("key",req_obj.get("task_key")),
          "support_diagnostic_baseline_path":str(baseline_record),"support_diagnostic_baseline_sha256":sha(baseline_record),
          "array_validation":arrays,"classification":"byte-exact original container available for isolated publication; live artifact unchanged"})
    if args.verify_only:
        print(json.dumps({"verify_only":True,"candidate_count":len(records),
          "exact_sha_matches":sum(x["source_candidate_sha256"]==x["old_expected_sha256"] for x in records),
          "array_exactness_verified":all(all(a["values_exact"] for a in x["array_validation"]["arrays"]) for x in records),
          "worker_records_verified":all(x["initial_worker_result_artifact_sha256"]==x["old_expected_sha256"] for x in records),
          "outputs_would_be_under":str(OUTPUT)},sort_keys=True,indent=2))
        return
    manifest={"created_utc":now,"experiment":"E3","scope":"nine direct generative route NPZ containers only",
      "audit_path":str(AUDIT),"audit_sha256":sha(AUDIT),"issues_csv_path":str(ISSUES),"issues_csv_sha256":sha(ISSUES),
      "registry_path":str(REGISTRY),"registry_sha256":sha(REGISTRY),
      "restoration_rule":"publish only when retained NPZ bytes match initial worker-record artifact_sha256 exactly",
      "live_artifacts_modified":False,"models_loaded":False,"fit_predict_calibrate_generate_performed":False,
      "files":records}
    manifest["restoration_code_path"]=str(Path(__file__).resolve()); manifest["restoration_code_sha256"]=sha(__file__)
    src=ROOT/"source"
    hf=lambda n:sha(src/n)
    manifest["engine_code_sha256"]=hashlib.sha256((hf("science.py")+hf("phase_worker.py")).encode()).hexdigest()
    MANIFEST.parent.mkdir(parents=True,exist_ok=True); MANIFEST.write_text(json.dumps(manifest,sort_keys=True,indent=2))
    receipt={"created_utc":now,"restored_count":len(records),"exact_sha_matches":sum(x["restored_sha256"]==x["old_expected_sha256"] for x in records),
      "array_exactness_verified":all(all(a["values_exact"] for a in x["array_validation"]["arrays"]) for x in records),
      "crc_verified":all(x["array_validation"]["old_zip_crc"]=="ok" for x in records),
      "manifest_path":str(MANIFEST),"manifest_sha256":sha(MANIFEST),"outputs_root":str(OUTPUT),
      "live_artifacts_modified":False,"all_scientific_computation_performed":False}
    RECEIPT.parent.mkdir(parents=True,exist_ok=True); RECEIPT.write_text(json.dumps(receipt,sort_keys=True,indent=2))
    print(json.dumps(receipt,sort_keys=True,indent=2))
if __name__=="__main__": main()
