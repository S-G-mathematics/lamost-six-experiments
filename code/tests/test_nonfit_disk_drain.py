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
    "STORAGE_DRAIN_FLOOR_BYTES":6*1024**3,"STORAGE_DRAIN_OUTPUT_RESERVE_BYTES":2*1024**3,
    "_STORAGE_DRAIN_HASH_CACHE":{},"_STORAGE_DRAIN_HASH_CACHE_MAX":256,"__file__":str(SOURCE),"GIB":1024**3,"STORAGE_DRAIN_OUTPUT_RESERVE_BYTES":2*1024**3,
 "WORKING_STORAGE_POLICY":{"policy_id":"working-reserve-6gib-one-fit-v1","working_reserve_bytes":6*1024**3,
 "maximum_restore_bytes":10*1024**3,"maximum_single_restore_asset_bytes":1024**3,
 "per_active_or_new_task_output_reserve_bytes":2*1024**3,"maximum_concurrent_fit_tasks":1,
 "restore_index_rel":"operations/terminal_result_retention_v2_20261030/guardian/retention_index.json",
 "restore_index_schema":"lamost-terminal-result-retention-index/2","full_archive_verification":"finalization_only"}}
need=[e6,NODES["_is_e6_v2_ensemble"],NODES["_is_e4_et_control_fit"],NODES["_dispatch_stage_priority"],
      NODES["order_ready_for_admission"],NODES["_storage_drain_artifact_file"],
      NODES["_storage_drain_small_json"],NODES["_storage_drain_stream_sha256"],
      NODES["_storage_drain_valid_hash"],NODES["_storage_drain_task_evidence"],NODES["_storage_expected_campaign"],NODES["retention_restore_budget"],NODES["retention_budget_matches_policy"],NODES["storage_required_bytes"],NODES["storage_drain_candidate"]]
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
def campaign_fixture(root):
 project=Path(root).resolve().parent
 rel=NS["WORKING_STORAGE_POLICY"]["restore_index_rel"]
 key="e4/rep_1/eval/direct/random_forest/control"
 src="runtime_20261025/artifacts/"+key+"/test_outcomes.npz"
 aliases=[src,"runtime_20261025/artifacts/"+key+"/attempts/fixture/test_outcomes.npz"]
 row={"task_key":key,"task_family":4,"source_path":src,"source_bytes":100,"source_sha256":"a"*64,
  "asset_name":"fixture-result.zip","asset_bytes":50,"asset_sha256":"b"*64,"native_paths":aliases,"unlinked_paths":aliases,
  "link_count":2,"retirement_kind":"complete_inode_group","fresh_native_inventory_verified":True,
  "asset_remote_evidence_path":"fixture/remote.json","asset_remote_evidence_sha256":"c"*64,
  "member_record_evidence_path":"fixture/member.json","member_record_evidence_sha256":"d"*64,
  "manifest_sha256":"e"*64,"physical_inventory_sha256":"f"*64,"plan_sha256":"1"*64,
  "archive_crc32":"00000000","archive_member":src}
 index=project/rel
 writej(index,{"schema":NS["WORKING_STORAGE_POLICY"]["restore_index_schema"],"restore_required":True,"retired":[row]})
 budget=NS["retention_restore_budget"](index)
 policy={"schema":"lamost-working-storage-admission-policy/1","policy_id":NS["WORKING_STORAGE_POLICY"]["policy_id"],
  "controller_candidate_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),"freeze_binding_value":NS["WORKING_STORAGE_POLICY"],
  "retention_index_path":rel,"retention_index_schema":NS["WORKING_STORAGE_POLICY"]["restore_index_schema"],
  "maximum_concurrent_fit_tasks":1,"per_active_or_new_task_output_reserve_bytes":2*1024**3,
  "retention_index_sha256":budget["index_sha256"],"retention_row_count":budget["row_count"],
  "retention_restore_bytes":budget["restore_bytes"],"largest_restore_asset_bytes":budget["largest_asset_bytes"],"retention_restore_required":True}
 prel="operations/fixture_working_storage_policy.json"
 raw=json.dumps(policy,sort_keys=True,separators=(",",":")).encode()
 pp=project/prel;pp.parent.mkdir(parents=True,exist_ok=True);pp.write_bytes(raw)
 current=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 frozen={"storage_admission_policy":NS["WORKING_STORAGE_POLICY"],"storage_admission_amendment":{"schema":"lamost-controller-operational-source-amendment/1",
  "candidate_controller_sha256":current,"policy_path":prel,"policy_sha256":hashlib.sha256(raw).hexdigest()}}
 NS["R"]=Path(root)
 return frozen

def ev(root,task,tasks,ready=None,running=None,free=22*1024**3,archive="inactive",hold=False):
 tasks={x["key"]:x for x in tasks};frozen=campaign_fixture(root)
 return NS["storage_drain_candidate"](tasks,ready or [task],running or [],free,root,archive,hold,frozen)
class NonfitDiskDrainTests(unittest.TestCase):
 def test_allows_validated_physical_e4_random_forest_and_extra_trees_eval(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir()
   for method in ("random_forest","extra_trees"):
    fit=fit_fixture(root,4,1,method,"direct","control"); task=eval_fixture(root,fit)
    chosen,proof=ev(root,task,[fit])
    self.assertEqual(chosen["key"],task["key"])
    self.assertEqual(proof["fit_key"],fit["key"])
    self.assertEqual(proof["drain_kind"],"evaluation")
    self.assertTrue(proof["no_model_fit_or_serialization"])
    self.assertEqual(proof["required_free_bytes"],8*1024**3+150)
    self.assertEqual(proof["pipeline_sha256"],fit["result"]["result"]["pipeline_sha256"])
 def test_allows_validated_e5_clean_alias_without_a_model_fit(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();src_key="e4/rep_2/eval/direct/extra_trees/control"
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
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
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
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   fit["artifact_dir"]=foreign
   self.assertIsNone(ev(root,task,[fit]))
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   p=root/"artifacts"/fit["key"]/"pipeline.joblib";payload=p.read_bytes();p.unlink()
   outside=root/"outside.joblib";outside.write_bytes(payload);p.symlink_to(outside)
   self.assertIsNone(ev(root,task,[fit]))
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   p=root/"artifacts"/fit["key"]/"pipeline.joblib";p.write_bytes(b"changed after validation")
   self.assertIsNone(ev(root,task,[fit]))
 def test_working_floor_restore_liability_and_two_gib_per_active_plus_new_task_reserve(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   required0=8*1024**3+150
   self.assertIsNone(ev(root,task,[fit],free=required0-1))
   base_proof=ev(root,task,[fit],free=required0)
   self.assertIsNotNone(base_proof)
   self.assertEqual(base_proof[1]["hard_free_floor_bytes"],6*1024**3+150)
   active=eval_fixture(root,fit);active["status"]="running"
   required1=10*1024**3+150
   self.assertIsNone(ev(root,task,[fit],running=[active],free=required1-1))
   proof=ev(root,task,[fit],running=[active],free=required1)
   self.assertIsNotNone(proof);self.assertEqual(proof[1]["active_drain_task_count"],1)
   self.assertEqual(proof[1]["reserved_output_total_bytes"],4*1024**3)
 def test_denies_active_fit_generation_storage_hold_or_any_archive_overlap(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   active_fit={"key":"active-fit","kind":"fit","status":"running"}
   active_gen={"key":"active-gen","kind":"generate","status":"running"}
   self.assertIsNone(ev(root,task,[fit],running=[active_fit]))
   self.assertIsNone(ev(root,task,[fit],running=[active_gen]))
   self.assertIsNone(ev(root,task,[fit],hold=True))
   self.assertIsNone(ev(root,task,[fit],archive="active"))
   self.assertIsNone(ev(root,task,[fit],archive="blocked"))
 def test_only_successful_dependencies_are_admissible_and_ready_status_required(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)/"runtime_20261025";root.mkdir();fit=fit_fixture(root);task=eval_fixture(root,fit)
   wrong=dict(task,dependencies=["missing"])
   self.assertIsNone(ev(root,wrong,[fit]))
   nonready=dict(task,status="validated_terminal")
   self.assertIsNone(ev(root,nonready,[fit]))
   retried=dict(task,attempts=[{"attempt_id":"old"}])
   self.assertIsNone(ev(root,retried,[fit]))
 def test_normal_future_space_gate_and_hard_limits_remain_in_source(self):
  source=SOURCE.read_text()
  self.assertIn("budget=retention_restore_budget(index_path)",source)
  self.assertIn("required=storage_required_bytes(budget['restore_bytes'],budget['largest_asset_bytes'],len(active_evidence))",source)
  self.assertIn("working_reserve_bytes':6*GIB",source)
  self.assertIn("if storage and archive_fit_overlap_context().get('mode')!='blocked':",source)
  self.assertIn("'worker_memory_limit_gib':10",source)
  self.assertIn("'trial_timeout_seconds':600",source)
  self.assertIn("'termination_grace_seconds':30",source)
  node=NODES["admit"]
  args=[a.arg for a in node.args.args]
  self.assertIn("storage_drain_evidence",args)
  self.assertIn("resource_profile['storage_drain_policy']",source)
  staged_gate=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="storage_allow")
  self.assertEqual(hashlib.sha256(ast.dump(staged_gate,include_attributes=False).encode()).hexdigest(),
                   "3aeac25662cbbe5880b725acd78439910d5b1cfdb3509835123053906739df64")

if __name__=="__main__":unittest.main(verbosity=2)
