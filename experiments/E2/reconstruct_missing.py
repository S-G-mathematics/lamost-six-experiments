import csv,datetime,hashlib,json,pathlib,resource,signal,sys,time,traceback,functools
import joblib,numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import balanced_accuracy_score
from threadpoolctl import threadpool_limits
BASE=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
ROOT=BASE/'project'
OUT=BASE/'e2_20261024'/'reconstruction'
sys.path.insert(0,str(ROOT))
from benchmark.engine import FEATURES,load_data,_model_module,_predict_chunks
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1<<20),b''):h.update(x)
 return h.hexdigest()
@functools.lru_cache(maxsize=1)
def get_frame():
 frame,split_col=load_data(ROOT/'lamost_baseline',include_test=False)
 return frame.set_index('sample_id',drop=False),split_col
def run(budget,rep,method):
 src=ROOT/'benchmark/results/e1'/f'rep_{rep}'/f'n_{budget}'/method
 done=json.loads((src/'complete.json').read_text())
 if done.get('status')!='complete':raise RuntimeError('frozen E1 cell not complete')
 if (src/'pipeline.joblib').exists():raise RuntimeError('original pipeline already available')
 with np.load(src/'role_membership.npz') as z:
  fit_ids=z['fit_ids'].copy();tune_ids=z['tuning_ids'].copy();cal_ids=z['calibration_ids'].copy()
 if len(set(fit_ids.tolist()))!=len(fit_ids):raise RuntimeError('duplicate fit IDs')
 frame,split_col=get_frame()
 fit=frame.loc[fit_ids];tune=frame.loc[tune_ids]
 if fit[split_col].astype(str).str.lower().eq('test').any() or tune[split_col].astype(str).str.lower().eq('test').any():raise RuntimeError('test leakage')
 Xraw=fit[FEATURES].to_numpy(dtype=np.float64)
 imputer=SimpleImputer(strategy='median').fit(Xraw)
 scaler=StandardScaler().fit(imputer.transform(Xraw))
 Xfit=scaler.transform(imputer.transform(Xraw)).astype(np.float64)
 Xtune=scaler.transform(imputer.transform(tune[FEATURES].to_numpy(dtype=np.float64))).astype(np.float64)
 yfit=fit['label_id'].to_numpy(dtype=np.int64);ytune=tune['label_id'].to_numpy(dtype=np.int64)
 seed=271828+(rep-1)*1000+900
 dest=OUT/f'n_{budget}'/f'rep_{rep}'/method
 dest.mkdir(parents=True,exist_ok=True)
 started=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (dest/'started.json').write_text(json.dumps({'started_utc':started,'source_complete_sha256':sha(src/'complete.json'),'source_role_sha256':sha(src/'role_membership.npz'),'selected_params':done['selected_params'],'fit_seed':seed,'status':'reconstructing','provenance':'E2 replacement fit, distinct from frozen E1 artifact'},indent=2)+'\n')
 def alarm(_sig,_frame):raise TimeoutError('E2 reconstruction fit exceeded 180 s')
 signal.signal(signal.SIGALRM,alarm)
 t=time.monotonic()
 try:
  signal.alarm(180)
  with threadpool_limits(limits=1):
   model=_model_module(method).make_model(method,done['selected_params'],seed,n_jobs=1).fit(Xfit,yfit)
 finally:signal.alarm(0)
 seconds=time.monotonic()-t
 with threadpool_limits(limits=1):
  pred,_=_predict_chunks(model,Xtune,50000)
 score=float(balanced_accuracy_score(ytune,pred))
 expected=float(done['best_tuning_balanced_accuracy'])
 joblib.dump({'model':model,'imputer':imputer,'scaler':scaler,'params':done['selected_params'],'seed':seed},dest/'pipeline.joblib',compress=3)
 gate={'status':'reconstructed_tuning_checked','budget':budget,'repetition':rep,'method':method,'fit_seed':seed,'fit_rows':len(fit_ids),'tuning_rows':len(tune_ids),'calibration_rows':len(cal_ids),'fit_seconds':seconds,'selected_fit_tuning_balanced_accuracy':score,'original_best_trial_tuning_balanced_accuracy':expected,'absolute_difference':abs(score-expected),'same_selected_params':True,'source_complete_sha256':sha(src/'complete.json'),'source_role_sha256':sha(src/'role_membership.npz'),'reconstructed_pipeline_sha256':sha(dest/'pipeline.joblib'),'classification_performance_status':'original frozen E1 result not reproduced; cannot attribute original BA to this new fit','reconstructed_not_original':True,'completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 (dest/'reconstruction.json').write_text(json.dumps(gate,indent=2)+'\n')
 print(json.dumps(gate),flush=True)
if __name__=='__main__':
 from benchmark.engine import ExperimentRunner
 get_frame()
 cap=ExperimentRunner._apply_memory_cap(6.0)
 print('MEMORY_CAP',cap,flush=True)
 if sys.argv[1] in ('--batch-shard','--reference-shard'):
  family='primary' if sys.argv[1]=='--batch-shard' else 'classical_reference'
  shard=int(sys.argv[2])
  with (BASE/'e2_20261024'/'E2_artifact_availability_270.csv').open(newline='') as f: rows=list(csv.DictReader(f))
  tasks=[(int(x['budget']),int(x['repetition']),x['method']) for x in rows if x['family_set']==family and x['e2_availability']=='missing_historical_pipeline']
  tasks.sort(key=lambda x:(x[0],x[1],x[2]))
  for b,r,m in tasks[shard::2]:
   dest=OUT/f'n_{b}'/f'rep_{r}'/m
   if (dest/'reconstruction.json').exists():continue
   try:run(b,r,m)
   except Exception as exc:
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'error.json').write_text(json.dumps({'status':'reconstruction_error','error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(),'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2)+'\n')
    print('ERROR',b,r,m,str(exc),flush=True)
 else:
  b,r,m=sys.argv[1:4];run(int(b),int(r),m)
