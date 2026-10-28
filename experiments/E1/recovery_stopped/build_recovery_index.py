import pathlib as _stop_pathlib
if _stop_pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e1_recovery_20261024/RECOVERY_CUTOFF.json').exists():
    raise SystemExit('E1 recovery disabled by user stop; no further E1 jobs')
import json,pathlib,collections,datetime,hashlib
base=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
root=base/'project';rec=base/'e1_recovery_20261024'
report=json.loads((root/'benchmark/results/e1_report_validated_no_bootstrap.json').read_text())
rows=[]
for old in report['cells']:
 if old['classification']=='successful_test_evaluation':continue
 method=old['method'];budget=old['budget'];rep=old['repetition']
 key=f'n_{budget}/rep_{rep}/{method}'
 if method=='arf' and budget==1000 and rep==1:
  out=rec/'arf_1000_rep1'
 elif method=='extra_trees' and budget==100000 and rep==3:
  out=rec/'extra_trees_100000_rep3'
 elif method=='arf' and old['classification']=='scientific_model_or_support_failure':
  out=rec/'small_arf_cells'/method/f'n_{budget}'/f'rep_{rep}'
 elif method=='arf':
  out=rec/'arf_cells'/method/f'n_{budget}'/f'rep_{rep}'
 else:
  out=rec/'nonarf_cells'/method/f'n_{budget}'/f'rep_{rep}'
 row={'key':key,'original_classification':old['classification'],'original_status':old['status'],'recovery_output':str(out) if out else None,'recovery_status':'queued'}
 if method=='arf' and old['classification']=='scientific_model_or_support_failure':
  pilot=rec/'arf_minclass_variant/pilot_results/e1/rep_1/n_100/arf'
  if not (pilot/'complete.json').exists():
   pilot_manifest=pilot/'manifest.json'
   if pilot_manifest.exists() and json.loads(pilot_manifest.read_text()).get('status')=='failed':
    row['recovery_status']='unsupported_after_minclass_feasibility_failure'
   else:
    row['recovery_status']='awaiting_minclass_feasibility'
 if out:
  cell=out/'results/e1'/f'rep_{rep}'/f'n_{budget}'/method
  complete=cell/'complete.json';manifest=cell/'manifest.json'
  if complete.exists():
   result=json.loads(complete.read_text())
   row['recovery_status']='successful_test_evaluation'
   row['metrics']={'balanced_accuracy':result.get('test_metrics',{}).get('balanced_accuracy'),'coverage':result.get('test_coverage'),'mean_prediction_set_size':result.get('mean_prediction_set_size')}
  elif manifest.exists():
   data=json.loads(manifest.read_text())
   row['recovery_status']=data.get('status','unknown')
   row['error']=data.get('error')
  if manifest.exists():
   original=root/'benchmark/results/e1'/f'rep_{rep}'/f'n_{budget}'/method/'manifest.json'
   a=json.loads(original.read_text())['roles']['roles'];b=json.loads(manifest.read_text())['roles']['roles']
   row['same_role_membership']=all(a[x]['ids_sha256']==b[x]['ids_sha256'] for x in ['fit','tune','calibration'])
 if method!='arf':
  final=rec/'finalized_nonarf_cells'/method/f'n_{budget}'/f'rep_{rep}'/'finalization.json'
  if final.exists():
   result=json.loads(final.read_text())
   row['recovery_status']='successful_test_evaluation_from_saved_pipeline'
   row['metrics']={'balanced_accuracy':result['balanced_accuracy'],'coverage':result['coverage'],'mean_prediction_set_size':result['mean_prediction_set_size']}
   row['saved_pipeline_finalization']=str(final)
 rows.append(row)
assert len(rows)==91
status=collections.Counter(r['recovery_status'] for r in rows)
data={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_frozen_report':str(root/'benchmark/results/e1_report_validated_no_bootstrap.json'),'source_frozen_report_sha256':hashlib.sha256((root/'benchmark/results/e1_report_validated_no_bootstrap.json').read_bytes()).hexdigest(),'recovery_protocol':'separate EC2 output; trial timeout 600 s and 10 GiB memory headroom, versus frozen E1 180 s and 6 GiB; original successful cells and frozen results preserved','status_counts':dict(status),'cells':rows,'small_support_variant_pilot':{'cell':'n_100/rep_1/arf','source':str(rec/'arf_small_support_variant'),'change':'min_samples_leaf=1 below five per-class fit observations; one development trial','result':'failed: non-finite FORDE parameters'}}
dest=rec/'recovery_index.json';tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n');tmp.replace(dest)
print(json.dumps({'index':str(dest),'status_counts':dict(status)},sort_keys=True))
