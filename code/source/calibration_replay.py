"""Calibration replay primitives. These functions do not load models."""
import hashlib, json, math, os, datetime
from pathlib import Path
import numpy as np

ALPHA = .1
ORDER = tuple(range(7))
RULES = {"probability": "1-p_true", "margin": "negative_margin"}
IDENTITY_FIELDS = ("pipeline_sha256","role_file_sha256","calibration_ids_sha256","X_cal_sha256","y_cal_sha256",
                   "score_kind","rule","class_order","alpha","rank","helper_sha256","dependencies")

def typed_sha(a):
    a = np.ascontiguousarray(a); h = hashlib.sha256()
    h.update(str(a.dtype).encode()); h.update(str(a.shape).encode()); h.update(a.view(np.uint8))
    return h.hexdigest()

def derive(scores, y, kind, alpha=ALPHA):
    s=np.asarray(scores,dtype=np.float64); y=np.asarray(y,dtype=np.int64)
    if kind not in RULES or s.shape!=(len(y),7) or not np.isfinite(s).all(): raise ValueError("invalid score matrix")
    if y.ndim!=1 or np.any((y<0)|(y>6)) or not 0<float(alpha)<1: raise ValueError("invalid labels/alpha")
    if kind=="probability":
        if np.any(s<0) or not np.allclose(s.sum(1),1.,atol=1e-6,rtol=0): raise ValueError("invalid probabilities")
        v=1.-s[np.arange(len(y)),y]
    else: v=-s[np.arange(len(y)),y]
    n=len(v); k=int(math.ceil((n+1)*(1-float(alpha))))
    q=float(np.partition(v,k-1)[k-1]) if k<=n else float("inf")
    return {"threshold":q,"calibration_n":n,"rank_k":k,"nonconformity":np.asarray(v,dtype=np.float64),
            "score_kind":kind,"nonconformity_rule":RULES[kind],"alpha":float(alpha),"class_order":list(ORDER)}

def make_identity(*,pipeline_sha256,role_file_sha256,ids,X,y,kind,helper_sha256,dependencies):
    d={"pipeline_sha256":pipeline_sha256,"role_file_sha256":role_file_sha256,"calibration_ids_sha256":typed_sha(ids),
       "X_cal_sha256":typed_sha(X),"y_cal_sha256":typed_sha(y),"score_kind":kind,"rule":RULES[kind],
       "class_order":list(ORDER),"alpha":ALPHA,"rank":"ceil((n+1)*(1-alpha)); partition(k-1)",
       "helper_sha256":helper_sha256,"dependencies":dependencies}
    return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":")).encode()).hexdigest(),d

def compare(saved,derived,fit_key,pipeline_sha,require_rule=False):
    if not isinstance(saved,dict): return ["saved threshold record missing"]
    bad=[]
    for k,w in (("calibration_n",derived["calibration_n"]),("score_kind",derived["score_kind"]),("fit_key",fit_key),("pipeline_sha256",pipeline_sha)):
        if saved.get(k)!=w: bad.append(k+"_mismatch")
    q=saved.get("threshold",saved.get("conformal_threshold"))
    try:
        if q is None or not np.isclose(float(q),derived["threshold"],atol=1e-10,rtol=0): bad.append("threshold_mismatch")
    except Exception: bad.append("threshold_invalid")
    if require_rule and saved.get("nonconformity_rule")!=derived["nonconformity_rule"]: bad.append("nonconformity_rule_mismatch")
    return bad

def file_sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

def atomic_json(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+".tmp."+str(os.getpid()))
    with t.open("w") as f:
        f.write(json.dumps(obj,sort_keys=True,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))
        f.flush();os.fsync(f.fileno())
    os.replace(t,p);_fsync_dir(p.parent)

def _fsync_dir(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def save_replay(root,identity,derived,metadata):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); dest=root/identity
    if dest.exists():
        existing=load_replay(dest,identity)
        if not np.array_equal(existing["nonconformity"],np.asarray(derived["nonconformity"],dtype=np.float64)):
            raise ValueError("existing replay differs for identical identity")
        for k,v in metadata.items():
            if existing["metadata"].get(k)!=v: raise ValueError(f"existing replay metadata differs: {k}")
        if existing["metadata"].get("threshold")!=derived["threshold"] or existing["metadata"].get("rank_k")!=derived["rank_k"]:
            raise ValueError("existing replay q/rank differs")
        return dest
    tmp=root/(".tmp-"+identity+"-"+str(os.getpid())); tmp.mkdir()
    try:
        v=derived["nonconformity"]
        if v.nbytes>160*1024*1024: raise ValueError("vector exceeds 160 MiB")
        with (tmp/"nonconformity.npz").open("wb") as f:
            np.savez_compressed(f,nonconformity=v);f.flush();os.fsync(f.fileno())
        payload={k:metadata[k] for k in IDENTITY_FIELDS}
        expected=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if expected!=identity: raise ValueError("identity does not match replay inputs")
        d=dict(metadata,identity=identity,identity_payload=payload,nonconformity_sha256=typed_sha(v),nonconformity_file_sha256=file_sha(tmp/"nonconformity.npz"),
               threshold=derived["threshold"],calibration_n=derived["calibration_n"],rank_k=derived["rank_k"],score_kind=derived["score_kind"],nonconformity_rule=derived["nonconformity_rule"])
        atomic_json(tmp/"metadata.json",d); os.replace(tmp,dest);_fsync_dir(root)
    except BaseException:
        import shutil; shutil.rmtree(tmp,ignore_errors=True); raise
    return dest

def load_replay(path,identity):
    p=Path(path); m=json.loads((p/"metadata.json").read_text()); f=p/"nonconformity.npz"
    payload=m.get("identity_payload")
    if not isinstance(payload,dict) or set(payload)!=set(IDENTITY_FIELDS): raise ValueError("identity payload missing or malformed")
    recomputed=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if identity!=p.name or recomputed!=identity or m.get("identity")!=identity: raise ValueError("identity/directory/payload mismatch")
    for key in ("pipeline_sha256","role_file_sha256","calibration_ids_sha256","X_cal_sha256","y_cal_sha256","score_kind","class_order","alpha"):
        if m.get(key)!=payload.get(key): raise ValueError(f"metadata disagrees with identity payload: {key}")
    deps=payload.get("dependencies",{})
    for source_key,metadata_key in (("source_evaluation_sha256","source_evaluation_sha256"),
                                    ("calibration_json_sha256","calibration_json_sha256"),
                                    ("frozen_source_report_sha256","frozen_source_report_sha256"),
                                    ("scoring_module_sha256","scoring_module_sha256"),
                                    ("class_order_contract","class_order_source")):
        if source_key in deps and m.get(metadata_key)!=deps[source_key]: raise ValueError(f"metadata dependency mismatch: {metadata_key}")
    if m.get("alpha")!=ALPHA or payload.get("alpha")!=ALPHA: raise ValueError("unexpected replay alpha")
    if m.get("class_order")!=list(ORDER) or payload.get("class_order")!=list(ORDER): raise ValueError("invalid replay class order")
    kind=m.get("score_kind")
    if kind not in RULES or m.get("nonconformity_rule")!=RULES[kind] or payload.get("score_kind")!=kind or payload.get("rule")!=RULES[kind]: raise ValueError("invalid score kind/rule")
    if file_sha(f)!=m.get("nonconformity_file_sha256"): raise ValueError("replay file SHA mismatch")
    with np.load(f,allow_pickle=False) as z: v=np.asarray(z["nonconformity"],dtype=np.float64)
    if not np.isfinite(v).all() or typed_sha(v)!=m.get("nonconformity_sha256"): raise ValueError("vector SHA/content invalid")
    if kind=="probability" and (np.any(v<0) or np.any(v>1)): raise ValueError("probability nonconformity is outside [0,1]")
    n=len(v); k=int(math.ceil((n+1)*(1-ALPHA))); q=float(np.partition(v,k-1)[k-1]) if k<=n else float("inf")
    if m.get("rank_k")!=k or n!=int(m["calibration_n"]) or not np.isclose(q,float(m["threshold"]),atol=1e-12,rtol=0): raise ValueError("q/n/rank differs from exact quantile rule")
    return {"metadata":m,"nonconformity":v,"rank_k":k}

def alias_matches(alias,physical):
    return all(alias.get(k)==physical.get(k) for k in ("threshold","calibration_n","score_kind","nonconformity_rule","pipeline_sha256","fit_key"))

def alias_role_matches(physical,role_file_sha256,calibration_ids_sha256,X_cal_sha256,y_cal_sha256):
    return all((physical or {}).get(k)==v for k,v in (
        ("role_file_sha256",role_file_sha256),("calibration_ids_sha256",calibration_ids_sha256),
        ("X_cal_sha256",X_cal_sha256),("y_cal_sha256",y_cal_sha256)))

def validate_alias(alias,physical_doc,physical_row,role_file_sha256,calibration_ids_sha256,X_cal_sha256,y_cal_sha256):
    alias=alias or {}; kind=alias.get("score_kind")
    expected_rule=RULES.get(kind)
    declared_rule=alias.get("nonconformity_rule")
    if declared_rule is None and kind=="probability": declared_rule=expected_rule
    raw_order=alias.get("class_order")
    labels={"A":0,"F":1,"G":2,"K":3,"M":4,"GALAXY":5,"QSO":6}
    if raw_order is None:
        class_match=bool(physical_doc and alias.get("fit_key")==physical_doc.get("fit_key")
            and alias.get("pipeline_sha256")==physical_doc.get("pipeline_sha256")
            and alias.get("fit_key")==physical_row.get("fit_key")
            and alias.get("pipeline_sha256")==physical_row.get("pipeline_sha256"))
        class_basis="same verified fit and pipeline identity"
    else:
        try: order=[labels[str(v)] if str(v) in labels else int(v) for v in raw_order]
        except Exception: order=[]
        class_match=order==list(ORDER) and order==list(physical_row.get("class_order", []))
        class_basis="alias evaluation class_order"
    try: alpha=float(alias.get("alpha",alias.get("conformal_alpha",ALPHA)))
    except Exception: alpha=float("nan")
    checks={"threshold_and_provenance":bool(physical_doc and alias_matches(alias,physical_doc)),
      "calibration_role":alias_role_matches(physical_row,role_file_sha256,calibration_ids_sha256,X_cal_sha256,y_cal_sha256),
      "score_kind":kind==physical_row.get("score_kind"),"nonconformity_rule":declared_rule==physical_row.get("nonconformity_rule"),
      "class_order":class_match,"alpha":alpha==float(physical_row.get("alpha",ALPHA)),"class_order_basis":class_basis}
    checks["match"]=all(v for k,v in checks.items() if k!="class_order_basis")
    return checks

def summarize(physical,aliases):
    pv=sum(x.get("status")=="validated" for x in physical); av=sum(x.get("status")=="inherited" for x in aliases)
    pm=sum(x.get("status")=="mismatch" for x in physical); am=sum(x.get("status")=="mismatch" for x in aliases)
    complete=pv==len(physical) and av==len(aliases)
    return {"required_physical":len(physical),"successful_physical":pv,"mismatch_physical":pm,"unavailable_physical":len(physical)-pv-pm,
            "required_aliases":len(aliases),"inherited_aliases":av,"mismatch_aliases":am,"unavailable_aliases":len(aliases)-av-am,
            "complete":complete,"independent_q_recomputed":complete}


def verify_supervision_receipt(audit_doc, receipt, audit_sha256, accepted_prior_receipts=None, phase_ledger=None):
    """Verify an external parent's immutable supervision evidence and identity bindings.

    This verifier does not observe liveness or enforce resource limits. It checks the
    parent's receipt against the auditor's immutable output and its private JSONL phase
    ledger; only a separate parent may assert PID/start-tick checks and cap enforcement.
    accepted_prior_receipts maps verified receipt SHA256 to identity sets.
    """
    reasons=[]; phases_ok=True
    if not isinstance(audit_doc,dict) or not isinstance(receipt,dict):
        return {"valid":False,"q_replay_coverage_complete":False,"qualified_complete":False,
                "expected_identity_count":0,"verified_identity_count":0,"reasons":["audit_or_receipt_invalid"]}
    if audit_doc.get("schema_version")!="lamost-calibration-replay-audit/1" or audit_doc.get("complete") is not False:
        reasons.append("raw_audit_not_immutable_unqualified_snapshot")
    if receipt.get("schema_version")!="lamost-calibration-replay-supervision/1": reasons.append("receipt_schema_invalid")
    if receipt.get("status") not in {"complete","partial"}: reasons.append("receipt_status_invalid")
    if receipt.get("audit_sha256")!=audit_sha256: reasons.append("audit_sha256_mismatch")
    if receipt.get("registry_snapshot_sha256")!=audit_doc.get("registry_snapshot_sha256"): reasons.append("registry_snapshot_sha256_mismatch")
    nonce=audit_doc.get("replay_run_nonce")
    if not nonce or receipt.get("run_nonce")!=nonce: reasons.append("run_nonce_mismatch")
    if receipt.get("audit_process_exit_code")!=0 or receipt.get("audit_process_exit_verified") is not True:
        reasons.append("audit_process_exit_unverified")
    if receipt.get("finalized_after_audit_exit") is not True: reasons.append("receipt_not_finalized_after_audit_exit")
    if receipt.get("phase_ledger_sha256")!=audit_doc.get("phase_ledger_sha256"): reasons.append("phase_ledger_sha256_mismatch")
    if receipt.get("accepted_prior_receipts_index_sha256")!=audit_doc.get("accepted_prior_receipts_index_sha256"):
        reasons.append("accepted_prior_receipts_index_sha256_mismatch")
    ledger_events={}
    if not isinstance(phase_ledger,(bytes,bytearray)):
        reasons.append("phase_ledger_payload_missing")
    else:
        if hashlib.sha256(phase_ledger).hexdigest()!=audit_doc.get("phase_ledger_sha256"):
            reasons.append("phase_ledger_payload_mismatch")
        try:
            for raw in bytes(phase_ledger).splitlines():
                if not raw: continue
                event=json.loads(raw)
                if event.get("schema_version")!="lamost-calibration-replay-phase-ledger/1" or event.get("run_nonce")!=nonce:
                    reasons.append("phase_ledger_event_invalid"); continue
                key=(event.get("phase_id"),event.get("event"))
                if not key[0] or key in ledger_events: reasons.append("phase_ledger_duplicate_event"); continue
                canonical=json.dumps(event,sort_keys=True,separators=(",",":")).encode()
                if raw!=canonical: reasons.append("phase_ledger_noncanonical_event")
                ledger_events[key]={"event":event,"sha256":hashlib.sha256(raw).hexdigest()}
        except Exception:
            reasons.append("phase_ledger_parse_error")
    limits=receipt.get("limits",{})
    if limits.get("wall_seconds")!=600 or limits.get("rss_bytes")!=10*1024**3: reasons.append("declared_limits_mismatch")
    rows=audit_doc.get("records",[]); expected={}; alias_rows=[]
    for row in rows:
        if not isinstance(row,dict): reasons.append("audit_record_invalid"); continue
        if row.get("source_key"):
            alias_rows.append(row); continue
        mode=row.get("supervision_mode")
        if row.get("identity") and row.get("fit_key") and mode in {"replayed","cache_reuse"}:
            for field in ("identity","metadata_sha256","nonconformity_file_sha256"):
                value=row.get(field)
                if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value): reasons.append("physical_identity_hash_invalid")
            if row["task_key"] in expected: reasons.append("duplicate_physical_task_key")
            expected[row["task_key"]]={"fit_key":row["fit_key"],"identity":row["identity"],
                "metadata_sha256":row.get("metadata_sha256"),"nonconformity_file_sha256":row.get("nonconformity_file_sha256"),
                "supervision_mode":mode,"prior_receipt_sha256":row.get("prior_receipt_sha256")}
        elif row.get("status")=="validated" and row.get("fit_key"):
            reasons.append("validated_physical_row_missing_supervision_identity")
    physical_rows=[r for r in rows if isinstance(r,dict) and not r.get("source_key")]
    complete_from_rows=bool(physical_rows) and all(r.get("status")=="validated" for r in physical_rows) and all(r.get("status")=="inherited" for r in alias_rows)
    if audit_doc.get("q_replay_coverage_complete") is not complete_from_rows:
        reasons.append("q_replay_coverage_claim_inconsistent_with_rows")
    bykey={r.get("task_key"):r for r in rows if isinstance(r,dict)}
    for alias in alias_rows:
        if alias.get("status")=="inherited":
            source=bykey.get(alias.get("physical_source_key"))
            if not source or source.get("status")!="validated" or source.get("identity")!=alias.get("source_identity"):
                reasons.append("alias_source_identity_unverified")
            for field in ("threshold_match","calibration_role_match","score_kind_match","nonconformity_rule_match","class_order_match","alpha_match"):
                if alias.get(field) is not True: reasons.append("alias_validation_flag_failed:"+field)
    observed={}; receipt_phases=receipt.get("phase_records")
    if not isinstance(receipt_phases,list): receipt_phases=[]; reasons.append("phase_records_missing")
    phases_by_id={}
    for phase in receipt_phases:
        if not isinstance(phase,dict): reasons.append("phase_record_invalid"); continue
        pid=phase.get("phase_id"); mode=phase.get("mode")
        if not pid or pid in phases_by_id: reasons.append("phase_id_missing_or_duplicate"); continue
        phases_by_id[pid]=phase
        if mode not in {"replayed","cache_reuse"}: reasons.append("phase_mode_invalid"); continue
        if phase.get("run_nonce")!=nonce: reasons.append("phase_run_nonce_mismatch")
        start=ledger_events.get((pid,"start")); finish=ledger_events.get((pid,"finish"))
        if not start or not finish:
            reasons.append("phase_ledger_start_or_finish_missing")
        else:
            a=start["event"]; b=finish["event"]
            for event in (a,b):
                if event.get("mode")!=mode or event.get("fit_key")!=phase.get("fit_key") or event.get("task_keys")!=phase.get("task_keys"):
                    reasons.append("phase_ledger_receipt_scope_mismatch")
                if event.get("run_nonce")!=nonce or event.get("phase")!=phase.get("phase"):
                    reasons.append("phase_ledger_nonce_or_name_mismatch")
            if mode=="cache_reuse" and any(a.get("prior_receipts",{}).get(k)!=phase.get("prior_receipt_sha256") or b.get("prior_receipts",{}).get(k)!=phase.get("prior_receipt_sha256") for k in phase.get("task_keys",[])):
                reasons.append("phase_ledger_cache_lineage_mismatch")
            if a.get("phase_id")!=b.get("phase_id") or a.get("pid")!=b.get("pid") or a.get("process_start_ticks")!=b.get("process_start_ticks"):
                reasons.append("phase_ledger_process_identity_changed")
            if phase.get("started_utc")!=a.get("utc") or phase.get("finished_utc")!=b.get("utc"):
                reasons.append("phase_timestamp_ledger_mismatch")
            try:
                ledger_elapsed=float(b["monotonic"])-float(a["monotonic"])
                if not math.isfinite(ledger_elapsed) or ledger_elapsed<0: reasons.append("phase_ledger_time_reversed")
                if ledger_elapsed>600: reasons.append("phase_ledger_wall_cap_failed")
                try:
                    reported_elapsed=float(phase.get("duration_seconds"))
                    if not math.isclose(reported_elapsed,ledger_elapsed,rel_tol=0,abs_tol=1e-6): reasons.append("phase_duration_ledger_mismatch")
                except Exception: reasons.append("phase_duration_invalid")
            except Exception: reasons.append("phase_ledger_monotonic_missing")
            if phase.get("phase_start_event_sha256")!=start["sha256"] or phase.get("phase_finish_event_sha256")!=finish["sha256"]:
                reasons.append("phase_ledger_event_hash_mismatch")
        if phase.get("phase")!=("calibration_score_replay" if mode=="replayed" else "cache_reuse"):
            reasons.append("phase_name_mismatch")
        status=phase.get("status")
        if status not in {"passed","failed","interrupted"}: reasons.append("phase_status_invalid")
        if status!="passed": phases_ok=False
        if not phase.get("started_utc") or not phase.get("finished_utc"): reasons.append("phase_timestamps_missing")
        if not isinstance(phase.get("measurement_method"),str) or not phase.get("measurement_method"): reasons.append("phase_memory_measurement_method_missing")
        try:
            elapsed=float(phase.get("duration_seconds")); peak=int(phase.get("peak_process_tree_rss_bytes"))
            if not math.isfinite(elapsed) or elapsed<0 or elapsed>600: reasons.append("phase_wall_cap_failed")
            if peak<0 or peak>10*1024**3: reasons.append("phase_rss_cap_failed")
        except Exception: reasons.append("phase_measurement_invalid")
        if phase.get("process_identity_verified") is not True or phase.get("cap_enforced") is not True: reasons.append("phase_supervision_unverified")
        if status=="passed" and phase.get("exit_code")!=0: reasons.append("phase_exit_not_success")
        if status!="passed" and not isinstance(phase.get("exit_code"),int): reasons.append("failed_phase_exit_code_missing")
        if mode=="cache_reuse":
            prior=phase.get("prior_receipt_sha256"); accepted=accepted_prior_receipts or {}
            if not prior or prior not in accepted: reasons.append("prior_receipt_unverified")
            if phase.get("artifact_integrity_verified") is not True: reasons.append("cached_artifact_integrity_unverified")
        bindings=phase.get("identity_bindings",[])
        if not isinstance(bindings,list): reasons.append("identity_bindings_invalid"); continue
        phase_tasks=set(phase.get("task_keys",[])); bound_tasks=set()
        phase_expected=phase_tasks.intersection(expected)
        if phase_expected and not bindings: reasons.append("identity_bindings_missing")
        for binding in bindings:
            if not isinstance(binding,dict): reasons.append("identity_binding_invalid"); continue
            task=binding.get("task_key"); want=expected.get(task)
            fields=("fit_key","identity","metadata_sha256","nonconformity_file_sha256")
            actual={k:binding.get(k) for k in fields}; wanted={k:want.get(k) for k in fields} if want else None
            if want is None: reasons.append("unexpected_identity_binding"); continue
            if actual!=wanted: reasons.append("identity_binding_mismatch"); continue
            bound_tasks.add(task)
            if want["supervision_mode"]!=mode: reasons.append("identity_mode_mismatch")
            if phase.get("fit_key")!=want["fit_key"]: reasons.append("phase_fit_key_mismatch")
            if mode=="cache_reuse":
                if binding.get("prior_receipt_sha256")!=want["prior_receipt_sha256"] or phase.get("prior_receipt_sha256")!=want["prior_receipt_sha256"]:
                    reasons.append("cache_lineage_binding_mismatch")
                verified=(accepted_prior_receipts or {}).get(phase.get("prior_receipt_sha256"),set())
                if want["identity"] not in verified: reasons.append("prior_receipt_does_not_cover_identity")
            if task in observed: reasons.append("duplicate_identity_binding")
            observed[task]=actual
        if phase_expected!=bound_tasks: reasons.append("phase_task_binding_coverage_mismatch")
    if set(observed)!=set(expected): reasons.append("required_identity_coverage_incomplete")
    if set(ledger_events)!={(pid,event) for pid in phases_by_id for event in ("start","finish")}:
        reasons.append("unreferenced_or_missing_phase_ledger_events")
    q_complete=audit_doc.get("q_replay_coverage_complete") is True
    if receipt.get("status")=="complete" and not phases_ok: reasons.append("complete_receipt_contains_failed_phase")
    valid=not reasons
    qualified=bool(valid and q_complete and receipt.get("status")=="complete" and phases_ok)
    return {"valid":valid,"q_replay_coverage_complete":q_complete,"qualified_complete":qualified,
        "expected_identity_count":len(expected),"verified_identity_count":len(observed),"reasons":sorted(set(reasons))}

def write_qualification_report(audit_path, receipt_path, qualification_path, accepted_prior_receipts=None, phase_ledger_path=None):
    """Write a separate qualification record after the external supervisor has exited.

    The source audit is hash-bound and never rewritten; this function cannot create the
    supervision receipt or certify process identity itself.
    """
    audit_path=Path(audit_path); receipt_path=Path(receipt_path)
    audit_bytes=audit_path.read_bytes(); receipt_bytes=receipt_path.read_bytes()
    audit_doc=json.loads(audit_bytes); receipt=json.loads(receipt_bytes)
    ledger_bytes=Path(phase_ledger_path).read_bytes() if phase_ledger_path else None
    result=verify_supervision_receipt(audit_doc,receipt,hashlib.sha256(audit_bytes).hexdigest(),
        accepted_prior_receipts=accepted_prior_receipts,phase_ledger=ledger_bytes)
    out={"schema_version":"lamost-calibration-replay-qualification/1",
      "generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "audit_path":audit_path.as_posix(),"audit_sha256":hashlib.sha256(audit_bytes).hexdigest(),
      "supervision_receipt_path":receipt_path.as_posix(),"supervision_receipt_sha256":hashlib.sha256(receipt_bytes).hexdigest(),
      "phase_ledger_path":Path(phase_ledger_path).as_posix() if phase_ledger_path else None,
      "phase_ledger_sha256":hashlib.sha256(ledger_bytes).hexdigest() if ledger_bytes is not None else None,
      **result}
    atomic_json(qualification_path,out)
    return out
