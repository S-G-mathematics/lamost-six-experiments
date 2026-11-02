import ast, hashlib, importlib.util, json, pathlib, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from test_native_fit_mixedsmall_profile import ROOT, install, role_fixture, input_dep, cold_index

GIB=1024**3
CTRL_PATH=ROOT/"source/controller.py"
SPEC=importlib.util.spec_from_file_location("native_fit_overlap_controller_fixture",CTRL_PATH)
controller=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(controller)
m=controller.archive_fit_admission
OP_SOURCES={
 "controller.py","archive_fit_admission.py","cold_auto_compaction.py","run_batch.py",
 "commit_batch_child.py","cold_model_storage.py","cold_codec_storage.py","reversible_joblib_codec.py",
 "cold_storage_safety.py","batch_plan.py","admission_evidence.py",
}
NATIVE={"cache/cache_manifest.json","manifests/E4_MANIFEST.json","manifests/E5_MANIFEST.json"}

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def jwrite(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,separators=(",",":")),encoding="utf-8")
 return p

def rewrite_qualified_fixture(root,freeze):
 op={n:digest(root/"source"/n) for n in sorted(OP_SOURCES)}
 native={n:digest(root/n) for n in sorted(NATIVE)}
 policy={
  "schema":m.POLICY_SCHEMA,"policy_id":"archive-native-fit-overlap-1.5gib-cpu1-v1","status":"qualified",
  "scope":{"experiments":[4,5],"kind":"fit","never_attempted":True,"reuse_pipeline":False,
   "routes":{"4":["direct","treatment"],"5":["direct","synthetic"]},
   "require_successful_dependencies":True,"no_existing_same_task_pipeline_or_checkpoint":True},
  "resources":{"helper_reservation_gib":1.5,"helper_cpu_reservation_units":1,"host_os_harbor_reserve_gib":6,
   "commitment_growth_margin_gib":2,"admission_only_safety_buffer_gib":1,"worker_memory_limit_gib":10,
   "trial_timeout_seconds":600,"phase_timeout_seconds":600,"termination_grace_seconds":30,
   "archive_wall_seconds":1800,"archive_wrapper_wall_seconds":1860,"archive_child_rss_limit_bytes":1073741824,
   "archive_child_address_space_limit_bytes":939524096,"archive_wrapper_rss_limit_bytes":1610612736,
   "native_threads":1,"nested_threads":1},
  "archive_operation":{"owner_operation":m.OWNER_OPERATION,"batch_policy":m.BATCH_POLICY,
   "archive_io_profile":m.IO_PROFILE,"storage_codec_policy":None},
  "source_sha256":op,"native_input_manifests":native,
  "qualification_path":"reports/engineering_audits/fixture_archive_native_fit_qualification.json",
 }
 praw=json.dumps(policy,sort_keys=True,separators=(",",":")).encode()
 psha=hashlib.sha256(praw).hexdigest()
 q={
  "schema":m.QUALIFICATION_SCHEMA,"status":"passed","policy_sha256":psha,
  "source_sha256":op,"native_input_manifests":native,
  "portable_suite":{"status":"passed","exit_code":0,"expected_test_count":15,"passed_test_count":15,"failed_test_count":0},
  "controller_harness":{"status":"passed","fit_attempts_started":0,"archive_helper_fixture_only":True},
 }
 qraw=json.dumps(q,sort_keys=True,separators=(",",":")).encode()
 qpath=root/policy["qualification_path"];jwrite(qpath,q)
 qsha=hashlib.sha256(qraw).hexdigest()
 jwrite(root/m.POLICY_REL,policy)
 freeze=dict(freeze)
 freeze["source_sha256"]={"controller.py":op["controller.py"],"archive_fit_admission.py":op["archive_fit_admission.py"]}
 freeze[m.POLICY_FIELD]=psha;freeze[m.QUALIFICATION_FIELD]=qsha
 return freeze,op,native

class NativeFitControllerHarness(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  from test_native_fit_mixedsmall_profile import HelperIdentityTests
  helper=HelperIdentityTests("test_actual_helper_chain_contract_accepts_mixedsmall_identity")
  self.root,self.proc,self.freeze=helper.active_fixture(self.tmp.name)
  self.addCleanup(self.tmp.cleanup)
  self.source,self.ids=role_fixture(self.root)
  cold_index(self.root)
  trainkey="e4/rep_1/cohort/A_half"
  self.train,self.train_hashes=input_dep(self.root,trainkey,{"data.npz":b"tiny cohort fixture"})
  selkey="e4/rep_1/fit/direct/logistic_regression/control"
  self.selection,self.selection_hashes=input_dep(self.root,selkey,{"selection.json":b'{"selected_params":{"C":1.0}}'},kind="fit")
  self.key="e4/rep_1/fit/direct/random_forest/A_half"
  self.task={"key":self.key,"experiment":4,"kind":"fit","route":"direct","method":"random_forest","rep":1,
   "condition":"A_half","status":"planned","attempts":[],"dependencies":[trainkey,selkey],
   "train_key":trainkey,"selection_key":selkey,"artifact_dir":str(self.root/"artifacts"/self.key)}
  self.definition=dict(self.task)
  self.tasks={trainkey:self.train,selkey:self.selection,self.key:self.task}
  self.freeze,self.op_sources,self.native=rewrite_qualified_fixture(self.root,self.freeze)
  self.context=m.inspect_runtime(self.root,self.freeze,proc_root=self.proc,uid=1000)
  self.assert_active()
  self.controller_patches=[
   patch.object(controller,"R",self.root),
   patch.object(controller,"DEFINITIONS",{self.key:self.definition}),
   patch.object(controller,"_archive_overlap_freeze",return_value=self.freeze),
   patch.object(controller,"archive_fit_overlap_context",side_effect=lambda:self.context),
   patch.object(controller,"load",side_effect=lambda db:self.tasks),
   patch.object(controller,"bracketed_worker_memory",return_value=(30*GIB,[],[])),
   patch.object(controller,"_bracketed_archive_helper",side_effect=self.helper_measurement),
   patch.object(controller.os,"cpu_count",return_value=8),
  ]
  for p in self.controller_patches:p.start()
  self.addCleanup(self.stop_patches)
  self.attempts_started=0
 def stop_patches(self):
  for p in reversed(self.controller_patches):p.stop()
 def assert_active(self):
  self.assertEqual(self.context.get("mode"),"active",self.context)
  self.assertEqual(self.context.get("reason"),"verified_raw_archive_helper")
 def helper_measurement(self,context):
  if context.get("evidence",{}).get("context_sha256")!=self.context.get("evidence",{}).get("context_sha256"):return None
  return {"available_bytes":30*GIB,"credited_pss_bytes":512*1024**2,
   "observed_peak_pss_bytes":700*1024**2,"context":self.context}
 def gate(self,task=None,definition=None):
  return controller._archive_fit_launch_gate(object(),task or self.task,6.0)
 def test_active_helper_accepts_fresh_e4_fit_without_launching_it(self):
  result=self.gate()
  self.assertIsInstance(result,dict)
  self.assertEqual(result["profile_id"],controller.ARCHIVE_FIT_OVERLAP_PROFILE)
  self.assertEqual(result["helper_cpu_reservation_units"],1)
  self.assertEqual(result["worker_reservation_bytes"],4*GIB)
  self.assertEqual(self.attempts_started,0)
 def test_active_helper_rejects_nonoverlap_model_reader(self):
  task=dict(self.task,key="e3/rep_1/fit/direct/random_forest/clean",experiment=3)
  self.tasks[task["key"]]=task;controller.DEFINITIONS[task["key"]]=dict(task)
  self.assertIs(self.gate(task),False)
  self.assertEqual(self.attempts_started,0)
 def test_active_helper_rejects_terminal_fit(self):
  task=dict(self.task,status="validated_terminal")
  self.assertIs(self.gate(task),False)
  self.assertEqual(self.attempts_started,0)
 def test_active_helper_rejects_prior_attempt_or_reuse(self):
  prior=dict(self.task,attempts=[{"attempt_id":"prior"}])
  self.assertIs(self.gate(prior),False)
  reuse=dict(self.task,reuse_pipeline=True)
  self.assertIs(self.gate(reuse),False)
  self.assertEqual(self.attempts_started,0)
 def test_active_helper_rejects_changed_source_or_inputs(self):
  source=self.root/"source/run_batch.py";old=source.read_bytes()
  source.write_bytes(old+b"\n# mutation fixture\n")
  self.context=m.inspect_runtime(self.root,self.freeze,proc_root=self.proc,uid=1000)
  self.assertEqual(self.context.get("mode"),"blocked")
  self.assertIs(self.gate(),False)
  source.write_bytes(old)
  self.context=m.inspect_runtime(self.root,self.freeze,proc_root=self.proc,uid=1000)
  self.assert_active()
  data=self.root/"artifacts"/self.train["key"]/"data.npz"
  old=data.read_bytes();data.write_bytes(old+b"tamper")
  self.assertIs(self.gate(),False)
  self.assertEqual(self.attempts_started,0)
 def test_active_helper_rejects_pending_dependency(self):
  self.train["status"]="running"
  self.assertIs(self.gate(),False)
  self.assertEqual(self.attempts_started,0)
 def test_storage_floor_blocks_fit_drain(self):
  below=controller.storage_drain_candidate(self.tasks,[self.task],[],19*GIB,self.root,"inactive",False)
  self.assertIsNone(below)
  floor=controller.storage_drain_candidate(self.tasks,[self.task],[],22*GIB,self.root,"inactive",False)
  self.assertIsNone(floor)
  tree=ast.parse(CTRL_PATH.read_text())
  run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run")
  calls=lambda node:{n.func.id for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
  storage_if=next(n for n in ast.walk(run) if isinstance(n,ast.If) and "storage" in ast.unparse(n.test) and "admission_candidate" in calls(n))
  self.assertIn("admission_candidate",calls(storage_if.body[0]) | calls(storage_if))
  self.assertIn("storage_drain_candidate",calls(run))
  self.assertEqual(self.attempts_started,0)

if __name__=="__main__":unittest.main(verbosity=2)
