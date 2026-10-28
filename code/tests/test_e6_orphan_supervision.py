import importlib.util, json, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock

HERE=Path(__file__).resolve().parent
STAGE=HERE.parent
stub=types.ModuleType('admission_evidence')
with mock.patch.dict(sys.modules, {'admission_evidence':stub}):
 spec=importlib.util.spec_from_file_location('e6_controller_orphan_tests',HERE.parent/'source'/'controller.py')
 controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)

class E6OrphanSupervisionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='e6-orphan-');self.root=Path(self.tmp.name);self.old=controller.R;controller.R=self.root
  (self.root/'source').mkdir();self.script=self.root/'source'/'worker.py';self.script.write_text('# fixture worker\n')
  self.key='e6/rep_1/ensemble/equal';self.aid='attempt-123'
  task={'key':self.key,'experiment':6,'kind':'ensemble','method':None,'e6_protocol_version':'E6-v2','_controller_attempt_id':self.aid,
        '_controller_request_path':str(self.root/'attempts'/self.key/self.aid/'request.json'),
        '_controller_worker_script_path':str(self.script),'_controller_worker_script_sha256':controller.sha(self.script)}
  self.request=Path(task['_controller_request_path']);self.request.parent.mkdir(parents=True);self.task=task
  cfg={'task':task,'attempt_id':self.aid,'result_path':str(self.request.parent/'result.json'),'dispatch_policy_id':'test-policy'}
  task['_controller_request_sha256']=controller._e6_request_digest(cfg)
  self.cfg=cfg;self.request.write_text(json.dumps(cfg,sort_keys=True))
  self.record={'key':self.key,'experiment':6,'kind':'ensemble','e6_protocol_version':'E6-v2','pid':200,'process_start_ticks':'parent-tick',
               'request_path':str(self.request),'attempts':[{'attempt_id':self.aid}]}
  self.state={'schema_version':'lamost-e6-phase-process/1','status':'running','role':'e6_prediction_phase','task_key':self.key,
    'attempt_id':self.aid,'stage':'tune','phase_id':'uuid-1','parent_pid':200,'parent_start_ticks':'parent-tick',
    'child_pid':300,'child_start_ticks':'child-tick','child_uid':controller.os.getuid(),'child_pgid':300,
    'started_epoch':1.0,'timeout_seconds':600,'rss_limit_kib':10*1024*1024,'termination_grace_seconds':30,
    'request_path':str(self.request),'request_sha256':task['_controller_request_sha256'],'worker_script_sha256':controller.sha(self.script)}
  self.state_path=self.root/'artifacts'/self.key/'attempts'/self.aid/'e6_phase_tune.json';self.state_path.parent.mkdir(parents=True)
  self.write_state()
  self.proc={200:{'state':'S','ppid':1,'pgid':200,'start_ticks':'parent-tick','uid':controller.os.getuid()},
             300:{'state':'S','ppid':200,'pgid':300,'start_ticks':'child-tick','uid':controller.os.getuid()}}
 def tearDown(self):
  controller.R=self.old;controller.E6_ORPHAN_IDENTITIES.clear();self.tmp.cleanup()
 def write_state(self):self.state_path.write_text(json.dumps(self.state,sort_keys=True))
 def mock_proc(self):return mock.patch.object(controller,'_proc_identity',side_effect=lambda pid:self.proc.get(int(pid)))
 def test_valid_owned_child_is_discovered_and_only_its_group_is_signaled(self):
  with self.mock_proc():
   found=controller.orphan_phases(self.record)
   self.assertEqual(len(found),1);self.assertEqual(found[0][0:2],(300,'child-tick'))
   with mock.patch.object(controller.os,'killpg') as kill:
    self.assertTrue(controller.terminate_verified(300,'child-tick','phase_worker.py'))
    kill.assert_called_once_with(300,controller.signal.SIGTERM)
 def test_wrong_attempt_or_request_hash_blocks_without_signal(self):
  self.state['attempt_id']='other';self.write_state()
  with self.mock_proc(),mock.patch.object(controller.os,'killpg') as kill:
   self.assertEqual(controller.orphan_phases(self.record),[])
   self.assertTrue(self.record['_e6_orphan_blocked'])
   kill.assert_not_called()
 def test_live_child_wrong_uid_or_inherited_group_is_blocked(self):
  with self.mock_proc():
   for field,value in [('child_uid',controller.os.getuid()+1),('child_pgid',200)]:
    original=self.state[field];self.state[field]=value;self.write_state()
    found=controller.orphan_phases(self.record)
    self.assertEqual(found,[]);self.assertTrue(self.record['_e6_orphan_blocked'])
    self.state[field]=original
 def test_historical_attempt_state_is_ignored_without_affecting_current_attempt(self):
  olddir=self.state_path.parent.parent/'attempt-old';olddir.mkdir()
  old=(olddir/'e6_phase_tune.json');old.write_text(json.dumps(dict(self.state,attempt_id='attempt-old')))
  with self.mock_proc():
   found=controller.orphan_phases(self.record)
   self.assertEqual(len(found),1)
   self.assertFalse(self.record.get('_e6_orphan_blocked'))
 def test_pid_reuse_or_zombie_is_gone_and_never_signaled(self):
  with self.mock_proc(),mock.patch.object(controller.os,'killpg') as kill:
   self.proc[300]['start_ticks']='reused'
   self.assertEqual(controller.orphan_phases(self.record),[])
   self.assertFalse(self.record.get('_e6_orphan_blocked'))
   self.proc[300]['start_ticks']='child-tick';self.proc[300]['state']='Z'
   self.assertEqual(controller.orphan_phases(self.record),[])
   kill.assert_not_called()
 def test_source_inventory_hashes_all_twelve_sources_including_phase_helper(self):
  names=['controller.py','worker.py','science.py','phase_worker.py','cohorts.py','ensemble.py','ensemble_maintenance_patch.py','e6_phase_supervisor.py','svm_margin/science.py','svm_margin/worker.py','svm_margin/phase_worker.py','admission_evidence.py']
  for name in names:
   target=self.root/'source'/name;target.parent.mkdir(parents=True,exist_ok=True)
   if not target.exists():target.write_text('fixture source '+name+'\n')
  hashes=controller.source_hashes()
  self.assertEqual(set(hashes),set(names))
  self.assertEqual(len(hashes),12)
  self.assertIn('e6_phase_supervisor.py',hashes)
 def test_request_digest_uses_canonical_ascii_escaping(self):
  self.task['fixture_unicode']='galaxy-\u2605'
  self.cfg['task']=self.task
  expected=controller.hashlib.sha256(controller.json.dumps(
   {'task':{k:v for k,v in self.task.items() if k!='_controller_request_sha256'},
    'attempt_id':self.cfg['attempt_id'],'result_path':self.cfg['result_path'],'dispatch_policy_id':self.cfg['dispatch_policy_id']},
   sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
  self.assertEqual(controller._e6_request_digest(self.cfg),expected)
  self.assertNotEqual(expected,controller._canonical_sha256(
   {'task':{k:v for k,v in self.task.items() if k!='_controller_request_sha256'},
    'attempt_id':self.cfg['attempt_id'],'result_path':self.cfg['result_path'],'dispatch_policy_id':self.cfg['dispatch_policy_id']}))
 def test_live_child_is_reaped_even_if_state_claims_terminal(self):
  self.state['status']='successful';self.write_state()
  with self.mock_proc(),mock.patch.object(controller.os,'killpg') as kill:
   found=controller.orphan_phases(self.record)
   self.assertEqual(len(found),1)
   self.assertTrue(controller.terminate_verified(300,'child-tick','phase_worker.py',True))
   kill.assert_called_once_with(300,controller.signal.SIGKILL)
 def test_malformed_policy_or_worker_script_hash_blocks(self):
  with self.mock_proc():
   self.state['timeout_seconds']=601;self.write_state()
   self.assertEqual(controller.orphan_phases(self.record),[])
   self.assertTrue(self.record['_e6_orphan_blocked'])
   self.state['timeout_seconds']=600;self.state['worker_script_sha256']='f'*64;self.write_state()
   self.assertEqual(controller.orphan_phases(self.record),[])
   self.assertTrue(self.record['_e6_orphan_blocked'])

if __name__=='__main__':unittest.main()
