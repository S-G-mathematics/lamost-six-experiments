import csv,datetime,hashlib,json,pathlib,signal,sys,time,traceback
import joblib,numpy as np
from sklearn.metrics import balanced_accuracy_score
from threadpoolctl import threadpool_limits
BASE=pathlib.Path('/home/ubuntu/lamost_e1_migration_20261023')
ROOT=BASE/'project'
E2=BASE/'e2_20261024'
sys.path.insert(0,str(ROOT))
from benchmark.engine import FEATURES,load_data,_predict_chunks,ExperimentRunner
frame,split_col=load_data(ROOT/'lamost_baseline',include_test=True)
test=frame[frame[split_col].astype(str).str.lower().eq('test')]
assert len(test)==500000
Xraw=test[FEATURES].to_numpy(dtype=np.float64)
y=test['label_id'].to_numpy(dtype=np.int64)
cap=ExperimentRunner._apply_memory_cap(6.0)
print('TEST_FRAME',len(test),'CAP',cap,flush=True)
with (E2/'E2_artifact_availability_270.csv').open(newline='') as f:
 audit={(int(x['budget']),int(x['repetition']),x['method']):x for x in csv.DictReader(f)}
def timeout(_sig,_frame):raise TimeoutError('E2 reconstruction test gate exceeded 180s')
signal.signal(signal.SIGALRM,timeout)
gate_files=list((E2/'reconstruction').glob('n_*/rep_*/*/reconstruction.json'))
priority={'gmm':0,'copula':1,'chow_liu':2,'kde':3,'arf':4}
gate_files.sort(key=lambda p:(int(p.parent.parent.parent.name.split('_')[1]),priority.get(p.parent.name,9),int(p.parent.parent.name.split('_')[1])))
shard=int(sys.argv[1]) if len(sys.argv)>1 else None
if shard is not None:
 assert shard in (0,1)
 gate_files=gate_files[shard::2]
print('GATE_TASKS',len(gate_files),'SHARD',shard,flush=True)
for gate_file in gate_files:
 gate=json.loads(gate_file.read_text())
 k=(gate['budget'],gate['repetition'],gate['method'])
 out=gate_file.parent/'test_reproduction_gate.json'
 if out.exists():continue
 if audit[k]['e2_availability']!='missing_historical_pipeline':continue
 try:
  obj=joblib.load(gate_file.parent/'pipeline.joblib')
  X=obj['scaler'].transform(obj['imputer'].transform(Xraw))
  started=time.monotonic()
  signal.alarm(180)
  with threadpool_limits(limits=1):
   pred,_=_predict_chunks(obj['model'],X,50000)
  signal.alarm(0)
  score=float(balanced_accuracy_score(y,pred))
  original=float(audit[k]['e1_balanced_accuracy'])
  result={'status':'reproduced_original_test_balanced_accuracy' if abs(score-original)<1e-10 else 'classification_not_reproduced','budget':k[0],'repetition':k[1],'method':k[2],'reconstructed_balanced_accuracy':score,'frozen_e1_balanced_accuracy':original,'absolute_difference':abs(score-original),'test_rows':len(y),'inference_seconds':time.monotonic()-started,'reconstructed_not_original_artifact':True,'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 except Exception as exc:
  signal.alarm(0)
  result={'status':'test_reproduction_gate_error','error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc(),'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
 out.write_text(json.dumps(result,indent=2)+'\n')
 print('TEST_GATE',k,result['status'],result.get('absolute_difference'),flush=True)
