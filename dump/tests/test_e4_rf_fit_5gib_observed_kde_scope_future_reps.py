import copy,hashlib,json,tempfile,sys,unittest
from pathlib import Path
from unittest.mock import patch,Mock
STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
import admission_evidence as ae
import controller as c

PINNED_AUDIT_SHA=ae.E4_RF_FIT_5G_AUDIT_SHA256
PINNED_MODELS_BASIC_SHA=ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256

LABELS=['A','F','G','K','M','GALAXY','QSO']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,sort_keys=True)+'\n')

class E4RfFitFiveGiBTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'runtime';self.root.mkdir()
  self.original_audit_path=ae.E4_RF_FIT_5G_AUDIT_PATH
  self.original_audit_sha=ae.E4_RF_FIT_5G_AUDIT_SHA256
  self.original_models_sha=ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256
  self.definition={'key':'e4/rep_1/fit/treatment/random_forest/A_half_generated_gmm','experiment':4,'kind':'fit','rep':1,
   'method':'random_forest','route':'treatment','condition':'A_half_generated_gmm','treatment':'generated_gmm','generator':'gmm',
   'train_key':'e4/rep_1/append/A_half/gmm','dependencies':['e4/rep_1/append/A_half/gmm'],
   'selection_mode':'tune','trials':10,'selection_key':None,
   'selection_policy':'tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget'}
  self.task={**self.definition,'status':'planned','attempts':[]}
  self.audit=self.root/ae.E4_RF_FIT_5G_AUDIT_PATH
  self.audit_doc={'assessment':{'verdict':'SUPPORTS ONLY A PROVISIONAL 5 GiB ADMISSION RESERVATION WITH THE EXISTING 10 GiB HARD CAP AND PROMOTION GUARD.'},
   'current_counts':{'successful':25},'tuning_trials':{'actual_trial_phase_receipts':202},
   'final_fit_phases':{'receipt_count':25},'frozen_domain':{'fit_rows_max_observed':82394}}
  write(self.audit,self.audit_doc)
  model_path=self.root.parent/'project'/'benchmark'/'models_basic.py'
  model_path.parent.mkdir(parents=True,exist_ok=True);model_path.write_text('trial.suggest_categorical("n_estimators", [200, 500])\n')
  ae.E4_RF_FIT_5G_AUDIT_SHA256=sha(self.audit)
  ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256=sha(model_path)
  ae.E4_RF_FIT_5G_AUDIT_PATH=str(self.audit.relative_to(self.root))
  self.evidence={'profile_id':ae.E4_TREATMENT_RF_6G_PROFILE_ID,'reservation_gib':6,'treatment':'generated_gmm',
   'training_rows':82394,'npz_header_shapes':{'X':[82394,6],'y':[82394],'ids':[82394]},'train_key':self.definition['train_key']}
  self.original=ae._eligible_e4_treatment_rf_6gib
  def six_gate(t,d,root):
   if t.get('attempts') or t.get('key')!=d.get('key') or d.get('experiment')!=4 or d.get('kind')!='fit' or d.get('method')!='random_forest' or d.get('route')!='treatment':return False,None
   return True,copy.deepcopy(self.evidence)
  ae._eligible_e4_treatment_rf_6gib=six_gate
  c.R=self.root;c.DEFINITIONS={self.definition['key']:self.definition};c.LAST_MEMORY_ADMISSION={}
 def tearDown(self):
  ae._eligible_e4_treatment_rf_6gib=self.original
  ae.E4_RF_FIT_5G_AUDIT_PATH=self.original_audit_path
  ae.E4_RF_FIT_5G_AUDIT_SHA256=self.original_audit_sha
  ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256=self.original_models_sha
  self.tmp.cleanup()
 def test_authoritative_resource_audit_and_model_search_hashes_are_pinned(self):
  runtime=Path('/home/ubuntu/lamost_e1_migration_20261023/runtime_20261025')
  audit=runtime/ae.E4_RF_FIT_5G_AUDIT_PATH
  models=runtime.parent/'project'/'benchmark'/'models_basic.py'
  self.assertEqual(sha(audit),PINNED_AUDIT_SHA)
  self.assertEqual(sha(models),PINNED_MODELS_BASIC_SHA)

 def test_exact_narrow_candidate_gets_five_gib_and_stays_heavy(self):
  ok,e=ae.eligible_e4_treatment_rf_fit_5gib(self.task,self.definition,self.root)
  assert ok and e['reservation_gib']==5 and e['prior_reservation_gib']==6
  assert c.worker_reservation_bytes(self.task)==5*c.GIB
  assert c.worker_resource_class(self.task)=='heavy'
  assert e['frozen_n_estimators_domain']==[200,500]
  assert e['resource_audit_sha256']==ae.E4_RF_FIT_5G_AUDIT_SHA256
 def test_out_of_row_range_weighted_arf_kde_and_attempted_fail_closed(self):
  for rows in (80610,82395):
   e=copy.deepcopy(self.evidence);e['training_rows']=rows;e['npz_header_shapes']={'X':[rows,6],'y':[rows],'ids':[rows]}
   with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(True,e)):
    assert not ae.eligible_e4_treatment_rf_fit_5gib(self.task,self.definition,self.root)[0]
  for treatment in ('weighted','generated_arf'):
   d={**self.definition,'treatment':treatment}
   with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(True,{**self.evidence,'treatment':treatment})):
    assert not ae.eligible_e4_treatment_rf_fit_5gib(self.task,d,self.root)[0]
  attempted={**self.task,'attempts':[{'attempt_id':'old'}]}
  assert not ae.eligible_e4_treatment_rf_fit_5gib(attempted,self.definition,self.root)[0]
 def test_audit_and_model_search_hash_changes_fail_closed(self):
  audit_hash=ae.E4_RF_FIT_5G_AUDIT_SHA256;model_hash=ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256
  try:
   self.audit.write_text('{}\n')
   assert not ae.eligible_e4_treatment_rf_fit_5gib(self.task,self.definition,self.root)[0]
   write(self.audit,self.audit_doc);ae.E4_RF_FIT_5G_AUDIT_SHA256=sha(self.audit)
   model=self.root.parent/'project'/'benchmark'/'models_basic.py';model.write_text('# changed search\n')
   assert not ae.eligible_e4_treatment_rf_fit_5gib(self.task,self.definition,self.root)[0]
  finally:
   ae.E4_RF_FIT_5G_AUDIT_SHA256=audit_hash;ae.E4_RF_FIT_5G_MODELS_BASIC_SHA256=model_hash
 def test_future_generated_kde_rf_matching_conditions_are_eligible_and_raw_kde_is_not(self):
  key='e4/rep_2/fit/treatment/random_forest/GALAXY_tenth_generated_kde'
  definition={**self.definition,'key':key,'rep':2,'treatment':'generated_kde','generator':'kde','condition':'GALAXY_tenth_generated_kde','train_key':'e4/rep_2/append/GALAXY_tenth/kde'}
  task={**self.task,'key':key}
  evidence={**self.evidence,'treatment':'generated_kde','training_rows':82394,'train_key':definition['train_key']}
  with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(True,evidence)):
   ok,proof=ae.eligible_e4_treatment_rf_fit_5gib(task,definition,self.root)
  assert ok and proof['reservation_gib']==5
  wrong={**definition,'condition':'F_half_generated_kde','key':'e4/rep_2/fit/treatment/random_forest/F_half_generated_kde'}
  with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(True,evidence)):
   assert not ae.eligible_e4_treatment_rf_fit_5gib({**task,'key':wrong['key']},wrong,self.root)[0]
  terminal_key='e4/rep_1/fit/treatment/random_forest/GALAXY_tenth_generated_kde'
  terminal={**definition,'rep':1,'key':terminal_key}
  terminal_task={**task,'key':terminal_key,'attempts':[{'attempt_id':'existing'}]}
  assert not ae.eligible_e4_treatment_rf_fit_5gib(terminal_task,terminal,self.root)[0]
  raw_kde={**definition,'method':'kde','route':'direct','treatment':'direct'}
  with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(False,None)):
   assert not ae.eligible_e4_treatment_rf_fit_5gib(task,raw_kde,self.root)[0]
 def test_outside_narrow_envelope_retains_existing_six_gib_where_eligible(self):
  e=copy.deepcopy(self.evidence);e['training_rows']=80610;e['npz_header_shapes']={'X':[80610,6],'y':[80610],'ids':[80610]}
  with patch.object(ae,'_eligible_e4_treatment_rf_6gib',return_value=(True,e)):
   assert ae.eligible_e4_treatment_rf_fit_5gib(self.task,self.definition,self.root)==(False,None)
   assert c.worker_reservation_bytes(self.task)==6*c.GIB
  old5={**self.task,'attempts':[{'attempt_id':'old'}],'admission_reservation_bytes':5*c.GIB,
       'admission_profile_id':ae.E4_RF_FIT_5G_PROFILE_ID}
  assert c.worker_reservation_bytes(old5)==5*c.GIB
  old={**self.task,'attempts':[{'attempt_id':'old'}],'admission_reservation_bytes':6*c.GIB,
       'admission_profile_id':ae.E4_TREATMENT_RF_6G_PROFILE_ID}
  assert c.worker_reservation_bytes(old)==6*c.GIB
  assert c.promoted_reservation_bytes(old,6*c.GIB+1)==10*c.GIB
 def test_admit_records_five_gib_profile_without_changing_worker_request(self):
  key=self.definition['key'];task=dict(self.task)
  proc=Mock(pid=424242)
  with patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'start_ticks',return_value='77'),patch.object(c,'put'),patch.object(c,'event'):
   c.admit(None,task)
  assert task['admission_profile_id']==ae.E4_RF_FIT_5G_PROFILE_ID
  assert task['admission_reservation_bytes']==5*c.GIB
  request=json.loads(Path(task['request_path']).read_text())
  assert request['task']=={**self.definition,'artifact_dir':str(self.root/'artifacts'/key)}
  assert 'admission_profile_id' not in request['task']
  assert task['attempts'][-1]['resource_profile']['admission_profile_id']==ae.E4_RF_FIT_5G_PROFILE_ID

if __name__=='__main__':
 import unittest
 unittest.main()
