import ast
import json
import sys
import tempfile
import types
import unittest
import unittest.mock
from pathlib import Path

# Portable layout contract: when copied to runtime_20261025/tests, this resolves
# runtime_20261025/source/finalize_project.py without relying on the working directory.
CANDIDATE_SOURCE = Path(__file__).resolve().parents[1] / 'source' / 'finalize_project.py'

class TestE3Rep1PublicationDisclosure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_text = CANDIDATE_SOURCE.read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.source_text)
        cls.funcs = {n.name: n for n in cls.tree.body if isinstance(n, ast.FunctionDef)}
        cls.namespace = {'Path': Path, 'EvidenceError': RuntimeError}
        nodes = [cls.funcs['_e3_rep1_publication_disclosure'],
                 cls.funcs['_insert_e3_rep1_publication_disclosure'],
                 cls.funcs['sanitize_operational_json']]
        cls.namespace.update({'ast': ast, 'json': json})
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(CANDIDATE_SOURCE), 'exec'),
             cls.namespace)

    def write_valid_note(self, runtime):
        reports = runtime / 'reports'
        reports.mkdir(exist_ok=True)
        note = reports / 'E3_RF_REP1_PUBLICATION_LIMITATION.md'
        note.write_text(
            'The selected model has no fit_publication.json. Its pipeline, selected '
            'configuration, fit result and validation record remain present and '
            'hash-consistent. This missing publication receipt does not by itself '
            'invalidate the recorded successful E3 evaluation. No receipt has been '
            'reconstructed.',
            encoding='utf-8')
        return note

    def test_wiring_and_placement_before_e4_and_report_write(self):
        self.assertIn('_e3_rep1_publication_disclosure', self.funcs)
        self.assertIn('_insert_e3_rep1_publication_disclosure', self.funcs)
        calls = [n for n in ast.walk(self.funcs['make_final_report'])
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == '_insert_e3_rep1_publication_disclosure']
        self.assertEqual(len(calls), 1)
        writes = [n for n in ast.walk(self.funcs['make_final_report'])
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == 'write_text']
        self.assertTrue(writes)
        self.assertLess(min(n.lineno for n in calls), min(n.lineno for n in writes))
        with tempfile.TemporaryDirectory(prefix='e3_disclosure_') as td:
            runtime = Path(td)
            self.write_valid_note(runtime)
            lines = ['## Experiment 3', '## Experiment 4 - fixture']
            result = self.namespace['_insert_e3_rep1_publication_disclosure'](lines, runtime)
            e4 = next(i for i, line in enumerate(result) if line.startswith('## Experiment 4'))
            disclosure = result[e4 - 2]
            self.assertIn('no fit_publication.json', disclosure)
            self.assertIn('hash-consistent', disclosure)
            self.assertIn('no receipt was reconstructed', disclosure)
            self.assertLess(result.index(disclosure), e4)

    def test_archive_sanitizer_removes_ownership_nonces_recursively(self):
        module = types.ModuleType('reason_text_curation')
        module.sanitize_reason_text = lambda value: value
        with unittest.mock.patch.dict(sys.modules, {'reason_text_curation': module}):
            original = {
                'hold_nonce': 'private-hold',
                'nested': {'nonce': 123, 'pid': 9876, 'operation_id': 'op-7'},
                'attempt_id': 'attempt-4', 'task_sha256': 'abc123',
                'peak_tree_rss_bytes': 456789,
            }
            cleaned = self.namespace['sanitize_operational_json'](original)
        encoded = json.dumps(cleaned, sort_keys=True)
        self.assertNotIn('hold_nonce', encoded)
        self.assertNotIn('private-hold', encoded)
        self.assertNotIn('nonce', encoded)
        self.assertNotIn('9876', encoded)
        self.assertEqual(cleaned['nested']['operation_id'], 'op-7')
        self.assertEqual(cleaned['attempt_id'], 'attempt-4')
        self.assertEqual(cleaned['task_sha256'], 'abc123')
        self.assertEqual(cleaned['peak_tree_rss_bytes'], 456789)

    def test_missing_note_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix='e3_disclosure_missing_') as td:
            with self.assertRaises(RuntimeError):
                self.namespace['_e3_rep1_publication_disclosure'](Path(td))

    def test_malformed_note_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix='e3_disclosure_malformed_') as td:
            runtime = Path(td)
            reports = runtime / 'reports'
            reports.mkdir()
            (reports / 'E3_RF_REP1_PUBLICATION_LIMITATION.md').write_text(
                'A publication file is missing.', encoding='utf-8')
            with self.assertRaises(RuntimeError):
                self.namespace['_e3_rep1_publication_disclosure'](runtime)

if __name__ == '__main__':
    unittest.main()
