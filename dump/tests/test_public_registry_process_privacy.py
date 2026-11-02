from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'source'))
spec = importlib.util.spec_from_file_location('candidate_finalize_project', R / 'source/finalize_project.py')
finalizer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = finalizer
spec.loader.exec_module(finalizer)

def all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower().replace('-', '_')
            yield from all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_keys(child)

def test_public_registry_recursively_removes_private_process_identity(tmp_path):
    raw = {'tasks': {'case-1': {'key': 'case-1', 'status': 'validated_terminal', 'outcome': 'successful',
        'balanced_accuracy': 0.8125, 'attempt_id': 'attempt-safe-id',
        'resource_profile': {'peak_tree_rss_bytes': 123456, 'threads': 1},
        'process': {'pgid': 101, 'process_start_ticks': 202, 'process_group_id': 303,
            'start_ticks': 404, 'worker_pid': 505, 'pid': 606,
            'process_receipt': {'argv': ['secret command'], 'receipt': 'private'},
            'safe': {'phase': 'test', 'seconds': 12.5}},
        'attempts': [{'attempt_id': 'attempt-safe-id', 'started_utc': '2026-10-28T00:00:00Z',
            'status': 'successful', 'peak_tree_rss_bytes': 777, 'pgid': 707, 'process_start_ticks': 808}]}}}
    (tmp_path / 'registry.json').write_text(json.dumps(raw), encoding='utf-8')
    parsed = json.loads(finalizer.public_registry(tmp_path))
    keys = set(all_keys(parsed))
    forbidden = {'pgid', 'process_start_ticks', 'process_group_id', 'start_ticks', 'worker_pid', 'pid',
                 'process_receipt', 'argv', 'receipt'}
    assert not (keys & forbidden)
    task = parsed['tasks']['case-1']
    assert task['balanced_accuracy'] == 0.8125 and task['outcome'] == 'successful'
    assert task['resource_profile']['peak_tree_rss_bytes'] == 123456
    assert task['attempts'][0]['peak_tree_rss_bytes'] == 777
    assert task['attempts'][0]['attempt_id'] == 'attempt-safe-id'

def test_public_registry_sanitizes_embedded_reason_process_receipts(tmp_path):
    raw = {'tasks': {'case-2': {'key': 'case-2', 'outcome': 'scientific_failure',
        'reason': "phase_timeout: {'phase':'test','seconds':600,'pgid':901,'process_start_ticks':902,'reason':'timeout'}",
        'attempts': [{'attempt_id': 'attempt-2', 'reason':
            "phase_timeout: {'phase':'fit','seconds':9.5,'pgid':903,'process_start_ticks':904,'reason':'timeout'}"}]}}}
    (tmp_path / 'registry.json').write_text(json.dumps(raw), encoding='utf-8')
    parsed = json.loads(finalizer.public_registry(tmp_path))
    reasons = [parsed['tasks']['case-2']['reason'], parsed['tasks']['case-2']['attempts'][0]['reason']]
    joined = ' '.join(reasons)
    assert 'pgid' not in joined and 'process_start_ticks' not in joined
    assert all(x not in joined for x in ('901', '902', '903', '904'))
    assert 'phase' in joined and 'seconds' in joined and 'timeout' in joined

def test_public_registry_removes_hold_tokens_but_preserves_scientific_identity(tmp_path):
    raw = {'tasks': {'case-3': {'key': 'case-3', 'attempt_id': 'attempt-3',
        'hold_nonce': 'opaque-private', 'nonce': 'opaque-private-2', 'accuracy': 0.75, 'status': 'successful'}}}
    (tmp_path / 'registry.json').write_text(json.dumps(raw), encoding='utf-8')
    parsed = json.loads(finalizer.public_registry(tmp_path))
    task = parsed['tasks']['case-3']
    assert 'hold_nonce' not in task and 'nonce' not in task
    assert task['attempt_id'] == 'attempt-3' and task['accuracy'] == 0.75
