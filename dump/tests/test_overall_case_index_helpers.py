import json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]/'source'
sys.path.insert(0,str(HERE))
from case_index_helpers import (resource_projection,attempt_projection,model_provenance,
 normalize_state,later_status_counts,validate_planned_experiment_counts,manifest_budget,kernel_process_proven)

class CaseIndexHelperTests(unittest.TestCase):
 def test_status_totals_are_derived_when_outcomes_change(self):
  rows=[{'experiment':4,'status_normalized':'successful'},{'experiment':4,'status_normalized':'pending'},
        {'experiment':5,'status_normalized':'scientific_failure'}]
  self.assertEqual(later_status_counts(rows),{'4':{'pending':1,'successful':1},'5':{'scientific_failure':1}})
  rows[1]['status_normalized']='successful'
  self.assertEqual(later_status_counts(rows)['4'],{'successful':2})
 def test_planned_counts_remain_design_bound(self):
  rows=[{'experiment':3}]*69+[{'experiment':4}]*1773+[{'experiment':5}]*960+[{'experiment':6}]*21
  self.assertEqual(validate_planned_experiment_counts(rows,{3:69,4:1773,5:960,6:21}),{3:69,4:1773,5:960,6:21})
  with self.assertRaises(ValueError):validate_planned_experiment_counts(rows[:-1],{3:69,4:1773,5:960,6:21})
 def test_manifest_budget_is_dynamic_and_single_value(self):
  self.assertEqual(manifest_budget({'budgets':[100000]}),100000)
  self.assertEqual(manifest_budget({'budgets':[300000]}),300000)
  with self.assertRaises(ValueError):manifest_budget({'budgets':[100000,300000]})
 def test_admission_profile_fields_and_source_are_retained_safely(self):
  projected=resource_projection({'kind':'fit'},{'resource_profile':{'admission_profile_id':'E4_RF_4G','admission_reservation_bytes':4294967296,'worker_memory_limit_gib':10,'worker_memory_gib':10,'phase_timeout_seconds':600,'pid':77},'resource_profile_source':'admission_manifest'})
  self.assertEqual(projected['admission_profile_id'],'E4_RF_4G')
  self.assertEqual(projected['admission_reservation_bytes'],4294967296)
  self.assertEqual(projected['worker_memory_limit_gib'],10)
  self.assertEqual(projected['resource_profile_source'],'admission_manifest')
  self.assertNotIn('pid',projected)
 def test_alias_is_not_mislabeled_as_new_fit(self):
  t={'kind':'alias','dependencies':['e3/rep_1/eval/direct/kde']}
  self.assertEqual(model_provenance(t,{}),'evaluation_alias_of:e3/rep_1/eval/direct/kde')
 def test_running_needs_exact_argv_and_nested_task_attempt_identity(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);proc=root/'321';proc.mkdir();runtime=root/'runtime_20261025'
   entry=runtime/'source/worker.py';entry.parent.mkdir(parents=True);entry.write_text('# fixture')
   req=root/'request.json';key='e4/rep_1/fit/direct/rbf_svm/control'
   req.write_text(json.dumps({'task':{'key':key,'attempt_id':'attempt-abc'}}))
   (proc/'cwd').symlink_to(root,target_is_directory=True)
   fields=['S']+['0']*18+['777'];(proc/'stat').write_text('321 (worker (nested)) '+' '.join(fields))
   def argv(worker,request):
    (proc/'cmdline').write_bytes(('\0'.join(['/usr/bin/python',str(worker),'--request',str(request)])+'\0').encode())
   argv(entry,req)
   task={'key':key,'kind':'fit','method':'rbf_svm','pid':321,'process_start_ticks':777,
         'attempt_id':'attempt-abc','worker_entrypoint':str(entry),'request_path':str(req)}
   self.assertTrue(kernel_process_proven(task,root))
   # The script token must match exactly; a correct request cannot mask a wrong worker.
   wrong=root/'worker.py';wrong.write_text('# wrong worker');argv(wrong,req)
   self.assertFalse(kernel_process_proven(task,root))
   # Correct PID and entrypoint still fail when nested request task identity differs.
   argv(entry,req);req.write_text(json.dumps({'task':{'key':'e5/rep_1/fit/direct/rbf_svm/control','attempt_id':'attempt-abc'}}))
   self.assertFalse(kernel_process_proven(task,root))
   req.write_text(json.dumps({'task':{'key':key,'attempt_id':'wrong-attempt'}}))
   self.assertFalse(kernel_process_proven(task,root))
   req.write_text(json.dumps({'task':{'key':key,'attempt_id':'attempt-abc'}}))
   task['process_start_ticks']=778
   self.assertFalse(kernel_process_proven(task,root))
   task['process_start_ticks']=777;task['pid']=999
   self.assertFalse(kernel_process_proven(task,root))
 def test_worker_entrypoint_is_derived_from_runtime_and_method(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);runtime=root/'runtime_20261025';entry=runtime/'source/svm_margin/worker.py'
   entry.parent.mkdir(parents=True);entry.write_text('# fixture')
   proc=root/'321';proc.mkdir();req=root/'request.json';key='e5/rep_1/fit/direct/rbf_svm/control'
   req.write_text(json.dumps({'task':{'key':key}}));(proc/'cwd').symlink_to(root,target_is_directory=True)
   (proc/'stat').write_text('321 (svm worker) '+' '.join(['S']+['0']*18+['778']))
   (proc/'cmdline').write_bytes(('\0'.join(['/usr/bin/python',str(entry),'--request',str(req)])+'\0').encode())
   task={'key':key,'kind':'fit','method':'rbf_svm','pid':321,'process_start_ticks':778,'request_path':str(req)}
   self.assertTrue(kernel_process_proven(task,root,runtime_root=runtime))
 def test_running_registry_state_without_proof_stays_pending(self):
  self.assertEqual(normalize_state('running',None,False),'pending')
  self.assertEqual(normalize_state('running',None,True),'running')
if __name__=='__main__':unittest.main()

