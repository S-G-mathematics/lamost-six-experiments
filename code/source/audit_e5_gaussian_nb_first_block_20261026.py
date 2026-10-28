from pathlib import Path
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import json,sys,csv,hashlib,datetime,statistics
r=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025');sys.path.insert(0,str(r/'source'))
import audit_artifacts
raw=(r/'registry.json').read_bytes();reg=json.loads(raw);ts=reg['tasks'];bykey={t['key']:t for t in ts}
cases=sorted([t for t in ts if t.get('experiment')==5 and t.get('method')=='gaussian_nb' and t.get('scientific_case')],key=lambda t:t['key'])
assert len(cases)==30 and all(t['status']=='validated_terminal' and t.get('outcome')=='successful' for t in cases)
available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
assert available>=16*1024**3
aud=audit_artifacts.Auditor(r);validset={t['key'] for t in ts if t['status']=='validated_terminal' and t.get('outcome')=='successful'}
rows=[]
for t in cases:
 aud.evaluation_audit(t,bykey,validset,alias=t['kind']=='alias')
 p=r/'artifacts'/t['key']/'evaluation.json';d=json.loads(p.read_text())
 rows.append({'key':t['key'],'rep':t['rep'],'condition':t['condition'],'mechanism':t.get('mechanism'),'rate':t.get('rate'),'balanced_accuracy':d['balanced_accuracy'],'coverage':d['coverage'],'set_size':d['set_size'],'calibration_n':d['calibration_n'],'test_n':d.get('test_n',500000),'evaluation_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
assert not aud.issues,aud.issues
clean={x['rep']:x for x in rows if x['condition']=='clean'};assert len(clean)==3
paired=[]
for x in rows:
 if x['condition']=='clean':continue
 c=clean[x['rep']]
 paired.append({**x,'clean_key':c['key'],'clean_evaluation_sha256':c['evaluation_sha256'],**{f'delta_{m}':x[m]-c[m] for m in ('balanced_accuracy','coverage','set_size')}})
assert len(paired)==27
summary=[]
for cond in sorted({x['condition'] for x in paired}):
 group=[x for x in paired if x['condition']==cond];assert {x['rep'] for x in group}=={1,2,3}
 summary.append({'condition':cond,'matched_repetitions':len(group),**{f'{m}_mean':statistics.mean(x[m] for x in group) for m in ('balanced_accuracy','coverage','set_size','delta_balanced_accuracy','delta_coverage','delta_set_size')},**{f'{m}_sample_sd':statistics.stdev(x[m] for x in group) for m in ('balanced_accuracy','coverage','set_size','delta_balanced_accuracy','delta_coverage','delta_set_size')}})
outputs={}
for name,data in [('E5_GAUSSIAN_NB_FIRST_BLOCK_REPETITIONS_20261026.csv',rows),('E5_GAUSSIAN_NB_FIRST_BLOCK_PAIRED_20261026.csv',paired),('E5_GAUSSIAN_NB_FIRST_BLOCK_SUMMARY_20261026.csv',summary)]:
 dst=r/'reports'/name;assert not dst.exists()
 with dst.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
 outputs[name]={'bytes':dst.stat().st_size,'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),'rows':len(data)}
receipt={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'First complete E5 Gaussian Naive Bayes block only, 30 successful outcomes:3 clean and27 corrupted. Saved-outcome independent metric/identity audit and matched descriptive differences; no model inference/fitting; not E5 completion.','registry_sha256':hashlib.sha256(raw).hexdigest(),'auditor_source_sha256':hashlib.sha256((r/'source/audit_artifacts.py').read_bytes()).hexdigest(),'audit_issue_count':len(aud.issues),'diagnostic_limitations':aud.diagnostics,'available_ram_preflight_bytes':available,'cases':rows,'paired_summary':summary,'outputs':outputs,'limitations':['Only one method block of960 E5 planned outcomes.','Descriptive paired means and sample standard deviations across3repetitions; no bootstrap or significance claims.','Saved calibration metadata is checked; unsaved calibration score quantile and fitted-pipeline internals are not independently reconstructed here.']}
p=r/'reports/engineering_audits/E5_GAUSSIAN_NB_FIRST_BLOCK_AUDIT_20261026.json';assert not p.exists();p.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'issue_count':len(aud.issues),'clean_mean':{m:statistics.mean(x[m] for x in clean.values()) for m in ('balanced_accuracy','coverage','set_size')},'paired_summary':summary,'csv_outputs':outputs}))
