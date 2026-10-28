import argparse,csv,datetime,hashlib,importlib.metadata,json,pathlib,sys,time,traceback
import joblib,numpy as np,pandas as pd
from sdmetrics.reports.single_table import QualityReport
BASE=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
ROOT=BASE/'project'
sys.path.insert(0,str(ROOT))
from benchmark.engine import FEATURES,load_data
BUDGETS=[3000,10000,30000,100000,300000,1000000]
PRIMARY=['gmm','copula','arf','kde','chow_liu']
REFERENCE=['gaussian_nb','shared_diagonal','lda','qda']
METADATA={'columns':{name:{'sdtype':'numerical'} for name in FEATURES}}
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def seed(*items):
 payload='|'.join(map(str,items)).encode()
 return int.from_bytes(hashlib.sha256(payload).digest()[:4],'big')
def write_json(path,obj):
 tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_text(json.dumps(obj,indent=2,sort_keys=True,default=str)+chr(10))
 tmp.replace(path)
def run_cell(audit,frame_index,budget,rep,method,out):
 key=(budget,rep,method)
 row=audit[key]
 if row['e2_availability']!='ready':raise RuntimeError('E2 cell not ready: '+str(key))
 source=pathlib.Path(row['path'])
 dest=out/'cells'/f'n_{budget}'/f'rep_{rep}'/method
 dest.mkdir(parents=True,exist_ok=True)
 if (dest/'complete.json').exists():
  print('SKIP_COMPLETE',key,flush=True);return
 role_file=source/'role_membership.npz'
 with np.load(role_file) as z:
  cal_ids=z['calibration_ids']
 if len(cal_ids)!=len(set(cal_ids.tolist())):raise RuntimeError('duplicate calibration IDs')
 if not frame_index.index.is_unique:raise RuntimeError('baseline sample IDs not unique')
 cal=frame_index.loc[cal_ids]
 source_manifest=json.loads((source/'manifest.json').read_text())
 expected_counts=source_manifest['roles']['roles']['calibration']['counts']
 observed=np.bincount(cal['label_id'].to_numpy(dtype=np.int64),minlength=7).tolist()
 if observed!=expected_counts:raise RuntimeError('calibration class counts disagree with frozen manifest')
 pipe=pathlib.Path(row['pipeline_override_path']) if row.get('pipeline_override_path') else source/'pipeline.joblib'
 if sha(pipe)!=row['pipeline_sha256']:raise RuntimeError('saved pipeline hash changed')
 obj=joblib.load(pipe)
 model=obj['model'];scaler=obj['scaler']
 if not hasattr(model,'sample_class'):raise RuntimeError('saved model cannot sample class')
 reference_dir=out/'references'/f'n_{budget}'/f'rep_{rep}'
 reference_dir.mkdir(parents=True,exist_ok=True)
 class_records=[]
 for c in range(7):
  ids=np.sort(cal_ids[cal['label_id'].to_numpy(dtype=np.int64)==c])
  n=min(2000,len(ids))
  ref_seed=seed('e2','real_reference',budget,rep,c,271828)
  selected=np.sort(np.random.default_rng(ref_seed).choice(ids,size=n,replace=False)) if n else np.asarray([],dtype=ids.dtype)
  ref_file=reference_dir/f'class_{c}_ids.npz'
  if ref_file.exists():
   with np.load(ref_file) as saved:
    if not np.array_equal(saved['sample_id'],selected):raise RuntimeError('reference sample drift')
  else:np.savez_compressed(ref_file,sample_id=selected)
  record={'class_id':c,'real_available':len(ids),'diagnostic_n':n,'low_precision':n<20,'real_reference_ids_sha256':sha(ref_file),'reference_seed':ref_seed,'status':'pending'}
  class_dir=dest/f'class_{c}';class_dir.mkdir(exist_ok=True)
  if n<2:
   record['status']='unavailable_fewer_than_two_real_rows'
   write_json(class_dir/'result.json',record);class_records.append(record);continue
  real=frame_index.loc[selected,FEATURES].to_numpy(dtype=np.float64)
  if np.any(np.sum(np.isfinite(real),axis=0)<2):
   record['status']='unavailable_insufficient_finite_feature_values'
   write_json(class_dir/'result.json',record);class_records.append(record);continue
  syn_seed=seed('e2','synthetic',budget,rep,method,c,271828)
  record['synthetic_seed']=syn_seed
  try:
   synthetic_scaled=np.asarray(model.sample_class(c,n,syn_seed),dtype=np.float64)
   if synthetic_scaled.shape!=(n,6) or not np.isfinite(synthetic_scaled).all():
    raise ValueError('invalid generated sample shape or nonfinite values')
   synthetic=scaler.inverse_transform(synthetic_scaled)
   if synthetic.shape!=(n,6) or not np.isfinite(synthetic).all():
    raise ValueError('invalid native-scale synthetic values')
   np.savez_compressed(class_dir/'diagnostic_samples.npz',real_sample_id=selected,real_native=real,synthetic_native=synthetic)
   real_df=pd.DataFrame(real,columns=FEATURES)
   synthetic_df=pd.DataFrame(synthetic,columns=FEATURES)
   quality=QualityReport()
   quality.generate(real_df,synthetic_df,METADATA,verbose=False)
   overall=float(quality.get_score())
   props=quality.get_properties()
   scores={str(x['Property']):float(x['Score']) for x in props.to_dict('records')}
   for property_name,filename in [('Column Shapes','column_shapes.csv'),('Column Pair Trends','column_pair_trends.csv')]:
    quality.get_details(property_name).to_csv(class_dir/filename,index=False)
   record.update({'sdmetrics_score':overall,'column_shapes_score':scores.get('Column Shapes'),'column_pair_trends_score':scores.get('Column Pair Trends'),'synthetic_sample_sha256':sha(class_dir/'diagnostic_samples.npz')})
   if not all(np.isfinite(x) for x in [overall,record['column_shapes_score'],record['column_pair_trends_score']]):
    record['status']='unavailable_undefined_quality_property'
   else:record['status']='valid_low_precision' if n<20 else 'valid'
  except Exception as exc:
   record['status']='unavailable_generation_or_quality_error'
   record['error']=type(exc).__name__+': '+str(exc)
   record['traceback']=traceback.format_exc()
  write_json(class_dir/'result.json',record)
  class_records.append(record)
 valid=all(x['status'] in ['valid','valid_low_precision'] for x in class_records)
 result={'experiment':2,'budget':budget,'repetition':rep,'method':method,'primary_family':method in PRIMARY,'status':'fidelity_complete' if valid else 'fidelity_unavailable','class_balanced_fidelity':float(np.mean([x['sdmetrics_score'] for x in class_records])) if valid else None,'direct_classification_balanced_accuracy':float(row['e1_balanced_accuracy']) if row.get('e1_balanced_accuracy') else None,'classification_balanced_accuracy_from_frozen_e1':float(row['e1_balanced_accuracy']) if row.get('e1_balanced_accuracy') and not row.get('pipeline_override_path') else None,'class_reports':class_records,'sdmetrics_version':importlib.metadata.version('sdmetrics'),'metadata':METADATA,'source_e1_cell':str(source),'source_pipeline_sha256':row['pipeline_sha256'],'pipeline_provenance':row.get('pipeline_provenance','original_frozen_e1_selected_fit'),'classification_performance_status':row.get('classification_performance_status','frozen_e1_selected_fit'),'classification_source':row.get('classification_source','frozen_e1_test_evaluation'),'original_frozen_e1_balanced_accuracy':float(row['original_e1_balanced_accuracy']) if row.get('original_e1_balanced_accuracy') else None,'reproduction_gate_status':row.get('reproduction_gate_status'),'source_e1_complete_sha256':sha(source/'complete.json'),'calibration_reference_only':True,'matched_diagnostic_size_rule':'min(2000, held-out calibration class rows)','bootstrap':False,'test_based_selection':False,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 write_json(dest/'complete.json',result)
 print('E2_CELL',budget,rep,method,result['status'],result['class_balanced_fidelity'],flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--cell',default=None);p.add_argument('--all-ready',action='store_true');p.add_argument('--all-reference',action='store_true');args=p.parse_args()
 out=BASE/'e2_20261024'
 with (out/'E2_artifact_availability_270.csv').open(newline='',encoding='utf-8') as f:
  rows=list(csv.DictReader(f))
 audit={(int(x['budget']),int(x['repetition']),x['method']):x for x in rows}
 if args.cell:
  budget,rep,method=args.cell.split('/')
  selected=[(int(budget.removeprefix('n_')),int(rep.removeprefix('rep_')),method)]
 elif args.all_ready:
  selected=sorted([k for k,v in audit.items() if v['family_set']=='primary' and v['e2_availability']=='ready'],key=lambda x:(x[0],x[1],PRIMARY.index(x[2])))
 elif args.all_reference:
  selected=sorted([k for k,v in audit.items() if v['family_set']=='classical_reference' and v['e2_availability']=='ready'],key=lambda x:(x[0],x[1],REFERENCE.index(x[2])))
 else:raise SystemExit('choose --cell, --all-ready or --all-reference')
 config={'experiment':2,'source_protocol_sha256':sha(ROOT/'benchmark/protocol_source.txt'),'source_frozen_report_sha256':sha(ROOT/'benchmark/results/e1_report_validated_no_bootstrap.json'),'primary_methods':PRIMARY,'reference_methods':REFERENCE,'budgets':BUDGETS,'repetitions':5,'seed':271828,'sdmetrics_version':importlib.metadata.version('sdmetrics'),'metadata':METADATA,'reference_role':'frozen_E1_calibration','no_test_based_selection':True,'no_bootstrap':True,'no_TSTR':True,'frozen_E1_source_untouched':True,'artifact_audit':str(out/'E2_artifact_availability_270.csv')}
 write_json(out/'E2_CONFIG.json',config)
 frame,split_col=load_data(ROOT/'lamost_baseline',include_test=False)
 if frame[split_col].astype(str).str.lower().eq('test').any():raise RuntimeError('test rows entered E2 fidelity reference frame')
 indexed=frame.set_index('sample_id',drop=False)
 print('E2_REFERENCE_FRAME',len(indexed),'cells',len(selected),flush=True)
 for budget,rep,method in selected:run_cell(audit,indexed,budget,rep,method,out)
if __name__=='__main__':main()
