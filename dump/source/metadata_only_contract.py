"""Strict opt-in E3-to-E5 metadata-only dependency contract."""
import hashlib, json
from pathlib import Path

POLICY = "e3-e5-fixed-selection-json-v1"
PINNED_CODE = {
    "parallel_rf/worker.py": "5741d1f60b513a6da0023e508b8d17d28e8f6e4355f30c08d5cfb81f1f233ab9",
    "parallel_rf/science.py": "e36c8040c7dca254fc7e16a53ffe860872df31a77868a7bc6480162f32d253c6",
    "parallel_rf/phase_worker.py": "6bbc631629227aa5113badefac6206884187ce01fa2d9d77edf66b477d6c08a3",
}
_RUNTIME_FIELDS = frozenset({
    # Registry lifecycle fields set by initialize(), admit(), terminalize(),
    # retry/recovery, and worker supervision in the frozen controller.
    "status", "outcome", "observed_utc", "validation_state", "attempts", "pid",
    "process_start_ticks", "started_utc", "finished_utc", "result",
    "artifact_dir", "selection_source", "train_path", "request_path",
    "result_path", "started_epoch", "finished_epoch", "reason",
    "peak_tree_rss_bytes", "superseded_operational_states",
    "admission_reservation_bytes", "admission_profile_id",
    "admission_profile_evidence", "adaptive_policy_revision",
    "admission_resource_policy", "dispatch_policy_id",
    "admission_resource_observation", "_archive_native_fit_overlap_proof",
    "_e6_orphan_blocked", "adaptive_emergency_available_bytes",
    "adaptive_emergency_reason", "adaptive_emergency_term_epoch",
    "adaptive_incident_history", "adaptive_promoted_heavy",
    "adaptive_promoted_utc", "adaptive_promotion_reason",
    "effective_dependencies", "forced_outcome", "forced_reason",
    "forced_term_epoch", "operational_recoveries", "orphan_term_epoch",
    "retry_after_epoch",
})

def _sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def _stable_sha(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError("selection JSON is not a regular file")
    before=path.stat(follow_symlinks=False)
    digest=_sha(path)
    after=path.stat(follow_symlinks=False)
    ident=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    if ident(before)!=ident(after): raise ValueError("selection JSON changed while hashing")
    return digest

def _json_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _definition(task):
    return {k:v for k,v in task.items() if k not in _RUNTIME_FIELDS}

def _stable_json(path):
    path=Path(path)
    digest=_stable_sha(path)
    value=json.loads(path.read_text())
    if _stable_sha(path)!=digest: raise ValueError("frozen plan JSON changed while reading")
    if not isinstance(value,dict): raise ValueError("frozen plan JSON root is invalid")
    return value,digest

def _frozen_definitions(root):
    manifests=Path(root)/"runtime_20261025"/"manifests"
    plan_path=manifests/"tasks.json";freeze_path=manifests/"freeze.json"
    plan_doc,plan_sha=_stable_json(plan_path)
    freeze_doc,freeze_sha=_stable_json(freeze_path)
    if freeze_doc.get("plan_sha256")!=plan_sha: raise ValueError("task plan does not match frozen plan SHA")
    if _stable_sha(plan_path)!=plan_sha or _stable_sha(freeze_path)!=freeze_sha:
        raise ValueError("frozen task source changed during contract validation")
    rows=plan_doc.get("tasks") if isinstance(plan_doc.get("tasks"),list) else None
    if rows is None: raise ValueError("frozen task plan has no task list")
    definitions={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("key"),str) or row["key"] in definitions:
            raise ValueError("frozen task plan has invalid or duplicate task key")
        definitions[row["key"]]=row
    return definitions

def _bound_definition(root,record,frozen):
    key=record.get("key")
    if not isinstance(frozen,dict): raise ValueError("missing frozen task definition")
    stable_record=_definition(record)
    stable_frozen=_definition(frozen)
    if stable_record!=stable_frozen: raise ValueError("registry task definition differs from frozen plan")
    extra=set(record)-set(frozen)-_RUNTIME_FIELDS
    if extra: raise ValueError("registry task has unclassified runtime fields: "+",".join(sorted(extra)))
    runtime=Path(root)/"runtime_20261025"
    if "artifact_dir" in record:
        expected=(runtime/"artifacts"/key).resolve()
        if Path(str(record["artifact_dir"])).resolve()!=expected:
            raise ValueError("registry artifact_dir is not the canonical task path")
    selection_source=record.get("selection_source")
    if selection_source:
        producer=record.get("selection_key")
        if not producer: raise ValueError("selection_source exists without a frozen selection_key")
        expected=(runtime/"artifacts"/producer/"selection.json").resolve()
        if Path(str(selection_source)).resolve()!=expected:
            raise ValueError("selection_source is not the canonical producer selection JSON")
    return stable_frozen

def _tasks(records):
    if isinstance(records,dict):
        rows=records.get("tasks") if isinstance(records.get("tasks"),list) else records.values()
    else: rows=records
    return {t["key"]:t for t in rows}

def build_contract(root, producer, records, closure):
    """Return a reproducible binding, or fail closed if any edge is not metadata-only."""
    root=Path(root).resolve()
    tasks=_tasks(records)
    definitions=_frozen_definitions(root)
    src=tasks.get(producer)
    if not src or producer!="e3/rep_2/fit/synthetic/random_forest/copula":
        raise ValueError("producer outside qualified E3 rep2 copula scope")
    if src.get("kind")!="fit" or src.get("method")!="random_forest" or int(src.get("experiment",0))!=3:
        raise ValueError("producer is not E3 RF fit")
    all_keys={producer}|set(closure)
    stable_definitions={}
    for task_key in sorted(all_keys):
        record=tasks.get(task_key)
        if record is None or task_key not in definitions: raise ValueError("contract task is absent from registry or frozen plan")
        stable_definitions[task_key]=_bound_definition(root,record,definitions[task_key])
    runtime=root/"runtime_20261025"
    for rel,want in PINNED_CODE.items():
        path=runtime/"source"/rel
        if not path.is_file() or _sha(path)!=want: raise ValueError("RF metadata consumer code pin mismatch: "+rel)
    selection_rel=f"runtime_20261025/artifacts/{producer}/selection.json"
    selection= root/selection_rel
    if selection.resolve(strict=True).relative_to(root)!=Path(selection_rel):
        raise ValueError("selection JSON path resolved outside canonical root")
    expected=(src.get("result") or {}).get("validation",{}).get("files",{}).get("selection.json")
    if not expected or not selection.is_file() or _stable_sha(selection)!=expected:
        raise ValueError("producer selection JSON does not match validated hash")
    try: parsed=json.loads(selection.read_text())
    except Exception as e: raise ValueError("invalid producer selection JSON") from e
    if not isinstance(parsed,dict) or not any(k in parsed for k in ("params","selected_params","best_params")):
        raise ValueError("selection JSON lacks fixed parameter object")
    pending_fits=[]; pending_evals=[]; allowed=set()
    for key in sorted(closure):
        t=tasks.get(key)
        if not t: raise ValueError("missing closure task")
        status=t.get("status")
        if status=="validated_terminal" and not (
            (t.get("kind")=="fit" and int(t.get("experiment",0))==5 and t.get("method")=="random_forest" and t.get("selection_key")==producer) or
            (t.get("kind")=="eval" and int(t.get("experiment",0))==5 and t.get("method")=="random_forest")):
            continue
        if t.get("kind")=="fit" and int(t.get("experiment",0))==5 and t.get("method")=="random_forest":
            if t.get("selection_key")!=producer or t.get("selection_mode")!="fixed" or t.get("selection_policy")!="frozen_clean_selected_params_no_retuning" or t.get("reuse_pipeline"):
                raise ValueError("pending E5 fit is not fixed-selection-only")
            if any(t.get(k) for k in ("fit_key","source_key","model_key","model_task","pipeline_task","artifact_task","producer_task","member_task","model_references","model_refs","model_keys","member_keys","artifact_references")):
                raise ValueError("pending E5 fit has physical model reference")
            if status not in ("waiting_for_dependency","pending","running","validated_terminal"): raise ValueError("unexpected E5 fit state")
            pending_fits.append({"task_key":key,"definition_sha256":_json_sha(stable_definitions[key])})
            allowed.add(key)
        elif t.get("kind")=="eval" and int(t.get("experiment",0))==5 and t.get("method")=="random_forest":
            fit=t.get("fit_key")
            if t.get("reuse_pipeline") or any(t.get(k) for k in ("source_key","model_key","model_task","pipeline_task","artifact_task","producer_task","member_task","model_references","model_refs","model_keys","member_keys","artifact_references")):
                raise ValueError("E5 evaluation has an extra physical model reference")
            if not isinstance(fit,str) or fit==producer or not fit.startswith("e5/") or tasks.get(fit,{}).get("selection_key")!=producer:
                raise ValueError("pending evaluation does not read its own E5 fit")
            if set(t.get("dependencies") or [])!={fit}:
                raise ValueError("E5 evaluation has an extra source dependency")
            if status not in ("waiting_for_dependency","pending","running","validated_terminal"): raise ValueError("unexpected E5 eval state")
            pending_evals.append({"task_key":key,"definition_sha256":_json_sha(stable_definitions[key]),"fit_key":fit})
            allowed.add(key)
        else: raise ValueError("unclassified nonterminal consumer")
    if not pending_fits or len(pending_fits)!=9 or len(pending_evals)!=9:
        raise ValueError("qualified E3 contract requires exactly nine E5 fits and evaluations")
    # Verify each pending eval is paired with an E5 fit in this same closure.
    fitkeys={x["task_key"] for x in pending_fits}
    paired={x["fit_key"] for x in pending_evals}
    if paired!=fitkeys or len(paired)!=len(pending_evals):
        raise ValueError("pending E5 evaluations do not pair one-to-one with the qualified fits")
    return {"policy":POLICY,"producer_task":producer,"selection_json_path":selection_rel,
            "selection_json_sha256":expected,"consumer_code_sha256":PINNED_CODE,
            "pending_metadata_fit_tasks":pending_fits,"pending_own_fit_evaluations":pending_evals,
            "full_consumer_closure":sorted(closure),"contract_sha256":_json_sha({
             "policy":POLICY,"producer_task":producer,"selection_json_path":selection_rel,
             "selection_json_sha256":expected,"consumer_code_sha256":PINNED_CODE,
             "pending_metadata_fit_tasks":pending_fits,"pending_own_fit_evaluations":pending_evals,
             "full_consumer_closure":sorted(closure)})}
