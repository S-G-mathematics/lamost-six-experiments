import collections, importlib.util, json, sys
from pathlib import Path
import pytest

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "source"))
spec = importlib.util.spec_from_file_location("staged_finalize_project_scope", R / "source" / "finalize_project.py")
fp = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fp
spec.loader.exec_module(fp)

AMP = "manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json"
APP = "reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json"
PLAN_SHA = "a" * 64

def _task(key, exp, condition, scientific=True, outcome=None, rep=1, method="random_forest", route="direct"):
    return {"key": key, "experiment": exp, "rep": rep, "scientific_case": scientific,
            "kind": "eval" if "/eval/" in key else "fit", "method": method, "condition": condition,
            "route": route, "mode": "direct", "target_class": 0, "ratio": 0.5,
            "treatment": None, "mechanism": None, "rate": None, "generator": None,
            "budget": None, "outcome": outcome}

def _row(task, outcome, score=None):
    return {k: task.get(k) for k in ("key", "experiment", "rep", "method", "condition", "route", "mode", "target_class", "ratio", "treatment", "mechanism", "rate", "generator")} | {"outcome": outcome, "balanced_accuracy": score, "coverage": None, "mean_set_size": None}

def scope_fixture(tmp_path):
    runtime = tmp_path / "runtime_20261025"
    (runtime / "manifests").mkdir(parents=True)
    (runtime / "reports").mkdir()
    tasks=[]; selected=[]; stopped=[]; closure=[]; pending_closure=[]; excluded=[]; ledger=[]
    selected_counts=collections.Counter()
    for i in range(45):
        exp=4 if i<14 else 5; key=f"e{exp}/rep_1/eval/direct/random_forest/selected_{i}"
        task=_task(key,exp,f"selected_{i}"); tasks.append(task); selected.append(key); closure.append(key); pending_closure.append(key); selected_counts[str(exp)]+=1
        outcome="successful" if i<30 else "scientific_failure" if i<35 else "unsupported" if i<38 else "unavailable_dependency"
        ledger.append(_row(task,outcome,0.5 if outcome=="successful" else None))
        dep=f"e{exp}/rep_1/fit/direct/random_forest/selected_{i}"; tasks.append(_task(dep,exp,f"selected_{i}",scientific=False)); closure.append(dep); pending_closure.append(dep)
    stopped_counts=collections.Counter()
    for i in range(168):
        exp=4 if i<67 else 5; key=f"e{exp}/rep_2/eval/direct/random_forest/stopped_{i}"
        task=_task(key,exp,f"stopped_{i}",rep=2); tasks.append(task); stopped.append(key); excluded.append(key); stopped_counts[str(exp)]+=1
        ledger.append(_row(task,"user_stopped"))
    for i in range(77):
        key=f"e4/rep_1/fit/shared/terminal_closure_{i}";tasks.append(_task(key,4,f"terminal_closure_{i}",scientific=False));closure.append(key)
    for i in range(2610):
        key=f"e3/rep_{1+i%3}/eval/direct/filler_{i}";task=_task(key,3,f"filler_{i}",method="logistic_regression",rep=1+i%3)
        tasks.append(task);ledger.append(_row(task,"successful",0.4))
    for i in range(166):
        key=f"e5/rep_1/fit/direct/extra_{i}";tasks.append(_task(key,5,f"extra_{i}",scientific=False));excluded.append(key)
    while len(tasks)<6270:
        i=len(tasks);tasks.append(_task(f"ops/task_{i}",0,f"ops_{i}",scientific=False))
    plan={"plan_sha256":PLAN_SHA,"tasks":tasks};(runtime/"manifests/tasks.json").write_text(json.dumps(plan),encoding="utf-8")
    counts={"selected_pending_scientific":45,"user_stopped_scientific":168,"selected_pending_tasks":90,"user_stopped_tasks":334}
    byexp={e:{"selected_pending_scientific":selected_counts[e],"user_stopped_scientific":stopped_counts[e]} for e in ("4","5")}
    amendment={"schema":"lamost-user-single-evaluation-scope-amendment/1","original_plan_sha256":PLAN_SHA,
      "original_task_count":6270,"original_scientific_count":2823,"axes":["experiment","method","condition","route"],
      "selected_evaluation_keys":selected,"user_stopped_scientific_keys":stopped,
      "selected_dependency_closure":closure,"selected_pending_dependency_closure_keys":pending_closure,
      "pending_dependency_closure_count":90,"excluded_nonterminal_task_keys":excluded,"excluded_nonterminal_task_count":334,
      "user_stopped_scientific_count":168,"counts_by_experiment":byexp,"no_metric_values_read":True,"preserves_all_prior_outcomes":True}
    ap=runtime/AMP;ap.write_text(json.dumps(amendment,sort_keys=True),encoding="utf-8")
    app={"schema":"lamost-user-scope-amendment-application/1","status":"applied_and_verified",
      "amendment_path":str(ap.resolve()),"amendment_sha256":fp.sha_file(ap),"original_plan_sha256":PLAN_SHA,
      "original_plan_unchanged":True,"existing_terminal_unchanged":True,"only_closure_pending_proof":True,
      "counts":counts,"by_experiment":byexp,"applied_utc":"2026-10-29T00:00:00Z"}
    (runtime/APP).write_text(json.dumps(app,sort_keys=True),encoding="utf-8")
    return runtime, {"plan_sha256":PLAN_SHA}, ledger, selected, stopped

def test_applied_amendment_receipt_binds_fixed_counts_and_selected_outcomes(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    info=fp._scope_amendment_info(runtime,terminal,ledger)
    assert info["selected_count"]==45 and info["stopped_count"]==168
    assert info["selected_outcomes"]=={"successful":30,"scientific_failure":5,"unsupported":3,"unavailable_dependency":7}
    assert info["stopped_by_experiment"]=={"4":67,"5":101}

def test_coverage_splits_user_stopped_from_pending_idempotently(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    rd=runtime/"reports";fp.write_csv(rd/"planned_case_ledger.csv",ledger)
    groups=collections.Counter(fp._scope_group_tuple(r) for r in ledger if r["outcome"]=="user_stopped")
    summary=[]
    for group,n in groups.items():
        row=dict(zip(fp._REPORT_GROUP_FIELDS,group));row.update({"planned":3,"successful":1,"failed_or_interrupted":0,"unsupported":0,"unavailable_dependency":0,"pending_or_active":n})
        summary.append(row)
    fp.write_csv(rd/"experiment_outcome_coverage.csv",summary)
    info=fp._split_user_stopped_coverage(runtime,terminal)
    out=fp.csvrows(rd/"experiment_outcome_coverage.csv")
    assert info["stopped_count"]==168 and sum(int(r["user_stopped"]) for r in out)==168
    assert sum(int(r["pending_or_active"]) for r in out)==0
    fp._split_user_stopped_coverage(runtime,terminal)
    out2=fp.csvrows(rd/"experiment_outcome_coverage.csv")
    assert sum(int(r["user_stopped"]) for r in out2)==168 and sum(int(r["pending_or_active"]) for r in out2)==0

def test_changed_stopped_key_status_fails_closed(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    ledger[45]["outcome"]="scientific_failure"
    with pytest.raises(fp.EvidenceError,match="not recorded user_stopped"):
        fp._scope_amendment_info(runtime,terminal,ledger)

def test_missing_application_receipt_fails_closed(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    (runtime/APP).unlink()
    with pytest.raises(fp.EvidenceError,match="pair is incomplete"):
        fp._scope_amendment_info(runtime,terminal,ledger)

def test_scope_counts_or_amendment_hash_mutation_rejects(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    ap=runtime/AMP;amendment=json.loads(ap.read_text());amendment["selected_pending_dependency_closure_keys"].pop()
    ap.write_text(json.dumps(amendment))
    with pytest.raises(fp.EvidenceError,match="closure counts differ"):
        fp._scope_amendment_info(runtime,terminal,ledger)
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path/"app_counts")
    p=runtime/APP;app=json.loads(p.read_text());app["counts"]["user_stopped_tasks"]=333;p.write_text(json.dumps(app))
    with pytest.raises(fp.EvidenceError,match="counts differ"):
        fp._scope_amendment_info(runtime,terminal,ledger)

def test_user_stopped_without_scope_receipt_is_not_silently_pending(tmp_path):
    runtime=tmp_path/"runtime_20261025";(runtime/"reports").mkdir(parents=True)
    ledger=[{"key":"e4/rep_1/eval/x","experiment":"4","outcome":"user_stopped"}]
    fp.write_csv(runtime/"reports/planned_case_ledger.csv",ledger)
    with pytest.raises(fp.EvidenceError,match="require the applied scope amendment"):
        fp._split_user_stopped_coverage(runtime,{"outcomes":{}})

def test_scope_disclosure_keeps_planned_denominator_and_reports_actual_rep_counts(tmp_path):
    runtime,terminal,ledger,selected,stopped=scope_fixture(tmp_path)
    info=fp._scope_amendment_info(runtime,terminal,ledger)
    lines=fp._single_eval_scope_report_lines(info)
    text=" ".join(lines)
    assert "original 6,270-task DAG and 2,823 scientific-case denominator remain unchanged" in text
    assert "one evaluation per unique method/condition group" in text
    assert "one evaluation each" in text and "do not establish replication-based uncertainty" in text
    rep=fp._repetition_outcome_rows(ledger)
    assert len(rep)==7
    assert sum(row[6] for row in rep)==168


def test_figure_denominators_preserve_multiple_figures_per_experiment(tmp_path):
    runtime=tmp_path/"runtime_20261025";rd=runtime/"reports";rd.mkdir(parents=True)
    rows=[];figures=[]
    for exp in (3,4,5,6):
        task=_task(f"e{exp}/rep_1/eval/direct/method/case",exp,"case")
        rows.append(_row(task,"successful",0.5))
        for j in range(2 if exp==4 else 1):
            path=rd/f"E{exp}_figure_{j}.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n"+b"x"*600)
            figures.append({"path":str(path)})
    fp.write_csv(rd/"planned_case_ledger.csv",rows)
    (rd/"report_result.json").write_text(json.dumps({"figure_paths":figures}),encoding="utf-8")
    records=fp.figure_denominators(rd)
    e4=[r for r in records if r["experiment"]==4]
    assert len(e4)==2
    assert {r["path"] for r in e4}=={"E4_figure_0.png","E4_figure_1.png"}
    assert sum(r["successful_BA_evaluation_denominator"] for r in e4)==2
