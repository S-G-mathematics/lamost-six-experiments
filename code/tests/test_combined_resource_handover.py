import importlib.util,sys,tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch,Mock
SOURCE=Path(__file__).resolve().parents[1]/'source'
sys.path.insert(0,str(SOURCE))
import controller as c
import admission_evidence as ae
class CombinedResourceHandoverTests(unittest.TestCase):
 def test_future_term_timestamp_is_not_inside_grace(self):
  task={'key':'x','status':'running','adaptive_emergency_term_epoch':110}
  with patch.object(c,'verified_adaptive_worker',return_value=True),patch.object(c,'orphan_phases',return_value=[]):
   self.assertEqual(c.pending_reclaim_in_grace({'x':task},8*c.GIB,observed_epoch=100),[])
 def test_new_profiles_are_recorded_without_changing_frozen_scientific_request(self):
  profiles=[(4,'arf',ae.E4_ARF_6G_PROFILE_ID,6),(5,'arf',ae.E5_ARF_6G_PROFILE_ID,6),(4,'random_forest',ae.E4_WEIGHTED_RF_5G_PROFILE_ID,5)]
  for exp,method,profile,gib in profiles:
   with self.subTest(profile=profile),tempfile.TemporaryDirectory() as td:
    runtime=Path(td);key=f'e{exp}/rep_1/fit/{method}/fixture'
    definition={'key':key,'experiment':exp,'kind':'fit','method':method,'seed':9271,'trials':5 if exp==4 and method=='arf' else 0,'route':'direct' if method=='arf' else 'treatment'}
    task={**definition,'status':'planned','attempts':[]}
    evidence={'profile_id':profile,'reservation_gib':gib,'resource_audit_sha256':'b3530fd93a17095fa6d3e8b7071b4df943cceea829ecad4415513ac06bf11c49'}
    with patch.object(c,'R',runtime),patch.object(c.archive_fit_admission,'inspect_runtime',return_value={'mode':'inactive'}),patch.object(c,'DEFINITIONS',{key:dict(definition)}),patch.object(c,'put'),patch.object(c,'event'),patch.object(c,'start_ticks',return_value='123'),patch.object(c.subprocess,'Popen',return_value=Mock(pid=9876)) as popen,patch.object(ae,'eligible_e5_direct_rf_eval',return_value=(False,None)),patch.object(ae,'eligible_e4_treatment_rf_eval',return_value=(False,None)),patch.object(ae,'eligible_e4_treatment_rf_fit_5gib',return_value=(False,None)),patch.object(ae,'eligible_2gib_resource_profile',return_value=(False,None)),patch.object(ae,'eligible_4gib',return_value=(False,None)),patch.object(ae,'eligible_rf_resource_profiles',return_value=(True,evidence)):
     self.assertEqual(c.worker_reservation_bytes(task),gib*c.GIB)
     c.admit(None,task)
    self.assertEqual(task['admission_profile_id'],profile)
    self.assertEqual(task['attempts'][0]['resource_profile']['admission_profile_evidence'],evidence)
    self.assertEqual(task['attempts'][0]['resource_profile']['worker_memory_limit_gib'],10)
    self.assertEqual(task['attempts'][0]['resource_profile']['trial_timeout_seconds'],600)
    req=json.loads(Path(task['request_path']).read_text())
    self.assertEqual(req['task'],{**definition,'artifact_dir':str(runtime/'artifacts'/key)})
    self.assertEqual(len(popen.call_args_list),1)
 def test_previous_attempt_reservation_is_preserved(self):
  for n in (4,5,6,10):
   t={'key':'old','kind':'fit','method':'arf','attempts':[{'attempt_id':'old'}],'admission_reservation_bytes':n*c.GIB}
   self.assertEqual(c.worker_reservation_bytes(t),n*c.GIB)
if __name__=='__main__':unittest.main()
