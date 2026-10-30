import ast,hashlib,importlib.util,json,pathlib,sys,tempfile,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codec_overlap_helper',HERE/'source/archive_fit_admission.py')
h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
G=1024**3
SOURCES=['controller.py','archive_fit_admission.py','cold_auto_compaction.py','run_batch.py','commit_batch_child.py','cold_model_storage.py','cold_codec_storage.py','reversible_joblib_codec.py','cold_storage_safety.py','batch_plan.py','admission_evidence.py']
NATIVE=['cache/cache_manifest.json','manifests/E4_MANIFEST.json','manifests/E5_MANIFEST.json']
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);return hashlib.sha256(b).hexdigest()
def fixture(root):
 root=pathlib.Path(root);sh={}
 for n in SOURCES:
  b=(HERE/'source/archive_fit_admission.py').read_bytes() if n=='archive_fit_admission.py' else (b'PINS = {}\n' if n=='cold_auto_compaction.py' else b'SOURCE_PINS = {}\n' if n=='run_batch.py' else ('fixture '+n+'\n').encode())
  sh[n]=put(root/'source'/n,b)
 ni={n:put(root/n,('fixture '+n).encode()) for n in NATIVE}
 scope={'experiments':[4,5],'kind':'fit','never_attempted':True,'reuse_pipeline':False,'routes':{'4':['direct','treatment'],'5':['direct','synthetic']},'require_successful_dependencies':True,'no_existing_same_task_pipeline_or_checkpoint':True,'native_input_only':True,'archive_model_aliases_must_be_terminal':True}
 resources={'helper_reservation_gib':1.5,'helper_cpu_reservation_units':1,'host_os_harbor_reserve_gib':6,'commitment_growth_margin_gib':2,'admission_only_safety_buffer_gib':1,'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'archive_wall_seconds':1800,'archive_wrapper_wall_seconds':1860,'archive_child_rss_limit_bytes':1073741824,'archive_child_address_space_limit_bytes':939524096,'archive_wrapper_rss_limit_bytes':1610612736,'native_threads':1,'nested_threads':1,'batch_max_bytes':G,'batch_max_inode_groups':64,'encoded_temp_max_bytes':4*G,'archive_disk_reserve_bytes':10*G,'archive_disk_growth_margin_bytes':2*G}
 op={'owner_operation':h.OWNER_OPERATION,'batch_policy':h.CODEC_BATCH_POLICY,'archive_io_profile':h.CODEC_IO_PROFILE,'storage_codec_policy':h.CODEC_STORAGE_POLICY}
 doc={'schema':'lamost-archive-native-codec-fit-overlap-policy/1','status':'qualified','policy_id':h.CODEC_POLICY_ID,'scope':scope,'resources':resources,'archive_operation':op,'overlap_classes':{'current_workers':'validated_existing_worker_identities','new_workers':'native_fit_proof_pristine_task_and_dependencies'},'source_sha256':sh,'native_input_manifests':ni,'qualification_path':'reports/engineering_audits/q.json'}
 pp=root/h.CODEC_POLICY_REL;ps=put(pp,json.dumps(doc,sort_keys=True,separators=(',',':')).encode())
 test_hashes={n:put(root/n,('fixture test '+n).encode()) for n in ('tests/test_native_codec_overlap.py','tests/test_native_fit_scope.py','tests/test_verified_zombie_reap.py','tests/test_driver_cli_alignment.py')}
 focused={'schema':'lamost-archive-native-codec-fit-overlap-focused-tests/1','status':'passed','source_sha256':sh,'test_file_sha256':test_hashes,'expected_test_count':25,'passed_test_count':25,'failed_test_count':0,'fit_attempts_started':0,'limits':{'address_space_limit_bytes':1073741824,'wall_seconds':60,'native_threads':1,'nice':19}}
 fp='reports/engineering_audits/focused_codec_tests.json';fs=put(root/fp,json.dumps(focused,sort_keys=True,separators=(',',':')).encode())
 admission={'schema':'lamost-archive-native-codec-overlap-admission-harness/1','status':'passed','source_sha256':sh,'fit_attempts_started':0,'archive_helper_fixture_only':True,'controller_admission_gate':'passed','helper_identity_and_resource_gates':'passed','existing_worker_identity_validation':'passed','archive_alias_ownership_closure':'passed','no_candidate_archive_model_fd_race':True,'workers_checked':0,'unverified_workers':0,'archive_operation':op,'overlap_classes':doc['overlap_classes']}
 ap='reports/engineering_audits/native_admission_harness.json';ass=put(root/ap,json.dumps(admission,sort_keys=True,separators=(',',':')).encode())
 q={'schema':h.CODEC_QUALIFICATION_SCHEMA,'status':'passed','policy_sha256':ps,'source_sha256':sh,'native_input_manifests':ni,
   'focused_codec_tests':{'status':'passed','receipt_path':fp,'receipt_sha256':fs,'test_file_sha256':test_hashes},
   'native_admission_harness':{'status':'passed','receipt_path':ap,'receipt_sha256':ass},
   'overlap_classes':doc['overlap_classes']}
 qs=put(root/doc['qualification_path'],json.dumps(q,sort_keys=True,separators=(',',':')).encode())
 frozen={'source_sha256':{'controller.py':sh['controller.py'],'archive_fit_admission.py':sh['archive_fit_admission.py']},h.CODEC_POLICY_FIELD:ps,h.CODEC_QUALIFICATION_FIELD:qs}
 return root,frozen,doc

def fixture12(root):
 root=pathlib.Path(root);sh={}
 for n in SOURCES:
  if n=='archive_fit_admission.py': b=pathlib.Path(h.__file__).read_bytes()
  elif n in ('cold_auto_compaction.py','commit_batch_child.py'): b=b'PINS = {}\n'
  elif n=='run_batch.py': b=b'SOURCE_PINS = {}\n'
  else: b=('fixture '+n+'\n').encode()
  sh[n]=put(root/'source'/n,b)
 ni={n:put(root/n,('fixture '+n).encode()) for n in NATIVE}
 scope={'experiments':[4,5],'kind':'fit','never_attempted':True,'reuse_pipeline':False,
   'routes':{'4':['direct','treatment'],'5':['direct','synthetic']},
   'require_successful_dependencies':True,'no_existing_same_task_pipeline_or_checkpoint':True,
   'native_input_only':True,'archive_model_aliases_must_be_terminal':True}
 resources={'helper_reservation_gib':1.5,'helper_cpu_reservation_units':1,
   'host_os_harbor_reserve_gib':6,'commitment_growth_margin_gib':2,'admission_only_safety_buffer_gib':1,
   'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,
   'termination_grace_seconds':30,'archive_wall_seconds':5400,'archive_wrapper_wall_seconds':5460,
   'archive_child_rss_limit_bytes':1073741824,'archive_child_address_space_limit_bytes':939524096,
   'archive_wrapper_rss_limit_bytes':1610612736,'native_threads':1,'nested_threads':1,
   'batch_max_bytes':4*G,'batch_max_inode_groups':64,'encoded_temp_max_bytes':8*G,
   'archive_disk_reserve_bytes':14*G,'archive_disk_growth_margin_bytes':2*G,'max_payload_bytes':12*G}
 op={'owner_operation':h.OWNER_OPERATION,'batch_policy':h.CODEC_BATCH_POLICY,
   'archive_io_profile':h.CODEC12_IO_PROFILE,'storage_codec_policy':h.CODEC12_STORAGE_POLICY}
 overlap={'current_workers':'validated_existing_worker_identities',
   'new_workers':'native_fit_proof_pristine_task_and_dependencies'}
 qpath='reports/engineering_audits/q12.json'
 doc={'schema':'lamost-archive-native-codec-payload12-fit-overlap-policy/1',
   'status':'qualified','policy_id':h.CODEC12_POLICY_ID,'scope':scope,'resources':resources,
   'archive_operation':op,'overlap_classes':overlap,'source_sha256':sh,
   'native_input_manifests':ni,'qualification_path':qpath}
 pp=root/h.CODEC12_POLICY_REL
 ps=put(pp,json.dumps(doc,sort_keys=True,separators=(',',':')).encode())
 codec4_tests=('tests/test_codec4gib_archive_profile.py','tests/test_driver_cli_alignment.py')
 codec4_hashes={n:put(root/n,('fixture test '+n).encode()) for n in codec4_tests}
 codec4={'schema':'lamost-codec4-profile-focused-tests/1','status':'passed',
   'source_sha256':sh,'test_file_sha256':codec4_hashes,'expected_test_count':10,
   'passed_test_count':10,'failed_test_count':0,'fit_attempts_started':0,
   'limits':{'address_space_limit_bytes':1073741824,'wall_seconds':60,'native_threads':1,'nice':19}}
 codec4_path='reports/engineering_audits/codec4.json'
 codec4_sha=put(root/codec4_path,json.dumps(codec4,sort_keys=True,separators=(',',':')).encode())
 payload_test='tests/test_codec_payload12_profile.py'
 payload_hashes={payload_test:put(root/payload_test,b'fixture payload12 focused test')}
 payload={'schema':'lamost-codec-payload12-profile-focused-tests/1','status':'passed',
   'source_sha256':sh,'test_file_sha256':payload_hashes,'expected_test_count':8,
   'passed_test_count':8,'failed_test_count':0,'fit_attempts_started':0,
   'limits':{'address_space_limit_bytes':1073741824,'wall_seconds':60,'native_threads':1,'nice':19}}
 payload_path='reports/engineering_audits/payload12.json'
 payload_sha=put(root/payload_path,json.dumps(payload,sort_keys=True,separators=(',',':')).encode())
 admission={'schema':'lamost-archive-native-codec-overlap-admission-harness/1',
   'status':'passed','source_sha256':sh,'fit_attempts_started':0,
   'archive_helper_fixture_only':True,'controller_admission_gate':'passed',
   'helper_identity_and_resource_gates':'passed','existing_worker_identity_validation':'passed',
   'archive_alias_ownership_closure':'passed','no_candidate_archive_model_fd_race':True,
   'workers_checked':0,'unverified_workers':0,'archive_operation':op,'overlap_classes':overlap}
 admission_path='reports/engineering_audits/native_admission12.json'
 admission_sha=put(root/admission_path,json.dumps(admission,sort_keys=True,separators=(',',':')).encode())
 q={'schema':h.CODEC12_QUALIFICATION_SCHEMA,'status':'passed','policy_sha256':ps,
   'source_sha256':sh,'native_input_manifests':ni,
   'codec4_profile_tests':{'status':'passed','receipt_path':codec4_path,
     'receipt_sha256':codec4_sha,'test_file_sha256':codec4_hashes},
   'payload12_profile_tests':{'status':'passed','receipt_path':payload_path,
     'receipt_sha256':payload_sha,'test_file_sha256':payload_hashes},
   'native_admission_harness':{'status':'passed','receipt_path':admission_path,
     'receipt_sha256':admission_sha},'overlap_classes':overlap}
 qs=put(root/qpath,json.dumps(q,sort_keys=True,separators=(',',':')).encode())
 frozen={'source_sha256':{'controller.py':sh['controller.py'],
   'archive_fit_admission.py':sh['archive_fit_admission.py']},
   h.CODEC12_POLICY_FIELD:ps,h.CODEC12_QUALIFICATION_FIELD:qs}
 return root,frozen,doc,admission

def procset(root,opid,nonce,doc):
 py=str(root.parent/'venv/bin/python');base='a'*64
 op=doc['archive_operation'];io=op['archive_io_profile'];bp=op['batch_policy'];codec=op['storage_codec_policy']
 d={'pid':11,'ppid':1,'pgid':11,'start_ticks':'101','uid':1000,'cwd':str(root),'argv':[py,str(root/'source/cold_auto_compaction.py'),'--storage-codec-policy',codec,'--archive-io-profile',io]}
 w={'pid':12,'ppid':11,'pgid':12,'start_ticks':'102','uid':1000,'cwd':str(root),'argv':[py,str(root/'source/run_batch.py'),'--baseline-sha256',base,'--operation-id',opid,'--batch-policy',bp,'--storage-codec-policy',codec,'--archive-io-profile',io]}
 c={'pid':13,'ppid':12,'pgid':13,'start_ticks':'103','uid':1000,'cwd':str(root),'argv':[py,str(root/'source/commit_batch_child.py'),'--operation-dir',str(root/'runs'/opid),'--baseline-sha256',base,'--operation-id',opid,'--hold-nonce',nonce,'--batch-policy',bp,'--storage-codec-policy',codec,'--archive-io-profile',io]}
 return [('cold_auto_compaction.py',d),('run_batch.py',w),('commit_batch_child.py',c)],d,w,c

def write_proc_fixture(base, records, *, extra=None):
 base=pathlib.Path(base);base.mkdir(parents=True,exist_ok=True)
 rows=list(records)
 if extra:rows.extend(extra)
 for role,rec in rows:
  pid=int(rec['pid']);d=base/str(pid);d.mkdir()
  fields=['S',str(rec['ppid']),str(rec['pgid'])]+['0']*16+[str(rec['start_ticks'])]
  (d/'stat').write_text(f"{pid} (python) "+' '.join(fields)+'\n')
  (d/'status').write_text(f"Name:\tpython\nUid:\t{rec['uid']}\t{rec['uid']}\t{rec['uid']}\t{rec['uid']}\n")
  (d/'cmdline').write_bytes(b'\0'.join(x.encode() for x in rec['argv'])+b'\0')
  (d/'cwd').symlink_to(rec['cwd'],target_is_directory=True)
 return base

def active(root,frozen,doc):
 opid='auto_storage_20261029T010000Z_12345678';nonce='a'*32
 op=doc['archive_operation'];put(root/'ADMISSION_HOLD.json',json.dumps({'owner_operation':h.OWNER_OPERATION,'batch_policy':op['batch_policy'],'archive_io_profile':op['archive_io_profile'],'storage_codec_policy':op['storage_codec_policy'],'operation_id':opid,'nonce':nonce,'reason':'one-shot bounded cold-model archive batch; pause new admissions only'}).encode())
 od=root/'runs'/opid;od.mkdir(parents=True);pd=root/'logs/private/cold_auto_compaction'/opid;pd.mkdir(parents=True)
 rec,d,w,c=procset(root,opid,nonce,doc)
 put(pd/'private_process_inventory.json',json.dumps({'operation_id':opid,'archive_io_profile':doc['archive_operation']['archive_io_profile'],'driver_identity':{'pid':d['pid'],'process_start_ticks':d['start_ticks'],'source_sha256':doc['source_sha256']['cold_auto_compaction.py']},'wrapper_identity':{'pid':w['pid'],'process_start_ticks':w['start_ticks'],'pgid':w['pgid'],'argv':w['argv']}}).encode())
 put(od/'private_child_identity.json',json.dumps({'pid':c['pid'],'process_start_ticks':c['start_ticks'],'pgid':c['pgid'],'script':str(root/'source/commit_batch_child.py'),'address_space_limit_bytes':939524096}).encode())
 op=doc['archive_operation'];res=doc['resources'];tail=77;required=res['batch_max_bytes']+res['archive_disk_reserve_bytes']+res['archive_disk_growth_margin_bytes']+tail;admission={'batch_policy':op['batch_policy'],'archive_io_profile':op['archive_io_profile'],'storage_codec_policy':op['storage_codec_policy'],'helper_reservation_bytes':int(1.5*G),'policy_host_reserve_bytes':6*G,'policy_growth_margin_bytes':2*G,'batch_max_bytes':res['batch_max_bytes'],'batch_max_inode_groups':res['batch_max_inode_groups'],'encoded_temp_max_bytes':res['encoded_temp_max_bytes'],'child_wall_limit_seconds':res['archive_wall_seconds'],'transient_disk_reserve_bytes':res['archive_disk_reserve_bytes'],'archive_tail_backup_bytes':tail,'transient_disk_required_bytes':required};
 if op['storage_codec_policy']==h.CODEC12_STORAGE_POLICY:admission['max_payload_bytes']=res['max_payload_bytes']
 put(od/'private_admission.json',json.dumps(admission).encode())
 return rec
class RawAdmissionCompatibilityTests(unittest.TestCase):
 def test_current_raw_policy_fit_proof_and_reaper_are_ast_identical(self):
  live=pathlib.Path(__file__).resolve().parent/'fixtures'/'archive_fit_admission_raw_baseline.py'
  self.assertEqual(hashlib.sha256(live.read_bytes()).hexdigest(),'d06fdf9b616b41eebcbaf43f4276c9bab2085901f618f8f6c17068538bd0b25c')
  current=pathlib.Path(h.__file__).read_text();baseline=live.read_text()
  def nodes(text):
   tree=ast.parse(text)
   return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
  old,new=nodes(baseline),nodes(current)
  for name in ('_policy','native_fit_proof','reap_recorded_zombies','_cold_model_manifest_refs'):
   self.assertEqual(new[name],old[name],name)
  def value(text,name):
   for n in ast.parse(text).body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets):return ast.literal_eval(n.value)
   raise AssertionError(name)
  self.assertEqual(value(current,'IO_PROFILE'),'bounded-1800-mixedsmall4gib2048')
  self.assertEqual(value(current,'IO_PROFILE'),value(baseline,'IO_PROFILE'))

class CodecPolicyTests(unittest.TestCase):
 def test_only_exact_qualified_codec_profile_is_allowed(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,_=fixture(td)
   self.assertTrue(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.IO_PROFILE,batch_policy=h.BATCH_POLICY,storage_codec_policy=None))
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,{},archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
  with tempfile.TemporaryDirectory() as td:
   r,f,_=fixture(td);(r/'source/reversible_joblib_codec.py').write_bytes(b'changed pinned codec')
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
 def test_missing_focused_receipt_or_test_file_tamper_fails_closed(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);qp=r/doc['qualification_path'];q=json.loads(qp.read_text());q.pop('focused_codec_tests')
   qs=put(qp,json.dumps(q,sort_keys=True,separators=(',',':')).encode());f[h.CODEC_QUALIFICATION_FIELD]=qs
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);(r/'tests/test_native_codec_overlap.py').write_bytes(b'tampered test')
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
 def test_unqualified_or_wrong_caps_source_or_receipt_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);q=r/doc['qualification_path'];qd=json.loads(q.read_text());qd['status']='not_run';qs=put(q,json.dumps(qd,sort_keys=True,separators=(',',':')).encode());f[h.CODEC_QUALIFICATION_FIELD]=qs
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);doc['resources']['batch_max_inode_groups']=16;pp=r/h.CODEC_POLICY_REL;ps=put(pp,json.dumps(doc,sort_keys=True,separators=(',',':')).encode());f[h.CODEC_POLICY_FIELD]=ps
   self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC_STORAGE_POLICY))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc);bad=r/'runs/auto_storage_20261029T010000Z_12345678/private_admission.json';ad=json.loads(bad.read_text());ad['transient_disk_required_bytes']-=1;bad.write_text(json.dumps(ad))
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('blocked','codec_admission_envelope_mismatch'))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc);bad=r/'runs/auto_storage_20261029T010000Z_12345678/private_admission.json'
   ad=json.loads(bad.read_text());ad['batch_max_inode_groups']=65;bad.write_text(json.dumps(ad))
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('blocked','codec_admission_envelope_mismatch'))
 def test_exact_process_receipt_chain_allows_active_and_bad_identity_blocks(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc)
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('active','verified_codec_archive_helper'))
   self.assertEqual(state['evidence']['helper_cpu_reservation_units'],1)
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc);rec[-1][1]['argv'][-1]='mismatched'
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('blocked','child_command_mismatch'))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc);rec[0][1]['uid']=2000
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('blocked','helper_uid_mismatch'))
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td);rec=active(r,f,doc)
   foreign={'pid':14,'ppid':1,'pgid':14,'start_ticks':'104','uid':1000,'cwd':str(r/'foreign'),'argv':[str(r.parent/'venv/bin/python'),str(r/'foreign'/'cold_auto_compaction.py')]}
   (r/'foreign').mkdir()
   proc=write_proc_fixture(r/'proc_fixture',rec,extra=[('cold_auto_compaction.py',foreign)])
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('blocked','unrecognized_archive_script_process'))
 def test_payload12_qualified_policy_and_exact_helper_identity_fixture(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,doc,receipt=fixture12(td)
   self.assertTrue(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC12_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC12_STORAGE_POLICY))
   self.assertTrue(receipt['archive_helper_fixture_only']);self.assertEqual(receipt['workers_checked'],0)
   rec=active(r,f,doc)
   proc=write_proc_fixture(r/'proc_fixture',rec)
   state=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((state['mode'],state['reason']),('active','verified_codec_archive_helper'))
   self.assertEqual(state['evidence']['source_sha256'],receipt['source_sha256'])
   rec[0][1]['uid']=2000
   proc=write_proc_fixture(r/'proc_fixture2',rec)
   rejected=h.inspect_runtime(r,f,proc_root=proc,uid=1000)
   self.assertEqual((rejected['mode'],rejected['reason']),('blocked','helper_uid_mismatch'))
  for field,bad_value in [('existing_worker_identity_validation','not_run'),('archive_alias_ownership_closure','not_run'),('no_candidate_archive_model_fd_race',False)]:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as td:
    r,f,doc,receipt=fixture12(td);ap=r/'reports/engineering_audits/native_admission12.json';ad=json.loads(ap.read_text());ad[field]=bad_value;asha=put(ap,json.dumps(ad,sort_keys=True,separators=(',',':')).encode())
    qp=r/doc['qualification_path'];q=json.loads(qp.read_text());q['native_admission_harness']['receipt_sha256']=asha;f[h.CODEC12_QUALIFICATION_FIELD]=put(qp,json.dumps(q,sort_keys=True,separators=(',',':')).encode())
    self.assertFalse(h.native_codec_overlap_policy_allowed(r,f,archive_io_profile=h.CODEC12_IO_PROFILE,batch_policy=h.CODEC_BATCH_POLICY,storage_codec_policy=h.CODEC12_STORAGE_POLICY))
class NativeFitCodecQualificationTests(unittest.TestCase):
 def test_pristine_native_fit_gets_codec_profile_binding_and_old_attempt_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   r,f,doc=fixture(td)
   ids={k:('%064x'%(i+1)) for i,k in enumerate(('fit','tune','cal','test'))}
   source='b'*64
   role=put(r/'cache/roles/rep_1.npz',b'tiny role fixture')
   put(r/'cache/cache_manifest.json',json.dumps({'cache_files':{'roles/rep_1.npz':role},'roles':{'1':{'source_sha256':source,'id_hashes':ids}}}).encode())
   for e in ('E4','E5'):put(r/f'manifests/{e}_MANIFEST.json',json.dumps({'role_hashes':{'1':{'source_sha256':source,'id_hashes':ids}}}).encode())
   put(r/'manifests/cold_model_store_manifest.json',json.dumps({'schema_version':'lamost-cold-model-store/1','members':[]}).encode())
   dep='e4/rep_1/cohort/clean';data=put(r/'artifacts'/dep/'data.npz',b'tiny native input')
   result=r/'artifacts'/dep/'fit_result.json'
   put(result,json.dumps({'key':dep,'status':'successful','validation':{'status':'validated','task_key':dep,'files':{'data.npz':data}}}).encode())
   selection=r/'manifests/imported_selections/clean/selection.json';put(selection,json.dumps({'selected_params':{'n_estimators':7}}).encode())
   doc['native_input_manifests']={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in NATIVE}
   pp=r/h.CODEC_POLICY_REL;ps=put(pp,json.dumps(doc,sort_keys=True,separators=(',',':')).encode())
   qp=r/doc['qualification_path'];qd=json.loads(qp.read_text());qd['policy_sha256']=ps;qd['native_input_manifests']=doc['native_input_manifests']
   qs=put(qp,json.dumps(qd,sort_keys=True,separators=(',',':')).encode());f[h.CODEC_POLICY_FIELD]=ps;f[h.CODEC_QUALIFICATION_FIELD]=qs
   task={'key':'e4/rep_1/fit/direct/random_forest/label_noise_20','experiment':4,'kind':'fit','route':'direct','method':'random_forest','rep':1,'status':'planned','attempts':[],'reuse_pipeline':False,'dependencies':[dep],'train_key':dep,'selection_source':str(selection.parent)}
   tasks={dep:{'key':dep,'status':'validated_terminal','outcome':'successful','validation_state':'validated','result_path':str(result)},task['key']:task}
   hold={'owner_operation':h.OWNER_OPERATION,'batch_policy':h.CODEC_BATCH_POLICY}
   put(r/'ADMISSION_HOLD.json',json.dumps(hold).encode())
   proof=h.qualify_candidate(r,task,dict(task),tasks,f)
   self.assertIsNotNone(proof,repr(h.native_fit_proof(r,task,dict(task),tasks)));self.assertEqual(proof['overlap_profile'],'codec')
   self.assertEqual(proof['archive_operation'],doc['archive_operation'])
   self.assertIsNone(h.qualify_candidate(r,{**task,'attempts':[{'attempt_id':'old'}]},dict(task),tasks,f))
 def test_nonempty_archived_alias_for_candidate_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   r=pathlib.Path(td);ids={k:('%064x'%(i+1)) for i,k in enumerate(('fit','tune','cal','test'))};source='b'*64
   role=put(r/'cache/roles/rep_1.npz',b'tiny role fixture')
   put(r/'cache/cache_manifest.json',json.dumps({'cache_files':{'roles/rep_1.npz':role},'roles':{'1':{'source_sha256':source,'id_hashes':ids}}}).encode())
   for e in ('E4','E5'):put(r/f'manifests/{e}_MANIFEST.json',json.dumps({'role_hashes':{'1':{'source_sha256':source,'id_hashes':ids}}}).encode())
   dep='e4/rep_1/cohort/clean';data=put(r/'artifacts'/dep/'data.npz',b'tiny native input');result=r/'artifacts'/dep/'fit_result.json'
   put(result,json.dumps({'key':dep,'status':'successful','validation':{'status':'validated','task_key':dep,'files':{'data.npz':data}}}).encode())
   selection=r/'manifests/imported_selections/clean/selection.json';put(selection,json.dumps({'selected_params':{'n_estimators':7}}).encode())
   task={'key':'e4/rep_1/fit/direct/random_forest/label_noise_20','experiment':4,'kind':'fit','route':'direct','method':'random_forest','rep':1,'status':'planned','attempts':[],'reuse_pipeline':False,'dependencies':[dep],'train_key':dep,'selection_source':str(selection.parent)}
   tasks={dep:{'key':dep,'status':'validated_terminal','outcome':'successful','validation_state':'validated','result_path':str(result)},task['key']:task}
   cold=r/'manifests/cold_model_store_manifest.json';put(cold,json.dumps({'schema_version':'lamost-cold-model-store/1','members':[]} ).encode())
   proof=h.native_fit_proof(r,task,dict(task),tasks);self.assertIsNotNone(proof)
   target=proof['candidate_pipeline_logical_path']
   put(cold,json.dumps({'schema_version':'lamost-cold-model-store/1','members':[{'logical_path':'runtime/other/pipeline.joblib','aliases':[target]}]}).encode())
   self.assertIsNone(h.native_fit_proof(r,task,dict(task),tasks))

if __name__=='__main__':unittest.main(verbosity=2)
