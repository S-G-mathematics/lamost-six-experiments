#!/usr/bin/env python3
import json,csv,hashlib,datetime,os,argparse,sys,re,statistics,collections
from pathlib import Path
ROOT=Path('/home/ubuntu/lamost_e1_migration_20261023');R=ROOT/'runtime_20261025'
parser=argparse.ArgumentParser(description='Refresh descriptive tables from registry and validated evaluation JSON only.')
parser.add_argument('--output',type=Path,required=True,help='New snapshot output directory under runtime_20261025/reports')
parser.add_argument('--template',type=Path,default=R/'reports/deadline_submission_20261029/DEADLINE_INTERIM_SCIENTIFIC_REPORT.md')
parser.add_argument('--scope-amendment',type=Path,default=R/'manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json')
parser.add_argument('--scope-application',type=Path,default=R/'reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json')
parser.add_argument('--scope-canonical-amendment-path',type=Path,default=None,help='Canonical immutable EC2 source path bound to the copied amendment bytes.')
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

def canonical_amendment_binding(candidate,root=ROOT):
 expected=(Path(root)/'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json').resolve()
 actual=Path(candidate).resolve()
 if actual!=expected: raise ValueError('Canonical amendment path binding mismatch')
 return actual
def state_of(t):
 x=t.get('outcome') or t.get('status')
 if t.get('status')=='validated_terminal' and isinstance(x,dict): x=x.get('status') or x.get('outcome') or t.get('status')
 if isinstance(x,dict): x=x.get('status') or x.get('outcome') or t.get('status')
 if x=='waiting_dependency': x='waiting_for_dependency'
 return x
REP_GROUP_FIELDS=('experiment','budget','method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator')
def _condition_identity(t):
 return tuple(str(t.get(k) or '') for k in REP_GROUP_FIELDS)
def repetition_coverage(rows):
 groups={}
 for t in rows:
  key=_condition_identity(t);g=groups.setdefault(key,{'example':t,'states':collections.Counter(),'reps':set(),'metric_reps':set(),'rows':0})
  s=state_of(t);g['states'][s]+=1;g['rows']+=1
  if t.get('rep') is not None:g['reps'].add(str(t.get('rep')))
  if t.get('rep') is not None and t.get('evaluation_json_available') in (True,'True',1,'1'):g['metric_reps'].add(str(t.get('rep')))
 out=[]
 for g in groups.values():
  t=g['example'];c=g['states']
  out.append({'experiment':t.get('experiment'),'budget':t.get('budget'),'method':t.get('method'),'condition':t.get('condition'),'route':t.get('route'),'mode':t.get('mode'),'target_class':t.get('target_class'),'ratio':t.get('ratio'),'treatment':t.get('treatment'),'mechanism':t.get('mechanism'),'rate':t.get('rate'),'generator':t.get('generator'),'planned_repetition_rows':g['rows'],'rep_ids':'|'.join(sorted(g['reps'])),'validated_metric_repetitions':len(g['metric_reps']),'metric_rep_ids':'|'.join(sorted(g['metric_reps'])),'scientific_success_rows':c.get('successful',0),'scientific_failure_rows':c.get('scientific_failure',0),'unsupported_rows':c.get('unsupported',0),'unavailable_rows':c.get('unavailable_dependency',0),'user_stopped_rows':c.get('user_stopped',0),'operationally_interrupted_rows':c.get('operationally_interrupted',0),'operationally_invalid_rows':c.get('operationally_invalid',0),'packaging_pending_rows':c.get('packaging_pending',0),'waiting_rows':c.get('waiting_for_dependency',0)+c.get('planned',0),'running_rows':c.get('running',0)})
 return out
def validate_scope_payload(amendment,application,cases,registry_task_rows,plan_sha,expected_task_count=6270,expected_scientific_count=2823):
 stopped={str(t['key']) for t in cases if state_of(t)=='user_stopped'}
 if not amendment:
  if stopped:raise ValueError('User-stopped rows require an authorized scope amendment')
  if application is not None:raise ValueError('Application receipt exists without its amendment')
  if len(cases)!=expected_scientific_count:raise ValueError('Original scientific-case denominator changed')
  return {'status':'not_applied','selected_evaluation_count':0,'user_stopped_scientific_count':0,'plan_sha256':plan_sha}
 if amendment.get('schema')!='lamost-user-single-evaluation-scope-amendment/1':raise ValueError('Unknown scope amendment schema')
 if amendment.get('original_plan_sha256')!=plan_sha:raise ValueError('Scope amendment does not bind original tasks.json bytes')
 if amendment.get('original_task_count')!=expected_task_count or amendment.get('original_scientific_count')!=expected_scientific_count:raise ValueError('Scope amendment denominator mismatch')
 if registry_task_rows!=expected_task_count or len(cases)!=expected_scientific_count:raise ValueError('Registry does not account for original task/scientific rows')
 selected=[str(k) for k in amendment.get('selected_evaluation_keys',[])];declared=[str(k) for k in amendment.get('user_stopped_scientific_keys',[])]
 if len(selected)!=45 or len(set(selected))!=45:raise ValueError('Selected evaluation keys must be 45 unique cases')
 if len(declared)!=168 or len(set(declared))!=168:raise ValueError('User-stopped keys must be 168 unique planned cases')
 if amendment.get('no_metric_values_read') is not True:raise ValueError('Scope selection is not attested score-independent')
 if amendment.get('preserves_all_prior_outcomes') is not True:raise ValueError('Scope amendment does not preserve prior terminal outcomes')
 if amendment.get('axes')!=['experiment','method','route','generator','condition','mechanism','rate','ratio','target_class','treatment']:raise ValueError('Scope amendment axes differ from the declared unique-case identity')
 case_by={str(t['key']):t for t in cases}
 if not set(selected+declared)<=set(case_by):raise ValueError('Amendment references unknown/non-scientific task keys')
 if any(int(case_by[k].get('experiment',0)) not in (4,5) for k in selected+declared):raise ValueError('Scope amendment may select/stop E4 or E5 repetitions only')
 selected_groups=[_condition_identity(case_by[k]) for k in selected]
 if len(set(selected_groups))!=len(selected_groups):raise ValueError('Multiple selected repetitions for one unique method/condition')
 if any(state_of(case_by[k])=='user_stopped' for k in selected):raise ValueError('A selected evaluation is already user-stopped')
 declared_by=amendment.get('by_experiment') or amendment.get('counts_by_experiment')
 if not isinstance(declared_by,dict):raise ValueError('Scope amendment lacks per-experiment counts')
 for exp,selected_n,stopped_n in (('E4',14,67),('E5',31,101)):
  item=declared_by.get(exp) or declared_by.get(str(int(exp[1:])))
  if not isinstance(item,dict):raise ValueError('Missing per-experiment scope counts')
  def count_item(keys):
   for k in keys:
    if k in item:
     v=item[k];return v if isinstance(v,int) else len(v) if isinstance(v,list) else None
   return None
  if count_item(('selected','selected_evaluations','selected_evaluation_keys','selected_pending_scientific'))!=selected_n or count_item(('user_stopped','user_stopped_scientific','user_stopped_scientific_keys'))!=stopped_n:raise ValueError('Per-experiment scope count mismatch')
 if set(declared)&set(selected):raise ValueError('Selected and user-stopped task keys overlap')
 if application is None:
  if stopped:raise ValueError('Registry has user-stopped rows without applied receipt')
  return {'status':'authorized_not_applied','selected_evaluation_count':len(selected),'user_stopped_scientific_count':len(declared),'plan_sha256':plan_sha}
 if application.get('schema')!='lamost-user-scope-amendment-application/1' or application.get('status')!='applied_and_verified':raise ValueError('Scope application is not verified')
 if amendment.get('preserves_all_prior_outcomes') is not True:raise ValueError('Applied amendment does not attest prior outcome preservation')
 closure=amendment.get('dependency_closure_keys') or [];pending_closure=amendment.get('selected_pending_dependency_closure_keys') or []
 if len(closure)!=167 or len(set(closure))!=167 or len(pending_closure)!=90 or len(set(pending_closure))!=90 or amendment.get('pending_dependency_closure_count')!=90:raise ValueError('Amendment dependency-closure accounting mismatch')
 if not set(pending_closure)<=set(closure):raise ValueError('Pending dependency closure is not contained in the full closure')
 if application.get('amendment_sha256')!=amendment.get('_sha256'):raise ValueError('Application receipt SHA does not match amendment')
 expected_path=amendment.get('_path')
 observed_path=application.get('amendment_path')
 if not expected_path or not observed_path:raise ValueError('Application receipt lacks amendment path binding')
 expected_abs=str(Path(expected_path).resolve())
 allowed_paths={expected_abs,'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json'}
 if str(observed_path) not in allowed_paths:raise ValueError('Application receipt amendment path mismatch')
 app_by=application.get('by_experiment')
 if not isinstance(app_by,dict):raise ValueError('Application receipt lacks per-experiment counts')
 for exp,selected_n,stopped_n in (('E4',14,67),('E5',31,101)):
  item=app_by.get(exp) or app_by.get(str(int(exp[1:])))
  if not isinstance(item,dict):raise ValueError('Application receipt lacks E4/E5 count rows')
  selected_value=next((item[k] for k in ('selected','selected_evaluations','selected_evaluation_count','selected_pending_initial','selected_pending_scientific') if k in item),None)
  stopped_value=next((item[k] for k in ('user_stopped','user_stopped_scientific','user_stopped_scientific_count') if k in item),None)
  if selected_value!=selected_n or stopped_value!=stopped_n:raise ValueError('Application receipt per-experiment counts mismatch')
 if application.get('original_plan_sha256')!=plan_sha or application.get('original_plan_unchanged') is not True:raise ValueError('Original plan not preserved')
 if application.get('existing_terminal_unchanged') is not True or application.get('only_closure_pending_proof') is not True:raise ValueError('Missing prior-terminal/closure-pending proof')
 if stopped!=set(declared):raise ValueError('Current registry stopped keys differ from authorized key list')
 actual_selected_by=collections.Counter(f'E{case_by[k].get("experiment")}' for k in selected)
 actual_stopped_by=collections.Counter(f'E{case_by[k].get("experiment")}' for k in declared)
 if actual_selected_by!={'E4':14,'E5':31} or actual_stopped_by!={'E4':67,'E5':101}:raise ValueError('Registry scope keys do not match the authorized E4/E5 allocations')
 c=application.get('counts') or {}
 if c.get('selected_pending_scientific')!=45 or c.get('user_stopped_scientific')!=168 or c.get('selected_pending_tasks')!=90 or c.get('user_stopped_tasks')!=334:raise ValueError('Application initial counts mismatch')
 return {'status':'applied_and_verified','selected_evaluation_count':len(selected),'user_stopped_scientific_count':len(stopped),'selected_current_success_or_terminal_count':sum(state_of(case_by[k]) in {'successful','scientific_failure','unsupported','unavailable_dependency'} for k in selected),'selected_current_running_count':sum(state_of(case_by[k])=='running' for k in selected),'selected_current_waiting_count':sum(state_of(case_by[k]) in {'planned','waiting_for_dependency'} for k in selected),'plan_sha256':plan_sha,'amendment_path':'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','amendment_sha256':amendment['_sha256'],'application_path':'runtime_20261025/reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json','application_sha256':application.get('_sha256'),'application_applied_utc':application.get('applied_utc')}

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
 mixed=[{'experiment':4,'method':'rf','condition':'half','rep':1,'status':'successful','outcome':'successful','evaluation_json_available':True},{'experiment':4,'method':'rf','condition':'half','rep':2,'status':'user_stopped','outcome':'user_stopped'},{'experiment':4,'method':'rf','condition':'half','rep':3,'status':'validated_terminal','outcome':{'status':'unavailable_dependency'}}]
 mc=collections.Counter(state_of(x) for x in mixed);assert mc=={'successful':1,'user_stopped':1,'unavailable_dependency':1}
 cov=repetition_coverage(mixed);assert len(cov)==1 and cov[0]['planned_repetition_rows']==3 and cov[0]['validated_metric_repetitions']==1 and cov[0]['user_stopped_rows']==1 and cov[0]['unavailable_rows']==1
 cases=[];selected=[];stopped=[];byexp={}
 for experiment,sel_count,stop_count,prefix in ((4,14,67,'E4'),(5,31,101,'E5')):
  byexp[prefix]={'selected':sel_count,'user_stopped':stop_count}
  for j in range(sel_count):
   key=f'e{experiment}/selected{j}/r1';selected.append(key);cases.append({'key':key,'experiment':experiment,'method':f'm{j}','condition':f'c{j}','rep':1,'status':'successful','outcome':'successful'})
  for j in range(stop_count):
   key=f'e{experiment}/stopped{j}/r2';stopped.append(key);cases.append({'key':key,'experiment':experiment,'method':f'stopm{j}','condition':f'stopc{j}','rep':2,'status':'user_stopped','outcome':'user_stopped'})
 a={'schema':'lamost-user-single-evaluation-scope-amendment/1','original_plan_sha256':'fixture','original_task_count':len(cases),'original_scientific_count':len(cases),'selected_evaluation_keys':selected,'user_stopped_scientific_keys':stopped,'no_metric_values_read':True,'preserves_all_prior_outcomes':True,'axes':['experiment','method','route','generator','condition','mechanism','rate','ratio','target_class','treatment'],'dependency_closure_keys':[f'closure{i}' for i in range(167)],'selected_pending_dependency_closure_keys':[f'closure{i}' for i in range(90)],'pending_dependency_closure_count':90,'by_experiment':byexp,'_sha256':'fixturehash','_path':'/fixture/runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json'}
 a['_path']='/fixture/runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json'
 app={'schema':'lamost-user-scope-amendment-application/1','status':'applied_and_verified','amendment_path':'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','amendment_sha256':'fixturehash','original_plan_sha256':'fixture','original_plan_unchanged':True,'existing_terminal_unchanged':True,'only_closure_pending_proof':True,'counts':{'selected_pending_scientific':45,'user_stopped_scientific':168,'selected_pending_tasks':90,'user_stopped_tasks':334},'by_experiment':{'4':{'selected_pending_scientific':14,'user_stopped_scientific':67},'5':{'selected_pending_scientific':31,'user_stopped_scientific':101}}}
 z=validate_scope_payload(a,app,cases,len(cases),'fixture',len(cases),len(cases));assert z['status']=='applied_and_verified' and z['user_stopped_scientific_count']==168
 assert z['selected_current_success_or_terminal_count']==45 and z['selected_current_waiting_count']==0
 bad_exp=dict(a);bad_exp['selected_evaluation_keys']=selected[:-1]+[stopped[0]]
 try:validate_scope_payload(bad_exp,app,cases,len(cases),'fixture',len(cases),len(cases))
 except ValueError:pass
 else:raise AssertionError('non-E4/E5 scope allocation accepted')
 try:validate_scope_payload(a,None,cases,len(cases),'fixture',len(cases),len(cases))
 except ValueError:pass
 else:raise AssertionError('user-stopped registry without application receipt accepted')
 for bad in ({**app,'amendment_sha256':'bad'},{**app,'amendment_path':'elsewhere.json'},{**app,'existing_terminal_unchanged':False},{**app,'by_experiment':{'E4':{'selected':14,'user_stopped':66},'E5':{'selected':31,'user_stopped':101}}}):
  try:validate_scope_payload(a,bad,cases,len(cases),'fixture',len(cases),len(cases))
  except ValueError:pass
  else:raise AssertionError('inconsistent application accepted')
 print('pure refresh and stopped-scope fixtures passed; no evaluation artifact opened');sys.exit(0)
regp=R/'registry.json';reg=json.loads(regp.read_text());obs=reg['observed_utc'];tasks=reg['tasks'];cases=[t for t in tasks if t.get('scientific_case') and t.get('experiment') in (3,4,5,6)]
plan_path=R/'manifests/tasks.json';plan=json.loads(plan_path.read_text());planned_scientific={str(t['key']) for t in plan.get('tasks',[]) if t.get('scientific_case') and t.get('experiment') in (3,4,5,6)}
plan_task_keys={str(t['key']) for t in plan.get('tasks',[])}
if len(plan_task_keys)!=6270 or len(planned_scientific)!=2823:raise ValueError('Authoritative frozen task manifest denominator mismatch')
if {str(t['key']) for t in cases}!=planned_scientific:raise ValueError('Registry scientific keys differ from the frozen 2,823-case plan')
if len(tasks)!=6270: raise ValueError('Sanitized SQLite snapshot must bind 6,270 DAG rows')
amend_path=args.scope_amendment if args.scope_amendment.is_absolute() else ROOT/args.scope_amendment
app_path=args.scope_application if args.scope_application.is_absolute() else ROOT/args.scope_application
amendment=json.loads(amend_path.read_text()) if amend_path.is_file() else None
application=json.loads(app_path.read_text()) if app_path.is_file() else None
if amendment is not None:
 amendment['_sha256']=sha(amend_path)
 if args.scope_canonical_amendment_path is not None:
  amendment['_path']=str(canonical_amendment_binding(args.scope_canonical_amendment_path,ROOT))
 else: amendment['_path']=str(amend_path.resolve())
if application is not None:application['_sha256']=sha(app_path);application['_path']=str(app_path.resolve())
if amendment is not None:
 if not set(amendment.get('dependency_closure_keys') or [])<=plan_task_keys or not set(amendment.get('selected_pending_dependency_closure_keys') or [])<=plan_task_keys:raise ValueError('Amendment closure contains unknown task keys')
 stopped_records=amendment.get('user_stopped_keys') or []
 if not isinstance(stopped_records,list) or len(stopped_records)!=334 or any(not isinstance(x,dict) or not x.get('key') for x in stopped_records):raise ValueError('Amendment task-level user-stop records do not match the 334-task record')
 stopped_tasks={str(x['key']) for x in stopped_records}
 if len(stopped_tasks)!=334 or not stopped_tasks<=plan_task_keys:raise ValueError('Amendment task-level user-stop keys do not match the frozen task plan')
 if not set(str(k) for k in amendment.get('user_stopped_scientific_keys',[]))<=stopped_tasks:raise ValueError('Scientific user-stopped rows are missing from task-level stop records')
scope_info=validate_scope_payload(amendment,application,cases,len(tasks),sha(R/'manifests/tasks.json'))

expected_planned={3:69,4:1773,5:960,6:21}
assert len(cases)==sum(expected_planned.values()),len(cases)
for e,n in expected_planned.items(): assert sum(t.get('experiment')==e for t in cases)==n,(e,n)
if not args.output.is_absolute(): OUT=ROOT/args.output
OUT.mkdir(parents=True,exist_ok=True)
counts={}
for e in (3,4,5,6):counts[e]=collections.Counter(state_of(t) for t in cases if t['experiment']==e)
assert set(counts)=={3,4,5,6}
def norm_outcome(t):
 return state_of(t)
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
coverage_rows=repetition_coverage(ledger)
wc('condition_repetition_coverage.csv',coverage_rows)
status_fields=['experiment','planned','successful','scientific_failure','unsupported','unavailable','user_stopped','operationally_interrupted','operationally_invalid','packaging_pending','not_attempted','waiting','running','note']
def status_row(name,planned,c,note,**extra):
 d={'experiment':name,'planned':planned,'successful':c.get('successful',0),'scientific_failure':c.get('scientific_failure',0),'unsupported':c.get('unsupported',0),'unavailable':c.get('unavailable_dependency',0),'user_stopped':c.get('user_stopped',0),'operationally_interrupted':c.get('operationally_interrupted',0),'operationally_invalid':c.get('operationally_invalid',0),'packaging_pending':c.get('packaging_pending',0),'not_attempted':0,'waiting':c.get('waiting_for_dependency',0)+c.get('planned',0),'running':c.get('running',0),'note':note}
 d.update(extra);return d
statusrows=[status_row('E1 frozen',765,{'successful':674,'scientific_failure':81,'unsupported':10},'55 resource failures; 26 supervisor-terminal manifests remained started'),status_row('E1 recovery supplement',91,{'successful':24,'scientific_failure':10,'user_stopped':2},'Separate stopped supplement',not_attempted=55),status_row('E2 primary',150,{'successful':108,'unavailable_dependency':42},'Original/reconstructed provenance retained'),status_row('E2 classical references',120,{'successful':120},'Separate from primary grid')]
for e,n,p in [(3,'E3',69),(4,'E4',1773),(5,'E5',960),(6,'E6 all',21)]:statusrows.append(status_row(n,p,counts[e],'Read-only registry snapshot'))
statusrows += [status_row('E6 primary ensembles',len(e6_primary),e6pc,'Primary ensemble task outcomes from registry'),status_row('E6 member references',len(e6_members),e6mc,'Member-reference aliases and dependencies')]
wc('experiment_status_summary.csv',statusrows,status_fields)
(OUT/'scope_amendment_receipt.json').write_text(json.dumps(scope_info,indent=2,sort_keys=True)+'\n',encoding='utf-8')
if amendment is not None:
 public_amendment={'schema':amendment.get('schema'),'amendment_id':amendment.get('amendment_id'),'created_utc':amendment.get('created_utc'),'original_plan_sha256':amendment.get('original_plan_sha256'),'original_task_count':amendment.get('original_task_count'),'original_scientific_count':amendment.get('original_scientific_count'),'axes':amendment.get('axes'),'scope':amendment.get('scope'),'rule':amendment.get('rule'),'no_metric_values_read':amendment.get('no_metric_values_read'),'preserves_all_prior_outcomes':amendment.get('preserves_all_prior_outcomes'),'selected_evaluation_keys':amendment.get('selected_evaluation_keys'),'user_stopped_scientific_keys':amendment.get('user_stopped_scientific_keys'),'counts_by_experiment':{str(e):{k:v for k,v in item.items() if k not in {'evaluation_repetition_counts'}} for e,item in (amendment.get('counts_by_experiment') or {}).items()},'full_dependency_closure_key_count':len(amendment.get('dependency_closure_keys') or []),'selected_pending_dependency_closure_count':len(amendment.get('selected_pending_dependency_closure_keys') or []),'source_path':'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','source_sha256':amendment.get('_sha256')}
 (OUT/'scope_amendment_public.json').write_text(json.dumps(public_amendment,indent=2,sort_keys=True)+'\n',encoding='utf-8')
if application is not None:
 public_application={'schema':application.get('schema'),'status':application.get('status'),'applied_utc':application.get('applied_utc'),'amendment_path':'runtime_20261025/manifests/PROSPECTIVE_REPETITION_SCOPE_AMENDMENT_20261029.json','amendment_sha256':application.get('amendment_sha256'),'original_plan_sha256':application.get('original_plan_sha256'),'original_plan_unchanged':application.get('original_plan_unchanged'),'existing_terminal_unchanged':application.get('existing_terminal_unchanged'),'only_closure_pending_proof':application.get('only_closure_pending_proof'),'counts':application.get('counts'),'by_experiment':application.get('by_experiment'),'source_path':'runtime_20261025/reports/SINGLE_EVAL_SCOPE_APPLICATION_20261029.json','source_sha256':application.get('_sha256')}
 (OUT/'scope_application_public.json').write_text(json.dumps(public_application,indent=2,sort_keys=True)+'\n',encoding='utf-8')
# Status snapshot figure: stopped and operational states are separate from failures.
def figitem(name,total,c,not_attempted=0,unsupported=None):
 return (name,total,c.get('successful',0),c.get('scientific_failure',0),c.get('unsupported',0) if unsupported is None else unsupported,c.get('unavailable_dependency',0),c.get('user_stopped',0),not_attempted,c.get('operationally_interrupted',0)+c.get('operationally_invalid',0)+c.get('packaging_pending',0),c.get('waiting_for_dependency',0)+c.get('planned',0)+c.get('running',0))
items=[('E1 frozen',765,674,81,0,0,0,0,0,0),('E1 recovery',91,24,10,0,0,2,55,0,0),('E2 primary',150,108,0,0,42,0,0,0,0),('E2 classical',120,120,0,0,0,0,0,0,0),figitem('E3',69,counts[3]),figitem('E4',1773,counts[4]),figitem('E5',960,counts[5]),figitem('E6 ensembles',len(e6_primary),e6pc),figitem('E6 member references',len(e6_members),e6mc)]
W=1120;H=520;left=250;right=110;top=65;barh=25;gap=14;scale=(W-left-right)/max(x[1] for x in items)
colors=['#27864b','#c64b26','#596579','#8794a8','#7c3aed','#db2777','#8b5cf6','#d69e2e']
labels=['Successful/evaluated','Scientific failure','Unsupported','Unavailable dependency','User-stopped','Not attempted','Operational interruption/invalid','Waiting or active']
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">','<rect width="100%" height="100%" fill="white"/>','<text x="32" y="32" font-family="Arial" font-size="20">Scientific case ledger status by experiment</text>']
for i,(name,total,succ,fail,unsup,unav,stopped,not_attempted,operational,wait) in enumerate(items):
 y=top+i*(barh+gap);svg.append(f'<text x="20" y="{y+18}" font-family="Arial" font-size="12">{name}</text>');x=left
 for val,col in zip((succ,fail,unsup,unav,stopped,not_attempted,operational,wait),colors):
  width=val*scale
  if val:
   svg.append(f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="{barh}" fill="{col}"/>')
   if width>35:svg.append(f'<text x="{x+width/2:.2f}" y="{y+17}" text-anchor="middle" font-family="Arial" font-size="10" fill="white">{val}</text>')
   x+=width
 svg.append(f'<text x="{left+total*scale+6:.2f}" y="{y+17}" font-family="Arial" font-size="11">{total}</text>')
for i,(color,label) in enumerate(zip(colors,labels)):
 row=i//4;col=i%4;x=left+col*210;y=433+row*24
 svg.append(f'<rect x="{x}" y="{y}" width="13" height="13" fill="{color}"/><text x="{x+18}" y="{y+11}" font-family="Arial" font-size="10">{label}</text>')
svg += [f'<text x="20" y="496" font-family="Arial" font-size="10">Registry snapshot {obs}; ledger states are not process-liveness claims; E6 aliases are separate from primary ensembles.</text>','</svg>']
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
report=report.replace('| Experiment | Planned | Successful/evaluated | Recorded failures | Unsupported/unavailable | Waiting |','| Experiment | Planned | Successful/evaluated | Scientific failures | Unsupported | Unavailable | User-stopped | Not attempted | Operationally interrupted | Operationally invalid | Packaging pending | Waiting/active |')
def status_line(name,total,c,not_attempted=0):
 success=f'{c.get("successful",0)} aliases' if name=='E6 member references' else str(c.get('successful',0))
 return f'| {name} | {total:,} | {success} | {c.get("scientific_failure",0)} | {c.get("unsupported",0)} | {c.get("unavailable_dependency",0)} | {c.get("user_stopped",0)} | {not_attempted} | {c.get("operationally_interrupted",0)} | {c.get("operationally_invalid",0)} | {c.get("packaging_pending",0)} | {c.get("waiting_for_dependency",0)+c.get("planned",0)+c.get("running",0)} |'
fixed={'E1 frozen':({'successful':674,'scientific_failure':81,'unsupported':10},765),'E2 primary':({'successful':108,'unavailable_dependency':42},150),'E2 classical references':({'successful':120},120),'E6 primary ensembles':(e6pc,len(e6_primary)),'E6 member references':(e6mc,len(e6_members))}
for name,e,total in [('E3',3,69),('E4',4,1773),('E5',5,960)]:
 fixed[name]=(counts[e],total)
for name,(c,total) in fixed.items():
 report=re.sub(r'(?m)^\| '+re.escape(name)+r' \|.*$',status_line(name,total,c),report,count=1)
report=re.sub(r'(?m)^\| E1 stopped recovery \|.*$', '| E1 stopped recovery | 91 | 24 retries | 10 retry failures | 0 | 0 | 2 | 55 | 0 | 0 | 0 | 0 |', report,count=1)
scope_note=''
if scope_info['status']=='applied_and_verified':
 scope_note=f'\n\n## Prospective repetition-scope amendment\n\nA score-independent amendment was applied and verified at {scope_info.get("application_applied_utc","the recorded time")}. It selects one pending evaluation key per unique method/condition case from the original three-repetition plan, along with its reviewed dependency closure. All prior terminal outcomes are preserved. The original 2,823 scientific-case plan and task-manifest SHA remain unchanged. It marks {scope_info["user_stopped_scientific_count"]} pending scientific repetition rows user-stopped, not failed or unavailable; 167 closure tasks are in the full amendment set and 90 tasks were pending in the selected closure at application time. Selected cases may already have completed by this snapshot. See the sanitized [amendment](scope_amendment_public.json) and [application summary](scope_application_public.json). Actual repetition counts vary by condition; see [condition repetition coverage](condition_repetition_coverage.csv). Paired summaries use matched available repetitions; sample SD is undefined and blank at n=1. The original full three-repetition grid is not complete.'
elif scope_info['status']=='authorized_not_applied':
 scope_note='\n\n## Prospective repetition-scope amendment\n\nThe separate scope amendment is recorded, but no applied-and-verified receipt exists at this snapshot. No rows are reclassified user-stopped; the original three-repetition plan remains the denominator until the database application is verified.'
else:
 scope_note='\n\n## Repetition coverage\n\nThe original three-repetition plan remains the denominator. The condition repetition table reports actual metric repetitions and distinguishes scientific failures, unavailable outcomes, user-stopped rows, operational interruptions, and waiting rows. Sample SD is undefined and blank when n=1.'
report=report.replace('[complete E3-E6 case ledger](planned_case_ledger.csv), [per-repetition metrics]', '[complete E3-E6 case ledger](planned_case_ledger.csv), [condition repetition coverage](condition_repetition_coverage.csv), [per-repetition metrics]')
report=re.sub(r'(?m)^E4/E5 have \d+ planned cases waiting in the registry snapshot\..*$',lambda m:m.group(0)+scope_note,report,count=1)
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
report=re.sub(r'\n\n### Snapshot history\n.*\Z','',report,flags=re.S)
report += f'\n\n### Snapshot history\nThis {obs} UTC interim refresh supersedes the earlier 03:53Z interim snapshot. The earlier snapshot remains available in Git history at commit c6112170e168fda4a81fb1f9e72d942e2152b24e.'
(OUT/'DEADLINE_INTERIM_SCIENTIFIC_REPORT.md').write_text(report,encoding='utf-8')
(OUT/'DEADLINE_INTERIM_SCIENTIFIC_REPORT.md').write_text(report,encoding='utf-8')
# Hash-bound receipt.
files=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and p.name not in {'submission_receipt.json'}:
  files.append({'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)})
receipt={'status':'interim_descriptive_submission','observed_utc':obs,'registry_json_sha256':sha(regp),'planned_cases':len(cases),'counts':counts,'successful_valid_metric_rows':len(metrics),'per_class_rows':len(perclass),'confusion_matrix_cells':len(cmrows),'evaluation_json_inputs':len(inputs),'successful_cases_missing_metric_json':missing,'scope_amendment':scope_info,'condition_coverage_rows':len(coverage_rows),'models_loaded':0,'predictions_generated':0,'bootstrap':False,'figure':'current_status_coverage.svg','existing_scientific_figure_cutoff':'2026-10-28T17:00:39.712874Z','supersedes_git_commit':'c6112170e168fda4a81fb1f9e72d942e2152b24e','outputs':files}
(OUT/'submission_receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
print(json.dumps({'observed_utc':obs,'counts':counts,'metric_rows':len(metrics),'perclass_rows':len(perclass),'cm_cells':len(cmrows),'eval_inputs':len(inputs),'missing':missing,'out':str(OUT)}))
