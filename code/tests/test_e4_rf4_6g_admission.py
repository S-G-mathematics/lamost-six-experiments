import importlib.util
import json
import pathlib
import struct
import numpy as np
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve()
STAGE = HERE.parent.parent
RUNTIME = STAGE if (STAGE / 'source' / 'admission_evidence.py').is_file() else STAGE.parents[1]
sys.path.insert(0, str(RUNTIME / 'source'))
SPEC = importlib.util.spec_from_file_location('rf4_e4_staged_controller', STAGE / 'source' / 'controller.py')
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)
REAL_POLICY_LOADER = controller._rf4_e4_6g_policy

def npy_header(shape, descr):
    text = repr({'descr': descr, 'fortran_order': False, 'shape': shape})
    raw = text.encode('latin1')
    pad = (16 - ((10 + len(raw) + 1) % 16)) % 16
    raw += b' ' * pad + b'\n'
    return b'\x93NUMPY\x01\x00' + struct.pack('<H', len(raw)) + raw

def write_npz(path, rows=84000, xrows=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as z:
        z.writestr('X.npy', npy_header((xrows if xrows is not None else rows, 6), '<f4'))
        z.writestr('y.npy', npy_header((rows,), '<i8'))
        z.writestr('ids.npy', npy_header((rows,), '|S8'))

class RF4E4Admission6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.old_r = controller.R
        self.old_defs = controller.DEFINITIONS
        controller.R = self.root
        self.train_key = 'e4/rep_2/treatment/F_half/smote'
        self.fit_key = 'e4/rep_2/fit/treatment/random_forest/F_half_smote'
        for name in controller.RF4_SOURCE_NAMES:
            f=self.root/'source'/name; f.parent.mkdir(parents=True, exist_ok=True); f.write_text('adapter '+name)
        artifact = self.root / 'artifacts' / self.train_key
        parent = self.root / 'artifacts' / 'e4/rep_2/cohort/F_half'
        parent.mkdir(parents=True)
        artifact.mkdir(parents=True)
        self.task = {
            'key': self.fit_key, 'experiment': 4, 'rep': 2, 'kind': 'fit',
            'method': 'random_forest', 'route': 'treatment', 'condition': 'F_half_smote',
            'train_key': self.train_key, 'dependencies': [self.train_key],
            'status': 'waiting_dependency', 'attempts': [], 'reuse_pipeline': False,
            'task_sha256': 'a' * 64,
        }
        controller.DEFINITIONS = {self.fit_key: dict(self.task)}
        self.dep = {
            'key': self.train_key, 'experiment': 4, 'rep': 2, 'kind': 'e4_treatment',
            'status': 'validated_terminal', 'validation_state': 'validated',
            'cohort_key': 'e4/rep_2/cohort/F_half', 'artifact_dir': str(artifact),
            'result': {'key': self.train_key, 'status': 'successful', 'artifact_path': str(artifact),
                       'metadata': {'parent': str(parent)},
                       'validation': {'status': 'validated', 'task_key': self.train_key, 'files': {'data.npz': 'b' * 64}}},
        }
        counts = [12000] * 7
        meta = {'kind': 'e4_treatment', 'task_key': self.train_key, 'parent': str(parent),
                'counts_before': [10000] * 7, 'counts_after': counts}
        val = {'status': 'validated', 'task_key': self.train_key,
               'files': {'data.npz': 'b' * 64}}
        (artifact / 'metadata.json').write_text(json.dumps(meta))
        (artifact / 'validation.json').write_text(json.dumps(val))
        write_npz(artifact / 'data.npz', rows=sum(counts))
        self.policy = {'policy_sha256': 'c' * 64, 'evidence_sha256': 'd' * 64}
        self.policy_patch = mock.patch.object(controller, '_rf4_e4_6g_policy', return_value=self.policy)
        self.policy_patch.start()
        self.registry_patch = mock.patch.object(controller, 'load_registry_record_for_profile', return_value=self.dep)
        self.registry_patch.start()

    def tearDown(self):
        self.policy_patch.stop()
        self.registry_patch.stop()
        controller.R = self.old_r
        controller.DEFINITIONS = self.old_defs
        self.tmp.cleanup()

    def test_exact_e4_rep2_treatment_metadata_and_headers_eligible_at_6g(self):
        evidence = controller._e4_treatment_rf4_6g_eligible(self.task)
        self.assertEqual(evidence['reservation_gib'], 6)
        self.assertEqual(evidence['train_rows'], 84000)
        self.assertEqual(controller.worker_reservation_bytes(self.task), 6 * controller.GIB)
        self.assertEqual(controller.candidate_cpu_reservation_units(self.task), 4)

    def test_attempt_history_and_wrong_scope_never_receive_new_profile(self):
        for changes in (
            {'attempts': [{'attempt_id': 'old'}]},
            {'experiment': 5}, {'rep': 1}, {'route': 'direct'},
            {'kind': 'eval'}, {'method': 'extra_trees'}, {'reuse_pipeline': True},
        ):
            t = dict(self.task); t.update(changes)
            self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(t))
        self.assertEqual(controller.worker_reservation_bytes({'attempts': [], 'kind': 'fit', 'method': 'random_forest'}), 10 * controller.GIB)

    def test_wrong_or_missing_provenance_defaults_out_of_6g_scope(self):
        self.dep['validation_state'] = 'failed'
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))
        self.dep['validation_state'] = 'validated'
        self.dep['result']['status'] = 'failed'
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))

    def test_generated_append_dependency_uses_native_counts_metadata(self):
        self.dep['kind'] = 'e4_append'
        artifact = pathlib.Path(self.dep['artifact_dir'])
        meta = json.loads((artifact / 'metadata.json').read_text())
        meta['kind'] = 'e4_append'
        (artifact / 'metadata.json').write_text(json.dumps(meta))
        self.assertEqual(controller._e4_treatment_rf4_6g_eligible(self.task)['reservation_gib'], 6)

    def test_training_rows_above_evidence_ceiling_rejected(self):
        artifact = pathlib.Path(self.dep['artifact_dir'])
        meta_path = artifact / 'metadata.json'
        meta = json.loads(meta_path.read_text())
        meta['counts_after'] = [18000] * 7
        meta_path.write_text(json.dumps(meta))
        write_npz(artifact / 'data.npz', rows=126000)
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))

    def test_npz_wrong_feature_or_member_shape_rejected_without_array_load(self):
        artifact = pathlib.Path(self.dep['artifact_dir'])
        write_npz(artifact / 'data.npz', rows=84000, xrows=83999)
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))
        write_npz(artifact / 'data.npz', rows=84000)
        with zipfile.ZipFile(artifact / 'data.npz', 'a') as z:
            z.writestr('extra.npy', b'not-a-model')
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))

    def test_recorded_6g_resume_preserves_reservation_cpu_and_rf4_execution_profile(self):
        recorded = dict(self.task)
        recorded['admission_profile_id'] = controller.RF4_E4_6G_PROFILE_ID
        recorded['admission_reservation_bytes'] = 6 * controller.GIB
        recorded['admission_resource_policy'] = {
            'admission_profile_id': controller.RF4_E4_6G_PROFILE_ID,
            'admission_reservation_bytes': 6 * controller.GIB,
            'execution_policy': controller.RF4_EXECUTION_POLICY,
            'resource_profile': controller.RF4_RESOURCE_PROFILE,
            'cpu_reservation_units': 4,
        }
        recorded['attempts'] = [{'resource_profile': dict(recorded['admission_resource_policy'])}]
        self.assertEqual(controller.worker_reservation_bytes(recorded), 6 * controller.GIB)
        self.assertEqual(controller.worker_cpu_reservation_units(recorded), 4)
        self.assertEqual(controller.promoted_reservation_bytes(recorded, 7 * controller.GIB), 10 * controller.GIB)
        recorded['adaptive_promoted_heavy']=True
        self.assertTrue(controller._has_recorded_e4_treatment_rf6_profile(recorded))
        self.assertEqual(controller.worker_reservation_bytes(recorded),10*controller.GIB)

    def test_real_compressed_npz_header_fixture_is_accepted_without_array_loading(self):
        path = self.root / 'small_real_npz.npz'
        np.savez_compressed(path, X=np.zeros((3, 6), dtype=np.float32),
                            y=np.zeros(3, dtype=np.int64), ids=np.array(['a', 'b', 'c']))
        self.assertTrue(controller._e4_rf_npz_headers_match(path, 3))

    def test_legacy_rf4_recorded_attempt_stays_10g(self):
        old = {'attempts': [{'resource_profile': {
            'execution_policy': controller.RF4_EXECUTION_POLICY,
            'resource_profile': controller.RF4_RESOURCE_PROFILE,
            'admission_reservation_bytes': 10 * controller.GIB,
            'cpu_reservation_units': 4,
        }}]}
        self.assertEqual(controller.worker_reservation_bytes(old), 10 * controller.GIB)
        self.assertEqual(controller.worker_cpu_reservation_units(old), 4)

    def test_policy_absent_disables_lower_profile_and_bad_freeze_hash_fails_closed(self):
        self.assertIsNone(REAL_POLICY_LOADER({}))
        with self.assertRaises(RuntimeError):
            REAL_POLICY_LOADER({controller.RF4_E4_6G_POLICY_FIELD: 'bad'})

    def test_policy_binds_ten_observations_and_adapter_hashes(self):
        manifests=self.root/'manifests'; audits=self.root/'reports/engineering_audits'
        manifests.mkdir(parents=True); audits.mkdir(parents=True)
        source_map={name:controller.sha(self.root/'source'/name) for name in controller.RF4_SOURCE_NAMES}
        evidence={'schema_version':'lamost-rf4-e4-prospective-admission-evidence/1',
                  'inputs':{'source_files':[{'path':'source/'+name,'sha256':digest} for name,digest in source_map.items()]},
                  'observed':{'fits':[{'key':f'e4/rep_2/fit/treatment/random_forest/case_{i}',
                     'fit_result':{'training_rows':90000},'final_fit_phase_count':1,
                     'max_phase_tree_rss_kib':1024} for i in range(10)]}}
        ep=audits/pathlib.Path(controller.RF4_E4_6G_EVIDENCE_REL).name
        ep.write_text(json.dumps(evidence,sort_keys=True))
        evidence_sha=controller.sha(ep)
        policy={'schema':'lamost-e4-rf4-treatment-6gib-policy/1','status':'qualified',
          'scope':{'experiments':[4],'kind':'fit','methods':['random_forest'],'never_attempted':True,
                   'reuse_pipeline':False,'route':'treatment','rep':2,'max_training_rows':125955},
          'fit_n_jobs':4,'prediction_n_jobs':1,'native_threads':1,'admission_reservation_gib':6,
          'worker_memory_limit_gib':10,'trial_timeout_seconds':600,'phase_timeout_seconds':600,
          'termination_grace_seconds':30,'cpu_reservation_units':4,'evidence_path':controller.RF4_E4_6G_EVIDENCE_REL,
          'evidence_sha256':evidence_sha,'source_sha256':source_map}
        pp=manifests/pathlib.Path(controller.RF4_E4_6G_POLICY_REL).name
        pp.write_text(json.dumps(policy,sort_keys=True))
        pdigest=controller.sha(pp)
        (manifests/'freeze.json').write_text(json.dumps({controller.RF4_E4_6G_POLICY_FIELD:pdigest,'source_sha256':source_map}))
        with mock.patch.object(controller,'RF4_E4_6G_EVIDENCE_SHA',evidence_sha):
            loaded=REAL_POLICY_LOADER({controller.RF4_E4_6G_POLICY_FIELD:pdigest})
            self.assertEqual(loaded['policy_sha256'],pdigest)
            (self.root/'source'/controller.RF4_SOURCE_NAMES[0]).write_text('tampered')
            with self.assertRaises(RuntimeError):
                REAL_POLICY_LOADER({controller.RF4_E4_6G_POLICY_FIELD:pdigest})

    def test_candidate_policy_activates_against_exact_public_evidence_when_present(self):
        freeze_path=RUNTIME/'manifests/freeze.json'
        if not freeze_path.is_file():
            self.skipTest('no portable candidate freeze in isolated source stage')
        frozen=json.loads(freeze_path.read_text())
        if controller.RF4_E4_6G_POLICY_FIELD not in frozen:
            self.skipTest('candidate-only E4 RF6 policy is absent')
        old_root=controller.R;controller.R=RUNTIME
        try:
            policy=REAL_POLICY_LOADER(frozen)
            self.assertIsNotNone(policy)
            self.assertEqual(policy['policy_sha256'],frozen[controller.RF4_E4_6G_POLICY_FIELD])
            self.assertEqual(policy['evidence_sha256'],controller.RF4_E4_6G_EVIDENCE_SHA)
        finally:
            controller.R=old_root

    def test_same_task_checkpoint_or_output_prevents_fresh_lower_reservation(self):
        artifact = self.root / 'artifacts' / self.fit_key
        artifact.mkdir(parents=True)
        (artifact / 'pipeline.joblib').write_bytes(b'x')
        self.assertIsNone(controller._e4_treatment_rf4_6g_eligible(self.task))

if __name__ == '__main__':
    unittest.main()

