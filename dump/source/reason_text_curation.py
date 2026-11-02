from __future__ import annotations
import ast
import json
import re
from typing import Any

_SAFE_SUPERVISION_FIELDS={
    'phase','reason','seconds','elapsed','elapsed_seconds','duration_seconds','environment',
    'peak_tree_rss_kib','peak_tree_rss_bytes','peak_rss_kib','peak_rss_bytes',
    'exit_code','finished_at','started_at','observed_at','worker_finished_at',
    'source','source_id','source_key','source_path','source_sha256',
    'attempt','attempt_id','attempt_key','task_key','artifact_key',
    'source_identity','attempt_identity',
}
_PRIVATE_PROCESS_FIELDS={
    'pid','pgid','ppid','process_id','process_group_id','pid_start_time','process_start_ticks','start_ticks','worker_pid','controller_pid','owner_pid',
    'cmdline','command_line','argv','env','environ','environment_variables',
    'env_vars','stdout','stderr','stdout_tail','stderr_tail','process','process_receipt',
    'receipt','worker_inventory','verified_workers','workers','child_pids','tree_pids','request_path','result_path','worker_log_path','process_inventory',
}
_SUPERVISION_MARKER=re.compile(r'\bsupervision\s*=',re.I)

def _safe_supervision(value: Any):
    if not isinstance(value,dict): return value,False
    out={}; changed=False
    for key,item in value.items():
        normalized=str(key).strip().lower().replace('-','_')
        if normalized in {'phase_supervision','supervision'} and isinstance(item,dict):
            child,child_changed=_safe_supervision(item)
            out[key]=child;changed|=child_changed
        elif normalized in _PRIVATE_PROCESS_FIELDS or normalized not in _SAFE_SUPERVISION_FIELDS:
            changed=True
            continue
        elif normalized in {'source_identity','attempt_identity'} and isinstance(item,dict):
            child,child_changed=_safe_supervision(item)
            out[key]=child;changed|=child_changed
        else:
            out[key]=item
    return out,changed

def _remove_private_fields(value):
    if isinstance(value,dict):
        out={};changed=False
        for key,item in value.items():
            normalized=str(key).strip().lower().replace('-','_')
            if normalized in {'phase_supervision','supervision'} and isinstance(item,dict):
                clean,sub=_safe_supervision(item);out[key]=clean;changed|=sub
            elif normalized in _PRIVATE_PROCESS_FIELDS:
                changed=True;continue
            else:
                clean,sub=_remove_private_fields(item);out[key]=clean;changed|=sub
        return out,changed
    if isinstance(value,list):
        out=[];changed=False
        for item in value:
            clean,sub=_remove_private_fields(item);out.append(clean);changed|=sub
        return out,changed
    return value,False

def _sanitize_json_supervision(value):
    if isinstance(value,dict):
        out={};changed=False
        for key,item in value.items():
            if str(key).strip().lower().replace('-','_') in {'supervision','phase_supervision'} and isinstance(item,dict):
                safe,sub=_safe_supervision(item);out[key]=safe;changed|=sub
            else:
                clean,sub=_sanitize_json_supervision(item);out[key]=clean;changed|=sub
        return out,changed
    if isinstance(value,list):
        out=[];changed=False
        for item in value:
            clean,sub=_sanitize_json_supervision(item);out.append(clean);changed|=sub
        return out,changed
    return value,False

def sanitize_reason_text(value: Any) -> str | None:
    """Remove process receipts only from recognized embedded supervision dictionaries.

    Ordinary text is returned byte-for-byte. Scientific exception/category/message and
    traceback prefixes are preserved; supervision retains phase, timing, RSS, exit,
    reason, timestamps, and source/attempt identities.
    """
    if value is None:return None
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,sort_keys=True,default=str)
    try:
        parsed=json.loads(text)
    except Exception:
        parsed=None
    if isinstance(parsed,(dict,list)):
        if isinstance(parsed,dict) and 'phase' in parsed and any(k in parsed for k in ('seconds','elapsed_seconds','exit_code','peak_tree_rss_kib','peak_tree_rss_bytes')):
            clean,changed=_remove_private_fields(parsed)
        else:
            clean,changed=_sanitize_json_supervision(parsed)
        return json.dumps(clean,ensure_ascii=False,sort_keys=True,separators=(',',':')) if changed else text
    # Some older timeout/error receipts serialize the phase result directly after a label.
    # Sanitize only a parseable trailing dictionary that actually contains private process keys.
    labelled=re.match(r'^(.*?:\s*)(\{.*\})\s*$',text,re.DOTALL)
    if labelled:
        try: record=ast.literal_eval(labelled.group(2))
        except Exception: record=None
        if isinstance(record,dict):
            clean,changed=_remove_private_fields(record)
            if changed:
                return labelled.group(1)+json.dumps(clean,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    matches=list(_SUPERVISION_MARKER.finditer(text))
    if not matches:return text
    match=matches[-1]
    prefix=text[:match.start()]
    if prefix and not prefix.rstrip().endswith(';'):return text
    suffix=text[match.end():].strip()
    try:
        supervision=ast.literal_eval(suffix)
    except Exception:
        return text
    if not isinstance(supervision,dict):return text
    safe,changed=_safe_supervision(supervision)
    if not changed:return text
    marker=text[match.start():match.end()]
    clean_marker=re.sub(r'supervision\s*=', 'supervision=',marker,flags=re.I)
    return prefix+clean_marker+json.dumps(safe,ensure_ascii=False,sort_keys=True,separators=(',',':'))
