from __future__ import annotations
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'source'))
import batch_plan
import cold_auto_compaction as auto
import run_batch
import commit_batch_child as child
import archive_fit_admission as admission

class CodecPayload12ProfileTests(unittest.TestCase):
 def test_new_profile_uses_existing_codec4_resource_envelope(self):
  p=batch_plan.CODEC_PAYLOAD12_PROFILE
  self.assertEqual(p,'bounded-5400-codec4gib64-payload12')
  self.assertEqual(batch_plan.CODEC_LARGE_PROFILE,'bounded-5400-codec4gib64')
  self.assertEqual((batch_plan.CODEC_PAYLOAD12_MAX_BYTES,batch_plan.CODEC_PAYLOAD12_MAX_GROUPS,batch_plan.CODEC_PAYLOAD12_TEMP_MAX_BYTES,batch_plan.CODEC_PAYLOAD12_WALL_SECONDS),(4<<30,64,8<<30,5400))
  self.assertEqual(batch_plan.CODEC_PAYLOAD12_MAX_PAYLOAD_BYTES,12<<30)
  self.assertEqual(auto.outer_wrapper_wall_seconds(p),5460)
  self.assertEqual(batch_plan.CODEC_ARCHIVE_IO_PROFILES,(batch_plan.CODEC_MULTIGROUP_PROFILE,batch_plan.CODEC_LARGE_PROFILE,p))
  self.assertIn('reversible-xz-v1-payload12',(HERE/'source'/'cold_auto_compaction.py').read_text())

 def test_policy_cap_explicit_and_legacy_stays_two_gib(self):
  p=batch_plan.CODEC_PAYLOAD12_PROFILE
  new=auto.batch_config('reversible-xz-v1-payload12',p);old=auto.batch_config('reversible-xz-v1',batch_plan.CODEC_LARGE_PROFILE)
  self.assertEqual(new['max_payload_bytes'],12<<30);self.assertEqual(new['storage_codec_policy'],'reversible-xz-v1-payload12')
  self.assertEqual(old.get('max_payload_bytes',2<<30),2<<30);self.assertEqual((old['max_bytes'],old['max_groups'],old['codec_temp_budget_bytes'],old['wall_seconds']),(4<<30,64,8<<30,5400))

 def test_wrong_profile_policy_pairs_fail_closed(self):
  p=batch_plan.CODEC_PAYLOAD12_PROFILE
  for codec,profile in [('reversible-xz-v1',p),('reversible-xz-v1-payload12',batch_plan.CODEC_LARGE_PROFILE),('reversible-xz-v1-payload12','unknown')]:
   with self.subTest(codec=codec,profile=profile),self.assertRaises(ValueError):auto.batch_config(codec,profile)

 def test_runner_resolver_keeps_legacy_and_selects_exact_cap(self):
  p=batch_plan.CODEC_PAYLOAD12_PROFILE
  new=run_batch.resolve_batch_policy('storage-followup-codec','reversible-xz-v1-payload12',p)
  old=run_batch.resolve_batch_policy('storage-followup-codec','reversible-xz-v1',batch_plan.CODEC_LARGE_PROFILE)
  self.assertEqual((new['max_bytes'],new['max_groups'],new['wall_seconds'],new['codec_temp_budget_bytes'],new['max_payload_bytes']),(4<<30,64,5400,8<<30,12<<30))
  self.assertEqual(old.get('max_payload_bytes',2<<30),2<<30)
  with self.assertRaises(ValueError):run_batch.resolve_batch_policy('storage-followup-codec','reversible-xz-v1-payload12',None)
  argv=[str(HERE.parent/'venv/bin/python'),str(HERE/'source/cold_auto_compaction.py'),'--storage-codec-policy','reversible-xz-v1-payload12','--archive-io-profile',p]
  self.assertTrue(admission.driver_command_matches(argv,python=HERE.parent/'venv/bin/python',script=HERE/'source/cold_auto_compaction.py',batch_policy='storage-followup-codec',storage_codec='reversible-xz-v1-payload12',io_profile=p))
  self.assertFalse(admission.driver_command_matches(argv,python=HERE.parent/'venv/bin/python',script=HERE/'source/cold_auto_compaction.py',batch_policy='storage-followup-codec',storage_codec='reversible-xz-v1',io_profile=p))

 def test_child_resolver_requires_profile_and_agrees_with_runner(self):
  p=batch_plan.CODEC_PAYLOAD12_PROFILE
  cfg=child.validate_storage_policy('storage-followup-codec','reversible-xz-v1-payload12',p)
  self.assertEqual((cfg['max_bytes'],cfg['max_groups'],cfg['wall_seconds'],cfg['codec_temp_budget_bytes'],cfg['max_payload_bytes']),(4<<30,64,5400,8<<30,12<<30))
  with self.assertRaises(ValueError):child.validate_storage_policy('storage-followup-codec','reversible-xz-v1-payload12',None)
  legacy=child.validate_storage_policy('storage-followup-codec','reversible-xz-v1',batch_plan.CODEC_LARGE_PROFILE)
  self.assertEqual(legacy['max_bytes'],4<<30)

 def test_disk_formula_and_codec_gate_are_unmodified_and_fail_closed(self):
  self.assertEqual(batch_plan.codec_multigroup_disk_required_bytes(123,4<<30),(4<<30)+(14<<30)+(2<<30)+123)
  self.assertFalse(admission.native_codec_overlap_policy_allowed(HERE,{},archive_io_profile=batch_plan.CODEC_PAYLOAD12_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1-payload12'))
  self.assertFalse(admission.native_codec_overlap_policy_allowed(HERE,{},archive_io_profile=batch_plan.CODEC_LARGE_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1-payload12'))

 def test_unqualified_policy_never_enables_overlap(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);target=root/admission.CODEC12_POLICY_REL;target.parent.mkdir(parents=True)
   doc={'schema':'lamost-archive-native-codec-payload12-fit-overlap-policy/1','status':'unqualified','policy_id':admission.CODEC12_POLICY_ID}
   raw=(json.dumps(doc,sort_keys=True,separators=(',',':'))+'\n').encode();target.write_bytes(raw)
   frozen={admission.CODEC12_POLICY_FIELD:hashlib.sha256(raw).hexdigest(),admission.CODEC12_QUALIFICATION_FIELD:'a'*64}
   with self.assertRaisesRegex(ValueError,'codec12_policy_not_qualified'):admission._codec12_policy(root,frozen)

 def test_missing_freeze_binding_stays_disabled(self):
  self.assertIsNone(admission._codec12_policy(HERE,{}))
  self.assertFalse(admission.native_codec_overlap_policy_allowed(HERE,{},archive_io_profile=batch_plan.CODEC_PAYLOAD12_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1'))
  # Missing freeze pointers must remain disabled independently of the staged policy state.
  self.assertFalse(admission.native_codec_overlap_policy_allowed(HERE,{},archive_io_profile=batch_plan.CODEC_PAYLOAD12_PROFILE,batch_policy='storage-followup-codec',storage_codec_policy='reversible-xz-v1-payload12'))
if __name__=='__main__':unittest.main()
