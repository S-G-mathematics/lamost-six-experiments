import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

MOD=Path(__file__).parents[1]/"source"/"audit_artifacts.py"
spec=importlib.util.spec_from_file_location("staged_auditor",MOD)
auditor=importlib.util.module_from_spec(spec);spec.loader.exec_module(auditor)

class E4WeightSchemaAuditTests(unittest.TestCase):
    def cohort_fixture(self, include_weight=False):
        td=tempfile.TemporaryDirectory();rt=Path(td.name)
        (rt/"artifacts/cohort").mkdir(parents=True);(rt/"cache/roles").mkdir(parents=True)
        n=80000;original=np.arange(n,dtype=np.int64)%7
        counts=np.bincount(original,minlength=7); target=0; quota=int(np.floor(.5*counts[target]+.5))
        want=np.zeros(7,dtype=int);want[target]=quota
        left=n-quota; w=counts.astype(float);w[target]=0
        # Reproduce stable largest-remainder quotas for audit fixture.
        scaled=w*(left/w.sum());floors=np.floor(scaled).astype(int);want+=floors
        for i in np.argsort(-(scaled-floors),kind="stable")[:left-int(floors.sum())]:want[i]+=1
        y=np.repeat(np.arange(7),want).astype(np.int64);ids=np.arange(n,dtype=np.int64);X=np.zeros((n,6),dtype=np.float64)
        payload={"X":X,"y":y,"ids":ids}
        if include_weight:payload["sample_weight"]=np.ones(n,dtype=float)
        np.savez(rt/"artifacts/cohort/data.npz",**payload)
        np.savez(rt/"cache/roles/rep_1.npz",y_fit=original,tuning_ids=np.array([90001]),calibration_ids=np.array([90002]))
        meta={"target_class":0,"ratio":.5,"realized_counts":want.tolist(),"sample_weight_included":bool(include_weight)}
        (rt/"artifacts/cohort/metadata.json").write_text(json.dumps(meta))
        task={"key":"cohort","kind":"e4_cohort","rep":1,"target_class":0,"ratio":.5,"artifact_dir":"artifacts/cohort"}
        return td,rt,task,counts,want
    def test_unweighted_cohort_has_no_weight_array_and_metadata(self):
        td,rt,t,counts,want=self.cohort_fixture(False)
        try:
            a=auditor.Auditor(rt);a.e4_cohort_audit(t,{})
            self.assertEqual(a.issues,[])
        finally:td.cleanup()
    def test_untreated_cohort_weight_vector_is_rejected(self):
        td,rt,t,counts,want=self.cohort_fixture(True)
        try:
            a=auditor.Auditor(rt);a.e4_cohort_audit(t,{})
            checks={x["check"] for x in a.issues}
            self.assertIn("untreated_cohort_sample_weight",checks)
            self.assertIn("untreated_cohort_weight_metadata",checks)
        finally:td.cleanup()
    def treatment_fixture(self, treatment="weighted", corrupt_weight=False):
        td,rt,t,counts,want=self.cohort_fixture(False)
        base=rt/"artifacts/cohort"; by=np.asarray([2,3,3,3,3,3,3]); y=np.repeat(np.arange(7),by)
        orig=np.asarray([4,3,3,3,3,2,2],float); X=np.arange(len(y)*6,dtype=float).reshape(-1,6)
        np.savez(base/"data.npz",X=X,y=y,ids=np.arange(len(y)))
        (base/"metadata.json").write_text(json.dumps({"source_fit_counts":orig.tolist(),"added_count":2,"restore_added_count":2,"target_class":0}))
        out=rt/"artifacts/treatment";out.mkdir()
        if treatment=="weighted":
            w=(orig/orig.sum())/(by/by.sum());sw=w[y];sw/=sw.mean()
            if corrupt_weight:sw=np.ones(len(y))
            np.savez(out/"data.npz",X=X,y=y,ids=np.arange(len(y)),sample_weight=sw)
        else:
            yr=np.r_[y,np.zeros(2,dtype=int)];xr=np.r_[X,X[:2]]
            np.savez(out/"data.npz",X=xr,y=yr,ids=np.arange(len(yr)),sample_weight=np.ones(len(yr)))
        task={"key":"treatment","kind":"e4_treatment","rep":1,"target_class":0,"treatment":treatment,"cohort_key":"cohort","artifact_dir":"artifacts/treatment"}
        cohort_task=dict(t);return td,rt,task,cohort_task
    def test_explicit_weighted_arm_retains_expected_nonuniform_mean_one_weights(self):
        td,rt,t,ct=self.treatment_fixture()
        try:
            a=auditor.Auditor(rt);a.treatment_audit(t,{"cohort":ct})
            self.assertEqual(a.issues,[])
        finally:td.cleanup()
    def test_explicit_weighted_arm_rejects_uniform_weights(self):
        td,rt,t,ct=self.treatment_fixture(corrupt_weight=True)
        try:
            a=auditor.Auditor(rt);a.treatment_audit(t,{"cohort":ct})
            self.assertIn("weight_uniform",{x["check"] for x in a.issues})
            self.assertIn("weight_values",{x["check"] for x in a.issues})
        finally:td.cleanup()
    def test_generated_append_rejects_weight_array(self):
        td,rt,t,ct=self.treatment_fixture("ros")
        try:
            tdpath=rt/"artifacts/treatment/data.npz"
            with np.load(tdpath) as z:dat={k:z[k] for k in z.files}
            base=rt/"artifacts/append";base.mkdir()
            np.savez(base/"data.npz",**dat)
            task={"key":"append","kind":"e4_append","dependencies":["treatment"],"artifact_dir":"artifacts/append"}
            dep=dict(t,key="treatment",kind="e4_treatment",artifact_dir="artifacts/treatment")
            a=auditor.Auditor(rt);a.e4_append_audit(task,{"treatment":dep})
            self.assertIn("append_sample_weight",{x["check"] for x in a.issues})
        finally:td.cleanup()
    def test_nonweighted_treatment_rejects_weight_array(self):
        td,rt,t,ct=self.treatment_fixture("ros")
        try:
            a=auditor.Auditor(rt);a.treatment_audit(t,{"cohort":ct})
            self.assertIn("nonweighted_treatment_sample_weight",{x["check"] for x in a.issues})
        finally:td.cleanup()

if __name__=="__main__":unittest.main()
