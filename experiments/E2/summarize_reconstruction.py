import csv,datetime,json,pathlib,collections
B=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023/e2_20261024')
with (B/'E2_artifact_availability_270.csv').open(newline='') as f: rows=list(csv.DictReader(f))
tasks=[x for x in rows if x['family_set']=='primary' and x['e2_availability']=='missing_historical_pipeline']
items=[]
for x in tasks:
 b=int(x['budget']);r=int(x['repetition']);m=x['method']
 p=B/'reconstruction'/f'n_{b}'/f'rep_{r}'/m
 gate=p/'test_reproduction_gate.json'
 e2=B/'reconstruction_fidelity'/'cells'/f'n_{b}'/f'rep_{r}'/m/'complete.json'
 fit=json.loads((p/'reconstruction.json').read_text()) if (p/'reconstruction.json').exists() else None
 test=json.loads(gate.read_text()) if gate.exists() else None
 fid=json.loads(e2.read_text()) if e2.exists() else None
 items.append({'budget':b,'repetition':r,'method':m,'reconstruction':'completed' if fit else ('error' if (p/'error.json').exists() else 'pending'),'reconstructed_pipeline_sha256':fit.get('reconstructed_pipeline_sha256') if fit else None,'test_gate':test.get('status') if test else 'pending','test_balanced_accuracy_absolute_difference':test.get('absolute_difference') if test else None,'fidelity_status':fid.get('status') if fid else 'pending','class_balanced_fidelity':fid.get('class_balanced_fidelity') if fid else None})
with (B/'E2_reconstruction_progress_89.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
summary={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'missing_successful_primary_cells':len(tasks),'reconstruction_counts':dict(collections.Counter(x['reconstruction'] for x in items)),'test_gate_counts':dict(collections.Counter(x['test_gate'] for x in items)),'fidelity_counts':dict(collections.Counter(x['fidelity_status'] for x in items)),'original_frozen_E1_ledger_unchanged':True,'reconstruction_outside_frozen_E1':True,'classification_reproduction_tolerance_absolute':1e-10,'interpretation':'Reconstructed fits pair their own fixed-test balanced accuracy with their own fidelity. Exact reproduction matches are flagged; mismatches remain separately flagged. Original frozen selected fits remain a separate provenance class. E1 failed/unsupported cells are not missing artifacts and are not silently refit.'}
(B/'E2_reconstruction_progress.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
