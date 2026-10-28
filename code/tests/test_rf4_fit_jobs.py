import importlib.util
import importlib
import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch

STAGE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("parallel_rf_science_fixture",STAGE/"source/parallel_rf/science.py")
science=importlib.util.module_from_spec(spec);spec.loader.exec_module(science)

class Estimator:
 def __init__(self,n_jobs): self.n_jobs=n_jobs
class FakeModel:
 def __init__(self,n_jobs): self.estimator=Estimator(n_jobs);self.fit_jobs_seen=None;self.prediction_jobs_seen=None
 def fit(self,X,y):
  self.fit_jobs_seen=self.estimator.n_jobs
  return self
 def predict_proba(self,X):
  self.prediction_jobs_seen=self.estimator.n_jobs
  return [[1.0]]
class FakeModule:
 def __init__(self): self.model=None;self.jobs_seen=None
 def make_model(self,method,params,seed,n_jobs):
  self.jobs_seen=n_jobs;self.model=FakeModel(n_jobs);return self.model

class RF4ExecutionPolicyTests(unittest.TestCase):
 def test_rf_fit_uses_four_only_for_fit_then_one_for_prediction(self):
  policy={"LAMOST_RF_FIT_JOBS4":"1","LAMOST_RF_EXECUTION_POLICY":science.RF4_EXECUTION_POLICY,"LAMOST_RF_RESOURCE_PROFILE":science.RF4_RESOURCE_PROFILE}
  with patch.dict(os.environ,policy):
   task={"kind":"fit","method":"random_forest","experiment":4};mod=FakeModule()
   model,jobs=science._make_fit_model(mod,task,"trial_0",{},17,[],[])
   self.assertEqual((jobs,mod.jobs_seen,model.fit_jobs_seen),(4,4,4))
   model.predict_proba([])
   self.assertEqual(model.prediction_jobs_seen,1)
 def test_rf4_policy_rejects_non_rf_and_other_experiments(self):
  policy={"LAMOST_RF_FIT_JOBS4":"1","LAMOST_RF_EXECUTION_POLICY":science.RF4_EXECUTION_POLICY,"LAMOST_RF_RESOURCE_PROFILE":science.RF4_RESOURCE_PROFILE}
  with patch.dict(os.environ,policy):
   for task in ({"kind":"fit","method":"logistic","experiment":4},{"kind":"fit","method":"random_forest","experiment":3}):
    with self.assertRaises(ValueError):science._fit_n_jobs(task,"trial_0")
 def test_worker_imports_adapter_engine_and_uses_sibling_phase_worker(self):
  worker_path=STAGE/"source/parallel_rf/worker.py"
  adapter_path=(STAGE/"source/parallel_rf/science.py").resolve()
  phase_path=(STAGE/"source/parallel_rf/phase_worker.py").resolve()
  old_path=list(sys.path);old_science=sys.modules.pop("science",None)
  try:
   spec=importlib.util.spec_from_file_location("rf4_worker_path_fixture",worker_path)
   worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
   imported=importlib.import_module("science")
   self.assertEqual(Path(imported.__file__).resolve(),adapter_path)
   self.assertEqual(Path(imported._phase_worker_path()).resolve(),phase_path)
   self.assertEqual(worker.rf4_policy_constants(),(imported.RF4_EXECUTION_POLICY,imported.RF4_RESOURCE_PROFILE))
   for phase in ("trial_0","final_fit"):
    cfg=STAGE/"fixture_out"/f"phase_{phase}.json"
    cmd=imported._phase_worker_command(cfg)
    self.assertEqual(Path(cmd[1]).resolve(),phase_path)
    self.assertEqual(Path(cmd[2]),cfg)
  finally:
   sys.path[:]=old_path;sys.modules.pop("science",None)
   if old_science is not None:sys.modules["science"]=old_science
 def test_unmarked_legacy_fit_remains_single_job(self):
  with patch.dict(os.environ,{},clear=True):
   self.assertEqual(science._fit_n_jobs({"kind":"fit","method":"random_forest","experiment":5},"trial_0"),1)

if __name__=="__main__":unittest.main()
