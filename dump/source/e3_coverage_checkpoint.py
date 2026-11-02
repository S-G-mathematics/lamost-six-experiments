#!/usr/bin/env python3
"""Descriptive E3 checkpoint. No fitting, prediction, selection, or bootstrap."""
import csv,datetime,hashlib,io,json,pathlib,statistics,collections,os
R=pathlib.Path(__file__).resolve().parents[1];D=R/'reports'
labels=['A','F','G','K','M','GALAXY','QSO']
names=['planned_case_ledger.csv','per_repetition_metrics.csv','per_class_metrics.csv']
raw={n:(D/n).read_bytes() for n in names}
rows={n:list(csv.DictReader(io.StringIO(v.decode()))) for n,v in raw.items()}
plan=[r for r in rows[names[0]] if r['experiment']=='3']
perf={r['key']:r for r in rows[names[1]] if r['experiment']=='3'}
classes=collections.defaultdict(dict)
for r in rows[names[2]]:
 if r['experiment']=='3':
  k=int(r['class_id'])
  if k in classes[r['key']]:raise ValueError('duplicate class')
  classes[r['key']][k]=r
groups=collections.defaultdict(list)
for r in plan:groups[(r['route'],r.get('generator',''),r['method'])].append(r)
if len(plan)!=69 or len(groups)!=23:raise ValueError('wrong E3 plan shape')
summary=[];class_summary=[]
for (route,gen,method),planned in sorted(groups.items()):
 successful=[perf[r['key']] for r in planned if r['key'] in perf]
 if any(set(classes[r['key']])!=set(range(7)) for r in successful):raise ValueError('incomplete class diagnostics')
 cmeans=[]
 for c,label in enumerate(labels):
  vals=[float(classes[r['key']][c]['coverage']) for r in successful]
  n=[int(classes[r['key']][c]['n']) for r in successful]
  z={'route':route,'generator':gen,'method':method,'label':label,'planned_repetitions':len(planned),'successful_repetitions':len(vals),'test_n_each':n[0] if n else '', 'coverage_mean':statistics.mean(vals) if vals else '', 'coverage_sample_sd':statistics.stdev(vals) if len(vals)>1 else '', 'coverage_individual_repetitions':json.dumps({r['rep']:float(classes[r['key']][c]['coverage']) for r in successful},sort_keys=True)}
  if len(set(n))>1:raise ValueError('test class counts differ')
  class_summary.append(z)
  if vals:cmeans.append((z['coverage_mean'],label))
 for r in successful:
  cs=classes[r['key']]
  weighted=sum(int(x['n'])*float(x['coverage']) for x in cs.values())/sum(int(x['n']) for x in cs.values())
  if abs(weighted-float(r['coverage']))>1e-12:raise ValueError('marginal coverage mismatch')
 states=collections.Counter(r['outcome'] or r['status'] for r in planned)
 worst=min(cmeans) if cmeans else ('','')
 summary.append({'route':route,'generator':gen,'method':method,'planned_repetitions':len(planned),'successful_repetitions':len(successful),'outcomes':json.dumps(states,sort_keys=True),'balanced_accuracy_mean':statistics.mean(float(r['balanced_accuracy']) for r in successful) if successful else '', 'overall_coverage_mean':statistics.mean(float(r['coverage']) for r in successful) if successful else '', 'mean_set_size':statistics.mean(float(r['set_size']) for r in successful) if successful else '', 'minimum_class_mean_coverage':worst[0],'minimum_class_label':worst[1],'matched_repetitions':','.join(sorted(r['rep'] for r in successful))})
for n in names:
 if hashlib.sha256((D/n).read_bytes()).digest()!=hashlib.sha256(raw[n]).digest():raise RuntimeError('input changed during checkpoint')
now=datetime.datetime.now(datetime.timezone.utc);stamp=now.strftime('%Y%m%dT%H%M%SZ');prefix='E3_CONFORMAL_COVERAGE_CHECKPOINT_'+stamp
outputs=[]
for suffix,data in [('groups.csv',summary),('classes.csv',class_summary)]:
 p=D/(prefix+'_'+suffix)
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
 outputs.append(p)
lines=['# E3 conformal coverage checkpoint - INTERIM','', 'Observed UTC: '+now.isoformat(),'', 'This is a descriptive checkpoint of all 23 planned route/generator/learner groups, not a final E3 report or a model-selection analysis. E3 has 69 planned repetition outcomes; '+str(len(perf))+' successful outcomes currently have class diagnostics. The remaining outcomes retain their actual state; unavailable or failed evaluations have no imputed scores. No new fitting or inference was performed.','', 'The nominal conformal target is 90%. Overall coverage is population weighted across the fixed test cohort. It does not imply 90% coverage separately within each class. The table reports the smallest class mean coverage solely as a diagnostic; the companion class CSV reports every class and every available repetition. Means are descriptive, conditional on success. Sample SDs are repetition variability, not confidence intervals. No thresholds were adjusted.','', '| Route | Generator | Learner/method | Successful/planned repetitions | Overall coverage | Mean set size | Lowest class mean coverage |','|---|---|---|---:|---:|---:|---|']
for r in summary:
 def fmt(x):return f'{x:.4f}' if isinstance(x,(int,float)) else 'unavailable'
 lines.append('| '+ ' | '.join([r['route'],r['generator'] or 'shared real',r['method'],str(r['successful_repetitions'])+'/'+str(r['planned_repetitions']),fmt(r['overall_coverage_mean']),fmt(r['mean_set_size']),r['minimum_class_label']+' '+fmt(r['minimum_class_mean_coverage'])])+' |')
lines+=['','Source tables were SHA-256 checked unchanged during the calculation. Their exact hashes and output hashes are in the companion JSON receipt. Earlier E1/E2 test results were already observed. These are later-experiment results under the recorded E3 policy; they do not repair frozen E1 failures or fill unavailable E2 primary cells.']
md=D/(prefix+'.md');md.write_text('\n'.join(lines)+'\n');outputs.append(md)
receipt={'observed_utc':now.isoformat(),'scope':'interim E3 all planned groups; no new fits/predictions','planned_cases':len(plan),'planned_groups':len(groups),'successful_evaluations':len(perf),'source_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in raw.items()},'analysis_source_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'output_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in outputs},'bootstrap':False,'input_tables_unchanged_during_calculation':True}
(D/(prefix+'.json')).write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps(receipt))
