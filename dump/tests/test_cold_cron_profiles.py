import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "source" / "complete_delivery.py"
spec = importlib.util.spec_from_file_location("complete_delivery_staged", SOURCE)
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


class ColdCronProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cron-profile-")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_raw_codec_and_bounded_1800_forms_are_supported(self):
        base = str(self.root)
        rt = base + "/runtime_20261025"
        command = f"*/5 * * * * {base}/venv/bin/python {rt}/source/cold_auto_compaction.py"
        redirect = f">/dev/null 2>&1 # {delivery.TAG_COLD}"
        expected = (
            command + " " + redirect,
            command + " --storage-codec-policy reversible-xz-v1 " + redirect,
            command + " --archive-io-profile bounded-1800 " + redirect,
        )
        self.assertEqual(delivery.expected_cold_cron_lines(self.root), expected)
        lines = [line + "\n" for line in expected]
        kept, removed, unrecognized = delivery.cron_filter(lines, self.root)
        self.assertEqual(removed, lines)
        self.assertEqual(kept, [])
        self.assertEqual(unrecognized, [])

    def test_only_exact_supported_lines_are_removed(self):
        raw, codec, io = delivery.expected_cold_cron_lines(self.root)
        unrelated = "*/5 * * * * /opt/harbor/watch # HARBOR\n"
        foreign_tag = "*/5 * * * * /tmp/cold_auto_compaction.py >/dev/null 2>&1 # LAMOST_COLD_STORAGE_AIRBAG\n"
        lines = [raw + "\n", codec + "\n", io + "\n", unrelated, foreign_tag]
        kept, removed, unrecognized = delivery.cron_filter(lines, self.root)
        self.assertEqual(removed, lines[:3])
        self.assertEqual(kept, lines[3:])
        self.assertEqual(unrecognized, [foreign_tag])

    def test_unknown_and_combined_archive_profiles_fail_closed(self):
        raw, _codec, io = delivery.expected_cold_cron_lines(self.root)
        unknown = io.replace("--archive-io-profile bounded-1800", "--archive-io-profile bounded-600") + "\n"
        combined = raw.replace(" >/dev/null 2>&1 ", " --archive-io-profile bounded-1800 --storage-codec-policy reversible-xz-v1 >/dev/null 2>&1 ") + "\n"
        kept, removed, unrecognized = delivery.cron_filter([unknown, combined], self.root)
        self.assertEqual(kept, [unknown, combined])
        self.assertEqual(removed, [])
        self.assertEqual(unrecognized, [unknown, combined])


if __name__ == "__main__":
    unittest.main()
