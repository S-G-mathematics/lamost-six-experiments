"""Pure helpers for overall case-index snapshots; no scientific dependencies."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json

RESOURCE_KEYS={
 'admission_profile_id','admission_reservation_bytes','worker_memory_limit_gib','worker_memory_gib',
 'worker_admission_reservation_gib','worker_admission_reservation_gib_by_class','trial_seconds','trial_timeout_seconds',
 'phase_seconds','phase_timeout_seconds','prediction_chunk_rows','nested_threads','native_threads',
 'termination_grace_seconds','max_workers','worker_count_ceiling','admission_pause_below_gib',
 'host_os_harbor_reserve_gib','cpu_reserve_cores','alias_reservation_gib','bounded_helper_reservation_gib',
 'commitment_growth_margin_gib','max_operational_recoveries','resource_policy_version'
}
SOURCE_KEYS={'resource_profile_source','admission_profile_source','resource_policy_source'}

def resource_projection(task, metadata):
    """Allowlisted exact policy facts plus source labels; never exports process receipts."""
    profile=metadata.get('resource_profile')
    out={}
    if isinstance(profile,dict):
        for k in RESOURCE_KEYS & profile.keys():out[k]=profile[k]
        for k in SOURCE_KEYS & profile.keys():
            if isinstance(profile[k],str):out[k]=profile[k]
    for k in RESOURCE_KEYS:
        if k in metadata:out[k]=metadata[k]
    for k in SOURCE_KEYS:
        if isinstance(metadata.get(k),str):out[k]=metadata[k]
    if task.get('kind')=='alias':
        out['resource_note']='evaluation alias; resource values describe referenced computation only when explicitly sourced'
    return out

def attempt_projection(metadata):
    """Keep stable attempt references, never PIDs, start ticks, argv, or command lines."""
    allowed=('attempt_id','attempt_key','attempt_number','sequence')
    x=metadata.get('attempt_identity')
    if isinstance(x,str):return x
    if isinstance(x,dict):
        return {k:x[k] for k in allowed if k in x}
    attempts=metadata.get('attempts') or []
    if attempts and isinstance(attempts[-1],dict):
        return {k:attempts[-1][k] for k in allowed if k in attempts[-1]}
    return {}

def model_provenance(task, metadata):
    if task.get('kind')=='alias':
        refs=task.get('dependencies') or []
        return 'evaluation_alias_of:'+','.join(map(str,refs)) if refs else 'evaluation_alias_source_unavailable'
    fit=task.get('fit_key') or metadata.get('fit_key')
    if fit:return 'fit_reference:'+str(fit)
    prov=metadata.get('model_provenance')
    if isinstance(prov,dict):return str(prov.get('kind') or 'recorded_provenance_unspecified')
    if isinstance(prov,str):return prov
    return 'later_experiment_owned' if task.get('kind')=='fit' else 'provenance_not_recorded'

def normalize_state(status, outcome, kernel_proven=False):
    if status=='validated_terminal':
        mapping={'successful':'successful','scientific_failure':'scientific_failure',
          'unsupported':'unsupported','unavailable_dependency':'unavailable_dependency','user_stopped':'user_stopped'}
        if outcome not in mapping:raise ValueError('unmapped terminal outcome '+str(outcome))
        return mapping[outcome]
    if status=='running':return 'running' if kernel_proven else 'pending'
    mapping={'planned':'pending','waiting_for_dependency':'pending','operationally_interrupted':'pending',
      'operationally_invalid':'pending','user_stopped':'user_stopped','not_attempted_user_stopped':'not_attempted_user_stopped'}
    if status not in mapping:raise ValueError('unmapped state '+str(status))
    return mapping[status]

def later_status_counts(rows):
    """Counts current later-case statuses without assuming completion percentages."""
    c=Counter()
    for row in rows:c[(int(row['experiment']),row['status_normalized'])]+=1
    return {str(e):dict(sorted((state,n) for (exp,state),n in c.items() if exp==e)) for e in sorted({k[0] for k in c})}

def validate_planned_experiment_counts(rows, expected):
    c=Counter(int(r['experiment']) for r in rows)
    if dict(c)!=dict(expected):raise ValueError(f'planned scientific case counts changed: {dict(c)}')
    return dict(c)

def manifest_budget(manifest):
    budgets=manifest.get('budgets')
    if not isinstance(budgets,list) or len(budgets)!=1:
        raise ValueError('expected one frozen development budget in experiment manifest')
    return budgets[0]

def _recorded_attempt_id(task):
    value=task.get('attempt_id')
    if isinstance(value,str) and value:return value
    ident=task.get('attempt_identity')
    if isinstance(ident,dict) and ident.get('attempt_id'):return str(ident['attempt_id'])
    if isinstance(ident,str) and ident:
        try:
            obj=json.loads(ident)
            if isinstance(obj,dict) and obj.get('attempt_id'):return str(obj['attempt_id'])
        except ValueError:return ident
    attempts=task.get('attempts') or []
    if attempts and isinstance(attempts[-1],dict) and attempts[-1].get('attempt_id'):
        return str(attempts[-1]['attempt_id'])
    return ''

def _task_request_path(task):
    for k in ('request_path','worker_request_path','phase_request_path','worker_request'):
        v=task.get(k)
        if isinstance(v,str) and v:return v
    ident=task.get('attempt_identity')
    if isinstance(ident,dict):
        for k in ('request_path','worker_request_path','phase_request_path'):
            v=ident.get(k)
            if isinstance(v,str) and v:return v
    attempts=task.get('attempts') or []
    if attempts and isinstance(attempts[-1],dict):
        for k in ('request_path','worker_request_path','phase_request_path'):
            v=attempts[-1].get(k)
            if isinstance(v,str) and v:return v
    return ''

def _expected_worker(task,runtime_root):
    entry=task.get('worker_entrypoint') or task.get('entrypoint')
    if entry:return str(entry)
    if runtime_root is None:return ''
    method=str(task.get('method') or '')
    relative='source/svm_margin/worker.py' if method in ('linear_svm','rbf_svm') else 'source/worker.py'
    return str(Path(runtime_root).resolve()/relative)

def _resolve_argv_path(token,cwd):
    p=Path(token)
    return str((p if p.is_absolute() else Path(cwd)/p).resolve())

def _request_identity_matches(request_path,key,attempt_id):
    try: doc=json.loads(Path(request_path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return False
    taskdoc=doc.get('task') if isinstance(doc,dict) else None
    if not isinstance(taskdoc,dict):
        nested=doc.get('request') if isinstance(doc,dict) else None
        taskdoc=nested.get('task') if isinstance(nested,dict) else None
    if not isinstance(taskdoc,dict):return False
    taskkey=taskdoc.get('key') or taskdoc.get('task_key')
    if taskkey!=key:return False
    if attempt_id:
        attempt=taskdoc.get('attempt_id') or (doc.get('attempt_id') if isinstance(doc,dict) else None)
        if attempt is None and isinstance(doc,dict) and isinstance(doc.get('attempt'),dict):
            attempt=doc['attempt'].get('attempt_id')
        if str(attempt or '')!=attempt_id:return False
    return True

def kernel_process_proven(task, proc_root='/proc', runtime_root=None):
    """Proof from current /proc identity, exact NUL argv tokens, and nested request identity."""
    try:
        pid=int(task.get('pid'));expected_ticks=int(task.get('process_start_ticks'))
        key=str(task.get('key') or '');request=_task_request_path(task)
        entry=_expected_worker(task,runtime_root);attempt_id=_recorded_attempt_id(task)
        if pid<=0 or expected_ticks<=0 or not key or not request or not entry:return False
        proc=Path(proc_root)/str(pid)
        _,_,right=(proc/'stat').read_text().rpartition(')')
        fields=right.strip().split()
        if len(fields)<=19 or int(fields[19])!=expected_ticks:return False
        cwd=(proc/'cwd').resolve()
        argv=[x.decode(errors='replace') for x in (proc/'cmdline').read_bytes().split(b'\0') if x]
        resolved_entry=str(Path(entry).resolve() if Path(entry).is_absolute() else (cwd/entry).resolve())
        entry_matches=any(_resolve_argv_path(token,cwd)==resolved_entry for token in argv)
        expected_request=str(Path(request).resolve() if Path(request).is_absolute() else (cwd/request).resolve())
        # Request path may be a positional argv token or an option value; match the exact
        # NUL-delimited path token after resolving relative paths against the process cwd.
        request_matches=any(_resolve_argv_path(token,cwd)==expected_request for token in argv)
        if not entry_matches or not request_matches:return False
        if not _request_identity_matches(expected_request,key,attempt_id):return False
        return True
    except (OSError,ValueError,TypeError,IndexError):
        return False
