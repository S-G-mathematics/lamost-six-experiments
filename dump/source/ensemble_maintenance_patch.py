"""Isolated maintenance adapter for E6 prediction timeout/RSS terminal taxonomy.

This module is intentionally excluded from active ensemble execution until the
controller is paused and `apply_patch_file` is explicitly invoked by the owner.
It contains no model fitting or automatic resource-policy changes.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ACTIVE_SOURCE_SHA256 = 'a236d5e7c8a8ed33259c498d1fea3a901f7fd603542a2e140ac7c86146596e7c'
PATCH_MARKER = 'E6_PHASE_FAILURE_TAXONOMY_V1'
TERMINAL_PREFIX = 'E6_PHASE_TERMINAL:'

class E6PhaseFailure(RuntimeError):
    def __init__(self, record):
        self.record = dict(record)
        super().__init__(f"{TERMINAL_PREFIX} {self.record.get('failure_code')} in {self.record.get('stage')}")

class E6CachedPhaseFailure(RuntimeError):
    def __init__(self, record):
        self.record = dict(record)
        super().__init__(f"E6 phase dependency previously failed: {self.record.get('failure_code')} in {self.record.get('stage')}")

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _json_atomic(path, obj):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=p.name+'.',suffix='.tmp',dir=str(p.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def classify_prediction_phase_exception(exc, stage, fingerprint, mode, task_key):
    """Return evidence only for the exact supervised timeout/RSS exception shape."""
    message=str(exc)
    match=re.match(r'^prediction_(timeout|rss_limit):\s*(\{.*\})\s*$',message,re.DOTALL)
    if not match: return None
    reason=match.group(1)
    try: receipt=ast.literal_eval(match.group(2))
    except Exception: return None
    if not isinstance(receipt,dict) or receipt.get('reason')!=reason: return None
    seconds=receipt.get('seconds'); peak=receipt.get('peak_tree_rss_kib')
    if not isinstance(seconds,(int,float)) or not isinstance(peak,int): return None
    return {
        'status':'scientific_failure',
        'failure_code':'prediction_timeout' if reason=='timeout' else 'prediction_rss_limit',
        'reason':reason,
        'stage':str(stage),
        'source_mode':str(mode),
        'source_task_key':str(task_key),
        'observed_utc':utc_now(),
        'phase_seconds':float(seconds),
        'peak_tree_rss_kib':int(peak),
        'phase_exit_code':receipt.get('exit_code'),
        'phase_receipt':receipt,
        'exception_message':message,
        'fingerprint':fingerprint,
        'fingerprint_sha256':hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'policy':{'prediction_timeout_seconds':600,'rss_limit_kib':10*1024*1024,'termination_grace_seconds':30},
        'valid_evaluation_metrics_written':False,
    }

def _failure_path(shared_dir,stage):
    return Path(shared_dir)/f'{stage}.scientific_failure.json'

def _cached_record(path, fingerprint):
    try: record=json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception as exc: raise ValueError(f'corrupt E6 phase failure marker: {path}: {exc}') from exc
    expected=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if record.get('fingerprint_sha256')!=expected or record.get('fingerprint')!=fingerprint:
        raise ValueError(f'E6 phase failure marker fingerprint mismatch: {path}')
    if record.get('status')!='scientific_failure' or record.get('failure_code') not in {'prediction_timeout','prediction_rss_limit'}:
        raise ValueError(f'E6 phase failure marker has invalid terminal state: {path}')
    return record

def run_phase_with_terminal_failure_cache(*, stage, shared_dir, fingerprint, mode, task_key, runner):
    """Run one stage under the caller's shared lock; persist only evidenced failures.

    The existing executor acquires the per-fingerprint `phase.lock` around this
    call. A matching prior marker prevents both same-task operational recovery
    and the paired mode from restarting the identical phase.
    """
    marker=_failure_path(shared_dir,stage)
    if marker.exists():
        record=_cached_record(marker,fingerprint)
        if record.get('source_task_key')==str(task_key): raise E6PhaseFailure(record)
        raise E6CachedPhaseFailure(record)
    try:
        return runner()
    except Exception as exc:
        record=classify_prediction_phase_exception(exc,stage,fingerprint,mode,task_key)
        if record is None: raise
        record['phase_cache_directory']=str(Path(shared_dir))
        record['phase_failure_marker']=str(marker)
        _json_atomic(marker,record)
        raise E6PhaseFailure(record) from exc

def _safe_task_output(runtime,task):
    key=task.get('key')
    if not isinstance(key,str) or not key or Path(key).is_absolute() or any(part in {'.','..'} for part in Path(key).parts):
        raise ValueError('unsafe E6 task key while preserving phase evidence')
    root=(Path(runtime)/'artifacts').resolve(); out=(root/key).resolve()
    if root not in out.parents: raise ValueError('E6 task key escapes artifacts')
    out.mkdir(parents=True,exist_ok=True)
    return out

def result_from_terminal_exception(exc, task, runtime):
    """Convert a known first-observed scientific phase failure into no-score outcome."""
    if not isinstance(exc,E6PhaseFailure): raise TypeError(f'expected E6PhaseFailure, got {type(exc).__name__}')
    out=_safe_task_output(runtime,task)
    record={**exc.record,'task_key':task.get('key'),'mode':task.get('mode'),'terminal_state':'scientific_failure','valid_evaluation_metrics_written':False}
    _json_atomic(out/'E6_PHASE_TERMINAL.json',record)
    return {'status':'scientific_failure','reason':f"{record['failure_code']} during {record['stage']}",'phase_evidence_path':str(out/'E6_PHASE_TERMINAL.json'),'phase_evidence':record,'evaluation':None}

def _cached_outcome(exc,task,runtime):
    record={**exc.record,'task_key':task.get('key'),'mode':task.get('mode'),'terminal_state':'unavailable_dependency','dependency_failure_marker':exc.record.get('phase_failure_marker'),'valid_evaluation_metrics_written':False}
    out=_safe_task_output(runtime,task)
    _json_atomic(out/'E6_PHASE_TERMINAL.json',record)
    return {'status':'unavailable_dependency','reason':f"required shared E6 {record.get('stage')} posterior phase previously terminated under the fixed timeout/RSS policy",'phase_evidence_path':str(out/'E6_PHASE_TERMINAL.json'),'source_task_key':record.get('source_task_key'),'phase_evidence':record,'evaluation':None}

def execute_with_terminal_classification(original_execute, task, runtime):
    """Preserve known scientific failures; re-raise all unrelated implementation defects."""
    try: return original_execute(task,runtime)
    except E6PhaseFailure as exc: return result_from_terminal_exception(exc,task,runtime)
    except E6CachedPhaseFailure as exc: return _cached_outcome(exc,task,runtime)

def _patched_execute_snippet():
    return '''\ndef execute(task,runtime)->dict:\n    return execute_with_terminal_classification(_execute_e6_before_phase_taxonomy,task,runtime)\n'''

def _patched_stage_snippet():
    return '''            failure_marker=shared/f'{stage}.scientific_failure.json'\n            if failure_marker.exists():\n                record=_cached_record(failure_marker,fingerprint)\n                if record.get('source_task_key')==str(task['key']): raise E6PhaseFailure(record)\n                raise E6CachedPhaseFailure(record)\n            if cp.exists():\n                try: scores=_load_scores(cp)\n                except Exception: scores=None\n            else: scores=None\n            if scores is None:\n                rec=run_phase_with_terminal_failure_cache(stage=stage,shared_dir=shared,fingerprint=fingerprint,mode=mode,task_key=task['key'],runner=lambda:_run_prediction_phase(paths,X,cp))\n                scores=_load_scores(cp); phase_times[f'{stage}_seconds']=rec['seconds']; phase_times[f'{stage}_peak_tree_rss_kib']=rec['peak_tree_rss_kib']; phase_times[f'{stage}_cache_hit']=False\n'''

def prepare_patched_source(original_source):
    """Return modified source text; does not write or execute it."""
    source=original_source
    if PATCH_MARKER in source: raise ValueError('maintenance patch already appears applied')
    expected_import='import numpy as np\n'
    if expected_import not in source: raise ValueError('unexpected ensemble.py import block')
    source=source.replace(expected_import,expected_import+f'from ensemble_maintenance_patch import {", ".join(("E6PhaseFailure","E6CachedPhaseFailure","_cached_record","run_phase_with_terminal_failure_cache","execute_with_terminal_classification"))}  # {PATCH_MARKER}\n',1)
    original_stage='''            if cp.exists():\n                try: scores=_load_scores(cp)\n                except Exception: scores=None\n            else: scores=None\n            if scores is None:\n                rec=_run_prediction_phase(paths,X,cp)\n                scores=_load_scores(cp); phase_times[f'{stage}_seconds']=rec['seconds']; phase_times[f'{stage}_peak_tree_rss_kib']=rec['peak_tree_rss_kib']; phase_times[f'{stage}_cache_hit']=False\n'''
    if original_stage not in source: raise ValueError('expected E6 shared-stage block not found')
    source=source.replace(original_stage,_patched_stage_snippet(),1)
    declaration='def execute(task,runtime)->dict:\n'
    if source.count(declaration)!=1: raise ValueError('expected exactly one active E6 execute definition')
    source=source.replace(declaration,'def _execute_e6_before_phase_taxonomy(task,runtime)->dict:\n',1)
    source=source.rstrip()+_patched_execute_snippet()
    compile(source,'ensemble.py','exec')
    return source

def apply_patch_file(target_path, expected_sha256=ACTIVE_SOURCE_SHA256):
    """Apply only after the queue is paused; backs up the exact frozen source first."""
    target=Path(target_path); raw=target.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected_sha256: raise ValueError(f'ensemble.py changed since this maintenance patch was prepared: {digest}')
    source=raw.decode('utf-8-sig')
    modified=prepare_patched_source(source).encode('utf-8')
    backup=target.with_name(target.name+f'.pre_e6_taxonomy_{digest[:12]}')
    if backup.exists():
        if hashlib.sha256(backup.read_bytes()).hexdigest()!=digest: raise ValueError(f'backup path already exists with different contents: {backup}')
    else:
        with backup.open('xb') as f: f.write(raw); f.flush(); os.fsync(f.fileno())
    fd,tmp=tempfile.mkstemp(prefix=target.name+'.',suffix='.maintenance.tmp',dir=str(target.parent))
    try:
        with os.fdopen(fd,'wb') as f: f.write(modified); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
    return {'source_sha256_before':digest,'source_sha256_after':hashlib.sha256(modified).hexdigest(),'backup_path':str(backup),'patched_path':str(target),'patch_marker':PATCH_MARKER}
