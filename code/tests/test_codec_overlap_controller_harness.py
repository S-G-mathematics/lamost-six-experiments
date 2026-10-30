from pathlib import Path
import os, sys, unittest, hashlib
from unittest.mock import patch
STAGE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(STAGE/'source'))
# Earlier collected tests may have imported a different module named controller.
# Force this harness to bind to the candidate source under test.
sys.modules.pop('controller',None)
sys.modules.pop('archive_fit_admission',None)
import controller
_EXPECTED_CONTROLLER_SHA='7c873853af440e5b8da889e42b4a741df9b24668f54f654398b234c6217b2b9b'
assert Path(controller.__file__).resolve()==(STAGE/'source/controller.py').resolve()
assert hashlib.sha256(Path(controller.__file__).read_bytes()).hexdigest()==_EXPECTED_CONTROLLER_SHA
assert Path(controller.archive_fit_overlap_context.__code__.co_filename).resolve()==(STAGE/'source/controller.py').resolve()
G=1024**3
class NativeCodecAdmissionHarnessTests(unittest.TestCase):
    def setUp(self):
        self.key='e4/rep_1/fit/direct/random_forest/label_noise_20'
        self.task={'key':self.key,'experiment':4,'kind':'fit','route':'direct','method':'random_forest','rep':1,'status':'planned','attempts':[],'dependencies':['e4/rep_1/cohort/clean'],'reuse_pipeline':False}
        self.records={self.key:self.task}
        self.helper_context={'evidence':{'context_sha256':'a'*64}}
        self.profile=os.environ.get('LAMOST_TEST_CODEC_PROFILE','codec4')
        if self.profile not in {'codec1','codec4','codec12'}: raise ValueError('unsupported test profile')
        io_profile={'codec1':'bounded-1800-codec1gib64','codec4':'bounded-5400-codec4gib64','codec12':'bounded-5400-codec4gib64-payload12'}[self.profile]
        self.expected_overlap_profile={'codec1':'codec','codec4':'codec4','codec12':'codec12'}[self.profile]
        storage={'codec12':'reversible-xz-v1-payload12'}.get(self.profile,'reversible-xz-v1')
        self.archive_op={'owner_operation':'rf_cold_batch_wrapper_20261026','batch_policy':'storage-followup-codec','archive_io_profile':io_profile,'storage_codec_policy':storage}
        self.helper={'available_bytes':20*G,'credited_pss_bytes':512*1024**2,'observed_peak_pss_bytes':700*1024**2,'context':self.helper_context}
        self.patches=[]
        def start(target,*a,**kw):
            p=patch.object(target,*a,**kw);p.start();self.patches.append(p)
        start(controller,'archive_fit_overlap_context',return_value={'mode':'active','evidence':self.helper_context['evidence']})
        start(controller,'_archive_overlap_freeze',return_value={'source_sha256':{'controller.py':'c'*64,'archive_fit_admission.py':'d'*64}})
        start(controller,'load',return_value=self.records)
        start(controller.archive_fit_admission,'qualify_candidate',return_value={'proof_sha256':'b'*64,'overlap_profile':self.expected_overlap_profile,'archive_operation':self.archive_op})
        start(controller,'_bracketed_archive_helper',return_value=self.helper)
        start(controller,'bracketed_worker_memory',return_value=(20*G,[],[]))
        start(controller,'memory_admission_ok',return_value=True)
        start(controller,'cpu_admission_units',return_value=(0,2))
        start(controller,'candidate_cpu_reservation_units',return_value=1)
        start(controller,'worker_reservation_bytes',return_value=10*G)
        start(controller,'DEFINITIONS',{self.key:dict(self.task)})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def test_active_codec_context_passes_controller_gate_without_launching_fit(self):
        result=controller._archive_fit_launch_gate(object(),self.task,idle_hint=4)
        self.assertIsInstance(result,dict)
        self.assertEqual(result['task_input_proof']['proof_sha256'],'b'*64)
        self.assertEqual(result['task_input_proof']['overlap_profile'],self.expected_overlap_profile)
        self.assertEqual(result['task_input_proof']['archive_operation'],self.archive_op)
        self.assertEqual(result['helper_reservation_bytes'],int(1.5*G))
        controller.archive_fit_admission.qualify_candidate.assert_called_once()
        self.assertEqual(self.task['attempts'],[])
    def test_payload12_profile_is_bound_in_the_controller_launch_decision(self):
        if self.profile!='codec12': self.skipTest('run with LAMOST_TEST_CODEC_PROFILE=codec12')
        result=controller._archive_fit_launch_gate(object(),self.task,idle_hint=4)
        self.assertEqual(result['task_input_proof']['overlap_profile'],'codec12')
        self.assertEqual(result['task_input_proof']['archive_operation']['archive_io_profile'],'bounded-5400-codec4gib64-payload12')
        self.assertEqual(result['task_input_proof']['archive_operation']['storage_codec_policy'],'reversible-xz-v1-payload12')
        self.assertEqual(result['task_input_proof']['archive_operation']['batch_policy'],'storage-followup-codec')
        self.assertEqual(self.task['attempts'],[])
    def test_helper_failure_or_nonpristine_candidate_is_denied(self):
        with patch.object(controller,'_bracketed_archive_helper',return_value=None):
            self.assertIs(controller._archive_fit_launch_gate(object(),self.task,idle_hint=4),False)
        controller.archive_fit_admission.qualify_candidate.return_value=None
        self.assertIs(controller._archive_fit_launch_gate(object(),self.task,idle_hint=4),False)
    def test_inactive_policy_preserves_legacy_path_without_database_reads(self):
        with patch.object(controller,'archive_fit_overlap_context',return_value={'mode':'inactive'}), patch.object(controller,'load',side_effect=AssertionError('inactive path must not inspect task database')) as load:
            self.assertIsNone(controller._archive_fit_launch_gate(object(),self.task,idle_hint=4))
            load.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
