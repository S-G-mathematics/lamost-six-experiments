import io, hashlib, os, sys, tempfile, unittest, zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/"source"));sys.path.insert(0,str(HERE/"tests"))
import batch_plan
import cold_model_storage as cold
from commit_batch_child import filter_candidate_publication_aliases
from et_store_fixture import setup_store

EXPECTED_METHODS={"arf","cart","chow_liu","copula","extra_trees","gaussian_nb","gmm","hist_gb","kde","knn","lda","linear_svm","logistic","qda","random_forest","rbf_svm","shared_diagonal"}

class ET17ArchiveScopeTests(unittest.TestCase):
    def test_both_reviewed_allowlists_are_exactly_the_seventeen_known_methods(self):
        self.assertEqual(set(batch_plan.ARCHIVABLE_FIT_METHODS),EXPECTED_METHODS)
        self.assertEqual(set(cold._ARCHIVABLE_FIT_METHODS),EXPECTED_METHODS)
        self.assertNotIn("unreviewed_method",batch_plan.ARCHIVABLE_FIT_METHODS)

    def test_extra_trees_candidate_passes_existing_publication_store_and_alias_gates(self):
        with tempfile.TemporaryDirectory() as td:
            root,runtime,store,key,source,alias,obj,digest,records,item=setup_store(Path(td),method="extra_trees")
            candidates=batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold,packing="largest_first")
            self.assertEqual(len(candidates),1);candidate=candidates[0]
            self.assertEqual(candidate["producer_task"],key);self.assertEqual(candidate["method"],"extra_trees")
            self.assertEqual(candidate["source_sha256"],digest);self.assertEqual(set(candidate["aliases"]),set(item["aliases"]))
            source_bytes=source.read_bytes()
            eligible,receipt=filter_candidate_publication_aliases(candidates,records,store)
            self.assertEqual(len(eligible),1);self.assertEqual(receipt["excluded_group_count"],0)
            tx=store.commit_models(eligible,records);manifest=cold._manifest_load(store.manifest)
            self.assertEqual(manifest["members"][0]["method"],"extra_trees")
            self.assertEqual(manifest["members"][0]["sha256"],digest)
            self.assertEqual(store.read_bytes(item["source_relpath"],digest),source_bytes)
            self.assertFalse(source.exists());self.assertFalse(alias.exists())

    def test_unknown_method_and_wrong_experiment_remain_ineligible(self):
        with tempfile.TemporaryDirectory() as td:
            root,runtime,store,key,source,alias,obj,digest,records,item=setup_store(Path(td),method="extra_trees")
            self.assertEqual(len(batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold)),1)
            records[key]["method"]="unreviewed_method"
            self.assertEqual(batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold),[])
            records[key]["method"]="extra_trees";records[key]["experiment"]=7
            self.assertEqual(batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold),[])

    def test_nonterminal_consumer_and_candidate_method_relabel_remain_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root,runtime,store,key,source,alias,obj,digest,records,item=setup_store(Path(td),method="extra_trees")
            consumer=item["consumer_tasks"][0];records[consumer]["status"]="waiting_for_dependency"
            self.assertEqual(batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold),[])
            records[consumer]["status"]="validated_terminal"
            candidate=batch_plan.build_candidates(root,runtime,records,set(),cold._safety,cold)[0]
            bad=dict(candidate,method="random_forest")
            with self.assertRaises(cold.AmbiguousState):store._normalize([bad],records)

class SyntheticExtraTreesJoblibRoundTrip(unittest.TestCase):
    def test_synthetic_estimator_survives_zip_stored_filelike_roundtrip(self):
        import numpy as np, joblib
        from sklearn.ensemble import ExtraTreesClassifier
        rng=np.random.default_rng(81723);X=rng.normal(size=(128,6));y=np.tile(np.arange(7),19)[:128]
        X_score=rng.normal(size=(16,6))
        model=ExtraTreesClassifier(n_estimators=8,max_depth=4,min_samples_leaf=1,max_features="sqrt",random_state=271828,n_jobs=1).fit(X,y)
        expected=model.predict_proba(X_score)
        with tempfile.TemporaryDirectory() as td:
            original=Path(td)/"synthetic_et.joblib";joblib.dump(model,original,compress=0)
            raw=original.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:z.writestr("synthetic_et.joblib",raw)
            buf.seek(0)
            with zipfile.ZipFile(buf,"r") as z:
                self.assertIsNone(z.testzip());info=z.getinfo("synthetic_et.joblib")
                self.assertEqual(info.compress_type,zipfile.ZIP_STORED);self.assertEqual(info.file_size,len(raw))
                with z.open(info) as stream:restored_bytes=stream.read()
            self.assertEqual(hashlib.sha256(restored_bytes).hexdigest(),digest)
            restored=joblib.load(io.BytesIO(restored_bytes))
            self.assertIsInstance(restored,ExtraTreesClassifier)
            self.assertEqual(restored.get_params(deep=False),model.get_params(deep=False))
            np.testing.assert_array_equal(expected,restored.predict_proba(X_score))
            self.assertEqual(int(restored.n_jobs),1)

if __name__=="__main__":unittest.main()
