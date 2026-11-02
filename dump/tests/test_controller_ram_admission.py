import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
SRC=Path(__file__).resolve().parents[1]/"source"/"controller.py"
spec=importlib.util.spec_from_file_location("staged_controller",SRC)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
G=c.GIB
class AdaptiveAdmissionTests(unittest.TestCase):
 def test_classification_is_conservative(self):
  for method in ("logistic","hist_gb","kde"):
   self.assertEqual(c.worker_resource_class({"kind":"fit","method":method}),"light")
  for method in ("gmm","copula","chow_liu","random_forest","extra_trees","arf","rbf_svm","knn","mystery"):
   self.assertEqual(c.worker_resource_class({"kind":"fit","method":method}),"heavy")
  self.assertEqual(c.worker_resource_class({"kind":"generate","method":"chow_liu"}),"light")
  self.assertEqual(c.worker_resource_class({"kind":"generate","method":"arf"}),"heavy")
 def test_reservations_and_promotion(self):
  light={"kind":"fit","method":"logistic"}
  self.assertEqual(c.worker_reservation_bytes(light),2*G)
  self.assertEqual(c.promoted_reservation_bytes(light,2*G),2*G)
  self.assertEqual(c.promoted_reservation_bytes(light,2*G+1),10*G)
  self.assertEqual(c.worker_reservation_bytes({"kind":"fit","method":"arf"}),10*G)
  self.assertEqual(c.worker_reservation_bytes({"kind":"e4_cohort"}),G)
  self.assertEqual(c.worker_reservation_bytes({"kind":"alias"}),int(.25*G))
  self.assertEqual(c.worker_reservation_bytes({"kind":"alias","adaptive_promoted_heavy":True}),10*G)
 def test_cpu_slots_keep_two_idle_cores_without_static_two_worker_cap(self):
  self.assertEqual(c.cpu_admission_slots(6,16,8,2),6)
  self.assertEqual(c.cpu_admission_slots(3,16,2,2),0)
  self.assertEqual(c.cpu_admission_slots(0,16,0,2),0)
  self.assertEqual(c.cpu_admission_slots(20,16,12,2),0)
 def test_memory_math_and_commitment_margin(self):
  self.assertFalse(c.memory_admission_ok(8*G-1,[],2*G))
  self.assertTrue(c.memory_admission_ok(11*G,[],2*G))
  self.assertFalse(c.memory_admission_ok(10*G-1,[],2*G))
  self.assertTrue(c.memory_admission_ok(12*G,[(2*G,1*G)],2*G))
  self.assertFalse(c.memory_admission_ok(10*G,[(10*G,8*G)],2*G))
  self.assertFalse(c.needs_resource_reclaim(10*G,2*G))
  self.assertTrue(c.needs_resource_reclaim(9*G,2*G))
 def test_bracketed_sampler_credits_min_and_retains_peak(self):
  task={"key":"running","kind":"fit","method":"logistic"}
  calls=[];charges=iter([int(1.5*G),int(2.25*G)])
  result=c.bracketed_worker_memory([task],rows_reader=lambda:(calls.append("rows") or {}),available_reader=lambda:(calls.append("available") or 20*G),charge_reader=lambda t,r:next(charges))
  self.assertEqual(calls,["rows","available","rows"])
  self.assertEqual(result,(20*G,[int(1.5*G)],[int(2.25*G)]))
 def test_actual_candidate_promotes_from_bracket_peak_and_uses_min_credit(self):
  task={"key":"live-light","status":"running","kind":"fit","method":"logistic"}
  ready={"key":"next","kind":"fit","method":"gaussian_nb"}
  original=c.bracketed_worker_memory;calls=[];charges=iter([int(1.5*G),int(2.25*G)])
  def sample(running):
   return original(running,rows_reader=lambda:(calls.append("rows") or {}),available_reader=lambda:(calls.append("available") or 20*G),charge_reader=lambda t,r:next(charges))
  with patch.object(c,"bracketed_worker_memory",side_effect=sample),patch.object(c,"put"),patch.object(c,"atomic"):
   result=c.admission_candidate(None,[task],[ready],idle_cores=10)
  self.assertIsNone(result)
  self.assertTrue(task["adaptive_promoted_heavy"])
  row=c.LAST_MEMORY_ADMISSION["running_workers"][0]
  self.assertEqual(row["credited_pss_bytes"],int(1.5*G))
  self.assertEqual(row["observed_peak_pss_bytes"],int(2.25*G))
  self.assertEqual(row["reservation_bytes"],10*G)
 def test_actual_candidate_does_not_double_credit_growth(self):
  task={"key":"heavy-live","status":"running","kind":"fit","method":"random_forest"}
  ready={"key":"light-next","kind":"fit","method":"gaussian_nb"}
  original=c.bracketed_worker_memory;charges=iter([4*G,6*G])
  def sample(running):
   return original(running,rows_reader=lambda:{},available_reader=lambda:15*G,charge_reader=lambda t,r:next(charges))
  with patch.object(c,"bracketed_worker_memory",side_effect=sample),patch.object(c,"atomic"):
   result=c.admission_candidate(None,[task],[ready],idle_cores=10)
  self.assertIsNone(result)
  row=c.LAST_MEMORY_ADMISSION["running_workers"][0]
  self.assertEqual(row["credited_pss_bytes"],4*G)
  self.assertEqual(row["observed_peak_pss_bytes"],6*G)
 def test_e4_direct_rf_80k_profile_is_narrow_and_prospective(self):
  base={'experiment':4,'kind':'fit','method':'random_forest','route':'direct','rep':1,'condition':'A_half','train_key':'e4/rep_1/cohort/A_half'}
  self.assertTrue(c.is_e4_direct_rf_80k(base))
  self.assertEqual(c.worker_reservation_bytes(base),4*G)
  old=dict(base,status='running',attempts=[{'attempt_id':'old','resource_profile':{'admission_reservation_bytes':10*G}}])
  self.assertEqual(c.worker_reservation_bytes(old),10*G)
  promoted=dict(base,adaptive_promoted_heavy=True,admission_reservation_bytes=4*G)
  self.assertEqual(c.worker_reservation_bytes(promoted),10*G)
  excluded=[dict(base,experiment=3),dict(base,route='synthetic'),dict(base,route='treatment'),dict(base,condition='control'),dict(base,condition='B_half'),dict(base,rep=4),dict(base,train_key='other')]
  for task in excluded:
   task.pop('admission_reservation_bytes',None)
   self.assertFalse(c.is_e4_direct_rf_80k(task))
   self.assertEqual(c.worker_reservation_bytes(task),10*G)
 def test_admit_persists_profile_per_attempt_without_scientific_task_fields(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);key='e4/rep_1/fit/direct/random_forest/A_half'
   definition={'key':key,'kind':'fit','experiment':4,'method':'random_forest','route':'direct','rep':1,'condition':'A_half','train_key':'e4/rep_1/cohort/A_half'}
   task=dict(definition,status='planned',attempts=[]);proc=Mock(pid=12345)
   with patch.object(c,'R',root),patch.object(c,'DEFINITIONS',{key:definition}),patch.object(c.subprocess,'Popen',return_value=proc),patch.object(c,'start_ticks',return_value='123'),patch.object(c,'put'),patch.object(c,'event'):
    c.admit(None,task)
   self.assertEqual(task['admission_reservation_bytes'],4*G)
   profile=task['attempts'][-1]['resource_profile']
   self.assertEqual(profile['admission_profile_id'],c.E4_RF_80K_PROFILE_VERSION)
   self.assertEqual(profile['admission_reservation_bytes'],4*G)
   request=json.loads(Path(task['request_path']).read_text())
   expected=dict(definition,artifact_dir=str(root/'artifacts'/key))
   self.assertEqual(request['task'],expected)
   self.assertNotIn('admission_profile_id',request['task'])
 def test_old_attempt_and_pending_result_are_not_reclaim_targets(self):
  old={"status":"running","attempts":[{"attempt_id":"old"}]}
  new={"status":"running","attempts":[{"attempt_id":"new"}],"adaptive_policy_revision":c.ADAPTIVE_REVISION}
  self.assertFalse(c.adaptive_task_eligible(old));self.assertTrue(c.adaptive_task_eligible(new))
  with tempfile.TemporaryDirectory() as td:
   result=Path(td)/"worker_result.json";result.write_text("{}")
   task=dict(new,key="completed-result",result_path=str(result))
   with patch.object(c,"bracketed_worker_memory",return_value=(7*G,[],[])),patch.object(c,"verified_adaptive_worker",return_value=True) as verified,patch.object(c,"terminate_verified") as terminate,patch.object(c,"atomic"):
    c.EMERGENCY_BACKOFF_UNTIL=0
    c.emergency_interrupt_one(None,{task["key"]:task})
    terminate.assert_not_called()
    verified.assert_not_called()
  new["adaptive_emergency_term_epoch"]=1
  self.assertFalse(c.adaptive_task_eligible(new))
 def test_process_identity_guard_rejects_wrong_attempt(self):
  with tempfile.TemporaryDirectory() as td:
   req=Path(td)/"request.json";req.write_text(json.dumps({"attempt_id":"wrong-id","task":{"key":"k"}}))
   t={"key":"k","pid":4321,"process_start_ticks":"77","request_path":str(req),"attempts":[{"attempt_id":"expected-id"}],"adaptive_policy_revision":c.ADAPTIVE_REVISION}
   original=Path.read_bytes
   def read_bytes(path):
    if str(path)=="/proc/4321/cmdline":return (str(c.R/"source/worker.py")+"\0"+str(req)).encode()
    return original(path)
   with patch.object(c,"alive",return_value=True),patch.object(Path,"read_bytes",read_bytes):
    self.assertFalse(c.verified_adaptive_worker(t))
 def test_recovery_clears_stale_supervision_flags_but_keeps_promotion(self):
  t={"key":"k","status":"running","operational_recoveries":0,"forced_reason":"old","forced_outcome":"operationally_invalid","forced_term_epoch":4,"orphan_term_epoch":3,"adaptive_emergency_term_epoch":5,"adaptive_emergency_reason":"pressure","adaptive_emergency_available_bytes":1,"adaptive_promoted_heavy":True}
  with patch.object(c,"orphan_phases",return_value=[]),patch.object(c,"put"),patch.object(c,"event"):
   c.recover(None,t,"verified operational interruption")
  self.assertEqual(t["status"],"planned")
  for k in ("forced_reason","forced_outcome","forced_term_epoch","orphan_term_epoch","adaptive_emergency_term_epoch","adaptive_emergency_reason","adaptive_emergency_available_bytes"):
   self.assertNotIn(k,t)
  self.assertTrue(t["adaptive_promoted_heavy"])
  self.assertEqual(t["operational_recoveries"],1)
  self.assertEqual(t["adaptive_incident_history"][-1]["reason"],"verified operational interruption")

 def test_new_worker_uses_nice_priority_and_snapshots_policy(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);c.DEFINITIONS={"k":{"key":"k","kind":"eval","experiment":3}}
   task={"key":"k","status":"planned","attempts":[]}
   proc=Mock(pid=12345)
   with patch.object(c,"R",root),patch.object(c.subprocess,"Popen",return_value=proc) as popen,patch.object(c,"start_ticks",return_value="123"),patch.object(c,"put"),patch.object(c,"event"):
    c.admit(None,task)
   argv=popen.call_args.args[0]
   self.assertEqual(argv[:3],["/usr/bin/nice","-n","10"])
   self.assertEqual(argv[3],c.sys.executable)
   self.assertIn(str(root/"source"/"worker.py"),argv)
   self.assertIn(task["request_path"],argv)
   self.assertEqual(task["attempts"][-1]["resource_profile"]["worker_nice"],10)

if __name__=="__main__":unittest.main()
