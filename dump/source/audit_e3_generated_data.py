"""Read-only E3 synthetic-data identity/count audit; no model loading or inference."""
import pathlib,json,hashlib,datetime,collections,numpy as np
R=pathlib.Path(__file__).resolve().parents[1]
def file_sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def array_sha(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
reg=json.loads((R/'registry.json').read_text());tasks={t['key']:t for t in reg['tasks']};rows=[];issues=[];limits=[]
gens=[t for t in tasks.values() if t.get('experiment')==3 and t.get('kind')=='generate']
assert len(gens)==15
for t in sorted(gens,key=lambda t:t['key']):
 p=R/'artifacts'/t['key']/'data.npz';before=file_sha(p)
 with np.load(R/'cache/roles'/f"rep_{t['rep']}.npz",allow_pickle=False) as z:real=np.bincount(z['y_fit'].astype(int),minlength=7)
 with np.load(p,allow_pickle=False) as z:
  X=z['X'];y=z['y'].astype(np.int64)
  shape=list(X.shape);counts=np.bincount(y,minlength=7)
  if X.shape!=(400000,6) or y.shape!=(400000,) or not np.isfinite(X).all() or not np.array_equal(counts,5*real):issues.append({'key':t['key'],'issue':'synthetic_shape_finiteness_or_allocation'})
  xhash=array_sha(X.astype(np.float64,copy=False));yhash=array_sha(y)
  del X,y
 learners=[q for q in tasks.values() if q.get('experiment')==3 and q.get('kind')=='fit' and q.get('route')=='synthetic' and q.get('train_key')==t['key']]
 if len(learners)!=3 or {q['method'] for q in learners}!={'logistic','random_forest','hist_gb'}:issues.append({'key':t['key'],'issue':'shared_three_learner_plan_identity'})
 checks=[]
 for q in sorted(learners,key=lambda a:a['method']):
  state=q.get('outcome')
  if state=='successful':
   fitp=R/'artifacts'/q['key']/'fit_result.json';doc=json.loads(fitp.read_text());res=doc.get('result',{})
   xs=res.get('training_X_sha256');ys=res.get('training_y_sha256');src=res.get('source_sha256')
   if xs and ys:
    if xs!=xhash or ys!=yhash:issues.append({'key':q['key'],'issue':'recorded_training_array_hash_mismatch'})
    check='recorded_training_arrays_match_actual_shared_dataset'
   else:
    check='optional_per_array_hash_not_exposed_but_whole_dataset_hash_verified'
    limits.append({'key':q['key'],'limitation':check,'fit_result_sha256':file_sha(fitp)})
   if src!=before:issues.append({'key':q['key'],'issue':'recorded_training_file_hash_mismatch'})
   checks.append({'fit_key':q['key'],'outcome':state,'check':check,'recorded_source_file_sha256':src,'fit_result_sha256':file_sha(fitp)})
  else:checks.append({'fit_key':q['key'],'outcome':state,'check':'no_successful_selected_classifier_due_to_terminal_fit_failure'})
 if file_sha(p)!=before:issues.append({'key':t['key'],'issue':'data_changed_during_readonly_audit'})
 rows.append({'generation_key':t['key'],'rep':t['rep'],'generator':t.get('generator') or t.get('method'),'dataset_sha256':before,'shape':shape,'actual_class_counts':counts.tolist(),'real_fit_counts':real.tolist(),'allocation_rule':'exactly5times_each_real_fit_class_count; largest-remainder protocol yields integers at5x','training_X_float64_sha256':xhash,'training_y_int64_sha256':yhash,'learner_source_checks':checks})
out={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'all15E3 generateddatasets andall45plannedsynthetic-learnertraininglinks; no fits or model loads','source_sha256':file_sha(pathlib.Path(__file__)),'registry_observed_utc':reg['observed_utc'],'generated_datasets':len(rows),'generated_examples':15*400000,'planned_synthetic_learner_links':sum(len(r['learner_source_checks']) for r in rows),'successful_learner_links':sum(x['outcome']=='successful' for r in rows for x in r['learner_source_checks']),'successful_whole_dataset_hash_bindings':sum(x['outcome']=='successful' and x.get('recorded_source_file_sha256')==r['dataset_sha256'] for r in rows for x in r['learner_source_checks']),'issue_count':len(issues),'issues':issues,'diagnostic_limitations':limits,'results':rows,'status':'passed' if not issues else 'failed','bootstrap':False}
p=R/'reports/engineering_audits/E3_GENERATED_DATA_IDENTITY_AUDIT_20261026.json';p.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:out[k] for k in ['generated_utc','generated_datasets','generated_examples','planned_synthetic_learner_links','successful_learner_links','issue_count','diagnostic_limitations','status']}))
if issues:raise SystemExit(1)
