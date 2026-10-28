from __future__ import annotations
import hashlib, json, os, sys, time, tempfile
import fcntl
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from ensemble_maintenance_patch import E6PhaseFailure, E6CachedPhaseFailure, _cached_record, run_phase_with_terminal_failure_cache, execute_with_terminal_classification  # E6_PHASE_FAILURE_TAXONOMY_V1
MEMBERS=('gmm','copula','arf','kde','chow_liu')
def _project(runtime):
    p=Path(runtime).parent/'project'
    if not p.exists(): p=Path('/home/ubuntu/lamost_e1_migration_20261023/project')
    if str(p) not in sys.path: sys.path.insert(0,str(p))
    from benchmark import ensembles,evaluation
    return p,ensembles,evaluation
def _json(path,obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(obj,sort_keys=True,indent=2,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else int(x) if isinstance(x,np.integer) else float(x) if isinstance(x,np.floating) else str(x))+'\n'); os.replace(t,p)
def _sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def _validate_class_order(model,name):
    candidates=[]
    for obj,attr in ((model,'classes_'),(getattr(model,'estimator',None),'classes_'),(model,'class_ids_'),(model,'label_order')):
        value=getattr(obj,attr,None) if obj is not None else None
        if value is not None: candidates.append((attr,np.asarray(value)))
    for attr,value in candidates:
        if value.shape!=(7,) or not np.array_equal(value,np.arange(7)):
            raise ValueError(f'{name} exposes noncanonical class order in {attr}: {value.tolist()}')
    priors=getattr(model,'priors',None)
    if priors is not None and np.asarray(priors).shape!=(7,): raise ValueError(f'{name} prior vector does not contain seven fixed-order classes')
def _posterior(a,name):
    x=np.asarray(a,dtype=np.float64)
    if x.ndim!=2 or x.shape[1]!=7 or not np.isfinite(x).all() or np.any(x<0) or not np.allclose(x.sum(1),1.,atol=1e-6):
        raise ValueError(f'{name}: expected normalized finite nonnegative N x 7 posterior in class order 0..6')
    return x
def _load_npz(path,required):
    if not Path(path).exists(): raise FileNotFoundError(path)
    with np.load(path,allow_pickle=False) as z:
        missing=[k for k in required if k not in z]
        if missing: raise ValueError(f'{path}: missing keys {missing}')
        return {k:z[k].copy() for k in z.files}
def _role_ids(z,role):
    for k in (f'{role}_ids',f'{role.lower()}_ids'):
        if k in z: return np.asarray(z[k])
    return None
def _pipeline_path(runtime,key):
    if not isinstance(key,str) or not key or '..' in Path(key).parts or Path(key).is_absolute(): raise ValueError('unsafe fit dependency key')
    p=(Path(runtime)/'artifacts'/key/'pipeline.joblib').resolve()
    if Path(runtime).resolve() not in p.parents: raise ValueError('fit key escapes runtime artifact directory')
    return p
def _phase_child(conn,pipeline_paths,X,outfile):
    try:
        os.environ.update({"OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1"})
        try:
            from threadpoolctl import threadpool_limits
            threadpool_limits(1)
        except Exception: pass
        import joblib
        X=np.asarray(X,dtype=np.float64); n=len(X); result={}
        for name,path in pipeline_paths.items():
            pipe=joblib.load(path); model=pipe["model"]; pieces=[]
            for start in range(0,n,50000):
                block=X[start:start+50000]
                transformed=pipe["scaler"].transform(pipe["imputer"].transform(block))
                raw=model.score_matrix(transformed) if hasattr(model,"score_matrix") else model.predict_proba(transformed)
                pieces.append(_posterior(raw,f"{name} prediction"))
            result[name]=np.concatenate(pieces,axis=0) if pieces else np.empty((0,7),dtype=float)
        tmp=str(outfile)+f".{os.getpid()}.tmp.npz"
        np.savez_compressed(tmp,**result); os.replace(tmp,outfile)
        conn.send({"status":"success","n":n,"chunk_size":50000})
    except BaseException as exc:
        conn.send({"status":"error","error":f"{type(exc).__name__}: {exc}"})
    finally:
        conn.close()

def _tree_rss_kib(pid):
    rows={}
    for d in Path('/proc').iterdir():
        if not d.name.isdigit(): continue
        try:
            lines=(d/'status').read_text().splitlines(); ppid=int(next(x.split()[1] for x in lines if x.startswith('PPid:'))); rss=int(next(x.split()[1] for x in lines if x.startswith('VmRSS:'))); rows[int(d.name)]=(ppid,rss)
        except Exception: pass
    tree={pid}; changed=True
    while changed:
        changed=False
        for child,(parent,_) in rows.items():
            if parent in tree and child not in tree: tree.add(child); changed=True
    return sum(rows[x][1] for x in tree if x in rows)

def _run_prediction_phase(pipeline_paths,X,outfile,timeout=600,rss_limit_kib=10*1024*1024,grace=30):
    import multiprocessing as mp
    ctx=mp.get_context('fork'); parent,child=ctx.Pipe(duplex=False)
    proc=ctx.Process(target=_phase_child,args=(child,pipeline_paths,np.asarray(X),str(outfile))); proc.start(); child.close()
    started=time.monotonic(); peak=0; reason=None; owner_pid=os.getpid()
    while proc.is_alive():
        # Include this controller worker plus the isolated phase child and descendants.
        peak=max(peak,_tree_rss_kib(owner_pid))
        if peak>rss_limit_kib: reason='rss_limit'; break
        if time.monotonic()-started>timeout: reason='timeout'; break
        proc.join(.25)
    if reason:
        proc.terminate(); proc.join(grace)
        if proc.is_alive(): proc.kill(); proc.join()
    else: proc.join()
    msg=parent.recv() if parent.poll() else {"status":"error","error":f"worker exited {proc.exitcode} without a result"}
    parent.close()
    rec={"seconds":time.monotonic()-started,"peak_tree_rss_kib":peak,"reason":reason,"exit_code":proc.exitcode,"result":msg}
    if reason: raise RuntimeError(f"prediction_{reason}: {rec}")
    if proc.exitcode!=0 or msg.get('status')!='success': raise RuntimeError(f"prediction_phase_failed: {rec}")
    return rec

def _run_prediction_phase_v2(pipeline_paths,X,outfile,*,task,runtime,stage,timeout=600,rss_limit_kib=10*1024*1024,grace=30):
    from e6_phase_supervisor import run_phase
    attempt=task.get('_controller_attempt_id')
    if not isinstance(attempt,str) or not attempt or Path(attempt).name!=attempt:
        raise ValueError('E6-v2 requires controller-injected safe _controller_attempt_id')
    request_path=task.get('_controller_request_path'); request_sha=task.get('_controller_request_sha256')
    worker_sha=task.get('_controller_worker_script_sha256')
    if not isinstance(request_path,str) or not request_path or not isinstance(request_sha,str) or not isinstance(worker_sha,str):
        raise ValueError('E6-v2 requires controller-injected request and worker source identity')
    runtime=Path(runtime).resolve()
    request_file=Path(request_path).resolve()
    if runtime not in request_file.parents or not request_file.is_file(): raise ValueError('E6-v2 controller request path is missing or outside runtime')
    request=json.loads(request_file.read_text())
    if request.get('attempt_id')!=attempt or not isinstance(request.get('task'),dict) or request['task'].get('key')!=task.get('key'):
        raise ValueError('E6-v2 controller request task/attempt identity mismatch')
    request_task=dict(request['task']); request_task.pop('_controller_request_sha256',None)
    request_payload={'task':request_task,'attempt_id':request['attempt_id'],'result_path':request.get('result_path'),'dispatch_policy_id':request.get('dispatch_policy_id')}
    expected_request_sha=hashlib.sha256(json.dumps(request_payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if expected_request_sha!=request_sha: raise ValueError('E6-v2 controller request canonical digest mismatch')
    if request['task']!=task: raise ValueError('E6-v2 request task differs from executed task copy')
    worker_file=Path(__file__).with_name('worker.py')
    if not worker_file.is_file() or _member_comparison_file_sha(worker_file)!=worker_sha:
        raise ValueError('E6-v2 selected worker script SHA does not match installed worker')
    out=runtime/'artifacts'/str(task['key'])/'attempts'/attempt
    state=out/f'e6_phase_{stage}.json'; events=out/'e6_phase_events.jsonl'
    rec=run_phase(target=_phase_child,args=(pipeline_paths,np.asarray(X),str(outfile)),
        state_path=state,event_path=events,task_key=task['key'],attempt_id=attempt,stage=stage,
        request_path=request_path,request_sha256=request_sha,worker_script_sha256=worker_sha,
        timeout_seconds=timeout,rss_limit_kib=rss_limit_kib,grace_seconds=grace,output_path=outfile)
    if rec.get('reason') in {'timeout','rss_limit'}:
        receipt={'seconds':rec['seconds'],'peak_tree_rss_kib':rec['peak_tree_rss_kib'],
                 'reason':rec['reason'],'exit_code':rec['exit_code']}
        raise RuntimeError('prediction_%s: %r' % (rec['reason'],receipt))
    if rec.get('status')!='successful':
        raise RuntimeError(f'E6-v2 supervised prediction phase invalid: {rec}')
    return {'seconds':rec['seconds'],'peak_tree_rss_kib':rec['peak_tree_rss_kib'],
            'reason':None,'exit_code':rec['exit_code'],'result':rec['result'],
            'process_state_path':str(state.relative_to(runtime)),
            'process_state_sha256':_member_comparison_file_sha(state),
            'output_sha256':rec.get('output_sha256')}

def _e6_v2_validate_roles(roles,test,rep):
    required=('X_fit','y_fit','fit_ids','X_tune','y_tune','tuning_ids','X_cal','y_cal','calibration_ids')
    missing=[k for k in required if k not in roles]
    if missing: raise ValueError(f'E6-v2 role cache missing {missing}')
    arrays=[('fit',roles['X_fit'],roles['y_fit'],roles['fit_ids'],80000),('tune',roles['X_tune'],roles['y_tune'],roles['tuning_ids'],10000),('cal',roles['X_cal'],roles['y_cal'],roles['calibration_ids'],10000),('test',test['X'],test['y'],test['ids'],500000)]
    ids=[]
    for name,X,y,identity,n in arrays:
        X=np.asarray(X); y=np.asarray(y); identity=np.asarray(identity)
        if X.shape!=(n,6) or y.shape!=(n,) or identity.shape!=(n,): raise ValueError(f'E6-v2 {name} role shape/count mismatch')
        if not np.isfinite(X).all() or not np.issubdtype(y.dtype,np.integer) or np.any((y<0)|(y>=7)): raise ValueError(f'E6-v2 {name} role feature/label invalid')
        if len(np.unique(identity))!=n: raise ValueError(f'E6-v2 {name} IDs are not unique')
        if set(np.unique(y).tolist())!=set(range(7)): raise ValueError(f'E6-v2 {name} lacks one or more classes')
        ids.append(identity)
    for i in range(len(ids)):
        for j in range(i+1,len(ids)):
            if np.intersect1d(ids[i],ids[j]).size: raise ValueError('E6-v2 fit/tune/cal/test roles overlap')

def _e6_v2_validate_member_artifacts(runtime,task,name,key,pipe,pipeline_path,fit_ids,fit_y):
    evidence=task.get('member_fit_evidence')
    if not isinstance(evidence,dict) or set(evidence)!=set(MEMBERS): raise ValueError('E6-v2 requires complete member_fit_evidence for all five selected fits')
    exp=evidence[name]
    if not isinstance(exp,dict) or exp.get('fit_key')!=key or exp.get('method')!=name: raise ValueError(f'E6-v2 {name} fit evidence identity mismatch')
    expected_fields=('pipeline_sha256','selection_sha256','fit_result_sha256','validation_sha256','role_membership_sha256','training_ids_sha256','training_rows','class_order','feature_order','provenance_group','selected_params_sha256','class_counts')
    if any(exp.get(k) is None for k in expected_fields): raise ValueError(f'E6-v2 {name} fit evidence missing fields')
    if int(exp['training_rows'])!=80000 or list(exp['class_order'])!=list(range(7)) or len(exp['feature_order'])!=6 or len(exp['class_counts'])!=7 or sum(exp['class_counts'])!=80000: raise ValueError(f'E6-v2 {name} fit evidence role contract invalid')
    if np.bincount(np.asarray(fit_y,dtype=int),minlength=7).tolist()!=exp['class_counts']: raise ValueError(f'E6-v2 {name} class counts differ from fixed fit cohort')
    base=Path(runtime)/'artifacts'/key; sel=base/'selection.json'; fr=base/'fit_result.json'; val=base/'validation.json'
    for path,field in ((pipeline_path,'pipeline_sha256'),(sel,'selection_sha256'),(fr,'fit_result_sha256'),(val,'validation_sha256')):
        if not path.is_file() or _member_comparison_file_sha(path)!=exp[field]: raise ValueError(f'E6-v2 {name} {field} does not match recorded validated fit evidence')
    validation=json.loads(val.read_text()); fit_result=json.loads(fr.read_text()); selection=json.loads(sel.read_text())
    if validation.get('status') not in ('validated','successful') or validation.get('task_key') not in (None,key): raise ValueError(f'E6-v2 {name} validation record invalid')
    files=validation.get('files',{}); recorded=files.get('pipeline.joblib',files.get('pipeline'))
    if recorded!=exp['pipeline_sha256'] or files.get('selection.json')!=exp['selection_sha256']: raise ValueError(f'E6-v2 {name} validation does not bind pipeline and selection bytes')
    if fit_result.get('artifact_sha256')!=exp['pipeline_sha256']: raise ValueError(f'E6-v2 {name} fit result does not bind pipeline bytes')
    if fit_result.get('status') not in ('successful','success') or fit_result.get('task_key') not in (None,key) or fit_result.get('task',{}).get('key') not in (None,key): raise ValueError(f'E6-v2 {name} fit result is not successful/for expected key')
    result=fit_result.get('result',{})
    if result.get('status') not in ('successful','success') or result.get('training_ids_sha256')!=exp['training_ids_sha256'] or result.get('class_counts')!=exp['class_counts']: raise ValueError(f'E6-v2 {name} fit result training provenance/class counts mismatch')
    params=selection.get('selected_params',selection.get('params'))
    if not isinstance(params,dict) or pipe.get('params')!=params or hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=exp['selected_params_sha256'] or result.get('params')!=params: raise ValueError(f'E6-v2 {name} pipeline/selection/overlay params mismatch')
    if pipe.get('method') not in (None,name) or pipe.get('training_ids_sha256')!=exp['training_ids_sha256'] or _sha(fit_ids)!=exp['training_ids_sha256']: raise ValueError(f'E6-v2 {name} fit role/method identity mismatch')
    if int(pipe.get('training_rows',exp['training_rows']))!=80000: raise ValueError(f'E6-v2 {name} pipeline training row count mismatch')
    feature_order=pipe.get('feature_order',fit_result.get('feature_order'))
    if feature_order is None or list(feature_order)!=list(exp['feature_order']): raise ValueError(f'E6-v2 {name} feature order is missing or mismatched')
    if exp['provenance_group'] not in {'e2_reconstructed','e3_new_fit'}: raise ValueError(f'E6-v2 {name} provenance group is unknown')
    return dict(exp)

def _posterior_receipt(stage,score_path,scores,fingerprint):
    return {'schema_version':'lamost-e6-posterior-cache-receipt/1','stage':stage,'fingerprint':fingerprint,
            'fingerprint_sha256':hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'posterior_file_sha256':_member_comparison_file_sha(score_path),'row_count':len(next(iter(scores.values()))),
            'member_order':list(MEMBERS),'posterior_sha256':{m:_sha(scores[m]) for m in MEMBERS}}

def _verify_posterior_receipt(stage,score_path,receipt_path,scores,fingerprint):
    try: rec=json.loads(Path(receipt_path).read_text())
    except Exception as exc: raise ValueError(f'E6-v2 {stage} posterior cache receipt missing/corrupt; refusing recomputation: {exc}') from exc
    expected=_posterior_receipt(stage,score_path,scores,fingerprint)
    if rec!=expected: raise ValueError(f'E6-v2 {stage} posterior cache receipt/fingerprint/array hash mismatch; refusing recomputation')
    return rec

def _load_scores(path):
    with np.load(path,allow_pickle=False) as z: return {m:_posterior(z[m],m) for m in MEMBERS}

def _member_comparison_payload(*, task, members, model_hashes, fit_hashes, member_fit_evidence, fingerprint,
                               tune_ids, cal_ids, test_ids, phase_times, tune_scores, cal_scores, test_scores,
                               y_tune, y_cal, y_test, weights, mode, weights_obj,
                               ensemble_threshold, ensemble_result, evaluator,
                               candidate_ledger_path, candidate_ledger_sha256, weights_frozen_utc):
    # All comparisons use the already required E6 posterior arrays. The tuning-best
    # member and learned weights use tuning only; member q values use calibration;
    # test results are computed after weights are frozen and never choose a model.
    from sklearn.metrics import confusion_matrix
    tune_ba={name:float(evaluator.balanced_accuracy(y_tune,np.argmax(tune_scores[name],axis=1))) for name in MEMBERS}
    best=min(MEMBERS,key=lambda name:(-tune_ba[name],MEMBERS.index(name)))
    out={}
    for name in MEMBERS:
        q=evaluator.conformal_threshold(cal_scores[name],y_cal,score_kind='probability',alpha=.1)
        result=evaluator.conformal_evaluate(test_scores[name],y_test,q,score_kind='probability')
        out[name]={
            'fit_key':members[name], 'pipeline_sha256':model_hashes[name],
            'fit_ids_sha256':fit_hashes[name], 'role_membership_sha256':member_fit_evidence[name]['role_membership_sha256'],
            'selection_sha256':member_fit_evidence[name]['selection_sha256'],'fit_result_sha256':member_fit_evidence[name]['fit_result_sha256'],
            'validation_sha256':member_fit_evidence[name]['validation_sha256'],'selected_params_sha256':member_fit_evidence[name]['selected_params_sha256'],
            'provenance_group':member_fit_evidence[name]['provenance_group'],
            'score_kind':'probability','tuning_balanced_accuracy':tune_ba[name],
            'alpha':.1,'calibration_threshold':float(q),
            'calibration_n':int(len(y_cal)),'test_n':int(len(y_test)),
            'evaluation':{k:result[k] for k in ('balanced_accuracy','set_size','coverage','per_class')},
            'confusion_matrix':confusion_matrix(y_test,result['predictions'],labels=np.arange(7)).tolist()
        }
    return {
        'schema_version':'lamost-e6-member-comparisons/1',
        'protocol_version':'E6-v2','rep':int(task['rep']),
        'comparison_source_task_key':str(task['key']),'mode':mode,
        'member_order':list(MEMBERS),'members':out,
        'posterior_fingerprint':fingerprint,
        'fit_ids_sha256':next(iter(set(fit_hashes.values()))),
        'tuning_ids_sha256':_sha(tune_ids),'calibration_ids_sha256':_sha(cal_ids),
        'test_ids_sha256':_sha(test_ids),
        'score_rule':'native normalized seven-class posterior; argmax prediction; probability nonconformity 1-p_true',
        'quantile_rule':'finite-sample split-conformal: k=ceil((n_cal+1)*(1-alpha)); kth calibration nonconformity order statistic',
        'weights_frozen_utc':weights_frozen_utc,
        'weights_frozen_before_calibration_and_test':True,
        'tuning_best_member':best,'tuning_best_balanced_accuracy':tune_ba[best],
        'selected_weights':[float(x) for x in weights],
        'candidate_ledger_path':candidate_ledger_path,
        'candidate_ledger_sha256':candidate_ledger_sha256,
        'ensemble_threshold':float(ensemble_threshold),
        'ensemble_evaluation':{k:ensemble_result[k] for k in ('balanced_accuracy','set_size','coverage','per_class')},
        'ensemble_confusion_matrix':confusion_matrix(y_test,ensemble_result['predictions'],labels=np.arange(7)).tolist(),
        'phase_costs':dict(phase_times),
        'phase_cost_note':'Posterior phase costs/cache status are shared by equal and learned modes; member comparisons add no prediction phase.'
    }

def _member_comparison_file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def _save_scores(path,scores):
    tmp=Path(str(path)+f".{os.getpid()}.tmp.npz"); np.savez_compressed(tmp,**scores); os.replace(tmp,path)

def _member_evaluation_preflight(task):
    # E6-v2 makes the five selected fitted pipelines the ensemble dependencies.
    # E3 direct-evaluation references remain historical comparison metadata and
    # never gate E6-specific posterior computation. Tasks without the explicit
    # version retain the historical V1 preflight for replay.
    if task.get('e6_protocol_version') == 'E6-v2':
        members=task.get('members',{})
        if not isinstance(members,dict) or set(members)!=set(MEMBERS):
            missing=sorted(set(MEMBERS)-set(members)) if isinstance(members,dict) else list(MEMBERS)
            return {'state':'unavailable','reason':'E6-v2 requires all five selected generator fit keys','missing_members':missing}
        return {'state':'ready','reason':None,'dependency_basis':'five_selected_fits'}
    refs=task.get('member_evaluations',{})
    if not isinstance(refs,dict) or not refs:
        return {'state':'unavailable','reason':'E6 task lacks declared individual-member evaluation references'}
    observations=task.get('member_evaluation_dependency_observations')
    if not isinstance(observations,dict):
        return {'state':'waiting','reason':'E6 member evaluation dependency observations were not supplied'}
    missing=[key for key in refs.values() if key not in observations]
    if missing:
        return {'state':'waiting','reason':'E6 member evaluation dependency observations missing: '+', '.join(missing)}
    failed=[]
    pending=[]
    for key in refs.values():
        obs=observations[key]
        if obs.get('status')=='validated_terminal' and obs.get('outcome')!='successful':
            failed.append(key+': '+str(obs.get('outcome'))+((': '+str(obs.get('reason'))) if obs.get('reason') else ''))
        elif not (obs.get('status')=='validated_terminal' and obs.get('outcome')=='successful'):
            pending.append(key+': '+str(obs.get('status')))
    if failed:return {'state':'unavailable','reason':'required E6 member evaluation unavailable: '+'; '.join(failed)}
    if pending:return {'state':'waiting','reason':'required E6 member evaluations are not terminal-successful: '+'; '.join(pending)}
    return {'state':'ready','reason':None}

def _execute_e6_before_phase_taxonomy(task,runtime)->dict:
    """Evaluate one frozen five-member E6 ensemble; only prediction phases run."""
    gate=_member_evaluation_preflight(task)
    if gate['state']=='unavailable':
        return {'status':'unavailable_dependency','reason':gate['reason'],'evaluation':None,'posterior_phases_started':False}
    if gate['state']=='waiting':
        return {'status':'operationally_interrupted','reason':'E6 member preflight not ready: '+gate['reason'],'preflight_not_ready':True,'evaluation':None,'posterior_phases_started':False}
    _,ens,ev=_project(runtime)
    rep=int(task['rep']); mode=str(task.get('mode','equal'))
    if mode not in {'equal','learned'}: raise ValueError('E6 mode must be equal or learned')
    members=task.get('members',{})
    if set(members)!=set(MEMBERS): return {'status':'unavailable_dependency','reason':'five-member primary ensemble requires all five generator fits','missing_members':sorted(set(MEMBERS)-set(members))}
    runtime=Path(runtime).resolve(); cache=runtime/'cache'
    v2=task.get('e6_protocol_version')=='E6-v2'
    roles=_load_npz(cache/'roles'/f'rep_{rep}.npz',('X_tune','y_tune','X_cal','y_cal','fit_ids','tuning_ids','calibration_ids')+(('X_fit','y_fit') if v2 else ()))
    test=_load_npz(cache/'test.npz',('X','y','ids'))
    if v2: _e6_v2_validate_roles(roles,test,rep)
    for name,arr in [('X_tune',roles['X_tune']),('X_cal',roles['X_cal']),('X_test',test['X'])]:
        if arr.ndim!=2 or arr.shape[1]!=6 or not np.isfinite(arr).all(): raise ValueError(f'{name} must be finite N x 6')
    yt=np.asarray(roles['y_tune'],dtype=np.int64); yc=np.asarray(roles['y_cal'],dtype=np.int64); y=np.asarray(test['y'],dtype=np.int64); ids=np.asarray(test['ids'])
    for name,v,n in [('tuning',yt,len(roles['X_tune'])),('calibration',yc,len(roles['X_cal'])),('test',y,len(test['X']))]:
        if v.ndim!=1 or len(v)!=n or np.any((v<0)|(v>=7)): raise ValueError(f'{name} labels invalid')
    if ids.ndim!=1 or len(ids)!=len(y) or len(np.unique(ids))!=len(ids): raise ValueError('test IDs must be unique and row matched')
    out=runtime/'artifacts'/str(task['key']); out.mkdir(parents=True,exist_ok=True)
    import joblib
    paths={}; model_hashes={}; fit_hashes={}; member_fit_evidence={}
    for name in MEMBERS:
        pp=_pipeline_path(runtime,members[name])
        if not pp.exists(): return {'status':'unavailable_dependency','reason':f'missing pipeline for {name}','missing_members':[name],'fit_key':members[name]}
        pipe=joblib.load(pp)
        if not isinstance(pipe,dict) or not all(k in pipe for k in ('model','imputer','scaler')): raise ValueError(f'{name} pipeline schema invalid')
        if pipe.get('method') not in (None,name): raise ValueError(f'{name} pipeline method mismatch: {pipe.get("method")}')
        if getattr(pipe['model'],'score_kind','probability')!='probability': raise ValueError(f'{name} lacks native posterior probabilities')
        _validate_class_order(pipe['model'],name)
        fit_hash=pipe.get('training_ids_sha256')
        if not fit_hash: raise ValueError(f'{name} pipeline lacks fitting-ID provenance hash')
        fit_hashes[name]=fit_hash; paths[name]=pp
        h=hashlib.sha256()
        with pp.open('rb') as f:
            for block in iter(lambda:f.read(1<<20),b''): h.update(block)
        model_hashes[name]=h.hexdigest()
        if v2: member_fit_evidence[name]=_e6_v2_validate_member_artifacts(runtime,task,name,members[name],pipe,pp,np.asarray(roles['fit_ids']),np.asarray(roles['y_fit']))
    if len(set(fit_hashes.values()))!=1: raise ValueError('member fitting-role provenance hashes differ')
    if v2 and len({member_fit_evidence[m]['role_membership_sha256'] for m in MEMBERS})!=1: raise ValueError('E6-v2 member recorded role-membership identities differ')
    if v2 and len({tuple(member_fit_evidence[m]['feature_order']) for m in MEMBERS})!=1: raise ValueError('E6-v2 member feature orders differ')
    fit_ids=np.asarray(roles['fit_ids']); tune_ids=np.asarray(roles['tuning_ids']); cal_ids=np.asarray(roles['calibration_ids'])
    if _sha(fit_ids)!=next(iter(set(fit_hashes.values()))): raise ValueError('member fitting IDs do not match the exact repetition role cache')
    if len(np.unique(tune_ids))!=len(tune_ids) or len(tune_ids)!=len(yt): raise ValueError('tuning IDs do not match unique tuning rows')
    if len(np.unique(cal_ids))!=len(cal_ids) or len(cal_ids)!=len(yc): raise ValueError('calibration IDs do not match unique calibration rows')
    fingerprint={'pipeline_sha256':model_hashes,'fit_ids_sha256':_sha(fit_ids),'tuning_ids_sha256':_sha(tune_ids),'calibration_ids_sha256':_sha(cal_ids),'test_ids_sha256':_sha(ids),'X_tune_sha256':_sha(roles['X_tune']),'X_cal_sha256':_sha(roles['X_cal']),'X_test_sha256':_sha(test['X']),'y_tune_sha256':_sha(yt),'y_cal_sha256':_sha(yc),'y_test_sha256':_sha(y)}
    if v2: fingerprint['member_fit_evidence']=member_fit_evidence
    sig=hashlib.sha256(json.dumps(fingerprint,sort_keys=True).encode()).hexdigest()[:24]
    shared=cache/'e6_posteriors'/f'rep_{rep}'/sig; shared.mkdir(parents=True,exist_ok=True)
    lock_path=shared/'phase.lock'; phase_times={}
    def get_stage(stage,X):
        cp=shared/f'{stage}.npz'
        with lock_path.open('a+b') as lock:
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
            failure_marker=shared/f'{stage}.scientific_failure.json'
            if failure_marker.exists():
                record=_cached_record(failure_marker,fingerprint)
                if record.get('source_task_key')==str(task['key']): raise E6PhaseFailure(record)
                raise E6CachedPhaseFailure(record)
            receipt_path=shared/f'{stage}.receipt.json'
            if cp.exists():
                try: scores=_load_scores(cp)
                except Exception as exc:
                    if v2: raise ValueError(f'E6-v2 corrupt posterior cache; refusing phase retry: {exc}') from exc
                    scores=None
                if v2 and scores is not None: _verify_posterior_receipt(stage,cp,receipt_path,scores,fingerprint)
            else:
                scores=None
                if v2 and receipt_path.exists(): raise ValueError(f'E6-v2 orphan posterior receipt for absent {stage} cache')
            if scores is None:
                def _runner():
                    if v2: return _run_prediction_phase_v2(paths,X,cp,task=task,runtime=runtime,stage=stage)
                    return _run_prediction_phase(paths,X,cp)
                rec=run_phase_with_terminal_failure_cache(stage=stage,shared_dir=shared,fingerprint=fingerprint,mode=mode,task_key=task['key'],runner=_runner)
                scores=_load_scores(cp)
                if any(v.shape!=(len(X),7) for v in scores.values()): raise ValueError(f'{stage} cache row count invalid')
                if v2:
                    receipt=_posterior_receipt(stage,cp,scores,fingerprint); _json(receipt_path,receipt)
                    phase_times[f'{stage}_process_state_path']=rec.get('process_state_path')
                    phase_times[f'{stage}_process_state_sha256']=rec.get('process_state_sha256')
                    phase_times[f'{stage}_posterior_receipt_sha256']=hashlib.sha256(json.dumps(receipt,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                phase_times[f'{stage}_seconds']=rec['seconds']; phase_times[f'{stage}_peak_tree_rss_kib']=rec['peak_tree_rss_kib']; phase_times[f'{stage}_cache_hit']=False
            else:
                phase_times[f'{stage}_cache_hit']=True
            fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
        if any(v.shape!=(len(X),7) for v in scores.values()): raise ValueError(f'{stage} cache row count invalid')
        return scores
    tune_scores=get_stage('tune',roles['X_tune'])
    # Freeze the selected vector and its full tuning ledger before calibration or test predictions.
    weights_obj=None; start=time.monotonic()
    search_cfg=task.get('weight_search',{}) if isinstance(task.get('weight_search',{}),dict) else {}
    weight_seed=int(search_cfg.get('seed',int(task.get('seed',271828))+rep))
    if mode=='equal': weights=np.full(5,.2,dtype=float)
    else:
        weights_obj=ens.fit_ensemble_weights(tune_scores,yt,seed=weight_seed,dirichlet_candidates=int(search_cfg.get('dirichlet_candidates',1000)),candidate_cap=int(search_cfg.get('maximum_candidates',search_cfg.get('candidate_cap',2000))))
        weights=np.asarray(weights_obj['weights'],dtype=float)
    phase_times['weight_selection_seconds']=time.monotonic()-start
    weights_frozen_utc=datetime.now(timezone.utc).isoformat()
    np.savez_compressed(out/'tuning_posteriors.npz',**{f'{m}_posterior':tune_scores[m] for m in MEMBERS},y_tune=yt,tuning_ids=tune_ids)
    if weights_obj is not None: _json(out/'candidate_ledger.json',weights_obj)
    _json(out/'frozen_weights.json',{'mode':mode,'member_order':list(MEMBERS),'weights':weights.tolist(),'frozen_before_calibration_and_test':True,'weights_frozen_utc':weights_frozen_utc,'weight_search_seed':weight_seed,'fingerprint':fingerprint,'candidate_ledger':'candidate_ledger.json' if weights_obj is not None else None})
    cal_scores=get_stage('cal',roles['X_cal']); cal_mix=ens.ensemble_scores(cal_scores,weights)
    q=ev.conformal_threshold(cal_mix,yc,score_kind='probability',alpha=.1)
    test_scores=get_stage('test',test['X']); test_mix=ens.ensemble_scores(test_scores,weights)
    result=ev.conformal_evaluate(test_mix,y,q,score_kind='probability')
    member_comparisons=None
    if task.get('e6_protocol_version') == 'E6-v2':
        ledger_path='candidate_ledger.json' if weights_obj is not None else None
        ledger_sha=_member_comparison_file_sha(out/ledger_path) if ledger_path else None
        member_comparisons=_member_comparison_payload(
            task=task,members=members,model_hashes=model_hashes,fit_hashes=fit_hashes,
            member_fit_evidence=member_fit_evidence,fingerprint=fingerprint,
            tune_ids=tune_ids,cal_ids=cal_ids,test_ids=ids,phase_times=phase_times,tune_scores=tune_scores,
            cal_scores=cal_scores,test_scores=test_scores,y_tune=yt,y_cal=yc,y_test=y,
            weights=weights,mode=mode,weights_obj=weights_obj,ensemble_threshold=q,
            ensemble_result=result,evaluator=ev,candidate_ledger_path=ledger_path,
            candidate_ledger_sha256=ledger_sha,weights_frozen_utc=weights_frozen_utc)
        member_path=out/'member_comparisons.json'
        _json(member_path,member_comparisons)
    from sklearn.metrics import confusion_matrix
    np.savez_compressed(out/'test_outcomes.npz',sample_id=ids,y_pred=result['predictions'],set_mask=np.packbits(result['sets'],axis=1,bitorder='little')[:,0],covered=result['covered'],set_size=result['set_sizes'],y_true=y)
    evaluation={k:result[k] for k in ('balanced_accuracy','set_size','coverage','per_class')}
    evaluation.update({'confusion_matrix':confusion_matrix(y,result['predictions'],labels=np.arange(7)).tolist(),'calibration_n':len(yc),'test_n':len(y),'conformal_threshold':float(q),'alpha':.1,'score_kind':'probability','experiment':6,'repetition':rep,'mode':mode,'member_order':list(MEMBERS),'class_order':list(range(7)),'weights':weights.tolist(),'source_fit_keys':members,'pipeline_sha256':model_hashes,'training_role_hashes':{m:{'fit_ids_sha256':fit_hashes[m]} for m in MEMBERS},'fit_ids_sha256':_sha(fit_ids),'tuning_ids_sha256':_sha(tune_ids),'calibration_ids_sha256':_sha(cal_ids),'test_ids_sha256':_sha(ids),'phase_times_seconds':phase_times,'posterior_cache_key':sig,'set_mask_encoding':'one byte per row; low seven bits are classes 0..6','bootstrap':'not performed'})
    if member_comparisons is not None:
        evaluation['member_comparisons_path']='member_comparisons.json'
        evaluation['member_comparisons_sha256']=_member_comparison_file_sha(out/'member_comparisons.json')
        evaluation['e6_protocol_version']='E6-v2'
    _json(out/'evaluation.json',evaluation)
    return {'status':'success','evaluation':evaluation,'artifact_dir':str(out)}
def execute(task,runtime)->dict:
    return execute_with_terminal_classification(_execute_e6_before_phase_taxonomy,task,runtime)
