from __future__ import annotations
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'source'))
sp=importlib.util.spec_from_file_location('rf4_rep3_controller_admit_test',BASE/'source/controller.py')
ctl=importlib.util.module_from_spec(sp);sp.loader.exec_module(ctl)

class Rep3ControllerAdmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        self.old_root,self.old_defs=ctl.R,ctl.DEFINITIONS
        ctl.R=self.root;ctl.DEFINITIONS={}
        self.patch_archive=patch.object(ctl.archive_fit_admission,'inspect_runtime',return_value={'mode':'inactive'})
        self.patch_archive.start();self.addCleanup(self.patch_archive.stop)
        for name in ('controller.py','worker.py','science.py','phase_worker.py','cohorts.py','ensemble.py','ensemble_maintenance_patch.py','e6_phase_supervisor.py','svm_margin/science.py','svm_margin/worker.py','svm_margin/phase_worker.py','admission_evidence.py','archive_fit_admission.py')+ctl.RF4_SOURCE_NAMES:
            p=self.root/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture:'+name)
        (self.root/'manifests').mkdir(exist_ok=True)
        self.task={'key':'e4/rep_3/fit/treatment/random_forest/F_half_ros','experiment':4,'rep':3,
          'kind':'fit','method':'random_forest','route':'treatment','condition':'F_half_ros','treatment':'ros',
          'train_key':'e4/rep_3/treatment/F_half/ros','dependencies':['e4/rep_3/treatment/F_half/ros'],
          'selection_mode':'tune','selection_policy':'tune_each_treatment_on_same_frozen_tuning_role_with_equal_10_trial_budget',
          'selection_key':None,'selection_source':None,'trials':10,'seed':123,'optimizer_seed':456,
          'status':'waiting_for_dependency','attempts':[],'reuse_pipeline':False}
        ctl.DEFINITIONS={self.task['key']:dict(self.task)}
        self.evidence={'profile_id':ctl.RF4_E4_REP3_PROFILE_ID,'reservation_gib':6,'train_key':self.task['train_key']}
    def tearDown(self):
        ctl.R=self.old_root;ctl.DEFINITIONS=self.old_defs;self.tmp.cleanup()
    def test_actual_admit_records_rep3_profile_and_rf4_request_without_science_mutation(self):
        with patch.object(ctl,'_e4_treatment_rf4_rep3_6g_eligible',return_value=self.evidence), \
             patch.object(ctl,'_e4_treatment_rf4_6g_eligible',return_value=None), \
             patch.object(ctl,'_rf4_fit_eligible',return_value=None), \
             patch.object(ctl,'_rf4_policy',return_value={'manifest_sha256':'a'*64}), \
             patch.object(ctl,'_archive_fit_launch_gate',return_value=None), \
             patch.object(ctl,'start_ticks',return_value='12345'), \
             patch.object(ctl.subprocess,'Popen',return_value=type('Proc',(),{'pid':34567})()) as popen:
            self.assertEqual(ctl.worker_reservation_bytes(self.task),6*ctl.GIB)
            self.assertEqual(ctl.candidate_cpu_reservation_units(self.task),4)
            db=ctl.connect()
            try:
                self.assertTrue(ctl.admit(db,self.task))
            finally: db.close()
            cfg=json.loads(pathlib.Path(self.task['request_path']).read_text())
            self.assertEqual(self.task['admission_reservation_bytes'],6*ctl.GIB)
            self.assertEqual(self.task['admission_profile_id'],ctl.RF4_E4_REP3_PROFILE_ID)
            self.assertEqual(self.task['admission_resource_policy']['cpu_reservation_units'],4)
            self.assertEqual(cfg['execution_policy'],ctl.RF4_EXECUTION_POLICY)
            self.assertEqual(cfg['resource_profile'],ctl.RF4_RESOURCE_PROFILE)
            self.assertEqual(cfg['task']['key'],self.task['key'])
            self.assertNotIn('admission_profile_id',cfg['task'])
            self.assertEqual(pathlib.Path(popen.call_args.args[0][4]),self.root/'source/parallel_rf/worker.py')
    def test_recorded_rep3_profile_survives_actual_admit_resume(self):
        self.task['admission_profile_id']=ctl.RF4_E4_REP3_PROFILE_ID
        self.task['admission_reservation_bytes']=6*ctl.GIB
        self.task['admission_resource_policy']={'admission_profile_id':ctl.RF4_E4_REP3_PROFILE_ID,
          'admission_reservation_bytes':6*ctl.GIB,'execution_policy':ctl.RF4_EXECUTION_POLICY,
          'resource_profile':ctl.RF4_RESOURCE_PROFILE,'cpu_reservation_units':4}
        self.task['attempts']=[{'attempt_id':'prior','resource_profile':dict(self.task['admission_resource_policy'])}]
        with patch.object(ctl,'_e4_treatment_rf4_rep3_6g_eligible',return_value=None) as fresh_gate, \
             patch.object(ctl,'_e4_treatment_rf4_6g_eligible',return_value=None), \
             patch.object(ctl,'_rf4_fit_eligible',return_value=None), \
             patch.object(ctl,'_rf4_policy',return_value={'manifest_sha256':'a'*64}), \
             patch.object(ctl,'_archive_fit_launch_gate',return_value=None), \
             patch.object(ctl,'start_ticks',return_value='12345'), \
             patch.object(ctl.subprocess,'Popen',return_value=type('Proc',(),{'pid':34568})()):
            db=ctl.connect()
            try:self.assertTrue(ctl.admit(db,self.task))
            finally:db.close()
            fresh_gate.assert_not_called()
        self.assertEqual(self.task['admission_reservation_bytes'],6*ctl.GIB)
        self.assertEqual(self.task['admission_profile_id'],ctl.RF4_E4_REP3_PROFILE_ID)
        self.assertEqual(self.task['admission_resource_policy']['admission_profile_id'],ctl.RF4_E4_REP3_PROFILE_ID)
        self.assertEqual(self.task['attempts'][-1]['resource_profile']['admission_profile_id'],ctl.RF4_E4_REP3_PROFILE_ID)

if __name__=='__main__':unittest.main()
