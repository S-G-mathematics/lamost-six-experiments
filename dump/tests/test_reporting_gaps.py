import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STAGE = Path(__file__).resolve().parents[1]
LIVE_SOURCE = STAGE / 'source'
sys.path.insert(0, str(LIVE_SOURCE))
spec = importlib.util.spec_from_file_location('staged_reporting_gaps', STAGE / 'source' / 'reporting.py')
reporting = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reporting)
sys.path.remove(str(LIVE_SOURCE))


class ReportingGapTests(unittest.TestCase):
    def test_source_class_rate_uses_source_row_and_off_diagonal(self):
        task = {'task_key': 'e5/rep_1/corrupt/label_noise/0.1', 'rep': 1,
                'mechanism': 'label_noise', 'planned_rate': 0.1, 'realized_rate': 0.08}
        matrix = [[0, 2, 0, 0, 0, 0, 0],
                  [3, 7, 0, 0, 0, 0, 0]] + [[0] * 7 for _ in range(5)]
        transitions = [{'task_key': task['task_key'], 'mechanism': 'label_noise',
                        'old_class': old, 'new_class': new, 'transition_count': count}
                       for old, row in enumerate(matrix) for new, count in enumerate(row)]
        rows = reporting._label_noise_source_class_rates([task], transitions, {'1':[20,100,0,10,10,10,10]})
        self.assertEqual(len(rows), 7)
        self.assertEqual((rows[0]['original_source_class_count'], rows[0]['affected_source_class_count'], rows[0]['changed_label_count']), (20, 2, 2))
        self.assertEqual(rows[0]['realized_source_class_corruption_rate'], 0.1)
        self.assertEqual((rows[1]['original_source_class_count'], rows[1]['affected_source_class_count'], rows[1]['changed_label_count']), (100, 10, 3))
        self.assertEqual(rows[1]['realized_source_class_corruption_rate'], 0.03)
        self.assertEqual(rows[1]['source_class_label'], 'F')
        self.assertEqual(rows[2]['rate_status'], 'zero_source_support')
        self.assertIsNone(rows[2]['realized_source_class_corruption_rate'])

    def test_missing_transition_matrix_is_unavailable_not_zero(self):
        rows = reporting._label_noise_source_class_rates(
            [{'task_key': 'x', 'rep': 2, 'mechanism': 'label_noise'}], [], {'2':[5]*7})
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(row['rate_status'] == 'transition_matrix_unavailable' for row in rows))
        self.assertTrue(all(row['original_source_class_count'] == 5 and
                            row['realized_source_class_corruption_rate'] is None for row in rows))

    def test_original_counts_come_from_unmodified_fit_role_labels(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as td:
            rt=Path(td)
            roles=rt/'cache'/'roles'
            roles.mkdir(parents=True)
            np.savez_compressed(roles/'rep_1.npz', y_fit=np.asarray([0,0,1,2,2,2],dtype=np.int8))
            counts=reporting._original_fit_class_counts(rt,[
                {'rep':1,'mechanism':'label_noise'}])
            self.assertEqual(counts['1'],[2,1,3,0,0,0,0])

    def test_set_size_pairs_only_matching_rep_and_generator(self):
        cases = [
            {'key': 'clean1', 'scientific_case': True, 'experiment': 5, 'rep': 1, 'method': 'RF', 'route': 'synthetic',
             'generator': 'gmm', 'condition': 'clean', 'outcome': 'successful'},
            {'key': 'corrupt1', 'scientific_case': True, 'experiment': 5, 'rep': 1, 'method': 'RF', 'route': 'synthetic',
             'generator': 'gmm', 'mechanism': 'label_noise', 'rate': .1, 'outcome': 'successful'},
            {'key': 'clean2', 'scientific_case': True, 'experiment': 5, 'rep': 2, 'method': 'RF', 'route': 'synthetic',
             'generator': 'copula', 'condition': 'clean', 'outcome': 'successful'},
            {'key': 'corrupt2', 'scientific_case': True, 'experiment': 5, 'rep': 2, 'method': 'RF', 'route': 'synthetic',
             'generator': 'copula', 'mechanism': 'label_noise', 'rate': .1, 'outcome': 'successful'},
            {'key': 'clean_wrong', 'scientific_case': True, 'experiment': 5, 'rep': 2, 'method': 'RF', 'route': 'synthetic',
             'generator': 'gmm', 'condition': 'clean', 'outcome': 'successful'},
        ]
        class_rows = [{'key': key, 'class_id': '0', 'recall': .5, 'coverage': .9, 'set_size': 2.0}
                      for key in ('clean1', 'corrupt1', 'clean2', 'corrupt2', 'clean_wrong')]
        class_rows[1]['set_size'] = None
        pairs = reporting._paired_per_class(cases, class_rows)
        p1 = next(x for x in pairs if x['corrupted_key'] == 'corrupt1' and x['class_id'] == '0')
        self.assertTrue(p1['paired_available'])
        self.assertEqual(p1['recall_difference_a_minus_b'], 0.0)
        self.assertEqual(p1['coverage_difference_a_minus_b'], 0.0)
        self.assertIsNone(p1['set_size_difference_a_minus_b'])
        self.assertEqual(p1['clean_key'], 'clean1')
        p2 = next(x for x in pairs if x['corrupted_key'] == 'corrupt2' and x['class_id'] == '0')
        self.assertEqual(p2['clean_key'], 'clean2')
        self.assertEqual(p2['set_size_difference_a_minus_b'], 0.0)
        self.assertEqual(p2['clean_set_size'], 2.0)

    def test_summary_uses_available_pairs_sample_sd_and_n(self):
        rows = [
            {'mechanism': 'label_noise', 'rep': 1, 'paired_available': True,
             'recall_difference_a_minus_b': .2, 'coverage_difference_a_minus_b': .1,
             'set_size_difference_a_minus_b': 1.0},
            {'mechanism': 'label_noise', 'rep': 2, 'paired_available': True,
             'recall_difference_a_minus_b': .4, 'coverage_difference_a_minus_b': .3,
             'set_size_difference_a_minus_b': 3.0},
            {'mechanism': 'label_noise', 'rep': 3, 'paired_available': False,
             'recall_difference_a_minus_b': None, 'coverage_difference_a_minus_b': None,
             'set_size_difference_a_minus_b': None},
        ]
        summary = reporting._condition_paired_summary(rows, ('mechanism',),
            ('recall_difference_a_minus_b', 'coverage_difference_a_minus_b',
             'set_size_difference_a_minus_b'))[0]
        self.assertEqual(summary['available_repetitions'], 2)
        self.assertEqual(summary['unmatched_repetitions'], 1)
        self.assertEqual(summary['set_size_difference_a_minus_b_n'], 2)
        self.assertEqual(summary['set_size_difference_a_minus_b_mean'], 2.0)
        self.assertAlmostEqual(summary['set_size_difference_a_minus_b_sample_sd'], 2**0.5)
        self.assertEqual(summary['recall_difference_a_minus_b_n'], 2)

    def test_writer_emits_new_rate_table(self):
        names = ('_dataset_inventory_rows', '_e4_histogram_rows', '_e5_corruption_rows',
                 '_model_selection_rows', '_terminal_worker_cutoff_rows', '_resource_failure_rows',
                 '_evaluation_support_rows', '_e6_weight_rows')
        original = {name: getattr(reporting, name) for name in names}
        original_counts_fn = reporting._original_fit_class_counts
        reporting._original_fit_class_counts = lambda *_: {'1':[20,100,0,10,10,10,10]}
        reporting._dataset_inventory_rows = lambda *_: []
        reporting._e4_histogram_rows = lambda *_: []
        reporting._e5_corruption_rows = lambda *_: (
            [{'task_key': 'x', 'rep': 1, 'mechanism': 'label_noise',
              'planned_rate': .1, 'realized_rate': .1}],
            [{'task_key': 'x', 'rep': 1, 'mechanism': 'label_noise',
              'old_class': 0, 'new_class': 1, 'transition_count': 2}])
        reporting._model_selection_rows = lambda *_: []
        reporting._terminal_worker_cutoff_rows = lambda *_: []
        reporting._resource_failure_rows = lambda *_: ([], [])
        reporting._evaluation_support_rows = lambda *_: ([], [])
        reporting._e6_weight_rows = lambda *_: ([], [])
        try:
            with tempfile.TemporaryDirectory() as td:
                out = Path(td)
                counts = reporting._write_evidence_tables(td, [], out)
                with (out / 'E5_label_noise_source_class_rates.csv').open(
                        newline='', encoding='utf-8') as f:
                    saved = list(csv.DictReader(f))
                self.assertEqual(len(saved), 7)
                self.assertEqual(saved[0]['original_source_class_count'], '20')
                self.assertEqual(saved[0]['affected_source_class_count'], '2')
                self.assertEqual(saved[0]['changed_label_count'], '2')
                self.assertEqual(counts['E5_label_noise_source_class_rate_rows'], 7)
        finally:
            for name, value in original.items():
                setattr(reporting, name, value)
            reporting._original_fit_class_counts = original_counts_fn


if __name__ == '__main__':
    unittest.main()

