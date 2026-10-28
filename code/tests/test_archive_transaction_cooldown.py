import importlib.util
import math
from pathlib import Path
import unittest

SRC=Path(__file__).resolve().parents[1]/'source'/'cold_auto_compaction.py'
spec=importlib.util.spec_from_file_location("cold_auto_compaction_staged",SRC)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ArchiveCooldownTests(unittest.TestCase):
    def setUp(self):
        self.valid={
            "latest_transaction_id":"0123456789abcdef0123456789abcdef",
            "latest_journal_transaction_id":"0123456789abcdef0123456789abcdef",
            "latest_journal_state":"complete",
            "latest_transaction_completed_utc":1000.0,
        }

    def test_initial_recent_transaction_backs_off(self):
        self.assertEqual(module.archive_transaction_cooldown_reason(self.valid,1000.0),
                         "recent_archive_transaction_cooldown")

    def test_inside_window_backs_off_and_at_boundary_allows(self):
        self.assertEqual(module.archive_transaction_cooldown_reason(self.valid,1359.999),
                         "recent_archive_transaction_cooldown")
        self.assertIsNone(module.archive_transaction_cooldown_reason(self.valid,1360.0))

    def test_elapsed_past_window_allows(self):
        self.assertIsNone(module.archive_transaction_cooldown_reason(self.valid,1800.0))

    def test_future_completion_fails_closed(self):
        self.assertEqual(module.archive_transaction_cooldown_reason(self.valid,999.0),
                         "archive_transaction_completion_time_in_future")

    def test_malformed_or_missing_timestamp_fails_closed(self):
        for value in ("1000",None,float("nan"),float("inf"),True):
            b=dict(self.valid,latest_transaction_completed_utc=value)
            self.assertEqual(module.archive_transaction_cooldown_reason(b,2000.0),
                             "archive_transaction_completion_time_invalid")

    def test_wrong_transaction_id_or_state_fails_closed(self):
        wrong=dict(self.valid,latest_journal_transaction_id="f"*32)
        state=dict(self.valid,latest_journal_state="started")
        self.assertEqual(module.archive_transaction_cooldown_reason(wrong,2000.0),
                         "archive_transaction_identity_invalid")
        self.assertEqual(module.archive_transaction_cooldown_reason(state,2000.0),
                         "archive_transaction_identity_invalid")

    def test_guard_is_after_both_baseline_validations(self):
        source=SRC.read_text()
        needle="baseline=baseline_identity()"
        self.assertEqual(source.count(needle),2)
        for block in source.split(needle)[1:]:
            self.assertIn("archive_transaction_cooldown_reason(baseline,now_epoch)",block[:180])

if __name__=="__main__":
    unittest.main()
