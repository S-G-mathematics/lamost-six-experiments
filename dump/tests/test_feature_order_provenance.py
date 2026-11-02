import importlib.util,json,shutil,tempfile,unittest
from pathlib import Path

R=Path(__file__).resolve().parents[1]
FIX=R/"tests"/"fixtures"/"e6_feature_order_fix"
spec=importlib.util.spec_from_file_location("portable_e6_ensemble_feature_fix",R/"source"/"ensemble.py")
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class FrozenFeatureProvenanceTests(unittest.TestCase):
 def make_runtime(self):
  tmp=tempfile.TemporaryDirectory();rt=Path(tmp.name)
  (rt/"manifests").mkdir();(rt/"cache").mkdir()
  for name in ("E3_MANIFEST.json","E6_EXECUTION_OVERLAY_V2.json"):
   shutil.copy2(FIX/name,rt/"manifests"/name)
  shutil.copy2(FIX/"cache_manifest.json",rt/"cache"/"cache_manifest.json")
  return tmp,rt
 def expected(self,rt,order=None):
  e3=json.loads((rt/"manifests/E3_MANIFEST.json").read_text())
  return {"feature_order":list(order if order is not None else e3["features"]),
          "role_membership_sha256":e3["role_hashes"]["1"]["source_sha256"]}
 def test_legacy_unnamed_pipeline_uses_exact_hash_bound_manifest_and_role_metadata(self):
  tmp,rt=self.make_runtime()
  try:
   e3=json.loads((rt/"manifests/E3_MANIFEST.json").read_text())
   exp=self.expected(rt)
   order,basis,sha=engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{}, {})
   self.assertEqual(order,e3["features"])
   self.assertEqual(basis,"protocol_bound_E3_manifest_for_legacy_unnamed_pipeline")
   self.assertEqual(sha,engine._member_comparison_file_sha(rt/"manifests/E3_MANIFEST.json"))
  finally:tmp.cleanup()
 def test_embedded_pipeline_or_fit_result_order_must_match_frozen_manifest(self):
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);order=exp["feature_order"]
   self.assertEqual(engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{"feature_order":order},{})[1],
                    "embedded_feature_order_checked_against_frozen_manifests")
   bad=list(order);bad[0],bad[1]=bad[1],bad[0]
   with self.assertRaisesRegex(ValueError,"embedded pipeline"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{"feature_order":bad},{})
   with self.assertRaisesRegex(ValueError,"embedded fit_result"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{},{"feature_order":bad})
  finally:tmp.cleanup()
 def test_embedded_valid_order_is_still_bound_to_frozen_manifests(self):
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);order=exp["feature_order"]
   got=engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{"feature_order":order},{})
   self.assertEqual(got,(order,"embedded_feature_order_checked_against_frozen_manifests",engine._member_comparison_file_sha(rt/"manifests/E3_MANIFEST.json")))
  finally:tmp.cleanup()
 def test_missing_manifest_wrong_source_hash_reordered_overlay_and_role_mismatch_fail(self):
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);e3path=rt/"manifests/E3_MANIFEST.json";overlay=rt/"manifests/E6_EXECUTION_OVERLAY_V2.json"
   e3path.unlink()
   with self.assertRaisesRegex(ValueError,"missing frozen feature provenance"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{}, {})
  finally:tmp.cleanup()
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);op=rt/"manifests/E6_EXECUTION_OVERLAY_V2.json";doc=json.loads(op.read_text());doc["source_e3_manifest_sha256"]="0"*64;op.write_text(json.dumps(doc))
   with self.assertRaisesRegex(ValueError,"not bound"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{}, {})
  finally:tmp.cleanup()
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);bad=list(exp["feature_order"]);bad.reverse();exp["feature_order"]=bad
   with self.assertRaisesRegex(ValueError,"overlay/cache feature order"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{}, {})
  finally:tmp.cleanup()
  tmp,rt=self.make_runtime()
  try:
   exp=self.expected(rt);exp["role_membership_sha256"]="0"*64
   with self.assertRaisesRegex(ValueError,"role membership"):
    engine._e6_v2_feature_order_provenance(rt,{"rep":1},"gmm",exp,{}, {})
  finally:tmp.cleanup()
if __name__=="__main__":unittest.main()
