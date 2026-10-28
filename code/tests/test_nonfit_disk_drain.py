import ast
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"source"/"controller.py"
TREE=ast.parse(SOURCE.read_text())
NODES={n.name:n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
e6=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="E6_V2" for t in n.targets))
NS={"GIB":1024**3,"hashlib":hashlib,"json":json,"os":os,"pathlib":__import__("pathlib"),
    "stat":stat,"sha":lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest(),
    "worker_resource_class":lambda t:"light" if t.get("kind")=="alias" else "heavy",
    "worker_reservation_bytes":lambda t:2*1024**3,
    "STORAGE_DRAIN_POLICY_ID":"nonfit-e4e5-eval-only-20261028-v1",
    "STORAGE_DRAIN_FLOOR_BYTES":20*1024**3,"STORAGE_DRAIN_OUTPUT_RESERVE_BYTES":2*1024**3,
    "_STORAGE_DRAIN_HASH_CACHE":{},"_STORAGE_DRAIN_HASH_CACHE_MAX":256}
need=[e6,NODES["_is_e6_v2_ensemble"],NODES["_is_e4_et_control_fit"],NODES["_dispatch_stage_priority"],
      NODES["order_ready_for_admission"],NODES["_storage_drain_artifact_file"],
      NODES["_storage_drain_small_json"],NODES["_storage_drain_stream_sha256"],
      NODES["_storage_drain_valid_hash"],NODES["_storage_drain_task_evidence"],NODES["storage_drain_candidate"]]
exec(compile(ast.Module(body=need,type_ignores=[]),str(SOURCE),"exec"),NS)

def writej(p,value):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,sort_keys=True))
 return p
def fit_fixture(root,exp=4,rep=1,method="random_forest",route="direct",condition="control"):
 key=f"e{exp}/rep_{rep}/fit/{route}/{method}/{condition}"
 out=root/"artifacts"/key;out.mkdir(parents=True)
 model=out/"pipeline.joblib";model.write_bytes(b"validated fake pipeline bytes; never deserialized")
 digest=hashlib.sha256(model.read_bytes()).hexdigest()
 writej(out/"fit_result.json",{"artifact_sha256":digest,"result":{"pipeline_sha256":digest}})
 writej(out/"validation.json",{"status":"validated","task_key":key,"files":{"pipeline.joblib":digest}})
 fit={"key":key,"artifact_dir":str(out),"kind":"fit","experiment":exp,"rep":rep,"method":method,"route":route,
      "condition":condition,"status":"validated_terminal","outcome":"successful","validation_state":"validated",
      "result":{"status":"successful","artifact_sha256":digest,"result":{"status":"success","pipeline_sha256":digest}}}
 return fit
def eval_fixture(root,fit,exp=None):
 exp=fit["experiment"] if exp is None else exp
 key=f"e{exp}/rep_{fit['rep']}/eval/{fit['route']}/{fit['method']}/{fit['condition']}"
 return {"key":key,"artifact_dir":str(root/"artifacts"/key),"kind":"eval","experiment":exp,"rep":fit["rep"],
  "method":fit["method"],"route":fit["route"],"condition":fit["condition"],"fit_key":fit["key"],
  "dependencies":[fit["key"]],"status":"waiting_for_dependency"}
def ev(root,task,tasks,ready=None,running=None,free=22*1024**3,archive="inactive",hold=False):
 tasks={x["key"]:x for x in tasks}
 return NS["storage_drain_candidate"](tasks,ready or [task],running or [],free,root,archive,hold)
class NonfitDiskDrainTests(unittest.TestCase):
 def test_allows_validated_physical_e4_random_forest_and_extra_trees_eval(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for method in ("random_forest","extra_trees"):
    fit=fit_fixture(root,4,1,method,"direct","control"); task=eval_fixture(root,fit)
    chosen,proof=ev(root,task,[fit])
    self.assertEqual(chosen["key"],task["key"])
    self.assertEqual(proof["fit_key"],fit["key"])
    self.assertEqual(proof["drain_kind"],"evaluation")
    self.assertTrue(proof["no_model_fit_or_serialization"])
    self.assertEqual(proof["required_free_bytes"],22*1024**3)
    self.assertEqual(proof["pipeline_sha256"],fit["result"]["result"]["pipeline_sha256"])
 def test_allows_validated_e5_clean_alias_without_a_model_fit(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);src_key="e4/rep_2/eval/direct/extra_trees/control"
   srcout=root/"artifacts"/src_key;srcout.mkdir(parents=True)
   payload={"balanced_accuracy":0.7,"coverage":0.9};evfile=writej(srcout/"evaluation.json",payload)
   digest=hashlib.sha256(evfile.read_bytes()).hexdigest()
   writej(srcout/"validation.json",{"status":"validated","task_key":src_key,"files":{"evaluation.json":digest}})
   source={"key":src_key,"artifact_dir":str(srcout),"kind":"alias","experiment":4,"rep":2,"method":"extra_trees",
    "route":"direct","condition":"control","status":"validated_terminal","outcome":"successful","validation_state":"validated"}
   key="e5/rep_2/eval/direct/extra_trees/clean"
   alias={"key":key,"artifact_dir":str(root/"artifacts"/key),"kind":"alias","experiment":5,"rep":2,
    "method":"extra_trees","route":"direct","condition":"clean","source_key":src_key,"dependencies":[src_key],
    "status":"waiting_for_dependency"}
   chosen,proof=ev(root,alias,[source])
   self.assertEqual(chosen["key"],key);self.assertEqual(proof["drain_kind"],"clean_evaluation_alias")
   self.assertNotIn("fit_key",proof);self.assertEqual(proof["source_evaluation_sha256"],digest)
 def test_denies_nonfit_tasks_failed_or_unvalidated_fit_and_missing_model(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   for bad in ({"kind":"fit","experiment":4,"method":"extra_trees"},
               {"kind":"generate","experiment":4,"method":"random_forest"}):
    self.assertIsNone(ev(root,bad,[fit])[0] if ev(root,bad,[fit]) else None)
   failed=dict(fit,status="validated_terminal",outcome="scientific_failure")
   self.assertIsNone(ev(root,task,[failed]))
   unvalidated=dict(fit,validation_state="pending")
   self.assertIsNone(ev(root,task,[unvalidated]))
   (root/"artifacts"/fit["key"]/"pipeline.joblib").unlink()
   self.assertIsNone(ev(root,task,[fit]))
 def test_denies_foreign_or_symlinked_model_paths_and_hash_mismatches(self):
  with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as foreign:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   fit["artifact_dir"]=foreign
   self.assertIsNone(ev(root,task,[fit]))
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   p=root/"artifacts"/fit["key"]/"pipeline.joblib";payload=p.read_bytes();p.unlink()
   outside=root/"outside.joblib";outside.write_bytes(payload);p.symlink_to(outside)
   self.assertIsNone(ev(root,task,[fit]))
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   p=root/"artifacts"/fit["key"]/"pipeline.joblib";p.write_bytes(b"changed after validation")
   self.assertIsNone(ev(root,task,[fit]))
 def test_floor_and_two_gib_per_active_plus_new_task_reserve(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   self.assertIsNone(ev(root,task,[fit],free=22*1024**3-1))
   self.assertIsNotNone(ev(root,task,[fit],free=22*1024**3))
   active=eval_fixture(root,fit);active["status"]="running"
   self.assertIsNone(ev(root,task,[fit],running=[active],free=24*1024**3-1))
   proof=ev(root,task,[fit],running=[active],free=24*1024**3)
   self.assertIsNotNone(proof);self.assertEqual(proof[1]["active_drain_task_count"],1)
   self.assertEqual(proof[1]["reserved_output_total_bytes"],4*1024**3)
 def test_denies_active_fit_generation_storage_hold_or_any_archive_overlap(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   active_fit={"key":"active-fit","kind":"fit","status":"running"}
   active_gen={"key":"active-gen","kind":"generate","status":"running"}
   self.assertIsNone(ev(root,task,[fit],running=[active_fit]))
   self.assertIsNone(ev(root,task,[fit],running=[active_gen]))
   self.assertIsNone(ev(root,task,[fit],hold=True))
   self.assertIsNone(ev(root,task,[fit],archive="active"))
   self.assertIsNone(ev(root,task,[fit],archive="blocked"))
 def test_only_successful_dependencies_are_admissible_and_ready_status_required(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fit=fit_fixture(root);task=eval_fixture(root,fit)
   wrong=dict(task,dependencies=["missing"])
   self.assertIsNone(ev(root,wrong,[fit]))
   nonready=dict(task,status="validated_terminal")
   self.assertIsNone(ev(root,nonready,[fit]))
   retried=dict(task,attempts=[{"attempt_id":"old"}])
   self.assertIsNone(ev(root,retried,[fit]))
 def test_normal_future_space_gate_and_hard_limits_remain_in_source(self):
  source=SOURCE.read_text()
  self.assertIn("minimum=max(20*1024**3,STORAGE_ESTIMATE[1]+6*1024**3)",source)
  self.assertIn("if storage and archive_fit_overlap_context().get('mode')!='blocked':",source)
  self.assertIn("'worker_memory_limit_gib':10",source)
  self.assertIn("'trial_timeout_seconds':600",source)
  self.assertIn("'termination_grace_seconds':30",source)
  node=NODES["admit"]
  args=[a.arg for a in node.args.args]
  self.assertIn("storage_drain_evidence",args)
  self.assertIn("resource_profile['storage_drain_policy']",source)
  live_path=Path(__file__).resolve().parent/"evidence"/"controller_baseline_9caa7afd.py"
  live_text=live_path.read_text()
  live_tree=ast.parse(live_text)
  live_gate=next(n for n in live_tree.body if isinstance(n,ast.FunctionDef) and n.name=="storage_allow")
  staged_gate=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="storage_allow")
  self.assertEqual(ast.get_source_segment(live_text,live_gate),
                   ast.get_source_segment(source,staged_gate))

if __name__=="__main__":unittest.main(verbosity=2)
