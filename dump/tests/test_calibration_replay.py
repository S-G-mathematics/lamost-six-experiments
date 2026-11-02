import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).parent.parent/"source"))
import calibration_replay as cr
sys.path.insert(0,str(Path(__file__).parent.parent/"source"))
import audit_artifacts as audit
FROZEN_SCORING_FIXTURE=Path(__file__).resolve().parent/"fixtures"/"frozen_scoring_source"
PROJECT_ROOT=None
if (FROZEN_SCORING_FIXTURE/"benchmark"/"models_basic.py").is_file() and (FROZEN_SCORING_FIXTURE/"benchmark"/"results"/"e1_report_validated_no_bootstrap.json").is_file():
    PROJECT_ROOT=FROZEN_SCORING_FIXTURE
    sys.path.insert(0,str(PROJECT_ROOT))
else:
    for candidate in Path(__file__).resolve().parents:
        if (candidate/"project"/"benchmark").is_dir():
            PROJECT_ROOT=candidate/"project";sys.path.insert(0,str(PROJECT_ROOT));break

def test_probability_quantile_uses_partition_rank_9001():
    y=np.arange(10000,dtype=np.int64)%7
    scores=np.full((10000,7),1/7,dtype=np.float64)
    scores[np.arange(len(y)),y]=.5
    scores*= (1.0/scores.sum(1))[:,None]
    got=cr.derive(scores,y,"probability")
    expected=np.partition(1-scores[np.arange(len(y)),y],9000)[9000]
    assert got["rank_k"]==9001 and got["threshold"]==expected

def test_margin_uses_negative_native_margin():
    y=np.arange(70,dtype=np.int64)%7
    s=np.arange(490,dtype=np.float64).reshape(70,7)/19
    got=cr.derive(s,y,"margin")
    assert np.array_equal(got["nonconformity"],-s[np.arange(70),y])
    assert got["rank_k"]==64

def test_wrong_order_or_bad_probabilities_rejected():
    s=np.full((7,7),1/7); y=np.arange(7)
    with pytest.raises(ValueError):cr.derive(s[:-1],y,"probability")
    with pytest.raises(ValueError):cr.derive(np.full((7,7),.5),y,"probability")

def test_threshold_metadata_mismatch_is_explicit():
    y=np.arange(70)%7;s=np.full((70,7),1/7);d=cr.derive(s,y,"probability")
    assert not cr.compare({"threshold":d["threshold"],"calibration_n":70,"score_kind":"probability","fit_key":"f","pipeline_sha256":"p"},d,"f","p")
    assert "threshold_mismatch" in cr.compare({"threshold":0,"calibration_n":70,"score_kind":"probability","fit_key":"f","pipeline_sha256":"p"},d,"f","p")

def test_margin_saved_rule_must_match_native_score_contract():
    y=np.arange(70)%7; s=np.zeros((70,7)); d=cr.derive(s,y,"margin")
    saved={"threshold":d["threshold"],"calibration_n":70,"score_kind":"margin","fit_key":"f","pipeline_sha256":"p"}
    assert "nonconformity_rule_mismatch" in cr.compare(saved,d,"f","p",require_rule=True)
    saved["nonconformity_rule"]="negative_margin"
    assert not cr.compare(saved,d,"f","p",require_rule=True)

def test_identity_binds_role_arrays_threshold_dependency_and_helper():
    x=np.ones((4,6));y=np.arange(4);ids=np.arange(4)
    def ident(**kw):return cr.make_identity(pipeline_sha256="p",role_file_sha256="r",ids=ids,X=x,y=y,kind="probability",helper_sha256="h",dependencies={"evaluation_sha256":"e",**kw})[0]
    base=ident()
    assert ident(evaluation_sha256="different")!=base
    assert cr.make_identity(pipeline_sha256="p",role_file_sha256="r",ids=ids+1,X=x,y=y,kind="probability",helper_sha256="h",dependencies={})[0]!=base

def test_replay_artifact_roundtrip_and_tamper_detection(tmp_path):
    y=np.arange(70)%7;s=np.full((70,7),1/7);d=cr.derive(s,y,"probability");x=np.ones((70,6));ids=np.arange(70)
    ident,payload=cr.make_identity(pipeline_sha256="p",role_file_sha256="r",ids=ids,X=x,y=y,kind="probability",helper_sha256="h",dependencies={})
    path=cr.save_replay(tmp_path,ident,d,payload)
    assert cr.load_replay(path,ident)["rank_k"]==64
    with (path/"nonconformity.npz").open("ab") as f:f.write(b"x")
    with pytest.raises(ValueError):cr.load_replay(path,ident)

def test_replay_metadata_rank_and_identity_payload_are_revalidated(tmp_path):
    x=np.ones((70,6)); y=np.arange(70)%7; ids=np.arange(70)
    d=cr.derive(np.full((70,7),1/7),y,"probability")
    ident,payload=cr.make_identity(pipeline_sha256="p",role_file_sha256="r",ids=ids,X=x,y=y,kind="probability",helper_sha256="h",dependencies={})
    meta=dict(payload,task_key="t",fit_key="f")
    path=cr.save_replay(tmp_path,ident,d,meta)
    mp=path/"metadata.json"; doc=__import__("json").loads(mp.read_text());doc["rank_k"]=1;mp.write_text(__import__("json").dumps(doc))
    with pytest.raises(ValueError):cr.load_replay(path,ident)
    doc["rank_k"]=d["rank_k"];doc["threshold"]=0;mp.write_text(__import__("json").dumps(doc))
    with pytest.raises(ValueError):cr.load_replay(path,ident)
    doc["threshold"]=d["threshold"];doc["identity_payload"]["X_cal_sha256"]="tampered";mp.write_text(__import__("json").dumps(doc))
    with pytest.raises(ValueError):cr.load_replay(path,ident)

def test_existing_identity_cannot_accept_rewritten_metadata(tmp_path):
    x=np.ones((70,6));y=np.arange(70)%7;ids=np.arange(70);d=cr.derive(np.full((70,7),1/7),y,"probability")
    ident,payload=cr.make_identity(pipeline_sha256="p",role_file_sha256="r",ids=ids,X=x,y=y,kind="probability",helper_sha256="h",dependencies={})
    cr.save_replay(tmp_path,ident,d,{**payload,"task_key":"expected"})
    with pytest.raises(ValueError):cr.save_replay(tmp_path,ident,d,{**payload,"task_key":"changed"})

def test_alias_requires_exact_threshold_provenance():
    p={"threshold":.5,"calibration_n":10,"score_kind":"probability","pipeline_sha256":"p","fit_key":"f"}
    assert cr.alias_matches(dict(p,task_key="a"),p)
    assert not cr.alias_matches(dict(p,threshold=.6),p)

def test_alias_reuse_requires_exact_calibration_cohort_hashes():
    p={"role_file_sha256":"r","calibration_ids_sha256":"i","X_cal_sha256":"x","y_cal_sha256":"y"}
    assert cr.alias_role_matches(p,"r","i","x","y")
    assert not cr.alias_role_matches(p,"r","different","x","y")

def test_alias_gate_checks_cohort_score_rule_class_and_alpha():
    row={"threshold":.5,"calibration_n":10,"score_kind":"probability","nonconformity_rule":"1-p_true",
         "pipeline_sha256":"p","fit_key":"f","role_file_sha256":"r","calibration_ids_sha256":"i",
         "X_cal_sha256":"x","y_cal_sha256":"y","class_order":[0,1,2,3,4,5,6],"alpha":.1}
    doc={k:row[k] for k in ("threshold","calibration_n","score_kind","nonconformity_rule","pipeline_sha256","fit_key")}
    ok=cr.validate_alias(doc,doc,row,"r","i","x","y")
    assert ok["match"] and ok["class_order_basis"]=="same verified fit and pipeline identity"
    assert not cr.validate_alias(doc,doc,row,"r","changed","x","y")["match"]
    assert not cr.validate_alias(dict(doc,score_kind="margin",nonconformity_rule="negative_margin"),doc,row,"r","i","x","y")["match"]
    assert cr.validate_alias(dict(doc,class_order=[0,1,2,3,4,5,6]),doc,row,"r","i","x","y")["match"]
    assert cr.validate_alias(dict(doc,class_order=["A","F","G","K","M","GALAXY","QSO"]),doc,row,"r","i","x","y")["match"]
    assert not cr.validate_alias(dict(doc,class_order=[1,0,2,3,4,5,6]),doc,row,"r","i","x","y")["match"]
    assert not cr.validate_alias(dict(doc,alpha=.2),doc,row,"r","i","x","y")["match"]

def test_summary_requires_every_physical_and_alias():
    assert cr.summarize([{"status":"validated"}],[{"status":"inherited"}])["complete"]
    s=cr.summarize([{"status":"validated"},{"status":"unavailable"}],[{"status":"inherited"}])
    assert not s["complete"] and s["unavailable_physical"]==1 and not s["independent_q_recomputed"]

def test_auditor_replay_hook_uses_only_calibration_fixture(tmp_path):
    class Identity:
        def transform(self,x): return x
    class FixtureEstimator:
        classes_=np.arange(7)
        def predict_proba(self,x):return np.full((len(x),7),1/7,dtype=np.float64)
    runtime=tmp_path/"runtime"; (runtime/"cache/roles").mkdir(parents=True)
    (runtime/"artifacts/eval1").mkdir(parents=True); (runtime/"artifacts/fit1").mkdir(parents=True)
    X=np.arange(42,dtype=np.float64).reshape(7,6); y=np.arange(7,dtype=np.int64); ids=np.arange(100,107)
    np.savez_compressed(runtime/"cache/roles/rep_1.npz",X_cal=X,y_cal=y,calibration_ids=ids)
    from benchmark.models_basic import ClassifierModel
    class ScoreMatrixOnlyForReplay(ClassifierModel):
        def predict_proba(self,x):raise AssertionError("replay must preserve score_matrix-first frozen interface")
    model=ScoreMatrixOnlyForReplay(FixtureEstimator(),"probability"); derived=cr.derive(model.score_matrix(X),y,"probability")
    fitpipe=runtime/"artifacts/fit1/pipeline.joblib"; fitpipe.write_bytes(b"fixture only")
    pipeline_sha=cr.file_sha(fitpipe)
    evdoc={"threshold":derived["threshold"],"calibration_n":7,"score_kind":"probability","fit_key":"fit1","pipeline_sha256":pipeline_sha}
    (runtime/"artifacts/eval1/evaluation.json").write_text(__import__("json").dumps(evdoc))
    ft={"key":"fit1","kind":"fit","rep":1,"experiment":3,"method":"logistic",
        "result":{"result":{"class_counts":[1,1,1,1,1,1,1]}}}
    ev={"key":"eval1","kind":"eval","rep":1,"experiment":3,"fit_key":"fit1","status":"validated_terminal","outcome":"successful"}
    obj=audit.Auditor(runtime,replay_run_nonce="engineering-fixture-run");obj.project=PROJECT_ROOT
    pipe={"model":model,"imputer":Identity(),"scaler":Identity(),"class_counts":[1]*7,"training_rows":7}
    obj._replay_fit_calibrations(ft,{"fit1":ft,"eval1":ev},pipe,fitpipe)
    assert obj.calibration_replay_physical[0]["status"]=="validated"
    row=obj.calibration_replay_physical[0]
    assert row["calibration_n"]==7 and row["rank_k"]==8 and row["supervision_mode"]=="replayed"
    assert obj.calibration_replay_run_id=="engineering-fixture-run"
    events=[__import__("json").loads(x) for x in obj.calibration_replay_phase_ledger_path.read_text().splitlines()]
    assert [x["event"] for x in events]==["start","finish"] and all(x["run_nonce"]=="engineering-fixture-run" for x in events)
    assert events[0]["pid"]==events[1]["pid"] and events[0]["process_start_ticks"]==events[1]["process_start_ticks"]
    assert (runtime/row["nonconformity_path"]).is_file()
    replay_meta=__import__("json").loads((runtime/row["metadata_path"]).read_text())
    assert replay_meta["role_path"]=="cache/roles/rep_1.npz"
    assert replay_meta["pipeline_path"]=="artifacts/fit1/pipeline.joblib"
    progress=__import__("json").loads((runtime/"reports/CALIBRATION_REPLAY_PROGRESS.json").read_text())
    beacon=__import__("json").loads((runtime/"logs/operational/calibration_replay_supervisor_beacon.json").read_text())
    assert progress["state"]=="idle" and "pid" not in progress and progress["current_fit_key"] is None
    assert beacon["state"]=="idle" and beacon["pid"]>0 and beacon["process_start_ticks"] is not None

def test_auditor_reuses_verified_replay_cache_without_loading_pipeline(tmp_path):
    import json, sklearn, joblib, scipy
    from benchmark import models_basic
    runtime=tmp_path/"runtime";(runtime/"cache/roles").mkdir(parents=True);(runtime/"artifacts/eval2").mkdir(parents=True);(runtime/"artifacts/fit2").mkdir(parents=True)
    X=np.arange(42,dtype=np.float64).reshape(7,6);y=np.arange(7,dtype=np.int64);ids=np.arange(200,207)
    rolepath=runtime/"cache/roles/rep_2.npz";np.savez_compressed(rolepath,X_cal=X,y_cal=y,calibration_ids=ids)
    fitpipe=runtime/"artifacts/fit2/pipeline.joblib";fitpipe.write_bytes(b"not deserialized")
    psha=cr.file_sha(fitpipe);scores=np.full((7,7),1/7,dtype=np.float64);d=cr.derive(scores,y,"probability")
    ev={"key":"eval2","kind":"eval","rep":2,"experiment":3,"fit_key":"fit2","status":"validated_terminal","outcome":"successful"}
    doc={"threshold":d["threshold"],"calibration_n":7,"score_kind":"probability","fit_key":"fit2","pipeline_sha256":psha}
    evpath=runtime/"artifacts/eval2/evaluation.json";evpath.write_text(json.dumps(doc));evalsha=cr.file_sha(evpath)
    ft={"key":"fit2","kind":"fit","rep":2,"experiment":3,"method":"logistic","result":{"result":{"class_counts":[1]*7}}}
    source_sha=cr.file_sha(models_basic.__file__);contract="frozen ClassifierModel estimator.classes_"
    frozen_report=PROJECT_ROOT/"benchmark/results/e1_report_validated_no_bootstrap.json"
    deps={"numpy":np.__version__,"scoring_module_sha256":source_sha,"frozen_source_report_sha256":cr.file_sha(frozen_report),"class_order_contract":contract,"fit_class_counts":[1]*7,
          "scikit_learn":sklearn.__version__,"joblib":joblib.__version__,"scipy":scipy.__version__,"source_evaluation_sha256":evalsha,"calibration_json_sha256":None}
    ident,idoc=cr.make_identity(pipeline_sha256=psha,role_file_sha256=cr.file_sha(rolepath),ids=ids,X=X,y=y,kind="probability",
       helper_sha256=cr.file_sha(Path(__file__).parent.parent/"source/calibration_replay.py"),dependencies=deps)
    path=cr.save_replay(runtime/"artifacts/calibration_replay",ident,d,{**idoc,"task_key":"eval2","fit_key":"fit2","role_path":"cache/roles/rep_2.npz",
       "pipeline_path":"artifacts/fit2/pipeline.joblib","source_evaluation_sha256":evalsha,"calibration_json_sha256":None,"scoring_module_sha256":source_sha,
       "frozen_source_report_sha256":cr.file_sha(frozen_report),"class_order_source":contract})
    accepted={"schema_version":"lamost-calibration-replay-accepted-prior-receipts/1",
              "entries":[{"identity":ident,"receipt_sha256":"a"*64,"audit_sha256":"prior-audit"}]}
    unaccepted=audit.Auditor(runtime);unaccepted.project=PROJECT_ROOT
    assert not unaccepted._restore_replay_cache_for_fit(ft,{"fit2":ft,"eval2":ev})
    obj=audit.Auditor(runtime,accepted_prior_receipts=accepted);obj.project=PROJECT_ROOT;assert obj._restore_replay_cache_for_fit(ft,{"fit2":ft,"eval2":ev})
    assert obj.calibration_replay_physical[0]["supervision_mode"]=="cache_reuse"
    assert obj.calibration_replay_physical[0]["prior_receipt_sha256"]=="a"*64
    assert obj.calibration_replay_physical[0]["status"]=="validated" and path.is_dir()
    assert cr.load_replay(path,ident)["metadata"]["role_path"]=="cache/roles/rep_2.npz"
    assert cr.load_replay(path,ident)["metadata"]["pipeline_path"]=="artifacts/fit2/pipeline.joblib"
    # Copy identical tiny inputs and the immutable q proof to a different extraction root.
    import shutil
    relocated=tmp_path/"relocated"/"runtime";(relocated/"cache/roles").mkdir(parents=True)
    (relocated/"artifacts/fit2").mkdir(parents=True);(relocated/"artifacts/eval2").mkdir(parents=True)
    shutil.copy2(rolepath,relocated/"cache/roles/rep_2.npz")
    shutil.copy2(fitpipe,relocated/"artifacts/fit2/pipeline.joblib")
    shutil.copy2(evpath,relocated/"artifacts/eval2/evaluation.json")
    relocated_path=relocated/"artifacts/calibration_replay"/ident
    relocated_path.parent.mkdir(parents=True);shutil.copytree(path,relocated_path)
    relocated_audit=audit.Auditor(relocated,accepted_prior_receipts=accepted);relocated_audit.project=PROJECT_ROOT
    assert relocated_audit._restore_replay_cache_for_fit(ft,{"fit2":ft,"eval2":ev})
    assert relocated_audit.calibration_replay_physical[0]["identity"]==ident
    doc["threshold"]=.123;evpath.write_text(json.dumps(doc))
    obj2=audit.Auditor(runtime,accepted_prior_receipts=accepted);obj2.project=PROJECT_ROOT
    assert not obj2._restore_replay_cache_for_fit(ft,{"fit2":ft,"eval2":ev})


def _supervision_fixture(mode="replayed",status="complete",q_complete=True):
    import hashlib,json
    nonce="parent-run-0001"; phase_id="phase-01"; fit="fit-a"; task="eval-a"; identity="d"*64
    prior="b"*64 if mode=="cache_reuse" else None
    common={"schema_version":"lamost-calibration-replay-phase-ledger/1","run_nonce":nonce,
      "phase_id":phase_id,"mode":mode,"phase":"calibration_score_replay" if mode=="replayed" else "cache_reuse",
      "fit_key":fit,"task_keys":[task],"prior_receipts":{task:prior} if prior else {},
      "pid":1234,"process_start_ticks":9876}
    start={**common,"event":"start","monotonic":10.0,"utc":"2026-10-26T10:00:00Z"}
    finish={**common,"event":"finish","monotonic":11.0,"utc":"2026-10-26T10:00:01Z"}
    lines=[json.dumps(x,sort_keys=True,separators=(",",":")) for x in (start,finish)]
    ledger=("\n".join(lines)+"\n").encode(); sha=lambda x:hashlib.sha256(x.encode()).hexdigest()
    alias={"task_key":"alias-a","source_key":task,"physical_source_key":task,"source_identity":identity,"status":"inherited",
      "threshold_match":True,"calibration_role_match":True,"score_kind_match":True,"nonconformity_rule_match":True,"class_order_match":True,"alpha_match":True}
    audit_doc={"schema_version":"lamost-calibration-replay-audit/1","complete":False,"registry_snapshot_sha256":"registry-a",
      "replay_run_nonce":nonce,"phase_ledger_sha256":hashlib.sha256(ledger).hexdigest(),
      "q_replay_coverage_complete":q_complete,
      "records":[{"task_key":task,"fit_key":fit,"identity":identity,"metadata_sha256":"e"*64,
        "nonconformity_file_sha256":"f"*64,"status":"validated","supervision_mode":mode,
        "prior_receipt_sha256":prior},alias]}
    binding={"task_key":task,"fit_key":fit,"identity":identity,"metadata_sha256":"e"*64,"nonconformity_file_sha256":"f"*64}
    if prior: binding["prior_receipt_sha256"]=prior
    phase={"phase_id":phase_id,"mode":mode,"phase":common["phase"],"fit_key":fit,"task_keys":[task],"run_nonce":nonce,
      "status":"passed","started_utc":"2026-10-26T10:00:00Z","finished_utc":"2026-10-26T10:00:01Z",
      "duration_seconds":1.0,"measurement_method":"parent_process_tree_rss","peak_process_tree_rss_bytes":1024,
      "process_identity_verified":True,"cap_enforced":True,"exit_code":0,
      "phase_start_event_sha256":sha(lines[0]),"phase_finish_event_sha256":sha(lines[1]),"identity_bindings":[binding]}
    if prior:
      phase.update({"prior_receipt_sha256":prior,"artifact_integrity_verified":True})
    receipt={"schema_version":"lamost-calibration-replay-supervision/1","status":status,
      "audit_sha256":"audit-sha","registry_snapshot_sha256":"registry-a","run_nonce":nonce,
      "audit_process_exit_code":0,"audit_process_exit_verified":True,"finalized_after_audit_exit":True,
      "phase_ledger_sha256":hashlib.sha256(ledger).hexdigest(),"limits":{"wall_seconds":600,"rss_bytes":10*1024**3},
      "phase_records":[phase]}
    return audit_doc,receipt,ledger,prior,identity

def test_external_supervision_receipt_qualifies_only_hash_bound_completed_audit(tmp_path):
    import json,hashlib
    doc,receipt,ledger,_,_= _supervision_fixture()
    got=cr.verify_supervision_receipt(doc,receipt,"audit-sha",phase_ledger=ledger)
    assert got["valid"] and got["qualified_complete"]
    assert not cr.verify_supervision_receipt(doc,receipt,"wrong",phase_ledger=ledger)["valid"]
    bad_alias={**doc,"records":[doc["records"][0],{**doc["records"][1],"alpha_match":False}]}
    assert not cr.verify_supervision_receipt(bad_alias,receipt,"audit-sha",phase_ledger=ledger)["valid"]
    changed=bytearray(ledger);changed[0]^=1
    assert not cr.verify_supervision_receipt(doc,receipt,"audit-sha",phase_ledger=bytes(changed))["valid"]
    bad={**receipt,"phase_records":[{**receipt["phase_records"][0],"peak_process_tree_rss_bytes":10*1024**3+1}]}
    assert not cr.verify_supervision_receipt(doc,bad,"audit-sha",phase_ledger=ledger)["valid"]
    short={**receipt,"phase_records":[{**receipt["phase_records"][0],"duration_seconds":.5}]}
    assert "phase_duration_ledger_mismatch" in cr.verify_supervision_receipt(doc,short,"audit-sha",phase_ledger=ledger)["reasons"]
    events=[json.loads(line) for line in ledger.splitlines()]
    events[1]["monotonic"]=events[0]["monotonic"]+601
    lines=[json.dumps(x,sort_keys=True,separators=(",",":")) for x in events]
    long_ledger=("\n".join(lines)+"\n").encode(); longsha=lambda x:hashlib.sha256(x.encode()).hexdigest()
    long_digest=hashlib.sha256(long_ledger).hexdigest()
    oversized_doc={**doc,"phase_ledger_sha256":long_digest}
    oversized_receipt={**receipt,"phase_ledger_sha256":long_digest,
      "phase_records":[{**receipt["phase_records"][0],"phase_finish_event_sha256":longsha(lines[1])}]}
    reasons=cr.verify_supervision_receipt(oversized_doc,oversized_receipt,"audit-sha",phase_ledger=long_ledger)["reasons"]
    assert "phase_ledger_wall_cap_failed" in reasons
    audit_path=tmp_path/"CALIBRATION_REPLAY_AUDIT.json";receipt_path=tmp_path/"CALIBRATION_REPLAY_SUPERVISION.json"
    ledger_path=tmp_path/"phase.jsonl";out=tmp_path/"CALIBRATION_REPLAY_QUALIFICATION.json"
    raw=json.dumps(doc,sort_keys=True).encode(); audit_path.write_bytes(raw)
    receipt["audit_sha256"]=hashlib.sha256(raw).hexdigest();receipt_path.write_text(json.dumps(receipt))
    ledger_path.write_bytes(ledger)
    result=cr.write_qualification_report(audit_path,receipt_path,out,phase_ledger_path=ledger_path)
    assert result["qualified_complete"] and audit_path.read_bytes()==raw and json.loads(out.read_text())["audit_sha256"]==hashlib.sha256(raw).hexdigest()

def test_verified_cache_lineage_required_for_cached_q_qualification():
    doc,receipt,ledger,prior,identity=_supervision_fixture("cache_reuse")
    assert not cr.verify_supervision_receipt(doc,receipt,"audit-sha",phase_ledger=ledger)["valid"]
    accepted={prior:{identity}}
    assert cr.verify_supervision_receipt(doc,receipt,"audit-sha",accepted_prior_receipts=accepted,phase_ledger=ledger)["qualified_complete"]
    changed={**receipt,"phase_records":[{**receipt["phase_records"][0],"prior_receipt_sha256":"c"*64}]}
    assert not cr.verify_supervision_receipt(doc,changed,"audit-sha",accepted_prior_receipts=accepted,phase_ledger=ledger)["valid"]

def test_partial_audit_receipt_never_qualifies_complete():
    import hashlib
    doc={"schema_version":"lamost-calibration-replay-audit/1","complete":False,"registry_snapshot_sha256":"r","replay_run_nonce":"n","phase_ledger_sha256":hashlib.sha256(b"").hexdigest(),
      "q_replay_coverage_complete":False,"records":[{"task_key":"eval-missing","fit_key":"fit","status":"unavailable"}]}
    receipt={"schema_version":"lamost-calibration-replay-supervision/1","status":"partial","audit_sha256":"a",
      "registry_snapshot_sha256":"r","run_nonce":"n","audit_process_exit_code":0,"audit_process_exit_verified":True,
      "finalized_after_audit_exit":True,"phase_ledger_sha256":hashlib.sha256(b"").hexdigest(),
      "limits":{"wall_seconds":600,"rss_bytes":10*1024**3},"phase_records":[]}
    got=cr.verify_supervision_receipt(doc,receipt,"a",phase_ledger=b"")
    assert got["valid"] and not got["qualified_complete"] and not got["q_replay_coverage_complete"]
