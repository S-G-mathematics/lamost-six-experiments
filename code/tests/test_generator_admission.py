import importlib.util
import json
import shutil
import os
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
BASE=Path(r'/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025')
ST=BASE
SRC=ST/'source'

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
c=load('staged_controller',Path(r'/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025/staging/controller_admission_hold_20261026/controller.py'))
e=load('admission_evidence',SRC/'admission_evidence.py')
PLAN=json.loads((BASE/'manifests/tasks.json').read_text())['tasks']
REG={x['key']:x for x in json.loads((BASE/'registry.json').read_text())['tasks']}

def frozen(key): return next(x for x in PLAN if x['key']==key)
class EvidenceAdmissionTests(unittest.TestCase):
 def test_actual_e5_generator_cell_uses_validated_corruption_and_clean_model_evidence(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05'); t=dict(d,status='waiting_for_dependency',attempts=[])
  c.R=BASE; c.DEFINITIONS={x['key']:x for x in PLAN}
  ok,evidence=e.eligible_4gib(t,d,BASE)
  self.assertTrue(ok); self.assertEqual(evidence['train_key'],d['train_key'])
  self.assertEqual(evidence['dependency_fit_key'],d['dependencies'][1])
  # eligible_4gib remains a valid legacy evidence gate; the current higher-priority 2 GiB fit profile supplies the reservation.
  self.assertEqual(c.worker_reservation_bytes(t),2*c.GIB)
 def test_actual_frozen_e4_eval_without_train_key_uses_published_fit_metadata(self):
  c.R=BASE; c.DEFINITIONS={x['key']:x for x in PLAN}
  choices=[]
  for d in PLAN:
   if d.get('experiment')==4 and d.get('kind')=='eval' and d.get('method')=='random_forest' and d.get('route')=='direct':
    t=dict(d,status='planned',attempts=[])
    ok,proof=e.eligible_4gib(t,d,BASE)
    if ok: choices.append((t,d,proof))
  self.assertTrue(choices,'no E4 RF direct task had matching validated artifacts')
  t,d,proof=choices[0]
  self.assertNotIn('train_key',d); self.assertEqual(proof['train_key'],f"e4/rep_{d['rep']}/cohort/{d['condition']}")
  self.assertEqual(c.worker_reservation_bytes(t),4*c.GIB)
 def test_e4_generator_frozen_task_definition_and_actual_cohort(self):
  d=frozen('e4/rep_1/fit/direct/gmm/A_half')
  t=dict(d,status='waiting_for_dependency',attempts=[])
  ok,proof=e.eligible_4gib(t,d,BASE)
  self.assertTrue(ok); self.assertEqual(proof['npz_header_shapes']['X'],[80000,6])
 def test_wrong_or_missing_header_metadata_fail_closed(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05')
  src=BASE/'artifacts'/d['train_key']
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); dst=root/'artifacts'/d['train_key']; dst.mkdir(parents=True)
   for name in ('metadata.json','validation.json'): shutil.copy2(src/name,dst/name)
   import numpy as np
   np.savez(dst/'data.npz',X=np.zeros((79999,6),dtype='f4'),y=np.zeros(80000,dtype='i8'),ids=np.zeros(80000,dtype='i8'))
   self.assertFalse(e._valid_cohort(root,d['train_key'],5,1,d['condition']))
   (dst/'metadata.json').unlink()
   self.assertFalse(e._valid_cohort(root,d['train_key'],5,1,d['condition']))
 def test_wrong_or_missing_rf_publication_fails_closed_through_public_gate(self):
  choices=[]
  for d in PLAN:
   if d.get('experiment')==4 and d.get('kind')=='eval' and d.get('method')=='random_forest' and d.get('route')=='direct':
    t=dict(d,status='planned',attempts=[])
    if e.eligible_4gib(t,d,BASE)[0]: choices.append((t,d))
  self.assertTrue(choices)
  t,d=choices[0]; fit=d['fit_key']; train=f"e4/rep_{d['rep']}/cohort/{d['condition']}"
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   for key,names in ((fit,('fit_result.json','fit_publication.json','validation.json','pipeline.joblib')),(train,('metadata.json','validation.json','data.npz'))):
    src=BASE/'artifacts'/key; dst=root/'artifacts'/key; dst.mkdir(parents=True)
    for name in names: shutil.copy2(src/name,dst/name)
   pub=root/'artifacts'/fit/'fit_publication.json'; x=json.loads(pub.read_text());x['published_path']=str((root/'artifacts'/fit/'pipeline.joblib').resolve());pub.write_text(json.dumps(x))
   self.assertTrue(e.eligible_4gib(t,d,root)[0])
   x=json.loads(pub.read_text());x['pipeline_sha256']='0'*64;pub.write_text(json.dumps(x))
   self.assertFalse(e.eligible_4gib(t,d,root)[0])
   pub.unlink()
   self.assertFalse(e.eligible_4gib(t,d,root)[0])
 def test_malformed_cohort_metadata_fails_closed(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05'); t=dict(d,status='waiting_for_dependency',attempts=[])
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); src=BASE/'artifacts'/d['train_key']; dst=root/'artifacts'/d['train_key']; dst.mkdir(parents=True)
   for name in ('metadata.json','validation.json','data.npz'): shutil.copy2(src/name,dst/name)
   meta=json.loads((dst/'metadata.json').read_text());meta['rep']=['bad'];(dst/'metadata.json').write_text(json.dumps(meta))
   self.assertEqual(e.eligible_4gib(t,d,root),(False,None))
 def test_wrong_dependency_or_condition_never_gets_exception(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05'); t=dict(REG[d['key']])
  bad=dict(d,dependencies=['wrong',*d['dependencies'][1:]])
  self.assertFalse(e.eligible_4gib(t,bad,BASE)[0])
  bad=dict(d,condition='feature_noise_25')
  self.assertFalse(e.eligible_4gib(t,bad,BASE)[0])
  # Preserve the actual persisted 2 GiB attempt reservation on this registry task.
  self.assertEqual(c.worker_reservation_bytes(dict(t,attempts=[{'attempt_id':'old'}])),t['admission_reservation_bytes'])
  # An attempted task without persisted profile evidence remains at the default 10 GiB.
  unrecorded=dict(t,attempts=[{'attempt_id':'old'}],admission_reservation_bytes=None,admission_profile_id=None,admission_profile_evidence=None)
  self.assertEqual(c.worker_reservation_bytes(unrecorded),10*c.GIB)
 def _admit(self,task,definition,root):
  proc=Mock(pid=424242)
  with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{definition['key']:definition}),patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'start_ticks',return_value='77'),patch.object(c,'put'),patch.object(c,'event'):
   c.admit(None,task)
  return task
 def test_admit_writes_evidence_outside_scientific_request_and_resume_preserves_it(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05'); key=d['key']
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); task=dict(d,status='planned',attempts=[])
   evidence={'profile_id':e.PROFILE_ID,'reason':'fixture evidence','train_key':d['train_key']}
   with patch.object(c,'worker_reservation_bytes',return_value=4*c.GIB),patch.object(c.admission_evidence,'eligible_4gib',return_value=(True,evidence)):
    task=self._admit(task,d,root)
   req=json.loads(Path(task['request_path']).read_text())
   self.assertEqual(req['task'],dict(d,artifact_dir=str(root/'artifacts'/key)))
   self.assertEqual(task['attempts'][-1]['resource_profile']['admission_profile_evidence'],evidence)
   prior=task['attempts'][-1].copy(); resume=dict(d,status='planned',attempts=[prior],admission_reservation_bytes=4*c.GIB,admission_profile_id=e.PROFILE_ID,admission_profile_evidence=evidence)
   with patch.object(c,'worker_reservation_bytes',return_value=4*c.GIB):
    resume=self._admit(resume,d,root)
   self.assertEqual(resume['attempts'][0],prior)
   self.assertEqual(resume['attempts'][-1]['resource_profile']['admission_profile_evidence'],evidence)
 def test_promoted_resume_uses_default_profile_and_keeps_old_attempt(self):
  d=frozen('e5/rep_1/fit/direct/gmm/feature_noise_05')
  with tempfile.TemporaryDirectory() as td:
   old={'attempt_id':'prior','resource_profile':{'admission_profile_id':e.PROFILE_ID,'admission_reservation_bytes':4*c.GIB,'admission_profile_evidence':{'reason':'prior'}}}
   t=dict(d,status='planned',attempts=[old],adaptive_promoted_heavy=True,admission_reservation_bytes=4*c.GIB,admission_profile_id=e.PROFILE_ID,admission_profile_evidence={'reason':'prior'})
   t=self._admit(t,d,Path(td))
   self.assertEqual(t['attempts'][0],old)
   self.assertEqual(t['attempts'][-1]['resource_profile']['admission_reservation_bytes'],10*c.GIB)
   self.assertEqual(t['attempts'][-1]['resource_profile']['admission_profile_id'],'adaptive-concurrency-20261025-v1.1-default')
   self.assertNotIn('admission_profile_evidence',t['attempts'][-1]['resource_profile'])
 def test_pipeline_hashing_streams_and_memoizes_unchanged_file(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'pipeline.joblib';path.write_bytes(b'x'*(3*1024*1024+11))
   original_open=Path.open; chunks=[]
   class Reader:
    def __init__(self,raw): self.raw=raw
    def __enter__(self): return self
    def __exit__(self,*args): return self.raw.__exit__(*args)
    def read(self,n=-1):
     self_outer=chunks
     if n < 0 or n > 1024*1024: raise AssertionError('hash attempted an unbounded read')
     self_outer.append(n);return self.raw.read(n)
   def tracked_open(target,*args,**kwargs):
    raw=original_open(target,*args,**kwargs)
    return Reader(raw) if Path(target).resolve()==path.resolve() else raw
   e._SHA_CACHE.clear()
   with patch.object(Path,'open',tracked_open),patch.object(Path,'read_bytes',side_effect=AssertionError('read_bytes must not be used')):
    first=e._sha256_cached(path)
    self.assertEqual(first,hashlib.sha256(b'x'*(3*1024*1024+11)).hexdigest())
    self.assertGreaterEqual(len(chunks),4)
    chunks.clear()
    self.assertEqual(e._sha256_cached(path),first)
    self.assertEqual(chunks,[],'unchanged identity should use memoized digest')
 def test_same_size_pipeline_mutation_invalidates_hash_cache_and_fit_proof(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);key='e4/rep_1/fit/direct/random_forest/A_half';p=root/'artifacts'/key;p.mkdir(parents=True)
   payload=b'pipeline-v1';pipeline=hashlib.sha256(payload).hexdigest();(p/'pipeline.joblib').write_bytes(payload)
   task={'key':key,'experiment':4,'rep':1,'method':'random_forest','train_key':'e4/rep_1/cohort/A_half'}
   result={'status':'success','training_rows':80000,'class_counts':[1,1,1,1,1,1,79994],'pipeline_sha256':pipeline}
   full={'status':'successful','attempt_id':'attempt-a','task_sha256':'a'*64,'task':task,'result':result}
   (p/'fit_result.json').write_text(json.dumps(full))
   pub={'stage':'validated_publication','attempt_id':'attempt-a','task_sha256':'a'*64,'pipeline_sha256':pipeline,'published_path':str((p/'pipeline.joblib').resolve())}
   (p/'fit_publication.json').write_text(json.dumps(pub))
   val={'status':'validated','task_key':key,'files':{'pipeline.joblib':pipeline}}
   (p/'validation.json').write_text(json.dumps(val))
   e._SHA_CACHE.clear()
   self.assertTrue(e._valid_published_fit(root,key,4,1,'random_forest',task['train_key'],require_publication=True))
   old_identity=e._SHA_CACHE[str((p/'pipeline.joblib').resolve())][0]
   path=p/'pipeline.joblib';path.write_bytes(b'pipeline-v2')
   st=path.stat();os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns+1_000_000_000))
   new_hash=e._sha256_cached(path);new_identity=e._SHA_CACHE[str(path.resolve())][0]
   self.assertNotEqual(old_identity,new_identity)
   self.assertNotEqual(new_hash,pipeline)
   self.assertFalse(e._valid_published_fit(root,key,4,1,'random_forest',task['train_key'],require_publication=True))
if __name__=='__main__': unittest.main()
