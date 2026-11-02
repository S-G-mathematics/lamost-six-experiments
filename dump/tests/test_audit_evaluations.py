import os
import time
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

MOD=Path(__file__).parents[1]/"source"/"audit_artifacts.py"
spec=importlib.util.spec_from_file_location("audit_artifacts",MOD)
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class EvaluationAuditTests(unittest.TestCase):
    def fixture(self):
        td=tempfile.TemporaryDirectory();rt=Path(td.name)
        (rt/"cache/roles").mkdir(parents=True);(rt/"artifacts/eval").mkdir(parents=True)
        ids=np.arange(100,107,dtype=np.int64);y=np.arange(7,dtype=np.int8)
        X=np.zeros((7,6),dtype=np.float64)
        np.savez(rt/"cache/test.npz",X=X,y=y,ids=ids)
        role={"y_cal":np.array([0,1,2],dtype=np.int8),"fit_ids":np.array([1,2,3]),"calibration_ids":np.array([11,12,13])}
        np.savez(rt/"cache/roles/rep_1.npz",**role)
        cmanifest={"labels":list(audit.LABELS),"cache_files":{"test.npz":audit.sha256_file(rt/"cache/test.npz")}}
        (rt/"cache/cache_manifest.json").write_text(json.dumps(cmanifest))
        out=rt/"artifacts/eval";mask=(1<<y).astype(np.uint8);pred=y.copy();covered=np.ones(7,bool);size=np.ones(7,np.int64)
        np.savez(out/"test_outcomes.npz",sample_id=ids,y_pred=pred,set_mask=mask,covered=covered,set_size=size,fallback_mask=np.zeros(7,bool))
        per={str(c):{"n":1,"recall":1.0,"coverage":1.0,"set_size":1.0} for c in range(7)}
        metrics={"task_key":"eval","experiment":3,"repetition":1,"balanced_accuracy":1.0,"set_size":1.0,"coverage":1.0,
                 "per_class":per,"confusion_matrix":np.eye(7,dtype=int).tolist(),"calibration_n":3,"test_n":7,
                 "class_order":list(range(7)),"test_fallback_count":0}
        (out/"evaluation.json").write_text(json.dumps(metrics))
        files={"test_outcomes.npz":audit.sha256_file(out/"test_outcomes.npz"),"evaluation.json":audit.sha256_file(out/"evaluation.json")}
        validation={"status":"validated","files":files}
        (out/"validation.json").write_text(json.dumps(validation))
        task={"key":"eval","kind":"eval","rep":1,"artifact_dir":str(out),"result":{"result":metrics,"validation":validation}}
        return td,rt,task,ids,y
    def run_eval(self,fixture):
        td,rt,t,ids,y=fixture
        a=audit.Auditor(rt)
        a.evaluation_audit(t,{"eval":t},{"eval"})
        return a.issues
    def test_valid_metric_masks_ids_and_order(self):
        f=self.fixture()
        try:self.assertEqual(self.run_eval(f),[])
        finally:f[0].cleanup()
    def test_wrong_ids_and_order_are_reported(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;p=Path(t["artifact_dir"])/"test_outcomes.npz"
            with np.load(p) as z:d={k:z[k] for k in z.files}
            d["sample_id"]=ids[::-1];np.savez(p,**d)
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertIn("test_id_order",{x["check"] for x in a.issues})
        finally:f[0].cleanup()
    def test_wrong_prediction_labels_metrics_and_confusion(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;p=Path(t["artifact_dir"])/"test_outcomes.npz"
            with np.load(p) as z:d={k:z[k] for k in z.files}
            d["y_pred"]=np.roll(y,1);np.savez(p,**d)
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertTrue({"confusion_matrix","balanced_accuracy"}&{x["check"] for x in a.issues})
        finally:f[0].cleanup()
    def test_bad_bitmask_coverage_and_size(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;p=Path(t["artifact_dir"])/"test_outcomes.npz"
            with np.load(p) as z:d={k:z[k] for k in z.files}
            d["set_mask"][0]=np.uint8(2);np.savez(p,**d)
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertTrue({"mask_size","mask_coverage"}&{x["check"] for x in a.issues})
        finally:f[0].cleanup()
    def test_stored_overall_and_perclass_metrics_are_checked(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;ep=Path(t["artifact_dir"])/"evaluation.json";m=json.loads(ep.read_text())
            m["balanced_accuracy"]=.9;m["per_class"]["0"]["recall"]=.4;ep.write_text(json.dumps(m))
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            checks={x["check"] for x in a.issues}
            self.assertIn("balanced_accuracy",checks);self.assertIn("class_0_recall",checks)
        finally:f[0].cleanup()
    def test_alias_mismatch_is_reported_without_extra_physical_outcome(self):
        f=self.fixture()
        try:
            td,rt,src,ids,y=f;so=Path(src["artifact_dir"])
            ad=rt/"artifacts/alias";ad.mkdir()
            sm=json.loads((so/"evaluation.json").read_text())
            aliasm=dict(sm,task_key="alias",experiment=4,compute_reused=True,reused_from="eval")
            aliasm["coverage"]=.5;(ad/"evaluation.json").write_text(json.dumps(aliasm))
            ref={"source_key":"eval","source_evaluation_sha256":audit.sha256_file(so/"evaluation.json")}
            (ad/"artifact_ref.json").write_text(json.dumps(ref))
            files={"evaluation.json":audit.sha256_file(ad/"evaluation.json")}
            val={"status":"validated","files":files};(ad/"validation.json").write_text(json.dumps(val))
            t={"key":"alias","kind":"alias","source_key":"eval","artifact_dir":str(ad),"result":{"validation":val}}
            a=audit.Auditor(rt);paths,record=a.evaluation_audit(t,{"eval":src,"alias":t},{"eval","alias"},True)
            self.assertIn("alias_metrics_mismatch",{x["check"] for x in a.issues})
            self.assertFalse(record["physical_outcome"])
            self.assertTrue(any(str(p).endswith("test_outcomes.npz") for p in paths))
        finally:f[0].cleanup()
    def test_missing_fallback_mask_is_unknown_nonblocking_when_hashes_and_metrics_match(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f
            out=Path(t["artifact_dir"]);op=out/"test_outcomes.npz"
            with np.load(op) as z:d={k:z[k] for k in z.files if k!="fallback_mask"}
            np.savez(op,**d)
            files={"test_outcomes.npz":audit.sha256_file(op),"evaluation.json":audit.sha256_file(out/"evaluation.json")}
            validation={"status":"validated","files":files}
            (out/"validation.json").write_text(json.dumps(validation))
            t["result"]={"validation":validation,"result":json.loads((out/"evaluation.json").read_text())}
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertEqual(a.issues,[])
            self.assertEqual(len(a.diagnostics),1)
            self.assertEqual(a.diagnostics[0]["check"],"fallback_unknown")
            self.assertIn("No values were imputed",a.diagnostics[0]["evidence"])
        finally:f[0].cleanup()

    def test_missing_fallback_mask_remains_blocking_when_hash_mismatch(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;out=Path(t["artifact_dir"]);op=out/"test_outcomes.npz"
            with np.load(op) as z:d={k:z[k] for k in z.files if k!="fallback_mask"}
            np.savez(op,**d)
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertIn("fallback_missing",{x["check"] for x in a.issues})
            self.assertEqual(a.diagnostics,[])
        finally:f[0].cleanup()

    def test_present_fallback_mask_conflicting_count_is_blocking(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;out=Path(t["artifact_dir"]);op=out/"test_outcomes.npz"
            with np.load(op) as z:d={k:z[k] for k in z.files}
            d["fallback_mask"]=np.array([1,0,0,0,0,0,0],dtype=bool);np.savez(op,**d)
            m=json.loads((out/"evaluation.json").read_text());m["test_fallback_count"]=0
            (out/"evaluation.json").write_text(json.dumps(m))
            a=audit.Auditor(rt);a.evaluation_audit(t,{"eval":t},{"eval"})
            self.assertIn("fallback_count",{x["check"] for x in a.issues})
        finally:f[0].cleanup()

    def restoration_fixture(self):
        td,rt,t,ids,y=self.fixture()
        out=Path(t["artifact_dir"]); current=out/"test_outcomes.npz"
        with np.load(current) as z:cur={k:z[k] for k in z.files}
        core={k:cur[k] for k in ("sample_id","y_pred","set_mask","covered","set_size")}
        restored=rt/"artifacts"/"_restored_original_e3_containers"/"test_outcomes.original.npz";restored.parent.mkdir(parents=True)
        candidate=out/"diagnostic_baseline"/"test_outcomes_before_support_diagnostics.npz";candidate.parent.mkdir()
        np.savez(restored,**core);candidate.write_bytes(restored.read_bytes())
        cursha=audit.sha256_file(current);oldsha=audit.sha256_file(restored)
        oldresult=rt/"attempts"/"initial"/"worker_result.json";oldresult.parent.mkdir(parents=True)
        oldrequest=rt/"attempts"/"initial"/"request.json"
        latest=rt/"attempts"/"latest"/"worker_result.json";latest.parent.mkdir(parents=True)
        metrics=json.loads((out/"evaluation.json").read_text())
        metrics["threshold"]=0.3;metrics["score_kind"]="probability";(out/"evaluation.json").write_text(json.dumps(metrics))
        olddoc={"artifact_sha256":oldsha,"controller_attempt_id":"attempt0","key":"eval","result":metrics}
        oldresult.write_text(json.dumps(olddoc));oldrequest.write_text(json.dumps({"key":"eval"}))
        latest.write_text(json.dumps({"artifact_sha256":cursha,"key":"eval","result":metrics}))
        support=out/"support_diagnostic_baseline.json"
        support.write_text(json.dumps({"outcomes_path":str(candidate),"outcomes_sha256":oldsha,"evaluation":{"task_key":"eval"}}))
        (out/"validation.json").write_text(json.dumps({"files":{"test_outcomes.npz":cursha,"evaluation.json":audit.sha256_file(out/"evaluation.json")}}))
        t["attempts"]=[{"attempt_id":"attempt0","request_path":str(oldrequest),"result_path":str(oldresult)}]
        t["result_path"]=str(latest);t["result"]={"artifact_sha256":cursha}
        av={"original_members":list(core),"current_members":list(cur),"fallback_mask_omitted_only":True,
            "fallback_mask_shape":list(cur["fallback_mask"].shape),"fallback_true_count":int(np.count_nonzero(cur["fallback_mask"])),"old_zip_crc":"ok","current_zip_crc":"ok","member_order_preserved":True,
            "arrays":[{"name":n,"dtype":str(core[n].dtype),"shape":list(core[n].shape),"values_exact":True} for n in core]}
        item={"task_key":"eval","current_path":str(current),"restored_path":str(restored),"source_candidate_path":str(candidate),
              "support_diagnostic_baseline_path":str(support),"initial_worker_result_path":str(oldresult),"initial_request_path":str(oldrequest),
              "initial_attempt_id":"attempt0","old_expected_sha256":oldsha,"initial_worker_result_artifact_sha256":oldsha,
              "current_sha256":cursha,"restored_sha256":oldsha,"source_candidate_sha256":oldsha,
              "support_diagnostic_baseline_sha256":audit.sha256_file(support),"initial_worker_result_file_sha256":audit.sha256_file(oldresult),
              "initial_request_file_sha256":audit.sha256_file(oldrequest),"array_validation":av}
        return (td,rt,t,ids,y),item,metrics,current,latest
    def test_restoration_proof_validates_exact_shared_arrays(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f;a=audit.Auditor(rt)
            ok,info,paths=a._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertTrue(ok,info["errors"]);self.assertEqual(info["disposition"],"validated_supersession_only_fallback_mask_added")
        finally:f[0].cleanup()
    def test_restoration_proof_rejects_missing_or_wrong_fallback_true_count(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f
            a=audit.Auditor(rt);av=item["array_validation"];expected=av["fallback_true_count"]
            del av["fallback_true_count"]
            ok,info,_=a._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertIn("added fallback mask true-count mismatch",info["errors"])
            av["fallback_true_count"]=expected+1
            ok,info,_=a._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertIn("added fallback mask true-count mismatch",info["errors"])
            av["fallback_true_count"]=expected
        finally:f[0].cleanup()
    def test_restoration_proof_rejects_tampered_restored_hash(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f;Path(item["restored_path"]).write_bytes(Path(item["restored_path"]).read_bytes()+b"x")
            ok,info,_=audit.Auditor(rt)._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertTrue(any("restored/initial expected SHA chain" in e for e in info["errors"]))
        finally:f[0].cleanup()
    def test_restoration_proof_rejects_changed_core_member(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f
            with np.load(current) as z:d={k:z[k] for k in z.files}
            d["y_pred"][0]=1;np.savez(current,**d)
            sha=audit.sha256_file(current);item["current_sha256"]=sha;t["result"]["artifact_sha256"]=sha
            val=Path(t["artifact_dir"])/"validation.json";val.write_text(json.dumps({"files":{"test_outcomes.npz":sha}}))
            latest_doc=json.loads(latest.read_text());latest_doc["artifact_sha256"]=sha;latest.write_text(json.dumps(latest_doc))
            ok,info,_=audit.Auditor(rt)._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertTrue(any("core array mismatch" in e for e in info["errors"]))
        finally:f[0].cleanup()
    def test_restoration_proof_rejects_unexpected_current_member(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f
            with np.load(current) as z:d={k:z[k] for k in z.files}
            d["extra"]=np.array([1]);np.savez(current,**d)
            sha=audit.sha256_file(current);item["current_sha256"]=sha;t["result"]["artifact_sha256"]=sha
            val=Path(t["artifact_dir"])/"validation.json";doc=json.loads(val.read_text());doc["files"]["test_outcomes.npz"]=sha;val.write_text(json.dumps(doc))
            latest_doc=json.loads(latest.read_text());latest_doc["artifact_sha256"]=sha;latest.write_text(json.dumps(latest_doc))
            ok,info,_=audit.Auditor(rt)._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertTrue(any("unexpected NPZ member" in e for e in info["errors"]))
        finally:f[0].cleanup()
    def test_restoration_proof_rejects_latest_hash_mismatch(self):
        f,item,metrics,current,latest=self.restoration_fixture()
        try:
            td,rt,t,ids,y=f;latest_doc=json.loads(latest.read_text());latest_doc["artifact_sha256"]="0"*64;latest.write_text(json.dumps(latest_doc))
            ok,info,_=audit.Auditor(rt)._verify_restoration_entry(t,item,metrics,"manifestsha",True)
            self.assertFalse(ok);self.assertTrue(any("latest worker/registry artifact SHA mismatch" in e for e in info["errors"]))
        finally:f[0].cleanup()

    def test_file_hash_cache_invalidates_on_changed_file(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f;p=Path(t["artifact_dir"])/"test_outcomes.npz";a=audit.Auditor(rt)
            first=a.file_hash(p);p.write_bytes(p.read_bytes()+b"x");second=a.file_hash(p)
            self.assertNotEqual(first,second)
        finally:f[0].cleanup()


    def test_auditcache_invalidates_after_saved_outcome_changes(self):
        f=self.fixture()
        try:
            td,rt,t,ids,y=f
            t.update({"status":"validated_terminal","outcome":"successful"})
            (rt/"registry.json").write_text(json.dumps({"observed_utc":"fixture","tasks":[t]}))
            first=audit.Auditor(rt).run(evaluation_only=True)
            cache=json.loads((rt/"auditcache.json").read_text())
            sig1=cache["tasks"]["eval"]["signature"]
            p=Path(t["artifact_dir"])/"test_outcomes.npz"
            with np.load(p) as z:d={k:z[k] for k in z.files}
            d["y_pred"][0]=1;np.savez(p,**d)
            future=time.time()+2;os.utime(p,(future,future))
            second=audit.Auditor(rt).run(evaluation_only=True)
            cache=json.loads((rt/"auditcache.json").read_text())
            sig2=cache["tasks"]["eval"]["signature"]
            self.assertNotEqual(sig1,sig2)
            self.assertTrue(any(r["task_key"]=="eval" and r["status"]=="checked" for r in second["records"]))
            self.assertGreater(second["issue_count"],0)
        finally:f[0].cleanup()

if __name__=="__main__":unittest.main()
