import importlib.util,hashlib,json,pathlib,tempfile,unittest,sys
R=pathlib.Path(__file__).resolve().parents[1]
P=R/'source/final_review.py'
spec=importlib.util.spec_from_file_location('staged_final_review',P)
fr=importlib.util.module_from_spec(spec);spec.loader.exec_module(fr)
class CoverageTests(unittest.TestCase):
 def test_runtime_inventory_covers_nested_source_and_engineering_tests_not_staging(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);runtime=root/'runtime';(runtime/'source/svm_margin').mkdir(parents=True);(runtime/'source/__pycache__').mkdir();(runtime/'source/staging').mkdir();(runtime/'tests').mkdir();(runtime/'tests/staging').mkdir()
   (runtime/'source/controller.py').write_text('a');(runtime/'source/svm_margin/science.py').write_text('b');(runtime/'source/new_helper.py').write_text('c');(runtime/'source/__pycache__/ignored.py').write_text('d');(runtime/'source/staging/ignored.py').write_text('e');(runtime/'tests/test_review.py').write_text('f');(runtime/'tests/staging/ignored.py').write_text('g')
   got={x.relative_to(runtime).as_posix() for x in fr.runtime_python_paths(runtime)}
   self.assertEqual(got,{'source/controller.py','source/svm_margin/science.py','source/new_helper.py','tests/test_review.py'})
   self.assertIn('source/new_helper.py',got)
 def test_helper_module_addition_and_mutation_change_bound_hashes(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);runtime=root/'runtime';(runtime/'source').mkdir(parents=True);helper=runtime/'source/helper.py';helper.write_text('value=1\n')
   def digest():return fr.sha_bytes(fr.canon(fr.runtime_code_records(root,runtime,{})))
   h1=digest();(runtime/'source/new_scoring_helper.py').write_text('value=2\n');h2=digest();self.assertNotEqual(h1,h2)
   (runtime/'source/new_scoring_helper.py').write_text('value=3\n');h3=digest();self.assertNotEqual(h2,h3)
 def test_public_provenance_inventory_is_derived_in_memory_from_finalizer(self):
  finalizer=R/'source/finalize_project.py'
  reason_helper=R/'staging/reason_text_curation_20261026/source'
  sys.path.insert(0,str(reason_helper))
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);runtime=root/'runtime_20261025';m=runtime/'manifests';inc=m/'incidents';inc.mkdir(parents=True)
   def put(rel,content):
    p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content);return p
   for name in ('baseline_identity_boundary_audit.json','concurrency_user_authorization_20261025.json'):
    put('runtime_20261025/manifests/'+name,'{}\n')
   for i in range(7):put(f'runtime_20261025/manifests/freeze_before_{i}.json','{}\n')
   e4={'observed_utc':'2026-10-26T00:00:00Z','bootstrap':False,'amendment':{'amendment_id':'fixture-e4','scope':'E4 weights','reason':'schema correction','validation':{'passed':True}},'cohort_container_supersessions':[],'dependent_unavailability_reset_keys':['e4/fixture/reset'],'invalid_fit_keys':['e4/fixture/invalid'],'scientific_trial_history_rows':5,'raw_private_evidence_retained_on_EC2':'PRIVATE_PAYLOAD_E4_SHOULD_NOT_APPEAR'}
   svm={'incident_id':'fixture-svm','observed_utc':'2026-10-26T00:00:00Z','classification':'implementation defect','error_signature':'margin interface','scientific_method_definition':'native margins','SVM_source_sha256':{'science.py':'abc'},'newSVM_engine_sha256':'def','nonSVM_engine_sha256_unchanged':'ghi','affected_invalid_control_evaluations':3,'affected_invalid_fit_tasks':42,'requeued_keys':['e4/fixture/svm'],'ordinary_terminal_tasks_requeued':0,'E1_orE2fits_started':0,'scientific_workers_signaled':0,'resource_limits_unchanged':{'phase_seconds':600},'original_freeze_utc_unchanged':'2026-10-25T00:00:00Z','plan_sha256_unchanged':'jkl','valid_control_models_preserved_sha256':{'fit':'mno'},'private_process_receipt':'PRIVATE_PAYLOAD_SVM_SHOULD_NOT_APPEAR'}
   from test_cold_finalizer_adapter import copy_pinned_qualified_closure
   copy_pinned_qualified_closure(root)
   raw_e4='runtime_20261025/manifests/incidents/e4_weight_schema_20261025.json';raw_svm='runtime_20261025/manifests/incidents/svm_native_margin_api_20261026.json'
   put(raw_e4,json.dumps(e4));put(raw_svm,json.dumps(svm));put('runtime_20261025/manifests/incidents/private_process_receipt.json','PRIVATE_RECEIPT')
   expected={}
   result=fr.public_provenance_records(root,runtime,expected,finalizer_path=finalizer)
   views=result['archive_views'];sources=result['source_records']
   self.assertEqual(len(views),40)
   self.assertEqual(len(sources),39)
   self.assertIn('runtime_20261025/manifests/incidents/e4_weight_schema_20261025_summary.json',views)
   self.assertIn('runtime_20261025/manifests/incidents/svm_native_margin_api_20261026_summary.json',views)
   self.assertIn('runtime_20261025/manifests/public_scientific_provenance_manifest.json',views)
   self.assertFalse((runtime/'manifests/incidents/e4_weight_schema_20261025_summary.json').exists())
   self.assertFalse((runtime/'manifests/public_scientific_provenance_manifest.json').exists())
   self.assertIn(str((root/raw_e4).resolve()),expected);self.assertIn(str((root/raw_svm).resolve()),expected)
   self.assertNotIn(str((root/raw_e4).resolve()),{m for m in views})
   serialized=json.dumps({'sources':sources,'views':views})
   self.assertNotIn('PRIVATE_PAYLOAD_E4_SHOULD_NOT_APPEAR',serialized)
   self.assertNotIn('PRIVATE_PAYLOAD_SVM_SHOULD_NOT_APPEAR',serialized)
   self.assertNotIn('PRIVATE_RECEIPT',serialized)
   before=fr.sha_bytes(fr.canon(result))
   # A stale candidate source hash is rejected before the archive view can be regenerated.
   e4['scientific_trial_history_rows']=6;(root/raw_e4).write_text(json.dumps(e4))
   with self.assertRaises(Exception):fr.public_provenance_records(root,runtime,expected,finalizer_path=finalizer)
   changed=fr.public_provenance_records(root,runtime,{},finalizer_path=finalizer)
   self.assertNotEqual(before,fr.sha_bytes(fr.canon(changed)))
 def test_registry_projection_scrubs_embedded_process_receipt_and_keeps_science(self):
  with tempfile.TemporaryDirectory() as td:
   runtime=pathlib.Path(td);attempt={'attempt_id':'attempt-a1','reason':"phase_exit: ScientificFitFailure: configured trial timed out; supervision={'phase':'trial','reason':'timeout','pid':913477,'pgid':913477,'seconds':600.1,'peak_tree_rss_kib':2048,'exit_code':-15,'finished_at':'2026-10-25T00:00:00Z','attempt_id':'attempt-a1','source_sha256':'deadbeef'}"}
   tasks=[{'key':f'fixture/{i:04d}','status':'validated_terminal','outcome':'successful','attempts':[attempt] if i==0 else []} for i in range(6270)]
   (runtime/'registry.json').write_text(json.dumps({'tasks':tasks}))
   view=fr.registry_projection(runtime);self.assertEqual(view['task_count'],6270)
   reason=view['tasks'][0]['attempts'][0]['reason']
   self.assertIn('ScientificFitFailure: configured trial timed out',reason)
   self.assertIn('seconds',reason);self.assertIn('600.1',reason);self.assertIn('peak_tree_rss_kib',reason);self.assertIn('2048',reason);self.assertIn('exit_code',reason);self.assertIn('-15',reason);self.assertIn('attempt-a1',reason);self.assertIn('deadbeef',reason)
   for private in ('913477','\"pid\"','\"pgid\"'):self.assertNotIn(private,reason)

if __name__=='__main__':unittest.main(verbosity=2)
