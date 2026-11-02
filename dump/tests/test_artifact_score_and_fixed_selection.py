import importlib.util,sys,unittest,json,tempfile,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
BASE=Path(__file__).resolve().parents[1]
SRC=BASE/"source/audit_artifacts.py"
spec=importlib.util.spec_from_file_location("staged_auditor",SRC)
aud=importlib.util.module_from_spec(spec);spec.loader.exec_module(aud)
PROJECT=BASE.parent/"project"
sys.path.insert(0,str(PROJECT))
from benchmark.evaluation import conformal_evaluate
class MarginArtifactTests(unittest.TestCase):
 def setUp(self):
  self.y=np.arange(7,dtype=np.int64)
  self.scores=(np.arange(49,dtype=np.float64).reshape(7,7)/10.0)-2.0
  self.threshold=0.2
  self.reference=conformal_evaluate(self.scores,self.y,self.threshold,score_kind="margin")
  self.npz={"scores":self.scores,"score_kind":np.asarray("margin"),"score_class_order":np.arange(7,dtype=np.int8),"threshold":np.asarray(self.threshold,dtype=np.float64),"prediction_rule":np.asarray("argmax_class_score"),"nonconformity_rule":np.asarray("negative_margin")}
  self.evaluation={"score_kind":"margin","calibration_score_kind":"margin","threshold":self.threshold,"prediction_rule":"argmax_class_score","nonconformity_rule":"negative_margin","fit_key":"fit/e4/linear_svm","pipeline_sha256":"a"*64}
  self.calibration={"score_kind":"margin","threshold":self.threshold,"calibration_n":10000,"calibration_fallback_count":0,"fit_key":"fit/e4/linear_svm","pipeline_sha256":"a"*64}
 def checks(self,m=None,z=None,cal=None,required=True):
  m=self.evaluation if m is None else m;z=self.npz if z is None else z;cal=self.calibration if cal is None else cal
  return aud._score_contract_checks(m,z,self.y,self.reference["predictions"],self.reference["sets"],self.reference["covered"],self.reference["sets"].sum(1),10000,cal,required,"fit/e4/linear_svm")
 def test_native_margin_scores_match_frozen_e1_semantics(self):
  self.assertFalse(np.allclose(self.scores.sum(axis=1),1.0))
  self.assertEqual(self.checks(),[])
 def test_wrong_kind_rejected_without_softmax_fallback(self):
  z=dict(self.npz);z["score_kind"]=np.asarray("probability")
  names={c for c,_ in self.checks(z=z)}
  self.assertIn("npz_score_kind_mismatch",names)
  self.assertNotIn("probability_rows_not_normalized",names)
 def test_probability_validation_remains_strict(self):
  p=np.full((7,7),1/7,dtype=np.float64);e={"score_kind":"probability","threshold":0.8}
  z={"scores":p,"score_kind":np.asarray("probability"),"score_class_order":np.arange(7,dtype=np.int8),"threshold":np.asarray(.8)}
  ref=conformal_evaluate(p,self.y,.8,score_kind="probability")
  errors=aud._score_contract_checks(e,z,self.y,ref["predictions"],ref["sets"],ref["covered"],ref["sets"].sum(1),10000)
  self.assertEqual(errors,[])
  z["scores"]=p*2
  names={c for c,_ in aud._score_contract_checks(e,z,self.y,ref["predictions"],ref["sets"],ref["covered"],ref["sets"].sum(1),10000)}
  self.assertIn("probability_rows_not_normalized",names)
 def test_margin_shape_class_order_and_finiteness(self):
  z=dict(self.npz);z["scores"]=self.scores[:,:6]
  self.assertIn("scores_shape",{c for c,_ in self.checks(z=z)})
  z=dict(self.npz);z["score_class_order"]=np.arange(1,8,dtype=np.int8)
  self.assertIn("score_class_order",{c for c,_ in self.checks(z=z)})
  z=dict(self.npz);z["scores"]=self.scores.copy();z["scores"][0,0]=np.nan
  self.assertIn("scores_nonfinite",{c for c,_ in self.checks(z=z)})
 def test_margin_threshold_and_calibration_identity(self):
  z=dict(self.npz);z["threshold"]=np.asarray(.3)
  names={c for c,_ in self.checks(z=z)}
  self.assertIn("threshold_mismatch",names)
  cal=dict(self.calibration,score_kind="probability")
  self.assertIn("calibration_score_kind_mismatch",{c for c,_ in self.checks(cal=cal)})
  cal=dict(self.calibration,pipeline_sha256="b"*64)
  self.assertIn("calibration_pipeline_sha_mismatch",{c for c,_ in self.checks(cal=cal)})
 def test_legacy_archived_margin_without_scores_remains_compatible(self):
  e={"score_kind":"margin"};z={"y_pred":self.reference["predictions"]}
  self.assertEqual(aud._score_contract_checks(e,z,self.y,self.reference["predictions"],self.reference["sets"],self.reference["covered"],self.reference["sets"].sum(1),10000,require_scores=False),[])
 def test_versioned_svm_requires_scores_and_calibration_metadata(self):
  z={k:v for k,v in self.npz.items() if k!="scores"}
  names={c for c,_ in self.checks(z=z,cal=None,required=True)}
  self.assertIn("scores_missing",names)
 def test_nested_model_score_kind_preserves_existing_svm_fit_declaration(self):
  pipe={"model":SimpleNamespace(score_kind="margin")};meta={};fit_doc={}
  self.assertEqual(aud._declared_score_kinds(pipe,meta,fit_doc),[("pipeline",None),("pipeline_model","margin"),("registry_fit_result",None),("artifact_fit_result",None)])
 def test_versioned_svm_alias_copies_and_validates_local_calibration(self):
  with tempfile.TemporaryDirectory() as td:
   rt=Path(td)/"runtime";(rt/"cache/roles").mkdir(parents=True);(rt/"artifacts/source").mkdir(parents=True);(rt/"artifacts/alias").mkdir(parents=True)
   y=self.y;ids=np.arange(len(y),dtype=np.int64)
   np.savez(rt/"cache/test.npz",y=y,ids=ids)
   np.savez(rt/"cache/roles/rep_1.npz",y_cal=np.asarray([0,1],dtype=np.int64))
   bits=self.reference["sets"];mask=np.packbits(bits,axis=1,bitorder="little")[:,0]
   arrays={"sample_id":ids,"y_pred":self.reference["predictions"],"set_mask":mask.astype(np.uint8),"covered":self.reference["covered"],"set_size":bits.sum(1),**self.npz}
   for base in [rt/"artifacts/source",rt/"artifacts/alias"]:np.savez(base/"test_outcomes.npz",**arrays)
   cal=dict(self.calibration,calibration_n=2)
   for base in [rt/"artifacts/source",rt/"artifacts/alias"]:(base/"calibration.json").write_text(json.dumps(cal))
   ev=dict(self.evaluation,task_key="alias",experiment=5,repetition=1)
   (rt/"artifacts/source/evaluation.json").write_text(json.dumps(ev));(rt/"artifacts/alias/evaluation.json").write_text(json.dumps(ev))
   def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
   ref={"source_key":"source","source_test_outcomes_npz_sha256":sha(rt/"artifacts/source/test_outcomes.npz"),"alias_test_outcomes_npz_sha256":sha(rt/"artifacts/alias/test_outcomes.npz"),"source_calibration_json_sha256":sha(rt/"artifacts/source/calibration.json"),"alias_calibration_json_sha256":sha(rt/"artifacts/alias/calibration.json")}
   (rt/"artifacts/alias/artifact_ref.json").write_text(json.dumps(ref))
   auditor=aud.Auditor(rt);task={"key":"alias","source_key":"source","rep":1,"experiment":5,"method":"linear_svm","fit_key":"fit/e4/linear_svm"};paths=[]
   files=auditor._svm_alias_score_audit(task,rt/"artifacts/alias",rt/"artifacts/source",ev,paths)
   self.assertEqual(set(files),{"evaluation.json","test_outcomes.npz","calibration.json"})
   self.assertEqual(auditor.issues,[])
   bad=dict(ref,alias_calibration_json_sha256="0"*64);(rt/"artifacts/alias/artifact_ref.json").write_text(json.dumps(bad))
   auditor=aud.Auditor(rt);auditor._svm_alias_score_audit(task,rt/"artifacts/alias",rt/"artifacts/source",ev,[])
   self.assertIn("artifact_ref_alias_hash",{x["check"] for x in auditor.issues})


class FixedSelectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.rt=self.root/"runtime";self.rt.mkdir()
  self.auditor=aud.Auditor(self.rt)
  self.params={"C":1.25}
 def test_valid_imported_fixed_selection_binds_frozen_complete_hash_and_params(self):
  source_dir=self.rt/"manifests/imported_selections/e1_100000/rep_1/linear_svm";source_dir.mkdir(parents=True)
  frozen=self.root/"project/benchmark/results/e1/rep_1/n_100000/linear_svm/complete.json";frozen.parent.mkdir(parents=True)
  complete={"status":"complete","score_kind":"margin","selected_params":self.params,"best_tuning_balanced_accuracy":0.61}
  frozen.write_text(json.dumps(complete));source_sha=aud.sha256_file(frozen)
  imported={"selected_params":self.params,"source_path":"project/benchmark/results/e1/rep_1/n_100000/linear_svm/complete.json","source_sha256":source_sha,"source_status":"complete","source_tuning_balanced_accuracy":0.61,"provenance":"frozen E1 selected parameters"}
  (source_dir/"selection.json").write_text(json.dumps(imported))
  t={"key":"e4/rep_1/fit/direct/linear_svm/control","selection_mode":"fixed","selection_source":"runtime/manifests/imported_selections/e1_100000/rep_1/linear_svm","selection_key":None,"method":"linear_svm","rep":1}
  paths=[];self.auditor._fixed_selection_audit(t,{},self.params,{"selected_params":self.params},paths)
  self.assertEqual(self.auditor.issues,[]);self.assertIn(source_dir/"selection.json",paths);self.assertIn(frozen,paths)
 def test_imported_fixed_selection_wrong_params_fails(self):
  self._imported_fixture()
  t,selection,params,paths=self.imported
  wrong={"C":7.0};self.auditor._fixed_selection_audit(t,{},wrong,selection,paths)
  self.assertTrue({x["check"] for x in self.auditor.issues}&{"fixed_selection_params","fixed_selection_frozen_params"})
 def test_imported_fixed_selection_missing_source_fails(self):
  t={"key":"fixed","selection_mode":"fixed","selection_source":"runtime/missing","selection_key":None,"method":"linear_svm","rep":1}
  self.auditor._fixed_selection_audit(t,{},self.params,{"selected_params":self.params},[])
  self.assertIn("fixed_selection_source_record_missing",{x["check"] for x in self.auditor.issues})
 def test_imported_fixed_selection_bad_frozen_hash_fails(self):
  t,selection,params,paths=self._imported_fixture()
  frozen=self.root/"project/benchmark/results/e1/rep_1/n_100000/linear_svm/complete.json";frozen.write_text(json.dumps({"status":"complete","selected_params":self.params,"best_tuning_balanced_accuracy":0.61,"tampered":True}))
  self.auditor._fixed_selection_audit(t,{},params,selection,paths)
  self.assertIn("fixed_selection_frozen_hash",{x["check"] for x in self.auditor.issues})
 def _imported_fixture(self):
  source_dir=self.rt/"manifests/imported_selections/e1_100000/rep_1/linear_svm";source_dir.mkdir(parents=True,exist_ok=True)
  frozen=self.root/"project/benchmark/results/e1/rep_1/n_100000/linear_svm/complete.json";frozen.parent.mkdir(parents=True,exist_ok=True)
  complete={"status":"complete","score_kind":"margin","selected_params":self.params,"best_tuning_balanced_accuracy":0.61};frozen.write_text(json.dumps(complete))
  imported={"selected_params":self.params,"source_path":"project/benchmark/results/e1/rep_1/n_100000/linear_svm/complete.json","source_sha256":aud.sha256_file(frozen),"source_status":"complete","source_tuning_balanced_accuracy":0.61,"provenance":"frozen E1 selected parameters"};(source_dir/"selection.json").write_text(json.dumps(imported))
  t={"key":"fixed","selection_mode":"fixed","selection_source":"runtime/manifests/imported_selections/e1_100000/rep_1/linear_svm","method":"linear_svm","rep":1}
  paths=[];self.imported=(t,{"selected_params":self.params},self.params,paths);return t,self.imported[1],self.params,paths
 def _key_fixture(self,source_params=None):
  source_params=self.params if source_params is None else source_params
  src_key="e4/rep_1/fit/direct/gaussian_nb/control";srcout=self.rt/"artifacts"/src_key;srcout.mkdir(parents=True,exist_ok=True)
  sp=srcout/"selection.json";sp.write_text(json.dumps({"selected_params":source_params,"seed":12}))
  pp=srcout/"pipeline.joblib";pp.write_bytes(b"immutable pipeline placeholder");ph=aud.sha256_file(pp)
  source={"key":src_key,"kind":"fit","status":"validated_terminal","outcome":"successful","method":"gaussian_nb","rep":1,"result":{"result":{"params":source_params,"pipeline_sha256":ph}}}
  target={"key":"e5/rep_1/fit/direct/gaussian_nb/feature_noise_05","kind":"fit","outcome":"successful","method":"gaussian_nb","rep":1,"selection_mode":"fixed","selection_key":source["key"],"selection_source":None,"optimizer_seed":991}
  return source,target,sp,pp
 def test_valid_selection_key_fixed_selection(self):
  source,target,sp,pp=self._key_fixture();paths=[]
  self.auditor._fixed_selection_audit(target,{source["key"]:source},self.params,{"selected_params":self.params},paths)
  self.assertEqual(self.auditor.issues,[]);self.assertIn(sp,paths);self.assertIn(pp,paths)
  inputs=self.auditor.fit_inputs(target,{source["key"]:source})
  self.assertIn(sp,inputs);self.assertIn(pp,inputs)
 def test_selection_key_wrong_params_missing_source_and_bad_hash_fail(self):
  source,target,sp,pp=self._key_fixture({"var_smoothing":0.01});wrong={"C":8}
  self.auditor._fixed_selection_audit(target,{source["key"]:source},wrong,{"selected_params":wrong},[])
  self.assertIn("fixed_selection_params",{x["check"] for x in self.auditor.issues})
  self.auditor.issues.clear();target_missing=dict(target,selection_key="absent")
  self.auditor._fixed_selection_audit(target_missing,{source["key"]:source},self.params,{"selected_params":self.params},[])
  self.assertIn("fixed_selection_key_missing",{x["check"] for x in self.auditor.issues})
  self.auditor.issues.clear();unvalidated=dict(source,status="running",outcome="successful")
  self.auditor._fixed_selection_audit(target,{unvalidated["key"]:unvalidated},self.params,{"selected_params":self.params},[])
  self.assertIn("fixed_selection_key_invalid",{x["check"] for x in self.auditor.issues})
  self.auditor.issues.clear();source_bad=dict(source,result={"result":{"params":{"var_smoothing":0.01},"pipeline_sha256":"0"*64}})
  self.auditor._fixed_selection_audit(target,{source_bad["key"]:source_bad},self.params,{"selected_params":self.params},[])
  self.assertIn("fixed_selection_source_pipeline_hash",{x["check"] for x in self.auditor.issues})
 def test_selection_dependency_registry_changes_invalidate_cache_signature(self):
  source,target,sp,pp=self._key_fixture();by={source["key"]:source}
  before=self.auditor.task_signature_payload(target,by,{"pipeline":aud.sha256_file(pp)})
  changed=dict(source,status="running")
  after_status=self.auditor.task_signature_payload(target,{source["key"]:changed},{"pipeline":aud.sha256_file(pp)})
  self.assertNotEqual(before,after_status)
  changed_meta=json.loads(json.dumps(source));changed_meta["result"]["result"]["params"]={"var_smoothing":0.5}
  after_meta=self.auditor.task_signature_payload(target,{source["key"]:changed_meta},{"pipeline":aud.sha256_file(pp)})
  self.assertNotEqual(before,after_meta)
  self.assertNotEqual(hashlib.sha256(json.dumps(before,sort_keys=True,default=str).encode()).hexdigest(),hashlib.sha256(json.dumps(after_status,sort_keys=True,default=str).encode()).hexdigest())
 def test_optimizer_seed_checked_for_tuning_but_not_fixed(self):
  self.auditor._check_optimizer_seed({"key":"tune","selection_mode":"tune","optimizer_seed":41},{"optimizer_seed":42})
  self.assertIn("optimizer_seed",{x["check"] for x in self.auditor.issues})
  self.auditor.issues.clear();self.auditor._check_optimizer_seed({"key":"fixed","selection_mode":"fixed","optimizer_seed":41},{"seed":99})
  self.assertEqual(self.auditor.issues,[])
 def test_real_e5_fixed_selection_key_schema_and_input_dependencies(self):
  real=BASE
  reg=json.loads((real/"registry.json").read_text());by={t["key"]:t for t in reg["tasks"]}
  key="e5/rep_1/fit/direct/gaussian_nb/feature_noise_05"
  if key not in by or by[key].get("outcome")!="successful":self.skipTest("real E5 fixed-selection_key fixture not present yet")
  target=by[key];source=by[target["selection_key"]];actual=aud.Auditor(real);params=target["result"]["result"]["params"];selection=json.loads((actual.task_art(target)/"selection.json").read_text());paths=[]
  actual._fixed_selection_audit(target,by,params,selection,paths)
  self.assertEqual(actual.issues,[]);inputs=actual.fit_inputs(target,by)
  sout=actual.task_art(source);self.assertIn(sout/"selection.json",inputs);self.assertIn(sout/"pipeline.joblib",inputs)



class E4AppendAuditTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.rt=self.root/"runtime";(self.rt/"artifacts").mkdir(parents=True);(self.rt/"cache/roles").mkdir(parents=True)
  self._build_valid_fixture()
 def _sha(self,p):return aud.sha256_file(p)
 def _save_npz(self,path,**arrays):
  path.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(path,**arrays);return self._sha(path)
 def _task(self,key,**kwargs):return {"key":key,**kwargs}
 def _build_valid_fixture(self):
  self.cohort_key="e4/rep_1/cohort/A_half";self.gen_key="e4/rep_1/generate/A_half/gmm";self.fit_key="e4/rep_1/fit/direct/gmm/A_half";self.append_key="e4/rep_1/append/A_half/gmm"
  ids=np.arange(10,20,dtype=np.int64);ydev=np.asarray([0,0,1,2,3,4,1,2,3,4],dtype=np.int64)
  Xdev=np.arange(60,dtype=np.float64).reshape(10,6)
  np.save(self.rt/"cache/development_X.npy",Xdev);np.save(self.rt/"cache/development_y.npy",ydev);np.save(self.rt/"cache/development_ids.npy",ids)
  fitids=ids[:6];fit_y=ydev[:6];fit_X=Xdev[:6]
  np.savez(self.rt/"cache/roles/rep_1.npz",X_fit=fit_X,y_fit=fit_y,fit_ids=fitids,X_tune=Xdev[8:9],y_tune=ydev[8:9],tuning_ids=ids[8:9],X_cal=Xdev[9:10],y_cal=ydev[9:10],calibration_ids=ids[9:10])
  np.savez(self.rt/"cache/test.npz",ids=np.asarray([20],dtype=np.int64))
  cohort_ids=np.asarray([10,12,13,14,15,16],dtype=np.int64);pos=np.searchsorted(ids,cohort_ids);Xb=Xdev[pos];yb=ydev[pos]
  cohort_counts=np.bincount(yb,minlength=7)
  orig_counts=np.bincount(fit_y,minlength=7)
  cohort_meta={"kind":"e4_cohort","task_key":self.cohort_key,"rep":1,"target_class":0,"ratio":0.5,"N":6,"source_fit_counts":orig_counts.tolist(),"realized_counts":cohort_counts.tolist(),"restore_added_count":2,"ids_sha256":aud._typed_array_sha256(cohort_ids),"sample_weight_included":False}
  cohort_path=self.rt/"artifacts"/self.cohort_key;ch=self._save_npz(cohort_path/"data.npz",X=Xb,y=yb,ids=cohort_ids);(cohort_path/"metadata.json").write_text(json.dumps(cohort_meta))
  Xg=np.asarray([[100,101,102,103,104,105],[110,111,112,113,114,115]],dtype=np.float64);yg=np.asarray([0,0],dtype=np.int8)
  gen_path=self.rt/"artifacts"/self.gen_key;gh=self._save_npz(gen_path/"data.npz",X=Xg,y=yg)
  appX=np.concatenate([Xb,Xg]);appy=np.concatenate([yb,yg.astype(np.int64)]);syn=np.asarray([f"generated:{self.append_key}:{i}" for i in range(2)])
  appids=np.concatenate([cohort_ids.astype(str),syn])
  app_path=self.rt/"artifacts"/self.append_key;ah=self._save_npz(app_path/"data.npz",X=appX,y=appy,ids=appids)
  app_meta={"kind":"e4_append","task_key":self.append_key,"target_class":0,"added_count":2,"counts_before":cohort_counts.tolist(),"counts_after":np.bincount(appy,minlength=7).tolist(),"generator_metadata":{}}
  (app_path/"metadata.json").write_text(json.dumps(app_meta))
  self.bykey={
   self.cohort_key:self._task(self.cohort_key,kind="e4_cohort",status="validated_terminal",outcome="successful",rep=1,target_class=0,ratio=.5,result={"validation":{"files":{"data.npz":ch}}}),
   self.fit_key:self._task(self.fit_key,kind="fit",status="validated_terminal",outcome="successful",rep=1,method="gmm",train_key=self.cohort_key),
   self.gen_key:self._task(self.gen_key,kind="generate",status="validated_terminal",outcome="successful",rep=1,generator="gmm",target_class=0,cohort_key=self.cohort_key,dependencies=[self.fit_key,self.cohort_key],result={"result":{"n_rows":2,"class_counts":[2,0,0,0,0,0,0],"data_sha256":gh},"validation":{"files":{"data.npz":gh}}}),
   self.append_key:self._task(self.append_key,kind="e4_append",status="validated_terminal",outcome="successful",rep=1,target_class=0,target_label="A",ratio=.5,generator="gmm",condition="A_half",cohort_key=self.cohort_key,generated_key=self.gen_key,dependencies=[self.cohort_key,self.gen_key],result={"validation":{"files":{"data.npz":ah}}})
  }
  final_counts=np.bincount(appy,minlength=7)
  for name in ("ros","smote"):
   key=f"e4/rep_1/treatment/A_half/{name}";tp=self.rt/"artifacts"/key;th=self._save_npz(tp/"data.npz",X=appX,y=appy,ids=appids)
   self.bykey[key]=self._task(key,kind="e4_treatment",status="validated_terminal",outcome="successful",rep=1,target_class=0,cohort_key=self.cohort_key,treatment=name,result={"validation":{"files":{"data.npz":th}}})
 def _audit(self):
  a=aud.Auditor(self.rt);paths=a.e4_append_audit(self.bykey[self.append_key],self.bykey);return a.issues,paths
 def test_valid_generated_append_cohort_generator_roles_and_ros_smote(self):
  issues,paths=self._audit();self.assertEqual(issues,[]);self.assertTrue(any(str(p).endswith("metadata.json") for p in paths))
 def test_non_target_generated_label_is_rejected(self):
  p=self.rt/"artifacts"/self.gen_key/"data.npz";z=np.load(p);X=z["X"];y=z["y"].copy();y[1]=1;self._save_npz(p,X=X,y=y)
  self.assertIn("generated_target_count_or_class",{x["check"] for x in self._audit()[0]})
 def test_generated_nan_is_rejected(self):
  p=self.rt/"artifacts"/self.gen_key/"data.npz";z=np.load(p);X=z["X"].copy();X[0,0]=np.nan;self._save_npz(p,X=X,y=z["y"])
  self.assertIn("generated_nonfinite",{x["check"] for x in self._audit()[0]})
 def test_generated_suffix_order_is_rejected(self):
  p=self.rt/"artifacts"/self.append_key/"data.npz";z=np.load(p);X=z["X"].copy();X[-2:]=X[-2:][::-1];self._save_npz(p,X=X,y=z["y"],ids=z["ids"])
  self.assertIn("generated_feature_suffix",{x["check"] for x in self._audit()[0]})
 def test_real_id_in_synthetic_suffix_is_rejected(self):
  p=self.rt/"artifacts"/self.append_key/"data.npz";z=np.load(p);ids=z["ids"].copy();ids[-1]="10";self._save_npz(p,X=z["X"],y=z["y"],ids=ids)
  self.assertIn("synthetic_id_construction",{x["check"] for x in self._audit()[0]})
 def test_wrong_final_histogram_is_rejected(self):
  p=self.rt/"artifacts"/self.append_key/"data.npz";z=np.load(p);y=z["y"].copy();y[-1]=2;self._save_npz(p,X=z["X"],y=y,ids=z["ids"])
  self.assertIn("final_histogram",{x["check"] for x in self._audit()[0]})
 def test_output_validation_hash_mismatch_is_rejected(self):
  t=self.bykey[self.append_key];t["result"]["validation"]["files"]["data.npz"]="0"*64
  self.assertIn("append_artifact_hash",{x["check"] for x in self._audit()[0]})
 def test_wrong_dependency_schema_is_rejected(self):
  t=self.bykey[self.append_key];t["dependencies"]=[self.cohort_key,self.gen_key,"e4/rep_1/treatment/A_half/ros"]
  self.assertIn("dependency_schema",{x["check"] for x in self._audit()[0]})
 def test_tuning_calibration_id_leakage_is_rejected(self):
  p=self.rt/"artifacts"/self.cohort_key/"data.npz";z=np.load(p);ids=z["ids"].copy();ids[-1]=18;self._save_npz(p,X=z["X"],y=z["y"],ids=ids)
  self.assertIn("cohort_reserved_id_overlap",{x["check"] for x in self._audit()[0]})
 def test_cohort_id_metadata_digest_mismatch_is_rejected(self):
  p=self.rt/"artifacts"/self.cohort_key/"metadata.json";m=json.loads(p.read_text());m["ids_sha256"]="0"*64;p.write_text(json.dumps(m))
  self.assertIn("cohort_id_hash",{x["check"] for x in self._audit()[0]})
 def test_invalid_generator_dependency_is_rejected(self):
  t=self.bykey[self.append_key];t["generated_key"]="e4/rep_1/generate/missing/gmm"
  self.assertIn("generated_dependency_invalid",{x["check"] for x in self._audit()[0]})
 def test_append_dependency_registry_change_invalidates_signature(self):
  auditor=aud.Auditor(self.rt);task=self.bykey[self.append_key];before=auditor.task_signature_payload(task,self.bykey,{"append":"same"})
  changed=dict(self.bykey[self.cohort_key],status="running");by=dict(self.bykey);by[self.cohort_key]=changed
  after_cohort=auditor.task_signature_payload(task,by,{"append":"same"})
  self.assertNotEqual(before,after_cohort)
  ros_key="e4/rep_1/treatment/A_half/ros";changed_ros=dict(by[ros_key],outcome="failed");by[ros_key]=changed_ros
  after_ros=auditor.task_signature_payload(task,by,{"append":"same"})
  self.assertNotEqual(before,after_ros)
  fit_changed=dict(self.bykey[self.fit_key],status="running")
  byfit=dict(self.bykey);byfit[self.fit_key]=fit_changed
  after_fit=auditor.task_signature_payload(task,byfit,{"append":"same"})
  self.assertNotEqual(before,after_fit)
 def test_actual_validated_append_examples(self):
  real=BASE;reg=json.loads((real/"registry.json").read_text());tasks=reg["tasks"];by={t["key"]:t for t in tasks};valid=[t for t in tasks if t.get("kind")=="e4_append" and t.get("status")=="validated_terminal" and t.get("outcome")=="successful"]
  if len(valid)<3:self.skipTest("three actual validated append artifacts are not present")
  picks=[valid[0],valid[len(valid)//2],valid[-1]];a=aud.Auditor(real)
  for t in picks:
   before=len(a.issues);a.e4_append_audit(t,by);self.assertEqual(a.issues[before:],[],msg=t["key"])

if __name__=="__main__":unittest.main()
