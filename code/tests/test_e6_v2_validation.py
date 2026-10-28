import hashlib,json,tempfile,unittest
from pathlib import Path
import numpy as np
import e6_v2_validation as v

def file_sha(p): return v.sha_file(p)
def posterior(y,p=.8,shift=0):
    y=np.asarray(y,dtype=int); s=np.full((len(y),7),(1-p)/6,dtype=np.float64)
    s[np.arange(len(y)),(y+shift)%7]=p
    return s
def write_npz(p,**kw):
    p.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(p,**kw)
def receipt(stage,p,scores,fp):
    return {"schema_version":"lamost-e6-posterior-cache-receipt/1","stage":stage,"fingerprint":fp,
       "fingerprint_sha256":hashlib.sha256(json.dumps(fp,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
       "posterior_file_sha256":file_sha(p),"row_count":len(next(iter(scores.values()))),
       "member_order":list(v.MEMBERS),"posterior_sha256":{m:v.array_sha(scores[m]) for m in v.MEMBERS}}
def metrics(scores,y,q):
    return v._metrics(scores,y,q)
def fixture(root):
    rt=Path(root); (rt/'artifacts').mkdir(); (rt/'cache/roles').mkdir(parents=True); (rt/'cache').mkdir(exist_ok=True)
    fitids=np.arange(14,dtype=np.int64); tuneids=np.arange(100,114,dtype=np.int64); calids=np.arange(200,214,dtype=np.int64); testids=np.arange(300,314,dtype=np.int64)
    y=np.tile(np.arange(7,dtype=np.int8),2); X=np.arange(84,dtype=np.float64).reshape(14,6)/10
    write_npz(rt/'cache/roles/rep_1.npz',fit_ids=fitids,tuning_ids=tuneids,calibration_ids=calids,
       X_tune=X,y_tune=y,X_cal=X+.1,y_cal=y)
    write_npz(rt/'cache/test.npz',ids=testids,X=X+.2,y=y)
    models={m:('0'*63+str(i+1)) for i,m in enumerate(v.MEMBERS)}
    evid={m:{"fit_ids_sha256":v.array_sha(fitids),"role_membership_sha256":"rolehash",
       "selection_sha256":"sel-"+m,"fit_result_sha256":"fr-"+m,"validation_sha256":"val-"+m,
       "selected_params_sha256":"par-"+m,"provenance_group":"e3_new_fit"} for m in v.MEMBERS}
    fp={"pipeline_sha256":models,"fit_ids_sha256":v.array_sha(fitids),"tuning_ids_sha256":v.array_sha(tuneids),
       "calibration_ids_sha256":v.array_sha(calids),"test_ids_sha256":v.array_sha(testids),
       "X_tune_sha256":v.array_sha(X),"X_cal_sha256":v.array_sha(X+.1),"X_test_sha256":v.array_sha(X+.2),
       "y_tune_sha256":v.array_sha(y),"y_cal_sha256":v.array_sha(y),"y_test_sha256":v.array_sha(y),
       "member_fit_evidence":evid}
    sig=hashlib.sha256(json.dumps(fp,sort_keys=True).encode()).hexdigest()[:24]
    shared=rt/'cache/e6_posteriors/rep_1'/sig
    stages={}
    for stage, yy, p in (("tune",y,.8),("cal",y,.8),("test",y,.8)):
        scores={m:posterior(yy,p,0 if m=="gmm" else 0) for m in v.MEMBERS}
        path=shared/(stage+'.npz'); write_npz(path,**scores)
        (shared/(stage+'.receipt.json')).write_text(json.dumps(receipt(stage,path,scores,fp),sort_keys=True))
        stages[stage]=scores
    out=rt/'artifacts/e6/rep_1/ensemble/equal'; out.mkdir(parents=True)
    write_npz(out/'tuning_posteriors.npz',**{m+'_posterior':stages['tune'][m] for m in v.MEMBERS},y_tune=y,tuning_ids=tuneids)
    qs={m:v._q(stages['cal'][m],y) for m in v.MEMBERS}
    member_rows={}
    for m in v.MEMBERS:
        member_rows[m]={"fit_key":"e3/rep_1/fit/"+m,"pipeline_sha256":models[m],**evid[m],
          "score_kind":"probability","alpha":.1,"calibration_n":14,"test_n":14,
          "calibration_threshold":qs[m],"evaluation":{k:metrics(stages['test'][m],y,qs[m])[k] for k in ("balanced_accuracy","coverage","set_size","per_class")},
          "confusion_matrix":metrics(stages['test'][m],y,qs[m])["confusion_matrix"]}
    weights=[.2]*5; mixcal=sum(weights[i]*stages['cal'][m] for i,m in enumerate(v.MEMBERS)); qmix=v._q(mixcal,y)
    mixtest=sum(weights[i]*stages['test'][m] for i,m in enumerate(v.MEMBERS)); em=metrics(mixtest,y,qmix)
    doc={"schema_version":v.SCHEMA,"protocol_version":"E6-v2","rep":1,"comparison_source_task_key":"e6/rep_1/ensemble/equal",
      "mode":"equal","member_order":list(v.MEMBERS),"members":member_rows,"posterior_fingerprint":fp,
      "fit_ids_sha256":v.array_sha(fitids),"tuning_ids_sha256":v.array_sha(tuneids),"calibration_ids_sha256":v.array_sha(calids),"test_ids_sha256":v.array_sha(testids),
      "score_rule":v.SCORE_RULE,"quantile_rule":v.QUANTILE_RULE,"weights_frozen_utc":"2026-10-27T00:00:00Z",
      "weights_frozen_before_calibration_and_test":True,"tuning_best_member":"gmm","tuning_best_balanced_accuracy":1.,
      "selected_weights":weights,"candidate_ledger_path":None,"candidate_ledger_sha256":None,
      "ensemble_threshold":qmix,"ensemble_evaluation":{k:em[k] for k in ("balanced_accuracy","coverage","set_size","per_class")},
      "ensemble_confusion_matrix":em["confusion_matrix"]}
    sp=out/'member_comparisons.json';sp.write_text(json.dumps(doc,sort_keys=True))
    ev={"e6_protocol_version":"E6-v2","member_comparisons_path":"member_comparisons.json","member_comparisons_sha256":file_sha(sp),
      "posterior_cache_key":sig,"pipeline_sha256":models,"weights":weights,"conformal_threshold":qmix,
      "fit_ids_sha256":v.array_sha(fitids),"tuning_ids_sha256":v.array_sha(tuneids),
      "calibration_ids_sha256":v.array_sha(calids),"test_ids_sha256":v.array_sha(testids),
      "balanced_accuracy":em["balanced_accuracy"],"coverage":em["coverage"],"set_size":em["set_size"]}
    packed=np.packbits(em["sets"],axis=1,bitorder="little")[:,0]
    outcomes={"y_pred":em["predictions"],"set_mask":packed,"covered":em["covered"],"set_size":em["set_sizes"]}
    task={"kind":"ensemble","experiment":6,"e6_protocol_version":"E6-v2","key":"e6/rep_1/ensemble/equal","rep":1,"mode":"equal",
      "members":{"gmm":"e3/rep_1/fit/gmm","copula":"e3/rep_1/fit/copula","arf":"e3/rep_1/fit/arf","kde":"e3/rep_1/fit/kde","chow_liu":"e3/rep_1/fit/chow_liu"},
      "member_fit_evidence":evid}
    return rt,task,ev,outcomes,doc,shared,fp

class SavedCacheValidationTests(unittest.TestCase):
    def runfixture(self, mutate=None):
        with tempfile.TemporaryDirectory() as d:
            rt,task,ev,out,doc,shared,fp=fixture(d)
            if mutate: mutate(rt,task,ev,out,doc,shared,fp)
            return v.validate_e6_v2_saved_outputs(rt,task,ev,out,expected_fit_rows=14,expected_tune_rows=14,expected_cal_rows=14,expected_test_rows=14)
    def test_valid_cache_recomputes_all_member_and_ensemble_outputs(self):
        r=self.runfixture()
        self.assertEqual(r["status"],"validated",r["issues"])
        self.assertEqual(r["member_q_recomputed_from_saved_calibration_scores"],5)
        self.assertEqual(r["member_test_metrics_recomputed_from_saved_test_posteriors"],5)
    def test_wrong_member_q_is_rejected_even_when_sidecar_hash_updates(self):
        def m(rt,t,e,o,d,s,f):
            d["members"]["kde"]["calibration_threshold"]+=.02
            p=rt/"artifacts"/t["key"]/"member_comparisons.json";p.write_text(json.dumps(d,sort_keys=True));e["member_comparisons_sha256"]=file_sha(p)
        r=self.runfixture(m);self.assertEqual(r["status"],"invalid");self.assertIn("saved calibration posterior",r["issues"][0]["evidence"])
    def test_wrong_class_order_is_rejected(self):
        def m(rt,t,e,o,d,s,f): d["member_order"]=list(reversed(v.MEMBERS));p=rt/"artifacts"/t["key"]/"member_comparisons.json";p.write_text(json.dumps(d));e["member_comparisons_sha256"]=file_sha(p)
        r=self.runfixture(m);self.assertEqual(r["status"],"invalid")
    def test_role_identity_mismatch_is_rejected(self):
        def m(rt,t,e,o,d,s,f):
            with np.load(rt/'cache/roles/rep_1.npz') as z: arr={k:z[k] for k in z.files}
            arr["calibration_ids"]=arr["calibration_ids"]+1000;write_npz(rt/'cache/roles/rep_1.npz',**arr)
        r=self.runfixture(m);self.assertEqual(r["status"],"invalid");self.assertIn("fingerprint role/test mismatch",r["issues"][0]["evidence"])
    def test_modified_cache_fails_receipt_check(self):
        def m(rt,t,e,o,d,s,f):
            p=s/"test.npz"
            with np.load(p) as z: arr={k:z[k] for k in z.files}
            arr["gmm"][0,0]+=0.01;write_npz(p,**arr)
        r=self.runfixture(m);self.assertEqual(r["status"],"invalid");self.assertIn("receipt",r["issues"][0]["evidence"])
    def test_modified_member_test_metric_fails_recomputation(self):
        def m(rt,t,e,o,d,s,f):
            d["members"]["copula"]["evaluation"]["coverage"]=0.0
            p=rt/"artifacts"/t["key"]/"member_comparisons.json";p.write_text(json.dumps(d,sort_keys=True));e["member_comparisons_sha256"]=file_sha(p)
        r=self.runfixture(m);self.assertEqual(r["status"],"invalid");self.assertIn("coverage",r["issues"][0]["evidence"])
    def test_native_member_q_proof_is_content_addressed_and_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            vec=np.array([.1,.2,.3],dtype=np.float64)
            ident={"fit_key":"e3/rep_1/fit/gmm","pipeline_sha256":"p","role_file_sha256":"r","calibration_ids_sha256":"c","X_cal_sha256":"x","y_cal_sha256":"y"}
            md={"threshold":.2,"rank_k":2,"score_kind":"probability","nonconformity_rule":"1-p_true","alpha":.1,"class_order":list(range(7))}
            proof=v.persist_native_nonconformity(d,ident,vec,md)
            again=v.persist_native_nonconformity(d,ident,vec,md)
            self.assertEqual(proof,again)
            path=Path(d)/proof["nonconformity_path"]
            with np.load(path,allow_pickle=False) as z:self.assertTrue(np.array_equal(z["nonconformity"],vec))
            with path.open("ab") as f:f.write(b"tamper")
            with self.assertRaises(ValueError):v.persist_native_nonconformity(d,ident,vec,md)
if __name__=="__main__": unittest.main()
