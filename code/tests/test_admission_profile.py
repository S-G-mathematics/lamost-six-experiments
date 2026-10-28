import importlib.util
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("admission_evidence",HERE/"source"/"admission_evidence.py")
ae=importlib.util.module_from_spec(spec);spec.loader.exec_module(ae)

class E4GeneratedRFProfileTests(unittest.TestCase):
    def case(self,generator="arf",added=1000,rows=80000):
        rep=1;base="A_half";treatment="generated_"+generator;cond=base+"_"+treatment
        key=f"e4/rep_{rep}/fit/treatment/random_forest/{cond}"
        train=f"e4/rep_{rep}/append/{base}/{generator}"
        parent=f"e4/rep_{rep}/cohort/{base}"
        definition={"key":key,"experiment":4,"rep":rep,"kind":"fit","method":"random_forest","route":"treatment",
          "condition":cond,"treatment":treatment,"generator":generator,"train_key":train,"dependencies":[train],
          "selection_mode":"tune","selection_policy":"tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget",
          "selection_key":None,"selection_source":None,"trials":10,"seed":12,"optimizer_seed":34}
        task=dict(definition,status="planned",attempts=[])
        before=[12000,12000,12000,12000,12000,10000,10000]
        before[0]=80000-sum(before[1:])
        after=list(before);after[0]+=added
        total=sum(after)
        metadata={"task_key":parent,"kind":"e4_cohort","rep":rep,"condition":base,"N":80000,
          "tune_calibration_reserved":True,"sample_weight_included":False,"target_class":0,
          "realized_counts":before,"source_fit_counts":before}
        metadata["source_fit_counts"]=before
        append={"kind":"e4_append","task_key":train,"rep":rep,"parent":str(pathlib.Path("/fixture/artifacts")/parent),
          "generated_artifact":str(pathlib.Path("/fixture/artifacts")/f"e4/rep_{rep}/generate/{base}/{generator}"),
          "counts_before":before,"counts_after":after,"added_count":added,"target_class":0}
        shapes={"X":(total,6),"y":(total,),"ids":(total,)}
        cohort_shapes={"X":(80000,6),"y":(80000,),"ids":(80000,)}
        return task,definition,metadata,append,shapes,cohort_shapes
    def run_case(self,**kwargs):
        task,definition,metadata,append,shapes,cohort_shapes=self.case(**kwargs)
        with mock.patch.object(ae,"_valid_cohort",return_value=True), \
             mock.patch.object(ae,"_json",return_value=metadata), \
             mock.patch.object(ae,"_valid_npz_artifact",side_effect=lambda root,key:(metadata,cohort_shapes) if key.endswith("/cohort/A_half") else (append,shapes)), \
             mock.patch.object(ae,"_e4_generated_rf_role_context",return_value={"role_cache_sha256":"r","fit_counts":[12000,12000,12000,12000,12000,10000,10000]}), \
             mock.patch.object(ae,"_e4_generated_rf_review_provenance",return_value={"audit_sha256":"a"}), \
             mock.patch.object(ae,"_e4_generated_rf_generated_artifact_valid",return_value={"generation_rows":kwargs.get("added",1000)}):
            return ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,pathlib.Path("/fixture"))
    def test_actual_v2_receipt_schema_and_append_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            audit_rel=pathlib.Path(ae.E4_GENERATED_RF_6G_AUDIT_PATH)
            receipt_rel=pathlib.Path(ae.E4_GENERATED_RF_6G_RECEIPT_PATH)
            for rel in (audit_rel,receipt_rel):
                dest=root/rel;dest.parent.mkdir(parents=True,exist_ok=True)
                source=HERE/"tests"/"evidence"/rel.name.replace("_V2_RECEIPTS","_V2_RECEIPTS").replace(".json",".json")
                if rel.name.endswith("_V2.json"): source=HERE/"tests"/"evidence"/"E4_GENERATED_RF_ADMISSION_REVIEW_20261027_V2.json"
                else: source=HERE/"tests"/"evidence"/"E4_GENERATED_RF_ADMISSION_REVIEW_20261027_V2_RECEIPTS.json"
                shutil.copyfile(source,dest)
            fit="e4/rep_1/fit/treatment/random_forest/G_half_generated_arf"
            train="e4/rep_1/append/G_half/arf"
            for name in ("metadata.json","validation.json"):
                dest=root/"artifacts"/train/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(HERE/"tests"/"fixtures"/"v2_append_proof"/name,dest)
            proof=ae._e4_generated_rf_review_provenance(root,fit,train)
            self.assertIsNotNone(proof)
            self.assertEqual(proof["file_manifest_sha256"],ae.E4_GENERATED_RF_6G_FILE_MANIFEST_SHA256)
            (root/receipt_rel).write_bytes((root/receipt_rel).read_bytes()+b" ")
            self.assertIsNone(ae._e4_generated_rf_review_provenance(root,fit,train))
    def test_generated_artifact_shape_and_fit_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);base="A_half";generator="arf";rep=1;n=3;target=0
            key=f"e4/rep_{rep}/generate/{base}/{generator}"
            fit=f"e4/rep_{rep}/fit/direct/{generator}/{base}"
            cohort=f"e4/rep_{rep}/cohort/{base}"
            outdir=root/"artifacts"/key;outdir.mkdir(parents=True)
            import numpy as np, json, hashlib
            data=outdir/"data.npz"
            np.savez_compressed(data,X=np.zeros((n,6)),y=np.zeros(n,dtype=np.int8))
            digest=hashlib.sha256(data.read_bytes()).hexdigest()
            task={"key":key,"experiment":4,"rep":rep,"kind":"generate","generator":generator,
              "condition":base,"cohort_key":cohort,"fit_key":fit,"target_class":target,
              "restored_share":"original_target_share","added_count":n,"seed":91}
            result={"status":"successful","task":task,"result":{"status":"success","n_rows":n,
              "generation_seed":91,"class_counts":[n,0,0,0,0,0,0],"data_sha256":digest}}
            validation={"status":"validated","task_key":key,"files":{"data.npz":digest}}
            (outdir/"generation_result.json").write_text(json.dumps(result))
            (outdir/"validation.json").write_text(json.dumps(validation))
            fitdir=root/"artifacts"/fit;fitdir.mkdir(parents=True)
            params={"family":"fixture"}
            fitresult={"task":{"kind":"fit","route":"direct","selection_mode":"tune","trials":5,
              "selection_policy":"tune_on_matching_altered_cohort","seed":1,"optimizer_seed":2},
              "result":{"params":params,"training_rows":80000}}
            (fitdir/"fit_result.json").write_text(json.dumps(fitresult))
            (fitdir/"selection.json").write_text(json.dumps({"selected_params":params}))
            (fitdir/"validation.json").write_text(json.dumps({"files":{"selection.json":hashlib.sha256((fitdir/"selection.json").read_bytes()).hexdigest()}}))
            with mock.patch.object(ae,"_valid_published_fit",return_value=True):
                evidence=ae._e4_generated_rf_generated_artifact_valid(root,{},rep,base,generator,target,n)
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence["generation_rows"],n)
    def test_all_five_generator_families_eligible(self):
        for method in ("gmm","copula","arf","kde","chow_liu"):
            with self.subTest(method=method):
                ok,evidence=self.run_case(generator=method)
                self.assertTrue(ok);self.assertEqual(evidence["reservation_gib"],6);self.assertEqual(evidence["generator"],method)
    def test_observed_row_boundary_is_inclusive(self):
        ok,evidence=self.run_case(added=45934)
        self.assertTrue(ok);self.assertEqual(evidence["training_rows"],125934)
    def test_row_above_observed_boundary_rejected(self):
        ok,_=self.run_case(added=45935)
        self.assertFalse(ok)
    def test_unknown_generator_rejected(self):
        ok,_=self.run_case(generator="not_a_family")
        self.assertFalse(ok)
    def test_prior_attempt_rejected(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case()
        task["attempts"]=[{"attempt_id":"old"}]
        with mock.patch.object(ae,"_valid_cohort",return_value=True):
            ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,"/fixture")
        self.assertFalse(ok)
    def test_existing_reservation_rejected(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case()
        task["admission_reservation_bytes"]=6*ae.GIB
        ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,"/fixture")
        self.assertFalse(ok)
    def test_task_definition_mismatch_rejected(self):
        task,definition,*_=self.case();task["route"]="direct"
        ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,"/fixture")
        self.assertFalse(ok)
    def test_missing_append_validation_rejected(self):
        task,definition,*_=self.case()
        with mock.patch.object(ae,"_valid_cohort",return_value=True), \
             mock.patch.object(ae,"_valid_npz_artifact",return_value=None):
            ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,"/fixture")
        self.assertFalse(ok)
    def test_target_class_mismatch_rejected(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case()
        metadata["target_class"]=1
        with mock.patch.object(ae,"_valid_cohort",return_value=True), \
             mock.patch.object(ae,"_json",return_value=metadata), \
             mock.patch.object(ae,"_valid_npz_artifact",side_effect=lambda root,key:(metadata,cohort_shapes) if key.endswith("/cohort/A_half") else (append,shapes)), \
             mock.patch.object(ae,"_e4_generated_rf_role_context",return_value={"fit_counts":metadata["source_fit_counts"]}), \
             mock.patch.object(ae,"_e4_generated_rf_review_provenance",return_value={"audit_sha256":"a"}), \
             mock.patch.object(ae,"_e4_generated_rf_generated_artifact_valid",return_value={"generation_rows":1000}):
            ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,pathlib.Path("/fixture"))
        self.assertFalse(ok)
    def test_append_shape_mismatch_rejected(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case()
        bad_shapes={"X":(81001,6),"y":(81001,),"ids":(81001,)}
        with mock.patch.object(ae,"_valid_cohort",return_value=True), \
             mock.patch.object(ae,"_json",return_value=metadata), \
             mock.patch.object(ae,"_valid_npz_artifact",side_effect=lambda root,key:(metadata,cohort_shapes) if key.endswith("/cohort/A_half") else (append,bad_shapes)), \
             mock.patch.object(ae,"_e4_generated_rf_role_context",return_value={"fit_counts":metadata["source_fit_counts"]}), \
             mock.patch.object(ae,"_e4_generated_rf_review_provenance",return_value={"audit_sha256":"a"}), \
             mock.patch.object(ae,"_e4_generated_rf_generated_artifact_valid",return_value={"generation_rows":1000}):
            ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,pathlib.Path("/fixture"))
        self.assertFalse(ok)
    def test_generic_profile_dispatch_includes_new_gate(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case(added=45934)
        evidence={"profile_id":ae.E4_GENERATED_RF_6G_PROFILE_ID,"reservation_gib":6}
        with mock.patch.object(ae,"_eligible_e4_weighted_rf_5g",return_value=(False,None)), \
             mock.patch.object(ae,"_eligible_arf_6g",return_value=(False,None)), \
             mock.patch.object(ae,"_eligible_e4_treatment_rf_fit_5gib",return_value=(False,None)), \
             mock.patch.object(ae,"_eligible_e4_treatment_rf_6gib",return_value=(False,None)), \
             mock.patch.object(ae,"_eligible_e4_generated_restoration_rf_6gib",return_value=(True,evidence)):
            ok,result=ae.eligible_rf_resource_profiles(task,definition,pathlib.Path("/fixture"))
        self.assertTrue(ok);self.assertEqual(result,evidence)
    def test_wrong_generator_identity_rejected(self):
        task,definition,metadata,append,shapes,cohort_shapes=self.case(generator="arf")
        task["generator"]="kde"
        with mock.patch.object(ae,"_valid_cohort",return_value=True), \
             mock.patch.object(ae,"_json",return_value=metadata), \
             mock.patch.object(ae,"_valid_npz_artifact",side_effect=lambda root,key:(metadata,cohort_shapes) if key.endswith("/cohort/A_half") else (append,shapes)), \
             mock.patch.object(ae,"_e4_generated_rf_role_context",return_value={"fit_counts":metadata["source_fit_counts"]}), \
             mock.patch.object(ae,"_e4_generated_rf_review_provenance",return_value={"audit_sha256":"a"}), \
             mock.patch.object(ae,"_e4_generated_rf_generated_artifact_valid",return_value={"generation_rows":1000}):
            ok,_=ae.eligible_e4_generated_restoration_rf_fit_6gib(task,definition,pathlib.Path("/fixture"))
        self.assertFalse(ok)

    def test_controller_reservation_uses_new_evidence(self):
        controller_spec=importlib.util.spec_from_file_location("staged_controller",HERE/"source"/"controller.py")
        controller=importlib.util.module_from_spec(controller_spec);controller_spec.loader.exec_module(controller)
        task,definition,*_=self.case(added=45934)
        task.update(status="planned",attempts=[])
        controller.DEFINITIONS={task["key"]:definition}
        controller.R=pathlib.Path("/fixture")
        evidence={"profile_id":ae.E4_GENERATED_RF_6G_PROFILE_ID,"reservation_gib":6}
        with mock.patch.object(controller.admission_evidence,"eligible_e4_treatment_rf_fit_5gib",return_value=(False,None)), \
             mock.patch.object(controller.admission_evidence,"eligible_2gib_resource_profile",return_value=(False,None)), \
             mock.patch.object(controller.admission_evidence,"eligible_4gib",return_value=(False,None)), \
             mock.patch.object(controller.admission_evidence,"eligible_rf_resource_profiles",return_value=(True,evidence)):
            self.assertEqual(controller.worker_reservation_bytes(task),6*controller.GIB)

if __name__=="__main__": unittest.main(verbosity=2)

