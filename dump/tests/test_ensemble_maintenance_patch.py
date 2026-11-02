from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
import ensemble_maintenance_patch as patch

def _timeout(reason='timeout'):
    receipt={'seconds':601.2 if reason=='timeout' else 30.1,'peak_tree_rss_kib':10*1024*1024+4096 if reason=='rss_limit' else 321000,'exit_code':-15,'reason':reason,'result':{'status':'error','error':'worker terminated'}}
    return RuntimeError(f"prediction_{reason}: {receipt!r}")

def test_timeout_becomes_scientific_failure_and_pair_mode_does_not_reinfer(tmp_path):
    runtime=tmp_path/'runtime'; shared=runtime/'cache/e6_posteriors/rep_1/fingerprint-abc'; shared.mkdir(parents=True)
    fingerprint={'fit_hash':'fit0','test_ids_hash':'test0'}; calls=[]
    task_equal={'key':'e6/rep_1/ensemble/equal','rep':1,'mode':'equal'}
    def timeout_runner(): calls.append('ran'); raise _timeout('timeout')
    def run_equal(_task, _runtime):
        return patch.run_phase_with_terminal_failure_cache(stage='test',shared_dir=shared,fingerprint=fingerprint,mode='equal',task_key=task_equal['key'],runner=timeout_runner)
    first=patch.execute_with_terminal_classification(run_equal,task_equal,runtime)
    assert first['status']=='scientific_failure'
    assert first['evaluation'] is None
    assert 'balanced_accuracy' not in first
    assert first['phase_evidence']['failure_code']=='prediction_timeout'
    assert first['phase_evidence']['stage']=='test'
    assert first['phase_evidence']['peak_tree_rss_kib']==321000
    marker=Path(first['phase_evidence_path'])
    assert marker.is_file()
    assert json.loads(marker.read_text())['valid_evaluation_metrics_written'] is False
    assert not (runtime/'artifacts/e6/rep_1/ensemble/equal/test_outcomes.npz').exists()

    task_learned={'key':'e6/rep_1/ensemble/learned','rep':1,'mode':'learned'}
    def must_not_run(): calls.append('reran'); raise AssertionError('posterior phase must remain terminal under this fingerprint')
    def run_learned(_task, _runtime):
        return patch.run_phase_with_terminal_failure_cache(stage='test',shared_dir=shared,fingerprint=fingerprint,mode='learned',task_key=task_learned['key'],runner=must_not_run)
    second=patch.execute_with_terminal_classification(run_learned,task_learned,runtime)
    assert second['status']=='unavailable_dependency'
    assert second['evaluation'] is None and 'balanced_accuracy' not in second
    assert second['source_task_key']==task_equal['key']
    assert second['phase_evidence']['failure_code']=='prediction_timeout'
    assert second['phase_evidence']['dependency_failure_marker']==json.loads(marker.read_text())['phase_failure_marker']
    assert calls==['ran']
    assert not (runtime/'artifacts/e6/rep_1/ensemble/learned/test_outcomes.npz').exists()

    # A watchdog restart of the same logical task reports the same scientific
    # terminal outcome and also does not re-run the phase.
    repeated=patch.execute_with_terminal_classification(run_equal,task_equal,runtime)
    assert repeated['status']=='scientific_failure'
    assert calls==['ran']

def test_rss_limit_is_scientific_but_unstructured_failures_stay_unclassified(tmp_path):
    fp={'role':'r1'}
    rss=patch.classify_prediction_phase_exception(_timeout('rss_limit'),'cal',fp,'learned','e6/rep_1/learned')
    assert rss and rss['status']=='scientific_failure' and rss['failure_code']=='prediction_rss_limit'
    assert patch.classify_prediction_phase_exception(RuntimeError('prediction_timeout: no receipt'),'test',fp,'equal','k') is None
    assert patch.classify_prediction_phase_exception(RuntimeError('unexpected model bug'),'test',fp,'equal','k') is None
    assert patch.classify_prediction_phase_exception(TimeoutError('generic timeout'),'test',fp,'equal','k') is None

def test_unknown_errors_propagate_without_marker_or_false_metrics(tmp_path):
    shared=tmp_path/'shared'; shared.mkdir(); fp={'same':'fingerprint'}; runtime=tmp_path/'runtime'; task={'key':'e6/rep_1/equal','rep':1,'mode':'equal'}
    def buggy(): raise RuntimeError('unexpected posterior shape defect')
    with pytest.raises(RuntimeError,match='unexpected posterior shape defect'):
        patch.execute_with_terminal_classification(lambda _task, _runtime:patch.run_phase_with_terminal_failure_cache(stage='test',shared_dir=shared,fingerprint=fp,mode='equal',task_key=task['key'],runner=buggy),task,runtime)
    assert not list(shared.glob('*.scientific_failure.json'))
    assert not (runtime/'artifacts/e6/rep_1/equal/E6_PHASE_TERMINAL.json').exists()

def test_prepared_patch_is_syntax_valid_and_does_not_mutate_frozen_source():
    path=ROOT/'source/ensemble.py'; before=path.read_bytes(); digest=hashlib.sha256(before).hexdigest()
    if digest==patch.ACTIVE_SOURCE_SHA256:
        changed=patch.prepare_patched_source(before.decode('utf-8-sig'))
    else:
        backups=[q for q in path.parent.glob('ensemble.py.pre_e6_taxonomy_*') if hashlib.sha256(q.read_bytes()).hexdigest()==patch.ACTIVE_SOURCE_SHA256]
        assert len(backups)==1
        changed=patch.prepare_patched_source(backups[0].read_text(encoding='utf-8-sig'))
        # The current live source additionally contains the separately reviewed
        # member-reference gate; rebuilding the earlier taxonomy patch from its
        # preserved base should still remain syntactically valid.
        assert 'def _member_evaluation_preflight' in before.decode('utf-8-sig')
    compile(changed,str(path),'exec')
    assert patch.PATCH_MARKER in changed
    assert '_execute_e6_before_phase_taxonomy' in changed
    assert 'E6PhaseFailure' in changed and 'run_phase_with_terminal_failure_cache' in changed
    assert path.read_bytes()==before
