import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

MODULE = Path(__file__).parents[1] / "source" / "cohorts.py"
spec = importlib.util.spec_from_file_location("cohorts", MODULE)
cohorts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cohorts)


class CohortMathTests(unittest.TestCase):
    def test_half_up_and_restoration_counts(self):
        self.assertEqual(cohorts._half(1, 2), 1)
        self.assertEqual(cohorts._half(3, 2), 2)
        # p0 = 1/4, N=100, n=10: a=(25-10)/.75=20
        self.assertEqual(cohorts.added_count(25, 100, 10), 20)
        self.assertEqual(cohorts.added_count(25, 100, 25), 0)

    def test_largest_remainder_exact_and_tie_order(self):
        q = cohorts._largest(11, np.asarray([1, 1, 1]))
        self.assertEqual(q.sum(), 11)
        self.assertEqual(q.tolist(), [4, 4, 3])

    def test_label_noise_changes_every_selected_label(self):
        with tempfile.TemporaryDirectory() as td:
            rt = Path(td)
            (rt / "cache/roles").mkdir(parents=True)
            n, p = 100, 6
            y = np.arange(n, dtype=np.int64) % 7
            X = np.arange(n * p, dtype=np.float64).reshape(n, p)
            ids = np.arange(n, dtype=np.int64)
            np.savez(rt / "cache/roles/rep_0.npz",
                     X_fit=X, y_fit=y, fit_ids=ids,
                     X_tune=X[:4], y_tune=y[:4], tuning_ids=ids[:4] + 1000,
                     X_cal=X[4:8], y_cal=y[4:8], calibration_ids=ids[4:8] + 2000)
            # The unused tune/cal values intentionally have distinct IDs; role arrays are shape-valid.
            task = {"kind": "e5_corruption", "key": "label_20", "rep": 0,
                    "mechanism": "label_noise", "rate": .2, "seed": 17, "N": n}
            result = cohorts.execute(task, rt)
            self.assertEqual(result["status"], "successful")
            with np.load(rt / "artifacts/label_20/data.npz") as z:
                altered = z["y"]
                self.assertEqual(np.count_nonzero(altered != y), 20)
            with np.load(rt / "artifacts/label_20/audit.npz") as z:
                rows, old, new = z["affected_row_indices"], z["old_label"], z["new_label"]
                self.assertEqual(len(rows), 20)
                self.assertTrue(np.all(old != new))
                self.assertTrue(np.array_equal(altered[rows], new))
            self.assertTrue(np.array_equal(X, np.load(rt / "cache/roles/rep_0.npz")["X_fit"]))

    def test_nested_affected_masks_and_feature_noise_audit(self):
        with tempfile.TemporaryDirectory() as td:
            rt = Path(td)
            (rt / "cache/roles").mkdir(parents=True)
            n, p = 100, 6
            y = np.arange(n, dtype=np.int64) % 7
            X = np.random.default_rng(4).normal(size=(n, p))
            ids = np.arange(n, dtype=np.int64)
            np.savez(rt / "cache/roles/rep_0.npz",
                     X_fit=X, y_fit=y, fit_ids=ids,
                     X_tune=X[:4], y_tune=y[:4], tuning_ids=ids[:4] + 1000,
                     X_cal=X[4:8], y_cal=y[4:8], calibration_ids=ids[4:8] + 2000)
            resultsets = []
            perturbations = []
            for rate in (.05, .10, .20):
                key = f"noise_{int(rate*100)}"
                result = cohorts.execute({"kind":"e5_corruption","key":key,"rep":0,
                    "mechanism":"feature_noise","rate":rate,"seed":9,"N":n}, rt)
                self.assertEqual(result["status"], "successful")
                with np.load(rt / "artifacts" / key / "audit.npz") as z:
                    resultsets.append(set(z["affected_row_indices"].tolist()))
                    perturbations.append({int(row):(int(feature),float(delta)) for row,feature,delta in zip(z["affected_row_indices"],z["feature_index"],z["perturbation"])})
                    self.assertEqual(len(z["feature_index"]), int(n*rate))
                    self.assertEqual(len(z["perturbation"]), int(n*rate))
            self.assertTrue(resultsets[0] <= resultsets[1] <= resultsets[2])
            self.assertTrue(all(perturbations[0][i] == perturbations[1][i] == perturbations[2][i] for i in resultsets[0]))
            self.assertTrue(all(perturbations[1][i] == perturbations[2][i] for i in resultsets[1]))


    def test_e4_cohorts_disjoint_nested_and_exact_histograms(self):
        with tempfile.TemporaryDirectory() as td:
            rt = Path(td)
            (rt / "cache/roles").mkdir(parents=True)
            nfit, ntune, ncal, nextra = 80000, 5000, 5000, 20000
            ndev = nfit + ntune + ncal + nextra
            ids = np.arange(ndev, dtype=np.int64)
            ydev = ids % 7
            Xdev = np.column_stack([ids.astype(float) + j for j in range(6)])
            np.save(rt / "cache/development_X.npy", Xdev)
            np.save(rt / "cache/development_y.npy", ydev)
            np.save(rt / "cache/development_ids.npy", ids)
            fit_ids = ids[:nfit]
            tune_ids = ids[nfit:nfit+ntune]
            cal_ids = ids[nfit+ntune:nfit+ntune+ncal]
            np.savez(rt / "cache/roles/rep_0.npz",
                X_fit=Xdev[:nfit], y_fit=ydev[:nfit], fit_ids=fit_ids,
                X_tune=Xdev[nfit:nfit+ntune], y_tune=ydev[nfit:nfit+ntune], tuning_ids=tune_ids,
                X_cal=Xdev[nfit+ntune:nfit+ntune+ncal], y_cal=ydev[nfit+ntune:nfit+ntune+ncal],
                calibration_ids=cal_ids)
            result_sets = {}
            for ratio, key in ((.5, "e4_half"), (.1, "e4_tenth")):
                result = cohorts.execute({"kind":"e4_cohort","key":key,"rep":0,
                    "target_class":0,"ratio":ratio,"seed":31,"N":nfit}, rt)
                self.assertEqual(result["status"], "successful")
                with np.load(rt / "artifacts" / key / "data.npz") as z:
                    x, y, chosen = z["X"], z["y"], z["ids"]
                    self.assertEqual(x.shape, (nfit, 6))
                    self.assertNotIn("sample_weight", z.files)
                    self.assertEqual(len(np.unique(chosen)), nfit)
                    self.assertFalse(np.isin(chosen, np.r_[tune_ids, cal_ids]).any())
                    result_sets[ratio] = set(chosen[y == 0].tolist())
                    counts = np.bincount(y, minlength=7)
                    self.assertEqual(counts.sum(), nfit)
                self.assertEqual(result["metadata"]["realized_counts"], counts.tolist())
                self.assertFalse(result["metadata"]["sample_weight_included"])
                self.assertIn("only by explicit weighted treatment", result["metadata"]["weighting_policy"])
                self.assertEqual(result["metadata"]["restore_added_count"],
                    cohorts.added_count(result["metadata"]["source_fit_counts"][0], nfit, int(counts[0])))
            self.assertTrue(result_sets[.1] <= result_sets[.5])

            with np.load(rt/"artifacts/e4_half/data.npz") as base:
                half_counts=np.bincount(base["y"],minlength=7)
            weighted=cohorts.execute({"kind":"e4_treatment","key":"weighted","cohort_key":"e4_half","treatment":"weighted"},rt)
            self.assertEqual(weighted["status"],"successful")
            with np.load(rt/"artifacts/weighted/data.npz") as z:
                self.assertIn("sample_weight",z.files)
                self.assertAlmostEqual(float(z["sample_weight"].mean()),1.0,places=12)
                self.assertGreater(float(z["sample_weight"].std()),0.0)
                self.assertEqual(np.bincount(z["y"],minlength=7).tolist(),half_counts.tolist())

            ros=cohorts.execute({"kind":"e4_treatment","key":"ros","cohort_key":"e4_half","treatment":"ros","seed":19},rt)
            self.assertEqual(ros["status"],"successful")
            with np.load(rt/"artifacts/ros/data.npz") as z:
                self.assertNotIn("sample_weight",z.files)
                expected=half_counts.copy();expected[0]+=ros["metadata"]["added_count"]
                self.assertEqual(np.bincount(z["y"],minlength=7).tolist(),expected.tolist())
                self.assertEqual(len(z["y"]),nfit+ros["metadata"]["added_count"])
                self.assertEqual(ros["metadata"]["counts_after"],np.bincount(z["y"],minlength=7).tolist())

    def test_smote_uses_explicit_class_dictionary_and_exact_histogram(self):
        try:
            import imblearn
        except ImportError:
            self.skipTest("the project venv must provide imbalanced-learn")
        with tempfile.TemporaryDirectory() as td:
            rt = Path(td)
            base = rt / "artifacts" / "altered"
            base.mkdir(parents=True)
            counts = [5, 19, 19, 19, 19, 19, 40]
            y = np.repeat(np.arange(7), counts).astype(np.int64)
            rng = np.random.default_rng(12)
            X = np.column_stack([y + rng.normal(0, .1, len(y)) for _ in range(6)])
            np.savez(base / "data.npz", X=X, y=y, ids=np.arange(len(y)))
            with open(base / "metadata.json", "w") as f:
                import json
                json.dump({"target_class": 0, "source_fit_counts": [20]*7,
                    "restore_added_count": 18, "seed": 7}, f)
            result = cohorts.execute({"kind":"e4_treatment","key":"smote_out",
                "cohort_key":"altered","treatment":"smote","seed":7}, rt)
            self.assertEqual(result["status"], "successful")
            with np.load(rt / "artifacts" / "smote_out" / "data.npz") as z:
                self.assertNotIn("sample_weight", z.files)
                self.assertEqual(len(z["y"]), 158)
                self.assertEqual(np.bincount(z["y"], minlength=7).tolist(),
                    [23, 19, 19, 19, 19, 19, 40])
            self.assertEqual(result["metadata"]["sampling_strategy"], {0: 23})
            self.assertEqual(result["metadata"]["neighbors"], 4)


    def test_e4_append_accepts_science_generated_npz_and_exact_count(self):
        with tempfile.TemporaryDirectory() as td:
            rt = Path(td)
            b = rt / "artifacts" / "base"
            g = rt / "artifacts" / "generated"
            b.mkdir(parents=True)
            g.mkdir(parents=True)
            y = np.array([0, 1, 1, 2, 2, 3, 3], dtype=np.int64)
            X = np.arange(len(y)*6, dtype=float).reshape(len(y), 6)
            np.savez(b/"data.npz", X=X, y=y, ids=np.arange(len(y)))
            import json
            with open(b/"metadata.json","w") as f:
                json.dump({"target_class":0,"restore_added_count":2},f)
            np.savez(g/"data.npz", X=np.ones((2,6)), y=np.zeros(2,dtype=np.int64))
            result=cohorts.execute({"kind":"e4_append","key":"nested/appended",
                "cohort_key":"base","generated_key":"generated","target_class":0},rt)
            self.assertEqual(result["status"],"successful")
            with np.load(rt/"artifacts/nested/appended/data.npz") as z:
                self.assertNotIn("sample_weight",z.files)
                self.assertEqual(len(z["y"]),len(y)+2)
                self.assertEqual(np.bincount(z["y"],minlength=7).tolist(),
                    [3,2,2,2,0,0,0])


if __name__ == "__main__":
    unittest.main()
