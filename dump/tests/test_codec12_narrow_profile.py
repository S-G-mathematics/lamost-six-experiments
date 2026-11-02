from __future__ import annotations
import hashlib,json,sys,tempfile,shutil,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'source'))
import types
sys.modules.setdefault('controller',types.ModuleType('controller'))
import batch_plan, cold_auto_compaction as auto, run_batch, commit_batch_child as child, archive_fit_admission as admission
G=1<<30
TEST_FILES=('tests/test_codec12_narrow_profile.py','tests/test_codec_payload12_profile.py','tests/test_codec4gib_archive_profile.py','tests/test_driver_cli_alignment.py')
SOURCES=('controller.py','archive_fit_admission.py','cold_auto_compaction.py','run_batch.py','commit_batch_child.py','cold_model_storage.py','cold_codec_storage.py','reversible_joblib_codec.py','cold_storage_safety.py','batch_plan.py','admission_evidence.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canon(d):return (json.dumps(d,sort_keys=True,separators=(',',':'))+'\n').encode()
def make_policy_fixture(root):
 root=Path(root);src=root/'source';src.mkdir(parents=True,exist_ok=True)
 for n in SOURCES:shutil.copy2(HERE/'source'/n,src/n)
 for rel in ('cache/cache_manifest.json','manifests/E4_MANIFEST.json','manifests/E5_MANIFEST.json'):
  dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(HERE/rel,dst)
 for rel in TEST_FILES:
  td=root/rel;td.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(HERE/rel,td)
 sm={n:sha(src/n) for n in SOURCES}; ni={n:sha(root/n) for n in ('cache/cache_manifest.json','manifests/E4_MANIFEST.json','manifests/E5_MANIFEST.json')}
 op={'owner_operation':admission.OWNER_OPERATION,'batch_policy':'storage-followup-codec','archive_io_profile':batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE,'storage_codec_policy':'reversible-xz-v1-payload12'}
 overlap={'current_workers':'zero_before_archive_start','new_workers':'blocked_while_archive_helper_active'}
 scope={'kind':'archive_only','fit_overlap':False,'require_zero_running_workers':True,'source_rows_are_terminal_only':True,'complete_alias_groups_only':True}
 res={'helper_reservation_gib':1.5,'helper_cpu_reservation_units':1,'host_os_harbor_reserve_gib':6,'commitment_growth_margin_gib':2,'admission_only_safety_buffer_gib':1,'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,'termination_grace_seconds':30,'archive_wall_seconds':5400,'archive_wrapper_wall_seconds':5460,'archive_child_rss_limit_bytes':1073741824,'archive_child_address_space_limit_bytes':939524096,'archive_wrapper_rss_limit_bytes':1610612736,'native_threads':1,'nested_threads':1,'batch_max_bytes':G,'batch_max_inode_groups':64,'encoded_temp_max_bytes':8*G,'archive_disk_reserve_bytes':10*G,'archive_disk_growth_margin_bytes':2*G,'max_payload_bytes':12*G}
 policy={'schema':'lamost-archive-native-codec-payload12-narrow-fit-overlap-policy/1','status':'qualified','policy_id':'archive-native-codec-payload12-1gib64-archive-only-v1','scope':scope,'resources':res,'admission_temp_budget_field':'codec_temp_budget_bytes','legacy_temp_field_policy':'encoded_temp_max_bytes_must_be_absent_or_equal','archive_operation':op,'overlap_classes':overlap,'source_sha256':sm,'native_input_manifests':ni,'qualification_path':'reports/engineering_audits/ARCHIVE_NATIVE_CODEC12_NARROW_QUALIFICATION_20261030.json'}
 polraw=canon(policy);polsha=hashlib.sha256(polraw).hexdigest(); pp=root/admission.CODEC12_NARROW_POLICY_REL;pp.parent.mkdir(parents=True,exist_ok=True);pp.write_bytes(polraw)
 tf={rel:sha(HERE/rel) for rel in TEST_FILES}
 fr={'schema':'lamost-codec12-narrow-profile-focused-tests/1','status':'passed','source_sha256':sm,'test_file_sha256':tf,'expected_test_count':25,'passed_test_count':25,'failed_test_count':0,'combined_test_count':25,'combined_passed_test_count':25,'combined_failed_test_count':0,'fit_attempts_started':0,'limits':{'address_space_limit_bytes':1073741824,'wall_seconds':60,'native_threads':1,'nice':19}}
 fp=root/'reports/engineering_audits/CODEC12_NARROW_FOCUSED.json';fp.parent.mkdir(parents=True,exist_ok=True);fp.write_bytes(canon(fr))
 ar={'schema':'lamost-codec12-narrow-archive-preflight/1','status':'passed','source_sha256':sm,'archive_operation':op,'fit_attempts_started':0,'running_workers_before_archive':0,'new_fit_gate':'blocked_while_active','archive_alias_ownership_closure':'source_logic_pinned_fixture_only','fixture_only':True,'controller_gate_source_sha256':sm['controller.py']}
 ap=root/'reports/engineering_audits/CODEC12_NARROW_ARCHIVE_ONLY_PREFLIGHT.json';ap.write_bytes(canon(ar))
 q={'schema':admission.CODEC12_NARROW_QUALIFICATION_SCHEMA,'status':'passed','policy_sha256':polsha,'source_sha256':sm,'native_input_manifests':ni,'payload12_narrow_profile_tests':{'status':'passed','receipt_path':'reports/engineering_audits/CODEC12_NARROW_FOCUSED.json','receipt_sha256':sha(fp),'test_file_sha256':tf},'archive_only_preflight':{'status':'passed','receipt_path':'reports/engineering_audits/CODEC12_NARROW_ARCHIVE_ONLY_PREFLIGHT.json','receipt_sha256':sha(ap)}}
 qp=root/policy['qualification_path'];qp.parent.mkdir(parents=True,exist_ok=True);qp.write_bytes(canon(q));freeze={'source_sha256':sm,admission.CODEC12_NARROW_POLICY_FIELD:polsha,admission.CODEC12_NARROW_QUALIFICATION_FIELD:sha(qp)}
 (root/'ADMISSION_HOLD.json').write_text(json.dumps({'owner_operation':admission.OWNER_OPERATION,'batch_policy':'storage-followup-codec','archive_io_profile':batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE,'storage_codec_policy':'reversible-xz-v1-payload12'}))
 return freeze,sm
class NarrowPayload12ProfileTests(unittest.TestCase):
 def test_auto_profile_exact_limits_and_ceiling(self):
  p=batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE;c=auto.batch_config('reversible-xz-v1-payload12',p)
  self.assertEqual((c['max_bytes'],c['max_groups'],c['wall_seconds'],c['max_payload_bytes'],c['transient_disk_reserve_bytes'],c['transient_disk_margin_bytes'],c['codec_temp_budget_bytes']),(G,64,5400,12*G,10*G,2*G,8*G));self.assertEqual(auto.outer_wrapper_wall_seconds(p),5460)
 def test_runner_resolution_matches_auto(self):
  c=run_batch.resolve_batch_policy('storage-followup-codec','reversible-xz-v1-payload12',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE)
  self.assertEqual((c['max_bytes'],c['max_groups'],c['wall_seconds'],c['max_payload_bytes'],c['transient_disk_reserve_bytes'],c['transient_disk_margin_bytes'],c['codec_temp_budget_bytes']),(G,64,5400,12*G,10*G,2*G,8*G))
  self.assertEqual(batch_plan.codec_multigroup_disk_required_bytes(12345,c['max_bytes']),13*G+12345)
 def test_child_resolution_matches_runner(self):
  c=child.validate_storage_policy('storage-followup-codec','reversible-xz-v1-payload12',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE)
  self.assertEqual((c['max_bytes'],c['max_groups'],c['wall_seconds'],c['max_payload_bytes'],c['transient_disk_reserve_bytes'],c['transient_disk_margin_bytes'],c['codec_temp_budget_bytes']),(G,64,5400,12*G,10*G,2*G,8*G))
 def test_existing_profiles_remain_unchanged(self):
  self.assertEqual(auto.batch_config('reversible-xz-v1-payload12',batch_plan.CODEC_PAYLOAD12_PROFILE)['max_bytes'],4*G)
  self.assertEqual(auto.batch_config('reversible-xz-v1',batch_plan.CODEC_MULTIGROUP_PROFILE)['max_payload_bytes'],2*G)
 def test_mismatched_codec_pairs_fail(self):
  with self.assertRaises(ValueError):auto.batch_config('reversible-xz-v1',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE)
  with self.assertRaises(ValueError):run_batch.resolve_batch_policy('storage-followup-codec','reversible-xz-v1',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE)
  with self.assertRaises(ValueError):child.validate_storage_policy('storage-followup-codec','reversible-xz-v1',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE)
 def test_source_bound_archive_only_policy_and_fit_block(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);frozen,sm=make_policy_fixture(root);self.assertEqual(admission._codec12_narrow_policy(root,frozen)['profile'],'codec12_narrow')
   self.assertTrue(admission.native_codec_overlap_policy_allowed(root,frozen,archive_io_profile=batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1-payload12'))
   for kind in ('fit','eval'):
    task={'key':'e5/x','kind':kind};self.assertIsNone(admission.qualify_candidate(root,task,task,{},frozen))
   bad=dict(frozen);bad['source_sha256']=dict(sm,**{'controller.py':'0'*64})
   self.assertFalse(admission.native_codec_overlap_policy_allowed(root,bad,archive_io_profile=batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1-payload12'))
   qpath=root/'reports/engineering_audits/CODEC12_NARROW_ARCHIVE_ONLY_PREFLIGHT.json'
   original=json.loads(qpath.read_text());original['fixture_only']=False;qpath.write_bytes(canon(original))
   q=root/'reports/engineering_audits/ARCHIVE_NATIVE_CODEC12_NARROW_QUALIFICATION_20261030.json'
   qdoc=json.loads(q.read_text());qdoc['archive_only_preflight']['receipt_sha256']=sha(qpath);q.write_bytes(canon(qdoc))
   frozen[admission.CODEC12_NARROW_QUALIFICATION_FIELD]=sha(q)
   with self.assertRaises(ValueError):admission._codec12_narrow_policy(root,frozen)
 def test_controller_gate_blocks_all_kinds_and_archive_requires_zero_workers(self):
  controller=(HERE/'source/controller.py').read_text()
  self.assertEqual(sha(HERE/'source/controller.py'),'b6684a6031b47de96cce09d34db6ef01cc4a6b1f33ca68d026f7f38aef12c022')
  gate_start=controller.index('def _archive_fit_launch_gate')
  gate_end=controller.index('\ndef admission_candidate',gate_start)
  gate=controller[gate_start:gate_end]
  self.assertGreaterEqual(controller.count('_archive_fit_launch_gate('),3)
  self.assertIn('archive_fit_admission.qualify_candidate',gate)
  self.assertIn('if overlap is None:return False',gate)
  cold=(HERE/'source/cold_auto_compaction.py').read_text()
  self.assertIn("archive_io_profile in CODEC_ARCHIVE_IO_PROFILES and resource_doc['running']!=0",cold)
  self.assertIn('CODEC_PAYLOAD12_NARROW_PROFILE',cold)
  script=HERE/'source/cold_auto_compaction.py';argv=[str(Path(sys.executable)),str(script),'--storage-codec-policy','reversible-xz-v1-payload12','--archive-io-profile',batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE]
  self.assertTrue(admission.driver_command_matches(argv,python=Path(sys.executable),script=script,batch_policy='storage-followup-codec',storage_codec='reversible-xz-v1-payload12',io_profile=batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE))
  policy={'policy_id':'working-reserve-6gib-one-fit-v1','working_reserve_bytes':6*G,'maximum_restore_bytes':10*G,'maximum_single_restore_asset_bytes':G,'per_active_or_new_task_output_reserve_bytes':2*G,'maximum_concurrent_fit_tasks':1,'full_archive_verification':'finalization_only','restore_index_schema':'lamost-terminal-result-retention-index/2','restore_index_rel':'operations/retention_index.json'}
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);index=root/policy['restore_index_rel'];index.parent.mkdir(parents=True)
   index.write_text(json.dumps({'schema':policy['restore_index_schema'],'restore_required':True,'retired':[{'source_bytes':100,'asset_bytes':20}]}))
   index_sha=sha(index);required=policy['working_reserve_bytes']+120+policy['per_active_or_new_task_output_reserve_bytes']
   campaign={'policy_id':policy['policy_id'],'retention_index_path':policy['restore_index_rel'],'retention_index_sha256':index_sha,'retention_row_count':1,'retention_restore_bytes':100,'largest_restore_asset_bytes':20,'retention_restore_required':True}
   budget={'index_sha256':index_sha,'row_count':1,'restore_bytes':100,'largest_asset_bytes':20,'restore_required':True}
   obs={'policy_id':policy['policy_id'],'observed_utc':'2026-10-30T10:00:00+00:00','active_running_task_count':0,'admission_allowed':False,'free_bytes':required-1,'required_free_bytes':required,'restore_required':True,'restore_bytes_reserved':100,'largest_restore_asset_bytes_reserved':20,'working_reserve_bytes':policy['working_reserve_bytes'],'per_active_or_new_task_output_reserve_bytes':policy['per_active_or_new_task_output_reserve_bytes'],'full_archive_verification':'finalization_only','retention_index_matches_approved_campaign':True,'no_unique_artifacts_deleted':True,'retention_index_path':str(index),'retention_index_sha256':index_sha}
   self.assertTrue(auto._working_reserve_observation_valid(obs,policy,root,campaign,budget))
   trig,reason=auto.should_trigger_storage(obs,obs['free_bytes'],1793354400,storage_policy=policy,archive_io_profile=batch_plan.CODEC_PAYLOAD12_NARROW_PROFILE,runtime_root=root,approved_campaign=campaign,restore_budget=budget)
   self.assertTrue(trig);self.assertEqual(reason,'storage_below_controller_minimum')
   for field,value in [('required_free_bytes',required+1),('active_running_task_count',1),('retention_index_matches_approved_campaign',False),('retention_index_sha256','0'*64)]:
    bad=dict(obs);bad[field]=value;self.assertFalse(auto._working_reserve_observation_valid(bad,policy,root,campaign,budget))
   false_campaign=dict(campaign,retention_index_sha256='0'*64)
   self.assertFalse(auto._working_reserve_observation_valid(obs,policy,root,false_campaign,budget))
   bad_budget=dict(budget,row_count=2)
   self.assertFalse(auto._working_reserve_observation_valid(obs,policy,root,campaign,bad_budget))
   index.write_text(json.dumps({'schema':policy['restore_index_schema'],'restore_required':True,'retired':[{'source_bytes':101,'asset_bytes':20}]}))
   forged=dict(obs,retention_index_sha256=sha(index),restore_bytes_reserved=101,required_free_bytes=required+1)
   self.assertFalse(auto._working_reserve_observation_valid(forged,policy,root,campaign,budget))
   self.assertEqual(auto.should_trigger_storage(obs,obs['free_bytes'],1793354400)[1],'storage_observation_invalid')
   legacy={'observed_utc':'2026-10-30T10:00:00+00:00','minimum_free_bytes':100}
   self.assertEqual(auto.should_trigger_storage(legacy,99,1793354400),(True,'storage_below_controller_minimum'))

if __name__=='__main__':unittest.main()