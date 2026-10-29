import ast
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
RUNTIME = HERE
SOURCE = RUNTIME / "source" / "parallel_extra_trees"
RF_SOURCE = RUNTIME / "source" / "parallel_rf"
PROJECT = next((parent / "project" for parent in (RUNTIME, *RUNTIME.parents)
                if (parent / "project").is_dir()), None)
if PROJECT is None:
    raise RuntimeError("portable ET4 fixture cannot find the frozen project source")
_existing_global_science = sys.modules.get("science")
sys.path.insert(0, str(PROJECT))
try:
    from benchmark import models_basic
    from benchmark.evaluation import balanced_accuracy
    _spec = importlib.util.spec_from_file_location(
        "_lamost_et4_engineering_science", SOURCE / "science.py"
    )
    if _spec is None or _spec.loader is None:
        raise RuntimeError("could not load candidate ET4 science module")
    science = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = science
    _spec.loader.exec_module(science)
finally:
    sys.path.remove(str(PROJECT))
if sys.modules.get("science") is not _existing_global_science:
    raise RuntimeError("ET4 fixture changed the global science module binding")


def _assert_tree_identity(testcase, left, right):
    left_trees = left.estimator.estimators_
    right_trees = right.estimator.estimators_
    testcase.assertEqual(len(left_trees), len(right_trees))
    fields = ("children_left", "children_right", "feature", "threshold", "value",
              "impurity", "n_node_samples", "weighted_n_node_samples")
    for a, b in zip(left_trees, right_trees):
        testcase.assertEqual(int(a.random_state), int(b.random_state))
        for name in fields:
            np.testing.assert_array_equal(getattr(a.tree_, name), getattr(b.tree_, name))


class ExtraTrees4EngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.RandomState(20261029)
        # Synthetic engineering fixture only; no project roles or scientific data.
        cls.X = rng.normal(size=(140, 6)).astype(np.float32)
        cls.y = np.tile(np.arange(7, dtype=np.int64), 20)
        order = rng.permutation(len(cls.y))
        cls.X, cls.y = cls.X[order], cls.y[order]
        cls.Xv = rng.normal(size=(70, 6)).astype(np.float32)
        cls.yv = np.tile(np.arange(7, dtype=np.int64), 10)
        cls.Xv = cls.Xv[rng.permutation(len(cls.yv))]

    def fit(self, jobs, params):
        env = {
            "LAMOST_ET_FIT_JOBS4": "1",
            "LAMOST_ET_EXECUTION_POLICY": science.ET4_EXECUTION_POLICY,
            "LAMOST_ET_RESOURCE_PROFILE": science.ET4_RESOURCE_PROFILE,
        }
        saved = {k: os.environ.get(k) for k in env}
        try:
            if jobs == 1:
                for k in env:
                    os.environ.pop(k, None)
            else:
                os.environ.update(env)
            task = {"kind": "fit", "method": "extra_trees", "experiment": 4}
            model, actual_jobs = science._make_fit_model(
                models_basic, task, "trial_0", params, 271828, self.X, self.y
            )
            return model, actual_jobs
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_single_and_four_thread_trial_results_and_serialized_predictor_match(self):
        candidates = [
            {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 1, "max_features": "sqrt"},
            {"n_estimators": 200, "max_depth": 20, "min_samples_leaf": 5, "max_features": 1.0},
        ]
        single_scores, parallel_scores = [], []
        for params in candidates:
            single, single_jobs = self.fit(1, params)
            parallel, parallel_jobs = self.fit(4, params)
            self.assertEqual((single_jobs, parallel_jobs), (1, 4))
            self.assertEqual(single.estimator.n_jobs, 1)
            self.assertEqual(parallel.estimator.n_jobs, 1)
            np.testing.assert_array_equal(single.estimator.classes_, np.arange(7))
            np.testing.assert_array_equal(parallel.estimator.classes_, np.arange(7))
            _assert_tree_identity(self, single, parallel)
            p1 = science._scores(single, self.Xv)
            p4 = science._scores(parallel, self.Xv)
            np.testing.assert_array_equal(p1, p4)
            single_scores.append(float(balanced_accuracy(self.yv, np.argmax(p1, axis=1))))
            parallel_scores.append(float(balanced_accuracy(self.yv, np.argmax(p4, axis=1))))
            with tempfile.TemporaryDirectory() as td:
                path = Path(td) / "synthetic_pipeline.joblib"
                import joblib
                joblib.dump({"model": parallel, "params": params}, path)
                loaded = joblib.load(path)
                self.assertEqual(loaded["model"].estimator.n_jobs, 1)
                np.testing.assert_array_equal(science._scores(loaded["model"], self.Xv), p1)
        self.assertEqual(single_scores, parallel_scores)
        chosen_single = max(range(len(candidates)), key=lambda i: (single_scores[i], -i))
        chosen_parallel = max(range(len(candidates)), key=lambda i: (parallel_scores[i], -i))
        self.assertEqual(chosen_single, chosen_parallel)
        self.assertEqual(candidates[chosen_single], candidates[chosen_parallel])

    def test_factory_defaults_domains_and_preprocessing_path_match_generic_et(self):
        params = {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 1, "max_features": "sqrt"}
        generic = models_basic.make_model("extra_trees", params, 271828, n_jobs=1)
        staged, jobs = self.fit(4, params)
        self.assertEqual(jobs, 4)
        expected = generic.estimator.get_params(deep=False)
        actual = staged.estimator.get_params(deep=False)
        self.assertEqual(actual, expected)
        self.assertEqual(actual["bootstrap"], False)
        self.assertEqual(actual["criterion"], "gini")
        self.assertEqual(actual["n_jobs"], 1)
        class Trial:
            def __init__(self):
                self.choices = {}
            def suggest_categorical(self, name, values):
                self.choices[name] = list(values)
                return values[0]
        trial = Trial()
        models_basic.suggest_parameters(trial, "extra_trees", n_fit=420, min_class=60)
        self.assertEqual(trial.choices, {
            "n_estimators": [200, 500],
            "max_depth": [10, 20, None],
            "min_samples_leaf": [1, 5, 20],
            "max_features": ["sqrt", 1.0],
        })
        def functions(path, wanted):
            tree = ast.parse(path.read_text())
            return {n.name: ast.dump(n, include_attributes=False)
                    for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name in wanted}
        names = {"_model_module", "_preprocess", "_train_model", "_fit_phase"}
        rf = functions(RF_SOURCE / "science.py", names)
        et = functions(SOURCE / "science.py", names)
        normalized = {k: v.replace("_et4_provenance", "_rf4_provenance") for k, v in et.items()}
        self.assertEqual(set(rf), set(normalized))
        self.assertEqual(rf, normalized)

    def test_profile_is_limited_to_fresh_e4_e5_extra_trees_fit_phases(self):
        task = {"kind": "fit", "method": "extra_trees", "experiment": 4}
        os.environ.update({
            "LAMOST_ET_FIT_JOBS4": "1",
            "LAMOST_ET_EXECUTION_POLICY": science.ET4_EXECUTION_POLICY,
            "LAMOST_ET_RESOURCE_PROFILE": science.ET4_RESOURCE_PROFILE,
        })
        try:
            self.assertEqual(science._fit_n_jobs(task, "trial_0"), 4)
            self.assertEqual(science._fit_n_jobs(task, "final_fit"), 4)
            self.assertEqual(science._fit_n_jobs(task, "evaluate"), 1)
            self.assertEqual(science._fit_n_jobs({**task, "experiment": 5}, "trial_0"), 4)
            for invalid in (
                {**task, "method": "random_forest"},
                {**task, "experiment": 3},
                {**task, "kind": "eval"},
                {**task, "reuse_pipeline": "pipeline.joblib"},
            ):
                with self.assertRaises(ValueError):
                    science._fit_n_jobs(invalid, "trial_0")
        finally:
            for k in ("LAMOST_ET_FIT_JOBS4", "LAMOST_ET_EXECUTION_POLICY", "LAMOST_ET_RESOURCE_PROFILE"):
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
