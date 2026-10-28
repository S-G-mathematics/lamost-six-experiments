from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source'
sys.path.insert(0,str(SRC))
def load_source_module(name):
    spec=importlib.util.spec_from_file_location('e6gate_'+name,SRC/(name+'.py'))
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
controller=load_source_module('controller')
import ensemble

METHODS=('gmm','copula','arf','kde','chow_liu')
def task_record():
    return {'key':'e6/rep_1/ensemble/equal','experiment':6,'kind':'ensemble','status':'planned','outcome':None,
      'scientific_case':True,'dependencies':[f'e3/rep_1/fit/{m}' for m in METHODS],
      'member_evaluations':{m:f'e3/rep_1/eval/direct/{m}' for m in METHODS}}
def task_states(task, *, pending=None, failed=None):
    states={}
    for key in controller.effective_dependencies(task):
        alias=key in task.get('member_evaluations',{}).values()
        common={'key':key,'experiment':6,'kind':'alias' if alias else 'fit','scientific_case':True}
        if key==pending:states[key]={**common,'status':'waiting_for_dependency','outcome':None}
        elif key==failed:states[key]={**common,'status':'validated_terminal','outcome':'scientific_failure'}
        else:states[key]={**common,'status':'validated_terminal','outcome':'successful'}
    return states
def observations(states,task):
    return {key:{'status':states[key]['status'],'outcome':states[key].get('outcome'),'reason':'fixture failure' if states[key].get('outcome')!='successful' else None}
      for key in task['member_evaluations'].values()}

def test_controller_requires_all_declared_e6_member_references(tmp_path):
    c=controller;c.R=tmp_path
    db=c.connect();task=task_record();states=task_states(task)
    for value in states.values():c.put(db,value)
    c.put(db,task);live={**states,task['key']:task}
    assert set(c.effective_dependencies(task))==set(task['dependencies'])|set(task['member_evaluations'].values())
    assert c.ready_tasks(db,live)==[task]
    assert task['effective_dependencies']==c.effective_dependencies(task)
    db.close()

@pytest.mark.parametrize('case',('pending','failed'))
def test_controller_does_not_launch_until_member_reference_terminal_success(tmp_path,case):
    c=controller;c.R=tmp_path
    db=c.connect();task=task_record();ref=next(iter(task['member_evaluations'].values()))
    states=task_states(task,pending=ref if case=='pending' else None,failed=ref if case=='failed' else None)
    for value in states.values():c.put(db,value)
    c.put(db,task);live={**states,task['key']:task}
    ready=c.ready_tasks(db,live)
    assert task not in ready
    if case=='pending':
        assert task['status']=='waiting_for_dependency'
        assert live[ref]['status']=='waiting_for_dependency'
    else:
        assert task['status']=='validated_terminal' and task['outcome']=='unavailable_dependency'
        assert ref in task['reason'] and 'scientific_failure' in task['reason']
    db.close()

@pytest.mark.parametrize('experiment,kind',((3,'eval'),(4,'fit'),(5,'fit')))
def test_non_e6_dependency_semantics_unchanged(experiment,kind,tmp_path):
    c=controller;c.R=tmp_path
    db=c.connect();base={'key':'base','status':'validated_terminal','outcome':'successful'}
    t={'key':f'e{experiment}/task','experiment':experiment,'kind':kind,'status':'planned','dependencies':['base'],'member_evaluations':{'m':'unrelated/member'}}
    c.put(db,base);c.put(db,t)
    assert c.effective_dependencies(t)==['base']
    assert c.ready_tasks(db,{'base':base,t['key']:t})==[t]
    db.close()

def test_ensemble_preflight_blocks_failed_or_pending_member_before_model_access(monkeypatch,tmp_path):
    task=task_record();states=task_states(task)
    task['members']={m:f'fit/{m}' for m in METHODS};task['member_evaluation_dependency_observations']=observations(states,task)
    assert ensemble._member_evaluation_preflight(task)['state']=='ready'
    touched=[]
    monkeypatch.setattr(ensemble,'_project',lambda runtime:touched.append('project import'))
    failed_key=task['member_evaluations']['kde']
    bad={**task,'member_evaluation_dependency_observations':dict(task['member_evaluation_dependency_observations'])}
    bad['member_evaluation_dependency_observations'][failed_key]={'status':'validated_terminal','outcome':'scientific_failure','reason':'fixed evaluation timeout'}
    result=ensemble._execute_e6_before_phase_taxonomy(bad,tmp_path)
    assert result['status']=='unavailable_dependency'
    assert result['posterior_phases_started'] is False and result['evaluation'] is None and touched==[]
    pending={**task,'member_evaluation_dependency_observations':dict(task['member_evaluation_dependency_observations'])}
    pending['member_evaluation_dependency_observations'][failed_key]={'status':'waiting_for_dependency','outcome':None}
    result=ensemble._execute_e6_before_phase_taxonomy(pending,tmp_path)
    assert result['status']=='operationally_interrupted' and result['preflight_not_ready']
    assert result['posterior_phases_started'] is False and touched==[]

def test_applied_freeze_amendment_and_plan_identity():
    freeze=json.loads((ROOT/'manifests/freeze.json').read_text())
    plan=(ROOT/'manifests/tasks.json').read_bytes()
    assert hashlib.sha256(plan).hexdigest()==freeze['plan_sha256']
    assert freeze['frozen_utc']=='2026-10-25T04:46:31.018995+00:00'
    for name in ('controller.py','ensemble.py'):
        actual=hashlib.sha256((SRC/name).read_bytes()).hexdigest()
        assert freeze['source_sha256'][name]==actual
    amendments=json.loads((ROOT/'manifests/plan_amendments.json').read_text())['amendments']
    amendment=next(a for a in amendments if a.get('amendment_id')=='e6_declared_member_gate_20261025')
    assert amendment['plan_file_sha256_before_after']==hashlib.sha256(plan).hexdigest()
    assert amendment['source_after_sha256']=={n:freeze['source_sha256'][n] for n in ('controller.py','ensemble.py')}
    assert amendment['E6_prior_ensemble_attempts']==0

def test_terminal_e6_phase_cache_still_prevents_duplicate_same_policy_attempt(tmp_path):
    from ensemble_maintenance_patch import E6CachedPhaseFailure,run_phase_with_terminal_failure_cache
    import ensemble_maintenance_patch as patch
    fp={'roles':'fixture-only'};marker=tmp_path/'test.scientific_failure.json'
    patch._json_atomic(marker,{'status':'scientific_failure','failure_code':'prediction_timeout','stage':'test','source_task_key':'e6/equal','fingerprint':fp,
      'fingerprint_sha256':hashlib.sha256(json.dumps(fp,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    calls=[]
    with pytest.raises(E6CachedPhaseFailure):
        run_phase_with_terminal_failure_cache(stage='test',shared_dir=tmp_path,fingerprint=fp,mode='learned',task_key='e6/learned',runner=lambda:calls.append(True))
    assert calls==[]
