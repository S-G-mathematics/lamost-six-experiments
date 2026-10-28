import os,resource
os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
from pathlib import Path
import csv,json,hashlib,math,sqlite3,collections,statistics,datetime
R=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025');D=R/'reports/e5_completed_generator_routes_20261027'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(n):
 with (D/n).open() as f:return list(csv.DictReader(f))
issues=[];counts=collections.Counter()
def ck(ok,n):
 counts[n]+=1
 if not ok:issues.append(n)
def num(v):return float(v)
def eq(a,b):return math.isclose(float(a),float(b),rel_tol=0,abs_tol=1e-11)
m=json.loads((D/'manifest.json').read_text())
ck(sha(D/'manifest.json')=='c5d36a2249583c0e24b7ded0d01257b50a4936fead0938dec7f8b27d039cfe30','manifest_pin')
avail=rows('planned_case_availability.csv');ck(len(avail)==270 and len({r['task_key'] for r in avail})==270,'270_unique_planned')
db=sqlite3.connect('file:'+str(R/'registry.sqlite')+'?mode=ro',uri=True);db.execute('BEGIN');tasks={};metrics={};metric_shas={}
for r in avail:
 t=json.loads(db.execute('select record from tasks where key=?',(r['task_key'],)).fetchone()[0]);tasks[t['key']]=t
 ck(t['status']=='validated_terminal' and t['outcome']=='successful' and t['validation_state']=='validated','successful_validated_actual')
 p=R/r['evaluation_json'];v=json.loads((p.parent/'validation.json').read_text())
 ck(sha(p)==v['files']['evaluation.json'],'evaluation_validation_hash')
 e=json.loads(p.read_text());metrics[t['key']]=e;metric_shas[t['key']]=sha(p)
 ck(e['test_n']==500000 and e['calibration_n']==10000,'eval_cohort_counts')
 cm=e['confusion_matrix'];pc=e['per_class'];ck(len(cm)==7 and all(len(z)==7 for z in cm),'cm_shape')
 total=sum(sum(row) for row in cm);ck(total==500000,'cm_total')
 for k in range(7):
  support=sum(cm[k]);ck(support==int(pc[str(k)]['n']),'cm_support')
  ck(eq(cm[k][k]/support,pc[str(k)]['recall']),'cm_recall')
 ck(eq(sum(pc[str(k)]['recall'] for k in range(7))/7,e['balanced_accuracy']),'balanced_accuracy_from_cm')
 for metric in ['coverage','set_size']:ck(eq(sum(pc[str(k)]['n']*pc[str(k)][metric] for k in range(7))/total,e[metric]),'weighted_class_'+metric)
db.close()
pair=rows('matched_route_comparisons_by_repetition.csv')
ck(len(pair)==180,'180_route_rows')
for row in pair:
 dk,sk=row['direct_task_key'],row['synthetic_task_key'];dc,sc=row['direct_clean_task_key'],row['synthetic_clean_task_key']
 d,s,cd,cs=(metrics[x] for x in [dk,sk,dc,sc])
 td,ts=tasks[dk],tasks[sk]
 ck(td['rep']==ts['rep']==int(row['rep']) and td['method']==ts['generator']==row['generator_family'] and ts['method']==row['downstream_learner'],'route_identity')
 for met in ['balanced_accuracy','coverage','set_size']:
  expected={'direct_'+met:d[met],'synthetic_'+met:s[met],'synthetic_minus_direct_'+met:s[met]-d[met]}
  if row['mechanism']!='clean':
   expected.update({'direct_corruption_change_'+met:d[met]-cd[met],'synthetic_corruption_change_'+met:s[met]-cs[met],'synthetic_minus_direct_change_'+met:(s[met]-cs[met])-(d[met]-cd[met])})
  for col,w in expected.items():ck(eq(row[col],w),'overall_metric_or_paired_difference')
def verify_summaries(raw,summary,keycols,name):
 groups=collections.defaultdict(list)
 for r in raw:groups[tuple(r[k] for k in keycols)].append(r)
 ck(len(groups)==len(summary),name+'_group_count')
 seen=set()
 for r in summary:
  key=tuple(r[k] for k in keycols);seen.add(key);rr=groups[key]
  ck(len(rr)==3 and int(r['planned_repetitions'])==int(r['available_repetitions'])==3,name+'_n3')
  for c in r:
   if c.endswith('_mean'):
    col=c[:-5]
    if col in rr[0]:
     vals=[float(x[col]) for x in rr];ck(eq(r[c],statistics.mean(vals)),name+'_mean')
     ck(eq(r[col+'_sample_sd'],statistics.stdev(vals)),name+'_sample_sd')
     ck(int(r[col+'_n'])==3,name+'_count')
 ck(set(groups)==seen,name+'_identities')
keycols=['generator_family','downstream_learner','mechanism','rate']
corrupt=[r for r in pair if r['mechanism']!='clean'];ck(len(corrupt)==162,'162_corrupt_pairs')
summary=rows('matched_route_degradation_summary.csv');ck(len(summary)==54,'54_summaries')
verify_summaries(corrupt,summary,keycols,'route_summary')
pcrows=rows('per_class_route_comparisons_by_repetition.csv');ck(len(pcrows)==1134,'1134_class_pairs')
pairmap={(r['rep'],r['generator_family'],r['downstream_learner'],r['mechanism'],r['rate']):r for r in corrupt}
for r in pcrows:
 base=pairmap[(r['rep'],r['generator_family'],r['downstream_learner'],r['mechanism'],r['rate'])]
 k=str(int(r['class_id']))
 d,s,cd,cs=(metrics[base[x]]['per_class'][k] for x in ['direct_task_key','synthetic_task_key','direct_clean_task_key','synthetic_clean_task_key'])
 ck(r['class_label']==['A','F','G','K','M','GALAXY','QSO'][int(k)],'class_label_order')
 for met in ['recall','coverage','set_size']:
  expected={'direct_corrupted_'+met:d[met],'synthetic_corrupted_'+met:s[met],'synthetic_minus_direct_'+met:s[met]-d[met],'direct_corruption_change_'+met:d[met]-cd[met],'synthetic_corruption_change_'+met:s[met]-cs[met],'synthetic_minus_direct_change_'+met:(s[met]-cs[met])-(d[met]-cd[met])}
  for col,w in expected.items():ck(eq(r[col],w),'class_metric_or_paired_difference')
pcs=rows('per_class_route_degradation_summary.csv');ck(len(pcs)==378,'378_class_summaries')
verify_summaries(pcrows,pcs,keycols+['class_id','class_label'],'class_summary')
ph=rows('evaluation_phase_costs.csv');ck(len(ph)==486,'486_phase_receipts')
pg=collections.defaultdict(list)
for r in ph:
 p=R/r['phase_evidence_path'];ck(sha(p)==r['phase_evidence_sha256'],'phase_receipt_sha')
 v=json.loads(p.read_text());ck(v['exit_code']==0 and not v['reason'] and eq(v['seconds'],r['phase_seconds']) and int(v['peak_tree_rss_kib'])==int(r['peak_tree_rss_kib']),'phase_values')
 ck(v['phase']=={'calibration':'calibrate','test_inference':'evaluate'}[r['phase']],'phase_identity')
 pg[(r['route'],r['phase'])].append(float(r['phase_seconds']))
for r in rows('evaluation_phase_cost_summary.csv'):
 vals=pg[(r['route'],r['phase'])]
 for c,v in [('sum_successful_phase_seconds',sum(vals)),('mean_phase_seconds',statistics.mean(vals)),('median_phase_seconds',statistics.median(vals)),('sample_sd_phase_seconds',statistics.stdev(vals)),('min_phase_seconds',min(vals)),('max_phase_seconds',max(vals))]:ck(eq(r[c],v),'phase_summary_'+c)
 ck(int(r['successful_phase_receipts'])==len(vals) and int(r['missing_or_failed_phase_receipts'])==0,'phase_summary_denominator')
costs=rows('dependency_cost_ledger.csv');ck(len(costs)==693 and len({r['task_key'] for r in costs})==693,'unique_dependency_cost_keys')
md=(D/'REPORT.md').read_text();ck(md.isascii() and '?' not in md,'ascii_report')
width=None
for l in md.splitlines():
 if l.startswith('|'):
  n=len(l.split('|'))-2
  if width is None:width=n
  ck(n==width,'markdown_columns')
 else:width=None
ck('exclude pre-admission queue waiting' in md and 'Global calibration replay validation' in md,'cost_and_validation_caveats')
ck(sha(D/'manifest.json')=='c5d36a2249583c0e24b7ded0d01257b50a4936fead0938dec7f8b27d039cfe30','manifest_unchanged')
out={'schema_version':'lamost-e5-route-root-table-review/1','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':not issues,'issues':issues,'checks':dict(counts),'input_manifest_sha256':sha(D/'manifest.json'),'evaluation_json_hashes':metric_shas,'outputs_sha256':{p.name:sha(p) for p in D.iterdir() if p.is_file() and p.name not in ['ROOT_TABLE_REVIEW.json','ROOT_FIGURE_REVIEW.json']},'scope':'270aggregateJSON/CM/classreconstruction;180routepairs(162corrupt);1134classpairs;54/378summaries;486actualsupervisedphasecosts;693unique dependency keys. No models/prediction arrays, qreplay orscienceexecution.','global_calibration_replay_complete':False,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}
dest=D/'ROOT_TABLE_REVIEW.json';assert not dest.exists();dest.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
print(json.dumps({'path':str(dest),'sha256':sha(dest),'passed':not issues,'issues':issues[:20],'checks':sum(counts.values()),'rss':out['peak_rss_bytes']}))
