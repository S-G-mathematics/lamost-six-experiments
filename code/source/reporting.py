from __future__ import annotations
import ast, csv, hashlib, json, math, os, re, statistics, subprocess, sys, tempfile, textwrap
from collections import Counter,defaultdict
from pathlib import Path
from cold_report_access import inspect_pipeline, ArtifactIdentityError
from reason_text_curation import sanitize_reason_text

METRICS=('balanced_accuracy','coverage','set_size')
def _effective_status(rec):
    status=rec.get('status')
    outcome=rec.get('outcome')
    if status=='validated_terminal':
        if isinstance(outcome,str): return outcome
        if isinstance(outcome,dict): return outcome.get('status') or outcome.get('outcome') or status
    return status
def _read_json(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None
def _metric(e,k):
    v=e.get(k)
    return float(v) if isinstance(v,(int,float)) and math.isfinite(float(v)) else None
def _write_csv(path,rows,fields=None):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if fields is None: fields=list(dict.fromkeys(k for row in rows for k in row))
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
def _safe_key_artifact_dir(runtime,rec):
    """Resolve an artifact key inside this runtime; artifact_dir is provenance only."""
    key=rec.get('key') if isinstance(rec,dict) else None
    if not isinstance(key,str) or not key or "\\" in key or key.startswith("/"): return None
    parts=key.split("/")
    if any(not part or part in {".",".."} or not re.fullmatch(r"[A-Za-z0-9_.-]+",part) for part in parts): return None
    root=(Path(runtime).resolve()/"artifacts").resolve()
    candidate=root.joinpath(*parts)
    try:
        if not candidate.resolve(strict=False).is_relative_to(root): return None
    except (OSError,ValueError): return None
    return candidate

def _find_eval(runtime,rec):
    if not rec.get('scientific_case'): return None
    status=_effective_status(rec); validation=rec.get('validation_state')
    if status!='successful': return None
    if validation not in {'valid','validated','passed','validated_terminal','success'}: return None
    ev=rec.get('outcome')
    if isinstance(ev,dict):
        if isinstance(ev.get('evaluation'),dict): return ev['evaluation']
        if any(k in ev for k in METRICS): return ev
    p=_safe_key_artifact_dir(runtime,rec)
    if p is not None:
        for name in ('evaluation.json','eval_result.json','phase_result.json'):
            d=_read_json(p/name)
            if not d: continue
            if isinstance(d.get('evaluation'),dict): return d['evaluation']
            if any(k in d for k in METRICS): return d
            if isinstance(d.get('result'),dict) and any(k in d['result'] for k in METRICS): return d['result']
    return None
def _e6_tuning_summary(rec):
    if rec.get('experiment')!=6 or rec.get('kind')!='ensemble' or not rec.get('artifact_dir'): return None, None, None
    p=Path(rec['artifact_dir'])/'tuning_posteriors.npz'
    if not p.exists(): return None, None, None
    try:
        import numpy as np
        order=('gmm','copula','arf','kde','chow_liu')
        with np.load(p,allow_pickle=False) as z:
            y=np.asarray(z['y_tune'],dtype=np.int64); scores={m:np.asarray(z[f'{m}_posterior'],dtype=float) for m in order}
        if y.ndim!=1 or any(a.shape!=(len(y),7) for a in scores.values()) or np.any((y<0)|(y>=7)): return None,None,None
        values={}
        for m in order:
            pred=np.argmax(scores[m],axis=1); recalls=[float(np.mean(pred[y==c]==c)) for c in range(7) if np.any(y==c)]
            values[m]=float(np.mean(recalls)) if len(recalls)==7 else None
        available=[m for m in order if values[m] is not None]
        best=min(available,key=lambda m:(-values[m],order.index(m))) if available else None
        return best,values.get(best) if best else None,values
    except Exception: return None,None,None
FAILURE_TYPES=('timeout','memory_rss','unsupported','observed_model_fit_error','unclassified','not_a_failure','not_applicable')
FAILURE_STATES={'scientific_failure','unsupported','unavailable_dependency','operationally_interrupted','operationally_invalid','failed','failure','fail','timeout'}
def _reason_text(value):
    if value is None:return None
    if isinstance(value,str):return value
    return json.dumps(value,sort_keys=True,default=str)
def _sanitize_reason(value):
    return sanitize_reason_text(_reason_text(value))

def _failure_evidence_type(status,reason=None):
    st=str(status or '').lower();text=(_reason_text(reason) or '').lower()
    if st in {'successful','success','validated','valid','passed','not_attempted','not_applicable'}:return 'not_a_failure'
    if st=='unsupported' or 'unsupported' in text or 'not supported' in text:return 'unsupported'
    if any(x in text for x in ('rss_limit','memory_limit','memory limit','out of memory','memoryerror','oom_kill','oom-kill')):return 'memory_rss'
    if 'timeout' in text or 'timed out' in text:return 'timeout'
    if st in {'scientific_failure','failed','failure','fail'} and text:
        if re.search(r'\b(ValueError|TypeError|RuntimeError|FloatingPointError|LinAlgError|ImportError|AttributeError|AssertionError)\b|model.?fit.?error|fit failed',_reason_text(reason) or '',re.I):return 'observed_model_fit_error'
        return 'unclassified'
    if st in FAILURE_STATES:return 'unclassified'
    return 'not_applicable'

def _task_reason(task,doc=None):
    outcome=task.get('outcome')
    candidates=[task.get('reason'),task.get('failure_reason')]
    if isinstance(outcome,dict):candidates.extend((outcome.get('reason'),outcome.get('error'),outcome.get('message')))
    if isinstance(doc,dict):
        candidates.extend((doc.get('reason'),doc.get('error')))
        result=doc.get('result')
        if isinstance(result,dict):candidates.extend((result.get('reason'),result.get('error')))
    return next((x for x in candidates if x not in (None,'')),None)

def _file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def _terminal_worker_rss_cutoff(runtime,task):
    """Evidence-backed overlay for a terminal outer worker RSS cutoff.

    This overlay applies only to fit tasks explicitly terminated by the
    controller's worker process-tree RSS policy. It identifies the final
    recorded phase from matching attempt/request/state evidence and leaves raw
    checkpoint files untouched. Ambiguous or incomplete evidence is omitted.
    """
    if not isinstance(task,dict) or task.get('kind')!='fit': return None
    if _effective_status(task)!='scientific_failure': return None
    reason=task.get('reason') or task.get('forced_reason')
    if reason!='worker process-tree memory policy exceeded': return None
    peak=task.get('peak_tree_rss_bytes')
    if not isinstance(peak,int): return None
    cap=int(round(float((_read_json(Path(runtime)/'manifests/E3_MANIFEST.json') or {}).get('resource_policy',{}).get('worker_memory_gib',10))*1024**3))
    if peak<=cap:return None
    runtime=Path(runtime);key=task.get('key')
    art=_task_artifact(runtime,task);artifact_attempts=art/'attempts'
    controller_attempts=task.get('attempts') or []
    if not artifact_attempts.exists() or not controller_attempts:return None
    latest=controller_attempts[-1]
    req_path=Path(latest.get('request_path',''))
    if not req_path.is_absolute():req_path=runtime/req_path
    req=_read_json(req_path)
    if not req or req.get('attempt_id')!=latest.get('attempt_id') or req.get('task',{}).get('key')!=key:return None
    def identity(x):
        names=('key','kind','experiment','rep','method','route','generator','condition','seed','optimizer_seed','trials','train_key','sample_count')
        return {k:x.get(k) for k in names if k in x}
    controller_def=req.get('task',{})
    if identity(controller_def)!=identity(task):return None
    # Match the phase attempt to this exact controller attempt using task identity
    # and the worker's actual start timestamp; never choose an arbitrary old run.
    started=latest.get('started_utc') or task.get('started_utc')
    candidates=[]
    for ap in artifact_attempts.iterdir():
        if not ap.is_dir():continue
        attempt_doc=_read_json(ap/'attempt.json')
        if not attempt_doc or attempt_doc.get('task',{}).get('key')!=key:continue
        if identity(attempt_doc.get('task',{}))!=identity(task):continue
        try:
            from datetime import datetime
            a=datetime.fromisoformat(str(attempt_doc.get('started_at')).replace('Z','+00:00'))
            b=datetime.fromisoformat(str(started).replace('Z','+00:00'))
            delta=abs((a-b).total_seconds())
        except Exception:continue
        if delta<=300:candidates.append((delta,ap,attempt_doc))
    if len(candidates)!=1:return None
    _,ap,attempt_doc=candidates[0]
    selection_path=ap/'selection.json'
    selection=_read_json(selection_path)
    if not isinstance(selection,dict) or not isinstance(selection.get('trials'),list):return None
    trials=selection['trials']
    numbers=[]
    for tr in trials:
        try:numbers.append(int(tr.get('number')))
        except Exception:return None
    if len(set(numbers))!=len(numbers) or sorted(numbers)!=list(range(len(numbers))):return None
    phase_states=[]
    for state_path in ap.glob('phase_trial_*_state.json'):
        m=re.fullmatch(r'phase_trial_(\d+)_state\.json',state_path.name)
        if not m:continue
        idx=int(m.group(1));request_path=ap/f'phase_trial_{idx}.json';result_path=ap/f'phase_trial_{idx}_result.json'
        if not request_path.exists():continue
        state=_read_json(state_path);phase_req=_read_json(request_path)
        if not isinstance(state,dict) or not isinstance(phase_req,dict):continue
        if phase_req.get('task',{}).get('key') not in (None,key):continue
        if state.get('status')=='running' and not result_path.exists():
            phase_states.append({'phase':'trial','index':idx,'state':state,'request':phase_req,'state_path':state_path,'request_path':request_path,'result_path':result_path})
    final_states=[]
    for state_path in sorted(set(ap.glob('phase_final_fit*_state.json'))):
        phase_name=state_path.name[:-len('_state.json')]
        request_path=ap/(phase_name+'.json');result_path=ap/(phase_name+'_result.json')
        if not request_path.exists():continue
        state=_read_json(state_path);phase_req=_read_json(request_path)
        if not isinstance(state,dict) or not isinstance(phase_req,dict):continue
        if phase_req.get('task',{}).get('key') not in (None,key):continue
        if state.get('status')=='running' and not result_path.exists():
            final_states.append({'phase':'final_fit','index':None,'state':state,'request':phase_req,'state_path':state_path,'request_path':request_path,'result_path':result_path})
    active=phase_states+final_states
    if len(active)!=1:return None
    phase=active[0]
    nominal=int(task.get('trials') or 0)
    if nominal<=0:return None
    if phase['phase']=='trial':
        idx=phase['index']
        if idx in numbers or numbers!=list(range(idx)):return None
        started_indices=sorted(set(numbers)|{idx})
        if started_indices!=list(range(idx+1)):return None
        started_count=idx+1;aborted_index=idx
    else:
        started_indices=numbers
        if numbers!=list(range(len(numbers))):return None
        if any(str(tr.get('status','')).lower() in {'running','waiting'} for tr in trials):return None
        started_count=len(started_indices);aborted_index=None
    unattempted=list(range(started_count,nominal))
    evidence_files=[selection_path,ap/'attempt.json',req_path,phase['state_path'],phase['request_path']]
    for state_path in ap.glob('phase_trial_*_state.json'):
        evidence_files.extend([state_path,ap/(state_path.name.replace('_state.json','.json'))])
        evidence_files.append(ap/(state_path.name.replace('_state.json','_result.json')))
    evidence_files=list(dict.fromkeys(p for p in evidence_files if p.exists()))
    source_hashes_before={str(p.resolve().relative_to(runtime.resolve())):_file_sha256(p) for p in evidence_files}
    # Re-read once after hashing; this guards against accidental mutation during reporting.
    for p in evidence_files:_read_json(p)
    source_hashes_after={str(p.resolve().relative_to(runtime.resolve())):_file_sha256(p) for p in evidence_files}
    if source_hashes_before!=source_hashes_after:return None
    params=phase['request'].get('params')
    return {'task_key':key,'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'generator':task.get('generator') or task.get('condition'),
       'route':task.get('route'),'condition':task.get('condition'),'outcome':'scientific_failure','failure_evidence_type':'memory_rss',
       'failure_reason':reason,'terminal_finished_utc':task.get('finished_utc'),'terminal_observed_utc':task.get('observed_utc'),
       'peak_tree_rss_bytes':peak,'attempt_id':latest.get('attempt_id'),'artifact_attempt_id':ap.name,'terminal_fit_record_status':task.get('status'),
       'completed_trial_indices':numbers,'completed_trial_count':len(numbers),'actually_started_trial_count':started_count,
       'recorded_selection_trial_count':len(trials),'completed_trial_statuses':_json_cell({k:sum(1 for x in trials if x.get('status')==k) for k in sorted({x.get('status') for x in trials})}),
       'nominal_trial_budget':nominal,'aborted_trial_index':aborted_index,'aborted_trial_status':'worker_resource_policy_aborted',
       'aborted_trial_last_state_status':phase['state'].get('status') if phase['phase']=='trial' else None,
       'aborted_trial_last_observed_elapsed_seconds':phase['state'].get('elapsed_seconds'),
       'aborted_trial_last_observed_peak_tree_rss_kib':phase['state'].get('peak_tree_rss_kib'),
       'aborted_trial_params':_json_cell(params) if phase['phase']=='trial' else None,'aborted_trial_score':None,
       'cutoff_phase':phase['phase'],'cutoff_phase_state_path':str(phase['state_path'].resolve().relative_to(runtime.resolve())),
       'cutoff_phase_request_path':str(phase['request_path'].resolve().relative_to(runtime.resolve())),
       'last_observed_phase_elapsed_seconds':phase['state'].get('elapsed_seconds'),'last_observed_phase_peak_tree_rss_kib':phase['state'].get('peak_tree_rss_kib'),
       'not_attempted_trial_number_assigned':False if unattempted else None,'not_attempted_trial_status':'not_attempted_terminal_worker_failure' if unattempted else None,
       'unattempted_nominal_slot_indices':unattempted,'unattempted_nominal_slots':len(unattempted),
       'final_fit_started':phase['phase']=='final_fit','published_pipeline_present':((lambda: inspect_pipeline(task,runtime).get('available',False))() if task.get('kind')=='fit' and task.get('outcome')=='successful' else False),
       'worker_memory_cap_bytes':cap,'trial_history_path':str(selection_path.resolve().relative_to(runtime.resolve())),
       'terminal_record_source':'registry terminal worker RSS outcome plus matching attempt and active phase state',
       'source_file_sha256_before':_json_cell(source_hashes_before),'source_file_sha256_after':_json_cell(source_hashes_after),
       'source_file_hashes_unchanged':source_hashes_before==source_hashes_after,'os_oom_inferred':False}

def _terminal_worker_cutoff_rows(runtime,tasks):
    out=[]
    for task in tasks:
        if not isinstance(task,dict):continue
        row=_terminal_worker_rss_cutoff(runtime,task)
        if row:out.append(row)
    return out

def _model_selection_rows(runtime,tasks):
    rows=[]
    runtime=Path(runtime)
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind')!='fit': continue
        art=_task_artifact(runtime,task); result=_task_result(art,'fit'); attempt=_attempt_dir(art,result,task)
        sel=_read_json(art/'selection.json') or (_read_json(attempt/'selection.json') if attempt else None)
        source=(task.get('source_metadata') or {}).get('provenance') if isinstance(task.get('source_metadata'),dict) else None
        cell_outcome=_effective_status(task);cell_reason=_task_reason(task,result)
        base={'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'status':cell_outcome,'validation_state':task.get('validation_state'),'cell_failure_evidence_type':_failure_evidence_type(cell_outcome,cell_reason),'cell_raw_reason':_sanitize_reason(cell_reason),'source_provenance':source or task.get('reuse_pipeline') or task.get('selection_source'),'selection_artifact':str((attempt/'selection.json') if attempt and (attempt/'selection.json').exists() else art/'selection.json'),'attempt_id':attempt.name if attempt else None,'selected_trial':sel.get('selected_trial') if sel else None,'selected_params':_json_cell((sel or {}).get('selected_params',(sel or {}).get('params'))),'selected_score':(sel or {}).get('selected_score'),'history_state':'available' if sel and isinstance(sel.get('trials'),list) else ('reused_pipeline_history_not_required' if task.get('reuse_pipeline') else 'missing_or_not_yet_written'),'candidate_count':len(sel.get('trials',[])) if sel and isinstance(sel.get('trials'),list) else None}
        trials=sel.get('trials',[]) if sel and isinstance(sel.get('trials'),list) else []
        if trials:
            for tr in trials:
                index=tr.get('number',tr.get('trial_index'));tr_status=tr.get('status',tr.get('state'));raw=tr.get('error');trial_event=str(tr_status or '').lower() in FAILURE_STATES
                phase_path=attempt/f'phase_trial_{index}_result.json' if attempt and index is not None else None
                phase=_read_json(phase_path) if phase_path and phase_path.exists() else {}
                evtype=_failure_evidence_type(tr_status,raw)
                if evtype=='not_applicable' and trial_event:evtype='unclassified'
                if tr_status in {'success','duplicate_cached'}:evtype='not_a_failure'
                if not raw and phase.get('reason'):raw={'phase':phase.get('phase'),'reason':phase.get('reason'),'seconds':phase.get('seconds'),'peak_tree_rss_kib':phase.get('peak_tree_rss_kib'),'exit_code':phase.get('exit_code'),'finished_at':phase.get('finished_at')}
                try: phase_rel=str(phase_path.resolve().relative_to(runtime.resolve())) if phase_path and phase_path.exists() else None
                except ValueError: phase_rel=None
                seconds=tr.get('seconds') if tr.get('seconds') is not None else phase.get('seconds')
                phase_reason=phase.get('reason')
                if evtype=='not_a_failure' and phase_reason in {'timeout','rss_limit'}: # retain the phase event independently of trial outcome
                    evtype='timeout' if phase_reason=='timeout' else 'memory_rss';trial_event=True
                rows.append({**base,'trial_index':index,'trial_status':tr_status,'trial_score':tr.get('score',tr.get('value')),'trial_params':_json_cell(tr.get('params')),'trial_seconds':seconds,'trial_error':_sanitize_reason(raw),'raw_reason':_sanitize_reason(raw),'failure_evidence_type':evtype,'event_scope':'tuning_trial','trial_failure_event':trial_event,'event_counts_as_cell_failure':False,'cell_outcome':cell_outcome,'phase':phase.get('phase',f'trial_{index}' if index is not None else None),'phase_reason':phase_reason,'phase_seconds':phase.get('seconds'),'peak_tree_rss_kib':phase.get('peak_tree_rss_kib'),'phase_exit_code':phase.get('exit_code'),'phase_evidence_path':phase_rel,'duplicate_cached':tr_status=='duplicate_cached','selected':index==base['selected_trial']})
        else:
            rows.append({**base,'trial_index':None,'trial_status':base['history_state'],'trial_score':None,'trial_params':None,'trial_seconds':None,'trial_error':None,'raw_reason':None,'failure_evidence_type':base['cell_failure_evidence_type'],'event_scope':'fit_cell','trial_failure_event':False,'event_counts_as_cell_failure':cell_outcome in {'scientific_failure','unsupported'},'cell_outcome':cell_outcome,'phase':None,'phase_reason':None,'phase_seconds':None,'peak_tree_rss_kib':None,'phase_exit_code':None,'phase_evidence_path':None,'duplicate_cached':None,'selected':None})
    for row in rows:
        incident=_serialization_recovery_incident(runtime,{'key':row.get('task_key')})
        if incident:
            row.update({'superseded_attempt_id':incident['original_attempt_id'],'superseded_phase':'final_fit',
                        'superseded_phase_classification':'operationally_invalid_post_save_validation_memory_duplication',
                        'validated_recovery_pipeline_sha256':incident['pipeline_sha256'],
                        'superseded_phase_seconds':incident['phase_seconds'],
                        'superseded_phase_peak_tree_rss_kib':incident['peak_tree_rss_kib']})
    # Retain failed trials from prior attempts/checkpoints, even when a resumed current attempt
    # has replaced selection.json. These are trial events, not terminal cell failures.
    known={(r.get('task_key'),r.get('attempt_id'),str(r.get('trial_index'))) for r in rows}
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind')!='fit': continue
        art=_task_artifact(runtime,task); source=(task.get('source_metadata') or {}).get('provenance') if isinstance(task.get('source_metadata'),dict) else None
        attempts=art/'attempts'
        if not attempts.exists(): continue
        for ap in sorted(x for x in attempts.iterdir() if x.is_dir()):
            sel=_read_json(ap/'selection.json')
            for tr in (sel or {}).get('trials',[]) if isinstance((sel or {}).get('trials'),list) else []:
                ix=tr.get('number',tr.get('trial_index')); st=tr.get('status',tr.get('state')); key=(task.get('key'),ap.name,str(ix))
                if key in known or str(st or '').lower() not in FAILURE_STATES: continue
                phase_path=ap/f'phase_trial_{ix}_result.json' if ix is not None else None
                phase=_read_json(phase_path) if phase_path and phase_path.exists() else {}
                raw=tr.get('error'); txt=_reason_text(raw) or ''
                m=re.search(r':\s*(\{.*\})\s*$',txt,re.S); embedded={}
                if m:
                    try:
                        val=ast.literal_eval(m.group(1)); embedded=val if isinstance(val,dict) else {}
                    except Exception: pass
                reason=phase.get('reason') or embedded.get('reason')
                typ=_failure_evidence_type(st,raw)
                rows.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'status':_effective_status(task),'validation_state':task.get('validation_state'),'cell_failure_evidence_type':_failure_evidence_type(_effective_status(task),_task_reason(task)),'cell_raw_reason':_sanitize_reason(_task_reason(task)),'source_provenance':source or task.get('reuse_pipeline') or task.get('selection_source'),'selection_artifact':str(ap/'selection.json'),'attempt_id':ap.name,'selected_trial':None,'selected_params':None,'selected_score':None,'history_state':'prior_attempt_history','candidate_count':len((sel or {}).get('trials',[])),'trial_index':ix,'trial_status':st,'trial_score':tr.get('score',tr.get('value')),'trial_params':_json_cell(tr.get('params')),'trial_seconds':tr.get('seconds') if tr.get('seconds') is not None else phase.get('seconds',embedded.get('seconds')),'trial_error':_sanitize_reason(raw),'raw_reason':_sanitize_reason(raw),'failure_evidence_type':typ,'event_scope':'tuning_trial','trial_failure_event':True,'event_counts_as_cell_failure':False,'cell_outcome':_effective_status(task),'phase':phase.get('phase',embedded.get('phase')),'phase_reason':reason,'phase_seconds':phase.get('seconds',embedded.get('seconds')),'peak_tree_rss_kib':phase.get('peak_tree_rss_kib',embedded.get('peak_tree_rss_kib')),'phase_exit_code':phase.get('exit_code',embedded.get('exit_code')),'phase_evidence_path':str(phase_path.resolve().relative_to(runtime.resolve())) if phase_path and phase_path.exists() else None,'duplicate_cached':False,'selected':False})
                known.add(key)
    rows.append({'task_key':'historical/E1/auxiliary_tuning_histories','experiment':1,'rep':None,'method':'GMM / CART / linear SVM','route':None,'condition':'10k GMM rep3; 30k CART and linear SVM rep2/rep3','status':'historical_artifact_gap','validation_state':'metrics remain validated; exact histories unavailable','source_provenance':'migrated project benchmark/results provenance note','selection_artifact':None,'selected_trial':None,'selected_params':None,'selected_score':None,'history_state':'missing_historical_history','candidate_count':None,'trial_index':None,'trial_status':'not_available','trial_score':None,'trial_params':None,'trial_seconds':None,'trial_error':'Seven auxiliary tuning-history discrepancies; canonical histories are unavailable. No trial records reconstructed.','raw_reason':'Seven auxiliary tuning-history discrepancies; canonical histories are unavailable. No trial records reconstructed.','failure_evidence_type':'unclassified','event_scope':'historical_gap','trial_failure_event':False,'event_counts_as_cell_failure':False,'cell_outcome':'historical_artifact_gap','phase':None,'phase_reason':None,'phase_seconds':None,'peak_tree_rss_kib':None,'phase_exit_code':None,'phase_evidence_path':None,'duplicate_cached':None,'selected':None})
    trial_groups=defaultdict(list); nontrial=[]
    for row in rows:
        if row.get('event_scope')=='tuning_trial' and row.get('trial_index') is not None:
            trial_groups[(row.get('task_key'),str(row.get('trial_index')))].append(row)
        else: nontrial.append(row)
    for group in trial_groups.values():
        rank=lambda r:(r.get('phase_seconds') is not None,r.get('peak_tree_rss_kib') is not None,r.get('trial_seconds') is not None,bool(r.get('raw_reason')))
        chosen=max(group,key=rank)
        chosen['attempt_ids_with_this_trial_history']=_json_cell(sorted({r.get('attempt_id') for r in group if r.get('attempt_id')}))
        chosen['duplicate_attempt_history_rows_collapsed']=len(group)-1
        nontrial.append(chosen)
    cutoffs=_terminal_worker_cutoff_rows(runtime,tasks)
    for cutoff in cutoffs:
        for row in nontrial:
            if row.get('task_key')==cutoff['task_key']:
                row['terminal_worker_cutoff_after_trial']=cutoff['aborted_trial_index']
                row['terminal_worker_cutoff_phase']=cutoff['cutoff_phase']
                row['terminal_worker_cutoff_reason']=cutoff['failure_reason']
                row['terminal_worker_peak_tree_rss_bytes']=cutoff['peak_tree_rss_bytes']
                row['nominal_trial_budget']=cutoff['nominal_trial_budget']
                row['actually_started_trial_count']=cutoff['actually_started_trial_count']
                row['completed_trial_count']=cutoff['completed_trial_count']
                row['recorded_selection_trial_count']=cutoff['recorded_selection_trial_count']
                row['candidate_count']=cutoff['actually_started_trial_count']
                row['candidate_count_semantics']='started tuning slots; includes a worker-aborted tuning trial when applicable; not completed selection records'
        base={'task_key':cutoff['task_key'],'experiment':cutoff['experiment'],'rep':cutoff['rep'],'method':cutoff['method'],
          'route':cutoff['route'],'condition':cutoff['condition'],'status':'scientific_failure','validation_state':'validated_terminal_outcome',
          'cell_failure_evidence_type':'memory_rss','cell_raw_reason':cutoff['failure_reason'],'attempt_id':cutoff['attempt_id'],
          'history_state':'terminal_cutoff_overlay','candidate_count':cutoff['actually_started_trial_count'],
          'candidate_count_semantics':'started tuning slots; includes a worker-aborted tuning trial when applicable; not completed selection records',
          'nominal_trial_budget':cutoff['nominal_trial_budget'],'actually_started_trial_count':cutoff['actually_started_trial_count'],
          'completed_trial_count':cutoff['completed_trial_count'],'recorded_selection_trial_count':cutoff['recorded_selection_trial_count'],
          'terminal_worker_cutoff_after_trial':cutoff['aborted_trial_index'],'terminal_worker_cutoff_phase':cutoff['cutoff_phase'],
          'terminal_worker_cutoff_reason':cutoff['failure_reason'],'terminal_worker_peak_tree_rss_bytes':cutoff['peak_tree_rss_bytes'],
          'trial_failure_event':False,'event_counts_as_cell_failure':True,'cell_outcome':'scientific_failure'}
        if cutoff['cutoff_phase']=='trial':
            nontrial.append({**base,'cutoff_record_type':'actual_assigned_trial','trial_number_assigned':True,
              'trial_index':cutoff['aborted_trial_index'],'trial_status':'worker_resource_policy_aborted',
              'raw_trial_state_status':cutoff['aborted_trial_last_state_status'],'trial_score':None,
              'trial_params':cutoff['aborted_trial_params'],'trial_seconds':None,'failure_evidence_type':'memory_rss',
              'event_scope':'worker_trial_cutoff','phase':f"trial_{cutoff['aborted_trial_index']}",
              'phase_reason':cutoff['failure_reason'],'phase_seconds':None,
              'phase_last_observed_elapsed_seconds':cutoff['aborted_trial_last_observed_elapsed_seconds'],
              'peak_tree_rss_kib':cutoff['aborted_trial_last_observed_peak_tree_rss_kib'],
              'peak_tree_rss_bytes':cutoff['peak_tree_rss_bytes'],'phase_evidence_path':cutoff['cutoff_phase_state_path']})
        else:
            nontrial.append({**base,'cutoff_record_type':'actual_final_fit_phase','trial_number_assigned':False,
              'trial_index':None,'trial_status':'worker_resource_policy_aborted','trial_score':None,'trial_params':None,
              'trial_seconds':None,'failure_evidence_type':'memory_rss','event_scope':'worker_final_fit_cutoff',
              'phase':'final_fit','phase_reason':cutoff['failure_reason'],'phase_seconds':None,
              'phase_last_observed_elapsed_seconds':cutoff['last_observed_phase_elapsed_seconds'],
              'peak_tree_rss_kib':cutoff['last_observed_phase_peak_tree_rss_kib'],
              'peak_tree_rss_bytes':cutoff['peak_tree_rss_bytes'],'phase_evidence_path':cutoff['cutoff_phase_state_path']})
        for slot in cutoff['unattempted_nominal_slot_indices']:
            nontrial.append({**base,'cutoff_record_type':'unattempted_nominal_budget_slot','trial_index':None,
              'nominal_slot_index':slot,'budget_slot_index':slot,'trial_number_assigned':False,
              'trial_status':'not_attempted_terminal_worker_failure','raw_trial_state_status':None,
              'trial_score':None,'trial_params':None,'trial_seconds':None,'failure_evidence_type':'not_applicable',
              'event_scope':'nominal_budget_slot','phase':None,
              'phase_reason':'worker terminated before this nominal slot was requested','phase_seconds':None,
              'phase_last_observed_elapsed_seconds':None,'peak_tree_rss_kib':None,'peak_tree_rss_bytes':None,
              'phase_evidence_path':None,'event_counts_as_cell_failure':False})
    return nontrial

def _resource_failure_rows(runtime,tasks):
    runtime=Path(runtime);events=[]
    selection_rows=_model_selection_rows(runtime,tasks)
    for row in selection_rows:
        if row.get('trial_failure_event'):
            events.append({k:row.get(k) for k in ('task_key','experiment','rep','method','route','condition','event_scope','trial_index','trial_status','failure_evidence_type','raw_reason','cell_outcome','event_counts_as_cell_failure','phase','phase_reason','phase_seconds','trial_seconds','peak_tree_rss_kib','phase_exit_code','phase_evidence_path','source_provenance')})
    cutoffs={x['task_key']:x for x in _terminal_worker_cutoff_rows(runtime,tasks)}
    for task in tasks:
        if not isinstance(task,dict): continue
        cutoff=cutoffs.get(task.get('key'))
        if cutoff:
            events.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'event_scope':'worker_level_terminal','trial_index':cutoff['aborted_trial_index'],'trial_status':'worker_resource_policy_aborted','failure_evidence_type':'memory_rss','raw_reason':_sanitize_reason(cutoff['failure_reason']),'cell_outcome':'scientific_failure','event_counts_as_cell_failure':True,'phase':f"trial_{cutoff['aborted_trial_index']}" if cutoff['cutoff_phase']=='trial' else 'final_fit','phase_reason':cutoff['failure_reason'],'phase_seconds':None,'trial_seconds':None,'peak_tree_rss_kib':cutoff['last_observed_phase_peak_tree_rss_kib'],'peak_tree_rss_bytes':cutoff['peak_tree_rss_bytes'],'phase_exit_code':None,'phase_evidence_path':cutoff['cutoff_phase_state_path'],'source_provenance':'supervisor terminal registry record plus matching attempt and active phase state','worker_finished_utc':cutoff['terminal_finished_utc'],'worker_observed_utc':cutoff['terminal_observed_utc'],'linked_trial_index':cutoff['aborted_trial_index'],'last_observed_phase_elapsed_seconds':cutoff['last_observed_phase_elapsed_seconds'],'last_observed_phase_peak_tree_rss_kib':cutoff['last_observed_phase_peak_tree_rss_kib'],'nominal_trial_budget':cutoff['nominal_trial_budget'],'actually_started_trial_count':cutoff['actually_started_trial_count'],'completed_trial_count':cutoff['completed_trial_count'],'unattempted_nominal_slots':cutoff['unattempted_nominal_slots'],'unattempted_nominal_slot_indices':cutoff['unattempted_nominal_slot_indices'],'worker_peak_rss_source':'registry peak_tree_rss_bytes; no OS OOM inferred'})
        incident=_serialization_recovery_incident(runtime,task)
        if incident:
            # Preserve the original RSS phase as an operationally invalidated incident record.
            events.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'event_scope':'operationally_invalid_superseded','trial_index':None,'trial_status':'superseded_after_validated_checkpoint_recovery','failure_evidence_type':'operational_validation_defect','raw_reason':_sanitize_reason(incident.get('reason')),'cell_outcome':'operationally_invalid','event_counts_as_cell_failure':False,'phase':'final_fit','phase_reason':incident.get('phase_reason'),'phase_seconds':incident.get('phase_seconds'),'trial_seconds':None,'peak_tree_rss_kib':incident.get('peak_tree_rss_kib'),'phase_exit_code':incident.get('phase_exit_code'),'phase_evidence_path':str(incident.get('phase_path').resolve().relative_to(runtime.resolve())) if incident.get('phase_path') else None,'source_provenance':'checkpoint_recovery_provenance.json; incident manifest'})
        if task.get('kind')!='fit' and not task.get('scientific_case'):continue
        outcome=_effective_status(task)
        if outcome not in FAILURE_STATES or incident or cutoff:continue
        art=_task_artifact(runtime,task);doc=_task_result(art,task.get('kind'));reason=_task_reason(task,doc);typ=_failure_evidence_type(outcome,reason)
        events.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'event_scope':'scientific_case' if task.get('scientific_case') else 'fit_cell','trial_index':None,'trial_status':None,'failure_evidence_type':typ,'raw_reason':_sanitize_reason(reason),'cell_outcome':outcome,'event_counts_as_cell_failure':True,'phase':None,'phase_reason':None,'phase_seconds':None,'trial_seconds':None,'peak_tree_rss_kib':None,'phase_exit_code':None,'phase_evidence_path':None,'source_provenance':(task.get('source_metadata') or {}).get('provenance') if isinstance(task.get('source_metadata'),dict) else None})
    # Checkpoint migrations can copy the same Optuna failure into multiple attempt manifests.
    # Keep one failure event per fit/trial identity in resource counts, preferring its phase receipt.
    dedup={}
    other=[]
    for row in events:
        if row.get('event_scope')!='tuning_trial' or row.get('trial_index') is None:
            other.append(row);continue
        k=(row.get('task_key'),str(row.get('trial_index')))
        rank=(row.get('phase_seconds') is not None,row.get('peak_tree_rss_kib') is not None,bool(row.get('raw_reason')))
        old=dedup.get(k)
        if old is None or rank>(old[0]):dedup[k]=(rank,row)
    events=other+[v[1] for v in dedup.values()]
    summary=defaultdict(list)
    for row in events:
        if row.get('event_scope')=='operationally_invalid_superseded': continue
        summary[(row.get('experiment'),row.get('failure_evidence_type'),row.get('event_scope'))].append(row)
    counts=[]
    for (exp,typ,scope),rs in sorted(summary.items(),key=lambda kv:tuple('' if x is None else str(x) for x in kv[0])):
        fit_success={x.get('task_key') for x in rs if x.get('event_scope')=='tuning_trial' and x.get('cell_outcome')=='successful'}
        cell_fail={x.get('task_key') for x in rs if x.get('event_counts_as_cell_failure') is True}
        counts.append({'experiment':exp,'failure_evidence_type':typ,'event_scope':scope,'failure_event_count':len(rs),'unique_task_count':len({x.get('task_key') for x in rs}),'terminal_cell_failure_task_count':len(cell_fail),'successful_fit_tasks_with_failed_trial_count':len(fit_success),'timeout_event_count':sum(x.get('failure_evidence_type')=='timeout' for x in rs),'memory_rss_event_count':sum(x.get('failure_evidence_type')=='memory_rss' for x in rs),'trial_timeout_event_count':sum(x.get('failure_evidence_type')=='timeout' and x.get('event_scope')=='tuning_trial' for x in rs),'trial_memory_rss_event_count':sum(x.get('failure_evidence_type')=='memory_rss' and x.get('event_scope')=='tuning_trial' for x in rs),'worker_terminal_memory_rss_event_count':sum(x.get('failure_evidence_type')=='memory_rss' and x.get('event_scope')=='worker_level_terminal' for x in rs)})
    return events,counts

def _serialization_recovery_incident(runtime, task):
    """Return an evidence-backed reporting overlay for the known duplicate-copy validation defect."""
    if task.get('key') != 'e3/rep_1/fit/synthetic/random_forest/copula':
        return None
    art=_task_artifact(Path(runtime),task)
    provenance=_read_json(art/'checkpoint_recovery_provenance.json')
    if not provenance or provenance.get('validation_status')!='validated_single_copy_under_10GiB_600s':
        return None
    incident=_read_json(Path(runtime)/'manifests/incidents/serialization_validation_20261025/incident.json')
    if not incident:
        return None
    if incident.get('task_key') not in (None,task.get('key')): return None
    if incident.get('original_inner_attempt_id') not in (None,provenance.get('original_attempt_id')): return None
    if incident.get('original_pipeline_sha256') not in (None,provenance.get('pipeline_sha256')): return None
    attempt=art/'attempts'/str(provenance.get('original_attempt_id'))
    phase=_read_json(attempt/'phase_final_fit_result.json') or {}
    return {'incident_id':incident.get('incident_id'),'reason':incident.get('classification') or provenance.get('reason'),
            'original_attempt_id':provenance.get('original_attempt_id'),'pipeline_sha256':provenance.get('pipeline_sha256'),
            'validation_status':provenance.get('validation_status'),'phase_seconds':phase.get('seconds'),
            'peak_tree_rss_kib':phase.get('peak_tree_rss_kib'),'phase_exit_code':phase.get('exit_code'),
            'phase_reason':phase.get('reason'),'phase_path':attempt/'phase_final_fit_result.json'}

def _prediction_semantics(rec,e):
    """Return documented score, nonconformity, and prediction rules without loading a model."""
    ev=e if isinstance(e,dict) else {}
    rec=rec if isinstance(rec,dict) else {}
    method=str(rec.get('method') or '').lower().replace('-','_')
    score=ev.get('score_kind') or rec.get('score_kind')
    if score in {'margin','decision_function','native_margin'}: score='native_margin'
    elif score in {'probabilities','predict_proba','probability'}: score='probability'
    else: score='native_margin' if method in {'linear_svm','rbf_svm'} else ('probability' if method else None)
    defaults={
        'probability':('one_minus_true_class_probability','argmax_fixed_class_order_probability'),
        'native_margin':('negative_true_class_margin','argmax_fixed_class_order_margin'),
    }
    nonconformity=ev.get('nonconformity_rule') or rec.get('nonconformity_rule')
    prediction=ev.get('prediction_rule') or rec.get('prediction_rule')
    if score in defaults:
        nonconformity=nonconformity or defaults[score][0]
        prediction=prediction or defaults[score][1]
    return {'score_kind':score,'nonconformity_rule':nonconformity,'prediction_rule':prediction}

def _task_row(rec,e,runtime=None):
    row={k:rec.get(k) for k in ('key','experiment','rep','method','condition','route','mode','target_class','ratio','treatment','mechanism','rate','generator','scientific_case','status','validation_state','artifact_dir')}
    incident=_serialization_recovery_incident(runtime,rec) if runtime is not None else None
    row.update(_prediction_semantics(rec,e))
    row['outcome']=_effective_status(rec)
    row['balanced_accuracy']=_metric(e,'balanced_accuracy') if e else None
    row['coverage']=_metric(e,'coverage') if e else None; row['set_size']=_metric(e,'set_size') if e else None
    row['test_n']=e.get('test_n') if e else None; row['calibration_n']=e.get('calibration_n') if e else None
    row['calibration_fallback_count']=e.get('calibration_fallback_count') if e else None; row['test_fallback_count']=e.get('test_fallback_count') if e else None
    row['test_fallback_per_class']=e.get('test_fallback_per_class') if e else None; row['support_diagnostic_completion']=e.get('support_diagnostic_completion') if e else None
    best,best_ba,all_ba=_e6_tuning_summary(rec)
    row['tuning_best_member']=best; row['tuning_best_member_balanced_accuracy']=best_ba; row['member_tuning_balanced_accuracies']=all_ba
    reason=_task_reason(rec)
    row['unavailability_reason']=_sanitize_reason(reason)
    row['failure_raw_reason']=_sanitize_reason(reason)
    row['failure_evidence_type']=_failure_evidence_type(row['outcome'],reason)
    if incident:
        row['superseded_attempt_id']=incident['original_attempt_id']
        row['superseded_phase']='final_fit'
        row['superseded_phase_classification']='operationally_invalid_post_save_validation_memory_duplication'
        row['validated_recovery_pipeline_sha256']=incident['pipeline_sha256']
    return row
def _summary(rows):
    out=[]
    groups=defaultdict(list)
    for r in rows:
        if r.get('scientific_case'): groups[(r.get('experiment'),r.get('method'),r.get('condition'),r.get('route'),r.get('mode'),r.get('target_class'),r.get('ratio'),r.get('treatment'),r.get('mechanism'),r.get('rate'),r.get('generator'))].append(r)
    for key,rs in sorted(groups.items(),key=lambda x:tuple('' if v is None else str(v) for v in x[0])):
        rr={'experiment':key[0],'method':key[1],'condition':key[2],'route':key[3],'mode':key[4],'target_class':key[5],'ratio':key[6],'treatment':key[7],'mechanism':key[8],'rate':key[9],'generator':key[10],'planned':len(rs),'successful':sum(r.get('outcome')=='successful' and r['balanced_accuracy'] is not None for r in rs),'failed_or_interrupted':sum(r.get('outcome') in {'scientific_failure','operationally_interrupted','operationally_invalid'} for r in rs),'unsupported':sum(r.get('outcome')=='unsupported' for r in rs),'unavailable_dependency':sum(r.get('outcome')=='unavailable_dependency' for r in rs),'pending_or_active':sum(r.get('outcome',r.get('status')) in {'planned','waiting_for_dependency','running','user_stopped','packaging_pending'} for r in rs)}
        for m in METRICS:
            vals=[r[m] for r in rs if r[m] is not None]
            rr[m+'_n']=len(vals); rr[m+'_mean']=statistics.mean(vals) if vals else None; rr[m+'_sample_sd']=statistics.stdev(vals) if len(vals)>1 else None
        out.append(rr)
    return out
def _paired(rows):
    """Create repetition-level contrasts using experiment-specific matching keys."""
    by_exp=defaultdict(list)
    for r in rows:
        if r.get('balanced_accuracy') is not None: by_exp[r.get('experiment')].append(r)
    out=[]
    def contrast(exp,base,a,b,ra,rb):
        rec={'experiment':exp,'rep':base[0],'condition':str(base[1:]),'arm_a':a,'arm_b':b}
        for m in METRICS:
            rec[f'paired_{m}_difference_a_minus_b']=None if ra.get(m) is None or rb.get(m) is None else ra[m]-rb[m]
        out.append(rec)
    for exp,rs in by_exp.items():
        if exp==3:
            # Real-only learner fits are shared across generator families; match them by repetition and learner.
            synth=[r for r in rs if 'synthetic' in str(r.get('route') or '').lower()]
            real=[r for r in rs if 'real' in str(r.get('route') or '').lower()]
            direct=[r for r in rs if str(r.get('route') or '').lower().startswith('direct')]
            for srow in synth:
                gen=srow.get('generator') or srow.get('condition'); rep=srow.get('rep'); learner=srow.get('method')
                rrows=[r for r in real if r.get('rep')==rep and r.get('method')==learner]
                drows=[r for r in direct if r.get('rep')==rep and (r.get('generator') or r.get('method'))==gen]
                for rrow in rrows:
                    contrast(exp,(rep,gen,learner),'synthetic_only','real_only',srow,rrow)
                for drow in drows:
                    contrast(exp,(rep,gen,learner),'synthetic_only','direct_bayes',srow,drow)
                    for rrow in rrows: contrast(exp,(rep,gen,learner),'real_only','direct_bayes',rrow,drow)
        elif exp==4:
            # Same repetition, target class, severity and downstream method; contrast treatments/routes.
            grouped=defaultdict(dict)
            for r in rs:
                base=(r.get('rep'),r.get('target_class'),r.get('ratio'),r.get('condition'),r.get('method'))
                arm=r.get('treatment') or r.get('route') or r.get('method')
                grouped[base][str(arm)]=r
            for base,arms in grouped.items():
                names=sorted(arms)
                for i,a in enumerate(names):
                    for b in names[i+1:]: contrast(exp,base,a,b,arms[a],arms[b])
        elif exp==5:
            # Corruption cases pair against the corresponding clean pipeline and by matched rate/repetition.
            grouped=defaultdict(list)
            for r in rs:
                grouped[(r.get('rep'),r.get('method'),r.get('route'),r.get('generator'),r.get('condition'))].append(r)
            # Also pair all available methods against the same clean route within each repetition.
            for r in rs:
                if not r.get('mechanism') or r.get('mechanism')=='clean': continue
                clean=[c for c in rs if c.get('rep')==r.get('rep') and c.get('method')==r.get('method') and c.get('route')==r.get('route') and c.get('generator')==r.get('generator') and (c.get('condition') in {'clean','clean_control','control'} or c.get('mechanism')=='clean')]
                for c in clean:
                    contrast(exp,(r.get('rep'),r.get('method'),r.get('route'),r.get('generator'),r.get('mechanism'),r.get('rate')),'corrupted','clean_control',r,c)
        elif exp==6:
            grouped=defaultdict(list)
            for r in rs: grouped[(r.get('rep'),)].append(r)
            for base,grp in grouped.items():
                members={str(r.get('method')):r for r in grp if r.get('route')=='member' or r.get('condition')=='member_reference'}
                ensembles=[r for r in grp if r.get('mode') in {'equal','learned'} or r.get('condition') in {'equal','learned'}]
                for i,a in enumerate(ensembles):
                    amode=str(a.get('mode') or a.get('condition'))
                    for name,mr in members.items(): contrast(exp,base,amode,name,a,mr)
                    best=a.get('tuning_best_member')
                    if best and best in members: contrast(exp,base,amode,'tuning_best_'+best,a,members[best])
                    for b in ensembles[i+1:]: contrast(exp,base,amode,str(b.get('mode') or b.get('condition')),a,b)
    return out

def _e4_paired_controls(case_rows, class_rows=()):
    """E4 altered-vs-unchanged and treatment-vs-untreated pairs; retain unmatched plans."""
    direct={(r.get("rep"),r.get("method"),r.get("target_class"),r.get("ratio")):r
            for r in case_rows if r.get("experiment")==4 and r.get("route")=="direct"
            and r.get("condition") not in {"control","unchanged_control"}}
    controls={(r.get("rep"),r.get("method")):r
              for r in case_rows if r.get("experiment")==4 and r.get("condition") in {"control","unchanged_control"}}
    out=[]
    classes={str(r.get("key"))+"|"+str(r.get("class_id")):r for r in class_rows}
    def emit(a,b,comparison):
        ready=bool(a.get("outcome")=="successful" and b and b.get("outcome")=="successful" and a.get("balanced_accuracy") is not None and b.get("balanced_accuracy") is not None)
        why="paired" if ready else ("no_matching_control" if b is None else "one_or_both_evaluations_unavailable")
        z={"experiment":4,"rep":a.get("rep"),"method":a.get("method"),
           "target_class":a.get("target_class"),"ratio":a.get("ratio"),
           "condition":a.get("condition"),"treatment":a.get("treatment") or a.get("route"),
           "comparison":comparison,"case_key":a.get("key"),"control_key":b.get("key") if b else None,
           "case_status":a.get("outcome") or a.get("status"),
           "control_status":(b.get("outcome") or b.get("status")) if b else None,
           "case_reason":a.get("unavailability_reason"),"control_reason":b.get("unavailability_reason") if b else None,
           "paired_available":ready,"pair_status":why}
        for metric in METRICS:
            av=a.get(metric); bv=b.get(metric) if b else None
            z["case_"+metric]=av; z["control_"+metric]=bv
            z["paired_"+metric+"_difference_a_minus_b"]=(av-bv) if ready and av is not None and bv is not None else None
        ca=classes.get(str(a.get("key"))+"|"+str(a.get("target_class"))) if a.get("target_class") is not None else None
        cb=classes.get(str(b.get("key"))+"|"+str(a.get("target_class"))) if b and a.get("target_class") is not None else None
        for metric in ("recall","coverage"):
            av=ca.get(metric) if ca else None; bv=cb.get(metric) if cb else None
            z["case_target_class_"+metric]=av; z["control_target_class_"+metric]=bv
            z["paired_target_class_"+metric+"_difference_a_minus_b"]=(av-bv) if ready and av is not None and bv is not None else None
        out.append(z)
    for a in case_rows:
        if a.get("experiment")!=4 or a.get("condition") in {"control","unchanged_control"}: continue
        rep,method=a.get("rep"),a.get("method")
        control=controls.get((rep,method))
        if a.get("route")=="direct":
            emit(a,control,"altered_direct_minus_unchanged_control")
        elif a.get("route")=="treatment":
            untreated=direct.get((rep,method,a.get("target_class"),a.get("ratio")))
            emit(a,untreated,"treatment_minus_untreated_altered")
            emit(a,control,"treatment_minus_unchanged_control")
    return out

def _e5_paired_metrics(case_rows):
    """Overall E5 corruption-minus-clean contrasts keyed to the matching clean pipeline."""
    clean=[r for r in case_rows if r.get("scientific_case") and r.get("experiment")==5 and
           (r.get("condition") in {"clean","clean_control","control"} or r.get("mechanism")=="clean")]
    out=[]
    for a in case_rows:
        if not a.get("scientific_case") or a.get("experiment")!=5 or not a.get("mechanism") or a.get("mechanism")=="clean": continue
        cand=[b for b in clean if b.get("rep")==a.get("rep") and b.get("method")==a.get("method") and b.get("route")==a.get("route") and b.get("generator")==a.get("generator")]
        b=cand[0] if len(cand)==1 else None
        ready=bool(b and a.get("outcome")=="successful" and b.get("outcome")=="successful" and a.get("balanced_accuracy") is not None and b.get("balanced_accuracy") is not None)
        reason="paired" if ready else "no_unique_clean_reference" if b is None else "corrupted_evaluation_unavailable" if a.get("outcome")!="successful" else "clean_evaluation_unavailable"
        row={"rep":a.get("rep"),"method":a.get("method"),"route":a.get("route"),"generator":a.get("generator"),"mechanism":a.get("mechanism"),"rate":a.get("rate"),"corrupted_key":a.get("key"),"corrupted_status":a.get("outcome") or a.get("status"),"corrupted_reason":a.get("unavailability_reason") or a.get("failure_raw_reason"),"clean_key":b.get("key") if b else None,"clean_status":(b.get("outcome") or b.get("status")) if b else None,"clean_reason":(b.get("unavailability_reason") or b.get("failure_raw_reason")) if b else None,"paired_available":ready,"pair_status":reason}
        for metric in METRICS:
            av=a.get(metric);bv=b.get(metric) if b else None
            row["corrupted_"+metric]=av;row["clean_"+metric]=bv
            row["paired_"+metric+"_difference_a_minus_b"]=(av-bv) if ready and av is not None and bv is not None else None
        out.append(row)
    return out

def _paired_per_class(case_rows, class_rows):
    """E5 corruption-minus-clean per-class contrasts with explicit unmatched states."""
    classes={str(r.get("key"))+"|"+str(r.get("class_id")):r for r in class_rows}
    cases_by_key={str(r.get("key")):r for r in case_rows}
    clean_cases=[r for r in case_rows if r.get("scientific_case") and r.get("experiment")==5 and
                 (r.get("condition") in {"clean","clean_control","control"} or r.get("mechanism")=="clean")]
    out=[]
    for corrupt in case_rows:
        if not corrupt.get("scientific_case") or corrupt.get("experiment")!=5 or not corrupt.get("mechanism") or corrupt.get("mechanism")=="clean":
            continue
        candidates=[c for c in clean_cases if c.get("rep")==corrupt.get("rep")
                    and c.get("method")==corrupt.get("method")
                    and c.get("route")==corrupt.get("route")
                    and c.get("generator")==corrupt.get("generator")]
        clean=candidates[0] if len(candidates)==1 else None
        for class_id in ("0","1","2","3","4","5","6"):
            a=classes.get(str(corrupt.get("key"))+"|"+class_id)
            b=classes.get(str(clean.get("key"))+"|"+class_id) if clean else None
            ready=bool(a and b and cases_by_key.get(str(corrupt.get("key")),{}).get("outcome")=="successful" and cases_by_key.get(str(clean.get("key")),{}).get("outcome")=="successful")
            reason=("paired" if ready else
                    "no_unique_clean_reference" if clean is None else
                    "corrupted_evaluation_unavailable" if a is None or cases_by_key.get(str(corrupt.get("key")),{}).get("outcome")!="successful" else
                    "clean_evaluation_unavailable")
            out.append({
                "experiment":5,"rep":corrupt.get("rep"),"method":corrupt.get("method"),
                "route":corrupt.get("route"),"generator":corrupt.get("generator"),
                "mechanism":corrupt.get("mechanism"),"rate":corrupt.get("rate"),
                "class_id":class_id,"corrupted_key":corrupt.get("key"),
                "corrupted_status":corrupt.get("outcome") or corrupt.get("status"),"corrupted_reason":corrupt.get("unavailability_reason") or corrupt.get("failure_raw_reason"),
                "clean_key":clean.get("key") if clean else None,
                "clean_status":(clean.get("outcome") or clean.get("status")) if clean else None,
                "clean_reason":(clean.get("unavailability_reason") or clean.get("failure_raw_reason")) if clean else None,
                "paired_available":ready,"pair_status":reason,
                "corrupted_recall":a.get("recall") if a else None,"clean_recall":b.get("recall") if b else None,
                "recall_difference_a_minus_b":(a.get("recall")-b.get("recall")) if ready and a.get("recall") is not None and b.get("recall") is not None else None,
                "corrupted_coverage":a.get("coverage") if a else None,"clean_coverage":b.get("coverage") if b else None,
                "coverage_difference_a_minus_b":(a.get("coverage")-b.get("coverage")) if ready and a.get("coverage") is not None and b.get("coverage") is not None else None,
                "corrupted_set_size":a.get("set_size") if a else None,
                "clean_set_size":b.get("set_size") if b else None,
                "set_size_difference_a_minus_b":(a.get("set_size")-b.get("set_size")) if ready and a.get("set_size") is not None and b.get("set_size") is not None else None,
            })
    return out

def _condition_paired_summary(rows, key_fields, value_fields, planned_repetitions=3):
    """Summarize only matched repetition contrasts within exact scientific strata."""
    groups=defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k) for k in key_fields)].append(row)
    out=[]
    for key,group in sorted(groups.items(),key=lambda kv:tuple("" if v is None else str(v) for v in kv[0])):
        z={k:v for k,v in zip(key_fields,key)}
        reps={str(r.get("rep")) for r in group}
        z["planned_repetitions"]=planned_repetitions
        z["rows"]=len(group)
        z["available_repetitions"]=sum(bool(r.get("paired_available")) for r in group)
        z["unmatched_repetitions"]=max(0,planned_repetitions-z["available_repetitions"])
        for field in value_fields:
            vals=[float(r[field]) for r in group if r.get("paired_available") and r.get(field) is not None]
            z[field+"_n"]=len(vals)
            z[field+"_mean"]=statistics.mean(vals) if vals else None
            z[field+"_sample_sd"]=statistics.stdev(vals) if len(vals)>1 else None
        out.append(z)
    return out

def _mean_sd(values):
    vals=[float(x) for x in values]
    return (statistics.mean(vals), statistics.stdev(vals) if len(vals)>1 else None)

def _paired_summary(rows):
    metrics=[k for k in rows[0] if k.startswith('paired_') and k.endswith('_difference_a_minus_b')] if rows else []
    keys=[k for k in (rows[0].keys() if rows else []) if k not in metrics and k!='rep']
    groups=defaultdict(list)
    for r in rows: groups[tuple(r.get(k) for k in keys)].append(r)
    out=[]
    for key,rs in groups.items():
        z={k:v for k,v in zip(keys,key)}; z['paired_repetitions']=len(rs)
        for m in metrics:
            vals=[r[m] for r in rs if r.get(m) is not None]
            z[m+'_n']=len(vals); z[m+'_mean']=statistics.mean(vals) if vals else None; z[m+'_sample_sd']=statistics.stdev(vals) if len(vals)>1 else None
        out.append(z)
    return out

def _task_artifact(runtime,task):
    # Treat artifact_dir as provenance only; resolve beneath the caller's extracted runtime.
    rt=Path(runtime).resolve()
    key=task.get('key')
    if not isinstance(key,str) or not key or any(part in ('','.','..') for part in key.split('/')):
        raise ValueError('invalid task key for artifact path')
    root=(rt/'artifacts').resolve(); target=(root/key).resolve()
    try: target.relative_to(root)
    except ValueError: raise ValueError('task key escapes runtime artifact root')
    return target
def _task_result(artifact,kind):
    names={'fit':'fit_result.json','generate':'generation_result.json','eval':'eval_result.json','ensemble':'evaluation.json','alias':'evaluation.json'}
    p=artifact/names.get(kind,'result.json')
    return _read_json(p) or {}
def _attempt_dir(artifact,doc,task):
    aid=doc.get('attempt_id')
    if aid:
        p=artifact/'attempts'/str(aid)
        if p.exists(): return p
    dirs=[p for p in (artifact/'attempts').glob('*') if p.is_dir()] if (artifact/'attempts').exists() else []
    return max(dirs,key=lambda p:p.stat().st_mtime) if dirs else None
def _phase_info(p):
    d=_read_json(p) or {}
    if not d: return None
    return {'seconds':d.get('seconds'),'peak_tree_rss_kib':d.get('peak_tree_rss_kib'),'exit_code':d.get('exit_code'),'reason':d.get('reason'),'phase':d.get('phase')}
def _task_wall_seconds(task):
    from datetime import datetime
    a=task.get('started_utc'); b=task.get('finished_utc')
    try: return max(0.0,(datetime.fromisoformat(str(b).replace('Z','+00:00'))-datetime.fromisoformat(str(a).replace('Z','+00:00'))).total_seconds())
    except Exception: return None
def _cost_rows(runtime,tasks):
    runtime=Path(runtime); rows=[]; task_by_key={str(t.get('key')):t for t in tasks if isinstance(t,dict)}
    for task in tasks:
        if not isinstance(task,dict): continue
        kind=task.get('kind'); artifact=_task_artifact(runtime,task); doc=_task_result(artifact,kind); result=doc.get('result',{}) if isinstance(doc.get('result'),dict) else {}
        attempt=_attempt_dir(artifact,doc,task); phases={}
        if attempt:
            for p in attempt.glob('phase_*_result.json'):
                info=_phase_info(p)
                if info: phases[p.stem.replace('phase_','').replace('_result','')]=info
        task_outcome=_effective_status(task); task_success=task_outcome=='successful' and task.get('validation_state')=='validated'
        logical_fit=task.get('fit_key') or task.get('source_key')
        if kind=='fit': logical_fit=task.get('key')
        if kind=='ensemble':
            logical_fit=';'.join(str(v) for v in task.get('members',{}).values())
        source=task.get('source_metadata') or {}
        source_prov=(source.get('provenance') if isinstance(source,dict) else None) or task.get('reuse_pipeline') or task.get('selection_source') or task.get('selection_key') or (task_by_key.get(str(logical_fit),{}).get('source_metadata') or {}).get('provenance')
        common={'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'task_kind':kind,'method':task.get('method'),'route':task.get('route'),'condition':task.get('condition'),'generator':task.get('generator'),'mechanism':task.get('mechanism'),'rate':task.get('rate'),'target_class':task.get('target_class'),'treatment':task.get('treatment'),'status':task.get('status'),'outcome':task_outcome,'validation_state':task.get('validation_state'),'task_validated_success':task_success,'logical_source_fit_key':logical_fit,'source_provenance':source_prov,'artifact_dir':str(artifact),'attempt_id':doc.get('attempt_id') or task.get('attempt_id')}
        if kind=='fit':
            route=str(task.get('route') or '')
            if route=='generator' or (task.get('method') in {'gmm','copula','arf','kde','chow_liu'} and route not in {'synthetic','real'} and '/fit/synthetic/' not in str(task.get('key')) and '/fit/real/' not in str(task.get('key'))): stage='generator_fit'
            elif route=='synthetic' or '/fit/synthetic/' in str(task.get('key')): stage='synthetic_only_training'
            elif route=='real' or '/fit/real/' in str(task.get('key')): stage='real_only_training'
            else: stage='downstream_or_direct_training'
            reused=bool(result.get('reused') or task.get('reuse_pipeline'))
            final=phases.get('final_fit',{})
            if not final and isinstance(result.get('phase_supervision'),dict): final=_phase_info_from_dict(result['phase_supervision'])
            selection_doc=_read_json(artifact/'selection.json') or {}
            trials=selection_doc.get('trials',[])
            trial_phases=[(name,info) for name,info in phases.items() if name.startswith('trial_')]
            if trial_phases:
                for name,info in trial_phases:
                    rows.append({**common,'stage':'tuning_trial','logical_stage':stage,'trial_index':name.removeprefix('trial_'),'phase_seconds':info.get('seconds'),'selection_trial_seconds':info.get('seconds'),'model_fit_seconds':None,'generation_seconds':None,'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':info.get('peak_tree_rss_kib'),'phase_exit_code':info.get('exit_code'),'phase_reason':info.get('reason'),'phase_success':info.get('exit_code')==0 and info.get('reason') in (None,''),'reused_pipeline':reused,'actual_model_fit_performed':info.get('exit_code')==0 and info.get('reason') in (None,''),'model_fit_executions':1 if info.get('exit_code')==0 and info.get('reason') in (None,'') else None,'source_path':task.get('reuse_pipeline') or task.get('selection_source')})
            elif trials:
                sec=[float(x.get('seconds')) for x in trials if isinstance(x,dict) and isinstance(x.get('seconds'),(int,float)) and x.get('status')!='duplicate_cached']
                if sec: rows.append({**common,'stage':'tuning_trials_aggregate','logical_stage':stage,'trial_index':None,'phase_seconds':sum(sec),'selection_trial_seconds':sum(sec),'model_fit_seconds':None,'generation_seconds':None,'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':None,'phase_exit_code':None,'phase_reason':'aggregated physical time from selection.json; duplicate_cached copied durations excluded','phase_success':None,'reused_pipeline':reused,'actual_model_fit_performed':any(isinstance(x,dict) and x.get('status')=='success' for x in trials),'model_fit_executions':sum(1 for x in trials if isinstance(x,dict) and x.get('status')=='success') or None,'source_path':task.get('reuse_pipeline') or task.get('selection_source')})
            actual_fit=None if reused else result.get('fit_seconds')
            phase_sec=final.get('seconds')
            rows.append({**common,'stage':'pipeline_reuse' if reused else stage,'logical_stage':stage,'trial_index':None,'phase_seconds':phase_sec,'selection_trial_seconds':None,'model_fit_seconds':0.0 if reused else actual_fit,'generation_seconds':None,'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':phase_sec if reused else None,'peak_tree_rss_kib':final.get('peak_tree_rss_kib'),'phase_exit_code':final.get('exit_code'),'phase_reason':final.get('reason'),'phase_success':(task_success and (reused or actual_fit is not None)),'reused_pipeline':reused,'actual_model_fit_performed':bool(not reused and actual_fit is not None),'model_fit_executions':1 if not reused and actual_fit is not None else None,'source_path':result.get('source') or task.get('reuse_pipeline') or task.get('selection_source')})
        elif kind=='generate':
            phase=result.get('phase_supervision',{}); rows.append({**common,'stage':'generator_generation','logical_stage':'generator_generation','trial_index':None,'phase_seconds':phase.get('seconds'),'selection_trial_seconds':None,'model_fit_seconds':None,'generation_seconds':phase.get('seconds'),'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':phase.get('peak_tree_rss_kib'),'phase_exit_code':phase.get('exit_code'),'phase_reason':phase.get('reason'),'phase_success':task_success and phase.get('exit_code')==0,'reused_pipeline':False,'actual_model_fit_performed':False,'source_path':task.get('fit_key')})
        elif kind=='eval':
            for phase_name,stage in (('calibrate','calibration'),('evaluate','test_inference')):
                info=phases.get(phase_name,{})
                if not info and phase_name=='evaluate' and isinstance(result.get('phase_supervision'),dict): info=_phase_info_from_dict(result['phase_supervision'])
                rows.append({**common,'stage':stage,'logical_stage':stage,'trial_index':None,'phase_seconds':info.get('seconds'),'selection_trial_seconds':None,'model_fit_seconds':None,'generation_seconds':None,'calibration_seconds':info.get('seconds') if stage=='calibration' else None,'inference_seconds':info.get('seconds') if stage=='test_inference' else None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':info.get('peak_tree_rss_kib'),'phase_exit_code':info.get('exit_code'),'phase_reason':info.get('reason'),'phase_success':task_success and info.get('exit_code')==0,'reused_pipeline':False,'actual_model_fit_performed':False,'source_path':task.get('fit_key')})
        elif kind=='ensemble':
            metrics=result if result else _read_json(artifact/'evaluation.json') or {}
            times=metrics.get('phase_times_seconds',{}) if isinstance(metrics,dict) else {}
            for time_key,stage,rss_key in (('tune_seconds','tuning_inference','tune_peak_tree_rss_kib'),('weight_selection_seconds','weight_selection',None),('cal_seconds','calibration','cal_peak_tree_rss_kib'),('test_seconds','test_inference','test_peak_tree_rss_kib')):
                sec=times.get(time_key)
                # E6 timing keys can be prefixed by stage in the ensemble executor.
                alt={'tune_seconds':'tune_seconds','cal_seconds':'cal_seconds','test_seconds':'test_seconds'}.get(time_key)
                if sec is None and time_key=='tune_seconds': sec=times.get('tune_seconds')
                if sec is None and time_key=='cal_seconds': sec=times.get('cal_seconds')
                if sec is None and time_key=='test_seconds': sec=times.get('test_seconds')
                if sec is None and time_key=='weight_selection_seconds': sec=times.get(time_key)
                if sec is not None:
                    rows.append({**common,'stage':stage,'logical_stage':stage,'trial_index':None,'phase_seconds':sec,'selection_trial_seconds':None,'model_fit_seconds':None,'generation_seconds':None,'calibration_seconds':sec if stage=='calibration' else None,'inference_seconds':sec if stage in {'tuning_inference','test_inference'} else None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':times.get(rss_key) if rss_key else None,'phase_exit_code':0,'phase_reason':None,'phase_success':task_success,'reused_pipeline':True,'actual_model_fit_performed':False,'source_path':logical_fit})
        elif kind in {'e4_cohort','e4_treatment','e4_append','e5_corruption'}:
            stage={'e4_cohort':'imbalance_cohort_construction','e4_treatment':'imbalance_treatment_dataset','e4_append':'generated_restoration_append','e5_corruption':'fitting_corruption_construction'}[kind]
            wall=_task_wall_seconds(task)
            rows.append({**common,'stage':stage,'logical_stage':stage,'trial_index':None,'phase_seconds':None,'observed_task_wall_seconds':wall,'selection_trial_seconds':None,'model_fit_seconds':None,'generation_seconds':None,'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':None,'peak_tree_rss_kib':None,'phase_exit_code':None,'phase_reason':'synchronous transform; no subprocess-level RSS phase receipt','phase_success':task_success,'reused_pipeline':False,'actual_model_fit_performed':False,'source_path':task.get('cohort_key') or task.get('generated_key') or task.get('fit_key')})
        elif kind=='alias':
            rows.append({**common,'stage':'evaluation_alias','logical_stage':'evaluation','trial_index':None,'phase_seconds':0.0 if task_success else None,'selection_trial_seconds':None,'model_fit_seconds':0.0 if task_success else None,'generation_seconds':None,'calibration_seconds':None,'inference_seconds':None,'reuse_overhead_seconds':0.0 if task_success else None,'peak_tree_rss_kib':None,'phase_exit_code':0 if task_success else None,'phase_reason':'reused validated evaluation; no new model inference' if task_success else 'alias is not validated; no phase duration claimed','phase_success':task_success,'reused_pipeline':True,'actual_model_fit_performed':False,'source_path':task.get('source_key')})
    for row in rows:
        secs=row.get('phase_seconds')
        if isinstance(secs,(int,float)) and math.isfinite(float(secs)):
            row['phase_observation_status']='observed'
        elif row.get('outcome') in {'planned','waiting_for_dependency','running','user_stopped','packaging_pending'}:
            row['phase_observation_status']='not_attempted_or_not_yet_observed'
        else:
            row['phase_observation_status']='no_valid_phase_receipt'
    return rows

def _phase_info_from_dict(d):
    return {k:d.get(k) for k in ('seconds','peak_tree_rss_kib','exit_code','reason','phase')}
def _cost_summary(rows):
    groups=defaultdict(list)
    keys=('experiment','stage','logical_stage','method','route','condition','generator','mechanism','rate','target_class','treatment')
    for row in rows: groups[tuple(row.get(k) for k in keys)].append(row)
    out=[]
    for key,rs in groups.items():
        item={k:v for k,v in zip(keys,key)}; item['planned_or_observed_phase_rows']=len(rs)
        item['successful_phase_n']=sum(r.get('phase_success') is True for r in rs)
        item['validated_task_success_n']=len({r.get('task_key') for r in rs if r.get('task_validated_success') is True})
        for col in ('phase_seconds','model_fit_seconds','selection_trial_seconds','generation_seconds','calibration_seconds','inference_seconds','reuse_overhead_seconds','peak_tree_rss_kib','model_fit_executions'):
            vals=[float(r[col]) for r in rs if isinstance(r.get(col),(int,float)) and math.isfinite(float(r[col]))]
            item[col+'_n']=len(vals); item[col+'_sum']=sum(vals) if vals else None; item[col+'_mean']=statistics.mean(vals) if vals else None; item[col+'_sample_sd']=statistics.stdev(vals) if len(vals)>1 else None
        out.append(item)
    return out

def _e3_family_series(all_rows,learner,metric,generator):
    def family(row):
        rr=str(row.get('route') or '').lower()
        if rr.startswith('direct'): return 'direct_bayes'
        if 'synthetic' in rr: return 'synthetic_only'
        if 'real' in rr: return 'real_only'
        return None
    def gen(row):
        rr=str(row.get('route') or '').lower()
        return str(row.get('generator') or row.get('method') or '').lower() if rr.startswith('direct') or 'synthetic' in rr else None
    direct={r.get('rep'):r for r in all_rows if r.get('experiment')==3 and r.get('scientific_case') and family(r)=='direct_bayes' and gen(r)==generator and r.get(metric) is not None}
    synth={r.get('rep'):r for r in all_rows if r.get('experiment')==3 and r.get('scientific_case') and family(r)=='synthetic_only' and gen(r)==generator and str(r.get('method'))==learner and r.get(metric) is not None}
    real={r.get('rep'):r for r in all_rows if r.get('experiment')==3 and r.get('scientific_case') and family(r)=='real_only' and str(r.get('method'))==learner and r.get(metric) is not None}
    reps=sorted(set(direct)&set(synth)&set(real),key=lambda x:(str(type(x)),x))
    return reps,([float(direct[x][metric]) for x in reps],[float(synth[x][metric]) for x in reps],[float(real[x][metric]) for x in reps]),(len(direct),len(synth),len(real))

def _e3_footnote_position(ax_position):
    return ((ax_position.x0+ax_position.x1)/2, .025)

def _e3_global_ylim(metric,values):
    vals=[float(x) for x in values if isinstance(x,(int,float)) and math.isfinite(float(x))]
    if metric=='set_size': low_cap,high_cap,pad=0.0,7.0,.05
    else: low_cap,high_cap,pad=0.0,1.0,.015
    if not vals:return (low_cap,high_cap)
    lo=min(vals);hi=max(vals);margin=max(pad,(hi-lo)*.08)
    lo=max(low_cap,lo-margin);hi=min(high_cap,hi+margin)
    if metric=='coverage':lo=min(lo,.9);hi=max(hi,.9)
    if hi<=lo:
        lo=max(low_cap,lo-pad);hi=min(high_cap,hi+pad)
    return lo,hi

def _symmetric_heatmap_limits(matrices):
    import numpy as np
    finite=[]
    for matrix in matrices:
        arr=np.asarray(matrix,dtype=float)
        finite.extend(np.abs(arr[np.isfinite(arr)]).tolist())
    bound=max(max(finite,default=0.0),0.01)
    return (-bound,bound)

def _add_heatmap_colorbar(fig, axes, mappable, label, shrink=.7, pad=.02):
    """Bind one legend to the exact panel group sharing that mappable scale."""
    bar=fig.colorbar(mappable,ax=axes,shrink=shrink,pad=pad)
    bar.set_label(label)
    return bar

def _annotated_heatmap(ax, matrix, row_labels, col_labels, title, limits=None):
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import TwoSlopeNorm
    arr=np.asarray(matrix,dtype=float); masked=np.ma.masked_invalid(arr)
    cmap=plt.get_cmap("coolwarm").with_extremes(bad="#d9d9d9")
    vmin,vmax=limits or _symmetric_heatmap_limits([arr])
    im=ax.imshow(masked,aspect="auto",cmap=cmap,norm=TwoSlopeNorm(vmin=vmin,vcenter=0,vmax=vmax))
    ax.set_title(title,fontsize=9);ax.set_yticks(range(len(row_labels)),row_labels,fontsize=6)
    ax.set_xticks(range(len(col_labels)),col_labels,rotation=35,ha="right",fontsize=6)
    ax.set_xticks([x-.5 for x in range(1,len(col_labels))],minor=True);ax.set_yticks([y-.5 for y in range(1,len(row_labels))],minor=True)
    ax.grid(which="minor",color="white",linewidth=.6);ax.tick_params(which="minor",bottom=False,left=False)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            if np.isfinite(arr[i,j]):ax.text(j,i,f"{arr[i,j]:+.2f}",ha="center",va="center",fontsize=5,color="black")
    return im

def _main_heatmaps(runtime,outdir,rows,class_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    Path(outdir).mkdir(parents=True,exist_ok=True);made=[]
    e4=_e4_paired_controls(rows,class_rows);e5=_e5_paired_metrics(rows)
    classes={"0":"A","1":"F","2":"G","3":"K","4":"M","5":"GALAXY","6":"QSO"}
    treatments=("weighted","ros","smote","generated_gmm","generated_copula","generated_arf","generated_kde","generated_chow_liu")
    metric_defs=[("BA","paired_balanced_accuracy_difference_a_minus_b"),("Target-class recall","paired_target_class_recall_difference_a_minus_b"),("Overall coverage","paired_coverage_difference_a_minus_b"),("Mean set size","paired_set_size_difference_a_minus_b")]
    fig,axs=plt.subplots(4,2,figsize=(20,20),squeeze=False);row_images=[None]*4
    for i,(title,col) in enumerate(metric_defs):
        shared_vals=[float(r[col]) for r in e4 if r.get("comparison")=="treatment_minus_untreated_altered" and r.get("paired_available") and r.get(col) is not None and float(r.get("ratio") or 0) in {0.5,0.1}]
        row_limits=_symmetric_heatmap_limits([shared_vals])
        for j,(ratio,sev) in enumerate(((0.5,"Half share"),(0.1,"One-tenth share"))):
            pairs=[(c,l) for c in range(7) for l in ("logistic","random_forest","hist_gb")]
            labels=[f"{classes[str(c)]} - {learner}" for c,learner in pairs];mat=np.full((21,8),np.nan);counts=np.zeros((21,8),int)
            for ri,(c,learner) in enumerate(pairs):
                for ci,t in enumerate(treatments):
                    q=[r for r in e4 if r.get("comparison")=="treatment_minus_untreated_altered" and str(r.get("target_class"))==str(c) and float(r.get("ratio") or 0)==ratio and r.get("method")==learner and r.get("treatment")==t and r.get("paired_available") and r.get(col) is not None]
                    if q:mat[ri,ci]=statistics.mean(float(r[col]) for r in q);counts[ri,ci]=len(q)
            image=_annotated_heatmap(axs[i,j],mat,labels,treatments,f"{title}: restoration - untreated; {sev}",limits=row_limits)
            row_images[i]=image
            for ri in range(21):
                for ci in range(8):
                    axs[i,j].text(ci,ri+.25,f"{counts[ri,ci]}/3",ha="center",va="center",fontsize=4,color="#444444")
            axs[i,j].set_xlabel("Restoration arm; grey = no matched repetitions (see availability ledger)")
    fig.suptitle("E4 restoration effects by target and learner. Cell labels give matched repetitions / 3; interpret set size with coverage.",fontsize=11)
    fig.tight_layout(rect=(0,0,0.90,.97))
    for i,(title,_) in enumerate(metric_defs):
        _add_heatmap_colorbar(fig,axs[i,:],row_images[i],f"{title} paired difference",shrink=.72,pad=.02)
    p=Path(outdir)/"E4_restoration_effect_heatmaps.png";fig.savefig(p,dpi=180,bbox_inches="tight");plt.close(fig);made.append(str(p))

    methods=sorted({r.get("method") for r in e4 if r.get("comparison")=="altered_direct_minus_unchanged_control"})
    fig,axs=plt.subplots(2,2,figsize=(19,15),squeeze=False);row_images=[None]*2
    for i,(title,col) in enumerate((("BA","paired_balanced_accuracy_difference_a_minus_b"),("Target-class recall","paired_target_class_recall_difference_a_minus_b"))):
        shared_vals=[float(r[col]) for r in e4 if r.get("comparison")=="altered_direct_minus_unchanged_control" and r.get("paired_available") and r.get(col) is not None and float(r.get("ratio") or 0) in {0.5,0.1}]
        row_limits=_symmetric_heatmap_limits([shared_vals])
        for j,(ratio,sev) in enumerate(((0.5,"Half share"),(0.1,"One-tenth share"))):
            mat=np.full((len(methods),7),np.nan);counts=np.zeros_like(mat,dtype=int)
            for ri,method in enumerate(methods):
                for ci in range(7):
                    q=[r for r in e4 if r.get("comparison")=="altered_direct_minus_unchanged_control" and r.get("method")==method and str(r.get("target_class"))==str(ci) and float(r.get("ratio") or 0)==ratio and r.get("paired_available") and r.get(col) is not None]
                    if q:mat[ri,ci]=statistics.mean(float(r[col]) for r in q);counts[ri,ci]=len(q)
            image=_annotated_heatmap(axs[i,j],mat,methods,[classes[str(c)] for c in range(7)],f"Direct {title}: altered - unchanged; {sev}",limits=row_limits)
            row_images[i]=image
            for ri in range(len(methods)):
                for ci in range(7):
                    axs[i,j].text(ci,ri+.25,f"{counts[ri,ci]}/3",ha="center",va="center",fontsize=5,color="#444444")
            axs[i,j].set_xlabel("Target class; grey = no matched repetitions (see availability ledger)")
    fig.suptitle("E4 direct-method effects; every method, target and severity retained. Labels give matched repetitions / 3.",fontsize=11)
    fig.tight_layout(rect=(0,0,0.90,.96))
    for i,(title,_) in enumerate((("BA","paired_balanced_accuracy_difference_a_minus_b"),("Target-class recall","paired_target_class_recall_difference_a_minus_b"))):
        _add_heatmap_colorbar(fig,axs[i,:],row_images[i],f"{title} paired difference",shrink=.78,pad=.02)
    p=Path(outdir)/"E4_direct_method_effect_heatmaps.png";fig.savefig(p,dpi=180,bbox_inches="tight");plt.close(fig);made.append(str(p))

    rates=(.05,.10,.20);mechanisms=("feature_noise","missingness","label_noise")
    methods=sorted({r.get("method") for r in rows if r.get("experiment")==5 and r.get("scientific_case") and r.get("route")=="direct"})
    for mech in mechanisms:
        shared_vals=[float(r["paired_balanced_accuracy_difference_a_minus_b"]) for r in e5 if r.get("mechanism")==mech and r.get("paired_available") and r.get("paired_balanced_accuracy_difference_a_minus_b") is not None]
        mech_limits=_symmetric_heatmap_limits([shared_vals])
        groups=[("direct","Direct methods",methods)]
        for learner in ("logistic","random_forest","hist_gb"):
            gens=sorted({r.get("generator") for r in rows if r.get("experiment")==5 and r.get("scientific_case") and r.get("route")=="synthetic" and r.get("method")==learner and r.get("generator")})
            groups.append((learner,"Synthetic-only - "+learner,gens or ["No planned cases"]))
        fig,axs=plt.subplots(1,4,figsize=(20,10),squeeze=False);image=None
        for ax,(grp,title,labels) in zip(axs[0],groups):
            mat=np.full((len(labels),3),np.nan);counts=np.zeros((len(labels),3),int)
            for ri,label in enumerate(labels):
                if label=="No planned cases": continue
                for ci,rate in enumerate(rates):
                    q=[r for r in e5 if r.get("mechanism")==mech and float(r.get("rate") or 0)==rate and r.get("paired_available") and r.get("paired_balanced_accuracy_difference_a_minus_b") is not None and ((r.get("route")=="direct" and r.get("method")==label) if grp=="direct" else (r.get("route")=="synthetic" and r.get("method")==grp and r.get("generator")==label))]
                    if q:mat[ri,ci]=statistics.mean(float(r["paired_balanced_accuracy_difference_a_minus_b"]) for r in q);counts[ri,ci]=len(q)
            image=_annotated_heatmap(ax,mat,labels,[f"{int(rate*100)}%" for rate in rates],title,limits=mech_limits)
            for ri in range(len(labels)):
                for ci in range(3):
                    ax.text(ci,ri+.25,f"{counts[ri,ci]}/3",ha="center",va="center",fontsize=5,color="#444444")
            ax.set_xlabel("Affected fitting-row rate")
        fig.suptitle(f"E5 {mech}: balanced accuracy difference (corrupted - clean); cell labels show matched n/3.",fontsize=11)
        fig.tight_layout(rect=(0,.055,.90,.95))
        fig.text(.5,.012,"Grey cells have no matched repetitions (0/3); consult the availability ledger. Color values are shown only for evaluated pairs.",ha="center",va="bottom",fontsize=8)
        _add_heatmap_colorbar(fig,axs.ravel().tolist(),image,"Mean paired delta balanced accuracy",shrink=.65,pad=.02)
        p=Path(outdir)/f"E5_{mech}_paired_BA_heatmaps.png";fig.savefig(p,dpi=180,bbox_inches="tight");plt.close(fig);made.append(str(p))
    return made

def _plotting_support_env():
    """Use the recorded frozen-NumPy-first overlay for the static plot subprocess."""
    here=Path(__file__).resolve()
    project_root=next((parent for parent in here.parents
        if (parent/'venv'/'lib'/'python3.12'/'site-packages').is_dir()),here.parents[2])
    overlay=[
        project_root/'venv'/'lib'/'python3.12'/'site-packages',
        Path('/home/ubuntu/.local/lib/python3.12/site-packages'),
        Path('/usr/lib/python3/dist-packages'),
    ]
    env=os.environ.copy()
    env['PYTHONPATH']=os.pathsep.join(str(p) for p in overlay)
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        env[name]='1'
    env['MPLBACKEND']='Agg'
    return env

def _figures(runtime,outdir,rows):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except Exception:
        # The scientific venv omits plotting libraries; the EC2 host system Python
        # has matplotlib. Delegate only static report rendering, never analysis/fitting.
        system_python=Path('/usr/bin/python3')
        if not system_python.exists(): return []
        report_source=Path(__file__).resolve()
        out=Path(outdir); out.mkdir(parents=True,exist_ok=True)
        fd,payload=tempfile.mkstemp(prefix='figure_rows_',suffix='.json',dir=str(out))
        os.close(fd)
        try:
            Path(payload).write_text(json.dumps({'runtime':str(runtime),'outdir':str(out),'rows':rows},allow_nan=False),encoding='utf-8')
            code=("import json,sys; from pathlib import Path; d=json.load(open(sys.argv[1])); "
                  "sys.path.insert(0,str(Path(sys.argv[2]).parent)); import reporting; "
                  "print(json.dumps(reporting._figures(d['runtime'],d['outdir'],d['rows'])))")
            proc=subprocess.run([str(system_python),'-c',code,payload,str(report_source)],capture_output=True,text=True,timeout=180,env=_plotting_support_env())
            if proc.returncode==0:
                return json.loads(proc.stdout.strip().splitlines()[-1])
        except Exception:
            pass
        finally:
            try: Path(payload).unlink()
            except FileNotFoundError: pass
        return []
    made=[]
    def valkey(r,m): return r.get(m)
    d3=[r for r in rows if r.get('experiment')==3 and r.get('scientific_case') and r.get('balanced_accuracy') is not None]
    if d3:
        learners=sorted({str(r.get('method')) for r in d3 if 'synthetic' in str(r.get('route','')).lower() or 'real' in str(r.get('route','')).lower()})
        routes=('direct Bayes','synthetic-only','real-only')
        families=('gmm','copula','arf','kde','chow_liu')
        def route_family(row):
            rr=str(row.get('route') or '').lower()
            if rr.startswith('direct'): return 'direct_bayes'
            if 'synthetic' in rr: return 'synthetic_only'
            if 'real' in rr: return 'real_only'
            return None
        def family_generator(row):
            rr=str(row.get('route') or '').lower()
            return str(row.get('generator') or row.get('method') or '').lower() if rr.startswith('direct') or 'synthetic' in rr else None
        for metric in METRICS:
            fig,axs=plt.subplots(1,max(1,len(learners)),figsize=(7*max(1,len(learners)),5),sharey=True,squeeze=False); axs=axs.ravel()
            global_displayed=[]
            panel_missing={}
            for ax,learner in zip(axs,learners):
                displayed=[]
                missing=[]
                for gi,g in enumerate(families):
                    reps,values,route_ns=_e3_family_series(rows,learner,metric,g)
                    if not reps:
                        missing.append(f'{g} (D/S/R {route_ns[0]}/{route_ns[1]}/{route_ns[2]})')
                        continue
                    displayed.extend(v for route_values in values for v in route_values)
                    means=[statistics.mean(v) for v in values]
                    sds=[statistics.stdev(v) if len(v)>1 else None for v in values]
                    for mu,sd in zip(means,sds):
                        displayed.append(mu)
                        if sd is not None: displayed.extend((mu-sd,mu+sd))
                    global_displayed.extend(displayed)
                    offset=(gi-(len(families)-1)/2)*0.055
                    xs=[0+offset,1+offset,2+offset]
                    color=f'C{gi}'
                    ax.plot(xs,means,marker='o',color=color,label=f'{g} (matched n={len(reps)}; real baseline reused)')
                    for x,mu,sd,vals in zip(xs,means,sds,values):
                        if sd is None: ax.scatter([x],[mu],color=color,s=28,zorder=4)
                        else: ax.errorbar([x],[mu],yerr=[sd],color=color,capsize=3,zorder=3)
                        for v in vals: ax.scatter([x],[v],color=color,s=17,alpha=.45,zorder=2)
                ax.set_title(f'{learner}: family-specific matched triples')
                ax.set_xticks([0,1,2],routes,rotation=18,ha='right')
                ax.grid(axis='y',alpha=.25)
                ax.set_ylabel(metric.replace('_',' ').title() + (' (zoomed axis)' if metric!='set_size' else ''))
                handles,legend_labels=ax.get_legend_handles_labels()
                if handles: ax.legend(handles,legend_labels,fontsize=7)
                if missing:
                    panel_missing[learner]=missing
            ylim=_e3_global_ylim(metric,global_displayed)
            for ax in axs: ax.set_ylim(ylim)
            fig.suptitle(f'E3 {metric} by learner and generator\nFamily-specific matched repetitions; means +/- sample SD (n=1: no SD); shared real-only fits reused.',fontsize=11)
            fig.tight_layout(rect=(0,.17,1,.90))
            fig.canvas.draw()
            for ax,learner in zip(axs,learners):
                missing=panel_missing.get(learner)
                if missing:
                    x,y=_e3_footnote_position(ax.get_position())
                    note='No matched triple: '+', '.join(missing)
                    fig.text(x,y,textwrap.fill(note,width=76),ha='center',va='bottom',fontsize=7)
            p=Path(outdir)/f'E3_{metric}_route_comparison.png'; fig.savefig(p,dpi=150); plt.close(fig); made.append(str(p))
    d4=[r for r in rows if r.get('experiment')==4 and r.get('scientific_case') and r.get('balanced_accuracy') is not None]
    if d4:
        for metric in METRICS:
            fig,axs=plt.subplots(2,4,figsize=(20,9),sharey=True); axs=axs.ravel()
            for c,ax in enumerate(axs[:7]):
                altered=[r for r in d4 if str(r.get('target_class'))==str(c) and r.get(metric) is not None]
                controls=[r for r in d4 if (r.get('condition') in {'control','unchanged_control'} or (r.get('target_class') in (None,'') and r.get('condition')=='control')) and r.get(metric) is not None]
                q=altered+controls
                groups=defaultdict(list)
                for r in altered: groups[(str(r.get('method')),str(r.get('treatment') or r.get('route') or 'direct'),str(r.get('ratio') or r.get('condition') or ''))].append((int(r.get('rep') or 0),float(r[metric])))
                for r in controls: groups[(str(r.get('method')),'unchanged_control','control')].append((int(r.get('rep') or 0),float(r[metric])))
                labels=sorted(groups); means=[statistics.mean(v for _,v in groups[k]) for k in labels]
                ax.bar(range(len(labels)),means,capsize=1)
                for x,k in enumerate(labels):
                    vals=[v for _,v in groups[k]]; sd=statistics.stdev(vals) if len(vals)>1 else None
                    if sd is not None: ax.errorbar([x],[means[x]],yerr=[sd],fmt='none',ecolor='black',capsize=2,lw=.8)
                    for rep,v in groups[k]: ax.scatter([x],[v],s=9,alpha=.45,color='black',zorder=3)
                    ax.annotate(f'n={len(vals)}/3',(x,means[x]),xytext=(0,3),textcoords='offset points',ha='center',fontsize=4,rotation=90)
                ax.set_title(f'target {c}; n={len(q)}'); ax.set_xticks(range(len(labels)),[f'{k[0]}:{k[1]}:{k[2]}' for k in labels],rotation=90,fontsize=4); ax.grid(axis='y',alpha=.2)
            axs[7].axis('off'); ax=axs[0]; ax.set_ylabel(metric.replace('_',' ').title())
            if metric in {'balanced_accuracy','coverage'}: ax.set_ylim(0,1)
            elif metric=='set_size': ax.set_ylim(0,7)
            fig.suptitle(f'E4 {metric}; target × method × treatment × severity shown separately; bars are means ± sample SD'); fig.tight_layout()
            p=Path(outdir)/f'E4_{metric}_target_treatment.png'; fig.savefig(p,dpi=150); plt.close(fig); made.append(str(p))
    d4rec=[r for r in rows if r.get("experiment")==4 and r.get("scientific_case") and (r.get("target_class_recall") is not None or r.get("control_target_recall_by_class"))]
    if d4rec:
        fig,axs=plt.subplots(2,4,figsize=(20,9),sharey=True); axs=axs.ravel()
        for c,ax in enumerate(axs[:7]):
            altered=[r for r in d4rec if str(r.get("target_class"))==str(c)]
            controls=[r for r in d4rec if r.get("condition") in {"control","unchanged_control"} and r.get("control_target_recall_by_class",{}).get(str(c)) is not None]
            groups=defaultdict(list)
            for r in altered: groups[(str(r.get("method")),str(r.get("treatment") or r.get("route") or "direct"),str(r.get("ratio") or r.get("condition") or ""))].append((r.get("rep"),float(r["target_class_recall"])))
            for r in controls: groups[(str(r.get("method")),"unchanged_control","control")].append((r.get("rep"),float(r["control_target_recall_by_class"][str(c)])))
            labels=sorted(groups)
            for x,k in enumerate(labels):
                vals=[v for _,v in groups[k]]; mu=statistics.mean(vals); sd=statistics.stdev(vals) if len(vals)>1 else None
                ax.bar([x],[mu],color="#6b8e9b")
                if sd is not None: ax.errorbar([x],[mu],yerr=[sd],fmt="none",ecolor="black",capsize=2)
                for _,v in groups[k]: ax.scatter([x],[v],s=8,color="black",alpha=.5,zorder=3)
                ax.annotate(f"n={len(vals)}/3",(x,mu),xytext=(0,3),textcoords="offset points",ha="center",fontsize=5,rotation=90)
            ax.set_title(f"Target class {c}")
            ax.set_xticks(range(len(labels)),[f"{k[0]}:{k[1]}:{k[2]}" for k in labels],rotation=90,fontsize=4)
            ax.grid(axis="y",alpha=.2)
        axs[7].axis("off"); axs[0].set_ylabel("Target-class recall")
        axs[0].set_ylim(0,1)
        fig.suptitle("E4 target-class recall by target, learner, treatment, and severity; matched control values and repetition points",fontsize=11)
        fig.tight_layout()
        p=Path(outdir)/"E4_target_class_recall.png"; fig.savefig(p,dpi=150); plt.close(fig); made.append(str(p))
    d5=[r for r in rows if r.get('experiment')==5 and r.get('scientific_case') and r.get('balanced_accuracy') is not None]
    if d5:
        for metric in METRICS:
            fig,axs=plt.subplots(1,3,figsize=(18,5),sharey=True)
            for ax,mech in zip(axs,('feature_noise','missingness','label_noise')):
                q=[r for r in d5 if r.get('mechanism')==mech and r.get(metric) is not None]; arms=defaultdict(lambda:defaultdict(list))
                for r in q:
                    arm='|'.join(str(r.get(k) or '') for k in ('route','method','generator'))
                    arms[arm][str(r.get('rate'))].append(float(r[metric]))
                clean=[r for r in d5 if r.get('mechanism') in (None,'clean') and r.get('condition') in {'clean','clean_control','control'} and r.get(metric) is not None]
                for r in clean:
                    arm='|'.join(str(r.get(k) or '') for k in ('route','method','generator'))
                    if arm in arms: arms[arm]['clean'].append(float(r[metric]))
                numeric=sorted({str(r.get('rate')) for r in q},key=lambda x:float(x) if x.replace('.','',1).isdigit() else float('inf'))
                rates=['clean']+numeric
                for arm,byrate in arms.items():
                    ys=[statistics.mean(byrate[x]) if x in byrate else float('nan') for x in rates]
                    ax.plot(range(len(rates)),ys,marker='o',label=arm)
                    for xi,rate_label in enumerate(rates):
                        if rate_label in byrate:
                            vals=byrate[rate_label]
                            sd=statistics.stdev(vals) if len(vals)>1 else None
                            if sd is not None: ax.errorbar([xi],[ys[xi]],yerr=[sd],fmt='none',ecolor='black',capsize=2,lw=.7)
                            for v in vals: ax.scatter([xi],[v],s=8,alpha=.4,color='black',zorder=3)
                            ax.annotate(f'n={len(vals)}/3',(xi,ys[xi]),xytext=(0,4),textcoords='offset points',ha='center',fontsize=4)
                ax.set_title(f'{mech}; n={len(q)}'); ax.set_xticks(range(len(rates)),rates); ax.grid(alpha=.2)
            if metric in {'balanced_accuracy','coverage'}: axs[0].set_ylim(0,1)
            elif metric=='set_size': axs[0].set_ylim(0,7)
            axs[0].set_ylabel(metric.replace('_',' ').title()); handles,labels=axs[-1].get_legend_handles_labels()
            if handles: axs[-1].legend(handles,labels,fontsize=5,bbox_to_anchor=(1.02,1),loc='upper left')
            fig.suptitle(f'E5 {metric} by mechanism, rate, route, learner and generator; lines preserve method strata'); fig.tight_layout()
            p=Path(outdir)/f'E5_{metric}_corruption_sweeps.png'; fig.savefig(p,dpi=150,bbox_inches='tight'); plt.close(fig); made.append(str(p))
    d6=[r for r in rows if r.get('experiment')==6 and r.get('scientific_case')]
    if d6:
        group_defs=[('gmm','GMM','member'),('copula','Copula','member'),('arf','ARF','member'),('kde','KDE','member'),('chow_liu','Chow-Liu','member'),('equal','Equal-weight ensemble','ensemble'),('learned','Tuning-weighted ensemble','ensemble')]
        rep_colors={1:'#2166ac',2:'#b2182b',3:'#1b7837'}
        markers={1:'o',2:'s',3:'^'}
        available=sum(1 for r in d6 if (r.get('route')=='member' or r.get('condition')=='member_reference') and r.get('balanced_accuracy') is not None)
        planned_members=sum(1 for r in d6 if r.get('route')=='member' or r.get('condition')=='member_reference')
        available_ens=sum(1 for r in d6 if (r.get('kind')=='ensemble' or r.get('route') in {'equal','learned'} or r.get('condition') in {'equal','learned'}) and r.get('balanced_accuracy') is not None)
        planned_ens=sum(1 for r in d6 if r.get('kind')=='ensemble' or r.get('route') in {'equal','learned'} or r.get('condition') in {'equal','learned'})
        for metric in METRICS:
            fig,ax=plt.subplots(figsize=(13,6))
            for x,(key,label,kind) in enumerate(group_defs):
                def belongs(r):
                    if kind=='member': return str(r.get('generator') or r.get('method') or '').lower()==key
                    return str(r.get('mode') or r.get('method') or r.get('route') or '').lower()==key
                planned=[r for r in d6 if belongs(r)]
                vals=[r for r in planned if r.get(metric) is not None and r.get('outcome')=='successful']
                if not vals:
                    ax.axvspan(x-.28,x+.28,color='#dddddd',alpha=.8,zorder=0)
                    ax.text(x,.50,'n=0/3\nUnavailable',ha='center',va='center',fontsize=8,color='#555555',transform=ax.get_xaxis_transform())
                    continue
                ys=[]
                for r in vals:
                    rep=int(r.get('rep') or 0); y=float(r[metric]); ys.append(y)
                    ax.scatter(x,y,s=48,marker=markers.get(rep,'o'),color=rep_colors.get(rep,'#555555'),edgecolor='white',linewidth=.5,zorder=3,label=f'rep {rep}' if x==0 else None)
                mu=statistics.mean(ys); sd=statistics.stdev(ys) if len(ys)>1 else None
                ax.errorbar(x,mu,yerr=sd if sd is not None else 0,fmt='D',color='black',capsize=4,zorder=4,label='Mean ± sample SD' if x==0 else None)
                ax.text(x,.96,f'n={len(vals)}/3',transform=ax.get_xaxis_transform(),ha='center',va='top',fontsize=8)
            ax.set_xticks(range(len(group_defs)),[x[1] for x in group_defs],rotation=20,ha='right')
            ax.set_ylabel({'balanced_accuracy':'Balanced accuracy','coverage':'Coverage','set_size':'Mean prediction set size'}.get(metric,metric.replace('_',' ').title()))
            ax.set_title(f'E6 {'Balanced accuracy' if metric=='balanced_accuracy' else 'Coverage' if metric=='coverage' else 'Mean prediction set size'}: {available}/{planned_members} member evaluations; {available_ens}/{planned_ens} ensemble evaluations')
            if metric=='coverage': ax.axhline(.9,color='#762a83',linestyle='--',linewidth=1,label='nominal overall coverage 0.90')
            if metric in {'balanced_accuracy','coverage'}: ax.set_ylim(0,1)
            elif metric=='set_size': ax.set_ylim(0,7)
            ax.grid(axis='y',alpha=.25)
            handles,labels=ax.get_legend_handles_labels()
            if handles: ax.legend(handles,labels,fontsize=8,ncol=4,loc='upper center',bbox_to_anchor=(.5,1.15))
            fig.tight_layout(); p=Path(outdir)/f'E6_{metric}_member_ensemble.png'; fig.savefig(p,dpi=150,bbox_inches='tight'); plt.close(fig); made.append(str(p))
    e6=[]
    for r in rows:
        if r.get('experiment')==6 and r.get('outcome')=='successful' and r.get('artifact_dir'):
            d=_read_json(Path(r['artifact_dir'])/'frozen_weights.json')
            if d: e6.append((r,d))
    if e6:
        fig,ax=plt.subplots(figsize=(9,4.5)); x=range(5)
        for r,d in e6: ax.plot(list(x),d['weights'],marker='o',label=f"rep {r.get('rep')} {d.get('mode')}")
        ax.set_xticks(list(x),['GMM','Copula','ARF','KDE','Chow–Liu']); ax.set(ylabel='Global ensemble weight',title='E6 frozen posterior-ensemble weights'); ax.set_ylim(0,1); ax.grid(alpha=.25); ax.legend(fontsize=8,ncol=2); fig.tight_layout()
        p=Path(outdir)/'E6_weights.png'; fig.savefig(p,dpi=150); plt.close(fig); made.append(str(p))
    return made

def _json_cell(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),default=str) if value is not None else None

def _artifact_metadata(runtime,task):
    art=_task_artifact(runtime,task)
    return _read_json(art/'metadata.json') or {}, art

def _label_counts(y):
    import numpy as np
    a=np.asarray(y,dtype=int)
    return np.bincount(a,minlength=7).astype(int).tolist() if a.ndim==1 and (len(a)==0 or (a.min()>=0 and a.max()<7)) else None

def _dependency_evaluation_use(tasks):
    bykey={str(t.get('key')):t for t in tasks if isinstance(t,dict)}
    uses={}
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind') not in {'eval','ensemble','alias'} or not task.get('scientific_case'): continue
        seen=set(); stack=[str(x) for x in task.get('dependencies',[]) if x]
        while stack:
            k=stack.pop()
            if k in seen: continue
            seen.add(k); uses.setdefault(k,set()).add(str(task.get('key')))
            parent=bykey.get(k,{})
            stack.extend(str(x) for x in parent.get('dependencies',[]) if x)
    return uses

def _dataset_inventory_rows(runtime,tasks):
    import numpy as np
    rt=Path(runtime); rows=[]; labels=['A','F','G','K','M','GALAXY','QSO']; features=['mag_ps_g','mag_ps_r','mag_ps_i','mag_ps_z','mag_ps_y','gaia_g_mean_mag']
    cm=_read_json(rt/'cache/cache_manifest.json') or {}; features=cm.get('features',features)
    uses=_dependency_evaluation_use(tasks)
    def add(name,kind,rep,n,counts,path,ids_unique=None,key=None,role=None,metadata=None):
        rows.append({'dataset_key':key,'dataset_name':name,'dataset_type':kind,'role':role,'rep':rep,'n_rows':n,'unique_id_count':ids_unique,'class_counts_0_to_6':_json_cell(counts),'label_order':_json_cell(labels),'predictor_names':_json_cell(features),'ids_labels_and_audit_fields_excluded_from_predictors':True,'row_identity_kind':('synthetic_generated_row_order' if kind=='generate' else ('source_sample_id' if str(kind).startswith('real_clean') else 'source_or_transform_ids_if_saved')),'source_path':str(path) if path else None,'metadata':_json_cell(metadata),'dependent_scientific_evaluation_count':len(uses.get(str(key),set())) if key else 0})
    devx=rt/'cache/development_X.npy'; devy=rt/'cache/development_y.npy'; devid=rt/'cache/development_ids.npy'
    if devx.exists() and devy.exists() and devid.exists():
        y=np.load(devy,mmap_mode='r',allow_pickle=False); ids=np.load(devid,mmap_mode='r',allow_pickle=False)
        add('clean development pool','real_clean_development',None,len(y),_label_counts(y),devx,len(np.unique(ids)),None,'development',{'roles_disjoint_by_saved_memberships':True})
    test=rt/'cache/test.npz'
    if test.exists():
        with np.load(test,allow_pickle=False) as z:
            y=z['y']; ids=z['ids']; add('fixed held-out test','real_clean_test',None,len(y),_label_counts(y),test,len(np.unique(ids)),None,'test',{'held_out_role':True})
    for rp in sorted((rt/'cache/roles').glob('rep_*.npz')):
        rep=rp.stem.removeprefix('rep_')
        with np.load(rp,allow_pickle=False) as z:
            for role,xk,yk,ik in [('fit','X_fit','y_fit','fit_ids'),('tuning','X_tune','y_tune','tuning_ids'),('calibration','X_cal','y_cal','calibration_ids')]:
                if all(k in z for k in (xk,yk,ik)):
                    y=z[yk]; ids=z[ik]; add(f'rep {rep} {role}',f'real_clean_{role}',rep,len(y),_label_counts(y),rp,len(np.unique(ids)),f'roles/rep_{rep}/{role}',role,{'membership_file':str(rp)})
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind') not in {'generate','e4_cohort','e4_treatment','e4_append','e5_corruption'}: continue
        art=_task_artifact(rt,task); data=art/'data.npz'; meta=_read_json(art/'metadata.json') or {}
        if data.exists():
            with np.load(data,allow_pickle=False) as z:
                y=z['y'] if 'y' in z else None; ids=z['ids'] if 'ids' in z else None
                n=len(y) if y is not None else (len(z['X']) if 'X' in z else None)
                counts=_label_counts(y) if y is not None else None
                add(str(task.get('key')),str(task.get('kind')),task.get('rep'),n,counts,data,len(np.unique(ids)) if ids is not None else None,task.get('key'),task.get('route') or task.get('condition'),meta)
        else:
            add(str(task.get('key')),str(task.get('kind')),task.get('rep'),None,None,data,None,task.get('key'),task.get('route') or task.get('condition'),{'status':_effective_status(task),'outcome_reason':task.get('reason')})
    return rows

def _e4_histogram_rows(runtime,tasks):
    import numpy as np
    rows=[]; uses=_dependency_evaluation_use(tasks); bykey={str(t.get('key')):t for t in tasks if isinstance(t,dict)}
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind') not in {'e4_cohort','e4_treatment','e4_append'}: continue
        meta,art=_artifact_metadata(runtime,task); parent_task=bykey.get(str(task.get('cohort_key')),{}); parent_meta,_=_artifact_metadata(runtime,parent_task) if parent_task else ({},None); base_meta=parent_meta or meta; data=art/'data.npz'; before=meta.get('counts_before') or base_meta.get('realized_counts'); after=meta.get('counts_after') or meta.get('realized_counts')
        if data.exists():
            with np.load(data,allow_pickle=False) as z:
                if 'y' in z: after=_label_counts(z['y'])
                sw=z['sample_weight'] if 'sample_weight' in z else None; yy=z['y'] if 'y' in z else None
                class_weight_means=[float(np.mean(sw[yy==c])) if sw is not None and yy is not None and np.any(yy==c) else None for c in range(7)]
        else: class_weight_means=None
        dep=set(uses.get(str(task.get('key')),set()))
        rows.append({'task_key':task.get('key'),'rep':task.get('rep'),'task_kind':task.get('kind'),'status':_effective_status(task),'validation_state':task.get('validation_state'),'condition':task.get('condition'),'target_class':task.get('target_class',meta.get('target_class',base_meta.get('target_class'))),'ratio':task.get('ratio',meta.get('ratio',base_meta.get('ratio'))),'target_treatment':task.get('treatment'),'original_share':base_meta.get('original_share'),'original_fit_n':sum(base_meta.get('source_fit_counts') or []) if base_meta.get('source_fit_counts') else None,'source_fit_counts':_json_cell(base_meta.get('source_fit_counts')),'counts_before_0_to_6':_json_cell(before),'counts_after_0_to_6':_json_cell(after),'dataset_n_before':sum(before) if before else None,'dataset_n_after':sum(after) if after else None,'added_count':meta.get('added_count',meta.get('restore_added_count',base_meta.get('restore_added_count'))),'target_added_count':meta.get('added_count',meta.get('restore_added_count',base_meta.get('restore_added_count'))),'target_share_before':(before[int(task.get('target_class',base_meta.get('target_class',0)))]/sum(before)) if before and sum(before) else None,'target_share_after':(after[int(task.get('target_class',base_meta.get('target_class',0)))]/sum(after)) if after and sum(after) else None,'sample_weight_mean_by_class':_json_cell(class_weight_means),'sample_weight_mean':meta.get('sample_weight_mean'),'smote_neighbors':meta.get('neighbors'),'sampling_strategy':_json_cell(meta.get('sampling_strategy')),'generator_source_task_key':task.get('generated_key'),'generator_source_artifact':meta.get('generated_artifact'),'generator_metadata':_json_cell(meta.get('generator_metadata')),'cohort_source_task_key':task.get('cohort_key'),'artifact_metadata_path':str(art/'metadata.json') if (art/'metadata.json').exists() else None,'dependent_scientific_evaluation_count':len(dep),'dependent_evaluation_keys':_json_cell(sorted(dep)),'metadata_recorded':bool(meta)})
    return rows

def _e5_corruption_rows(runtime,tasks):
    import hashlib,numpy as np
    rows=[]; transitions=[]
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind')!='e5_corruption': continue
        meta,art=_artifact_metadata(runtime,task); audit_path=art/'audit.npz'; data_path=art/'data.npz'; audit={}
        if audit_path.exists():
            with np.load(audit_path,allow_pickle=False) as z: audit={k:z[k].copy() for k in z.files}
        mask=audit.get('affected_mask'); mask_sha=hashlib.sha256(np.ascontiguousarray(mask).view(np.uint8)).hexdigest() if mask is not None else None
        ids=audit.get('affected_ids'); ids_sha=hashlib.sha256(np.ascontiguousarray(ids).view(np.uint8)).hexdigest() if ids is not None else meta.get('affected_ids_sha256')
        tr=meta.get('transition_counts') or audit.get('transition_counts')
        if hasattr(tr,'tolist'): tr=tr.tolist()
        if tr is not None:
            for old in range(7):
                for new in range(7):
                    transitions.append({'task_key':task.get('key'),'rep':task.get('rep'),'mechanism':task.get('mechanism',meta.get('mechanism')),'rate':task.get('rate',meta.get('rate')),'old_class':old,'new_class':new,'old_label':['A','F','G','K','M','GALAXY','QSO'][old],'new_label':['A','F','G','K','M','GALAXY','QSO'][new],'transition_count':int(tr[old][new])})
        audit_hashes={k:hashlib.sha256(np.ascontiguousarray(v).view(np.uint8)).hexdigest() for k,v in audit.items()}
        scales=meta.get('feature_scale') or audit.get('per_feature_scale')
        if hasattr(scales,'tolist'): scales=scales.tolist()
        row={'task_key':task.get('key'),'rep':task.get('rep'),'status':_effective_status(task),'validation_state':task.get('validation_state'),'mechanism':task.get('mechanism',meta.get('mechanism')),'planned_rate':task.get('rate',meta.get('rate')),'realized_rate':meta.get('realized_rate'),'affected_count':meta.get('affected_count'),'fit_count':meta.get('fit_count'),'affected_ids_sha256':ids_sha,'affected_mask_sha256':mask_sha,'audit_array_sha256':_json_cell(audit_hashes),'feature_index_sha256':audit_hashes.get('feature_index'),'perturbation_sha256':audit_hashes.get('perturbation'),'affected_row_indices_sha256':audit_hashes.get('affected_row_indices'),'feature_indices':_json_cell(audit.get('feature_index').tolist() if audit.get('feature_index') is not None else None),'feature_scale_vector':_json_cell(scales),'scale_fallbacks':_json_cell(meta.get('scale_fallbacks')),'noise_definition':meta.get('noise'),'missing_cells':meta.get('missing_cells'),'missing_indicator':meta.get('missing_indicator'),'changed_label_count':meta.get('changed_label_count'),'transition_counts':_json_cell(tr),'other_roles_touched':meta.get('other_roles_touched'),'audit_artifact':str(audit_path) if audit_path.exists() else None,'data_artifact':str(data_path) if data_path.exists() else None,'realization_metadata_present':bool(meta),'metadata_path':str(art/'metadata.json') if (art/'metadata.json').exists() else None}
        for i in range(6): row[f'feature_scale_{i}']=scales[i] if scales and len(scales)>i else None
        rows.append(row)
    return rows,transitions

def _label_noise_source_class_rates(corruption_rows, transition_rows, original_counts_by_rep):
    """Compute rates over the full original fitting support, not affected-only rows."""
    labels=("A","F","G","K","M","GALAXY","QSO")
    by_task=defaultdict(list)
    for row in transition_rows:
        if row.get("mechanism")=="label_noise":
            by_task[str(row.get("task_key"))].append(row)
    out=[]
    for task in corruption_rows:
        if task.get("mechanism")!="label_noise":
            continue
        key=str(task.get("task_key"))
        matrix=by_task.get(key,[])
        rep_counts=original_counts_by_rep.get(str(task.get("rep")))
        for source in range(7):
            source_rows=[r for r in matrix if int(r.get("old_class",-1))==source]
            affected=sum(int(r.get("transition_count",0)) for r in source_rows)
            changed=sum(int(r.get("transition_count",0)) for r in source_rows
                        if int(r.get("new_class",-1))!=source)
            original=(int(rep_counts[source]) if rep_counts is not None and len(rep_counts)>source else None)
            if not matrix:
                rate=None
                status="transition_matrix_unavailable"
            elif original is None:
                rate=None
                status="original_fit_class_counts_unavailable"
            elif original==0:
                rate=None
                status="zero_source_support"
            else:
                rate=changed/original
                status="available"
            out.append({
                "task_key":task.get("task_key"),"rep":task.get("rep"),
                "planned_corruption_rate":task.get("planned_rate"),
                "realized_corruption_rate":task.get("realized_rate"),
                "source_class_id":source,"source_class_label":labels[source],
                "original_source_class_count":original,"affected_source_class_count":affected,
                "changed_label_count":changed,"realized_source_class_corruption_rate":rate,
                "rate_status":status,
            })
    return out

def _original_fit_class_counts(runtime, corruption_rows):
    """Read original role-label counts once per repetition; labels only, no model/data fitting."""
    import numpy as np
    rt=Path(runtime)
    reps={str(r.get("rep")) for r in corruption_rows if r.get("mechanism")=="label_noise"}
    counts={}
    for rep in reps:
        path=rt/"cache"/"roles"/f"rep_{rep}.npz"
        if not path.is_file():
            continue
        try:
            with np.load(path,allow_pickle=False) as z:
                if "y_fit" in z:
                    y=np.asarray(z["y_fit"]).astype(int,copy=False)
                    if y.ndim==1 and np.all((y>=0)&(y<7)):
                        counts[rep]=np.bincount(y,minlength=7).tolist()
        except Exception:
            continue
    return counts

def _evaluation_support_rows(runtime,tasks):
    import numpy as np
    rows=[]; perclass=[]
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind') not in {'eval','ensemble','alias'}: continue
        art=_task_artifact(runtime,task); ev=_read_json(art/'evaluation.json') or {}
        outcomes=art/'test_outcomes.npz'; has_out=outcomes.exists(); fb=None; outcomes_complete=False; fallback_n=None; n=None
        if has_out:
            try:
                with np.load(outcomes,allow_pickle=False) as z:
                    outcomes_complete=all(k in z for k in ('sample_id','y_pred','set_mask','covered','set_size'))
                    if 'fallback_mask' in z:
                        fb=np.asarray(z['fallback_mask'],bool); fallback_n=int(fb.sum()); n=len(fb)
            except Exception: pass
        cls=ev.get('test_fallback_per_class') or {}
        for c in range(7):
            v=cls.get(str(c),cls.get(c,{})) if isinstance(cls,dict) else {}
            perclass.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'generator':task.get('generator'),'condition':task.get('condition'),'class_id':c,'class_label':['A','F','G','K','M','GALAXY','QSO'][c],'test_class_n':v.get('n') if isinstance(v,dict) else None,'test_fallback_count':v.get('fallback_count') if isinstance(v,dict) else None,'test_fallback_rate':(v.get('fallback_count')/v.get('n')) if isinstance(v,dict) and v.get('n') else None})
        completion=ev.get('support_diagnostic_completion')
        rows.append({'task_key':task.get('key'),'experiment':task.get('experiment'),'rep':task.get('rep'),'method':task.get('method'),'route':task.get('route'),'generator':task.get('generator'),'condition':task.get('condition'),'status':_effective_status(task),'validation_state':task.get('validation_state'),'calibration_n':ev.get('calibration_n'),'calibration_fallback_count':ev.get('calibration_fallback_count'),'test_n':ev.get('test_n'),'test_fallback_count':ev.get('test_fallback_count'),'test_fallback_count_recomputed_from_saved_mask':fallback_n,'test_fallback_count_matches_metric':fallback_n==ev.get('test_fallback_count') if fallback_n is not None and ev.get('test_fallback_count') is not None else None,'test_fallback_per_class':_json_cell(cls),'test_outcomes_present':has_out,'test_outcomes_core_fields_present':outcomes_complete,'fallback_mask_present':fb is not None,'test_prediction_completion_flag':bool(outcomes_complete and fb is not None and n==ev.get('test_n')),'support_diagnostic_completion_status':('completed_without_refit' if isinstance(completion,dict) and completion.get('unchanged_predictions_and_sets_verified') and completion.get('classifier_refitted') is False else ('not_recorded' if completion is None else 'recorded_but_not_verified')),'fallback_mask_n':n,'support_diagnostic_completion':_json_cell(completion),'unchanged_predictions_and_sets_verified':completion.get('unchanged_predictions_and_sets_verified') if isinstance(completion,dict) else None,'previous_outcomes_sha256':completion.get('previous_outcomes_sha256') if isinstance(completion,dict) else None,'evaluation_json_present':bool(ev)})
    return rows,perclass

def _e6_weight_rows(runtime,tasks):
    weights=[]; candidates=[]
    for task in tasks:
        if not isinstance(task,dict) or task.get('kind')!='ensemble': continue
        art=_task_artifact(runtime,task); frozen=_read_json(art/'frozen_weights.json') or {}; ledger=_read_json(art/'candidate_ledger.json') or {}
        order=frozen.get('member_order') or ledger.get('member_order') or ['gmm','copula','arf','kde','chow_liu']; w=frozen.get('weights') or ledger.get('weights')
        row={'task_key':task.get('key'),'rep':task.get('rep'),'mode':task.get('mode'),'status':_effective_status(task),'validation_state':task.get('validation_state'),'weight_search_seed':frozen.get('weight_search_seed',ledger.get('seed')),'member_order':_json_cell(order),'weights':_json_cell(w),'equal_weight_expected':task.get('mode')=='equal','frozen_before_calibration_and_test':frozen.get('frozen_before_calibration_and_test'),'selected_candidate':ledger.get('selected_candidate'),'candidate_count':ledger.get('candidate_count'),'candidate_ledger_present':bool(ledger),'candidate_ledger_path':str(art/'candidate_ledger.json') if (art/'candidate_ledger.json').exists() else None,'frozen_weights_path':str(art/'frozen_weights.json') if (art/'frozen_weights.json').exists() else None}
        for i,name in enumerate(order): row[f'weight_{name}']=w[i] if w and len(w)>i else None
        weights.append(row)
        for cand in ledger.get('candidates',[]) if isinstance(ledger.get('candidates'),list) else []:
            cw=cand.get('weights',[]); cr={'task_key':task.get('key'),'rep':task.get('rep'),'mode':task.get('mode'),'candidate_index':cand.get('candidate'),'balanced_accuracy':cand.get('balanced_accuracy'),'selected':cand.get('candidate')==ledger.get('selected_candidate'),'candidate_weights':_json_cell(cw)}
            for i,name in enumerate(order): cr[f'weight_{name}']=cw[i] if len(cw)>i else None
            candidates.append(cr)
    return weights,candidates

def _write_evidence_tables(runtime,tasks,report_dir):
    rt=Path(runtime); out=Path(report_dir)
    inventory=_dataset_inventory_rows(rt,tasks); e4hist=_e4_histogram_rows(rt,tasks)
    _write_csv(out/'dataset_inventory.csv',inventory)
    _write_csv(out/'E4_class_histograms.csv',e4hist,fields=['task_key','rep','task_kind','status','validation_state','condition','target_class','ratio','target_treatment','original_share','original_fit_n','source_fit_counts','counts_before_0_to_6','counts_after_0_to_6','dataset_n_before','dataset_n_after','added_count','target_added_count','target_share_before','target_share_after','sample_weight_mean_by_class','sample_weight_mean','smote_neighbors','sampling_strategy','generator_source_task_key','generator_source_artifact','generator_metadata','cohort_source_task_key','artifact_metadata_path','dependent_scientific_evaluation_count','dependent_evaluation_keys','metadata_recorded'])
    e5,trans=_e5_corruption_rows(rt,tasks); _write_csv(out/'E5_corruption_realization_summary.csv',e5); _write_csv(out/'label_transition_counts.csv',trans,fields=['task_key','rep','mechanism','rate','old_class','new_class','old_label','new_label','transition_count']); original_fit_counts=_original_fit_class_counts(rt,e5); label_noise_rates=_label_noise_source_class_rates(e5,trans,original_fit_counts); _write_csv(out/'E5_label_noise_source_class_rates.csv',label_noise_rates,fields=['task_key','rep','planned_corruption_rate','realized_corruption_rate','source_class_id','source_class_label','original_source_class_count','affected_source_class_count','changed_label_count','realized_source_class_corruption_rate','rate_status'])
    selection_rows=_model_selection_rows(rt,tasks); _write_csv(out/'model_selection_ledger.csv',selection_rows)
    cutoff_rows=_terminal_worker_cutoff_rows(rt,tasks)
    _write_csv(out/'terminal_trial_cutoffs.csv',cutoff_rows)
    (out/'terminal_trial_cutoffs.json').write_text(json.dumps(cutoff_rows,indent=2,sort_keys=True,default=str)+'\n',encoding='utf-8')
    resource_rows,resource_counts=_resource_failure_rows(rt,tasks)
    _write_csv(out/'resource_failure_ledger.csv',resource_rows,fields=['task_key','experiment','rep','method','route','condition','event_scope','trial_index','trial_status','failure_evidence_type','raw_reason','cell_outcome','event_counts_as_cell_failure','phase','phase_reason','phase_seconds','trial_seconds','peak_tree_rss_kib','peak_tree_rss_bytes','worker_peak_rss_source','worker_finished_utc','worker_observed_utc','linked_trial_index','last_observed_phase_elapsed_seconds','last_observed_phase_peak_tree_rss_kib','nominal_trial_budget','unattempted_nominal_slots','phase_exit_code','phase_evidence_path','source_provenance'])
    _write_csv(out/'resource_failure_summary.csv',resource_counts,fields=['experiment','failure_evidence_type','event_scope','failure_event_count','unique_task_count','terminal_cell_failure_task_count','successful_fit_tasks_with_failed_trial_count','timeout_event_count','memory_rss_event_count','trial_timeout_event_count','trial_memory_rss_event_count','worker_terminal_memory_rss_event_count'])
    support,perclass=_evaluation_support_rows(rt,tasks); _write_csv(out/'evaluation_support_fallbacks.csv',support); _write_csv(out/'evaluation_support_fallbacks_per_class.csv',perclass)
    e6,candidates=_e6_weight_rows(rt,tasks); _write_csv(out/'E6_weights.csv',e6); _write_csv(out/'E6_candidate_ledger.csv',candidates,fields=['task_key','rep','mode','candidate_index','balanced_accuracy','selected','candidate_weights','weight_gmm','weight_copula','weight_arf','weight_kde','weight_chow_liu'])
    return {'dataset_inventory_rows':len(inventory),'E4_histogram_rows':len(e4hist),'E5_corruption_rows':len(e5),'label_transition_rows':len(trans),'E5_label_noise_source_class_rate_rows':len(label_noise_rates),'model_selection_ledger_rows':len(selection_rows),'resource_failure_event_rows':len(resource_rows),'resource_failure_summary_rows':len(resource_counts),'terminal_trial_cutoff_rows':len(cutoff_rows),'evaluation_support_rows':len(support),'evaluation_support_per_class_rows':len(perclass),'E6_weight_rows':len(e6),'E6_candidate_rows':len(candidates)}

def report(runtime)->dict:
    runtime=Path(runtime).resolve(); root=runtime.parent; reg=_read_json(runtime/'registry.json') or {'tasks':[]}
    tasks=reg.get('tasks',[]); rows=[]; class_rows=[]
    for rec in tasks:
        if not isinstance(rec,dict): continue
        e=_find_eval(runtime,rec); rows.append(_task_row(rec,e,runtime))
        if e and isinstance(e.get('per_class'),dict):
            for c,v in e['per_class'].items():
                if isinstance(v,dict): class_rows.append({'key':rec.get('key'),'experiment':rec.get('experiment'),'rep':rec.get('rep'),'method':rec.get('method'),'condition':rec.get('condition'),'route':rec.get('route'),'mode':rec.get('mode'),'target_class':rec.get('target_class'),'ratio':rec.get('ratio'),'treatment':rec.get('treatment'),'mechanism':rec.get('mechanism'),'rate':rec.get('rate'),'generator':rec.get('generator'),'class_id':c,**{k:v.get(k) for k in ('n','recall','coverage','set_size')}})
    report_dir=runtime/'reports'; report_dir.mkdir(parents=True,exist_ok=True)
    evidence_table_counts=_write_evidence_tables(runtime,tasks,report_dir)
    planned=[r for r in rows if r.get('scientific_case')]
    _write_csv(report_dir/'planned_case_ledger.csv',planned)
    _write_csv(report_dir/'per_class_metrics.csv',class_rows)
    _write_csv(report_dir/'E5_per_class_paired_differences.csv',_paired_per_class(rows,class_rows))
    _write_csv(report_dir/'all_task_ledger.csv',rows)
    _write_csv(report_dir/'experiment_outcome_coverage.csv',_summary(rows))
    _write_csv(report_dir/'per_repetition_metrics.csv',[r for r in planned if r.get('balanced_accuracy') is not None])
    paired=_paired(planned)
    _write_csv(report_dir/'matched_paired_differences.csv',paired)
    e4_control_pairs=_e4_paired_controls(planned,class_rows)
    e5_pc_pairs=_paired_per_class(planned,class_rows)
    _write_csv(report_dir/'E4_CONTROL_TREATMENT_PAIRED.csv',e4_control_pairs)
    e4_summary=_condition_paired_summary(e4_control_pairs,('comparison','method','target_class','ratio','treatment'),('paired_balanced_accuracy_difference_a_minus_b','paired_coverage_difference_a_minus_b','paired_set_size_difference_a_minus_b','paired_target_class_recall_difference_a_minus_b','paired_target_class_coverage_difference_a_minus_b'))
    _write_csv(report_dir/'E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv',e4_summary)
    e5_metric_pairs=_e5_paired_metrics(planned)
    _write_csv(report_dir/'E5_clean_corrupted_paired_metrics.csv',e5_metric_pairs)
    e5metric_summary=_condition_paired_summary(e5_metric_pairs,('method','route','generator','mechanism','rate'),('paired_balanced_accuracy_difference_a_minus_b','paired_coverage_difference_a_minus_b','paired_set_size_difference_a_minus_b'))
    _write_csv(report_dir/'E5_clean_corrupted_paired_metrics_summary.csv',e5metric_summary)
    _write_csv(report_dir/'E5_per_class_paired_differences.csv',e5_pc_pairs)
    e5_summary=_condition_paired_summary(e5_pc_pairs,('method','route','generator','mechanism','rate','class_id'),('recall_difference_a_minus_b','coverage_difference_a_minus_b','set_size_difference_a_minus_b'))
    _write_csv(report_dir/'E5_per_class_paired_summary.csv',e5_summary)
    recall_lookup={(str(x.get('key')),str(x.get('class_id'))):x.get('recall') for x in class_rows}
    for r in rows:
        if r.get('experiment')==4 and r.get('target_class') is not None:
            r['target_class_recall']=recall_lookup.get((str(r.get('key')),str(r.get('target_class'))))
        if r.get('experiment')==4 and r.get('condition') in {'control','unchanged_control'}:
            r['control_target_recall_by_class']={str(x.get('class_id')):x.get('recall') for x in class_rows if x.get('key')==r.get('key')}
    _write_csv(report_dir/'matched_paired_summary.csv',_paired_summary(paired))
    costs=_cost_rows(runtime,tasks)
    _write_csv(report_dir/'costs.csv',costs)
    _write_csv(report_dir/'cost_summary.csv',_cost_summary(costs))
    figures=_figures(runtime,report_dir,rows)
    figures.extend(_main_heatmaps(runtime,report_dir,rows,class_rows))
    # Explicitly connect prior validated reports without changing or refitting them.
    e1=root/'project/benchmark/results/e1_report_validated_no_bootstrap.json'
    e2=root/'e2_20261024/E2_CURRENT_REPORT.md'
    e2avail=root/'e2_20261024/E2_all_generators_270.csv'
    e2strata=root/'e2_20261024/E2_within_stratum_descriptive_30.csv'
    recovery=root/'e1_recovery_20261024/RECOVERY_CUTOFF.json'
    e2audit=_read_json(root/'e2_20261024/E2_INTEGRITY_AUDIT.json') or {}
    e1d=_read_json(e1) or {}; recovery_d=_read_json(recovery) or {}; e2rows=[]; e2strata_rows=[]
    if e2avail.exists():
        with e2avail.open(newline='',encoding='utf-8') as f: e2rows=list(csv.DictReader(f))
    if e2strata.exists():
        with e2strata.open(newline='',encoding='utf-8') as f: e2strata_rows=list(csv.DictReader(f))
    primary_e2=[r for r in e2rows if r.get('family_set')=='primary']
    classical_e2=[r for r in e2rows if r.get('family_set')!='primary']
    e2_unavailable=sum(r.get('provenance')=='unavailable' for r in primary_e2)
    e2_primary_available=len(primary_e2)-e2_unavailable
    e2_fullfive=sum(str(r.get('protocol_full_five_family','')).lower()=='true' for r in e2strata_rows)
    counts=Counter(str(r.get('outcome') or r.get('status')) for r in planned)
    md=['# LAMOST project descriptive report','',f"Registry observation: {reg.get('observed_utc','not recorded')}",'','## New runtime coverage','',f"Planned scientific cases in this registry: {len(planned)}; evaluated outcomes recorded: {sum(r.get('balanced_accuracy') is not None for r in planned)}.",'','| State | Count |','|---|---:|']
    for state in ('successful','validated_terminal','scientific_failure','unsupported','unavailable_dependency','operationally_interrupted','operationally_invalid','user_stopped','planned','waiting_for_dependency','running','packaging_pending'):
        if counts.get(state): md.append(f'| {state} | {counts[state]} |')
    e4n=sum(r.get('experiment')==4 and r.get('balanced_accuracy') is not None for r in planned); e5n=sum(r.get('experiment')==5 and r.get('balanced_accuracy') is not None for r in planned)
    e4pairs=e4_control_pairs; e4matched=sum(x.get('paired_available') for x in e4pairs)
    e5classpairs=e5_pc_pairs; e5classmatched=sum(x.get('paired_available') for x in e5classpairs)
    md += ['', 'Evidence tables include dataset/role inventory, exact E4 class histograms, E5 corruption realizations and label transitions, model-selection trials/provenance, calibration/test fallback completion flags, and E6 frozen weights plus the complete saved candidate ledger. Empty candidate and transition files retain their headers when no such artifacts exist. Synthetic example counts, restored counts and untouched real role counts remain distinct.', '', 'Results are descriptive and repetition matched. Means and sample standard deviations appear in the coverage table; no bootstrap intervals or significance claims are produced. A non-success is not treated as an evaluated score.','', '## E4 and E5 descriptive coverage','', f'E4 currently has {e4n} evaluated scientific cases in this registry snapshot; {e4matched}/{len(e4pairs)} planned control contrasts have both evaluations available. E4_CONTROL_TREATMENT_PAIRED.csv keeps direct altered-versus-unchanged and treatment-versus-untreated/unchanged contrasts separate by repetition, target, severity, and method; E4_CONTROL_TREATMENT_PAIRED_SUMMARY.csv gives condition-specific paired n, mean, and sample SD without pooling target/severity/method strata. Main effect heatmaps are separate from overview panels. See the outcome coverage and resource ledgers for failures and unavailable dependencies.', f'E5 currently has {e5n} evaluated scientific cases; {e5classmatched}/{len(e5classpairs)} planned per-class corruption-versus-clean rows have both class metrics available. E5_clean_corrupted_paired_metrics_summary.csv and E5_per_class_paired_summary.csv provide condition-specific paired n, means, and sample SD for overall and class-level outcomes; their underlying row ledgers preserve method, route, generator, mechanism, rate, class, and repetition, and unmatched cases carry status/reason with blank differences. Main paired-delta heatmaps show all planned method/route/generator/rate cells, with unavailable cells grey. Contrasts are conditional on paired successful evaluations and do not support universal robustness claims.', '', '## Frozen E1 and E2 integration','']
    if e1d:
        cc=e1d.get('cell_counts',{}); md += [f"Frozen E1 validated report: {e1}",f"765 planned cells; {cc.get('successful_test_evaluation',674)} successful, {cc.get('resource_failure',55)+cc.get('supervisor_terminal_failure_without_cell_completion',26)} failed (resource/supervisor-terminal categories), and {cc.get('scientific_model_or_support_failure',10)} unsupported/model-support failures. The user-facing frozen ledger reports 81 failures plus 10 unsupported; source report evidence remains linked.", '']
    else: md += [f'Frozen E1 validated report not found at expected path: {e1}.','']
    rc=recovery_d.get('counts',recovery_d.get('status_counts',{}))
    if recovery_d:
        md += [f"Stopped E1 recovery supplement: {recovery_d.get('cutoff_utc','timestamp unavailable')}; recorded counts {rc}; explicitly stopped early at user request. Source: {recovery}.", '']
    cutoff_rows=_terminal_worker_cutoff_rows(runtime,tasks)
    if cutoff_rows:
        bykey={str(t.get('key')):t for t in tasks if isinstance(t,dict)}
        def depends_on(key,target,seen=None):
            seen=seen or set()
            if key==target:return True
            if key in seen:return False
            seen.add(key);rec=bykey.get(str(key),{})
            return any(depends_on(str(d),target,seen.copy()) for d in rec.get('dependencies',[]))
        md += ['', '## Terminal worker RSS cutoff and dependent availability','']
        for c in cutoff_rows:
            e3cases=sum(1 for t in tasks if t.get('experiment')==3 and t.get('scientific_case') and _effective_status(t)=='unavailable_dependency' and any(depends_on(str(d),c['task_key']) for d in t.get('dependencies',[])))
            e5cases=sum(1 for t in tasks if t.get('experiment')==5 and t.get('scientific_case') and _effective_status(t)=='unavailable_dependency' and any(depends_on(str(d),c['task_key']) for d in t.get('dependencies',[])))
            label=f"E{c['experiment']} repetition {c['rep']} {c.get('route') or 'fit'} {c.get('method')}"+(f" / {c.get('generator')}" if c.get('generator') else '')
            common=f"{label} reached the recorded worker process-tree RSS limit ({c['worker_memory_cap_bytes']} bytes) and terminated at {c['terminal_finished_utc']} with supervisor-measured peak {c['peak_tree_rss_bytes']} bytes. The terminal event is tied to attempt {c['attempt_id']} and the matching checkpoint phase."
            if c['cutoff_phase']=='trial':
                phase_text=(f" Trial {c['aborted_trial_index']} was assigned and has a last-saved {c['aborted_trial_last_state_status']} state; its last observed elapsed time is {c['last_observed_phase_elapsed_seconds']} s and observed phase RSS {c['last_observed_phase_peak_tree_rss_kib']} KiB. No trial score or completed duration is imputed. Completed trial records: {c['completed_trial_count']} ({c['completed_trial_statuses']}).")
            else:
                phase_text=(f" The final-fit phase has a last-saved running state (last observed elapsed {c['last_observed_phase_elapsed_seconds']} s; phase RSS {c['last_observed_phase_peak_tree_rss_kib']} KiB). No completed final-fit duration or score is imputed. Completed trial records: {c['completed_trial_count']} ({c['completed_trial_statuses']}).")
            unattempted=', '.join(str(x) for x in c['unattempted_nominal_slot_indices']) or 'none'
            tail=f" Nominal tuning budget was {c['nominal_trial_budget']}; started {c['actually_started_trial_count']} slots, completed {c['completed_trial_count']} tuning records, and nominal slots not attempted: {unattempted}. Pipeline present: {c['published_pipeline_present']}. {e3cases} dependent E3 and {e5cases} dependent E5 evaluation cells are unavailable dependencies where applicable. Raw trial/checkpoint state was not modified. No OS-level OOM is inferred."
            md.append(common+phase_text+tail)
    md += [f'E2 report source: {e2}.',f"E2 primary: {e2_primary_available}/{len(primary_e2)} evaluated; {e2_unavailable} unavailable. Separate classical references: {len(classical_e2) - sum(r.get('provenance')=='unavailable' for r in classical_e2)}/{len(classical_e2)} available. Complete five-family correlation strata: {e2_fullfive}/{len(e2strata_rows)}. Artifact audit: {e2audit.get('evaluated_cells','not recorded')} evaluated cells, {e2audit.get('class_valid',0)+e2audit.get('class_valid_low_precision',0)} class reports, {e2audit.get('integrity_errors','audit unavailable')} integrity errors; {e2audit.get('class_valid_low_precision',0)} low-precision class flags. Reconstruction fidelity gate: {e2audit.get('reconstruction_gate_exact',0)} exact and {e2audit.get('reconstruction_gate_mismatch',0)} with recorded accuracy difference; maximum absolute difference {e2audit.get('reconstruction_gate_max_abs_BA_difference','not recorded')}.",f'E2 final family ledger: {len(e2rows)} rows in {e2avail}; primary coverage remains transparently incomplete.','', '## Figures','']
    md += [f'- {Path(p).name}' for p in figures] if figures else ['No later-experiment evaluation figures available yet.']
    prior_figures=[root/'project/learning_curves_through_300000.png',root/'e1_wrapup_20261024/E1_learning_curves_all_budgets.html',root/'e2_20261024/E2_combined_fidelity_vs_accuracy.html']
    for fp in prior_figures:
        if fp.exists(): md.append(f'- Prior validated figure: `{fp.relative_to(root)}`')
    md += ['', '## Resource and timing results','', 'Phase-level wall-clock and process-tree RSS observations are in `costs.csv`; grouped totals, means, sample SDs and actual successful phase counts are in `cost_summary.csv`. Fit search trials, final model fitting, generator fitting, 400k-row generation, downstream training, calibration and test inference are separate stages. E4 cohort construction and E5 corruption construction are reported as observed task wall time because their implementation executes synchronously and exposes no isolated phase RSS receipt. Reused pipelines show zero new model-training time and retain any reuse/load validation overhead separately; logical fit dependencies and provenance are recorded by key. Timings depend on this EC2 hardware, concurrent system load, process startup, I/O and library versions; observed RSS is a process-tree peak, not a portable algorithmic cost. Missing timings stay blank rather than being imputed as zero.','', '## Interpretation and limitations','', 'Comparisons use only matching successful repetitions. Survivorship and dependency unavailability can limit interpretation. E1 and E2 outcomes were already observed before the later experiments; later evaluations are not prospective untouched-test evaluations. Frozen E1 outcomes remain separate from E1 recovery and experiment-specific models. Auxiliary tuning-history and omitted historical model/prediction caveats remain in the source E1/E2 reports.']
    (report_dir/'PROJECT_DESCRIPTIVE_REPORT.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    return {'status':'success','report_dir':str(report_dir),'planned_scientific_cases':len(planned),'evaluated_cases':sum(r.get('balanced_accuracy') is not None for r in planned),'state_counts':dict(counts),'figure_paths':figures,'cost_rows':len(costs),'cost_summary_rows':len(_cost_summary(costs)),'evidence_table_counts':evidence_table_counts,'e1_source':str(e1) if e1d else None,'e2_source':str(e2) if e2.exists() else None}
