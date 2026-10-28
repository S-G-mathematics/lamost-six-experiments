import tempfile
import unittest
from pathlib import Path

import batch_plan
import cold_model_storage as cold
from commit_batch_child import filter_candidate_publication_aliases
from test_cold_model_storage import setup_store

EXPECTED_METHODS = {
    "arf", "cart", "chow_liu", "copula", "gaussian_nb", "gmm", "hist_gb",
    "kde", "knn", "lda", "linear_svm", "logistic", "qda", "random_forest",
    "rbf_svm", "shared_diagonal",
}


class MixedFamilyArchiveScopeTests(unittest.TestCase):
    def test_reviewed_method_allowlist_matches_core_and_planner(self):
        self.assertEqual(set(batch_plan.ARCHIVABLE_FIT_METHODS), EXPECTED_METHODS)
        self.assertEqual(set(cold._ARCHIVABLE_FIT_METHODS), EXPECTED_METHODS)

    def test_hist_gb_candidate_passes_existing_publication_and_store_guards(self):
        with tempfile.TemporaryDirectory() as td:
            root, runtime, store, key, source, alias, obj, digest, records, item = setup_store(Path(td), method="hist_gb")
            candidates = batch_plan.build_candidates(root, runtime, records, set(), cold._safety, cold, packing="largest_first")
            self.assertEqual(len(candidates), 1)
            candidate = candidates[0]
            self.assertEqual(candidate["producer_task"], key)
            self.assertEqual(candidate["method"], "hist_gb")
            self.assertEqual(candidate["source_sha256"], digest)
            self.assertEqual(set(candidate["aliases"]), set(item["aliases"]))
            original_payload = source.read_bytes()
            eligible, receipt = filter_candidate_publication_aliases(candidates, records, store)
            self.assertEqual(len(eligible), 1)
            self.assertEqual(receipt["excluded_group_count"], 0)
            tx = store.commit_models(eligible, records)
            manifest = cold._manifest_load(store.manifest)
            self.assertEqual(len(manifest["members"]), 1)
            self.assertEqual(manifest["members"][0]["method"], "hist_gb")
            self.assertEqual(manifest["members"][0]["sha256"], digest)
            self.assertEqual(store.read_bytes(item["source_relpath"], digest), original_payload)
            journal = __import__("json").loads((store.journals / tx / "journal.json").read_text())
            self.assertEqual(journal["items"][0]["method"], "hist_gb")
            self.assertEqual(store._validate_existing_members(manifest, records), {key, *item["consumer_tasks"]})

    def test_method_gate_does_not_weaken_consumer_experiment_or_receipt_gates(self):
        with tempfile.TemporaryDirectory() as td:
            root, runtime, store, key, source, alias, obj, digest, records, item = setup_store(Path(td), method="hist_gb")
            def candidates():
                return batch_plan.build_candidates(root, runtime, records, set(), cold._safety, cold)
            self.assertEqual(len(candidates()), 1)
            consumer = item["consumer_tasks"][0]
            records[consumer]["status"] = "waiting_for_dependency"
            self.assertEqual(candidates(), [])
            records[consumer]["status"] = "validated_terminal"
            records[key]["experiment"] = 7
            self.assertEqual(candidates(), [])
            records[key]["experiment"] = 3
            records[key]["method"] = "unreviewed_method"
            self.assertEqual(candidates(), [])
            records[key]["method"] = "hist_gb"
            pipeline = Path(records[key]["artifact_dir"]) / "attempts" / records[key]["result"]["attempt_id"] / "fit_publication.json"
            pipeline.unlink()
            candidates_before_receipt_filter = batch_plan.build_candidates(root, runtime, records, set(), cold._safety, cold)
            self.assertEqual(len(candidates_before_receipt_filter), 1)
            eligible, receipt = filter_candidate_publication_aliases(candidates_before_receipt_filter, records, store)
            self.assertEqual(eligible, [])
            self.assertEqual(receipt["excluded_group_count"], 1)

    def test_core_rejects_candidate_method_disagreement(self):
        with tempfile.TemporaryDirectory() as td:
            root, runtime, store, key, source, alias, obj, digest, records, item = setup_store(Path(td), method="hist_gb")
            candidates = batch_plan.build_candidates(root, runtime, records, set(), cold._safety, cold)
            bad = dict(candidates[0], method="random_forest")
            with self.assertRaises(cold.AmbiguousState):
                store._normalize([bad], records)

if __name__ == "__main__": unittest.main()
