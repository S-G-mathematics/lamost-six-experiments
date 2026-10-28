from __future__ import annotations
import pathlib,json,sys,os,time,hashlib,traceback,datetime
import numpy as np
R=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'source'/'svm_margin'))
sys.path.insert(1,str(R.parent/'project'))
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(p,obj):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp')
 t.write_text(json.dumps(obj,indent=2,sort_keys=True,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else int(x) if isinstance(x,np.integer) else float(x) if isinstance(x,np.floating) else str(x))+'\n');os.replace(t,p)
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def check_evaluation(task,out,metrics):
 required=['balanced_accuracy','set_size','coverage','per_class']
 if any(k not in metrics for k in required):raise ValueError('evaluation schema lacks metric fields')
 for k in ['balanced_accuracy','coverage']:
  if not 0<=float(metrics[k])<=1:raise ValueError('invalid evaluation '+k)
 if not 0<=float(metrics['set_size'])<=7:raise ValueError('invalid set_size')
 p=out/'test_outcomes.npz'
 if not p.exists():raise ValueError('missing test_outcomes.npz')
 with np.load(R/'cache/test.npz',allow_pickle=False) as z:y=z['y'].astype(int);ids=z['ids']
 with np.load(p,allow_pickle=False) as z:
  for k in ['sample_id','y_pred','set_mask','covered','set_size']:
   if k not in z:raise ValueError('missing outcome '+k)
  pred=z['y_pred'].astype(int);mask=z['set_mask'].reshape(-1).astype(np.uint8);cov=z['covered'].astype(bool);size=z['set_size'].astype(int)
  if not np.array_equal(ids,z['sample_id']):raise ValueError('test sample ID/order mismatch')
 if any(a.shape!=(len(y),) for a in [pred,mask,cov,size]):raise ValueError('outcome row count/shape mismatch')
 if np.any((pred<0)|(pred>6)) or np.any(mask>127):raise ValueError('class order/mask invalid')
 bits=np.unpackbits(mask[:,None],axis=1,bitorder='little')[:,:7]
 expected_cov=bits[np.arange(len(y)),y].astype(bool)
 if not np.array_equal(size,bits.sum(1)) or not np.array_equal(cov,expected_cov):raise ValueError('set bitmask outcomes disagree')
 conf=np.bincount(y*7+pred,minlength=49).reshape(7,7)
 ba=np.mean(np.diag(conf)/conf.sum(1))
 if abs(ba-float(metrics['balanced_accuracy']))>1e-10 or abs(cov.mean()-float(metrics['coverage']))>1e-10 or abs(size.mean()-float(metrics['set_size']))>1e-10:raise ValueError('metric/outcome disagreement')
 if task.get('kind') in {'eval','alias'}:
  with np.load(p,allow_pickle=False) as z:
   if 'fallback_mask' not in z:raise ValueError('selected evaluation lacks required support-fallback diagnostic')
   fallback=z['fallback_mask'].astype(bool)
   if task.get('method') in {'linear_svm','rbf_svm'}:
    for field in ('scores','score_kind','score_class_order','threshold','prediction_rule','nonconformity_rule'):
     if field not in z:raise ValueError('SVM score evidence missing '+field)
    raw_scores=z['scores']
    stored_kind=str(np.asarray(z['score_kind']).item())
    class_order=np.asarray(z['score_class_order'])
    stored_threshold=float(np.asarray(z['threshold']).item())
    if stored_kind!='margin' or metrics.get('score_kind')!='margin' or metrics.get('calibration_score_kind')!='margin':raise ValueError('SVM scores must remain explicitly marked native margins')
    if str(np.asarray(z['prediction_rule']).item())!='argmax_class_score' or metrics.get('prediction_rule')!='argmax_class_score':raise ValueError('SVM prediction rule must be frozen argmax of class scores')
    if str(np.asarray(z['nonconformity_rule']).item())!='negative_margin' or metrics.get('nonconformity_rule')!='negative_margin':raise ValueError('SVM nonconformity rule must be negative margin')
    if raw_scores.dtype!=np.dtype('float64') or raw_scores.shape!=(len(y),7) or not np.isfinite(raw_scores).all():raise ValueError('SVM class scores must be finite float64 N x 7')
    if not np.array_equal(class_order,np.arange(7,dtype=class_order.dtype)):raise ValueError('SVM score class order must be 0..6')
    if stored_threshold!=float(metrics.get('threshold',float('nan'))):raise ValueError('SVM NPZ/evaluation threshold mismatch')
    if not np.array_equal(np.argmax(raw_scores,axis=1),pred):raise ValueError('SVM argmax margin predictions mismatch')
    raw_sets=(-raw_scores)<=stored_threshold
    if not np.array_equal(raw_sets,bits):raise ValueError('SVM margin conformal sets do not match -score threshold rule')
    calibration=out/'calibration.json'
    if not calibration.is_file():raise ValueError('SVM evaluation lacks calibration.json')
    cd=json.loads(calibration.read_text())
    if cd.get('score_kind')!='margin' or cd.get('nonconformity_rule')!='negative_margin' or float(cd.get('threshold',float('nan'))) != stored_threshold:raise ValueError('SVM calibration/evaluation score kind, rule, or threshold mismatch')
    if cd.get('fit_key')!=metrics.get('fit_key') or cd.get('pipeline_sha256')!=metrics.get('pipeline_sha256'):raise ValueError('SVM calibration/evaluation fit or pipeline provenance mismatch')
  if fallback.shape!=(len(y),) or int(fallback.sum())!=int(metrics.get('test_fallback_count',-1)):raise ValueError('fallback diagnostic count mismatch')
  cal_n=int(metrics.get('calibration_n',0))
  if not 0<=int(metrics.get('calibration_fallback_count',-1))<=cal_n:raise ValueError('calibration fallback diagnostic invalid')
 baseline=out/'support_diagnostic_baseline.json'
 if baseline.exists():
  previous=json.loads(baseline.read_text())
  for k in ['balanced_accuracy','coverage','set_size','threshold']:
   if k in previous['evaluation'] and metrics.get(k)!=previous['evaluation'][k]:raise ValueError('diagnostic-only completion changed prior evaluation metric '+k)
  with np.load(previous['outcomes_path'],allow_pickle=False) as old,np.load(p,allow_pickle=False) as new:
   for k in ['sample_id','y_pred','set_mask','covered','set_size']:
    if not np.array_equal(old[k],new[k]):raise ValueError('diagnostic-only completion changed saved '+k)
  metrics['support_diagnostic_completion']={'previous_outcomes_sha256':previous['outcomes_sha256'],'unchanged_predictions_and_sets_verified':True,'classifier_refitted':False}
 metrics['confusion_matrix']=conf.tolist();metrics['test_n']=len(y)
 metrics['task_key']=task['key'];metrics['experiment']=task['experiment'];metrics['repetition']=task['rep']
 atomic(out/'evaluation.json',metrics)
 files={p.name:sha(p),'evaluation.json':sha(out/'evaluation.json')}
 if task.get('method') in {'linear_svm','rbf_svm'}:files['calibration.json']=sha(out/'calibration.json')
 return files
def validate(task,result):
 out=R/'artifacts'/task['key'];kind=task['kind'];files={}
 status=result.get('status')
 if status not in ['successful','success']:return {}
 if kind=='fit':
  import joblib
  p=out/'pipeline.joblib';s=out/'selection.json'
  if not p.exists() or not s.exists():raise ValueError('fit missing pipeline or selection')
  pipe=joblib.load(p);sel=json.loads(s.read_text())
  params=sel.get('selected_params',sel.get('params'))
  if params is None or pipe.get('params')!=params:raise ValueError('pipeline/selection mismatch')
  if not all(k in pipe for k in ['model','imputer','scaler','seed','training_ids_sha256']):raise ValueError('fit provenance/preprocessing incomplete')
  files={p.name:sha(p),s.name:sha(s)}
 elif kind in ['eval','ensemble']:
  met=result.get('evaluation')
  if met is None:
   met=result.get('result',{})
   if 'evaluation' in met:met=met['evaluation']
  files=check_evaluation(task,out,met)
 elif kind in ['generate','e4_cohort','e4_treatment','e4_append','e5_corruption']:
  p=out/'data.npz'
  with np.load(p,allow_pickle=False) as z:
   X=z['X'];y=z['y']
   if X.ndim!=2 or X.shape[1]!=6 or y.shape!=(len(X),) or np.any((y<0)|(y>6)) or np.isinf(X).any():raise ValueError('invalid training artifact shape/labels')
   if kind=='generate' and task.get('n_rows') and len(y)!=int(task['n_rows']):raise ValueError('wrong generated row count')
   if kind=='generate' and not np.isfinite(X).all():raise ValueError('generated nonfinite values')
   if kind=='e4_cohort':
    if len(y)!=80000 or 'ids' not in z or len(np.unique(z['ids']))!=80000:raise ValueError('invalid E4 cohort identities/count')
    with np.load(R/'cache/roles'/f"rep_{task['rep']}.npz",allow_pickle=False) as role:
     if np.intersect1d(z['ids'],np.concatenate([role['tuning_ids'],role['calibration_ids']])).size:raise ValueError('E4 role leakage')
   if kind=='e5_corruption' and len(y)!=80000:raise ValueError('invalid E5 fit row count')
  files={p.name:sha(p)}
 elif kind=='alias':
  p=out/'evaluation.json'
  if not p.exists():raise ValueError('alias missing evaluation')
  if task.get('method') in {'linear_svm','rbf_svm'}:
   metrics=json.loads(p.read_text())
   files=check_evaluation(task,out,metrics)
   ref=out/'artifact_ref.json'
   if not ref.is_file():raise ValueError('SVM alias missing artifact_ref.json')
   refdata=json.loads(ref.read_text());srcdir=R/'artifacts'/refdata.get('source_key','')
   src_eval=srcdir/'evaluation.json'
   if not src_eval.is_file() or sha(src_eval)!=refdata.get('source_evaluation_sha256'):raise ValueError('SVM alias source evaluation hash mismatch')
   for name in ('test_outcomes.npz','calibration.json'):
    srcfile=srcdir/name; dstfile=out/name; stem=name.replace('.','_')
    if not srcfile.is_file() or sha(srcfile)!=refdata.get('source_'+stem+'_sha256') or sha(dstfile)!=refdata.get('alias_'+stem+'_sha256') or sha(srcfile)!=sha(dstfile):raise ValueError('SVM alias source/target artifact byte identity failed: '+name)
   if metrics.get('fit_key')!=json.loads((out/'calibration.json').read_text()).get('fit_key'):raise ValueError('SVM alias fit provenance mismatch')
   files[ref.name]=sha(ref)
  else: files={p.name:sha(p)}
 validation={'status':'validated','task_key':task['key'],'observed_utc':now(),'files':files,'code_sha256':sha(pathlib.Path(__file__)),'bootstrap':False}
 atomic(out/'validation.json',validation)
 return validation
def execute(task):
 out=R/'artifacts'/task['key'];out.mkdir(parents=True,exist_ok=True)
 kind=task['kind']
 if kind=='alias':
  srcdir=R/'artifacts'/task['source_key']; src=srcdir/'evaluation.json'
  if not src.exists():return {'status':'unavailable_dependency','reason':'source evaluation unavailable','source_key':task['source_key']}
  x=json.loads(src.read_text());x.update({'task_key':task['key'],'experiment':task['experiment'],'compute_reused':True,'reused_from':task['source_key']})
  ref={'source_key':task['source_key'],'source_evaluation_sha256':sha(src)}
  atomic(out/'evaluation.json',x)
  if task.get('method') in {'linear_svm','rbf_svm'}:
   import shutil
   for name in ('test_outcomes.npz','calibration.json'):
    source=srcdir/name
    if not source.is_file():raise ValueError('SVM alias source missing '+name)
    shutil.copy2(source,out/name);ref['source_'+name.replace('.','_')+'_sha256']=sha(source);ref['alias_'+name.replace('.','_')+'_sha256']=sha(out/name)
  atomic(out/'artifact_ref.json',ref)
  return {'status':'successful','result':x}
 if task.get('train_key'):task['train_path']=str(R/'artifacts'/task['train_key']/'data.npz')
 if task.get('selection_key'):task['selection_source']=str(R/'artifacts'/task['selection_key'])
 if kind in ['fit','eval','generate']:
  import science
  return science.execute(task,R)
 if kind.startswith('e4_') or kind=='e5_corruption':
  import cohorts
  return cohorts.execute(task,R)
 if kind=='ensemble':
  import ensemble
  return ensemble.execute(task,R)
 raise ValueError('unknown task kind '+kind)
def main():
 request=pathlib.Path(sys.argv[1]);cfg=json.loads(request.read_text());task=cfg['task'];resultfile=pathlib.Path(cfg['result_path'])
 started=now()
 try:
  result=execute(task)
  if result.get('status')=='success':result['status']='successful'
  result['validation']=validate(task,result)
 except BaseException as exc:
  result={'status':'operationally_invalid','reason':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()}
 result.update({'key':task['key'],'controller_attempt_id':cfg['attempt_id'],'worker_pid':os.getpid(),'started_utc':started,'finished_utc':now()})
 atomic(resultfile,result)
if __name__=='__main__':main()
