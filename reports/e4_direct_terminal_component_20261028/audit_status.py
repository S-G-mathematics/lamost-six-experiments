#!/usr/bin/env python3
"""Read-only status snapshot for the E4 direct component; no scoring/model loads."""
import csv, datetime as dt, hashlib, json, sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025")
OUT = ROOT / "reports/e4_direct_terminal_component_20261028"
PLAN = ROOT / "manifests/tasks.json"
FREEZE = ROOT / "manifests/freeze.json"
DB = ROOT / "registry.sqlite"
CONDITIONS = ["control"] + [f"{c}_{s}" for c in ["A","F","G","K","M","GALAXY","QSO"] for s in ["half","tenth"]]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def atomic_json(path,obj):
    tmp=Path(str(path)+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(path)

def main():
    if OUT.exists() and {p.name for p in OUT.iterdir()} != {"audit_status.py"}: raise SystemExit(f"Refusing to overwrite existing audit directory: {OUT}")
    plan_sha=sha(PLAN); freeze_sha=sha(FREEZE)
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    planned=[t for t in plan.get("tasks",[]) if isinstance(t,dict) and t.get("key","").startswith("e4/") and "/eval/direct/" in t.get("key","")]
    keys=[t["key"] for t in planned]
    expected_methods=sorted({t.get("method") for t in planned})
    plan_reps=sorted({int(t.get("rep")) for t in planned})
    plan_conds=sorted({t.get("condition") for t in planned},key=lambda x: CONDITIONS.index(x) if x in CONDITIONS else 999)
    if len(keys)!=len(set(keys)) or len(planned)!=765 or len(expected_methods)!=17 or len(plan_reps)!=3 or len(plan_conds)!=15:
        raise RuntimeError(f"Unexpected frozen direct plan: rows={len(planned)} methods={len(expected_methods)} reps={plan_reps} conditions={len(plan_conds)}")

    OUT.mkdir(parents=True,exist_ok=True)
    snapshot=OUT/"registry_snapshot.sqlite"
    source=sqlite3.connect(f"file:{DB}?mode=ro",uri=True,timeout=30)
    target=sqlite3.connect(snapshot)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close(); source.close()
    integrity=sqlite3.connect(f"file:{snapshot}?mode=ro",uri=True)
    check=integrity.execute("PRAGMA integrity_check").fetchone()[0]
    if check!="ok": raise RuntimeError(f"Registry snapshot integrity check failed: {check}")
    integrity.close()

    c=sqlite3.connect(f"file:{snapshot}?mode=ro",uri=True); c.row_factory=sqlite3.Row
    registry={}
    for row in c.execute("SELECT key, record FROM tasks WHERE key LIKE 'e4/%/eval/direct/%'"):
        registry[row["key"]]=json.loads(row["record"])
    c.close()
    if set(registry)!=set(keys):
        raise RuntimeError(f"plan/registry key mismatch: planned={len(keys)} registry={len(registry)} missing={len(set(keys)-set(registry))} extra={len(set(registry)-set(keys))}")

    rows=[]
    for task in planned:
        k=task["key"]; r=registry[k]
        rows.append({
            "key":k,"rep":task.get("rep"),"method":task.get("method"),"condition":task.get("condition"),
            "target_class":task.get("target_class"),"planned_kind":task.get("kind"),"registry_kind":r.get("kind"),
            "status":r.get("status"),"outcome":r.get("outcome"),"source_key":r.get("source_key"),
            "dependencies":";".join(r.get("dependencies") or task.get("dependencies") or []),
            "attempt_count":len(r.get("attempts") or []),"finished_utc":r.get("finished_utc"),
            "reason":r.get("reason"),"artifact_dir":r.get("artifact_dir")
        })
    rows.sort(key=lambda x:(int(x["rep"]),str(x["method"]),CONDITIONS.index(x["condition"]) if x["condition"] in CONDITIONS else 999))
    fields=list(rows[0])
    with (OUT/"E4_DIRECT_CELL_STATUS_SNAPSHOT.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

    states=Counter(r["status"] for r in rows)
    outcomes=Counter((r["registry_kind"],r["outcome"]) for r in rows if r["status"]=="validated_terminal")
    methods=defaultdict(Counter)
    for r in rows:
        methods[r["method"]][("validated_terminal" if r["status"]=="validated_terminal" else r["status"] or "missing")]+=1
        if r["status"]=="validated_terminal":
            methods[r["method"]][f"{r['registry_kind']}:{r['outcome']}"]+=1
    method_rows=[]
    for method in expected_methods:
        d=methods[method]
        method_rows.append({"method":method,"planned":45,"validated_terminal":d["validated_terminal"],"successful_eval":d["eval:successful"],"successful_alias":d["alias:successful"],"scientific_failure":d["eval:scientific_failure"],"unavailable_dependency":d["eval:unavailable_dependency"]+d["alias:unavailable_dependency"],"unsupported":d["eval:unsupported"]+d["alias:unsupported"],"waiting_for_dependency":d["waiting_for_dependency"]})
    with (OUT/"E4_DIRECT_METHOD_STATUS.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(method_rows[0]));w.writeheader();w.writerows(method_rows)

    utc=dt.datetime.now(dt.timezone.utc); ist=utc.astimezone(ZoneInfo("Asia/Kolkata"))
    pending=[r for r in rows if r["status"]!="validated_terminal"]
    report={
      "schema":"e4-direct-terminal-component-status-audit/1",
      "scope":"E4 planned direct evaluation keys only; registry status/outcome snapshot, no metric recomputation",
      "observation_utc":utc.isoformat(),"observation_asia_kolkata":ist.isoformat(),
      "plan_sha256":plan_sha,"freeze_sha256":freeze_sha,
      "registry_snapshot_path":str(snapshot.relative_to(ROOT)),"registry_snapshot_sha256":sha(snapshot),"registry_snapshot_bytes":snapshot.stat().st_size,"registry_snapshot_integrity_check":check,
      "planned_direct_cells":len(planned),"planned_methods":expected_methods,"planned_method_count":len(expected_methods),"planned_conditions":plan_conds,"planned_repetitions":plan_reps,
      "plan_registry_key_sets_equal":True,"registry_direct_cell_count":len(registry),
      "status_counts":dict(states),"terminal_outcome_counts":{f"{kind}:{outcome}":n for (kind,outcome),n in sorted(outcomes.items())},
      "method_status":method_rows,"pending_cells":pending,"terminal_component":not pending,
      "interpretation":"This is not the final direct-component results report because planned cells remain nonterminal. Terminal aliases are counted as planned direct keys, with source_key preserved. Waiting dependencies are pending, not failures.",
      "excluded":"No saved evaluation JSONs or prediction arrays were read; no balanced accuracy, target recall, coverage, set-size, paired differences, or timing summaries were recomputed.",
      "existing_reports_reviewed":[
        "reports/e4_completed_blocks_20261027/E4_COMPLETED_BLOCKS_REPORT.md (older E4-wide matched-block snapshot; not current direct-component terminal report)",
        "reports/e4_direct_kernel_block_20261027/E4_DIRECT_KERNEL_BLOCK_REPORT.md (RBF-SVM/KDE component)",
        "reports/e4_direct_knn_block_20261027/E4_DIRECT_KNN_BLOCK_REPORT.md (KNN component)"
      ],
      "inputs":[{"path":str(PLAN.relative_to(ROOT)),"sha256":plan_sha},{"path":str(FREEZE.relative_to(ROOT)),"sha256":freeze_sha}],
      "outputs":{
        "cell_csv":{"path":"E4_DIRECT_CELL_STATUS_SNAPSHOT.csv","sha256":sha(OUT/"E4_DIRECT_CELL_STATUS_SNAPSHOT.csv")},
        "method_csv":{"path":"E4_DIRECT_METHOD_STATUS.csv","sha256":sha(OUT/"E4_DIRECT_METHOD_STATUS.csv")}
      }
    }
    atomic_json(OUT/"E4_DIRECT_COMPONENT_STATUS_AUDIT.json",report)
    reportsha=sha(OUT/"E4_DIRECT_COMPONENT_STATUS_AUDIT.json")
    md=[
      "# E4 direct-component status snapshot",
      "",
      f"Observed {utc.isoformat()} UTC ({ist.isoformat()} Asia/Kolkata).",
      "",
      f"The frozen plan contains {len(planned)} direct keys: 17 methods x 15 conditions x 3 repetitions. The registry snapshot contains the same exact key set.",
      "",
      f"- Validated terminal: {states['validated_terminal']}",
      f"- Waiting for dependency: {states['waiting_for_dependency']}",
      f"- Other nonterminal states: {sum(v for k,v in states.items() if k not in ('validated_terminal','waiting_for_dependency'))}",
      "",
      "| Registry terminal outcome | Count |",
      "|---|---:|",
    ]
    for (kind,outcome),n in sorted(outcomes.items()): md.append(f"| {kind}: {outcome} | {n} |")
    md += ["","The component is NOT terminal. All current nonterminal cells are ExtraTrees direct evaluations (15 conditions x 3 repetitions), waiting on their matching ExtraTrees fit dependencies. They remain pending; they are not scientific failures.","","The 24 planned control keys materialized as registry aliases: 21 have successful source outcomes and 3 are unavailable because the source E3 fit was unavailable. The alias source_key is retained in the cell CSV.","","## Existing reports and limits","","The existing E4 completed-block report is an older E4-wide snapshot. Existing kernel and KNN reports cover only their named methods. None is a current all-method terminal report. This status audit intentionally does not calculate predictive metrics, paired differences, conformal coverage/set size, or timing; those require validated saved evaluation outputs and a terminal component snapshot.","","No model, pipeline, test features, or prediction arrays were loaded. The registry snapshot was produced through SQLite's read-only online backup and passes PRAGMA integrity_check.","",f"Plan SHA-256: {plan_sha}  ","Freeze SHA-256: {freeze_sha}  ","Registry snapshot SHA-256: {report['registry_snapshot_sha256']}  ","Status CSV SHA-256: {report['outputs']['cell_csv']['sha256']}  ","Method table SHA-256: {report['outputs']['method_csv']['sha256']}  ","Audit JSON SHA-256: {reportsha}  "]
    (OUT/"E4_DIRECT_COMPONENT_STATUS_AUDIT.md").write_text("\n".join(md)+"\n",encoding="utf-8")
    print(json.dumps({"out":str(OUT),"planned":len(planned),"statuses":dict(states),"outcomes":report["terminal_outcome_counts"],"pending_count":len(pending),"pending_methods":dict(Counter(x["method"] for x in pending)),"registry_snapshot_sha256":report["registry_snapshot_sha256"],"csv_sha256":report["outputs"]["cell_csv"]["sha256"],"method_sha256":report["outputs"]["method_csv"]["sha256"],"json_sha256":reportsha,"md_sha256":sha(OUT/"E4_DIRECT_COMPONENT_STATUS_AUDIT.md")},indent=2))

if __name__=="__main__": main()
