import csv,hashlib,json,pathlib,sys,traceback,datetime
BASE=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
E2=BASE/'e2_20261024'
sys.path.insert(0,str(E2))
from run_e2_fidelity import load_data,ROOT,run_cell
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return h.hexdigest()
with (E2/'E2_artifact_availability_270.csv').open(newline='') as f:
 audit={(int(x['budget']),int(x['repetition']),x['method']):x for x in csv.DictReader(f)}
frame,split_col=load_data(ROOT/'lamost_baseline',include_test=False)
indexed=frame.set_index('sample_id',drop=False)
out=E2/'reconstruction_fidelity'
for gate_file in sorted((E2/'reconstruction').glob('n_*/rep_*/*/reconstruction.json')):
 gate=json.loads(gate_file.read_text())
 k=(gate['budget'],gate['repetition'],gate['method'])
 if audit[k]['e2_availability']!='missing_historical_pipeline':continue
 if gate['status']!='reconstructed_tuning_checked':continue
 test_gate_file=gate_file.parent/'test_reproduction_gate.json'
 test_gate=json.loads(test_gate_file.read_text()) if test_gate_file.exists() else None
 valid_gate=test_gate is not None and test_gate.get('status') in ('reproduced_original_test_balanced_accuracy','classification_not_reproduced')
 pipe=gate_file.parent/'pipeline.joblib'
 if sha(pipe)!=gate['reconstructed_pipeline_sha256']:raise RuntimeError('reconstruction pipeline hash drift')
 row=dict(audit[k])
 row['e2_availability']='ready'
 row['pipeline_override_path']=str(pipe)
 row['pipeline_sha256']=gate['reconstructed_pipeline_sha256']
 row['pipeline_provenance']='E2_reconstructed_fit_from_frozen_selected_params_and_roles'
 row['classification_performance_status']='reconstructed_test_BA_measured_on_fixed_test' if valid_gate else 'reconstructed_test_BA_pending_or_unavailable'
 row['classification_source']='E2_reconstructed_fit_fixed_test_evaluation' if valid_gate else 'pending'
 row['original_e1_balanced_accuracy']=row['e1_balanced_accuracy']
 row['e1_balanced_accuracy']=test_gate['reconstructed_balanced_accuracy'] if valid_gate else ''
 row['reproduction_gate_status']=test_gate['status'] if test_gate else 'pending'
 existing=out/'cells'/f'n_{k[0]}'/f'rep_{k[1]}'/k[2]/'complete.json'
 if existing.exists():
  record=json.loads(existing.read_text())
  record['direct_classification_balanced_accuracy']=float(test_gate['reconstructed_balanced_accuracy']) if valid_gate else None
  record['classification_balanced_accuracy_from_frozen_e1']=None
  record['original_frozen_e1_balanced_accuracy']=float(row['original_e1_balanced_accuracy'])
  record['classification_performance_status']=row['classification_performance_status']
  record['classification_source']=row['classification_source']
  record['reproduction_gate_status']=row['reproduction_gate_status']
  existing.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
  print('UPDATE_PAIRING',k,flush=True)
  continue
 try:run_cell({k:row},indexed,*k,out)
 except Exception as exc:
  p=out/'errors'/f'{k[0]}_{k[1]}_{k[2]}.json';p.parent.mkdir(parents=True,exist_ok=True)
  p.write_text(json.dumps({'error':str(exc),'traceback':traceback.format_exc(),'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
  print('ERROR',k,str(exc),flush=True)
