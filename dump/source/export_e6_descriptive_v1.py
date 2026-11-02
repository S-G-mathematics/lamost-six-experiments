import argparse,csv,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import zoneinfo
from cold_report_access import fit_reference
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rt=a.runtime.resolve();out=a.output.resolve();td=rt/'source/e6_descriptive_templates'
def j(x):return json.loads(x.read_text(encoding='utf-8'))
def h(x):
 z=hashlib.sha256()
 with x.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):z.update(b)
 return z.hexdigest()
def task_artifact_dir(runtime,task):
 # Registry artifact_dir is display/provenance metadata. Archived native artifacts
 # always live under the explicit runtime root at artifacts/<task key>.
 rt=Path(runtime).resolve()
 key=task.get('key')
 if not isinstance(key,str) or not key or any(part in ('','.','..') for part in key.split('/')):
  raise ValueError('Invalid artifact task key')
 root=(rt/'artifacts').resolve()
 target=(root/key).resolve()
 try: target.relative_to(root)
 except ValueError: raise ValueError('Task key escapes runtime artifact root')
 return target

def rows(x):
 with x.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))
def put(x,rs):
 with x.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
r=j(rt/'registry.json');alltasks=r['tasks'];ts=[t for t in alltasks if t.get('experiment')==6 and t.get('scientific_case')];by={t['key']:t for t in ts};fit_tasks={t['key']:t for t in alltasks if t.get('kind')=='fit'}
if len(ts)!=21 or len(by)!=21:raise SystemExit('E6 registry must contain 21 unique scientific cells')
led=rows(td/'cell_ledger.csv');av=rows(td/'availability.csv');members=rows(td/'member_per_repetition.csv')
if (len(led),len(av),len(members))!=(21,21,15):raise SystemExit('Reviewed template row counts changed')
evals={}
for k,t in by.items():
 ep=task_artifact_dir(rt,t)/'evaluation.json'
 if t.get('outcome')=='successful' and ep.exists():
  e=j(ep)
  if e.get('task_key')!=k:raise SystemExit('evaluation key mismatch '+k)
  evals[k]=e
if len(evals)!=12:raise SystemExit('Expected 12 saved evaluation JSONs')
fig_expected={'E6_balanced_accuracy_member_ensemble.png':'b4ce92a014a39b04feac8dff49fa1b45a2e5e495a7f4c38f925271905caf7727','E6_coverage_member_ensemble.png':'e3f16d5a5b32eb2a17c017a6cac683630af9cd19822460363ada5607d1dea005','E6_set_size_member_ensemble.png':'16647f069a418fa9c297b67c35a2db675a4d61950fcc5783656bcc9a62329850'}
for name,digest in fig_expected.items():
 f=rt/'reports'/name
 if not f.exists() or h(f)!=digest: raise SystemExit('Reviewed E6 figure hash mismatch: '+name)
qa_path=rt/'reports/engineering_audits/E6_FIGURE_VISUAL_QA_PASSED_20261025.json'
if not qa_path.exists() or h(qa_path)!='def9a7e57f2d738a0d2affe338a43a11e4fc3b4cda73c6ab4d1dc56b3e26d05a': raise SystemExit('Visual QA receipt mismatch')
for x in led:
 t=by[x['task_key']];e=evals.get(x['task_key'])
 for col,key in [('status','status'),('outcome','outcome'),('validation_state','validation_state')]:
  if col in x:x[col]=t.get(key,'') or ''
 for col,key in [('balanced_accuracy','balanced_accuracy'),('coverage','coverage'),('mean_set_size','set_size')]:
  if col in x:x[col]=e.get(key,'') if e else ''
 if 'evaluation_present' in x:x['evaluation_present']=str(bool(e))
for x in av:
 t=by.get(x.get('task_key'))
 if t:
  e=evals.get(t['key'])
  for col,val in [('E6_alias_outcome',t.get('outcome')),('evaluation_available',bool(e)),('reason',t.get('reason'))]:
   if col in x:x[col]=val or ''
for x in members:
 t=by.get(x['task_key'])
 if t:x.update(fit_reference(t,rt,fit_tasks,all_tasks={z['key']:z for z in alltasks if z.get('key')}))
 e=evals.get(x['task_key'])
 if not e: continue
 for col,key in [('balanced_accuracy','balanced_accuracy'),('coverage','coverage'),('mean_set_size','set_size'),('threshold','threshold'),('calibration_fallback_count','calibration_fallback_count'),('test_fallback_count','test_fallback_count')]:
  if col in x:x[col]=e.get(key,'')
 names=['A','F','G','K','M','GALAXY','QSO']
 for i,n in enumerate(names):
  c=e.get('per_class',{}).get(str(i),{})
  for col,key in [(f'n_{n}','n'),(f'recall_{n}','recall'),(f'coverage_{n}','coverage'),(f'set_size_{n}','set_size')]:
   if col in x:x[col]=c.get(key,'')
out.mkdir(parents=True,exist_ok=True)
put(out/'E6_FINAL_CELL_LEDGER_21.csv',led);put(out/'E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv',av);put(out/'E6_MEMBER_PER_REPETITION.csv',members)
base=(td/'report_base.md').read_text(encoding='utf-8')
add='''## Frozen conformal rule and classwise coverage\n\nThe frozen evaluation uses probability nonconformity 1 - p_true. The calibration threshold is the finite-sample order statistic at k = ceil((n + 1) × 0.90), selected as the kth smallest score by numpy.partition; if k exceeds n, threshold is infinity. With n=10,000, k=9,001. A test class is included when 1 - p_class <= threshold; no label is forcibly inserted. No threshold was changed after test evaluation. Overall coverage near 90% does not imply 90% coverage for every class. Across three saved repetitions, class A mean coverage was GMM 0.7856, copula 0.4973, ARF 0.5178, and Chow–Liu 0.6131 (n=3 each).\n\nThe planned tuning-best-member comparator was not selected or evaluated because required member availability prevented the E6 posterior phase; neither ensemble weight search nor tuning-best selection ran.\n\n## Data-only regeneration\n\nFrom the extraction root run: `cd <extraction-root>; /usr/bin/python3 runtime_20261025/source/export_e6_descriptive.py --runtime runtime_20261025 --project project --output runtime_20261025/reports`. The exporter reads registry records, reviewed provenance templates and saved evaluation JSONs only; it performs descriptive table and summary generation only, with no new fitting, posterior generation, or calibration/test inference.\n'''
qa='\n## Figure visual QA\n\nThe three published E6 figures passed root visual and semantic review at 2026-10-25T17:56:54Z. Receipt: `reports/engineering_audits/E6_FIGURE_VISUAL_QA_PASSED_20261025.json` (SHA-256 `def9a7e57f2d738a0d2affe338a43a11e4fc3b4cda73c6ab4d1dc56b3e26d05a`). The receipt binds the exact figure hashes recorded in E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json.\n'
base=base.replace('## Primary ensemble method and state',add+qa+'\n## Primary ensemble method and state')
(baseout:=out/'E6_FINAL_DESCRIPTIVE_REPORT.md').write_text(base,encoding='utf-8',newline='\n')
now=datetime.now(timezone.utc);rec={'experiment':6,'status':'E6 accounting/member descriptives complete; primary ensembles unavailable; not full project completion','publication_status':'reviewed_descriptive_primary_unavailable','observed_utc':now.strftime('%Y-%m-%dT%H:%M:%SZ'),'observed_asia_kolkata':now.astimezone(zoneinfo.ZoneInfo('Asia/Kolkata')).isoformat(),'registry_observed_utc':r.get('observed_utc'),'counts':{'planned':21,'terminal':21,'pipelines_available':15,'successful_member_references':12,'unavailable_KDE_member_references':3,'primary_ensembles':6,'primary_ensembles_unavailable':6,'primary_ensemble_attempts':0},'actions':{'fits':0,'model_loads':0,'posterior_generation':0,'calibration_or_test_inference':0,'bootstrap':0},'source_sha256':{str(x.relative_to(rt.parent)) if x.is_relative_to(rt.parent) else str(x):h(x) for x in [a.project/'benchmark/protocol_source.txt',rt/'manifests/E3_MANIFEST.json',rt/'manifests/E6_MANIFEST.json',rt/'manifests/freeze.json',rt/'manifests/plan_amendments.json',rt/'manifests/tasks.json',rt/'registry.json',rt/'source/ensemble.py',rt/'source/reporting.py',Path(__file__)] if x.exists()},'output_sha256':{x.name:h(x) for x in [baseout,out/'E6_FINAL_CELL_LEDGER_21.csv',out/'E6_ARTIFACT_AND_EVALUATION_AVAILABILITY.csv',out/'E6_MEMBER_PER_REPETITION.csv',out/'E6_balanced_accuracy_member_ensemble.png',out/'E6_coverage_member_ensemble.png',out/'E6_set_size_member_ensemble.png']},'figure_review':{'status':'passed','receipt':'reports/engineering_audits/E6_FIGURE_VISUAL_QA_PASSED_20261025.json','receipt_sha256':'def9a7e57f2d738a0d2affe338a43a11e4fc3b4cda73c6ab4d1dc56b3e26d05a','reviewed_live_figure_sha256':{'E6_balanced_accuracy_member_ensemble.png':'b4ce92a014a39b04feac8dff49fa1b45a2e5e495a7f4c38f925271905caf7727','E6_coverage_member_ensemble.png':'e3f16d5a5b32eb2a17c017a6cac683630af9cd19822460363ada5607d1dea005','E6_set_size_member_ensemble.png':'16647f069a418fa9c297b67c35a2db675a4d61950fcc5783656bcc9a62329850'}}}
(out/'E6_FINAL_DESCRIPTIVE_RECEIPT_20261025.json').write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps({'report':str(baseout),'sha256':h(baseout),'member_rows':len(members),'evaluation_jsons':len(evals)}))