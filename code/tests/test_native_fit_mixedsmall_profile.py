import ast, hashlib, importlib.util, json, os, pathlib, shutil, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'source/archive_fit_admission.py'
sp=importlib.util.spec_from_file_location('mixedsmall_native_fit_admission_test',MODULE)
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

def write(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 return hashlib.sha256(data).hexdigest()
def jwrite(path,obj):return write(path,json.dumps(obj,sort_keys=True,separators=(',',':')).encode())
def valid_rel(value):
 return isinstance(value,str) and bool(value) and '\\' not in value and not pathlib.PurePosixPath(value).is_absolute() and pathlib.PurePosixPath(value).as_posix()==value and not any(x in ('','.','..') for x in pathlib.PurePosixPath(value).parts)
def install(root):
 source=root/'source';source.mkdir(parents=True,exist_ok=True)
 srcroot=ROOT/'source'
 required={'controller.py','archive_fit_admission.py','cold_auto_compaction.py','run_batch.py','commit_batch_child.py','cold_model_storage.py','cold_codec_storage.py','reversible_joblib_codec.py','cold_storage_safety.py','batch_plan.py','admission_evidence.py'}
 for name in required:shutil.copyfile(srcroot/name,source/name)
 native={}
 for rel,value in (('cache/cache_manifest.json',{'fixture':'cache'}),('manifests/E4_MANIFEST.json',{'fixture':'e4'}),('manifests/E5_MANIFEST.json',{'fixture':'e5'})):
  native[rel]=jwrite(root/rel,value)
 source_map={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in sorted(required)}
 resources={'helper_reservation_gib':1.5,'helper_cpu_reservation_units':1,'host_os_harbor_reserve_gib':6,
  'commitment_growth_margin_gib':2,'admission_only_safety_buffer_gib':1,'worker_memory_limit_gib':10,
  'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,
  'archive_wall_seconds':1800,'archive_wrapper_wall_seconds':1860,'archive_child_rss_limit_bytes':1073741824,
  'archive_child_address_space_limit_bytes':939524096,'archive_wrapper_rss_limit_bytes':1610612736,
  'native_threads':1,'nested_threads':1}
 scope={'experiments':[4,5],'kind':'fit','never_attempted':True,'reuse_pipeline':False,
  'routes':{'4':['direct','treatment'],'5':['direct','synthetic']},
  'require_successful_dependencies':True,'no_existing_same_task_pipeline_or_checkpoint':True}
 policy={'schema':m.POLICY_SCHEMA,'policy_id':'archive-native-fit-overlap-1.5gib-cpu1-v1','status':'qualified',
  'scope':scope,'resources':resources,
  'archive_operation':{'owner_operation':m.OWNER_OPERATION,'batch_policy':m.BATCH_POLICY,'archive_io_profile':m.IO_PROFILE,'storage_codec_policy':None},
  'source_sha256':source_map,'native_input_manifests':native,
  'qualification_path':'reports/engineering_audits/fixture_overlap_qualification.json'}
 policy_raw=json.dumps(policy,sort_keys=True,separators=(',',':')).encode();policy_sha=write(root/m.POLICY_REL,policy_raw)
 qualification={'schema':m.QUALIFICATION_SCHEMA,'status':'passed','policy_sha256':policy_sha,'source_sha256':source_map,
  'native_input_manifests':native,'portable_suite':{'status':'passed','exit_code':0,'expected_test_count':1,'passed_test_count':1,'failed_test_count':0},
  'controller_harness':{'status':'passed','fit_attempts_started':0,'archive_helper_fixture_only':True}}
 qraw=json.dumps(qualification,sort_keys=True,separators=(',',':')).encode()
 qpath=root/policy['qualification_path'];qsha=write(qpath,qraw)
 freeze={'source_sha256':{'controller.py':source_map['controller.py'],'archive_fit_admission.py':source_map['archive_fit_admission.py']},
  m.POLICY_FIELD:policy_sha,m.QUALIFICATION_FIELD:qsha}
 return freeze,source_map,native
def role_fixture(root,rows=1):
 source='a'*64;ids={k:('%064x'%(i+1)) for i,k in enumerate(('fit','tune','cal','test'))}
 rolehash=write(root/'cache/roles/rep_1.npz',b'tiny role-membership fixture')
 jwrite(root/'cache/cache_manifest.json',{'cache_files':{'roles/rep_1.npz':rolehash},'roles':{'1':{'source_sha256':source,'id_hashes':ids}}})
 for exp in ('E4','E5'):jwrite(root/f'manifests/{exp}_MANIFEST.json',{'role_hashes':{'1':{'source_sha256':source,'id_hashes':ids}}})
 return source,ids
def input_dep(root,key,files,kind='cohort'):
 out=root/'artifacts'/key;hashes={}
 for name,data in files.items():hashes[name]=write(out/name,data)
 result=out/'worker_result.json'
 jwrite(result,{'key':key,'status':'successful','validation':{'status':'validated','task_key':key,'files':hashes}})
 return {'key':key,'kind':kind,'status':'validated_terminal','outcome':'successful','validation_state':'validated','result_path':str(result)},hashes
def cold_index(root,members=None):
 p=root/'manifests/cold_model_store_manifest.json';jwrite(p,{'schema_version':'lamost-cold-model-store/1','members':members or []});return p
class MixedProfilePolicyTests(unittest.TestCase):
 def test_mixedsmall_policy_profile_is_exact_and_keeps_hard_science_resources(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);freeze,source_map,native=install(root)
   doc=m._policy(root,freeze)
   self.assertEqual(doc['document']['archive_operation']['archive_io_profile'],'bounded-1800-mixedsmall4gib2048')
   self.assertEqual(doc['document']['resources']['helper_reservation_gib'],1.5)
   self.assertEqual(doc['document']['resources']['helper_cpu_reservation_units'],1)
   self.assertEqual(doc['document']['resources']['worker_memory_limit_gib'],10)
   self.assertEqual(doc['document']['resources']['trial_timeout_seconds'],600)
   self.assertEqual(doc['document']['resources']['phase_timeout_seconds'],600)
   self.assertEqual(doc['document']['resources']['termination_grace_seconds'],30)
   self.assertEqual(doc['source_sha256'],source_map)
   self.assertEqual(doc['native_input_manifests'],native)
 def test_wrong_archive_profile_is_rejected_even_with_rehashed_policy(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);freeze,_,_=install(root);p=root/m.POLICY_REL
   d=json.loads(p.read_text());d['archive_operation']['archive_io_profile']='bounded-1800'
   policy_raw=json.dumps(d,sort_keys=True,separators=(',',':')).encode();policy_sha=write(p,policy_raw)
   qpath=root/d['qualification_path'];q=json.loads(qpath.read_text());q['policy_sha256']=policy_sha
   qsha=write(qpath,json.dumps(q,sort_keys=True,separators=(',',':')).encode())
   freeze[m.POLICY_FIELD]=policy_sha;freeze[m.QUALIFICATION_FIELD]=qsha
   with self.assertRaisesRegex(ValueError,'policy_archive_operation'):m._policy(root,freeze)
class NativeProofFixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'runtime_20261025';self.root.mkdir()
  self.tasks={};self.source,self.ids=role_fixture(self.root)
  self.cold_path=cold_index(self.root)
  trainkey='e4/rep_1/cohort/A_half'
  self.train,self.train_hashes=input_dep(self.root,trainkey,{'data.npz':b'tiny cohort bytes'})
  selkey='e4/rep_1/fit/direct/logistic_regression/control'
  self.selection,self.selection_hashes=input_dep(self.root,selkey,{'selection.json':json.dumps({'selected_params':{'C':1.0}}).encode()},kind='fit')
  self.tasks[trainkey]=self.train;self.tasks[selkey]=self.selection
  key='e4/rep_1/fit/direct/random_forest/A_half'
  self.task={'key':key,'experiment':4,'kind':'fit','route':'direct','method':'random_forest','rep':1,
   'condition':'A_half','status':'planned','attempts':[],'dependencies':[trainkey,selkey],
   'train_key':trainkey,'selection_key':selkey}
  self.definition=dict(self.task)
  self.tasks[key]=self.task
 def tearDown(self):self.temp.cleanup()
 def proof(self):return m.native_fit_proof(self.root,self.task,self.definition,self.tasks)
 def test_selection_only_dependency_without_data_npz_is_validated(self):
  proof=self.proof()
  self.assertIsNotNone(proof)
  self.assertEqual(proof['selection']['key'],self.selection['key'])
  self.assertEqual(proof['dependency_evidence'][self.selection['key']]['data_sha256'],None)
  self.assertEqual(proof['dependency_evidence'][self.selection['key']]['selection_sha256'],self.selection_hashes['selection.json'])
  self.assertEqual(proof['dependency_evidence'][self.train['key']]['data_sha256'],self.train_hashes['data.npz'])
  self.assertEqual(proof['role_cache']['id_hashes'],self.ids)
  self.assertEqual(proof['cold_model_manifest_sha256'],hashlib.sha256(self.cold_path.read_bytes()).hexdigest())
 def test_train_dependency_without_data_npz_fails_closed(self):
  depkey=self.train['key'];result=Path(self.train['result_path']);d=json.loads(result.read_text())
  d['validation']['files']={};jwrite(result,d)
  self.assertIsNone(self.proof())
 def test_mutated_train_or_selection_hash_fails_closed(self):
  train=self.root/'artifacts'/self.train['key']/'data.npz';train.write_bytes(b'changed')
  self.assertIsNone(self.proof())
  train.write_bytes(b'tiny cohort bytes')
  sel=self.root/'artifacts'/self.selection['key']/'selection.json';sel.write_text('{"selected_params":{"C":2}}')
  self.assertIsNone(self.proof())
 def test_current_cold_alias_of_candidate_model_blocks_refit(self):
  target=(pathlib.PurePosixPath(self.root.name)/'artifacts'/self.task['key']/'pipeline.joblib').as_posix()
  cold_index(self.root,[{'logical_path':'runtime_20261025/cold_models/old.joblib','aliases':[target]}])
  self.assertIsNone(self.proof())
 def test_current_cold_logical_path_of_candidate_model_blocks_refit(self):
  target=(pathlib.PurePosixPath(self.root.name)/'artifacts'/self.task['key']/'pipeline.joblib').as_posix()
  cold_index(self.root,[{'logical_path':target,'aliases':[]}])
  self.assertIsNone(self.proof())
 def test_missing_or_malformed_cold_manifest_blocks_native_fit(self):
  self.cold_path.unlink();self.assertIsNone(self.proof())
  jwrite(self.cold_path,{'schema_version':'wrong','members':[]});self.assertIsNone(self.proof())
 def test_prior_attempt_reuse_or_existing_same_task_file_blocks(self):
  self.task['attempts']=[{'attempt_id':'old'}];self.assertIsNone(self.proof())
  self.task['attempts']=[];self.task['reuse_pipeline']=True;self.definition['reuse_pipeline']=True;self.assertIsNone(self.proof())
  self.task.pop('reuse_pipeline');self.definition.pop('reuse_pipeline')
  write(self.root/'artifacts'/self.task['key']/'pipeline.joblib',b'existing model')
  self.assertIsNone(self.proof())
class HelperIdentityTests(unittest.TestCase):
 def fake_proc(self,proc_root,pid,ppid,pgid,ticks,argv,cwd,uid=1000):
  base=Path(proc_root)/str(pid);base.mkdir(parents=True)
  fields=['S',str(ppid),str(pgid)]+['0']*16+[str(ticks)]
  (base/'stat').write_text(f'{pid} (python3) '+' '.join(fields))
  (base/'status').write_text(f'Name:\tpython3\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
  (base/'cmdline').write_bytes(b'\0'.join(x.encode() for x in argv)+b'\0')
  (base/'cwd').symlink_to(cwd,target_is_directory=True)
 def active_fixture(self,tmp,wrong_ticks=False):
  root=Path(tmp)/'runtime_20261025';root.mkdir()
  freeze,source_map,_=install(root)
  proc=Path(tmp)/'proc';proc.mkdir()
  opid='auto_storage_20261028T010000Z_12345678';nonce='a'*32;base='b'*64
  op=root/'runs'/opid;op.mkdir(parents=True)
  private=root/'logs/private/cold_auto_compaction'/opid;private.mkdir(parents=True)
  driver_pid,wrapper_pid,child_pid=201,202,203
  driver_argv=[str(root.parent/'venv/bin/python'),str(root/'source/cold_auto_compaction.py'),'--archive-io-profile',m.IO_PROFILE]
  wrapper_argv=[str(root.parent/'venv/bin/python'),str(root/'source/run_batch.py'),'--baseline-sha256',base,'--operation-id',opid,'--batch-policy',m.BATCH_POLICY,'--archive-io-profile',m.IO_PROFILE]
  child_argv=[str(root.parent/'venv/bin/python'),str(root/'source/commit_batch_child.py'),'--operation-dir',str(op),'--baseline-sha256',base,'--operation-id',opid,'--hold-nonce',nonce,'--batch-policy',m.BATCH_POLICY,'--archive-io-profile',m.IO_PROFILE]
  self.fake_proc(proc,driver_pid,1,driver_pid,111,driver_argv,root)
  self.fake_proc(proc,wrapper_pid,driver_pid,wrapper_pid,222,wrapper_argv,root)
  child_ticks='334' if wrong_ticks else '333'
  self.fake_proc(proc,child_pid,wrapper_pid,child_pid,child_ticks,child_argv,root)
  jwrite(root/'ADMISSION_HOLD.json',{'owner_operation':m.OWNER_OPERATION,'batch_policy':m.BATCH_POLICY,
   'operation_id':opid,'nonce':nonce,'reason':'one-shot bounded cold-model archive batch; pause new admissions only'})
  jwrite(private/'private_process_inventory.json',{'operation_id':opid,'archive_io_profile':m.IO_PROFILE,
   'driver_identity':{'pid':driver_pid,'process_start_ticks':'111','source_sha256':source_map['cold_auto_compaction.py']},
   'wrapper_identity':{'pid':wrapper_pid,'process_start_ticks':'222','pgid':wrapper_pid,'argv':wrapper_argv}})
  jwrite(op/'private_child_identity.json',{'pid':child_pid,'process_start_ticks':'333','pgid':child_pid,
   'script':str(root/'source/commit_batch_child.py'),'address_space_limit_bytes':939524096})
  jwrite(op/'private_admission.json',{'batch_policy':m.BATCH_POLICY,'archive_io_profile':m.IO_PROFILE,
   'storage_codec_policy':None,'helper_reservation_bytes':int(1.5*1024**3),
   'policy_host_reserve_bytes':6*1024**3,'policy_growth_margin_bytes':2*1024**3})
  return root,proc,freeze
 def test_actual_helper_chain_contract_accepts_mixedsmall_identity(self):
  with tempfile.TemporaryDirectory() as td:
   root,proc,freeze=self.active_fixture(td)
   state=m.inspect_runtime(root,freeze,proc_root=proc,uid=1000)
   self.assertEqual(state['mode'],'active')
   self.assertEqual(state['reason'],'verified_raw_archive_helper')
   self.assertEqual(state['evidence']['helper_reservation_bytes'],int(1.5*1024**3))
 def test_helper_pid_start_tick_mismatch_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   root,proc,freeze=self.active_fixture(td,wrong_ticks=True)
   state=m.inspect_runtime(root,freeze,proc_root=proc,uid=1000)
   self.assertEqual(state['mode'],'blocked')
   self.assertIn(state['reason'],('child_receipt_identity_mismatch','child_process_tree_mismatch','child_command_mismatch'))
class StorageGateBoundaryTests(unittest.TestCase):
 def test_standard_storage_allow_source_is_unchanged_from_live(self):
  staged=ROOT/'source/controller.py'
  live=ROOT.parents[2]/'source/controller.py'
  staged_text=staged.read_text();live_text=live.read_text()
  st=ast.parse(staged_text);lt=ast.parse(live_text)
  sn=next(n for n in st.body if isinstance(n,ast.FunctionDef) and n.name=='storage_allow')
  ln=next(n for n in lt.body if isinstance(n,ast.FunctionDef) and n.name=='storage_allow')
  self.assertEqual(ast.get_source_segment(staged_text,sn),ast.get_source_segment(live_text,ln))
  self.assertIn("if storage and archive_fit_overlap_context().get('mode')!='blocked':",staged_text)
  self.assertIn("archive_context.get('mode')=='active'",staged_text)

if __name__=='__main__':unittest.main(verbosity=2)
