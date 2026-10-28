import importlib.util,sys,tempfile,json,hashlib,shutil,csv
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]/'source'
ROOT=BASE.parent.parent
RT=ROOT/'runtime_20261025'
sys.path.insert(0,str(RT/'source'))
sys.path.insert(0,str(RT/'source'))
spec=importlib.util.spec_from_file_location('staged_finalizer',BASE/'finalize_project.py')
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def bytes_for(entry):return entry.source if isinstance(entry.source,bytes) else Path(entry.source).read_bytes()
def fixture():
 td=tempfile.TemporaryDirectory();root=Path(td.name);runtime=root/'runtime_20261025'
 for d in ['project','e1_wrapup_20261024','e1_recovery_20261024','e2_20261024','runtime_20261025']:
  (root/d).mkdir(parents=True,exist_ok=True)
 (root/'project/scientific.json').write_text(json.dumps({'dataset_hash':'abc','scientific_metric':0.75}))
 (root/'e1_wrapup_20261024/summary.json').write_text(json.dumps({'frozen_cells':765}))
 (root/'e1_recovery_20261024/cutoff.json').write_text(json.dumps({'stopped_early':True}))
 (root/'project/operations').mkdir()
 (root/'project/operations/process_receipt.json').write_text(json.dumps({'pid':999,'private_receipt':'no'}))
 mf=runtime/'manifests';mf.mkdir(parents=True)
 actual=RT/'manifests'
 for name in ['baseline_identity_boundary_audit.json','concurrency_user_authorization_20261025.json']+[p.name for p in actual.glob('freeze_before_*.json')]:
  shutil.copy2(actual/name,mf/name)
 inc=mf/'incidents';inc.mkdir()
 for name in ['e4_weight_schema_20261025.json','svm_native_margin_api_20261026.json']:
  shutil.copy2(actual/'incidents'/name,inc/name)
 for name,rel in [('controller_identity_hold.json','controller_identity_hold.json'),('dequeue_hold_resolved.json','serialization_validation_20261025/dequeue_hold_resolved.json')]:
  src=actual/'incidents'/rel
  (inc/name).write_bytes(src.read_bytes())
 (inc/'private_process_receipt.json').write_text(json.dumps({'worker_pid':1234,'process_receipt':'no'}))
 for d in ['source','tests','cache','artifacts','reports','review_audit','manifests/imported_selections']:
  (runtime/d).mkdir(parents=True,exist_ok=True)
 (runtime/'source/fixture.py').write_text('# source')
 (runtime/'registry.json').write_text(json.dumps({'tasks':[]}))
 (runtime/'master_index.json').write_text('{}')
 return td,root,runtime
def hashmap(root):
 out={}
 for p in root.rglob('*.json'):out[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
 return out
def test_collect_full_public_provenance_and_privacy():
 td,root,runtime=fixture()
 try:
  actual=RT/'reports/resource_failure_ledger.csv'
  with actual.open(newline='') as f:rawrows=list(csv.DictReader(f))
  reasons=[x['raw_reason'] for x in rawrows if 'pid' in x.get('raw_reason','').lower() or 'pgid' in x.get('raw_reason','').lower()]
  assert len(reasons)==2
  report=runtime/'reports/resource_failure_ledger.csv'
  with report.open('w',newline='') as f:
   w=csv.writer(f,lineterminator='\n');w.writerow(['task_key','raw_reason','metric']);w.writerow(['e3/rep_2/fit/arf',reasons[0],'1.25']);w.writerow(['e3/rep_3/fit/arf',reasons[1],'2.50'])
  # Exercise JSON-string path with one actual saved reason; temporary fixture is deleted after this test.
  j=runtime/'reports/attempt_reason.json';j.write_text(json.dumps({'raw_reason':reasons[0],'balanced_accuracy':0.75}))
  reg=(runtime/'registry.json').read_text()
  entries=m.collect_full(root,runtime,b'# readme',reg,expected_source_sha256=hashmap(root))
  members={e.member:e for e in entries}
  expected={
   'project/scientific.json','e1_wrapup_20261024/summary.json','e1_recovery_20261024/cutoff.json',
   'runtime_20261025/manifests/baseline_identity_boundary_audit.json',
   'runtime_20261025/manifests/concurrency_user_authorization_20261025.json',
   'runtime_20261025/manifests/incidents/e4_weight_schema_20261025_summary.json',
   'runtime_20261025/manifests/incidents/svm_native_margin_api_20261026_summary.json',
   'runtime_20261025/manifests/public_scientific_provenance_manifest.json'}
  expected|={'runtime_20261025/manifests/'+p.name for p in (runtime/'manifests').glob('freeze_before_*.json')}
  assert expected<=set(members),expected-set(members)
  assert not any('process_receipt' in k or 'controller_identity_hold' in k or 'dequeue_hold_resolved' in k for k in members)
  project=json.loads(bytes_for(members['project/scientific.json']))
  assert project=={'dataset_hash':'abc','scientific_metric':0.75}
  e4=json.loads(bytes_for(members['runtime_20261025/manifests/incidents/e4_weight_schema_20261025_summary.json']))
  assert e4['source_manifest_sha256']==hashlib.sha256((runtime/'manifests/incidents/e4_weight_schema_20261025.json').read_bytes()).hexdigest()
  assert e4['scientific_trial_history_row_count']==262 and 'raw_private_evidence_retained_on_EC2' not in json.dumps(e4)
  svm=json.loads(bytes_for(members['runtime_20261025/manifests/incidents/svm_native_margin_api_20261026_summary.json']))
  assert svm['affected_invalid_fit_tasks']==42 and svm['E1_orE2fits_started']==0 and 'pid' not in json.dumps(svm).lower()
  inventory=json.loads(bytes_for(members['runtime_20261025/manifests/public_scientific_provenance_manifest.json']))
  assert len(inventory['included'])==11 and 'process receipts' in inventory['retained_only_omissions']['scope']
  assert all({'source_sha256','archive_sha256','archive_member'}<=set(x) for x in inventory['included'])
  assert all(x['archive_sha256'] for x in inventory['included'])
  full_csv=bytes_for(members['runtime_20261025/reports/resource_failure_ledger.csv'])
  side=json.loads(bytes_for(members['runtime_20261025/reports/resource_failure_ledger.csv.curation.json']))
  parsed=list(csv.DictReader(full_csv.decode().splitlines()))
  assert [x['task_key'] for x in parsed]==['e3/rep_2/fit/arf','e3/rep_3/fit/arf']
  assert [x['metric'] for x in parsed]==['1.25','2.50']
  assert len(side['changed_cells'])==2 and side['source_sha256']==hashlib.sha256(report.read_bytes()).hexdigest()
  assert side['view_sha256']==hashlib.sha256(full_csv).hexdigest()
  assert 'pid' not in full_csv.decode().lower() and 'pgid' not in full_csv.decode().lower()
  json_view=bytes_for(members['runtime_20261025/reports/attempt_reason.json']).decode()
  assert 'balanced_accuracy' in json_view and '"pid"' not in json_view and '"pgid"' not in json_view
  # Compact collector uses the same sanitizer and emits the matching provenance sidecar.
  old_small=m.small_report_files;m.small_report_files=lambda _: [report]
  try:
   small_entries=m._small_entries(root,runtime,None,None,'/ec2/packages/compact.zip',expected_source_sha256=hashmap(root))
  finally:m.small_report_files=old_small
  sm={e.member:e for e in small_entries}
  assert 'reports/resource_failure_ledger.csv' in sm and 'reports/resource_failure_ledger.csv.curation.json' in sm
  assert bytes_for(sm['reports/resource_failure_ledger.csv'])==full_csv
  # Compact generation is bound to the reviewed source hash; late CSV/JSON mutation rejects before returning entries.
  csv_hash=hashlib.sha256(report.read_bytes()).hexdigest();report.write_text(report.read_text()+'\n')
  with __import__('unittest').TestCase().assertRaises(m.EvidenceError):
   m._small_entries(root,runtime,None,None,'/ec2/packages/compact.zip',expected_source_sha256={str(report.resolve()):csv_hash})
  json_hash=hashlib.sha256(j.read_bytes()).hexdigest();j.write_text(json.dumps({'raw_reason':'changed after review'}))
  old_small=m.small_report_files;m.small_report_files=lambda _: [j]
  try:
   with __import__('unittest').TestCase().assertRaises(m.EvidenceError):
    m._small_entries(root,runtime,None,None,'/ec2/packages/compact.zip',expected_source_sha256={str(j.resolve()):json_hash})
  finally:m.small_report_files=old_small
  # Unchanged CSVs are copied byte-for-byte and have no derived sidecar.
  plain=root/'plain.csv';plain.write_bytes(b'a,b\n1,2\n')
  unchanged=m._report_csv_archive_entries(plain,'reports/plain.csv','fixture',root,{str(plain.resolve()):hashlib.sha256(plain.read_bytes()).hexdigest()})
  assert len(unchanged)==1 and bytes_for(unchanged[0])==plain.read_bytes()
  with __import__('unittest').TestCase().assertRaises(m.EvidenceError):
   m._report_csv_archive_entries(plain,'reports/plain.csv','fixture',root,{str(plain.resolve()):'0'*64})
 finally:td.cleanup()
def test_collect_full_tree_expected_hash_mismatch_fails_closed():
 td,root,runtime=fixture()
 try:
  expected=hashmap(root);expected[str((root/'project/scientific.json').resolve())]='0'*64
  with __import__('unittest').TestCase().assertRaises(m.EvidenceError):
   m.collect_full(root,runtime,b'# readme',(runtime/'registry.json').read_text(),expected_source_sha256=expected)
 finally:td.cleanup()
if __name__=='__main__':
 test_collect_full_public_provenance_and_privacy();test_collect_full_tree_expected_hash_mismatch_fails_closed();print('2 collect_full archive fixtures passed')
