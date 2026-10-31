"""Synthetic integration checks for the real arfpy FORDE/FORGE adapter."""
import importlib.util
import unittest

import numpy as np

from benchmark.models_arf import make_model


class ARFDensityTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("arfpy"), "arfpy is not installed")
    def test_density_posterior_and_forge_use_the_fitted_model(self):
        rng = np.random.default_rng(2026)
        centers = np.array([
            [c * 2.0, -c * 0.7, c * 0.3, c * 1.1, -c * 0.2, c * 0.5]
            for c in range(7)
        ])
        X = np.concatenate([rng.normal(loc=centers[c], scale=0.8, size=(30, 6)) for c in range(7)])
        y = np.repeat(np.arange(7, dtype=np.int64), 30)
        model = make_model(
            "arf",
            {"num_trees": 100, "min_samples_leaf": 5, "max_depth": 10, "finite_bounds": "no"},
            seed=31,
            n_jobs=1,
        ).fit(X, y)

        # FORGE's tree/leaf law is cvg / n_trees. Check its leaf probabilities
        # sum to one for every class before relying on the same weights in the
        # density mixture.
        for arf_model in model.models_:
            leaf_prob = arf_model.bnds[["tree", "nodeid", "cvg"]].drop_duplicates(["tree", "nodeid"])
            totals = leaf_prob.groupby("tree")["cvg"].sum().to_numpy()
            np.testing.assert_allclose(totals, 1.0, atol=1e-12)

        lp = model.class_logpdf(X[:12])
        post = model.score_matrix(X[:12])
        self.assertEqual(lp.shape, (12, 7))
        self.assertEqual(post.shape, (12, 7))
        self.assertFalse(np.isnan(lp).any())
        self.assertTrue(np.isfinite(post).all())
        np.testing.assert_allclose(post.sum(axis=1), 1.0, atol=1e-12)
        np.testing.assert_array_equal(model.predict(X[:12]), post.argmax(axis=1))

        a = model.sample_class(3, 20, seed=71)
        b = model.sample_class(3, 20, seed=71)
        self.assertEqual(a.shape, (20, 6))
        self.assertTrue(np.isfinite(a).all())
        np.testing.assert_array_equal(a, b)

    def test_domain_respects_available_class_support(self):
        from benchmark.models_arf import complexity_key, suggest_parameters

        class FixedTrial:
            def suggest_categorical(self, name, choices):
                return choices[0]

        params = suggest_parameters(FixedTrial(), "arf", n_fit=700, min_class=20)
        self.assertEqual(params["num_trees"], 100)
        self.assertEqual(params["min_samples_leaf"], 5)
        self.assertEqual(params["finite_bounds"], "no")
        with self.assertRaisesRegex(ValueError, "at least five"):
            suggest_parameters(FixedTrial(), "arf", n_fit=7, min_class=4)
        self.assertLess(
            complexity_key("arf", {"num_trees": 100, "max_depth": 10, "min_samples_leaf": 20}),
            complexity_key("arf", {"num_trees": 100, "max_depth": 10, "min_samples_leaf": 5}),
        )


if __name__ == "__main__":
    unittest.main()
