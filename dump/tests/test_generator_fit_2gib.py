import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
BASE=Path(__file__).resolve().parents[1]
ST=BASE
SRC=ST/'source'

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
c=load('staged_controller',SRC/'controller.py');e=load('staged_evidence',SRC/'admission_evidence.py')
PLAN=json.loads((BASE/'manifests/tasks.json').read_text())['tasks'];PLAN_BY_KEY={x['key']:x for x in PLAN}
def d(key):return PLAN_BY_KEY[key]
def planned(definition,status='waiting_for_dependency'):
 return dict(definition,status=status,attempts=[])
class NarrowTwoGiBAdmissionTests(unittest.TestCase):
 def setUp(self):
  c.R=BASE;c.DEFINITIONS=PLAN_BY_KEY
 def test_actual_e5_fixed_generator_definition_has_two_gib_profile(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05');t=planned(definition)
  ok,proof=e.eligible_2gib_generator_fit(t,definition,BASE)
  self.assertTrue(ok);self.assertEqual(proof['profile_id'],e.GENERATOR_2G_PROFILE_ID)
  self.assertEqual(proof['reservation_gib'],2);self.assertEqual(proof['train_key'],definition['train_key'])
  self.assertEqual(c.worker_reservation_bytes(t),2*c.GIB)
 def test_actual_e4_fit_metadata_and_exact_search_policy(self):
  for method in ('gmm','copula','chow_liu'):
   definition=d(f'e4/rep_1/fit/direct/{method}/A_half');t=planned(definition)
   ok,proof=e.eligible_2gib_generator_fit(t,definition,BASE)
   self.assertTrue(ok,(method,proof));self.assertEqual(proof['reservation_gib'],2)
   self.assertEqual(definition['trials'],10);self.assertEqual(definition['selection_mode'],'tune')
 def test_e5_requires_exact_clean_selection_and_zero_trials(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05');t=planned(definition)
  for changes in ({'selection_key':'e3/rep_2/fit/gmm'},{'selection_mode':'tune'},{'trials':1},{'selection_policy':'other'}):
   altered=dict(definition,**changes)
   self.assertFalse(e.eligible_2gib_generator_fit(t,altered,BASE)[0],changes)
  base=json.loads((BASE/'artifacts/e3/rep_1/fit/gmm/selection.json').read_text())
  self.assertIsInstance(base['selected_params'],dict)
 def test_scope_excludes_attempted_wrong_method_route_and_non_fit_tasks(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05')
  self.assertFalse(e.eligible_2gib_generator_fit(dict(planned(definition),attempts=[{'attempt_id':'prior'}]),definition,BASE)[0])
  self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),dict(definition,route='synthetic'),BASE)[0])
  self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),dict(definition,method='arf'),BASE)[0])
  self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),dict(definition,kind='generate'),BASE)[0])
  self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),dict(definition,experiment=3),BASE)[0])
 def test_wrong_or_missing_cohort_proof_fails_closed(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05');source=BASE/'artifacts'/definition['train_key']
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);dst=root/'artifacts'/definition['train_key'];dst.mkdir(parents=True)
   for name in ('metadata.json','validation.json'):shutil.copy2(source/name,dst/name)
   import numpy as np
   np.savez(dst/'data.npz',X=np.zeros((80000,5),dtype='f4'),y=np.zeros(80000,dtype='i8'),ids=np.zeros(80000,dtype='i8'))
   self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),definition,root)[0])
   (dst/'metadata.json').unlink()
   self.assertFalse(e.eligible_2gib_generator_fit(planned(definition),definition,root)[0])
 def test_e4_random_forest_profiles_remain_four_gib(self):
  rf=d('e4/rep_1/fit/direct/random_forest/A_half');self.assertEqual(c.worker_reservation_bytes(planned(rf)),4*c.GIB)
  candidates=[x for x in PLAN if x.get('experiment')==4 and x.get('kind')=='eval' and x.get('method')=='random_forest' and x.get('route')=='direct']
  valid=None
  for x in candidates:
   t=planned(x,'planned')
   if e.eligible_4gib(t,x,BASE)[0]:valid=(t,x);break
  self.assertIsNotNone(valid)
  self.assertEqual(c.worker_reservation_bytes(valid[0]),4*c.GIB)
 def test_other_heavy_methods_keep_default_ten_gib(self):
  for key in ('e5/rep_1/fit/direct/arf/feature_noise_05','e5/rep_1/fit/direct/random_forest/feature_noise_05'):
   self.assertEqual(c.worker_reservation_bytes(planned(d(key))),10*c.GIB)
  # E4 treatment RF and synthetic RF are explicitly outside this profile.
  treatment=next(x for x in PLAN if x.get('experiment')==4 and x.get('kind')=='fit' and x.get('method')=='random_forest' and x.get('route')=='treatment')
  self.assertEqual(c.worker_reservation_bytes(planned(treatment)),10*c.GIB)
 def test_admit_persists_exact_two_gib_profile_without_request_mutation(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05');key=definition['key'];proof={'profile_id':e.GENERATOR_2G_PROFILE_ID,'reservation_gib':2,'reason':'fixture verified'};task=planned(definition,'planned');proc=Mock(pid=424242)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td)
   with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{key:definition}),patch.object(c,'worker_reservation_bytes',return_value=2*c.GIB),patch.object(c.admission_evidence,'eligible_2gib_generator_fit',return_value=(True,proof)),patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'start_ticks',return_value='77'),patch.object(c,'put'),patch.object(c,'event'):
    c.admit(None,task)
   self.assertEqual(task['admission_reservation_bytes'],2*c.GIB)
   self.assertEqual(task['admission_profile_id'],e.GENERATOR_2G_PROFILE_ID)
   self.assertEqual(task['admission_resource_policy']['admission_reservation_bytes'],2*c.GIB)
   self.assertEqual(task['admission_resource_policy']['admission_profile_id'],e.GENERATOR_2G_PROFILE_ID)
   self.assertEqual(task['attempts'][-1]['resource_profile']['admission_reservation_bytes'],2*c.GIB)
   self.assertEqual(task['attempts'][-1]['resource_profile']['admission_profile_evidence'],proof)
   request=json.loads(Path(task['request_path']).read_text());self.assertEqual(request['task'],dict(definition,artifact_dir=str(root/'artifacts'/key)))
   self.assertNotIn('admission_reservation_bytes',request['task'])
 def test_resume_preserves_two_gib_evidence_and_promotion_uses_default(self):
  definition=d('e5/rep_1/fit/direct/gmm/feature_noise_05');proof={'profile_id':e.GENERATOR_2G_PROFILE_ID,'reservation_gib':2,'reason':'persisted evidence'};prior={'attempt_id':'prior','resource_profile':{'admission_profile_id':e.GENERATOR_2G_PROFILE_ID,'admission_reservation_bytes':2*c.GIB,'admission_profile_evidence':proof}}
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);t=dict(planned(definition,'planned'),attempts=[prior],admission_reservation_bytes=2*c.GIB,admission_profile_id=e.GENERATOR_2G_PROFILE_ID,admission_profile_evidence=proof);proc=Mock(pid=424243)
   with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{definition['key']:definition}),patch.object(c,'worker_reservation_bytes',return_value=2*c.GIB),patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'start_ticks',return_value='78'),patch.object(c,'put'),patch.object(c,'event'):
    c.admit(None,t)
   self.assertEqual(t['attempts'][0],prior);self.assertEqual(t['attempts'][-1]['resource_profile']['admission_reservation_bytes'],2*c.GIB);self.assertEqual(t['attempts'][-1]['resource_profile']['admission_profile_evidence'],proof)
   promoted=dict(planned(definition,'planned'),attempts=[prior],adaptive_promoted_heavy=True,admission_reservation_bytes=2*c.GIB,admission_profile_id=e.GENERATOR_2G_PROFILE_ID,admission_profile_evidence=proof);proc2=Mock(pid=424244)
   with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{definition['key']:definition}),patch.object(c.subprocess,'Popen',return_value=proc2),patch.object(c,'start_ticks',return_value='79'),patch.object(c,'put'),patch.object(c,'event'):
    c.admit(None,promoted)
   self.assertEqual(promoted['attempts'][0],prior);self.assertEqual(promoted['attempts'][-1]['resource_profile']['admission_reservation_bytes'],10*c.GIB);self.assertEqual(promoted['attempts'][-1]['resource_profile']['admission_profile_id'],'adaptive-concurrency-20261025-v1.1-default')
 def test_two_gib_candidate_fits_headroom_that_rejects_four(self):
  reservations=[(10*c.GIB,1*c.GIB),(4*c.GIB,int(.5*c.GIB)),(4*c.GIB,int(.5*c.GIB))]
  available=int(27.5*c.GIB)
  self.assertTrue(c.memory_admission_ok(available,reservations,2*c.GIB))
  self.assertFalse(c.memory_admission_ok(available,reservations,4*c.GIB))
  self.assertFalse(c.memory_admission_ok(available,reservations,10*c.GIB))
 def test_helper_source_is_in_controller_source_hashes(self):
  self.assertIn('admission_evidence.py',c.source_hashes())
if __name__=='__main__':unittest.main()
