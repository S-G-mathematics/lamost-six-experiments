import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/'source'/'complete_delivery.py'
spec=importlib.util.spec_from_file_location('staged_complete_delivery',SOURCE)
delivery=importlib.util.module_from_spec(spec);spec.loader.exec_module(delivery)

class ExactColdCronCleanupTests(unittest.TestCase):
    def test_exact_codec_cron_replaced_with_owned_entries_only(self):
        with tempfile.TemporaryDirectory(prefix='cron_filter_fixture_') as td:
            root=Path(td);expected=delivery.expected_cron_lines(root)
            codec=delivery.expected_cold_cron_lines(root)[1]+'\n'
            unrelated_same_tag='*/5 * * * * /tmp/other_cold_job # '+delivery.TAG_COLD+'\n'
            unknown_flag=codec.rstrip('\n').replace(' >/dev/null',' --unrecognized-option >/dev/null')+'\n'
            harbor='*/5 * * * * /opt/harbor/watch # HARBOR\n'
            lines=[expected[delivery.TAG_AIRBAG]+'\n',expected[delivery.TAG_INDEX]+'\n',codec,unrelated_same_tag,unknown_flag,harbor]
            kept,removed,unknown=delivery.cron_filter(lines,root=root)
            self.assertEqual(removed,lines[:3])
            self.assertEqual(kept,lines[3:])
            self.assertEqual(unknown,[unrelated_same_tag,unknown_flag])

    def test_raw_exact_cold_line_and_existing_selftest_still_pass(self):
        self.assertEqual(delivery.expected_cold_cron_lines()[0],delivery.expected_cron_lines()[delivery.TAG_COLD])
        receipt=delivery.self_test()
        self.assertEqual(receipt['status'],'self_test_passed')
        self.assertTrue(receipt['all_three_owned_cron_entries_removed'])
        self.assertTrue(receipt['unrelated_same_tag_lines_preserved'])

if __name__=='__main__':unittest.main()
