"""Synthetic interface checks; these are not benchmark results."""
import unittest

import numpy as np

from benchmark.models_basic import ClassifierModel, METHODS, complexity_key, make_model, suggest_parameters


class FixedTrial:
    """Deterministic stand-in for the sequential adaptive search adapter."""
    def suggest_float(self, name, low, high, log=False):
        return float(np.sqrt(low * high) if log and low > 0 else (low + high) / 2)

    def suggest_categorical(self, name, choices):
        return choices[0]


def fixture_data():
    rng = np.random.default_rng(17)
    centers = rng.normal(size=(7, 6)) * 2
    y = np.repeat(np.arange(7), 24).astype(np.int64)
    X = np.vstack([rng.normal(loc=centers[c], scale=0.7, size=(24, 6)) for c in range(7)]).astype(np.float64)
    return X, y


def params_for(method):
    return {
        "gaussian_nb": {"var_smoothing": 1e-6},
        "shared_diagonal": {"variance_floor": 1e-6},
        "lda": {"shrinkage": 0.1},
        "qda": {"reg_param": 0.1, "variance_floor": 1e-6},
        "logistic": {"C": 1.0},
        "linear_svm": {"C": 1.0},
        "rbf_svm": {"C": 1.0, "gamma": 0.1, "cache_size_mb": 64},
        "knn": {"n_neighbors": 5, "weights": "uniform"},
        "cart": {"max_depth": 3, "min_samples_leaf": 1},
        "random_forest": {"n_estimators": 20, "max_depth": 5, "min_samples_leaf": 1, "max_features": "sqrt"},
        "extra_trees": {"n_estimators": 20, "max_depth": 5, "min_samples_leaf": 1, "max_features": "sqrt"},
        "hist_gb": {"max_iter": 20, "learning_rate": 0.1, "max_leaf_nodes": 15, "min_samples_leaf": 10, "l2_regularization": 0.0},
    }[method]


class BasicModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.X, cls.y = fixture_data()

    def test_all_methods_fit_and_return_fixed_seven_scores(self):
        for method in sorted(METHODS):
            with self.subTest(method=method):
                model = make_model(method, params_for(method), seed=43, n_jobs=1).fit(self.X, self.y)
                scores = model.score_matrix(self.X[:9])
                self.assertEqual(scores.shape, (9, 7))
                self.assertTrue(np.isfinite(scores).all())
                self.assertEqual(model.predict(self.X[:9]).shape, (9,))
                pred = model.predict(self.X[:9])
                self.assertTrue(np.all((pred >= 0) & (pred <= 6)))
                np.testing.assert_array_equal(pred, np.argmax(scores, axis=1))
                if model.score_kind == "probability":
                    self.assertTrue(np.all(scores >= 0))
                    np.testing.assert_allclose(scores.sum(axis=1), 1.0, atol=1e-7)
                else:
                    with self.assertRaises(AttributeError):
                        model.predict_proba(self.X[:1])
                    if method == "rbf_svm":
                        self.assertTrue(model.estimator.break_ties)

    def test_gaussian_density_sampling_and_posterior(self):
        for method in ("gaussian_nb", "shared_diagonal", "lda", "qda"):
            with self.subTest(method=method):
                model = make_model(method, params_for(method), seed=4).fit(self.X, self.y)
                logs = model.class_logpdf(self.X[:5])
                self.assertEqual(logs.shape, (5, 7))
                self.assertTrue(np.isfinite(logs).all())
                posterior = model.score_matrix(self.X[:5])
                np.testing.assert_allclose(posterior.sum(axis=1), 1, atol=1e-12)
                s1 = model.sample_class(3, 50, seed=77)
                s2 = model.sample_class(3, 50, seed=77)
                self.assertEqual(s1.shape, (50, 6))
                np.testing.assert_array_equal(s1, s2)
                cov = model.covs_[3]
                sign, logdet = np.linalg.slogdet(cov)
                self.assertGreater(sign, 0)
                self.assertTrue(np.isfinite(logdet))

    def test_missing_classes_and_infeasible_search_are_reported(self):
        with self.assertRaisesRegex(ValueError, "all labels"):
            make_model("logistic", {"C": 1}, 1).fit(self.X[self.y != 6], self.y[self.y != 6])
        with self.assertRaisesRegex(ValueError, "unsupported"):
            suggest_parameters(FixedTrial(), "knn", n_fit=2, min_class=0)
        with self.assertRaisesRegex(ValueError, "QDA"):
            suggest_parameters(FixedTrial(), "qda", n_fit=7, min_class=1)

    def test_trial_adapter_returns_domain_valid_parameters(self):
        trial = FixedTrial()
        self.assertGreater(suggest_parameters(trial, "rbf_svm", 800, 10)["gamma"], 0)
        self.assertLessEqual(suggest_parameters(trial, "knn", 4, 1)["n_neighbors"], 4)
        self.assertIn(suggest_parameters(trial, "hist_gb", 800, 100)["max_iter"], (100, 300))

    def test_complexity_tie_order_prefers_smoother_tree_configs(self):
        shallow = complexity_key("cart", {"max_depth": 6, "min_samples_leaf": 5})
        broad_leaf = complexity_key("cart", {"max_depth": 6, "min_samples_leaf": 20})
        self.assertLess(broad_leaf, shallow)

        rf_small_leaf = {"n_estimators": 200, "max_depth": 10, "min_samples_leaf": 1, "max_features": "sqrt"}
        rf_large_leaf = {**rf_small_leaf, "min_samples_leaf": 20}
        self.assertLess(complexity_key("random_forest", rf_large_leaf), complexity_key("random_forest", rf_small_leaf))

        hist_weak_reg = {"max_iter": 100, "max_leaf_nodes": 15, "min_samples_leaf": 10, "learning_rate": 0.1, "l2_regularization": 0.0}
        hist_simple = {**hist_weak_reg, "min_samples_leaf": 50, "l2_regularization": 10.0}
        self.assertLess(complexity_key("hist_gb", hist_simple), complexity_key("hist_gb", hist_weak_reg))
        self.assertLess(complexity_key("hist_gb", {**hist_weak_reg, "learning_rate": 0.03}), complexity_key("hist_gb", hist_weak_reg))

    def test_classifier_wrapper_uses_fixed_order_argmax_for_margin_ties(self):
        class TiedEstimator:
            classes_ = np.arange(7)

            def decision_function(self, X):
                return np.zeros((len(X), 7), dtype=np.float64)

            def predict(self, X):
                # Stand-in for a native classifier whose internal tie policy
                # differs from the benchmark's fixed class-order policy.
                return np.full(len(X), 5)

        wrapper = ClassifierModel(TiedEstimator(), score_kind="margin")
        np.testing.assert_array_equal(wrapper.predict(np.zeros((3, 6))), np.zeros(3, dtype=np.int64))


if __name__ == "__main__":
    unittest.main()
