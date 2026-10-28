from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def load():
 p=ROOT/'source/reporting.py'
 spec=importlib.util.spec_from_file_location('staged_cutoff_reporting',p)
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
reporting=load()
GIB=1024**3
def fixture_runtime(tmp_path,phase='trial',cutoff=2,budget=5):
 runtime=tmp_path/'runtime'; key='e3/rep_9/fit/synthetic/random_forest/kde';art=runtime/'artifacts'/key
 ap=art/'attempts'/'engine-attempt-9';ap.mkdir(parents=True)
 (runtime/'manifests').mkdir(parents=True)
 (runtime/'manifests/E3_MANIFEST.json').write_text(json.dumps({'resource_policy':{'worker_memory_gib':10}}))
 task={'key':key,'kind':'fit','experiment':3,'rep':9,'method':'random_forest','route':'synthetic','generator':'kde','condition':'kde','seed':7,'optimizer_seed':8,'trials':budget,'train_key':'e3/rep_9/generate/kde','sample_count':400000,'artifact_dir':str(art),
  'status':'validated_terminal','outcome':'scientific_failure','reason':'worker process-tree memory policy exceeded','forced_reason':'worker process-tree memory policy exceeded','peak_tree_rss_bytes':11*GIB,'started_utc':'2026-10-25T10:00:00+00:00','finished_utc':'2026-10-25T10:45:00+00:00','observed_utc':'2026-10-25T10:45:00+00:00','attempts':[]}
 controller_attempt='controller-id-9';reqdir=runtime/'attempts'/key/controller_attempt;reqdir.mkdir(parents=True)
 reqpath=reqdir/'request.json';request={'attempt_id':controller_attempt,'task':{k:v for k,v in task.items() if k!='attempts'}}
 reqpath.write_text(json.dumps(request))
 task['attempts']=[{'attempt_id':controller_attempt,'request_path':str(reqpath),'started_utc':'2026-10-25T10:00:00+00:00'}]
 identity_task={k:v for k,v in task.items() if k not in ('status','outcome','reason','forced_reason','peak_tree_rss_bytes','started_utc','finished_utc','observed_utc','attempts')}
 (ap/'attempt.json').write_text(json.dumps({'attempt_id':'engine-attempt-9','started_at':'2026-10-25T10:00:00.100000+00:00','task':identity_task}))
 completed=list(range(cutoff)) if phase=='trial' else list(range(budget))
 trials=[{'number':i,'status':'success' if i%2 else 'scientific_failure','score':0.5 if i%2 else None,'params':{'trial':i}} for i in completed]
 (ap/'selection.json').write_text(json.dumps({'trials':trials}))
 states=completed if phase=='final_fit' else list(range(cutoff+1))
 for i in states:
  (ap/f'phase_trial_{i}.json').write_text(json.dumps({'task':identity_task,'params':{'trial':i},'phase':f'trial_{i}'}))
  state={'status':'finished','peak_tree_rss_kib':1000+i,'elapsed_seconds':50+i}
  if phase=='trial' and i==cutoff:state={'status':'running','peak_tree_rss_kib':10200000,'elapsed_seconds':321.25}
  (ap/f'phase_trial_{i}_state.json').write_text(json.dumps(state))
  if not (phase=='trial' and i==cutoff):(ap/f'phase_trial_{i}_result.json').write_text(json.dumps({'status':'success','seconds':45}))
 if phase=='final_fit':
  (ap/'phase_final_fit.json').write_text(json.dumps({'task':identity_task,'params':{'trial':'selected'},'phase':'final_fit'}))
  (ap/'phase_final_fit_state.json').write_text(json.dumps({'status':'running','peak_tree_rss_kib':9000000,'elapsed_seconds':222.5}))
 return runtime,task,ap
def test_actual_kde_rep2_dynamic_trial5_and_raw_hashes_unchanged():
 registry=json.loads((ROOT/'registry.json').read_text())
 task=next(t for t in registry['tasks'] if t.get('key')=='e3/rep_2/fit/synthetic/random_forest/kde')
 ap=Path(task['artifact_dir'])/'attempts'/'1792943753_04303faa'
 paths=[ap/'selection.json',ap/'attempt.json',ap/'phase_trial_5.json',ap/'phase_trial_5_state.json']
 before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 row=reporting._terminal_worker_rss_cutoff(ROOT,task)
 after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
 assert before==after
 assert row is not None and row['cutoff_phase']=='trial' and row['aborted_trial_index']==5
 assert row['completed_trial_count']==5 and row['actually_started_trial_count']==6
 assert row['unattempted_nominal_slot_indices']==[6,7,8,9]
 assert row['aborted_trial_last_observed_elapsed_seconds']==pytest.approx(408.50018761097454)
 assert row['source_file_hashes_unchanged'] is True
def test_known_gmm_rep2_trial8_and_unattempted_slot9_preserved():
 registry=json.loads((ROOT/'registry.json').read_text())
 task=next(t for t in registry['tasks'] if t.get('key')=='e3/rep_2/fit/synthetic/random_forest/gmm')
 row=reporting._terminal_worker_rss_cutoff(ROOT,task)
 assert row is not None and row['aborted_trial_index']==8
 assert row['completed_trial_count']==8 and row['actually_started_trial_count']==9
 assert row['unattempted_nominal_slot_indices']==[9]
def test_dynamic_trial_cutoff_and_all_remaining_budget_slots(tmp_path):
 runtime,task,ap=fixture_runtime(tmp_path,'trial',2,5);row=reporting._terminal_worker_rss_cutoff(runtime,task)
 assert row['aborted_trial_index']==2 and row['completed_trial_count']==2 and row['actually_started_trial_count']==3
 assert row['unattempted_nominal_slot_indices']==[3,4]
 assert json.loads(row['aborted_trial_params'])=={'trial':2}
def test_final_fit_cutoff_has_no_fabricated_aborted_trial(tmp_path):
 runtime,task,ap=fixture_runtime(tmp_path,'final_fit',None,5);row=reporting._terminal_worker_rss_cutoff(runtime,task)
 assert row is not None and row['cutoff_phase']=='final_fit'
 assert row['aborted_trial_index'] is None and row['completed_trial_count']==5
 assert row['actually_started_trial_count']==5 and row['unattempted_nominal_slot_indices']==[]
 rows=reporting._model_selection_rows(runtime,[task])
 phase_rows=[r for r in rows if r.get('cutoff_record_type')=='actual_final_fit_phase']
 assert len(phase_rows)==1 and phase_rows[0]['trial_index'] is None and phase_rows[0]['phase']=='final_fit'
def test_scientific_phase_timeout_is_not_outer_worker_cutoff(tmp_path):
 runtime,task,ap=fixture_runtime(tmp_path,'trial',2,5)
 task['reason']="phase_timeout: {'phase': 'trial_2', 'reason': 'timeout'}";task['forced_reason']=None
 assert reporting._terminal_worker_rss_cutoff(runtime,task) is None
