#!/usr/bin/env python3
import json,csv,hashlib,datetime,os,argparse,sys,re,statistics,collections
from pathlib import Path
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025'
parser=argparse.ArgumentParser(description='Refresh descriptive tables from registry and validated evaluation JSON only.')
parser.add_argument('--output',type=Path,required=True,help='New snapshot output directory under runtime_20261025/reports')
parser.add_argument('--template',type=Path,default=R/'reports/deadline_submission_20261029/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md')
parser.add_argument('--self-test',action='store_true')
args=parser.parse_args()
OUT=args.output if args.output.is_absolute() else ROOT/args.output
if OUT.exists() and any(OUT.iterdir()): raise FileExistsError(f'Output must be a new empty directory: {OUT}')
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def wc(name,rows,fields=None):
 if fields is None: fields=list(dict.fromkeys(k for r in rows for k in r))
 with (OUT/name).open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
sys.path.insert(0,str(R/'source'))
import reporting as paired_helpers
if args.self_test:
 demo=[{'key':'e4/r1/control','scientific_case':True,'experiment':4,'rep':1,'method':'demo','condition':'control','route':'direct','outcome':'successful','balanced_accuracy':0.5,'coverage':0.9,'set_size':2.0},{'key':'e4/r1/altered','scientific_case':True,'experiment':4,'rep':1,'method':'demo','condition':'half','route':'direct','target_class':'0','ratio':0.5,'outcome':'successful','balanced_accuracy':0.4,'coverage':0.9,'set_size':2.1}]
 classes=[{'key':'e4/r1/control','class_id':'0','recall':0.8,'coverage':0.9},{'key':'e4/r1/altered','class_id':'0','recall':0.6,'coverage':0.9}]
 pairs=paired_helpers._e4_paired_controls(demo,classes)
 assert len(pairs)==1 and round(pairs[0]['paired_balanced_accuracy_difference_a_minus_b'],6)==-0.1 and round(pairs[0]['paired_target_class_recall_difference_a_minus_b'],6)==-0.2
 clean={'key':'e5/r1/clean','scientific_case':True,'experiment':5,'rep':1,'method':'demo','route':'direct','condition':'clean','mechanism':'clean','outcome':'successful','balanced_accuracy':0.5,'coverage':0.9,'set_size':2.0}
 corrupt={'key':'e5/r1/corrupt','scientific_case':True,'experiment':5,'rep':1,'method':'demo','route':'direct','condition':'label_noise','mechanism':'label_noise','rate':0.05,'outcome':'successful','balanced_accuracy':0.4,'coverage':0.88,'set_size':2.1}
 p5=paired_helpers._e5_paired_metrics([clean,corrupt])
 assert len(p5)==1 and round(p5[0]['paired_balanced_accuracy_difference_a_minus_b'],6)==-0.1 and round(p5[0]['paired_coverage_difference_a_minus_b'],6)==-0.02
 sm=paired_helpers._condition_paired_summary(p5,['method','route','generator','mechanism','rate'],['paired_balanced_accuracy_difference_a_minus_b'])
 assert sm[0]['paired_balanced_accuracy_difference_a_minus_b_n']==1 and sm[0]['paired_balanced_accuracy_difference_a_minus_b_sample_sd'] is None
 print('pure refresh fixtures passed; no evaluation artifact opened');sys.exit(0)
regp=R/'registry.json';reg=json.loads(regp.read_text());obs=reg['observed_utc'];tasks=reg['tasks'];cases=[t for t in tasks if t.get('scientific_case') and t.get('experiment') in (3,4,5,6)]
expected_planned={3:69,4:1773,5:960,6:21}
assert len(cases)==sum(expected_planned.values()),len(cases)
for e,n in expected_planned.items(): assert sum(t.get('experiment')==e for t in cases)==n,(e,n)
if not args.output.is_absolute(): OUT=ROOT/args.output
OUT.mkdir(parents=True,exist_ok=True)
counts={}
for e in (3,4,5,6):
 c={}
 for t in cases:
  if t['experiment']==e:
   k=t.get('outcome') or t.get('status');c[k]=c.get(k,0)+1
 counts[e]=c
assert set(counts)=={3,4,5,6}
def norm_outcome(t):
 o=t.get('outcome') or t.get('status')
 if t.get('status')=='validated_terminal' and isinstance(o,dict): o=o.get('status') or o.get('outcome') or t.get('status')
 return o
e6_primary=[t for t in cases if t.get('experiment')==6 and (t.get('kind')=='ensemble' or t.get('mode') in {'equal','learned'})]
e6_members=[t for t in cases if t.get('experiment')==6 and (t.get('kind')=='alias' or t.get('condition')=='member_reference')]
e6pc=collections.Counter(norm_outcome(t) for t in e6_primary);e6mc=collections.Counter(norm_outcome(t) for t in e6_members)
labels=['A','F','G','K','M','GALAXY','QSO']; ledger=[];metrics=[];perclass=[];cmrows=[];inputs=[];missing=[]
for t in sorted(cases,key=lambda x:x['key']):
 key=t['key'];status=t.get('status');outcome=t.get('outcome') or status
 if status=='validated_terminal' and isinstance(outcome,dict):outcome=outcome.get('status') or outcome.get('outcome') or status
 art='runtime_20261025/artifacts/'+key
 row={'snapshot_observed_utc':obs,'task_key':key,'key':key,'scientific_case':True,'experiment':t['experiment'],'kind':t.get('kind'),'rep':t.get('rep'),'budget':t.get('budget'),'method':t.get('method'),'condition':t.get('condition'),'route':t.get('route'),'mode':t.get('mode'),'target_class':t.get('target_class'),'ratio':t.get('ratio'),'treatment':t.get('treatment'),'mechanism':t.get('mechanism'),'rate':t.get('rate'),'generator':t.get('generator'),'registry_status':status,'outcome':outcome,'validation_state':t.get('validation_state'),'dependencies_json':json.dumps(t.get('dependencies') or [],separators=(',',':')),'artifact_path_relative':art,'evaluation_json_available':False,'evaluation_json_sha256':'','balanced_accuracy':None,'coverage':None,'set_size':None,'calibration_n':None,'test_n':None,'score_kind':None,'threshold':None}
 ev=None;ep=R/'artifacts'/key/'evaluation.json'
 if outcome=='successful' and t.get('validation_state') in {'valid','validated','passed','validated_terminal','success'} and ep.is_file():
  raw=ep.read_bytes();row['evaluation_json_available']=True;row['evaluation_json_sha256']=hashlib.sha256(raw).hexdigest();inputs.append({'task_key':key,'experiment':t['experiment'],'path_relative':art+'/evaluation.json','sha256':row['evaluation_json_sha256']});ev=json.loads(raw)
  for k in ('balanced_accuracy','coverage','set_size','calibration_n','test_n','score_kind','threshold'):
   row[k]=ev.get(k)
  metrics.append(dict(row))
  pcs=ev.get('per_class')
  if isinstance(pcs,dict):
   for cl,v in pcs.items():
    if isinstance(v,dict):perclass.append({'task_key':key,'key':key,'experiment':t['experiment'],'rep':t.get('rep'),'method':t.get('method'),'route':t.get('route'),'condition':t.get('condition'),'target_class':t.get('target_class'),'ratio':t.get('ratio'),'treatment':t.get('treatment'),'mechanism':t.get('mechanism'),'rate':t.get('rate'),'generator':t.get('generator'),'class_id':str(cl),'n':v.get('n'),'recall':v.get('recall'),'coverage':v.get('coverage'),'set_size':v.get('set_size')})
  cm=ev.get('confusion_matrix')
  if isinstance(cm,list) and len(cm)==7 and all(isinstance(x,list) and len(x)==7 for x in cm):
   for i,rr in enumerate(cm):
    for j,val in enumerate(rr):cmrows.append({'task_key':key,'experiment':t['experiment'],'rep':t.get('rep'),'method':t.get('method'),'route':t.get('route'),'condition':t.get('condition'),'true_class':labels[i],'predicted_class':labels[j],'count':int(val)})
 if outcome=='successful' and ev is None:missing.append(key)
 ledger.append(row)
fields=['snapshot_observed_utc','task_key','experiment','kind','rep','budget','method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator','registry_status','outcome','validation_state','evaluation_json_available','balanced_accuracy','coverage','set_size','calibration_n','test_n','score_kind','threshold','dependencies_json','artifact_path_relative','evaluation_json_sha256']
wc('planned_case_ledger.csv',ledger,fields);wc('per_repetition_metrics.csv',metrics,fields)
wc('per_class_metrics.csv',perclass);wc('confusion_matrices_long.csv',cmrows)
wc('evaluation_input_hashes.csv',inputs,['task_key','experiment','path_relative','sha256'])
# Paired contrasts are computed from the same in-memory rows and saved evaluation JSON metrics.
paired=paired_helpers._paired(ledger)
e4pairs=paired_helpers._e4_paired_controls(ledger,perclass)
e4summary=paired_helpers._condition_paired_summary(e4pairs,['comparison','method','target_class','ratio','treatment'],['paired_balanced_accuracy_difference_a_minus_b','paired_coverage_difference_a_minus_b','paired_set_size_difference_a_minus_b','paired_target_class_recall_difference_a_minus_b','paired_target_class_coverage_difference_a_minus_b'])
e5pairs=paired_helpers._e5_paired_metrics(ledger)
e5summary=paired_helpers._condition_paired_summary(e5pairs,['method','route','generator','mechanism','rate'],['paired_balanced_accuracy_difference_a_minus_b','paired_coverage_difference_a_minus_b','paired_set_size_difference_a_minus_b'])
e5classpairs=paired_helpers._paired_per_class(ledger,perclass)
e5classsummary=paired_helpers._condition_paired_summary(e5classpairs,['method','route','generator','mechanism','rate','class_id'],['recall_difference_a_minus_b','coverage_difference_a_minus_b','set_size_difference_a_minus_b'])
wc('matched_paired_differences_current.csv',paired)
wc('E4_CONTROL_TREATMENT_PAIRED_CURRENT.csv',e4pairs)
wc('E4_CONTROL_TREATMENT_PAIRED_SUMMARY_CURRENT.csv',e4summary)
wc('E5_clean_corrupted_paired_metrics_CURRENT.csv',e5pairs)
wc('E5_clean_corrupted_paired_metrics_SUMMARY_CURRENT.csv',e5summary)
wc('E5_per_class_paired_differences_CURRENT.csv',e5classpairs)
wc('E5_per_class_paired_summary_CURRENT.csv',e5classsummary)
wc('condition_metric_summary.csv',paired_helpers._summary(ledger))
statusrows=[
{'experiment':'E1 frozen','planned':765,'successful':674,'scientific_failure':81,'unsupported':10,'unavailable':0,'waiting':0,'note':'55 resource failures; 26 supervisor-terminal manifests remained started'},
{'experiment':'E1 recovery supplement','planned':91,'successful':24,'scientific_failure':10,'unsupported':0,'unavailable':0,'waiting':0,'note':'Separate stopped supplement: 2 user-stopped; 55 not attempted'},
{'experiment':'E2 primary','planned':150,'successful':108,'scientific_failure':0,'unsupported':0,'unavailable':42,'waiting':0,'note':'Original/reconstructed provenance retained'},
{'experiment':'E2 classical references','planned':120,'successful':120,'scientific_failure':0,'unsupported':0,'unavailable':0,'waiting':0,'note':'Separate from primary grid'}]
for e,n,p in [(3,'E3',69),(4,'E4',1773),(5,'E5',960),(6,'E6 all',21)]:
 c=counts[e];statusrows.append({'experiment':n,'planned':p,'successful':c.get('successful',0),'scientific_failure':c.get('scientific_failure',0),'unsupported':c.get('unsupported',0),'unavailable':c.get('unavailable_dependency',0),'waiting':c.get('waiting_for_dependency',0),'note':'Read-only registry snapshot'})
statusrows += [{'experiment':'E6 primary ensembles','planned':len(e6_primary),'successful':e6pc.get('successful',0),'scientific_failure':e6pc.get('scientific_failure',0),'unsupported':e6pc.get('unsupported',0),'unavailable':e6pc.get('unavailable_dependency',0),'waiting':e6pc.get('waiting_for_dependency',0),'note':'Primary ensemble task outcomes from the registry'},
{'experiment':'E6 member references','planned':len(e6_members),'successful':e6mc.get('successful',0),'scientific_failure':e6mc.get('scientific_failure',0),'unsupported':e6mc.get('unsupported',0),'unavailable':e6mc.get('unavailable_dependency',0),'waiting':e6mc.get('waiting_for_dependency',0),'note':'Member-reference aliases and dependencies'}]
wc('experiment_status_summary.csv',statusrows)
# Status snapshot figure as standalone SVG, no model or external payload reads.
items=[('E1 frozen',765,674,81,10,0),('E2 primary',150,108,0,42,0),('E2 classical',120,120,0,0,0),('E3',69,counts[3].get('successful',0),counts[3].get('scientific_failure',0),counts[3].get('unavailable_dependency',0),counts[3].get('waiting_for_dependency',0)),('E4',1773,counts[4].get('successful',0),counts[4].get('scientific_failure',0),counts[4].get('unavailable_dependency',0),counts[4].get('waiting_for_dependency',0)),('E5',960,counts[5].get('successful',0),counts[5].get('scientific_failure',0),counts[5].get('unavailable_dependency',0),counts[5].get('waiting_for_dependency',0)),('E6 ensembles',len(e6_primary),e6pc.get('successful',0),e6pc.get('scientific_failure',0),e6pc.get('unavailable_dependency',0),e6pc.get('waiting_for_dependency',0)),('E6 refs',len(e6_members),e6mc.get('successful',0),e6mc.get('scientific_failure',0),e6mc.get('unavailable_dependency',0),e6mc.get('waiting_for_dependency',0))]
W=1000;H=430;left=220;right=80;top=70;barh=28;gap=15;scale=(W-left-right)/max(x[1] for x in items);cols=['#27864b','#c64b26','#738096','#d69e2e'];svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">','<rect width="100%" height="100%" fill="white"/>','<text x="40" y="35" font-family="Arial" font-size="20">Current scientific-case coverage (read-only registry snapshot)</text>']
for i,(name,total,succ,fail,unav,wait) in enumerate(items):
 y=top+i*(barh+gap);svg.append(f'<text x="20" y="{y+20}" font-family="Arial" font-size="13">{name}</text>');x=left
 for val,col in zip((succ,fail,unav,wait),cols):
  width=val*scale
  if val:
   svg.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="{barh}" fill="{col}"/>')
   if width>35:svg.append(f'<text x="{x+width/2:.2f}" y="{y+19}" text-anchor="middle" font-family="Arial" font-size="11" fill="white">{val}</text>')
   x+=width
 svg.append(f'<text x="{left+total*scale+7:.2f}" y="{y+19}" font-family="Arial" font-size="11">{total}</text>')
svg.append('<g font-family="Arial" font-size="12">')
for i,(c,l) in enumerate(zip(cols,['Successful/evaluated','Scientific failure','Unsupported/unavailable','Waiting'])):
 x=left+i*180;svg.append(f'<rect x="{x}" y="397" width="14" height="14" fill="{c}"/><text x="{x+20}" y="409">{l}</text>')
svg += ['</g>',f'<text x="20" y="425" font-family="Arial" font-size="10">Snapshot {obs}; E6 aliases shown separately from primary ensemble outcomes.</text>','</svg>']
(OUT/'current_status_coverage.svg').write_text('\n'.join(svg)+'\n')
# Findings report with references to reviewed component reports and all current tables.
report=f"""# LAMOST six-experiment research: consolidated interim submission

**INTERIM - not final project completion.** Read-only registry snapshot: {obs} UTC on the existing EC2. This submission combines frozen E1/E2 reports with current E3-E6 case outcomes and metrics from saved, validated evaluation JSONs. No model was loaded, fit, retuned, or used for inference; no bootstrap was run. Existing test outcomes are already observed, so later cohorts are not described as an untouched prospective test.

## Current status

| Experiment | Planned | Successful/evaluated | Recorded failures | Unsupported/unavailable | Waiting |
|---|---:|---:|---:|---:|---:|
| E1 frozen | 765 | 674 | 81 (55 resource; 26 supervisor-terminal manifests remained started) | 10 unsupported | 0 |
| E1 stopped recovery | 91 separate | 24 retries | 10 retry failures | 2 user-stopped; 55 not attempted | 0 |
| E2 primary | 150 | 108 | - | 42 unavailable | 0 |
| E2 classical references | 120 | 120 | - | 0 | 0 |
| E3 | 69 | 64 | 3 | 2 | 0 |
| E4 | 1,773 | 1,605 | 71 | 3 | 94 |
| E5 | 960 | 700 | 50 | 78 | 132 |
| E6 primary ensembles | 6 | 0 | 3 | 3 | 0 |
| E6 member references | 15 | 12 aliases | 0 | 3 | 0 |

E4/E5 have 226 planned cases waiting in the registry snapshot. Current planned outcomes and all available saved evaluation metrics are in the CSVs in this directory. Existing aggregate research figures remain dated to their validated analysis cutoff; the status chart is current at this snapshot.

## Shared data and protocol

The baseline has approximately 2,330,835 source representatives, seven labels (A, F, G, K, M, GALAXY, QSO), six predictors (Pan-STARRS g/r/i/z/y and Gaia G), and a fixed 500,000-source test cohort. IDs, labels, spectra, and audit metadata are not predictors. Fit, tuning, calibration, and test roles remain separate. E1/E2 test outcomes were observed before later experiment plans were frozen. Nominal conformal target is 90%; prediction-set size is interpreted together with overall and classwise coverage. No bootstrap confidence intervals or significance claims are included.

## E1 - frozen benchmark and stopped recovery

Frozen E1 is unchanged: 765 terminal, 674 successful, 81 failed (55 resource failures and 26 supervisor-terminal cells whose manifests remained started), and 10 unsupported. The 100k budget was terminal with 67 successes and 18 failures. E1's per-cell table, method-by-budget summaries, learning curves, coverage, set size, and actual successful repetition counts are in the [frozen report](../../experiments/E1/frozen/E1_WRAPUP.md) and [765-cell ledger](../../experiments/E1/frozen/E1_frozen_cells_765.csv). Frozen execution used 180 seconds per trial and a 6-GiB worker limit; timing depends on hardware and shared load.

The recovery supplement is separate and stopped: 24 successes, 10 retry failures, 2 user-stopped partial cells, 55 not attempted. Recovery never replaces frozen E1. Historical fitted classifiers and per-test-row predictions were omitted in the compact migration. Seven auxiliary tuning-history discrepancies remain documented.

## E2 - generator fidelity and direct classification

The primary grid is 108/150, with 42 unavailable because the frozen E1 selected fit did not exist. A separate classical reference set is 120/120. Original/reconstructed provenance remains explicit: 31 reconstructed balanced-accuracy comparisons failed the documented equality gate, and 210 of 1,596 class reports are low precision. Only four of 30 budget/repetition strata have all five primary generator families; their descriptive Spearman values are 0.700, 0.100, 0.300, and 0.700. These four strata do not support a general fidelity-classification relationship. See the [E2 report](../../experiments/E2/E2_CURRENT_REPORT.md), [combined 270 rows](../../experiments/E2/E2_all_generators_270.csv), [1,596 class reports](../../experiments/E2/E2_all_class_reports_1596.csv), and [integrity audit](../../experiments/E2/E2_INTEGRITY_AUDIT.json).

## E3 - direct Bayes, synthetic-only, real-only

E3 is terminal at 64/69 successful, 3 scientific failures, 2 unavailable. All 15 generator datasets were produced. Nine generator fits reused matching E2 reconstructed selected pipelines; six ARF/KDE fits were new E3 dependencies. All three direct-KDE test phases hit the fixed 600-second limit. Two GMM/KDE rep-2 synthetic random-forest cases are unavailable because their downstream fit tasks exceeded the 10-GiB process-tree policy. These are feasibility outcomes and carry no fabricated accuracy. See the [reviewed E3 report](../E3_FINAL_DESCRIPTIVE_REPORT.md) for route-specific denominators, repetitions, paired comparisons, conformal metrics, and phase cost scope.

## E4 - imbalance and restoration

E4 currently has 1,605 successes, 71 failures, 3 unavailable, and 94 waiting. The reviewed direct-KNN block contains all 45 cells (3 controls plus 42 altered); every altered condition is paired to the matching repetition's unchanged control. Across the 14 target-by-severity means, target-class recall fell in each condition. The 0.1 retained-share conditions include large classwise recall losses; some returned full seven-label sets with coverage 1, which is not an efficiency benefit.

The reviewed direct-kernel block shows availability and evaluation feasibility separately: all 45 RBF-SVM selected models existed, but 18 evaluations succeeded and 27 failed under the fixed policy. All 45 KDE selected models existed; 42 altered test phases timed out and 3 unchanged-control aliases were unavailable because E3 direct KDE timed out. See the [direct-KNN block](../e4_direct_knn_block_20261027/E4_DIRECT_KNN_BLOCK_REPORT.md) and [direct-kernel block](../e4_direct_kernel_block_20261027/E4_DIRECT_KERNEL_BLOCK_REPORT.md). These are condition-specific findings, not a universal restoration effect.

## E5 - fitting-data corruption

E5 currently has 700 successes, 50 failures, 78 unavailable, and 132 waiting. The reviewed direct-RF and direct-KNN blocks each include all 30 cells (3 clean controls and 27 corrupted) and all nine mechanism/rate strata with three matched repetitions. At 20% label noise, mean balanced-accuracy change was -0.017309 for RF and -0.023067 for KNN. At 20% feature noise it was -0.010556 and -0.009613; at 20% missingness -0.005531 and -0.006139. These compare only two direct routes under the specified masks. No universal ranking follows; coverage, set size, per-class effects, failures, and unavailable cases remain included in the component tables. See the [RF report](../e5_direct_rf_block_20261027/E5_DIRECT_RF_BLOCK_REPORT.md) and [KNN report](../e5_direct_knn_block_20261027/E5_DIRECT_KNN_BLOCK_REPORT.md).

## E6 - posterior ensembles

Twelve of 15 member-reference rows are successful aliases to existing E3 evaluations; three KDE references are unavailable following E3 direct-KDE timeouts. The six primary ensembles have no successful test evaluation: all three equal-weight test phases timed out, and learned-weight tasks are unavailable after the shared test phase terminated. This report therefore makes no ensemble performance or weight-benefit claim and does not label tuning-only artifacts as tested ensembles. See the [E6 interim record](../E6_CURRENT_DESCRIPTIVE_INTERIM_20261027T204752Z.md).

## Timing, provenance, and remaining validation

E1 used 180-second/6-GiB settings. E3-E6 settings are 600-second/10-GiB per worker; admission profiles and hardware differ, and timing is not directly comparable across all experiments. Existing cost tables are dated and are not reinterpreted as new timings. Final native calibration replay, full artifact validation, the cross-experiment final report, and final full/small archive CRC/SHA verification remain pending. This delivery is an interim scientific submission; it does not stop authorized work or mark pending cases terminal.
"""
# Use the reviewed prior report as template; replace only status-dependent text and E4/E5 summary tables.
template=args.template
if not template.is_absolute(): template=ROOT/template
if template.exists(): report=template.read_text(encoding='utf-8')
report=re.sub(r'(Read-only registry snapshot: )\d{4}-\d\d-\d\dT[^ ]+',lambda m:m.group(1)+obs,report)
def _statusrow(name,total,succ,fail,unav,wait): return f'| {name} | {total:,} | {succ:,} | {fail:,} | {unav:,} | {wait:,} |'
for prefix,newrow in [('| E3 |',_statusrow('E3',69,counts[3].get('successful',0),counts[3].get('scientific_failure',0),counts[3].get('unavailable_dependency',0)+counts[3].get('unsupported',0),counts[3].get('waiting_for_dependency',0))),('| E4 |',_statusrow('E4',1773,counts[4].get('successful',0),counts[4].get('scientific_failure',0),counts[4].get('unavailable_dependency',0)+counts[4].get('unsupported',0),counts[4].get('waiting_for_dependency',0))),('| E5 |',_statusrow('E5',960,counts[5].get('successful',0),counts[5].get('scientific_failure',0),counts[5].get('unavailable_dependency',0)+counts[5].get('unsupported',0),counts[5].get('waiting_for_dependency',0))),('| E6 primary ensembles |',_statusrow('E6 primary ensembles',len(e6_primary),e6pc.get('successful',0),e6pc.get('scientific_failure',0),e6pc.get('unavailable_dependency',0)+e6pc.get('unsupported',0),e6pc.get('waiting_for_dependency',0))),('| E6 member references |',_statusrow('E6 member references',len(e6_members),e6mc.get('successful',0),e6mc.get('scientific_failure',0),e6mc.get('unavailable_dependency',0)+e6mc.get('unsupported',0),e6mc.get('waiting_for_dependency',0)))]:
 report=re.sub(r'^'+re.escape(prefix)+r'.*$',newrow,report,flags=re.M)
report=report.replace('| Scientific failures |','| Recorded failures |')
waiting=counts[4].get('waiting_for_dependency',0)+counts[5].get('waiting_for_dependency',0)
report=re.sub(r'E4/E5 have \d+ planned cases waiting in the registry snapshot.',f'E4/E5 have {waiting} planned cases waiting in the registry snapshot.',report)
report=re.sub(r'E3 is terminal at .*?\. All 15 generator datasets',f'E3 is terminal at {counts[3].get("successful",0)}/69 successful, {counts[3].get("scientific_failure",0)} scientific failures, {counts[3].get("unavailable_dependency",0)} unavailable. All 15 generator datasets',report,count=1)
report=re.sub(r'E4 currently has .*?\. The reviewed direct-KNN block',f'E4 currently has {counts[4].get("successful",0)} successes, {counts[4].get("scientific_failure",0)} failures, {counts[4].get("unavailable_dependency",0)} unavailable, and {counts[4].get("waiting_for_dependency",0)} waiting. The reviewed direct-KNN block',report,count=1)
report=re.sub(r'E5 currently has .*?\. The reviewed direct-RF',f'E5 currently has {counts[5].get("successful",0)} successes, {counts[5].get("scientific_failure",0)} failures, {counts[5].get("unavailable_dependency",0)} unavailable, and {counts[5].get("waiting_for_dependency",0)} waiting. The reviewed direct-RF',report,count=1)
def _mdtable(headers,data): return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+'\n'.join('| '+' | '.join(map(str,r))+' |' for r in data)+'\n'
def _replace_table(heading,needle,table):
 global report
 h=report.index(heading); a=report.index(needle,h); b=report.find('\n\n',a)
 report=report[:a]+table.rstrip()+report[b:]
e4rows=[]
for comp in sorted({x.get('comparison') for x in e4summary}):
 g=[x for x in e4summary if x.get('comparison')==comp]; dist=collections.Counter(int(x.get('available_repetitions') or 0) for x in g)
 e4rows.append([comp,len(g),dist[3],dist[2],dist[1],dist[0],sum(int(x.get('paired_balanced_accuracy_difference_a_minus_b_n') or 0) for x in g)])
e5rows=[]
for mech in sorted({x.get('mechanism') for x in e5summary}):
 g=[x for x in e5summary if x.get('mechanism')==mech]; dist=collections.Counter(int(x.get('available_repetitions') or 0) for x in g)
 e5rows.append([mech,len(g),dist[3],dist[2],dist[1],dist[0],sum(int(x.get('paired_balanced_accuracy_difference_a_minus_b_n') or 0) for x in g)])
if '### All current matched-condition summaries' in report: _replace_table('### All current matched-condition summaries','| Comparison |',_mdtable(['Comparison','Planned strata','n=3','n=2','n=1','n=0','Total BA paired reps'],e4rows))
if '### All current matched corruption summaries' in report: _replace_table('### All current matched corruption summaries','| Mechanism |',_mdtable(['Mechanism','Planned strata','n=3','n=2','n=1','n=0','Total BA paired reps'],e5rows))
report=re.sub(r'(?m)^(\| E6 member references \| \d+ \| )(\d+)( \|)',lambda m:m.group(1)+m.group(2)+' aliases'+m.group(3),report,count=1)
report += f'\n\n### Snapshot history\nThis {obs} UTC interim refresh supersedes the earlier 03:53Z interim snapshot. The earlier snapshot remains available in Git history at commit c6112170e168fda4a81fb1f9e72d942e2152b24e.'
(OUT/'DEADLINE_INTERIM_SCIENTIFIC_REPORT.md').write_text(report,encoding='utf-8')
(OUT/'DEADLINE_INTERIM_SCIENTIFIC_REPORT.md').write_text(report,encoding='utf-8')
# Hash-bound receipt.
files=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and p.name not in {'submission_receipt.json'}:
  files.append({'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)})
receipt={'status':'interim_descriptive_submission','observed_utc':obs,'registry_json_sha256':sha(regp),'planned_cases':len(cases),'counts':counts,'successful_valid_metric_rows':len(metrics),'per_class_rows':len(perclass),'confusion_matrix_cells':len(cmrows),'evaluation_json_inputs':len(inputs),'successful_cases_missing_metric_json':missing,'models_loaded':0,'predictions_generated':0,'bootstrap':False,'figure':'current_status_coverage.svg','existing_scientific_figure_cutoff':'2026-10-28T17:00:39.712874Z','supersedes_git_commit':'c6112170e168fda4a81fb1f9e72d942e2152b24e','outputs':files}
(OUT/'submission_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({'observed_utc':obs,'counts':counts,'metric_rows':len(metrics),'perclass_rows':len(perclass),'cm_cells':len(cmrows),'eval_inputs':len(inputs),'missing':missing,'out':str(OUT)}))
