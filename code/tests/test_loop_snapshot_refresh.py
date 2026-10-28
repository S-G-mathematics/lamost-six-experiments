import ast
import collections
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/"source"/"controller.py"
TREE=ast.parse(SOURCE.read_text())
RUN=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="run")
LOOP=next(n for n in RUN.body if isinstance(n,ast.While))
defns={n.name:n for n in TREE.body if isinstance(n,ast.FunctionDef)}

def install_function(name,namespace):
 node=defns[name]
 module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
 exec(compile(module,str(SOURCE),"exec"),namespace)

class LoopSnapshotRefreshTests(unittest.TestCase):
 def test_drain_admission_is_visible_to_next_loop_check_and_export(self):
  self.assertIsInstance(LOOP.body[0],ast.Assign)
  assign=LOOP.body[0]
  self.assertEqual([t.id for t in assign.targets if isinstance(t,ast.Name)],["tasks"])
  self.assertIsInstance(assign.value,ast.Call)
  self.assertIsInstance(assign.value.func,ast.Name)
  self.assertEqual(assign.value.func.id,"load")
  self.assertEqual([a.id for a in assign.value.args if isinstance(a,ast.Name)],["db"])

  with tempfile.TemporaryDirectory() as td:
   runtime=Path(td);result_path=runtime/"worker_result.json"
   attempt_id="drain-attempt-example"
   result_path.write_text(json.dumps({"status":"successful","controller_attempt_id":attempt_id,
                                     "validation":{"status":"validated"}}))
   db=sqlite3.connect(":memory:")
   db.execute("CREATE TABLE tasks(key TEXT PRIMARY KEY, record TEXT NOT NULL)")
   admitted={"key":"e5/rep_2/eval/direct/random_forest/feature_noise_05",
             "kind":"eval","experiment":5,"status":"running","outcome":None,
             "pid":123,"process_start_ticks":456,"attempts":[{"attempt_id":attempt_id}],
             "result_path":str(result_path)}
   # This is the SQLite write performed at the end of admission. Keep a stale
   # pre-admission local mapping to reproduce the original drain-branch defect.
   namespace={"json":json}
   install_function("put",namespace);install_function("load",namespace)
   install_function("terminalize",namespace);install_function("check_running",namespace)
   install_function("export",namespace)
   events=[];outputs={}
   namespace.update({
    "db":db,"tasks":{"old":dict(admitted,status="planned")},
    "REAPER_ENABLED":False,"pathlib":__import__("pathlib"),"TERMINAL":{"successful","scientific_failure","unsupported","unavailable_dependency","user_stopped"},
    "process_table":lambda:{},"event":lambda d,k,p:events.append((k,p)),"os":os,
    "now":lambda:"2026-10-28T00:00:00+00:00","collections":collections,"R":runtime,
    "atomic":lambda path,value:outputs.__setitem__(Path(path).name,value)
   })
   namespace["put"](db,admitted)
   self.assertEqual(namespace["load"](db)[admitted["key"]]["status"],"running")
   # Run the production while-loop prefix: registry reload, optional reaper
   # branch (disabled), then production check_running over the refreshed map.
   prefix=LOOP.body[:3]
   exec(compile(ast.fix_missing_locations(ast.Module(body=prefix,type_ignores=[])),str(SOURCE),"exec"),namespace)
   refreshed=namespace["tasks"][admitted["key"]]
   self.assertEqual(refreshed["status"],"validated_terminal")
   self.assertEqual(refreshed["outcome"],"successful")
   self.assertIn(("task_terminal",{"key":admitted["key"],"outcome":"successful","reason":None}),events)
   export_call=min((n for n in ast.walk(LOOP) if isinstance(n,ast.Call)
                    and isinstance(n.func,ast.Name) and n.func.id=="export"),
                   key=lambda n:n.lineno)
   statement=ast.fix_missing_locations(ast.Module(body=[ast.Expr(value=export_call)],type_ignores=[]))
   exec(compile(statement,str(SOURCE),"exec"),namespace)
   self.assertEqual(outputs["status.json"]["active"],[])
   self.assertEqual(outputs["status.json"]["task_counts"],{"validated_terminal":1})
   self.assertEqual(json.loads(db.execute("SELECT record FROM tasks WHERE key=?",(admitted["key"],)).fetchone()[0])["outcome"],"successful")

if __name__=="__main__":unittest.main(verbosity=2)
