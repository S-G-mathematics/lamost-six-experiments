import csv, hashlib, json, pathlib, tempfile, unittest, zipfile
from unittest import mock
import publish_final as pf
from publish_final import Waiting, Invalid, TransientGit, once

def put(path,data):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
def digest(data): return hashlib.sha256(data).hexdigest()
def make_gate_fixture(base):
 root=pathlib.Path(base); runtime=root/'runtime'; repo=root/'repo'; project=root/'project'
 (runtime/'source').mkdir(parents=True);(runtime/'manifests').mkdir(parents=True);(runtime/'tests').mkdir(parents=True)
 (repo/'code/tests').mkdir(parents=True);(project/'benchmark/results').mkdir(parents=True);(project/'benchmark').mkdir(parents=True,exist_ok=True);(root/'packages').mkdir(parents=True)
 source=b'print("qualified")\n';source_sha=digest(source);put(runtime/'source/science.py',source)
 freeze={'source_sha256':{'science.py':source_sha}};freeze_b=json.dumps(freeze).encode();put(runtime/'manifests/freeze.json',freeze_b)
 task_b=b'{}';tasksha=digest(task_b);put(runtime/'manifests/tasks.json',task_b)
 for name in ('plan_summary.json','plan_amendments.json','E3_MANIFEST.json','E4_MANIFEST.json','E5_MANIFEST.json','E6_MANIFEST.json'):put(runtime/'manifests'/name,b'{}')
 runner=b'#!/bin/sh\n';test=b'# fixture\n';put(runtime/'tests/run.sh',runner);put(runtime/'tests/test_a.py',test)
 put(repo/'code/tests/run.sh',runner);put(repo/'code/tests/test_a.py',test)
 bundle={'runner':'runtime_20261025/tests/run.sh','runner_sha256':digest(runner),'tests':[{'test_member':'runtime_20261025/tests/test_a.py','portable_sha256':digest(test)}],'sources':[{'runtime_member':'runtime_20261025/source/science.py','source_sha256':source_sha}]}
 bundle_b=json.dumps(bundle).encode();put(runtime/'tests/PORTABLE_TEST_BUNDLE.json',bundle_b);put(repo/'code/tests/PORTABLE_TEST_BUNDLE.json',bundle_b)
 e1={}
 manifest_rows=[]
 for i in range(19):
  n=f'e1_{i:02d}.py';b=f'# E1 {i}\n'.encode();h=digest(b);e1[n]=h;put(project/'benchmark'/n,b)
  dest=f'code/E1/{n}';put(repo/dest,b);manifest_rows.append({'source':'project/benchmark/'+n,'destination':dest})
 config={'benchmark_python_source_sha256':e1};put(project/'benchmark/results/master_run_config.json',json.dumps(config).encode())
 (project/'benchmark/results/master_run_config.json').write_bytes(json.dumps(config).encode())
 put(project/'benchmark/protocol_source.txt',b'frozen protocol\n');put(project/'benchmark/dependencies.freeze.txt',b'frozen deps\n')
 with (repo/'file_manifest.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['source','destination']);w.writeheader();w.writerows(manifest_rows)
 proof={'decision':'pass','candidate_id':'fixture-candidate','manifest_sha256':'a'*64,'audit_receipt_sha256':'b'*64}
 full=put(root/'packages/full.zip',b'full archive receipt fixture');small=root/'packages/small.zip'
 report=put(runtime/'reports/final.md',b'# final fixture\n')
 report_member=b'# final report\n';smallmanifest={'files':[{'path':'reports/FINAL_SCIENTIFIC_REPORT.md','category':'reports_tables_figures','bytes':len(report_member),'sha256':digest(report_member)}]}
 with zipfile.ZipFile(small,'w',compression=zipfile.ZIP_DEFLATED) as z:
  z.writestr('reports/FINAL_SCIENTIFIC_REPORT.md',report_member)
  z.writestr('small_delivery_manifest.json',json.dumps(smallmanifest))
 def archive(path):
  st=path.stat();h=pf.file_sha(path)
  rec={'path':str(path),'bytes':st.st_size,'sha256':h,'mtime_ns':st.st_mtime_ns,'zip_crc_passed':True,'report_review_proof':proof}
  put(str(path)+'.receipt.json',json.dumps({k:rec[k] for k in ('path','bytes','sha256','mtime_ns','zip_crc_passed','report_review_proof')} ).encode())
  return rec
 fullrec=archive(full);smallrec=archive(small)
 outcomes={e:{'successful':n} for e,n in {'3':69,'4':1773,'5':960,'6':21}.items()}
 terminal={'total_tasks':6270,'scientific_counts':{'3':69,'4':1773,'5':960,'6':21},'plan_file_sha256':tasksha,'plan_sha256':'c'*64,'outcomes':outcomes,'registry_observed_utc':'2026-10-28T00:00:00Z'}
 ev={'e1_ledger':{'rows':765,'successful':674,'failed':81,'unsupported':10},'e2':{'primary_evaluated':108,'primary_planned':150,'unavailable':42,'classical_evaluated':120,'classical_planned':120,'low_precision':210},'e1_recovery_counts':{'successful_test_evaluation':24,'failed':10,'user_stopped':2,'not_attempted_user_stopped':55}}
 marker={'status':'delivery_pending_on_laptop','project_complete':False,'laptop_copy_verified':False,'report_review':proof,'terminal_registry':terminal,'runtime_source_freeze':{'freeze_sha256':digest(freeze_b),'source_files_verified':1},'full_archive':fullrec,'small_delivery_zip':smallrec,'final_report':{'path':str(report),'bytes':report.stat().st_size,'sha256':pf.file_sha(report)},'frozen_evidence':ev}
 put(runtime/'EC2_COMPLETE_DELIVERY_PENDING.json',json.dumps(marker).encode())
 put(runtime/'finalizer_state.json',json.dumps({'status':'delivery_pending_on_laptop','report_review_proof':proof,'full_archive':{'sha256':fullrec['sha256']}}).encode())
 return root,runtime,repo

class FinalGithubPublisherTests(unittest.TestCase):
 def test_incomplete_gate_never_touches_git_or_export(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[]; lock=pathlib.Path(d)/'lock'
   def gate(): calls.append('gate'); raise Waiting('not terminal')
   r=once(gate,lambda x:calls.append('git'),lambda x:calls.append('export'),lock)
   self.assertEqual(r['status'],'waiting');self.assertEqual(calls,['gate']);self.assertFalse(r['git_touched'])
 def test_verified_publication_is_idempotent(self):
  with tempfile.TemporaryDirectory() as d:
   calls=[];lock=pathlib.Path(d)/'lock';x={'ready':True,'fingerprint':'f'*64}
   r=once(lambda:x,lambda y:calls.append('verified_remote_refs') or {'verified_receipt':'receipt.json'},lambda y:calls.append('publish'),lock)
   self.assertEqual(r['status'],'already_published');self.assertEqual(calls,['verified_remote_refs']);self.assertEqual(r['verified_receipt'],'receipt.json')
 def test_actual_run_waits_incomplete_without_git(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);runtime=root/'runtime';repo=root/'repo';runtime.mkdir();repo.mkdir()
   with mock.patch.object(pf,'_already',side_effect=AssertionError('Git must not be reached')),mock.patch.object(pf,'publish',side_effect=AssertionError('publish must not be reached')):
    result=pf.run_once(root,runtime,repo)
   self.assertEqual(result['status'],'waiting');self.assertFalse(result['git_touched'])
 def test_actual_run_returns_verified_receipt_without_new_commit(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d);x={'ready':True,'fingerprint':'d'*64}
   with mock.patch.object(pf,'gate',return_value=x),mock.patch.object(pf,'_already',return_value={'verified_receipt':'receipt.json'}),mock.patch.object(pf,'publish',side_effect=AssertionError('idempotent path must not publish')):
    result=pf.run_once(root,runtime,repo)
   self.assertEqual(result['status'],'already_published');self.assertEqual(result['verified_receipt'],'receipt.json')
 def test_missing_finalizer_marker_is_waiting(self):
  from publish_final import gate
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'runtime').mkdir()
   with self.assertRaises(Waiting):gate(p,p/'runtime',p/'repo',lambda _:0)
 def test_realistic_finalizer_gate_binds_archives_and_sources(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d);x=pf.gate(root,runtime,repo,lambda _:0)
   self.assertTrue(x['ready']);self.assertEqual(x['terminal']['total_tasks'],6270)
   self.assertEqual(x['portable_test_file_count'],1);self.assertEqual(len(x['portable_sources']),1)
   self.assertEqual(x['small']['sha256'],pf.file_sha(x['small']['path']))
 def test_exact_specialized_worker_path_is_detected(self):
  with tempfile.TemporaryDirectory() as d:
   runtime=pathlib.Path(d)/'runtime'; target=runtime/'source/parallel_rf/worker.py';target.parent.mkdir(parents=True);target.write_text('#')
   proc=pathlib.Path(d)/'proc'/'4321';proc.mkdir(parents=True);(proc/'cwd').symlink_to('/')
   (proc/'cmdline').write_bytes(b'python3\0'+str(target).encode()+b'\0')
   self.assertEqual(pf.workers(runtime,pathlib.Path(d)/'proc'),1)
 def test_final_docs_overwrite_stale_interim_counts(self):
  with tempfile.TemporaryDirectory() as d:
   repo=pathlib.Path(d);x={'terminal':{'registry_observed_utc':'2026-10-28T22:00:00Z','outcomes':{'3':{'successful':60,'scientific_failure':5,'unsupported':4},'4':{'successful':1700,'scientific_failure':50,'unavailable_dependency':23},'5':{'successful':900,'scientific_failure':40,'unavailable_dependency':20},'6':{'successful':15,'scientific_failure':6}}},'evidence':{'e1_ledger':{'rows':765,'successful':674,'failed':81,'unsupported':10},'e2':{'primary_evaluated':108,'primary_planned':150,'unavailable':42,'classical_evaluated':120,'classical_planned':120},'e1_recovery_counts':{'successful_test_evaluation':24,'failed':10,'user_stopped':2,'not_attempted_user_stopped':55}}}
   (repo/'README.md').write_text('INTERIM active workers pending')
   pf._write_final_progress(repo,x,'abc123')
   text=(repo/'README.md').read_text()
   self.assertNotIn('INTERIM active workers pending',text);self.assertIn('1700',text);self.assertIn('not marked complete',text)
 def test_owned_cron_removal_preserves_other_lines(self):
  completed=lambda stdout='',returncode=0: type('R',(),{'stdout':stdout,'returncode':returncode})()
  calls=[]
  def fake(args,**kwargs):
   calls.append((args,kwargs))
   if args==['crontab','-l'] and len(calls)==1:return completed('0 * * * * other-task\n*/5 * * * * run --publish # LAMOST_FINAL_GITHUB_PUBLISHER_20261028\n')
   if args==['crontab','-l']:return completed('0 * * * * other-task\n')
   return completed()
  with mock.patch.object(pf.subprocess,'run',side_effect=fake):
   self.assertEqual(pf.remove_owned_cron(),1)
  self.assertEqual(calls[1][1]['input'],'0 * * * * other-task\n')
 def test_public_csv_privacy_fields_are_rejected_without_changing_scientific_headers(self):
  pf.public_content_check('table.csv',b'method,balanced_accuracy,attempt_id\nRF,0.81,abc\n')
  with self.assertRaises(Invalid):pf.public_content_check('table.csv',b'method,pid,balanced_accuracy\nRF,123,0.81\n')
 def test_archive_receipt_mtime_binding_is_enforced(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d);marker=json.loads((runtime/'EC2_COMPLETE_DELIVERY_PENDING.json').read_text());receipt=pathlib.Path(marker['full_archive']['path']+'.receipt.json');obj=json.loads(receipt.read_text());obj['mtime_ns']+=1;receipt.write_text(json.dumps(obj))
   with self.assertRaises(Invalid):pf.gate(root,runtime,repo,lambda _:0)
 def test_specialized_worker_blocks_final_gate(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d)
   with self.assertRaises(Waiting):pf.gate(root,runtime,repo,lambda _:1)
 def test_invalid_input_latches_until_gate_input_changes(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d)
   with mock.patch.object(pf,'gate',side_effect=Invalid('fixture invalid')):
    first=pf.run_once(root,runtime,repo);second=pf.run_once(root,runtime,repo)
   self.assertEqual(first['status'],'blocked_latched');self.assertEqual(second['status'],'blocked_latched')
   self.assertIn('latched',second['reason'])
 def test_transient_git_failure_backs_off_across_invocations(self):
  with tempfile.TemporaryDirectory() as d:
   root,runtime,repo=make_gate_fixture(d);x={'ready':True,'fingerprint':'f'*64}
   with mock.patch.object(pf,'gate',return_value=x),mock.patch.object(pf,'_already',side_effect=TransientGit('network')):
    first=pf.run_once(root,runtime,repo);second=pf.run_once(root,runtime,repo)
   self.assertEqual(first['status'],'waiting_backoff');self.assertEqual(second['status'],'waiting_backoff')
   self.assertGreaterEqual(second['retry_after_seconds'],1)
if __name__=='__main__':unittest.main()
