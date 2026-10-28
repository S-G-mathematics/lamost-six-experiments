import hashlib,json,pathlib,tempfile,unittest,subprocess
from finalization_safety import (begin_finalization_attempt,clear_finalization_latch,finish_finalization_attempt,
    portable_bundle_snapshot,portable_receipt_matches,PortableBundleError)
HERE=pathlib.Path(__file__).resolve().parents[1]

def write_bundle(root,mutations=None):
 runtime=root/'runtime_20261025';src=runtime/'source';tests=runtime/'tests';src.mkdir(parents=True,exist_ok=True);tests.mkdir(parents=True,exist_ok=True)
 source_names=('finalize_project.py','reporting.py','finalization_safety.py','final_review.py','audit_artifacts.py','calibration_replay.py','calibration_replay_supervisor.py')
 test_names=('test_finalization_safety.py','test_reporting_environment_policy.py','test_calibration_replay.py','test_calibration_replay_finalization_gate.py','test_calibration_replay_supervisor.py')
 sources=[];test_rows=[]
 for name in source_names:
  p=src/name;p.write_text('source '+name)
  sha=hashlib.sha256(p.read_bytes()).hexdigest()
  sources.append({'runtime_member':'runtime_20261025/source/'+name,'source_sha256':sha,'bundle_sha256':sha,'kind':'installed_port'})
 for name in test_names:
  p=tests/name;p.write_text('test '+name)
  sha=hashlib.sha256(p.read_bytes()).hexdigest()
  test_rows.append({'test_member':'runtime_20261025/tests/'+name,'portable_sha256':sha,'group':'fixture'})
 runner=tests/'run_portable_tests.sh'
 runner.write_text('#!/bin/bash\nset -e\n'+'\n'.join('  "'+f'$R/tests/{n}'+'" \\' for n in test_names[:-1])+'\n  "'+f'$R/tests/{test_names[-1]}'+'"\n')
 (src/'reporting_support_environment_20261026.json').write_text('{}\n')
 doc={'schema':'archive-native-installed-portable-tests/1','runtime_staging_present':False,
  'runner':'runtime_20261025/tests/run_portable_tests.sh','source_directory':'runtime_20261025/source','test_directory':'runtime_20261025/tests',
  'sources':sources,'tests':test_rows,'resource_review_proofs':[],'test_count_plan':{'fixture':4}}
 manifest=tests/'PORTABLE_TEST_BUNDLE.json';manifest.write_text(json.dumps(doc,sort_keys=True)+'\n')
 return runtime,doc,manifest

class FinalizationSafetyTests(unittest.TestCase):
 def test_unchanged_bundle_receipt_is_reused_only_for_exact_hashes(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   root=pathlib.Path(td);runtime,doc,manifest=write_bundle(root)
   snap=portable_bundle_snapshot(root,runtime)
   receipt={'schema_version':'lamost-terminal-portable-tests/1','status':'passed','exit_code':0,
    'bundle_fingerprint_sha256':snap['bundle_fingerprint_sha256'],'manifest_sha256':snap['manifest_sha256'],
    'runner_sha256':snap['runner_sha256'],'source_hashes':snap['source_hashes'],'test_hashes':snap['test_hashes'],
    'resource_proofs':snap['resource_proofs'],'environment_policy_sha256':snap['environment_policy_sha256'],
    'expected_test_count':snap['expected_test_count'],'passed_test_count':snap['expected_test_count']}
   self.assertTrue(portable_receipt_matches(receipt,snap))
   target=root/'runtime_20261025/source/reporting.py';target.write_text('changed source')
   with self.assertRaises(PortableBundleError):portable_bundle_snapshot(root,runtime)
   doc['sources'][1]['source_sha256']=hashlib.sha256(target.read_bytes()).hexdigest();doc['sources'][1]['bundle_sha256']=doc['sources'][1]['source_sha256']
   manifest.write_text(json.dumps(doc,sort_keys=True)+'\n')
   new=portable_bundle_snapshot(root,runtime)
   self.assertFalse(portable_receipt_matches(receipt,new))

 def test_two_same_fingerprint_failures_latch_but_changed_fingerprint_retries(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   runtime=pathlib.Path(td)/'runtime_20261025';runtime.mkdir()
   fingerprint='a'*64;payload={'input':'same'}
   for _ in range(2):
    started=begin_finalization_attempt(runtime,fingerprint,payload);self.assertEqual(started['status'],'started')
    done=finish_finalization_attempt(runtime,started['attempt_id'],'failed','fixture deterministic validation error')
    if _==1:self.assertEqual(done['status'],'FINALIZATION_REVIEW_REQUIRED')
   blocked=begin_finalization_attempt(runtime,fingerprint,payload)
   self.assertEqual(blocked['status'],'FINALIZATION_REVIEW_REQUIRED')
   changed=begin_finalization_attempt(runtime,'b'*64,{'input':'changed source/config'})
   self.assertEqual(changed['status'],'started')

 def test_subprocess_timeout_expired_is_operational_backoff(self):
  exc=subprocess.TimeoutExpired(cmd=['fixture'],timeout=60)
  self.assertTrue(__import__('finalization_safety').is_resource_backoff(exc))

 def test_interrupted_attempt_writes_separate_receipt_before_backoff(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   runtime=pathlib.Path(td)/'runtime_20261025';runtime.mkdir();fingerprint='e'*64;payload={'input':'running'}
   started=begin_finalization_attempt(runtime,fingerprint,payload)
   path=runtime/'logs/operational/finalization_retry_latch.json'
   latch=json.loads(path.read_text());latch['attempts'][0]['started_utc']='2026-01-01T00:00:00+00:00';path.write_text(json.dumps(latch))
   resumed=begin_finalization_attempt(runtime,fingerprint,payload)
   self.assertEqual(resumed['status'],'finalization_resource_backoff')
   rows=json.loads(path.read_text())['attempts']
   self.assertEqual(rows[0]['status'],'operational_backoff')
   receipt=runtime/'logs/operational/finalization_attempt_history'/fingerprint/(started['attempt_id']+'.json')
   self.assertTrue(receipt.is_file())
   self.assertEqual(json.loads(receipt.read_text())['reason'],'prior finalizer attempt ended without a completion receipt')

 def test_manual_clear_is_documented_and_preserves_attempt_history(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   runtime=pathlib.Path(td)/'runtime_20261025';runtime.mkdir();fingerprint='c'*64;payload={'config':'x'}
   for _ in range(2):
    started=begin_finalization_attempt(runtime,fingerprint,payload)
    finish_finalization_attempt(runtime,started['attempt_id'],'failed','same deterministic error')
   cleared=clear_finalization_latch(runtime,'Reviewed the failure receipts and corrected the identified operational cause.')
   self.assertTrue(cleared['attempt_history_preserved'])
   started=begin_finalization_attempt(runtime,fingerprint,payload)
   self.assertEqual(started['status'],'started')
   latch=json.loads((runtime/'logs/operational/finalization_retry_latch.json').read_text())
   self.assertEqual(len(latch['attempts']),3);self.assertEqual(latch['generation'],1)

 def test_resource_backoff_is_not_counted_as_deterministic_failure_and_is_bounded(self):
  with tempfile.TemporaryDirectory(dir=HERE/'tests') as td:
   runtime=pathlib.Path(td)/'runtime_20261025';runtime.mkdir();fingerprint='d'*64
   for idx in range(3):
    start=begin_finalization_attempt(runtime,fingerprint,{'resource':'same'})
    self.assertEqual(start['status'],'started')
    outcome=finish_finalization_attempt(runtime,start['attempt_id'],'operational_backoff','insufficient memory headroom','memory')
    if idx<2:
     self.assertEqual(outcome['status'],'finalization_resource_backoff')
     latch=json.loads((runtime/'logs/operational/finalization_retry_latch.json').read_text())
     rows=[x for x in latch['attempts'] if x['fingerprint_sha256']==fingerprint]
     self.assertEqual(sum(x['status']=='failed' for x in rows),0)
     rows[-1]['next_retry_epoch']=0;(runtime/'logs/operational/finalization_retry_latch.json').write_text(json.dumps(latch))
    else:self.assertEqual(outcome['status'],'FINALIZATION_REVIEW_REQUIRED')
