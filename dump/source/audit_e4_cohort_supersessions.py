#!/usr/bin/env python3
"""Read-only post-regeneration proof for the 42 E4 cohort containers."""
from __future__ import annotations
import argparse, hashlib, json, os, zipfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

MANIFEST_REL=Path("manifests/incidents/e4_weight_schema_20261025.json")
EXPECTED_PRODUCER_SHA="5d5988b365613966778abc7438926d9e1b26ec36b779df98586aa600a3d20a1d"
EXPECTED_COUNT=42

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def array_sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def crc_ok(path):
    with zipfile.ZipFile(path) as z:return z.testzip() is None

def audit(runtime, output):
    rt=Path(runtime).resolve(); regpath=rt/"registry.json"; regbytes=regpath.read_bytes()
    registry=json.loads(regbytes); regsha=hashlib.sha256(regbytes).hexdigest()
    manifest_path=rt/MANIFEST_REL; manifest_sha=sha(manifest_path); manifest=json.loads(manifest_path.read_text())
    entries=manifest.get("cohort_container_supersessions",[])
    amendment=manifest.get("amendment",{})
    source=rt/"source/cohorts.py"; source_sha=sha(source)
    bykey={t.get("key"):t for t in registry.get("tasks",[]) if t.get("key")}
    planned=sorted(x.get("task_key") for x in entries)
    issues=[]
    if len(entries)!=EXPECTED_COUNT or len(set(planned))!=EXPECTED_COUNT:issues.append("manifest does not enumerate exactly 42 unique cohort keys")
    if amendment.get("affected_cohort_helpers_to_regenerate")!=EXPECTED_COUNT:issues.append("amendment expected cohort count mismatch")
    if amendment.get("source_after_sha256",{}).get("cohorts.py")!=EXPECTED_PRODUCER_SHA:issues.append("incident amendment producer SHA differs from approved producer fix")
    if source_sha!=EXPECTED_PRODUCER_SHA:issues.append(f"live producer SHA differs: {source_sha}")
    states={k:(bykey[k].get("status"),bykey[k].get("outcome")) if k in bykey else ("missing",None) for k in planned}
    not_terminal=[k for k,v in states.items() if v!=("validated_terminal","successful")]
    base={"schema_version":1,"scope":"42 E4 regenerated cohort containers only","generated_utc":datetime.now(timezone.utc).isoformat(),
      "runtime":str(rt),"manifest_path":str(manifest_path),"manifest_sha256":manifest_sha,"registry_path":str(regpath),
      "registry_observed_utc":registry.get("observed_utc"),"registry_snapshot_sha256":regsha,
      "registry_task_count":len(registry.get("tasks",[])),"planned_cohorts":len(entries),"validated_terminal_successful_cohorts":len(entries)-len(not_terminal),
      "pending_or_nonterminal_keys":not_terminal,"producer_sha256":source_sha,"expected_producer_sha256":EXPECTED_PRODUCER_SHA}
    if not_terminal:
        base.update(status="not_run_until_all_42_validated_terminal_success",issues=issues)
        Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(base,indent=2,sort_keys=True))
        return base
    if len(entries)!=EXPECTED_COUNT:
        base.update(status="invalid_manifest_scope",issues=issues)
        Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(base,indent=2,sort_keys=True))
        return base
    results=[]
    for item in entries:
        key=item["task_key"]; task=bykey.get(key); row={"task_key":key,"errors":[]}
        def bad(msg):row["errors"].append(msg)
        old=rt/item["retained_container"]
        cur=Path(task.get("artifact_dir",""))/"data.npz"
        if not cur.is_absolute():cur=rt/cur
        meta=cur.parent/"metadata.json"; validation=cur.parent/"validation.json"; oldval=old.parent/"validation.json"
        before={str(p):sha(p) for p in (old,oldval,cur,meta,validation)}
        row.update(old_container_path=str(old),new_container_path=str(cur),old_container_sha256=before[str(old)],
          new_container_sha256=before[str(cur)],old_validation_sha256=before[str(oldval)],new_validation_json_sha256=before[str(validation)],
          new_metadata_sha256=before[str(meta)])
        if before[str(old)]!=item.get("original_container_sha256"):bad("retained original container SHA differs from incident manifest")
        if before[str(oldval)]!=item.get("original_validation_sha256"):bad("retained original validation SHA differs from incident manifest")
        if not crc_ok(old) or not crc_ok(cur):bad("old or new NPZ ZIP CRC check failed")
        try:
            ov=json.loads(oldval.read_text()); nv=json.loads(validation.read_text()); md=json.loads(meta.read_text())
            oldhash=ov.get("files",{}).get("data.npz"); newhash=nv.get("files",{}).get("data.npz")
            result_hash=task.get("result",{}).get("validation",{}).get("files",{}).get("data.npz")
            if oldhash!=before[str(old)]:bad("retained old validation does not bind old container")
            if newhash!=before[str(cur)] or result_hash!=before[str(cur)]:bad("new container SHA differs from worker validation registry")
            if nv.get("status")!="validated" or nv.get("task_key")!=key:bad("new validation record is not validated for this task")
            if md.get("sample_weight_included") is not False:bad(f"new metadata sample_weight_included={md.get('sample_weight_included')!r}, expected false")
        except Exception as e:bad(f"validation or metadata JSON could not be verified: {e}")
        try:
            with np.load(old,allow_pickle=False) as a,np.load(cur,allow_pickle=False) as b:
                oldkeys=list(a.files);newkeys=list(b.files)
                row["old_members"]=oldkeys;row["new_members"]=newkeys
                if oldkeys!=["X","y","ids","sample_weight"]:bad(f"unexpected original members/order: {oldkeys}")
                if newkeys!=["X","y","ids"]:bad(f"new cohort has unexpected members or weights: {newkeys}")
                hashes={}
                for name in ("X","y","ids"):
                    if name not in a.files or name not in b.files:bad(f"missing shared array {name}");continue
                    x=a[name];y=b[name]
                    info={"dtype_old":str(x.dtype),"dtype_new":str(y.dtype),"shape_old":list(x.shape),"shape_new":list(y.shape),
                          "values_exact":bool(x.dtype==y.dtype and x.shape==y.shape and np.array_equal(x,y,equal_nan=True))}
                    hashes[name]=array_sha(x)
                    if not info["values_exact"]:bad(f"shared array {name} differs in dtype, shape, or values")
                    if item.get("shared_array_sha256",{}).get(name)!=hashes[name]:bad(f"old shared-array {name} SHA differs from incident manifest")
                    row.setdefault("shared_arrays",{})[name]=info
                row["shared_array_sha256"]=hashes
        except Exception as e:bad(f"NPZ array comparison failed: {e}")
        after={str(p):sha(p) for p in (old,oldval,cur,meta,validation)}
        if before!=after:bad("an audited artifact changed during the read-only audit")
        row["passed"]=not row["errors"];results.append(row)
    issues.extend(f"{r['task_key']}: {e}" for r in results for e in r["errors"])
    base.update(status="validated" if not issues else "issues_found",cohorts_passed=sum(r["passed"] for r in results),
      cohorts_failed=sum(not r["passed"] for r in results),issues=issues,results=results,
      current_inputs_unchanged_after_audit=True)
    Path(output).parent.mkdir(parents=True,exist_ok=True);Path(output).write_text(json.dumps(base,indent=2,sort_keys=True))
    return base

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--runtime",default="/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025")
    ap.add_argument("--output",default=None);args=ap.parse_args()
    rt=Path(args.runtime);out=args.output or str(rt/"reports/engineering_audits/E4_COHORT_CONTAINER_SUPERSESSION_AUDIT_20261025.json")
    r=audit(rt,out);print(json.dumps({k:r.get(k) for k in ("generated_utc","status","manifest_sha256","registry_snapshot_sha256","planned_cohorts","validated_terminal_successful_cohorts","cohorts_passed","cohorts_failed","issues")},indent=2))
if __name__=="__main__":main()
