import csv
import hashlib
import json
import math
from pathlib import Path

MEMBER_ORDER = ('gmm', 'copula', 'arf', 'kde', 'chow_liu')
METRICS = ('balanced_accuracy', 'coverage', 'set_size')
PHASE_COST_ALLOWLIST = ('phase', 'seconds', 'peak_tree_rss_kib', 'cache_hit',
                        'source_task_key', 'source_attempt_id', 'resource_profile',
                        'phase_sha256', 'artifact_sha256')

class E6V2ReportError(ValueError):
    pass

def _num(value, label):
    try:
        x=float(value)
    except (TypeError, ValueError):
        raise E6V2ReportError(f'missing/non-numeric {label}')
    if not math.isfinite(x):
        raise E6V2ReportError(f'non-finite {label}')
    return x

def _metric(evaluation, metric, label):
    aliases={'set_size':('set_size','mean_set_size')}
    keys=aliases.get(metric,(metric,))
    for key in keys:
        if key in evaluation:
            return _num(evaluation[key],label+'.'+key)
    raise E6V2ReportError(f'missing {label}.{metric}')

def _evaluation(container, label):
    ev=container.get('evaluation', container)
    if not isinstance(ev,dict):
        raise E6V2ReportError(f'{label} metrics must be an object')
    vals={m:_metric(ev,m,label) for m in METRICS}
    if not isinstance(ev.get('per_class'),dict):
        raise E6V2ReportError(f'{label} must retain per-class metrics')
    if not isinstance(ev.get('confusion_matrix',[]),list):
        raise E6V2ReportError(f'{label} confusion_matrix must be a list when present')
    return vals, ev

def _weights_vector(doc):
    weights=doc.get('selected_weights')
    if isinstance(weights,dict):
        if set(weights)!=set(MEMBER_ORDER): raise E6V2ReportError('selected_weights member set mismatch')
        result=[_num(weights[m],'weight.'+m) for m in MEMBER_ORDER]
    elif isinstance(weights,list) and len(weights)==5:
        result=[_num(x,'weight') for x in weights]
    else:
        raise E6V2ReportError('selected_weights must be a five-member vector or map')
    if any(x<0 for x in result) or abs(sum(result)-1)>1e-8:
        raise E6V2ReportError('selected_weights must lie on the simplex')
    mode=doc.get('mode')
    if mode=='equal' and any(abs(x-.2)>1e-10 for x in result):
        raise E6V2ReportError('equal mode weights must be exactly 0.2 per member')
    return result

def validate_member_comparisons(doc, task):
    if not isinstance(doc,dict) or doc.get('protocol_version')!='E6-v2':
        raise E6V2ReportError('not an E6-v2 member-comparison document')
    if doc.get('comparison_source_task_key')!=task.get('key'):
        raise E6V2ReportError('comparison task key mismatch')
    if int(doc.get('rep',-1))!=int(task.get('rep',-2)) or doc.get('mode')!=task.get('mode'):
        raise E6V2ReportError('rep/mode mismatch')
    if doc.get('mode') not in ('equal','learned'):
        raise E6V2ReportError('unknown ensemble mode')
    if tuple(doc.get('member_order') or ())!=MEMBER_ORDER:
        raise E6V2ReportError('member order mismatch')
    for key in ('posterior_fingerprint','fit_ids_sha256','tuning_ids_sha256',
                'calibration_ids_sha256','test_ids_sha256','score_rule','quantile_rule'):
        if not isinstance(doc.get(key),str) or not doc[key]:
            raise E6V2ReportError('missing provenance field '+key)
    if 'probability' not in doc['score_rule'].lower():
        raise E6V2ReportError('E6 members must use probability scores')
    frozen=doc.get('weights_frozen_before_calibration_and_test')
    if frozen is not True:
        raise E6V2ReportError('explicit weights-frozen-before-calibration/test evidence is required')
    qrule=doc['quantile_rule'].lower()
    if 'ceil' not in qrule or not any(x in qrule for x in ('kth','order statistic','partition')):
        raise E6V2ReportError('quantile rule is not explicit finite-sample order statistic')
    members=doc.get('members')
    if not isinstance(members,dict) or tuple(members.keys())!=MEMBER_ORDER:
        # JSON object key order is part of this canonical producer contract.
        if not isinstance(members,dict) or set(members)!=set(MEMBER_ORDER):
            raise E6V2ReportError('five member records are required')
    member_rows=[]
    metric_map={}
    for name in MEMBER_ORDER:
        member=members[name]
        if not isinstance(member,dict): raise E6V2ReportError('member record must be an object: '+name)
        for field in ('fit_key','pipeline_sha256','fit_ids_sha256'):
            if not isinstance(member.get(field),str) or not member[field]:
                raise E6V2ReportError(f'missing {name}.{field}')
        if member['fit_ids_sha256']!=doc['fit_ids_sha256']:
            raise E6V2ReportError('member fitting-role identity mismatch: '+name)
        if member.get('score_kind','probability')!='probability':
            raise E6V2ReportError('member score kind mismatch: '+name)
        if int(member.get('calibration_n',0))!=10000 or int(member.get('test_n',0))!=500000:
            raise E6V2ReportError('member calibration/test sample counts do not match frozen E6 roles')
        vals, ev=_evaluation(member,'member '+name)
        metric_map[name]=vals
        member_rows.append({'rep':int(doc['rep']),'mode':doc['mode'],'member':name,
            'source_task_key':doc['comparison_source_task_key'],'fit_key':member['fit_key'],
            'pipeline_sha256':member['pipeline_sha256'],'fit_ids_sha256':member['fit_ids_sha256'],
            'posterior_fingerprint':doc['posterior_fingerprint'],
            'tuning_ids_sha256':doc['tuning_ids_sha256'],'calibration_ids_sha256':doc['calibration_ids_sha256'],
            'test_ids_sha256':doc['test_ids_sha256'],'score_rule':doc['score_rule'],'quantile_rule':doc['quantile_rule'],
            'threshold':member.get('calibration_threshold',member.get('conformal_threshold',member.get('threshold'))),
            'calibration_n':member['calibration_n'],'test_n':member['test_n'],
            'tuning_balanced_accuracy':member.get('tuning_balanced_accuracy'),
            'balanced_accuracy':vals['balanced_accuracy'],'coverage':vals['coverage'],'set_size':vals['set_size'],
            'per_class_json':json.dumps(ev['per_class'],sort_keys=True,separators=(',',':')),
            'confusion_matrix_json':json.dumps(ev['confusion_matrix'],separators=(',',':'))})
    best=doc.get('tuning_best_member')
    if best not in MEMBER_ORDER:
        raise E6V2ReportError('tuning_best_member must identify a member selected on tuning data')
    ensvals, ens_ev=_evaluation({'evaluation':doc.get('ensemble_evaluation')},'ensemble')
    weights=_weights_vector(doc)
    candidate_path=doc.get('candidate_ledger_path')
    candidate_sha=doc.get('candidate_ledger_sha256')
    if doc['mode']=='learned' and (not isinstance(candidate_path,str) or not isinstance(candidate_sha,str) or len(candidate_sha)!=64):
        raise E6V2ReportError('learned mode requires candidate-ledger path and SHA')
    ensemble_row={'rep':int(doc['rep']),'mode':doc['mode'],'task_key':task['key'],
        'balanced_accuracy':ensvals['balanced_accuracy'],'coverage':ensvals['coverage'],'set_size':ensvals['set_size'],
        'tuning_best_member':best,'tuning_best_balanced_accuracy':doc.get('tuning_best_balanced_accuracy'),
        'selected_weights_json':json.dumps(dict(zip(MEMBER_ORDER,weights)),sort_keys=True,separators=(',',':')),
        'posterior_fingerprint':doc['posterior_fingerprint'],'fit_ids_sha256':doc['fit_ids_sha256'],
        'tuning_ids_sha256':doc['tuning_ids_sha256'],'calibration_ids_sha256':doc['calibration_ids_sha256'],
        'test_ids_sha256':doc['test_ids_sha256'],'candidate_ledger_path':candidate_path or '',
        'candidate_ledger_sha256':candidate_sha or '',
        'per_class_json':json.dumps(ens_ev['per_class'],sort_keys=True,separators=(',',':')),
        'confusion_matrix_json':json.dumps(ens_ev['confusion_matrix'],separators=(',',':'))}
    comparisons=[]
    for comp_kind,comp_name in [('member',m) for m in MEMBER_ORDER]+[('tuning_best',best)]:
        ref=metric_map[comp_name]
        comparisons.append({'rep':int(doc['rep']),'mode':doc['mode'],'comparison_kind':comp_kind,
            'comparator':comp_name,'task_key':task['key'],
            **{f'ensemble_{m}':ensvals[m] for m in METRICS},
            **{f'comparator_{m}':ref[m] for m in METRICS},
            **{f'ensemble_minus_comparator_{m}':ensvals[m]-ref[m] for m in METRICS}})
    weights_row={'rep':int(doc['rep']),'mode':doc['mode'],'task_key':task['key'],
        **{f'weight_{m}':weights[i] for i,m in enumerate(MEMBER_ORDER)},
        'tuning_best_member':best,'candidate_ledger_path':candidate_path or '',
        'candidate_ledger_sha256':candidate_sha or ''}
    costs=[]
    raw_costs=doc.get('phase_costs',[])
    if isinstance(raw_costs,dict):
        raw_costs=[({'phase':name,**value} if isinstance(value,dict) else {'phase':name,'seconds':value})
                   for name,value in raw_costs.items()]
    for item in raw_costs if isinstance(raw_costs,list) else []:
        if isinstance(item,dict):
            costs.append({'rep':int(doc['rep']),'mode':doc['mode'],'task_key':task['key'],
                          **{k:item[k] for k in PHASE_COST_ALLOWLIST if k in item}})
    return {'ensemble':ensemble_row,'members':member_rows,'comparisons':comparisons,
            'weights':weights_row,'costs':costs}

def v2_availability_rows(tasks, runtime, loader=None):
    runtime=Path(runtime)
    out=[]
    for task in tasks:
        if task.get('kind')!='ensemble' or task.get('experiment')!=6 or not task.get('scientific_case'):
            continue
        status=task.get('outcome') or task.get('status') or ''
        row={'task_key':task.get('key'),'rep':task.get('rep'),'mode':task.get('mode'),
             'status':task.get('status'),'outcome':task.get('outcome'),'validation_state':task.get('validation_state'),
             'member_comparison_present':False,'reason':task.get('reason') or ''}
        if status=='successful' and task.get('validation_state') in ('validated','validated_terminal'):
            path=runtime/'artifacts'/str(task.get('key'))/'member_comparisons.json'
            doc=loader(path) if loader else json.loads(path.read_text(encoding='utf-8'))
            normalized=validate_member_comparisons(doc,task)
            row['member_comparison_present']=True
            row['_normalized']=normalized
            row['artifact_sha256']=hashlib.sha256(path.read_bytes()).hexdigest() if loader is None else ''
        out.append(row)
    return out

def superseded_gate_history(old_rows,current_tasks):
    old=[x for x in old_rows if x.get('cell_kind')=='primary_ensemble']
    current={x.get('key'):x for x in current_tasks}
    if len(old)!=6 or len({x.get('task_key') for x in old})!=6:
        raise E6V2ReportError('expected six historical primary-ensemble gate rows')
    result=[]
    for x in old:
        key=x['task_key'];now=current.get(key)
        if x.get('outcome')!='unavailable_dependency' or str(x.get('attempt_count'))!='0':
            raise E6V2ReportError('historical gate row is not a zero-attempt dependency outcome: '+key)
        result.append({'task_key':key,'rep':x.get('rep'),'mode':x.get('method_or_mode'),
            'historical_outcome':x.get('outcome'),'historical_status':x.get('status'),
            'historical_attempt_count':x.get('attempt_count'),'current_outcome':(now or {}).get('outcome',''),
            'history_classification':'superseded_runtime_gate_history_not_scientific_failure',
            'reason':'The earlier controller gate required successful E3 direct-evaluation references before E6 posterior phases; the E6-v2 plan corrects this dependency interpretation.'})
    return result

def summarize_comparisons(rows, modes=('equal','learned')):
    keys=[(mode,kind,name) for mode in modes for kind,names in (
        ('member',MEMBER_ORDER),('tuning_best',('tuning_best_member',))) for name in names]
    out=[]
    for mode,kind,name in keys:
        match=[r for r in rows if r['mode']==mode and r['comparison_kind']==kind and r['comparator']==name]
        row={'mode':mode,'comparison_kind':kind,'comparator':name,'planned_reps':3,'matched_n':len(match)}
        for metric in METRICS:
            vals=[float(r[f'ensemble_minus_comparator_{metric}']) for r in match]
            row[metric+'_mean']=sum(vals)/len(vals) if vals else ''
            row[metric+'_sample_sd']=(sum((x-sum(vals)/len(vals))**2 for x in vals)/(len(vals)-1))**.5 if len(vals)>1 else ''
            row[metric+'_rep_values_json']=json.dumps([{'rep':r['rep'],'delta':r[f'ensemble_minus_comparator_{metric}']} for r in match],separators=(',',':'))
        out.append(row)
    return out


CLASS_NAMES=('A','F','G','K','M','GALAXY','QSO')

def _artifact_dir(runtime,key):
    parts=key.split('/') if isinstance(key,str) else []
    if not parts or any(x in ('','.','..') for x in parts):
        raise E6V2ReportError('unsafe E6 task key')
    root=(Path(runtime).resolve()/'artifacts').resolve()
    path=(root.joinpath(*parts)).resolve()
    try:path.relative_to(root)
    except ValueError:raise E6V2ReportError('E6 artifact path escapes runtime')
    return path

def load_bound_member_comparisons(runtime,task):
    art=_artifact_dir(runtime,task.get('key'))
    ep=art/'evaluation.json'; cp=art/'member_comparisons.json'
    if not ep.is_file() or not cp.is_file():
        raise E6V2ReportError('successful E6 evaluation is missing bound comparison artifacts')
    evaluation=json.loads(ep.read_text(encoding='utf-8'))
    if evaluation.get('task_key')!=task.get('key'):
        raise E6V2ReportError('E6 evaluation task key mismatch')
    if evaluation.get('e6_protocol_version')!='E6-v2':
        raise E6V2ReportError('evaluation does not attest E6-v2')
    if evaluation.get('member_comparisons_path')!='member_comparisons.json':
        raise E6V2ReportError('member comparison path is not the expected task-local path')
    actual=hashlib.sha256(cp.read_bytes()).hexdigest()
    if evaluation.get('member_comparisons_sha256')!=actual:
        raise E6V2ReportError('member comparison file SHA does not match evaluation binding')
    doc=json.loads(cp.read_text(encoding='utf-8'))
    normalized=validate_member_comparisons(doc,task)
    ledger_rel=doc.get('candidate_ledger_path')
    if task.get('mode')=='learned':
        parts=Path(ledger_rel).parts if isinstance(ledger_rel,str) else ()
        if not parts or Path(ledger_rel).is_absolute() or any(x in ('','.','..') for x in parts):
            raise E6V2ReportError('candidate ledger path must be safe and task-relative')
        ledger=(art.joinpath(*parts)).resolve()
        try: ledger.relative_to(art.resolve())
        except ValueError: raise E6V2ReportError('candidate ledger escapes task artifact')
        if not ledger.is_file() or hashlib.sha256(ledger.read_bytes()).hexdigest()!=doc.get('candidate_ledger_sha256'):
            raise E6V2ReportError('candidate ledger content does not match recorded SHA')
    for metric in METRICS:
        value=evaluation.get(metric, evaluation.get('mean_set_size') if metric=='set_size' else None)
        if value is not None and abs(float(value)-normalized['ensemble'][metric])>1e-12:
            raise E6V2ReportError('evaluation and member comparison ensemble metrics disagree: '+metric)
    for field,expected in (('calibration_n',10000),('test_n',500000)):
        if evaluation.get(field) is not None and int(evaluation[field])!=expected:
            raise E6V2ReportError('evaluation sample size mismatch: '+field)
    if evaluation.get('per_class') is not None:
        if json.dumps(evaluation['per_class'],sort_keys=True,separators=(',',':'))!=json.dumps(doc['ensemble_evaluation']['per_class'],sort_keys=True,separators=(',',':')):
            raise E6V2ReportError('evaluation and member comparison per-class metrics disagree')
    return doc,normalized,actual

def _summary_rows(comparisons):
    return summarize_comparisons(comparisons)

def _mode_paired_summary(rows):
    result=[]
    for metric in METRICS:
        values=[float(r['learned_minus_equal_'+metric]) for r in rows]
        n=len(values);mean=sum(values)/n if n else ''
        sd=(sum((x-mean)**2 for x in values)/(n-1))**.5 if n>1 else ''
        result.append({'comparison':'learned_minus_equal','metric':metric,'planned_reps':3,
                       'matched_n':n,'mean':mean,'sample_sd':sd,
                       'rep_values_json':json.dumps([{'rep':r['rep'],'delta':r['learned_minus_equal_'+metric]} for r in rows],separators=(',',':'))})
    return result

def _per_class_comparisons(doc,task):
    ens=doc['ensemble_evaluation'];enspc=ens.get('per_class',{})
    members=doc['members'];best=doc['tuning_best_member'];out=[]
    for kind,name in [('member',m) for m in MEMBER_ORDER]+[('tuning_best',best)]:
        comp=members[name].get('evaluation',members[name]).get('per_class',{})
        for idx,label in enumerate(CLASS_NAMES):
            ev=enspc.get(str(idx),enspc.get(label,{})); cv=comp.get(str(idx),comp.get(label,{}))
            if not isinstance(ev,dict) or not isinstance(cv,dict):
                raise E6V2ReportError('per-class metrics missing for class '+label)
            row={'rep':int(task['rep']),'mode':task['mode'],'comparison_kind':kind,'comparator':name,
                 'class_index':idx,'class_name':label,'task_key':task['key'],
                 'ensemble_test_n':ev.get('n',ev.get('support','')),
                 'comparator_test_n':cv.get('n',cv.get('support',''))}
            for metric,aliases in [('recall',('recall',)),('coverage',('coverage',)),('set_size',('set_size','mean_set_size'))]:
                def get(d):
                    for key in aliases:
                        if key in d:return _num(d[key],label+'.'+key)
                    raise E6V2ReportError('per-class metric missing '+label+'.'+metric)
                av,bv=get(ev),get(cv)
                row['ensemble_'+metric]=av;row['comparator_'+metric]=bv;row['ensemble_minus_comparator_'+metric]=av-bv
            out.append(row)
    return out

def _write_csv(path,rows,fields=None):
    path=Path(path)
    if not rows and not fields:
        raise E6V2ReportError('field names required for an empty CSV')
    names=list(fields or rows[0].keys())
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=names,extrasaction='ignore');w.writeheader()
        for r in rows:w.writerow(r)


def _mode_paired(ensemble_rows):
    byrep={}
    for r in ensemble_rows:
        byrep.setdefault(int(r['rep']),{})[r['mode']]=r
    rows=[]
    for rep,pair in sorted(byrep.items()):
        if not {'equal','learned'}<=set(pair):continue
        e,l=pair['equal'],pair['learned']
        for field in ('posterior_fingerprint','fit_ids_sha256','tuning_ids_sha256','calibration_ids_sha256','test_ids_sha256'):
            if e.get(field)!=l.get(field):
                raise E6V2ReportError('equal/learned comparison does not share paired provenance: '+field)
        row={'rep':rep,'equal_task_key':e['task_key'],'learned_task_key':l['task_key']}
        for metric in METRICS:
            row['equal_'+metric]=e[metric];row['learned_'+metric]=l[metric]
            row['learned_minus_equal_'+metric]=l[metric]-e[metric]
        rows.append(row)
    return rows

def _weight_stability(weight_rows):
    bymode={}
    for r in weight_rows:bymode.setdefault(r['mode'],[]).append(r)
    pairs=[]
    for mode,records in bymode.items():
        records=sorted(records,key=lambda x:int(x['rep']))
        for i,a in enumerate(records):
            for b in records[i+1:]:
                av=[float(a[f'weight_{m}']) for m in MEMBER_ORDER]
                bv=[float(b[f'weight_{m}']) for m in MEMBER_ORDER]
                l1=sum(abs(x-y) for x,y in zip(av,bv))
                euclidean=sum((x-y)**2 for x,y in zip(av,bv))**.5
                pairs.append({'mode':mode,'rep_a':a['rep'],'rep_b':b['rep'],
                              'task_a':a['task_key'],'task_b':b['task_key'],
                              'l1_distance':l1,'euclidean_distance':euclidean})
    return pairs

def _per_class_summary(rows):
    grouped={}
    for r in rows:
        key=(r['mode'],r['comparison_kind'],r['comparator'],r['class_index'],r['class_name'])
        grouped.setdefault(key,[]).append(r)
    out=[]
    for key,group in sorted(grouped.items()):
        row=dict(zip(('mode','comparison_kind','comparator','class_index','class_name'),key))
        row['planned_reps']=3;row['matched_n']=len(group)
        for metric in ('recall','coverage','set_size'):
            values=[float(x[f'ensemble_minus_comparator_{metric}']) for x in group]
            row[metric+'_mean']=sum(values)/len(values) if values else ''
            row[metric+'_sample_sd']=(sum((x-row[metric+'_mean'])**2 for x in values)/(len(values)-1))**.5 if len(values)>1 else ''
            row[metric+'_rep_values_json']=json.dumps([{'rep':x['rep'],'delta':x[f'ensemble_minus_comparator_{metric}']} for x in group],separators=(',',':'))
        out.append(row)
    return out

def _partial_tuning_evidence(runtime,e6,output):
    runtime=Path(runtime);output=Path(output);rows=[];weight_rows=[]
    for task in sorted(e6,key=lambda x:(int(x.get('rep',0)),str(x.get('mode')))):
        key=task.get('key');art=_artifact_dir(runtime,key)
        wf=art/'frozen_weights.json';ledger_src=None;doc=None;ledger_doc=None;state='no_frozen_tuning_artifact'
        source_sha='';ledger_sha='';weight_values=[];ledger_count='';seed='';frozen_utc=''
        copied_weight='';copied_ledger=''
        if wf.is_file():
            try:
                raw=wf.read_bytes();source_sha=hashlib.sha256(raw).hexdigest();doc=json.loads(raw)
                if doc.get('mode')!=task.get('mode') or doc.get('member_order')!=list(MEMBER_ORDER):
                    raise E6V2ReportError('frozen weights mode/member order mismatch')
                if doc.get('frozen_before_calibration_and_test') is not True:
                    raise E6V2ReportError('weights lack pre-calibration/test freeze marker')
                weight_values=_weights_vector({'mode':doc.get('mode'),'selected_weights':doc.get('weights')})
                frozen_utc=doc.get('weights_frozen_utc') or ''
                seed=doc.get('weight_search_seed','')
                if task.get('mode')=='learned':
                    rel=doc.get('candidate_ledger')
                    parts=Path(rel).parts if isinstance(rel,str) else ()
                    if not parts or Path(rel).is_absolute() or any(x in ('','.','..') for x in parts):
                        raise E6V2ReportError('learned frozen weights lack a safe candidate ledger path')
                    ledger_src=art.joinpath(*parts).resolve()
                    try:ledger_src.relative_to(art.resolve())
                    except ValueError:raise E6V2ReportError('candidate ledger escapes task artifact directory')
                    if not ledger_src.is_file():raise E6V2ReportError('candidate ledger file is missing')
                    raw_ledger=ledger_src.read_bytes();ledger_sha=hashlib.sha256(raw_ledger).hexdigest();ledger_doc=json.loads(raw_ledger)
                    candidates=ledger_doc.get('candidates')
                    if not isinstance(candidates,list) or ledger_doc.get('member_order')!=list(MEMBER_ORDER):
                        raise E6V2ReportError('candidate ledger does not preserve the full declared search')
                    ledger_count=len(candidates);selected=int(ledger_doc.get('selected_candidate',-1))
                    if selected<0 or selected>=len(candidates) or candidates[selected].get('weights')!=weight_values:
                        raise E6V2ReportError('candidate ledger selected weights differ from frozen weights')
                    if ledger_doc.get('seed')!=seed:raise E6V2ReportError('candidate ledger seed differs from frozen weights')
                elif doc.get('candidate_ledger') not in (None,''):
                    raise E6V2ReportError('equal mode must not carry a learned candidate ledger')
                state='validated_frozen_tuning_evidence'
            except Exception as exc:
                state='invalid_partial_tuning_evidence';weight_values=[];ledger_count=''
                # Do not publish malformed weights or candidate data as valid evidence.
                source_sha=hashlib.sha256(wf.read_bytes()).hexdigest()
        if state=='validated_frozen_tuning_evidence':
            rel_parts=Path(*key.split('/'))
            target_dir=output/'partial_tuning'/rel_parts
            target_dir.mkdir(parents=True,exist_ok=True)
            (target_dir/'frozen_weights.json').write_bytes(wf.read_bytes())
            copied_weight=(Path('partial_tuning')/rel_parts/'frozen_weights.json').as_posix()
            if ledger_src is not None:
                (target_dir/'candidate_ledger.json').write_bytes(ledger_src.read_bytes())
                copied_ledger=(Path('partial_tuning')/rel_parts/'candidate_ledger.json').as_posix()
            if weight_values:
                weight_rows.append({'rep':task.get('rep'),'mode':task.get('mode'),'task_key':key,
                                    'outcome':task.get('outcome'),'weights':weight_values})
        rows.append({'task_key':key,'rep':task.get('rep'),'mode':task.get('mode'),
                     'task_outcome':task.get('outcome') or task.get('status'),'evidence_state':state,
                     'stage':'tuning_weights_frozen; calibration/test phases not evidenced' if state=='validated_frozen_tuning_evidence' and task.get('outcome')!='successful' else state,
                     'frozen_weights_source_sha256':source_sha,'frozen_weights_archive_path':copied_weight,
                     'candidate_ledger_source_sha256':ledger_sha,'candidate_ledger_archive_path':copied_ledger,
                     'candidate_count':ledger_count,'weight_search_seed':seed,
                     'weights_frozen_utc':frozen_utc,'weights_json':json.dumps(weight_values,separators=(',',':')) if weight_values else '',
                     'test_evaluation_present':str(task.get('outcome')=='successful' and (art/'evaluation.json').is_file()),
                     'performance_metrics_included':False})
    return rows,weight_rows

def _partial_weight_stability(rows):
    grouped={}
    for row in rows:grouped.setdefault(row['mode'],[]).append(row)
    out=[]
    for mode,records in sorted(grouped.items()):
        records=sorted(records,key=lambda r:int(r['rep']))
        for i,a in enumerate(records):
            for b in records[i+1:]:
                av=a.get('weights',[]);bv=b.get('weights',[])
                if len(av)!=5 or len(bv)!=5:continue
                delta=[x-y for x,y in zip(av,bv)]
                out.append({'mode':mode,'rep_a':a['rep'],'rep_b':b['rep'],'task_a':a['task_key'],'task_b':b['task_key'],
                            'outcome_a':a['outcome'],'outcome_b':b['outcome'],'matched_tuning_selections':2,
                            'l1_distance':sum(abs(x) for x in delta),'euclidean_distance':sum(x*x for x in delta)**.5,
                            'basis':'validated frozen tuning weights only; no test metric selection'})
    return out

def export_v2_outputs(runtime,tasks,old_ledger_path,output):
    runtime=Path(runtime);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    e6=[t for t in tasks if t.get('experiment')==6 and t.get('kind')=='ensemble' and t.get('scientific_case')]
    if len(e6)!=6 or len({t.get('key') for t in e6})!=6:
        raise E6V2ReportError('expected six E6 primary ensemble tasks')
    actual={(int(t.get('rep',0)),t.get('mode')) for t in e6}
    expected={(rep,mode) for rep in (1,2,3) for mode in ('equal','learned')}
    if actual!=expected:
        raise E6V2ReportError('E6 primary ensemble grid must contain one equal and learned task per repetition')
    with Path(old_ledger_path).open(newline='',encoding='utf-8') as f:
        old_rows=list(csv.DictReader(f))
    history=superseded_gate_history(old_rows,e6)
    historical_refs=[dict(x) for x in old_rows if x.get('cell_kind')=='member_reference']
    if len(historical_refs)!=15:
        raise E6V2ReportError('expected fifteen historical E3-derived member-reference rows')
    for x in historical_refs:
        x['provenance_group']='historical_E3_direct_reference_not_E6_scoring'
    availability=[]; ensemble_rows=[];member_rows=[];comparisons=[];perclass=[];weights=[];costs=[]
    for task in sorted(e6,key=lambda x:(int(x.get('rep',0)),str(x.get('mode')))):
        status=task.get('outcome') or task.get('status') or ''
        row={'task_key':task.get('key'),'rep':task.get('rep'),'mode':task.get('mode'),
             'status':task.get('status'),'outcome':task.get('outcome'),
             'validation_state':task.get('validation_state'),'member_comparison_present':False,
             'reason':task.get('reason') or ''}
        if status=='successful' and task.get('validation_state') in ('validated','validated_terminal'):
            doc,norm,digest=load_bound_member_comparisons(runtime,task)
            row['member_comparison_present']=True;row['member_comparisons_sha256']=digest
            ensemble_rows.append(norm['ensemble']);member_rows.extend(norm['members'])
            comparisons.extend(norm['comparisons']);weights.append(norm['weights']);costs.extend(norm['costs'])
            perclass.extend(_per_class_comparisons(doc,task))
        availability.append(row)
    summaries=_summary_rows(comparisons)
    ensemble_by_task={x['task_key']:x for x in ensemble_rows}
    main_ledger=[]
    for x in historical_refs:
        row={**x,'provenance_group':'historical_E3_direct_reference_not_E6_scoring'}
        main_ledger.append(row)
    for x in availability:
        e=ensemble_by_task.get(x['task_key'],{})
        main_ledger.append({'task_key':x['task_key'],'rep':x['rep'],'cell_kind':'primary_ensemble',
            'method_or_mode':x['mode'],'status':x['status'],'outcome':x['outcome'],
            'validation_state':x['validation_state'],'provenance_group':'E6_v2_primary_ensemble',
            'evaluation_present':str(bool(e)),'balanced_accuracy':e.get('balanced_accuracy',''),
            'coverage':e.get('coverage',''),'mean_set_size':e.get('set_size',''),
            'reason':x.get('reason','')})
    if len(main_ledger)!=21:
        raise E6V2ReportError('combined E6 ledger must contain 15 historical refs and six primary ensembles')
    mode_pairs=_mode_paired(ensemble_rows)
    mode_summary=_mode_paired_summary(mode_pairs)
    perclass_summary=_per_class_summary(perclass)
    weight_stability=_weight_stability(weights)
    partial_tuning,partial_weight_rows=_partial_tuning_evidence(runtime,e6,output)
    partial_weight_stability=_partial_weight_stability(partial_weight_rows)
    files={
      'E6_V2_MAIN_CELL_LEDGER_21.csv':(main_ledger,['task_key','rep','cell_kind','method_or_mode','family','outcome','status','validation_state','provenance_group','evaluation_present','balanced_accuracy','coverage','mean_set_size','reason']),
      'E6_V2_AVAILABILITY.csv':(availability,['task_key','rep','mode','status','outcome','validation_state','member_comparison_present','member_comparisons_sha256','reason']),
      'E6_V2_ENSEMBLE_REPETITIONS.csv':(ensemble_rows,['rep','mode','task_key','balanced_accuracy','coverage','set_size','tuning_best_member','tuning_best_balanced_accuracy','selected_weights_json','posterior_fingerprint','fit_ids_sha256','tuning_ids_sha256','calibration_ids_sha256','test_ids_sha256','candidate_ledger_path','candidate_ledger_sha256','per_class_json','confusion_matrix_json']),
      'E6_V2_MEMBER_COMPARISONS.csv':(member_rows,['rep','mode','member','source_task_key','fit_key','pipeline_sha256','fit_ids_sha256','posterior_fingerprint','tuning_ids_sha256','calibration_ids_sha256','test_ids_sha256','score_rule','quantile_rule','threshold','calibration_n','test_n','tuning_balanced_accuracy','balanced_accuracy','coverage','set_size','per_class_json','confusion_matrix_json']),
      'E6_V2_PAIRED_COMPARISONS.csv':(comparisons,['rep','mode','comparison_kind','comparator','task_key','ensemble_balanced_accuracy','ensemble_coverage','ensemble_set_size','comparator_balanced_accuracy','comparator_coverage','comparator_set_size','ensemble_minus_comparator_balanced_accuracy','ensemble_minus_comparator_coverage','ensemble_minus_comparator_set_size']),
      'E6_V2_PAIRED_SUMMARY.csv':(summaries,['mode','comparison_kind','comparator','planned_reps','matched_n','balanced_accuracy_mean','balanced_accuracy_sample_sd','balanced_accuracy_rep_values_json','coverage_mean','coverage_sample_sd','coverage_rep_values_json','set_size_mean','set_size_sample_sd','set_size_rep_values_json']),
      'E6_V2_MODE_PAIRED.csv':(mode_pairs,['rep','equal_task_key','learned_task_key','equal_balanced_accuracy','learned_balanced_accuracy','learned_minus_equal_balanced_accuracy','equal_coverage','learned_coverage','learned_minus_equal_coverage','equal_set_size','learned_set_size','learned_minus_equal_set_size']),
      'E6_V2_MODE_PAIRED_SUMMARY.csv':(mode_summary,['comparison','metric','planned_reps','matched_n','mean','sample_sd','rep_values_json']),
      'E6_V2_PER_CLASS_COMPARISONS.csv':(perclass,['rep','mode','comparison_kind','comparator','class_index','class_name','task_key','ensemble_test_n','comparator_test_n','ensemble_recall','comparator_recall','ensemble_minus_comparator_recall','ensemble_coverage','comparator_coverage','ensemble_minus_comparator_coverage','ensemble_set_size','comparator_set_size','ensemble_minus_comparator_set_size']),
      'E6_V2_PER_CLASS_SUMMARY.csv':(perclass_summary,['mode','comparison_kind','comparator','class_index','class_name','planned_reps','matched_n','recall_mean','recall_sample_sd','recall_rep_values_json','coverage_mean','coverage_sample_sd','coverage_rep_values_json','set_size_mean','set_size_sample_sd','set_size_rep_values_json']),
      'E6_V2_WEIGHTS.csv':(weights,['rep','mode','task_key','weight_gmm','weight_copula','weight_arf','weight_kde','weight_chow_liu','tuning_best_member','candidate_ledger_path','candidate_ledger_sha256']),
      'E6_V2_PHASE_COSTS.csv':(costs,['rep','mode','task_key','phase','seconds','peak_tree_rss_kib','cache_hit','source_task_key','source_attempt_id','resource_profile','phase_sha256','artifact_sha256']),
      'E6_V2_WEIGHT_STABILITY.csv':(weight_stability,['mode','rep_a','rep_b','task_a','task_b','l1_distance','euclidean_distance']),
      'E6_V2_PARTIAL_TUNING_EVIDENCE.csv':(partial_tuning,['task_key','rep','mode','task_outcome','evidence_state','stage','frozen_weights_source_sha256','frozen_weights_archive_path','candidate_ledger_source_sha256','candidate_ledger_archive_path','candidate_count','weight_search_seed','weights_frozen_utc','weights_json','test_evaluation_present','performance_metrics_included']),
      'E6_V2_TUNING_WEIGHT_STABILITY.csv':(partial_weight_stability,['mode','rep_a','rep_b','task_a','task_b','outcome_a','outcome_b','matched_tuning_selections','l1_distance','euclidean_distance','basis']),
      'E6_SUPERSEDED_AVAILABILITY_GATE_HISTORY.csv':(history,['task_key','rep','mode','historical_outcome','historical_status','historical_attempt_count','current_outcome','history_classification','reason'])
    }
    for name,(rs,fields) in files.items():_write_csv(output/name,rs,fields)
    return {name:len(rs) for name,(rs,_) in files.items()}


def _has_validated_member_comparison(row):
    present=row.get('member_comparison_present')
    if not (present is True or (isinstance(present,str) and present.strip().lower() in {'true','1','yes'})):
        return False
    digest=row.get('member_comparisons_sha256')
    return isinstance(digest,str) and len(digest)==64 and all(c in '0123456789abcdef' for c in digest.lower())


def render_status_section(availability, historical_gate, partial_tuning=None):
    if len(availability)!=6 or len(historical_gate)!=6:
        raise E6V2ReportError('status section requires all six current and six superseded primary cells')
    current_counts={}
    for row in availability:
        key=row.get('outcome') or row.get('status') or 'unclassified'
        current_counts[key]=current_counts.get(key,0)+1
    successes=sum(1 for r in availability if _has_validated_member_comparison(r))
    partial_tuning=partial_tuning or []
    partial=[r for r in partial_tuning if r.get('evidence_state')=='validated_frozen_tuning_evidence' and r.get('task_outcome')!='successful']
    counts=', '.join(f'{k}={v}' for k,v in sorted(current_counts.items())) or 'none observed'
    partial_note=(f'{len(partial)} unsuccessful primary task(s) retain validated frozen tuning weights; '
                  'their saved weights and, for learned mode, full candidate ledger are reported as tuning-only evidence without test metrics. '
                  'See E6_V2_PARTIAL_TUNING_EVIDENCE.csv and E6_V2_TUNING_WEIGHT_STABILITY.csv. '
                  'These tuning artifacts are not successful ensemble evaluations.')
    return ('## E6-v2 corrected ensemble outcomes\n\n'
        'The original six primary-ensemble rows were marked unavailable by a runtime gate that required successful E3 direct-evaluation references before E6 posterior work. The E6 protocol requires compatible fitted members and E6-specific normalized posterior phases; an E3 direct KDE test timeout does not alone establish that the fitted KDE model is unavailable. The six earlier zero-attempt states are retained separately in E6_SUPERSEDED_AVAILABILITY_GATE_HISTORY.csv as superseded gate history, not scientific failures or valid E6 attempts. This dependency interpretation was amended after the first E3 KDE direct-evaluation timeout; it is not represented as the original executable gate at freeze.\n\n'
        f'Current E6-v2 plan: {len(availability)} primary ensemble cells; outcomes in this registry snapshot: {counts}; {successes} of 6 have a successful validation-bound member_comparisons artifact. Historical E3-reference evaluations remain a distinct provenance group; their 15 rows are not E6-derived member comparison results. Only validated E6-v2 artifacts contribute ensemble/member metrics, paired differences, weight stability, and phase-cost rows. A failed or unavailable E6 posterior phase yields no score.\n\n'
        +partial_note+'\n\n'
        'All reports remain descriptive: actual matched repetitions only, sample SD when n >= 2 (undefined for n=1), no bootstrap/significance claims, and no universal ensemble-benefit claim. E6 ensemble test metrics do not constitute a new untouched test set because the fixed cohort was previously evaluated in E1/E2/E3.\n')
