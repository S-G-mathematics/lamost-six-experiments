import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve()
PROJECT = next(parent for parent in HERE.parents if (parent / "runtime_20261025").is_dir())
STAGED_DIR = PROJECT / "runtime_20261025" / "staging" / "working_storage_archive_closure_20261030"
if STAGED_DIR == HERE.parent:
    FINALIZER_UNDER_TEST = STAGED_DIR / "finalize_project.py"
else:
    FINALIZER_UNDER_TEST = PROJECT / "runtime_20261025" / "source" / "finalize_project.py"
sys.path.insert(0, str(PROJECT / "runtime_20261025" / "source"))
spec = importlib.util.spec_from_file_location("staged_finalize_project", FINALIZER_UNDER_TEST)
f = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = f
spec.loader.exec_module(f)


class OperationalArchiveClosureTests(unittest.TestCase):
    def test_exact_nine_members_and_legacy_28_member_runtime_allowlist(self):
        out, records = [], []
        f._add_pinned_operational_source_closure(PROJECT, out, {}, records)
        expected = set(f.PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256)
        self.assertEqual({e.member for e in out}, expected)
        self.assertEqual(len(out), 9)
        self.assertEqual({r["archive_member"] for r in records}, expected)
        self.assertEqual(len(f.PINNED_PUBLIC_QUALIFIED_CLOSURE_SHA256), 28)
        manifest = {r["archive_member"]: r for r in records}
        for path, (digest, _category, _curation) in f.PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256.items():
            self.assertEqual(manifest[path]["source_sha256"], digest)
            self.assertEqual(manifest[path]["archive_sha256"], digest)

    def test_missing_and_mutated_pinned_files_fail_closed(self):
        relative = "code.py"
        payload = b"approved source"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(f, "PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256", {relative: (digest, "source", "exact")}):
                with self.assertRaisesRegex(f.EvidenceError, "missing"):
                    f._add_pinned_operational_source_closure(root, [], {}, [])
                path = root / relative
                path.write_bytes(payload + b"changed")
                with self.assertRaisesRegex(f.EvidenceError, "SHA mismatch"):
                    f._add_pinned_operational_source_closure(root, [], {}, [])

    def test_public_provenance_builder_wires_exact_closure_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            runtime = root / "runtime_20261025"
            (runtime / "manifests").mkdir(parents=True)
            for relative in f.PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256:
                src = PROJECT / relative
                dst = root / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            out = []
            with patch.object(f, "_add_resource_review_evidence", lambda *a, **k: []), \
                 patch.object(f, "_add_pinned_qualified_input_closure", lambda *a, **k: []):
                f._add_public_provenance(root, runtime, out)
            by_member = {entry.member: entry for entry in out}
            expected = set(f.PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256)
            self.assertTrue(expected.issubset(by_member))
            manifest = json.loads(by_member["runtime_20261025/manifests/public_scientific_provenance_manifest.json"].source)
            included = {row["archive_member"]: row for row in manifest["included"]}
            self.assertTrue(expected.issubset(included))
            for member in expected:
                self.assertEqual(included[member]["source_sha256"], f.PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256[member][0])
            self.assertIn("All other staging and operations files", manifest["retained_only_omissions"]["scope"])

    def test_path_escape_is_rejected_before_read(self):
        with patch.object(f, "PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256", {"../outside.py": ("0" * 64, "source", "exact")}):
            with self.assertRaisesRegex(f.EvidenceError, "unsafe"):
                f._add_pinned_operational_source_closure(Path(tempfile.gettempdir()), [], {}, [])

    def test_private_operational_keys_are_rejected_in_json(self):
        payload = b'{"pid": 123}\n'
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "proof.json").write_bytes(payload)
            with patch.object(f, "PINNED_OPERATIONAL_SOURCE_CLOSURE_SHA256", {"proof.json": (digest, "proof", "exact")}):
                with self.assertRaisesRegex(f.EvidenceError, "excluded operational key"):
                    f._add_pinned_operational_source_closure(root, [], {}, [])

if __name__ == "__main__":
    unittest.main()
