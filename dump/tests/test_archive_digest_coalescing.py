import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE))
import cold_model_storage as cold


def make_store(root, archive):
    runtime = root / "runtime"
    store = cold.ColdModelStore(root, runtime, archive, runtime / "manifest.json", runtime / "journals")
    return store


def identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


class ArchiveDigestCoalescingTests(unittest.TestCase):
    def test_combined_digest_matches_independent_full_and_prefix_hashes(self):
        payload = (b"archive-data" * 8193) + bytes(range(256))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.bin"
            path.write_bytes(payload)
            for n in (0, 1, 4096, len(payload)):
                whole, prefix, size = cold.sha256_file_and_prefix(path, n, chunk=997)
                self.assertEqual(whole, hashlib.sha256(payload).hexdigest())
                self.assertEqual(prefix, hashlib.sha256(payload[:n]).hexdigest())
                self.assertEqual(size, len(payload))
            whole, prefixes, size = cold.sha256_file_and_prefixes(path, (0, 4096, len(payload)), chunk=997)
            self.assertEqual(whole, hashlib.sha256(payload).hexdigest())
            self.assertEqual(prefixes, {n: hashlib.sha256(payload[:n]).hexdigest() for n in (0,4096,len(payload))})
            self.assertEqual(size, len(payload))
            with self.assertRaises(cold.AmbiguousState):
                cold.sha256_file_and_prefix(path, len(payload) + 1)

    def test_reviewed_baseline_caches_exact_zip_identity_and_prefix(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); archive = root / "a.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z:
                z.writestr("old.bin", b"retained bytes" * 13)
            with zipfile.ZipFile(archive) as z:
                records = cold._zip_records_all(z); start = z.start_dir
            digest = cold.sha256_file(archive); st = archive.stat()
            manifest = {"archive_sha256": digest, "archive_bytes": st.st_size, "zip_records": records, "members": []}
            store = make_store(root, archive)
            got, checked, got_records = store._check_reviewed_baseline(manifest, digest)
            self.assertEqual(got, digest); self.assertEqual(got_records, records); self.assertEqual(identity(checked), identity(st))
            cache = store._archive_identity_cache
            self.assertEqual(cache["identity"], identity(st)); self.assertEqual(cache["prefix_bytes"], start)
            self.assertEqual(cache["prefix_sha256"], hashlib.sha256(archive.read_bytes()[:start]).hexdigest())
            self.assertEqual(store._verified_prefix_digest(digest, start), cache["prefix_sha256"])

    def test_legacy_three_field_cache_is_rehashed_not_treated_as_prefix_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); archive = root / "a.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z: z.writestr("old", b"legacy-cache-fixture")
            with zipfile.ZipFile(archive) as z: records = cold._zip_records_all(z); start = z.start_dir
            digest = cold.sha256_file(archive); st = archive.stat(); store = make_store(root, archive)
            manifest = {"archive_sha256":digest,"archive_bytes":st.st_size,"zip_records":records,"members":[]}
            legacy_cache = {"identity":identity(st),"sha256":digest,"zip_records":records}
            store._archive_identity_cache = dict(legacy_cache)
            original = cold.sha256_file_and_prefixes
            with mock.patch.object(cold, "sha256_file_and_prefixes", wraps=original) as rehash:
                actual, _, _ = store._check_archive_manifest(manifest)
            self.assertEqual(actual, digest); rehash.assert_called_once()
            store._archive_identity_cache = dict(legacy_cache)
            with mock.patch.object(cold, "sha256_file_and_prefixes", wraps=original) as rehash:
                prefix = store._verified_prefix_digest(digest, start)
            self.assertEqual(prefix, hashlib.sha256(archive.read_bytes()[:start]).hexdigest())
            rehash.assert_called_once()

    def test_stat_inode_drift_during_combined_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); archive = root / "a.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z: z.writestr("x", b"one")
            with zipfile.ZipFile(archive) as z: records = cold._zip_records_all(z)
            st = archive.stat(); digest = cold.sha256_file(archive)
            manifest = {"archive_sha256": digest, "archive_bytes": st.st_size, "zip_records": records, "members": []}
            store = make_store(root, archive)
            original = cold.sha256_file_and_prefix
            def replace_after_hash(path, prefix_bytes, chunk=8<<20):
                result = original(path, prefix_bytes, chunk)
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(path.read_bytes() + b"drift")
                replacement.replace(path)
                return result
            with mock.patch.object(cold, "sha256_file_and_prefix", side_effect=replace_after_hash):
                with self.assertRaises(cold.AmbiguousState): store._check_reviewed_baseline(manifest, digest)

    def test_postappend_combined_digest_proves_old_prefix_and_new_whole_file(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "a.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z: z.writestr("old", b"prefix-preserved")
            with zipfile.ZipFile(archive) as z: old_boundary = z.start_dir
            old_prefix = hashlib.sha256(archive.read_bytes()[:old_boundary]).hexdigest()
            with zipfile.ZipFile(archive, "a", compression=zipfile.ZIP_STORED) as z: z.writestr("new", b"new payload")
            final_bytes = archive.read_bytes()
            with zipfile.ZipFile(archive) as z: final_boundary = z.start_dir
            whole, prefixes, size = cold.sha256_file_and_prefixes(archive, (old_boundary, final_boundary), chunk=7)
            self.assertEqual(whole, hashlib.sha256(final_bytes).hexdigest())
            self.assertEqual(prefixes[old_boundary], old_prefix)
            self.assertEqual(prefixes[final_boundary], hashlib.sha256(final_bytes[:final_boundary]).hexdigest())
            self.assertEqual(size, len(final_bytes))
            archive.write_bytes(b"X" + archive.read_bytes()[1:])
            _, changed_prefix, _ = cold.sha256_file_and_prefix(archive, old_boundary, chunk=7)
            self.assertNotEqual(changed_prefix, old_prefix)

    def test_append_uses_one_final_stream_and_exports_exact_identity_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); runtime = root / "runtime"; archive = root / "a.zip"
            runtime.mkdir()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z: z.writestr("old", b"keep-existing")
            with zipfile.ZipFile(archive) as z: old_records = cold._zip_records_all(z); old_boundary = z.start_dir
            before = cold.sha256_file(archive)
            source_rel = "runtime_20261025/artifacts/fixture/pipeline.joblib"
            source = root / source_rel; source.parent.mkdir(parents=True); payload = b"fixture-new-model" * 29; source.write_bytes(payload)
            item = {"archive_member":"runtime_20261025/cold_models/fixture/model.zipmember",
                    "source_relpath":source_rel,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest(),
                    "crc32":zipfile.crc32(payload)}
            store = make_store(root, archive); tx = "cd" * 16; txdir = store._journal_dir(tx); txdir.mkdir(parents=True)
            j = {"transaction_id":tx,"archive_sha256_before":before,"central_directory_offset":old_boundary,
                 "old_zip_records":old_records,"items":[item],"storage_codec_policy":None}
            with zipfile.ZipFile(archive) as z: old_prefix = hashlib.sha256(archive.read_bytes()[:z.start_dir]).hexdigest()
            j["prefix_sha256"] = old_prefix
            result = store._append_locked(j)
            self.assertEqual(result["state"], "archive_committed")
            final_bytes = archive.read_bytes(); final_sha = hashlib.sha256(final_bytes).hexdigest()
            self.assertEqual(result["archive_sha256_after"], final_sha)
            self.assertEqual(store._archive_identity_cache["sha256"], final_sha)
            self.assertEqual(store._archive_identity_cache["prefix_bytes"], store._archive_identity_cache["zip_start_dir"])
            with zipfile.ZipFile(archive) as z:
                final_start = z.start_dir; final_records = cold._zip_records_all(z)
            self.assertEqual(store._archive_identity_cache["prefix_sha256"], hashlib.sha256(final_bytes[:final_start]).hexdigest())
            manifest = {"archive_sha256":final_sha,"archive_bytes":len(final_bytes),"zip_records":final_records,"members":[]}
            with mock.patch.object(cold, "sha256_file_and_prefixes", side_effect=AssertionError("cache miss caused redundant digest pass")):
                got, _, records = store._check_archive_manifest(manifest)
            self.assertEqual(got, final_sha); self.assertEqual(records, final_records)
            self.assertEqual(item["crc32"], zipfile.crc32(payload))

    def test_rollback_retains_exact_original_archive_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); runtime = root / "runtime"; archive = root / "a.zip"
            runtime.mkdir()
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as z: z.writestr("old", b"immutable-old-payload")
            original_bytes = archive.read_bytes(); original_sha = hashlib.sha256(original_bytes).hexdigest()
            with zipfile.ZipFile(archive) as z: boundary = z.start_dir
            tail = original_bytes[boundary:]; alias = root / "alias.bin"; alias.write_bytes(b"new-source")
            store = make_store(root, archive); tx = "fixture-tx"; txdir = store._journal_dir(tx); txdir.mkdir(parents=True)
            tail_path = txdir / "old_central_tail.bin"; tail_path.write_bytes(tail)
            st = archive.stat()
            j = {"transaction_id":tx,"items":[{"aliases":["alias.bin"],"sha256":hashlib.sha256(b"new-source").hexdigest()}],
                 "archive_device":st.st_dev,"archive_inode":st.st_ino,"central_directory_offset":boundary,
                 "tail_sha256":hashlib.sha256(tail).hexdigest(),"prefix_sha256":hashlib.sha256(original_bytes[:boundary]).hexdigest(),
                 "archive_size_before":len(original_bytes),"archive_sha256_before":original_sha,"state":"appending"}
            with open(archive, "ab") as f: f.write(b"partial-appended-data")
            store._rollback(j)
            self.assertEqual(archive.read_bytes(), original_bytes)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), original_sha)
            self.assertEqual(json.loads((txdir / "journal.json").read_text())["state"], "rolled_back")

if __name__ == "__main__": unittest.main()
