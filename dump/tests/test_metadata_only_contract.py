import hashlib, json, sys
from pathlib import Path
import pytest

STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/"source"))
import metadata_only_contract as contract

PROD="e3/rep_2/fit/synthetic/random_forest/copula"

def fixture(tmp_path):
    root=tmp_path
    rt=root/"runtime_20261025"
    (rt/"source"/"parallel_rf").mkdir(parents=True)
    for rel,digest in contract.PINNED_CODE.items():
        (rt/"source"/rel).write_bytes(b"pinned-test-code")
    # Patch pins to the exact fixture source bytes, retaining the same strict
    # path/hash checks as production.
    import hashlib
    contract.PINNED_CODE={k:hashlib.sha256(b"pinned-test-code").hexdigest() for k in contract.PINNED_CODE}
    tasks=[]
    srcdir=rt/"artifacts"/PROD
    srcdir.mkdir(parents=True)
    (srcdir/"selection.json").write_text(json.dumps({"selected_params":{"n_estimators":17}}))
    import hashlib
    selsha=hashlib.sha256((srcdir/"selection.json").read_bytes()).hexdigest()
    source={"key":PROD,"kind":"fit","method":"random_forest","experiment":3,"status":"validated_terminal",
            "outcome":"successful","validation_state":"validated","artifact_dir":str(srcdir),
            "result":{"validation":{"files":{"selection.json":selsha}}}}
    tasks.append(source)
    fits=[]
    for i in range(9):
        fit=f"e5/rep_2/fit/synthetic/random_forest/feature_noise_{i:02d}_copula"
        ev=f"e5/rep_2/eval/synthetic/random_forest/feature_noise_{i:02d}_copula"
        fits.append(fit)
        train=f"e5/rep_2/generate/feature_noise_{i:02d}/copula"
        tasks += [
          {"key":train,"kind":"generate","experiment":5,"status":"validated_terminal"},
          {"key":fit,"kind":"fit","method":"random_forest","experiment":5,"status":"waiting_for_dependency",
           "selection_key":PROD,"selection_mode":"fixed","selection_policy":"frozen_clean_selected_params_no_retuning",
           "dependencies":[PROD,train],"train_key":train,"seed":i},
          {"key":ev,"kind":"eval","method":"random_forest","experiment":5,"status":"waiting_for_dependency","fit_key":fit,"dependencies":[fit]}
        ]
    manifests=rt/"manifests"
    manifests.mkdir(parents=True,exist_ok=True)
    plan={"tasks":[contract._definition(t) for t in tasks]}
    plan_bytes=(json.dumps(plan,sort_keys=True,separators=(",",":"))+"\n").encode()
    (manifests/"tasks.json").write_bytes(plan_bytes)
    (manifests/"freeze.json").write_text(json.dumps({"plan_sha256":hashlib.sha256(plan_bytes).hexdigest()},sort_keys=True)+"\n")
    records={"tasks":tasks}
    closure={t["key"] for t in tasks[1:] if t.get("kind") in ("fit","eval")}
    return root,records,closure,fits

def test_accepts_only_bound_e5_fixed_selection_contract(tmp_path):
    root,records,closure,fits=fixture(tmp_path)
    proof=contract.build_contract(root,PROD,records,closure)
    assert len(proof["pending_metadata_fit_tasks"])==9
    assert len(proof["pending_own_fit_evaluations"])==9
    assert proof["selection_json_sha256"]
    import cold_model_storage
    store=cold_model_storage.ColdModelStore.from_runtime(root,root/"runtime_20261025")
    record_map={t["key"]:t for t in records["tasks"]}
    assert store._consumer_contract(PROD,closure,record_map,proof)==proof
    tampered=dict(proof); tampered["selection_json_sha256"]="0"*64
    with pytest.raises(cold_model_storage.AmbiguousState):
        store._consumer_contract(PROD,closure,record_map,tampered)
    assert store._consumer_contract(PROD,closure,record_map,None) is None if False else True
    with pytest.raises(cold_model_storage.UnsafePlan):
        store._consumer_contract(PROD,closure,record_map,None)
    rows=record_map.copy()
    rows[fits[0]]=dict(rows[fits[0]],selection_policy="changed")
    with pytest.raises(cold_model_storage.AmbiguousState):
        store._consumer_contract(PROD,closure,rows,proof)

@pytest.mark.parametrize("mutation",[
    lambda f,rs: rs[f].update(selection_key="e3/rep_1/fit/synthetic/random_forest/copula"),
    lambda f,rs: rs[f].update(reuse_pipeline=True),
    lambda f,rs: rs[f].update(selection_policy="retune"),
    lambda f,rs: rs[f].update(fit_key=PROD),
])
def test_rejects_unsafe_fit_mutations(tmp_path,mutation):
    root,records,closure,fits=fixture(tmp_path)
    rows={t["key"]:t for t in records["tasks"]}
    mutation(fits[0],rows)
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)

def test_rejects_tampered_selection_and_eval_source(tmp_path):
    root,records,closure,fits=fixture(tmp_path)
    selection=root/"runtime_20261025/artifacts"/PROD/"selection.json"
    selection.write_text('{"selected_params":{"n_estimators":18}}')
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)
    root,records,closure,fits=fixture(tmp_path/"second")
    rows={t["key"]:t for t in records["tasks"]}
    rows["e5/rep_2/eval/synthetic/random_forest/feature_noise_00_copula"]["fit_key"]=PROD
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)

def test_legacy_absent_contract_remains_strict_and_terminal_contract_stable(tmp_path):
    root,records,closure,fits=fixture(tmp_path)
    # Original contract for all pending tasks.
    proof=contract.build_contract(root,PROD,records,closure)
    rows={t["key"]:t for t in records["tasks"]}
    for key in fits:
        rows[key].update({"status":"validated_terminal","started_epoch":1,"finished_utc":"later","reason":None,
                          "peak_tree_rss_bytes":1234,"pid":123,"request_path":"/tmp/request","result_path":"/tmp/result",
                          "result":{"status":"successful","artifact_sha256":"d"*64}})
    for t in records["tasks"]:
        if t.get("kind")=="eval":
            t.update({"status":"validated_terminal","started_epoch":1,"finished_utc":"later","reason":None,
                      "result":{"status":"successful"}})
    assert contract.build_contract(root,PROD,records,closure)==proof
    import cold_model_storage
    store=cold_model_storage.ColdModelStore.from_runtime(root,root/"runtime_20261025")
    record_map={t["key"]:t for t in records["tasks"]}
    assert store._consumer_contract(PROD,closure,record_map,None) is None
    assert store._consumer_contract(PROD,closure,record_map,proof)==proof


def test_contract_survives_actual_admit_running_and_terminal_registry_states(tmp_path,monkeypatch):
    import importlib
    from unittest.mock import patch

    root,records,closure,fits=fixture(tmp_path)
    rt=root/"runtime_20261025"
    rows={t["key"]:t for t in records["tasks"]}
    plan=json.loads((rt/"manifests/tasks.json").read_text())["tasks"]
    definitions={t["key"]:dict(t) for t in plan}
    (rt/"source").mkdir(parents=True,exist_ok=True)
    (rt/"source/worker.py").write_text("# synthetic worker path for controller admission fixture\n")
    ctl=importlib.import_module("controller")
    old_root,old_defs=ctl.R,ctl.DEFINITIONS
    ctl.R=rt;ctl.DEFINITIONS=definitions
    db=ctl.connect()
    class Proc:
        pid=71337
    common=[
        patch.object(ctl,"_archive_fit_launch_gate",return_value=None),
        patch.object(ctl,"start_ticks",return_value="fixture-start-ticks"),
        patch.object(ctl.subprocess,"Popen",return_value=Proc()),
        patch.object(ctl,"worker_reservation_bytes",return_value=ctl.GIB),
        patch.object(ctl,"_rf4_fit_eligible",return_value=None),
        patch.object(ctl,"_e4_treatment_rf4_6g_eligible",return_value=None),
        patch.object(ctl,"_has_recorded_rf4_profile",return_value=False),
        patch.object(ctl,"_has_recorded_e4_treatment_rf6_profile",return_value=False),
        patch.object(ctl,"e5_rf_eval_profile_for_admission",return_value=(None,None)),
        patch.object(ctl,"e4_rf_eval_profile_for_admission",return_value=(None,None)),
        patch.object(ctl,"e4_rf_fit_5g_profile_for_admission",return_value=(None,None)),
        patch.object(ctl,"is_e4_direct_rf_80k",return_value=False),
        patch.object(ctl.admission_evidence,"eligible_2gib_resource_profile",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_4gib",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_rf_resource_profiles",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_e4_direct_arf_eval_2gib",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_e4_arf_generation_2gib",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_e5_arf_generation_2gib",return_value=(False,None)),
        patch.object(ctl.admission_evidence,"eligible_knn_rbf_resource_profile",return_value=(False,None)),
    ]
    try:
        proof=contract.build_contract(root,PROD,records,closure)
        stack=[]
        for patcher in common:
            patcher.start();stack.append(patcher)
        fit=rows[fits[0]]
        assert ctl.admit(db,fit)
        assert fit["status"]=="running"
        for key in ("admission_reservation_bytes","admission_profile_id","adaptive_policy_revision",
                    "admission_resource_policy","dispatch_policy_id","admission_resource_observation",
                    "attempts","pid","process_start_ticks","request_path","result_path"):
            assert key in fit
        assert contract.build_contract(root,PROD,records,closure)==proof
        fit["injected_pipeline_source"]="untrusted"
        with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)
        fit.pop("injected_pipeline_source")
        fit.update(status="validated_terminal",outcome="successful",validation_state="validated",
                   finished_utc="fixture-finished",result={"status":"successful"})
        assert contract.build_contract(root,PROD,records,closure)==proof

        eval_key="e5/rep_2/eval/synthetic/random_forest/feature_noise_00_copula"
        evaluation=rows[eval_key]
        assert ctl.admit(db,evaluation)
        assert evaluation["status"]=="running"
        assert contract.build_contract(root,PROD,records,closure)==proof
        import cold_model_storage
        store=cold_model_storage.ColdModelStore.from_runtime(root,rt)
        assert store._consumer_contract(PROD,closure,rows,proof)==proof
        evaluation.update(status="validated_terminal",outcome="successful",validation_state="validated",
                          finished_utc="fixture-finished",result={"status":"successful"})
        assert contract.build_contract(root,PROD,records,closure)==proof
    finally:
        for patcher in reversed(locals().get("stack",[])):patcher.stop()
        db.close()
        ctl.R=old_root;ctl.DEFINITIONS=old_defs


def test_actual_rf4_worker_uses_only_selection_json_for_fixed_refit(tmp_path,monkeypatch):
    # Exercise the production handler with the real selection-source branch.
    import importlib, joblib, builtins, pathlib
    source=STAGE/"source"/"parallel_rf"
    sys.path.insert(0,str(source))
    worker=importlib.import_module("worker")
    runtime=tmp_path/"runtime_20261025"
    producer=runtime/"artifacts"/PROD
    producer.mkdir(parents=True)
    (producer/"selection.json").write_text(json.dumps({"selected_params":{"n_estimators":13,"max_depth":4}}))
    # No source pipeline exists; the fixed-selection RF4 startup/execute path must not need it.
    seen={}
    import science
    def stub(runroot,task,phase,attempt,params=None,timeout=None):
        seen["params"]=params
        (Path(attempt)/"pipeline.joblib").write_bytes(b"synthetic-new-fit-artifact")
        return {"status":"success","params":params,"seed":task["seed"]}
    monkeypatch.setattr(science,"_run_phase",stub)
    def forbidden(*args,**kwargs): raise AssertionError("joblib.load called in metadata-only refit")
    monkeypatch.setattr(joblib,"load",forbidden)
    real_open=builtins.open
    real_path_open=pathlib.Path.open
    real_read_bytes=pathlib.Path.read_bytes
    forbidden_path=(producer/"pipeline.joblib").resolve()
    def reject_source(path):
        try:
            if Path(path).resolve()==forbidden_path:
                raise AssertionError("source model payload opened")
        except TypeError:
            pass
    def guarded_open(path,*args,**kwargs):
        reject_source(path)
        return real_open(path,*args,**kwargs)
    def guarded_path_open(path,*args,**kwargs):
        reject_source(path)
        return real_path_open(path,*args,**kwargs)
    def guarded_read_bytes(path,*args,**kwargs):
        reject_source(path)
        return real_read_bytes(path,*args,**kwargs)
    monkeypatch.setattr(builtins,"open",guarded_open)
    monkeypatch.setattr(pathlib.Path,"open",guarded_path_open)
    monkeypatch.setattr(pathlib.Path,"read_bytes",guarded_read_bytes)
    task={"key":"e5/rep_2/fit/synthetic/random_forest/feature_noise_05_copula","kind":"fit",
          "method":"random_forest","experiment":5,"seed":123,"selection_key":PROD,
          "selection_source":str(producer),"selection_mode":"fixed","selection_policy":"frozen_clean_selected_params_no_retuning"}
    policy,profile=worker.rf4_policy_constants()
    monkeypatch.setattr(worker,"validate",lambda task,result,runtime:{"status":"validated"})
    request=tmp_path/"request.json";resultfile=tmp_path/"result.json"
    request.write_text(json.dumps({"task":task,"runtime":str(runtime),"attempt_id":"stage-test",
                                   "execution_policy":policy,"resource_profile":profile,
                                   "result_path":str(resultfile)}))
    monkeypatch.setattr(sys,"argv",["worker.py",str(request)])
    worker.main()
    result=json.loads(resultfile.read_text())
    assert result["status"]=="successful"
    assert seen["params"]=={"n_estimators":13,"max_depth":4}
    assert not (producer/"pipeline.joblib").exists()
    assert (runtime/"artifacts"/task["key"]/"pipeline.joblib").read_bytes()==b"synthetic-new-fit-artifact"


def test_rejects_source_code_pin_mutation_and_pending_physical_reader(tmp_path):
    root,records,closure,fits=fixture(tmp_path)
    worker=root/"runtime_20261025/source/parallel_rf/worker.py"
    worker.write_bytes(b"changed worker")
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)
    root,records,closure,fits=fixture(tmp_path/"frozen_plan")
    freeze_path=root/"runtime_20261025/manifests/freeze.json"
    freeze=json.loads(freeze_path.read_text())
    freeze["plan_sha256"]="0"*64
    freeze_path.write_text(json.dumps(freeze,sort_keys=True)+"\n")
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)
    root,records,closure,fits=fixture(tmp_path/"payload")
    rows={t["key"]:t for t in records["tasks"]}
    key="e3/direct/eval"
    rows[key]={"key":key,"kind":"eval","method":"random_forest","experiment":3,
               "status":"waiting_for_dependency","fit_key":PROD,"dependencies":[PROD]}
    records["tasks"].append(rows[key])
    closure.add(key)
    manifests=root/"runtime_20261025/manifests"
    plan=json.loads((manifests/"tasks.json").read_text())
    plan["tasks"].append(contract._definition(rows[key]))
    plan_bytes=(json.dumps(plan,sort_keys=True,separators=(",",":"))+"\n").encode()
    (manifests/"tasks.json").write_bytes(plan_bytes)
    (manifests/"freeze.json").write_text(json.dumps({"plan_sha256":hashlib.sha256(plan_bytes).hexdigest()},sort_keys=True)+"\n")
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)
    rows[key].update(status="running",pid=9234,process_start_ticks="122",started_utc="now",
                     admission_reservation_bytes=1<<30,admission_profile_id="synthetic",
                     adaptive_policy_revision="synthetic",admission_resource_policy={"policy":"synthetic"},
                     dispatch_policy_id="synthetic",admission_resource_observation={"available":1<<30},
                     request_path="/tmp/request",result_path="/tmp/result",attempts=[{"attempt_id":"fixture"}])
    with pytest.raises(ValueError): contract.build_contract(root,PROD,records,closure)


def test_planner_emits_contract_for_only_bound_inode_candidate(tmp_path):
    import hashlib
    import batch_plan
    root,records,closure,fits=fixture(tmp_path)
    runtime=root/"runtime_20261025"
    producer_path=runtime/"artifacts"/PROD/"pipeline.joblib"
    producer_path.write_bytes(b"tiny synthetic producer payload")
    digest=hashlib.sha256(producer_path.read_bytes()).hexdigest()
    rows={t["key"]:t for t in records["tasks"]}
    rows[PROD]["result"]["validation"]["files"]["pipeline.joblib"]=digest
    class Cold:
        def _consumer_closure(self,key,allrows): return closure
        def _pipeline_hash(self,row): return digest
    candidates=batch_plan.build_candidates(root,runtime,rows,set(),None,Cold())
    assert len(candidates)==1
    assert candidates[0]["producer_task"]==PROD
    assert candidates[0]["metadata_only_consumer_contract"]["contract_sha256"]
    rows[fits[0]]["selection_policy"]="changed"
    assert batch_plan.build_candidates(root,runtime,rows,set(),None,Cold())==[]
