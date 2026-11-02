#!/usr/bin/env python3
"""Build a versioned, data-only companion case index from saved ledgers and a read-only SQLite snapshot."""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,io,json,os,sqlite3,sys,tempfile
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from case_index_helpers import resource_projection,attempt_projection,model_provenance,normalize_state,later_status_counts,validate_planned_experiment_counts,manifest_budget,kernel_process_proven

EXPECTED={'E1_frozen':{'successful':674,'scientific_failure':81,'unsupported':10},
'E1_recovery_stopped_early_user_request':{'successful':24,'scientific_failure':10,'user_stopped':2,'not_attempted_user_stopped':55},
'E2_primary':{'successful':108,'unavailable_dependency':42},'E2_classical_reference':{'successful':120}}
LATER_PLANNED={3:69,4:1773,5:960,6:21}
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str)
def read_csv(p):
 with Path(p).open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def atomic_bytes(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.tmp.',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
  dfd=os.open(path.parent,os.O_RDONLY)
  try:os.fsync(dfd)
  finally:os.close(dfd)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def atomic_json(path,obj):atomic_bytes(path,(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode())
def compact(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')) if x is not None else ''
def row(status,**x):
 return {'index_key':x.get('index_key',''),'native_key':x.get('native_key',''),'native_key_origin':x.get('native_key_origin','source_native_key'),
 'experiment':x.get('experiment'),'provenance_group':x.get('group',''),'task_kind':x.get('task_kind',''),
 'budget':x.get('budget',''),'budget_source_path':x.get('budget_source_path',''),'budget_source_sha256':x.get('budget_source_sha256',''),
 'repetition':x.get('rep',''),'method':x.get('method',''),'condition':x.get('condition',''),'route':x.get('route',''),
 'target_class':x.get('target_class',''),'ratio':x.get('ratio',''),'mechanism':x.get('mechanism',''),'rate':x.get('rate',''),
 'family_set':x.get('family_set',''),'model_provenance':x.get('model_provenance',''),
 'status_native':x.get('status_native',''),'outcome_native':x.get('outcome_native',''),'status_normalized':status,
 'success':status=='successful','failure':status=='scientific_failure','unsupported':status=='unsupported',
 'unavailable':status=='unavailable_dependency','pending':status=='pending','active':status=='running',
 'user_stopped':status=='user_stopped','not_attempted':status=='not_attempted_user_stopped',
 'failure_subtype':x.get('failure_subtype',''),'availability_reason':x.get('availability_reason',''),
 'running_liveness_kernel_proven':bool(x.get('liveproof',False)),
 'balanced_accuracy':x.get('balanced_accuracy',''),'coverage':x.get('coverage',''),'mean_set_size':x.get('mean_set_size',''),
 'fidelity':x.get('fidelity',''),'fidelity_status':x.get('fidelity_status',''),'reproduction_gate':x.get('reproduction_gate',''),
 'classification_source':x.get('classification_source',''),'classification_difference_flag':x.get('classification_difference_flag',''),
 'signed_reconstruction_accuracy_difference':x.get('signed_difference',''),'absolute_reconstruction_accuracy_difference':x.get('absolute_difference',''),
 'exact_accuracy_match':x.get('exact_accuracy_match',''),'e1_classification':x.get('e1_classification',''),
 'e1_manifest_status':x.get('e1_manifest_status',''),'pipeline_available':x.get('pipeline_available',''),
 'saved_test_predictions_available':x.get('saved_test_predictions_available',''),'roles_available':x.get('roles_available',''),
 'e2_availability':x.get('e2_availability',''),'recovery_status':x.get('recovery_status',''),
 'attempt_ref':x.get('attempt_ref',''),'dependency_keys':x.get('dependencies',''),'resource_profile_json':x.get('resource_profile',''),
 'resource_profile_source':x.get('resource_profile_source',''),'admission_profile_id':x.get('admission_profile_id',''),
 'admission_reservation_bytes':x.get('admission_reservation_bytes',''),'worker_memory_limit_gib':x.get('worker_memory_limit_gib',''),
 'worker_admission_reservation_gib':x.get('worker_admission_reservation_gib',''),
 'dataset_manifest_sha256':x.get('dataset_sha256',''),'configuration_sha256':x.get('config_sha256',''),
 'frozen_plan_sha256':x.get('plan_sha256',''),'execution_code_sha256_json':x.get('code_sha256',''),
 'observed_utc':x.get('observed_utc',''),'reason':x.get('reason',''),'stop_reason':x.get('stop_reason',''),
 'source_path':x.get('source_path',''),'source_sha256':x.get('source_sha256',''),
 'secondary_source_path':x.get('secondary_path',''),'secondary_source_sha256':x.get('secondary_sha256',''),
 'tertiary_source_path':x.get('tertiary_path',''),'tertiary_source_sha256':x.get('tertiary_sha256',''),
 'source_record_sha256':x.get('record_sha256',''),'metadata_snapshot_path':x.get('meta_path',''),
 'metadata_snapshot_sha256':x.get('meta_sha256',''),'master_index_status_snapshot':x.get('master_status',''),
 'master_index_outcome_snapshot':x.get('master_outcome',''),'master_state_matches_registry':x.get('master_match','')}
def build(root,runtime,output):
 root=Path(root).resolve();runtime=Path(runtime).resolve();output=Path(output)
 if not output.is_absolute():output=(runtime/output).resolve()
 stage_base=runtime/'staging/overall_case_index_20261026'
 report_base=runtime/'reports/overall_case_index'
 try:runtime.relative_to(root)
 except ValueError:raise SystemExit('runtime must remain under declared project root')
 publication_base=None
 for candidate in (stage_base,report_base):
  try:
   output.relative_to(candidate)
   if output==candidate:continue
   publication_base=candidate;break
  except ValueError:pass
 if publication_base is None:raise SystemExit('output must be a new version directory under staging case-index or reports/overall_case_index')
 if output.exists() and any(output.iterdir()):raise SystemExit('output version already exists and is nonempty; choose a new versioned output path')
 publication_base.mkdir(parents=True,exist_ok=True)
 output.mkdir(parents=True,exist_ok=True)
 src={
 'e1':root/'e1_wrapup_20261024/E1_frozen_cells_765.csv',
 'recovery':root/'e1_wrapup_20261024/E1_recovery_cutoff_91.csv',
 'e2':root/'e2_20261024/E2_all_generators_270.csv',
 'e2a':root/'e2_20261024/E2_artifact_availability_270.csv',
 'e2m':root/'e2_20261024/E2_missing_primary_42.csv',
 'e2d':runtime/'reports/E2_RECONSTRUCTION_DIFFERENCES_VERIFIED.csv',
 'db':runtime/'registry.sqlite','master':runtime/'master_index.json',
 'reason':runtime/'source/reason_text_curation.py'}
 manifests={e:runtime/f'manifests/E{e}_MANIFEST.json' for e in (3,4,5,6)}
 src.update({f'e{e}_manifest':p for e,p in manifests.items()})
 if any(not p.is_file() for p in src.values()):raise SystemExit('required source missing')
 before={k:file_sha(v) for k,v in src.items() if k!='db'}
 master_raw=src['master'].read_bytes(); master_sha=sha(master_raw); master=json.loads(master_raw)
 mp={t.get('key'):t for t in master.get('tasks',[]) if t.get('key')}
 if len(mp)!=6270:raise SystemExit('master-index snapshot task count changed')
 spec=importlib.util.spec_from_file_location('_case_reason_curation',src['reason']);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 sanitize=mod.sanitize_reason_text
 def clean(v):return sanitize(v) or ''
 e1=read_csv(src['e1']);rec=read_csv(src['recovery']);e2=read_csv(src['e2']);e2a=read_csv(src['e2a']);e2m=read_csv(src['e2m']);e2d=read_csv(src['e2d'])
 if (len(e1),len(rec),len(e2),len(e2a),len(e2m),len(e2d))!=(765,91,270,270,42,185):raise SystemExit('frozen E1/E2 input row count changed')
 # Frozen experiment budgets come from their authoritative manifest and are source-hash bound.
 manifests_obj={};manifest_sha={};budgets={}
 for e,p in manifests.items():
  raw=p.read_bytes();manifest_sha[e]=sha(raw);manifests_obj[e]=json.loads(raw);budgets[e]=manifest_budget(manifests_obj[e])
 if {e:int(manifests_obj[e].get('planned_task_count',-1)) for e in manifests} != {3:153,4:4110,5:1986,6:21}:
  raise SystemExit('later manifest task plan identity changed')
 # Use one SQLite read-only transaction, including all task records for a reproducible snapshot digest.
 db=src['db'];con=sqlite3.connect(f'file:{db}?mode=ro',uri=True,timeout=30);con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
 all_records=[]
 for raw, in con.execute('SELECT record FROM tasks ORDER BY key'):all_records.append((raw,json.loads(raw)))
 con.execute('COMMIT');con.close()
 all_task_map={t.get('key'):t for _,t in all_records if t.get('key')}
 sqlite_snapshot_sha=sha('\n'.join(canon(t) for _,t in sorted(all_records,key=lambda z:z[1].get('key',''))).encode())
 later=[(raw,t) for raw,t in all_records if t.get('experiment') in (3,4,5,6) and t.get('scientific_case') is True]
 validate_planned_experiment_counts([t for _,t in later],LATER_PLANNED)
 # Actual current worker task inventory is separate from the scientific evaluation rows.
 worker_kinds={'fit','generate','eval','ensemble'}
 workers=[t for _,t in all_records if t.get('kind') in worker_kinds]
 live_by_kind=Counter();unproven_by_kind=Counter();state_by_kind=Counter();running_worker_records=[]
 for t in workers:
  if t.get('status')=='running':
   proven=kernel_process_proven(t,runtime_root=runtime)
   if proven:live_by_kind[t['kind']]+=1
   else:unproven_by_kind[t['kind']]+=1
   wm=mp.get(t.get('key'),{});wrp=resource_projection(t,wm)
   running_worker_records.append({'task_key':t.get('key'),'kind':t.get('kind'),'kernel_liveness_proven':proven,
    'attempt_reference':attempt_projection(wm),'resource_profile_source':wrp.get('resource_profile_source') or wrp.get('admission_profile_source'),
    'admission_profile_id':wrp.get('admission_profile_id'),'admission_reservation_bytes':wrp.get('admission_reservation_bytes'),
    'worker_memory_limit_gib':wrp.get('worker_memory_limit_gib'),'worker_memory_gib':wrp.get('worker_memory_gib'),
    'worker_admission_reservation_gib_by_class':wrp.get('worker_admission_reservation_gib_by_class')})
  state_by_kind[(t['kind'],t.get('status','unknown'))]+=1
 # Build the frozen E1 index and exact recovery-to-frozen-cell join.
 e1p,e1h=str(src['e1']),before['e1']; e1map={x['key']:x for x in e1}
 e1class={'successful_test_evaluation':'successful','resource_failure':'scientific_failure',
 'supervisor_terminal_failure_without_cell_completion':'scientific_failure','scientific_model_or_support_failure':'unsupported'}
 rows=[]
 for x in e1:
  c=x['classification']
  if c not in e1class:raise SystemExit('unrecognized frozen E1 classification '+c)
  rows.append(row(e1class[c],index_key='e1_frozen:'+x['key'],native_key=x['key'],experiment=1,group='E1_frozen',
   budget=x['budget'],rep=x['repetition'],method=x['method'],status_native=c,outcome_native=x['manifest_status'],
   failure_subtype=c if c in ('resource_failure','supervisor_terminal_failure_without_cell_completion') else '',
   balanced_accuracy=x['balanced_accuracy'],coverage=x['coverage'],mean_set_size=x['mean_set_size'],e1_classification=c,
   e1_manifest_status=x['manifest_status'],source_path=str(src['e1']),source_sha256=e1h,record_sha256=sha(canon(x).encode())))
 if Counter(x['classification'] for x in e1)!=Counter({'successful_test_evaluation':674,'resource_failure':55,'supervisor_terminal_failure_without_cell_completion':26,'scientific_model_or_support_failure':10}):
  raise SystemExit('frozen E1 classification counts changed')
 recmap={'successful_test_evaluation':'successful','failed':'scientific_failure','user_stopped':'user_stopped','not_attempted_user_stopped':'not_attempted_user_stopped'}
 for x in rec:
  frozen=e1map.get(x['key'])
  if frozen is None:raise SystemExit('recovery key does not join frozen E1: '+x['key'])
  state=recmap.get(x['recovery_status'])
  if state is None:raise SystemExit('unrecognized recovery state '+x['recovery_status'])
  rows.append(row(state,index_key='e1_recovery:'+x['key'],native_key=x['key'],experiment=1,group='E1_recovery_stopped_early_user_request',
   budget=frozen['budget'],rep=frozen['repetition'],method=frozen['method'],status_native=x['recovery_status'],
   outcome_native=x['recovery_status'],failure_subtype='retry_failure' if state=='scientific_failure' else '',
   e1_classification=x['original_classification'],recovery_status=x['recovery_status'],stop_reason=clean(x['stop_reason']),
   source_path=str(src['recovery']),source_sha256=before['recovery'],record_sha256=sha(canon(x).encode())))
 # E2 retains original/reconstructed/unavailable roles and signed differences from the verified table.
 key=lambda x:(x['family_set'],x['budget'],x['repetition'],x['method'])
 amap={key(x):x for x in e2a};dmap={key(x):x for x in e2d};missing={(x['budget'],x['repetition'],x['method']):x for x in e2m}
 if len(amap)!=270 or len(dmap)!=185:raise SystemExit('E2 join keys are not unique')
 for x in e2:
  k=key(x);a=amap.get(k);d=dmap.get(k)
  if a is None:raise SystemExit('E2 availability row missing '+str(k))
  if x['provenance']=='E2_reconstructed_fit' and d is None:raise SystemExit('reconstructed E2 difference record missing '+str(k))
  state={'fidelity_complete':'successful','unavailable':'unavailable_dependency'}.get(x['fidelity_status'])
  if not state:raise SystemExit('unrecognized E2 fidelity state '+str(k))
  m=missing.get((x['budget'],x['repetition'],x['method'])) if x['family_set']=='primary' else None
  native='e2/'+x['family_set']+'/n_'+x['budget']+'/rep_'+x['repetition']+'/'+x['method']
  rows.append(row(state,index_key='e2:'+native,native_key=native,native_key_origin='derived_from_E2_dimensions',
   experiment=2,group='E2_primary' if x['family_set']=='primary' else 'E2_classical_reference',family_set=x['family_set'],
   budget=x['budget'],rep=x['repetition'],method=x['method'],status_native=x['fidelity_status'],outcome_native=state,
   availability_reason=clean(a.get('e2_availability','')),balanced_accuracy=x['balanced_accuracy'],fidelity=x['fidelity'],
   fidelity_status=x['fidelity_status'],model_provenance=x['provenance'],reproduction_gate=x['reproduction_gate'],
   classification_source=x['classification_source'],classification_difference_flag=x['reproduction_gate']=='classification_not_reproduced',
   signed_difference=d.get('signed_difference','') if d else '',absolute_difference=d.get('absolute_difference','') if d else '',
   exact_accuracy_match=d.get('exact_float_match','') if d else '',e1_classification=(m or a).get('classification',a.get('e1_classification','')),
   e1_manifest_status=(m or a).get('status',a.get('e1_status','')),pipeline_available=a.get('pipeline_available',''),
   saved_test_predictions_available=a.get('saved_test_predictions_available',''),roles_available=a.get('roles_available',''),
   e2_availability=a.get('e2_availability',''),source_path=str(src['e2']),source_sha256=before['e2'],
   record_sha256=sha(canon(x).encode()),secondary_path=str(src['e2a']),secondary_sha256=before['e2a'],
   tertiary_path=str(src['e2d'] if d else (src['e2m'] if m else '')),
   tertiary_sha256=before['e2d'] if d else (before['e2m'] if m else ''),reason=clean(m.get('error','')) if m else ''))
 e2_prov=Counter(x['provenance'] for x in e2)
 e2_diff=sum(x['reproduction_gate']=='classification_not_reproduced' for x in e2)
 e2_states=Counter((x['family_set'],x['fidelity_status']) for x in e2)
 if e2_prov!=Counter({'E2_reconstructed_fit':185,'original_saved_fit':43,'unavailable':42}) or e2_diff!=31:
  raise SystemExit('E2 provenance/difference counts changed')
 if e2_states!=Counter({('primary','fidelity_complete'):108,('primary','unavailable'):42,('classical_reference','fidelity_complete'):120}):
  raise SystemExit('frozen E2 primary/classical coverage counts changed')
 # Frozen later budgets and input manifest provenance.
 budget_source={e:(str(manifests[e]),manifest_sha[e],budgets[e]) for e in manifests}
 # Read-only SQLite status is authoritative; master-index is an enriched observation only.
 mismatch=0
 mismatch_all=sum(1 for _,t in all_records if t.get('key') in mp and (str(t.get('status',''))!=str(mp[t['key']].get('status','')) or str(t.get('outcome') or '')!=str(mp[t['key']].get('outcome') or '')))
 for raw,t in later:
  m=mp.get(t['key'],{}); liveproof=kernel_process_proven(t,runtime_root=runtime); state=normalize_state(t.get('status'),t.get('outcome'),liveproof)
  mismatch += int(str(t.get('status',''))!=str(m.get('status','')) or str(t.get('outcome') or '')!=str(m.get('outcome') or ''))
  rp=resource_projection(t,m);e=int(t['experiment']);attempt=attempt_projection(m)
  code=m.get('actual_engine_code_sha256') or m.get('planned_execution_code_sha256') or {}
  dependencies=compact(t.get('dependencies') or [])
  # No aliases are described as new fits; provenance names the alias/fit reference explicitly.
  prov=model_provenance(t,m)
  rows.append(row(state,index_key=t['key'],native_key=t['key'],experiment=e,group=f'E{e}_later_experiment',
   task_kind=t.get('kind',''),budget=budgets[e],budget_source_path=budget_source[e][0],budget_source_sha256=budget_source[e][1],
   rep=t.get('rep',''),method=t.get('method',''),condition=t.get('condition',''),route=t.get('route',''),
   target_class=t.get('target_class',''),ratio=t.get('ratio',''),mechanism=t.get('mechanism',''),rate=t.get('rate',''),
   model_provenance=prov,status_native=t.get('status',''),outcome_native=t.get('outcome') or '',
   liveproof=liveproof,failure_subtype=m.get('failure_evidence_type') or m.get('failure_subtype') or '',
   availability_reason=clean(m.get('reason') or t.get('reason') or '') if state=='unavailable_dependency' else '',
   attempt_ref=compact(attempt) if attempt else '',dependencies=dependencies,resource_profile=compact(rp),
   resource_profile_source=rp.get('resource_profile_source') or rp.get('admission_profile_source') or '',
   admission_profile_id=rp.get('admission_profile_id',''),admission_reservation_bytes=rp.get('admission_reservation_bytes',''),
   worker_memory_limit_gib=rp.get('worker_memory_limit_gib',''),
   worker_admission_reservation_gib=rp.get('worker_admission_reservation_gib',''),
   dataset_sha=m.get('dataset_manifest_sha256',''),config_sha=m.get('configuration_sha256',''),
   plan_sha=m.get('frozen_plan_sha256',''),code_sha=compact(code),observed_utc=t.get('observed_utc') or m.get('observed_utc',''),
   reason=clean(m.get('reason') or t.get('reason') or ''),
   source_path=str(db)+'#read-only-consistent-snapshot',source_sha256='',record_sha256=sha(canon(t).encode()),
   secondary_path=str(src['master']),secondary_sha256=master_sha,meta_path=str(src['master']),meta_sha256=master_sha,
   master_status=m.get('status',''),master_outcome=m.get('outcome',''),
   master_match=(str(t.get('status',''))==str(m.get('status','')) and str(t.get('outcome') or '')==str(m.get('outcome') or ''))))
 # The full canonical transaction snapshot hash is the source SHA, not the mutable SQLite main-file hash.
 for r in rows:
  if r['experiment'] in (3,4,5,6):r['source_sha256']=sqlite_snapshot_sha
 if len(rows)!=3949 or len({r['index_key'] for r in rows})!=len(rows):raise SystemExit('joined row count or composite uniqueness check failed')
 if sum(r['provenance_group']!='E1_recovery_stopped_early_user_request' for r in rows)!=3858:raise SystemExit('main scientific case row count must be 3858')
 if Counter(r['status_normalized'] for r in rows if r['provenance_group']=='E1_recovery_stopped_early_user_request') != Counter({'successful':24,'scientific_failure':10,'user_stopped':2,'not_attempted_user_stopped':55}):raise SystemExit('recovery cutoff accounting changed')
 for e,n in LATER_PLANNED.items():
  if sum(r['experiment']==e for r in rows)!=n:raise SystemExit(f'E{e} planned scientific row count changed')
 # Later status counts are derived; no expected completion totals are frozen in code.
 group_counts=defaultdict(Counter)
 for r in rows:group_counts[r['provenance_group']][r['status_normalized']]+=1
 counts_later=later_status_counts([r for r in rows if r['experiment'] in (3,4,5,6)])
 # Source files must remain byte-stable across the read/build interval.
 after={k:file_sha(v) for k,v in src.items() if k!='db'}
 if before!=after:raise SystemExit('a source file changed during index construction; discard this version')
 # Atomic data publication: immutable version directory -> ready marker -> current pointer.
 fields=list(rows[0]);buf=io.StringIO(newline='');w=csv.DictWriter(buf,fieldnames=fields);w.writeheader();w.writerows(rows)
 csv_bytes=buf.getvalue().encode('utf-8');csvp=output/'OVERALL_SCIENTIFIC_CASE_INDEX.csv';atomic_bytes(csvp,csv_bytes)
 summary={'schema':'lamost-overall-case-index/2','generated_utc':datetime.now(timezone.utc).isoformat(),
  'scope':'companion index; does not alter canonical execution plan/controller/registry',
  'main_scientific_case_rows':3858,'separate_E1_recovery_supplement_rows':91,'combined_rows':len(rows),
  'planned_later_rows_by_experiment':{str(k):v for k,v in LATER_PLANNED.items()},
  'counts_by_group':{g:dict(sorted(c.items())) for g,c in sorted(group_counts.items())},
  'later_current_status_counts':counts_later,'master_scientific_case_status_mismatches_diagnostic_only':mismatch,'master_all_task_status_mismatches_diagnostic_only':mismatch_all,
  'E1_frozen':{'successful':674,'resource_failure':55,'supervisor_terminal_failure_without_cell_completion':26,'unsupported':10},
  'E1_recovery_separate':{'successful':24,'failed':10,'user_stopped_partial':2,'not_attempted_user_stopped':55},
  'E2_primary':{'planned':150,'evaluated':108,'unavailable_missing_model_dependency':42,'reconstruction_accuracy_differences_retained':31,
    'provenance':dict(e2_prov)},
  'E2_classical_reference':{'planned':120,'evaluated':120},
  'sqlite':{'consistent_transaction_selected_case_count':len(later),'canonical_full_task_snapshot_sha256':sqlite_snapshot_sha,
   'source_path':str(db)+'#consistent-read-only-transaction','raw_main_db_file_hash_is_not_used_as_snapshot_identity':True},
  'master_index':{'source_path':str(src['master']),'source_file_sha256':master_sha,'observed_utc':master.get('observed_utc'),
   'used_for':'supplemental attempts/resource metadata and mismatch diagnostics; SQLite status remains authoritative'},
  'actual_worker_inventory':{'observed_source':'all SQLite registry task records plus per-task /proc identity proof',
   'computational_task_state_counts':{f'{k}|{s}':n for (k,s),n in sorted(state_by_kind.items())},
   'kernel_proven_running_worker_tasks_by_kind':dict(live_by_kind),
   'running_registry_worker_rows_without_current_kernel_proof_by_kind':dict(unproven_by_kind),
   'running_workers_without_process_identifiers':running_worker_records,
   'worker_kinds_counted':sorted(worker_kinds),'exported_process_ids_or_command_lines':False},
  'input_sources':{k:{'path':str(v),'sha256':before[k]} for k,v in src.items() if k!='db'},
  'experiment_manifests':{f'E{e}':{'path':str(manifests[e]),'sha256':manifest_sha[e],'budgets':manifests_obj[e]['budgets'],'derived_budget':budgets[e]} for e in manifests},
  'output_csv':{'path':str(csvp),'sha256':sha(csv_bytes),'row_count':len(rows)},
  'builder_script_sha256':file_sha(Path(__file__)),'builder_helper_path':str(Path(__file__).with_name('case_index_helpers.py')),'builder_helper_sha256':file_sha(Path(__file__).with_name('case_index_helpers.py'))}
 summary_bytes=(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode()
 sump=output/'OVERALL_SCIENTIFIC_CASE_INDEX_SUMMARY.json';atomic_bytes(sump,summary_bytes)
 ready={'status':'ready','ready_utc':datetime.now(timezone.utc).isoformat(),'output_directory':str(output),
  'csv_path':str(csvp),'csv_sha256':sha(csv_bytes),'summary_path':str(sump),'summary_sha256':sha(summary_bytes),
  'builder_script_sha256':summary['builder_script_sha256']}
 atomic_json(output/'READY.json',ready)
 ptr={'current_ready_path':str((output/'READY.json').relative_to(publication_base)),
  'ready_sha256':file_sha(output/'READY.json'),'updated_utc':datetime.now(timezone.utc).isoformat()}
 atomic_json(publication_base/'CURRENT.json',ptr)
 return {'rows':len(rows),'main_scientific_case_rows':3858,'current_status_counts':counts_later,
  'csv_path':str(csvp),'csv_sha256':sha(csv_bytes),'summary_path':str(sump),'ready_path':str(output/'READY.json'),
  'master_registry_status_mismatch_diagnostic_only':mismatch,'master_all_task_status_mismatch_diagnostic_only':mismatch_all,
  'running_kernel_proven_workers':dict(live_by_kind),'running_unproven_registry_workers':dict(unproven_by_kind)}
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--root',type=Path,default=Path('/home/ubuntu/lamost_e1_migration_20261023'))
 parser.add_argument('--runtime',type=Path,default=None)
 parser.add_argument('--output',type=Path,required=True,help='new versioned directory beneath runtime/staging/overall_case_index_20261026')
 a=parser.parse_args();root=a.root.resolve();runtime=(a.runtime or root/'runtime_20261025').resolve()
 print(json.dumps(build(root,runtime,a.output),indent=2))
if __name__=='__main__':main()

