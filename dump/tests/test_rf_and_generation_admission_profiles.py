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
  for key in ('e5/rep_1/fit/direct/arf/feature_noise_05',):
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

class NarrowRFAdmissionProfileTests(unittest.TestCase):
 def setUp(self):
  c.R=BASE;c.DEFINITIONS=PLAN_BY_KEY

 def test_actual_e5_nonarf_generation_has_two_gib_with_exact_provenance(self):
  found={}
  for definition in PLAN:
   if definition.get('experiment')!=5 or definition.get('kind')!='generate' or definition.get('generator') not in ('gmm','copula','chow_liu','kde'): continue
   task=planned(definition);ok,proof=e.eligible_2gib_resource_profile(task,definition,BASE)
   if ok: found.setdefault(definition['generator'],(definition,task,proof))
  for family in ('gmm','copula','kde'):
   self.assertIn(family,found)
  for family,(definition,task,proof) in found.items():
   self.assertEqual(definition['n_rows'],400000)
   self.assertEqual(proof['generation_ratio'],5)
   self.assertEqual(proof['generator'],family)
   self.assertEqual(sum(proof['training_class_counts']),80000)
   self.assertEqual(proof['profile_id'],e.E5_GENERATION_2G_PROFILE_ID)
   self.assertEqual(c.worker_reservation_bytes(task),2*c.GIB)

 def test_label_count_read_fails_closed_when_npz_changes_mid_read(self):
  import hashlib,numpy as np
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/'tiny.npz';np.savez(path,y=np.zeros(80000,dtype='i8'))
   digest=hashlib.sha256(path.read_bytes()).hexdigest();original=e.np.load
   def load_then_mutate(*args,**kwargs):
    result=original(*args,**kwargs)
    with open(path,'ab') as f:f.write(b'x')
    return result
   with patch.object(e.np,'load',side_effect=load_then_mutate):
    self.assertIsNone(e._npz_label_counts(path,digest))
 def test_e5_generation_rejects_wrong_family_rows_dependency_or_attempt(self):
  definition=d('e5/rep_1/generate/feature_noise_05/gmm');task=planned(definition)
  for changes in ({'n_rows':100000},{'mechanism':'label_noise'},{'rate':0.2},{'fit_key':'e5/rep_1/fit/direct/gmm/feature_noise_10'},
                  {'dependencies':[]},{'generator':'arf'}):
   changed=dict(definition,**changes)
   self.assertFalse(e.eligible_2gib_resource_profile(task,changed,BASE)[0],changes)
  self.assertFalse(e.eligible_2gib_resource_profile(dict(task,attempts=[{'attempt_id':'previous'}]),definition,BASE)[0])
  arf=d('e5/rep_1/generate/feature_noise_05/arf')
  self.assertFalse(e.eligible_2gib_resource_profile(planned(arf),arf,BASE)[0])
  self.assertEqual(c.worker_reservation_bytes(planned(arf)),10*c.GIB)

 def test_future_chow_generation_family_gate_uses_frozen_task_and_selected_config(self):
  definition=d('e5/rep_1/generate/feature_noise_05/chow_liu');fitkey=definition['fit_key'];clean='e3/rep_1/fit/chow_liu';train='e5/rep_1/corruption/feature_noise_05'
  clean_result=json.loads((BASE/'artifacts'/clean/'fit_result.json').read_text())
  clean_selection=json.loads((BASE/'artifacts'/clean/'selection.json').read_text())
  fit_definition=d(fitkey)
  fake_fit={'task':dict(fit_definition),'result':{'params':clean_selection['selected_params'],'source_sha256':'a'*64,'class_counts':[4519,17848,31159,17127,6913,1230,1204]}}
  actual_json=e._json
  def fake_json(path):
   value=actual_json(path)
   text=str(path)
   if text.endswith('/'+fitkey+'/fit_result.json'):return fake_fit
   return value
  shape={'X':(80000,6),'y':(80000,),'ids':(80000,)}
  with patch.object(e,'_json',side_effect=fake_json),patch.object(e,'_valid_npz_artifact',return_value=({'kind':'e5_corruption','rep':1,'mechanism':'feature_noise','rate':0.05},shape)),patch.object(e,'_valid_published_fit',return_value=True),patch.object(e,'_sha256_cached',return_value='a'*64),patch.object(e,'_npz_label_counts',return_value=fake_fit['result']['class_counts']):
   ok,proof=e.eligible_2gib_resource_profile(planned(definition),definition,BASE)
  self.assertTrue(ok,proof);self.assertEqual(proof['generator'],'chow_liu');self.assertEqual(proof['n_rows'],400000)
 def test_e5_generation_rejects_mismatched_fit_params_and_actual_label_counts(self):
  definition=d('e5/rep_1/generate/feature_noise_05/gmm');task=planned(definition);actual_json=e._json
  def mismatched_fit(path):
   value=actual_json(path)
   if str(path).endswith('/e5/rep_1/fit/direct/gmm/feature_noise_05/fit_result.json') and value:
    value=json.loads(json.dumps(value));value['result']['params']['n_components']=999
   return value
  with patch.object(e,'_json',side_effect=mismatched_fit):
   self.assertFalse(e.eligible_2gib_resource_profile(task,definition,BASE)[0])
  with patch.object(e,'_npz_label_counts',return_value=[1,1,1,1,1,1,79994]):
   self.assertFalse(e.eligible_2gib_resource_profile(task,definition,BASE)[0])
 def test_actual_e5_rf_fixed_fit_is_four_gib_and_identity_bound(self):
  definition=d('e5/rep_1/fit/direct/random_forest/feature_noise_05');t=planned(definition)
  ok,proof=e.eligible_rf_resource_profiles(t,definition,BASE)
  self.assertTrue(ok,proof);self.assertEqual(proof['reservation_gib'],4)
  self.assertEqual(proof['fit_key'],'e3/rep_1/fit/real/random_forest')
  self.assertEqual(proof['selected_params'],{'max_depth':None,'max_features':1.0,'min_samples_leaf':1,'n_estimators':200})
  self.assertEqual(c.worker_reservation_bytes(t),4*c.GIB)
 def test_e5_rf_wrong_selection_dependency_or_attempt_defaults_ten(self):
  definition=d('e5/rep_1/fit/direct/random_forest/feature_noise_05')
  for changes in ({'selection_key':'e3/rep_2/fit/real/random_forest'},{'mechanism':'missingness'},{'rate':0.2},{'dependencies':[definition['train_key']]},{'selection_mode':'tune'},{'trials':10},{'selection_policy':'other'},{'train_key':'e5/rep_1/corruption/missingness_05'}):
   changed=dict(definition,**changes)
   self.assertFalse(e.eligible_rf_resource_profiles(planned(definition),changed,BASE)[0],changes)
  self.assertFalse(e.eligible_rf_resource_profiles(dict(planned(definition),attempts=[{'attempt_id':'old'}]),definition,BASE)[0])
 def test_e5_rf_requires_valid_clean_fit_and_selected_configuration(self):
  definition=d('e5/rep_1/fit/direct/random_forest/feature_noise_05')
  basekey=definition['selection_key']; selection_path=BASE/'artifacts'/basekey/'selection.json'
  original=json.loads(selection_path.read_text())
  self.assertEqual(original['selected_params']['n_estimators'],200)
  changed=dict(definition,selection_key='e3/rep_1/fit/real/gmm')
  self.assertFalse(e.eligible_rf_resource_profiles(planned(definition),changed,BASE)[0])
  val=json.loads((BASE/'artifacts'/basekey/'validation.json').read_text())
  self.assertEqual(val['files']['selection.json'],e._sha256_cached(selection_path))
  actual_json=e._json
  def altered(path):
   value=actual_json(path)
   if str(path).endswith('/selection.json') and isinstance(value,dict):
    value=dict(value);value['selected_params']=dict(value.get('selected_params',{}),n_estimators=999)
   return value
  with patch.object(e,'_json',side_effect=altered),patch.object(e,'_valid_published_fit',return_value=True):
   self.assertFalse(e.eligible_rf_resource_profiles(planned(definition),definition,BASE)[0])
 def test_actual_e4_ros_and_generated_examples_are_six_gib(self):
  for key in ('e4/rep_1/fit/treatment/random_forest/A_half_ros','e4/rep_1/fit/treatment/random_forest/A_half_generated_chow_liu'):
   definition=d(key);ok,proof=e.eligible_rf_resource_profiles(planned(definition),definition,BASE)
   self.assertTrue(ok,(key,proof));self.assertEqual(proof['reservation_gib'],6)
   self.assertEqual(proof['training_rows'],82394);self.assertEqual(c.worker_reservation_bytes(planned(definition)),6*c.GIB)
 def test_e4_weighted_larger_synthetic_and_wrong_cohort_stay_default(self):
  weighted=d('e4/rep_1/fit/treatment/random_forest/A_half_weighted')
  self.assertFalse(e.eligible_rf_resource_profiles(planned(weighted),weighted,BASE)[0])
  self.assertEqual(c.worker_reservation_bytes(planned(weighted)),10*c.GIB)
  ros=d('e4/rep_1/fit/treatment/random_forest/A_half_ros')
  for changes in ({'train_key':'e4/rep_1/treatment/A_tenth/ros'},{'treatment':'weighted'},{'route':'synthetic'},{'trials':0},{'selection_mode':'fixed'}):
   changed=dict(ros,**changes)
   self.assertFalse(e.eligible_rf_resource_profiles(planned(ros),changed,BASE)[0],changes)
  generated=d('e4/rep_1/fit/treatment/random_forest/A_half_generated_arf')
  self.assertFalse(e.eligible_rf_resource_profiles(planned(generated),dict(generated,route='synthetic'),BASE)[0])
  self.assertFalse(e.eligible_rf_resource_profiles(planned(generated),dict(generated,generator='gmm'),BASE)[0])
  self.assertFalse(e.eligible_rf_resource_profiles(dict(planned(ros),attempts=[{'attempt_id':'prior'}]),ros,BASE)[0])

 def test_actual_larger_e4_treatment_is_not_admitted(self):
  definition=d('e4/rep_1/fit/treatment/random_forest/A_tenth_ros')
  ok,_=e.eligible_rf_resource_profiles(planned(definition),definition,BASE)
  self.assertFalse(ok)
  self.assertEqual(c.worker_reservation_bytes(planned(definition)),10*c.GIB)
 def test_e4_wrong_npz_header_fails_even_with_matching_file_hash(self):
  import hashlib,shutil,numpy as np
  definition=d('e4/rep_1/fit/treatment/random_forest/A_half_ros'); key=definition['train_key']
  source=BASE/'artifacts'/key
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);dst=root/'artifacts'/key;dst.mkdir(parents=True)
   parent_src=BASE/'artifacts/e4/rep_1/cohort/A_half';parent_dst=root/'artifacts/e4/rep_1/cohort/A_half';parent_dst.mkdir(parents=True)
   for name in ('metadata.json','validation.json','data.npz'):shutil.copy2(parent_src/name,parent_dst/name)
   meta=json.loads((source/'metadata.json').read_text());val=json.loads((source/'validation.json').read_text())
   meta['parent']=str(parent_dst)
   (dst/'metadata.json').write_text(json.dumps(meta));val['files']['data.npz']=''
   np.savez(dst/'data.npz',X=np.zeros((82394,5),dtype='f4'),y=np.zeros(82394,dtype='i8'),ids=np.zeros(82394,dtype='i8'))
   h=hashlib.sha256((dst/'data.npz').read_bytes()).hexdigest();val['files']['data.npz']=h
   (dst/'validation.json').write_text(json.dumps(val))
   self.assertFalse(e.eligible_rf_resource_profiles(planned(definition),definition,root)[0])
 def test_rf_profiles_persist_selected_resource_profile_on_admit(self):
  for key,reservation,profile,checker in (
      ('e5/rep_1/fit/direct/random_forest/feature_noise_05',4,e.E5_RF_4G_PROFILE_ID,'eligible_rf_resource_profiles'),
      ('e4/rep_1/fit/treatment/random_forest/A_half_ros',6,e.E4_TREATMENT_RF_6G_PROFILE_ID,'eligible_rf_resource_profiles'),
      ('e5/rep_1/generate/feature_noise_05/gmm',2,e.E5_GENERATION_2G_PROFILE_ID,'eligible_2gib_resource_profile')):
   definition=d(key);task=planned(definition,'planned');proc=Mock(pid=515151);proof={'profile_id':profile,'reservation_gib':reservation,'reason':'validated test profile'}
   with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{key:definition}),patch.object(c,'worker_reservation_bytes',return_value=reservation*c.GIB),patch.object(c.admission_evidence,checker,return_value=(True,proof)),patch.object(c,'start_ticks',return_value='91'),patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'put'),patch.object(c,'event'):
     c.admit(None,task)
    self.assertEqual(task['admission_reservation_bytes'],reservation*c.GIB)
    self.assertEqual(task['admission_profile_id'],profile)
    if definition.get('kind')=='generate':self.assertNotEqual(task['admission_profile_id'],e.GENERATOR_2G_PROFILE_ID)
    self.assertEqual(task['attempts'][-1]['resource_profile']['admission_reservation_bytes'],reservation*c.GIB)
    self.assertEqual(task['attempts'][-1]['resource_profile']['admission_profile_evidence'],proof)
    request=json.loads(Path(task['request_path']).read_text())
    self.assertNotIn('admission_reservation_bytes',request['task'])
 def test_existing_profiles_and_arbitrary_rf_stay_unchanged(self):
  self.assertEqual(c.worker_reservation_bytes(planned(d('e4/rep_1/fit/direct/random_forest/A_half'))),4*c.GIB)
  self.assertEqual(c.worker_reservation_bytes(planned(d('e5/rep_1/fit/direct/arf/feature_noise_05'))),10*c.GIB)
  self.assertEqual(c.worker_reservation_bytes(planned(d('e5/rep_1/fit/direct/random_forest/feature_noise_05'))),4*c.GIB)

if __name__=='__main__':unittest.main()
