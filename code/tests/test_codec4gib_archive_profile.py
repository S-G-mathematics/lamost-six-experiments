import sys
import unittest
import hashlib
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / 'source'))

import batch_plan
import cold_auto_compaction as auto
import archive_fit_admission as admission
from unittest.mock import patch


class Codec4GiBProfileTests(unittest.TestCase):
    def test_profile_limits_are_explicit_and_bounded(self):
        self.assertEqual(batch_plan.CODEC_LARGE_PROFILE, 'bounded-5400-codec4gib64')
        self.assertEqual(batch_plan.CODEC_LARGE_MAX_BYTES, 4 * (1 << 30))
        self.assertEqual(batch_plan.CODEC_LARGE_MAX_GROUPS, 64)
        self.assertEqual(batch_plan.CODEC_LARGE_TEMP_MAX_BYTES, 8 * (1 << 30))
        self.assertEqual(batch_plan.CODEC_LARGE_WALL_SECONDS, 5400)
        self.assertEqual(auto.CODEC_LARGE_PROFILE, batch_plan.CODEC_LARGE_PROFILE)
        self.assertEqual(auto.CODEC_LARGE_WRAPPER_WALL_SECONDS, 5460)

    def test_new_profile_batch_config_and_disk_formula(self):
        cfg = auto.batch_config('reversible-xz-v1', batch_plan.CODEC_LARGE_PROFILE)
        self.assertEqual(cfg['batch_policy'], 'storage-followup-codec')
        self.assertEqual(cfg['max_bytes'], 4 * (1 << 30))
        self.assertEqual(cfg['max_groups'], 64)
        self.assertEqual(cfg['codec_temp_budget_bytes'], 8 * (1 << 30))
        self.assertEqual(cfg['wall_seconds'], 5400)
        self.assertEqual(cfg['archive_io_profile'], batch_plan.CODEC_LARGE_PROFILE)
        tail = 123456789
        self.assertEqual(batch_plan.codec_multigroup_disk_required_bytes(tail, cfg['max_bytes']),
                         4 * (1 << 30) + 14 * (1 << 30) + 2 * (1 << 30) + tail)
        runner_source = (HERE / 'source' / 'run_batch.py').read_text()
        self.assertIn('codec_multigroup_disk_required_bytes(codec_tail_bytes,policy[\'max_bytes\'])', runner_source)

    def test_legacy_profile_remains_unchanged(self):
        cfg = auto.batch_config('reversible-xz-v1', batch_plan.CODEC_MULTIGROUP_PROFILE)
        self.assertEqual(cfg['max_bytes'], 1 << 30)
        self.assertEqual(cfg['max_groups'], 64)
        self.assertEqual(cfg['codec_temp_budget_bytes'], 4 * (1 << 30))
        self.assertEqual(cfg['wall_seconds'], 1800)
        self.assertEqual(auto.outer_wrapper_wall_seconds(batch_plan.CODEC_MULTIGROUP_PROFILE), 1860)
        self.assertEqual(batch_plan.codec_multigroup_disk_required_bytes(7),
                         (1 << 30) + 10 * (1 << 30) + 2 * (1 << 30) + 7)
        self.assertEqual(auto.CODEC_LARGE_TRANSIENT_DISK_RESERVE_BYTES, 14 * (1 << 30))

    def test_profile_rejects_wrong_codec_and_unknown_name(self):
        with self.assertRaises(ValueError):
            auto.batch_config(None, batch_plan.CODEC_LARGE_PROFILE)
        with self.assertRaises(ValueError):
            auto.batch_config('wrong-codec', batch_plan.CODEC_LARGE_PROFILE)
        with self.assertRaises(ValueError):
            auto.batch_config('reversible-xz-v1', 'bounded-5400-codec8gib64')
        with self.assertRaises(ValueError):
            auto.outer_wrapper_wall_seconds('bounded-5400-codec8gib64')

    def test_disk_formula_rejects_unrecognized_or_invalid_bounds(self):
        for bad in (0, 2 * (1 << 30), -1, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                batch_plan.codec_multigroup_disk_required_bytes(10, bad)
        for bad_tail in (-1, True):
            with self.subTest(tail=bad_tail), self.assertRaises(ValueError):
                batch_plan.codec_multigroup_disk_required_bytes(bad_tail, 4 * (1 << 30))

    def test_codec_overlap_policy_fails_closed_until_separately_qualified(self):
        frozen = {}
        self.assertFalse(admission.native_codec_overlap_policy_allowed(
            HERE, frozen,
            archive_io_profile=batch_plan.CODEC_LARGE_PROFILE,
            batch_policy='storage-followup-codec',
            storage_codec_policy='reversible-xz-v1'))
        self.assertFalse(admission.native_codec_overlap_policy_allowed(
            HERE, frozen,
            archive_io_profile=batch_plan.CODEC_LARGE_PROFILE,
            batch_policy='storage-followup-codec',
            storage_codec_policy=None))
        current = {'archive_fit_admission.py': 'a' * 64}
        with self.assertRaisesRegex(ValueError, 'codec4_profile_focused_tests_missing'):
            admission._validate_codec4_profile_receipt(HERE, {}, current)
        codec4_op = {'owner_operation': admission.OWNER_OPERATION,
                     'batch_policy': admission.CODEC_BATCH_POLICY,
                     'archive_io_profile': admission.CODEC4_IO_PROFILE,
                     'storage_codec_policy': admission.CODEC_STORAGE_POLICY}
        with patch.object(admission, '_selected_policy', return_value={'profile':'codec4','document':{'archive_operation':codec4_op},'policy_sha256':'a'*64,'qualification_sha256':'b'*64,'source_sha256':current,'native_input_manifests':{}}), patch.object(admission,'native_fit_proof',return_value={}):
            proof=admission.qualify_candidate(HERE,{}, {}, {}, {})
        self.assertEqual(proof['overlap_profile'],'codec4')
        self.assertEqual(proof['archive_operation'],codec4_op)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            testfile = root / 'tests' / 'test_codec4gib_archive_profile.py'
            testfile.parent.mkdir()
            testfile.write_bytes(b'fixture test bytes')
            test_sha = hashlib.sha256(testfile.read_bytes()).hexdigest()
            receipt = {
                'schema': 'lamost-codec4-profile-focused-tests/1',
                'status': 'passed',
                'source_sha256': current,
                'test_file_sha256': {'tests/test_codec4gib_archive_profile.py': test_sha},
                'expected_test_count': 6, 'passed_test_count': 6,
                'failed_test_count': 0, 'fit_attempts_started': 0,
                'limits': {'address_space_limit_bytes': 1 << 30,
                           'wall_seconds': 60, 'native_threads': 1, 'nice': 19},
            }
            receipt_path = root / 'reports' / 'engineering_audits' / 'codec4.json'
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps(receipt, sort_keys=True))
            qdoc = {'codec4_profile_tests': {
                'status': 'passed',
                'receipt_path': 'reports/engineering_audits/codec4.json',
                'receipt_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                'test_file_sha256': {'tests/test_codec4gib_archive_profile.py': test_sha},
            }}
            result = admission._validate_codec4_profile_receipt(root, qdoc, current)
            self.assertEqual(result['receipt_sha256'], qdoc['codec4_profile_tests']['receipt_sha256'])
            qdoc['codec4_profile_tests']['receipt_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'codec4_profile_receipt_sha_mismatch'):
                admission._validate_codec4_profile_receipt(root, qdoc, current)


if __name__ == '__main__':
    unittest.main()
