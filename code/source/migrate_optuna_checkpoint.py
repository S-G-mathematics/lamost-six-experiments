#!/usr/bin/env python3
"""Copy an interrupted Optuna checkpoint into a code-hash-scoped path without altering its source DB.

This is an operational migration utility; it performs no fit, prediction, or model-selection change.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sqlite3, tempfile, uuid
from pathlib import Path

OPERATIONAL_FIELDS={"attempt_id","worker_pid","started_at","observed_at","observed_utc","artifact_dir","controller_pid","status","attempts","attempt_number","queue_state","controller_state"}
SIDECARS=("trial_history.json","optuna_sampler.joblib","selection.json")

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def _load_task(path):
    obj=json.loads(Path(path).read_text())
    task=obj.get("task",obj)
    if not isinstance(task,dict) or not task.get("key"): raise ValueError(f"task JSON has no task.key: {path}")
    clean={k:v for k,v in task.items() if k not in OPERATIONAL_FIELDS}
    return obj,clean
def _task_hash(obj,clean):
    value=obj.get("task_sha256")
    if value: return value
    engine=obj.get("engine_code_sha256")
    if not engine: raise ValueError("task JSON needs task_sha256 or engine_code_sha256")
    identity=dict(clean); identity["engine_code_sha256"]=engine
    return hashlib.sha256(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()
def _study_name(key,task_hash):
    return "task_"+hashlib.sha256((key+task_hash).encode()).hexdigest()[:20]
def _conn(path,readonly=False):
    if readonly:
        return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro",uri=True)
    return sqlite3.connect(path)
def _db_snapshot(conn):
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    result={}
    for table in tables:
        rows=conn.execute('SELECT * FROM "'+table.replace('"','""')+'"').fetchall()
        result[table]=sorted([tuple(bytes(v) if isinstance(v,memoryview) else v for v in row) for row in rows],key=repr)
    return result
def _validate_trials(db_path,study_name,ledger_path=None):
    conn=_conn(db_path,True)
    try:
        rows=conn.execute("SELECT study_id,study_name FROM studies ORDER BY study_id").fetchall()
        matches=[sid for sid,name in rows if name==study_name]
        if len(matches)!=1: raise ValueError(f"expected one study named {study_name}, found {len(matches)}")
        trials=conn.execute("SELECT number,state FROM trials WHERE study_id=? ORDER BY number",matches).fetchall()
        table={int(num):state for num,state in trials}
        if ledger_path and Path(ledger_path).exists():
            ledger=json.loads(Path(ledger_path).read_text())
            status_map={"success":"COMPLETE","duplicate_cached":"COMPLETE","scientific_failure":"FAIL","failed":"FAIL",
                        "operationally_interrupted":"RUNNING","operationally_invalid":"RUNNING"}
            for row in ledger:
                n=int(row["number"]); status=row.get("status")
                if n not in table: raise ValueError(f"trial ledger number {n} absent from DB")
                expected=status_map.get(status)
                if expected and table[n]!=expected:
                    raise ValueError(f"trial {n} state mismatch: ledger={status}, DB={table[n]}")
        return {"study_id":matches[0],"trials":[{"number":int(n),"state":state} for n,state in trials]}
    finally: conn.close()
def _migrate(source_dir,dest_dir,source_task_path,new_task_path,apply=False):
    src=Path(source_dir).resolve(); dst=Path(dest_dir).resolve()
    if not src.is_dir(): raise FileNotFoundError(f"source checkpoint directory missing: {src}")
    source_db=src/"optuna.sqlite3"
    if not source_db.is_file(): raise FileNotFoundError(f"Optuna DB missing: {source_db}")
    old_obj,old_task=_load_task(source_task_path); new_obj,new_task=_load_task(new_task_path)
    if old_task!=new_task: raise ValueError("scientific task definitions differ; refusing checkpoint migration")
    key=old_task["key"]
    old_hash=_task_hash(old_obj,old_task); new_hash=_task_hash(new_obj,new_task)
    if old_hash==new_hash: raise ValueError("task hashes are identical; no migration is needed")
    old_name=_study_name(key,old_hash); new_name=_study_name(key,new_hash)
    source_hash=sha(source_db); ledger=src/"trial_history.json"
    before_conn=_conn(source_db,True)
    try:
        if before_conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("source DB integrity check failed")
        before_snapshot=_db_snapshot(before_conn)
    finally: before_conn.close()
    old_trials=_validate_trials(source_db,old_name,ledger if ledger.exists() else None)
    available=[p.name for p in (src/name for name in SIDECARS) if p.is_file()]
    receipt={"source_checkpoint_dir":str(src),"destination_checkpoint_dir":str(dst),
      "source_db_sha256":source_hash,"old_task_sha256":old_hash,"new_task_sha256":new_hash,
      "task_key":key,"old_study_name":old_name,"new_study_name":new_name,
      "scientific_task_definition_equal":True,"source_trials":old_trials["trials"],
      "copied_sidecars":available,"changes_to_source":"none","intended_database_change":"study_name only in a verified copy"}
    if not apply: return receipt
    if dst.exists() and any(dst.iterdir()): raise FileExistsError(f"destination checkpoint is not empty: {dst}")
    dst.mkdir(parents=True,exist_ok=True)
    temp_db=dst/("optuna.sqlite3."+uuid.uuid4().hex+".tmp")
    source_conn=_conn(source_db,True); target_conn=sqlite3.connect(temp_db)
    try:
        source_conn.backup(target_conn)
        target_conn.commit()
        found=target_conn.execute("SELECT study_id FROM studies WHERE study_name=?",(old_name,)).fetchall()
        if len(found)!=1: raise ValueError("copied DB does not contain exact old study name")
        if target_conn.execute("SELECT 1 FROM studies WHERE study_name=?",(new_name,)).fetchone():
            raise ValueError("new study name already exists in copied DB")
        target_conn.execute("UPDATE studies SET study_name=? WHERE study_id=?",(new_name,found[0][0]))
        target_conn.commit()
        if target_conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("copied/renamed DB integrity check failed")
        after_snapshot=_db_snapshot(target_conn)
        after_snapshot["studies"]=[tuple(old_name if x==new_name else x for x in row) for row in after_snapshot["studies"]]
        if before_snapshot!=after_snapshot:
            changed=[name for name in before_snapshot if before_snapshot.get(name)!=after_snapshot.get(name)]
            raise ValueError(f"database copy differs beyond the single intended study_name change in tables: {changed}")
        trial_check=target_conn.execute("SELECT number,state FROM trials WHERE study_id=? ORDER BY number",(found[0][0],)).fetchall()
        if trial_check!=[(t["number"],t["state"]) for t in old_trials["trials"]]:
            raise ValueError("trial IDs/states changed during copy")
    finally:
        target_conn.close(); source_conn.close()
    final_db=dst/"optuna.sqlite3"; os.replace(temp_db,final_db)
    sidecar_hashes={}
    for name in available:
        dest=dst/name
        if dest.exists(): raise FileExistsError(dest)
        shutil.copy2(src/name,dest)
        if sha(src/name)!=sha(dest): raise IOError(f"sidecar hash mismatch: {name}")
        sidecar_hashes[name]=sha(dest)
    receipt.update({"destination_db_sha256":sha(final_db),"new_study_name_verified":new_name,
      "destination_trials":old_trials["trials"],"sidecar_sha256":sidecar_hashes,"applied":True})
    (dst/"migration_receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2))
    # The source files and their hashes must still be identical after the copy.
    if sha(source_db)!=source_hash: raise RuntimeError("source DB changed during migration")
    return receipt
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-checkpoint-dir")
    ap.add_argument("--destination-checkpoint-dir")
    ap.add_argument("--source-task-json")
    ap.add_argument("--new-task-json")
    ap.add_argument("--apply",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test:
        import optuna
        with tempfile.TemporaryDirectory(prefix="lamost-optuna-copy-") as td:
            root=Path(td); src=root/"old"; dst=root/"new"; src.mkdir()
            db=src/"optuna.sqlite3"; storage="sqlite:///"+str(db)
            old_hash="oldhash"; old_name=_study_name("fixture/task",old_hash)
            st=optuna.create_study(study_name=old_name,storage=storage,direction="maximize")
            t0=st.ask(); t0.suggest_float("C",.01,1,log=True); st.tell(t0,.7)
            t1=st.ask(); t1.suggest_float("C",.01,1,log=True)
            (src/"trial_history.json").write_text(json.dumps([
              {"number":0,"status":"success","params":st.trials[0].params,"score":.7},
              {"number":1,"status":"operationally_interrupted","params":st.trials[1].params}]))
            task={"key":"fixture/task","kind":"fit","method":"logistic","seed":4,"attempt_id":"old"}
            newtask={**task,"attempt_id":"new"}
            oldrec={"task":task,"task_sha256":old_hash,"engine_code_sha256":"oldengine"}
            newrec={"task":newtask,"task_sha256":"newhash","engine_code_sha256":"newengine"}
            p1=root/"oldtask.json"; p2=root/"newtask.json"
            p1.write_text(json.dumps(oldrec)); p2.write_text(json.dumps(newrec))
            receipt=_migrate(src,dst,p1,p2,True)
            assert receipt["scientific_task_definition_equal"] and receipt["new_study_name_verified"]
            assert receipt["destination_trials"]==[{"number":0,"state":"COMPLETE"},{"number":1,"state":"RUNNING"}]
            assert sha(db)==receipt["source_db_sha256"] and (dst/"migration_receipt.json").exists()
        print("temporary Optuna DB copy/rename self-test passed")
        return
    if not all((a.source_checkpoint_dir,a.destination_checkpoint_dir,a.source_task_json,a.new_task_json)):
        ap.error("four paths are required unless --self-test")
    receipt=_migrate(a.source_checkpoint_dir,a.destination_checkpoint_dir,a.source_task_json,a.new_task_json,a.apply)
    print(json.dumps(receipt,sort_keys=True,indent=2))
if __name__=="__main__": main()
