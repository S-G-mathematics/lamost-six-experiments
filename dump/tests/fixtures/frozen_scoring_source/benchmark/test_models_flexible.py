import itertools
import unittest

import numpy as np

from scipy.special import ndtri

from benchmark.models_flexible import (
    _HistogramTailMarginal, _KDE, complexity_key, make_model, suggest_parameters,
)


def fixture():
    rng = np.random.default_rng(173)
    X0 = rng.normal(-1, 0.35, size=(28, 6))
    X1 = rng.normal(1, 0.45, size=(18, 6))
    return np.vstack([X0, X1]), np.r_[np.zeros(len(X0), dtype=int), np.ones(len(X1), dtype=int)]


class FlexibleDensityTests(unittest.TestCase):
  def test_all_families_score_sample_and_preserve_fixed_label_order(self):
    X, y = fixture()
    configs = [
        ("gmm", {"n_components": 1, "covariance_type": "diag", "reg_covar": 1e-4}),
        ("copula", {"marginal": "histogram_tail", "shrinkage": 0.2}),
        ("kde", {"bandwidth": 0.5}),
        ("chow_liu", {"n_bins": 4}),
    ]
    for method, params in configs:
        model = make_model(method, params, seed=27).fit(X, y)
        log_density = model.class_logpdf(X[:5])
        posterior = model.score_matrix(X[:5])
        assert log_density.shape == (5, 7)
        assert posterior.shape == (5, 7)
        assert np.isfinite(log_density[np.arange(5), y[:5]]).all()
        assert np.isneginf(log_density[:, 2:]).all()
        np.testing.assert_allclose(posterior.sum(axis=1), 1.0, atol=1e-12)
        np.testing.assert_array_equal(model.predict_proba(X[:5]), posterior)
        assert np.all(model.predict(X[:5]) < 2)
        sample = model.sample_class(1, 20, seed=918)
        assert sample.shape == (20, 6)
        assert np.isfinite(sample).all()

  def test_histogram_tail_marginal_cdf_pdf_and_inverse_agree(self):
    rng = np.random.default_rng(902)
    marginal = _HistogramTailMarginal(rng.normal(size=250))
    x = np.r_[marginal.edges[0] - 15 * marginal.tail_scale,
              marginal.edges[0] - marginal.tail_scale, marginal.edges[0],
              (marginal.edges[:-1] + marginal.edges[1:]) / 2,
              marginal.edges[-1], marginal.edges[-1] + marginal.tail_scale,
              marginal.edges[-1] + 15 * marginal.tail_scale]
    cdf = marginal.cdf(x)
    self.assertTrue(np.all(np.diff(cdf) > 0))
    np.testing.assert_allclose(marginal.ppf_from_normal(marginal.normal_score(x)), x,
                               rtol=1e-10, atol=1e-10)
    grid = np.linspace(marginal.edges[0] - 20 * marginal.tail_scale,
                       marginal.edges[-1] + 20 * marginal.tail_scale, 30001)
    area = np.trapezoid(np.exp(marginal.logpdf(grid)), grid)
    self.assertAlmostEqual(area, 1.0, delta=8e-4)
    probs = np.array([1e-10, 1e-7, 0.01, 0.5, 0.99, 1 - 1e-7, 1 - 1e-10])
    zq = ndtri(probs)
    np.testing.assert_allclose(marginal.cdf(marginal.ppf_from_normal(zq)), probs,
                               rtol=2e-7, atol=1e-15)

  def test_batched_kde_matches_direct_mixture_formula(self):
    rng = np.random.default_rng(96)
    rows = rng.normal(size=(1300, 6))
    queries = rng.normal(size=(350, 6))
    kde = _KDE(rows, 0.7)
    actual = kde.logpdf(queries)
    d2 = np.sum((queries[:7, None, :] - rows[None, :, :]) ** 2, axis=2)
    expected = kde.log_norm + np.logaddexp.reduce(-0.5 * d2 / 0.7**2, axis=1)
    np.testing.assert_allclose(actual[:7], expected, rtol=1e-12, atol=1e-12)

  def test_copula_samples_follow_its_fitted_marginals(self):
    X, y = fixture()
    model = make_model("copula", {"marginal": "histogram_tail", "shrinkage": 0.2}, seed=4).fit(X, y)
    samples = model.sample_class(0, 8000, seed=500)
    law = model.class_models[0]
    for j, marginal in enumerate(law.marginals):
        for p in (0.1, 0.5, 0.9):
            quantile = marginal.ppf_from_normal(np.array([ndtri(p)]))[0]
            self.assertAlmostEqual(float(np.mean(samples[:, j] <= quantile)), p, delta=0.025)

  def test_chow_liu_small_class_support_remains_smoothed_and_normalized(self):
    class Trial:
        def suggest_categorical(self, name, choices):
            self.asserted_choices = choices
            return choices[0]

    trial = Trial()
    params = suggest_parameters(trial, "chow_liu", n_fit=240, min_class=4)
    self.assertEqual(params["n_bins"], 8)
    rng = np.random.default_rng(11)
    X = rng.normal(size=(4, 6))
    model = make_model("chow_liu", params, seed=1).fit(X, np.zeros(4, dtype=int))
    law = model.class_models[0]
    np.testing.assert_allclose(law.probs[0].sum(), 1.0)
    for conditional in law.probs.values():
        np.testing.assert_allclose(conditional.sum(axis=1) if conditional.ndim == 2 else 1.0,
                                   np.ones(conditional.shape[0]) if conditional.ndim == 2 else 1.0)
    self.assertTrue(np.isfinite(model.class_logpdf(X)[:, 0]).all())
    self.assertTrue(np.isfinite(model.sample_class(0, 30, seed=12)).all())

  def test_complexity_keys_rank_stronger_smoothing_simpler(self):
    self.assertLess(complexity_key("gmm", {"n_components": 2, "covariance_type": "diag", "reg_covar": 1e-2}),
                    complexity_key("gmm", {"n_components": 2, "covariance_type": "diag", "reg_covar": 1e-4}))
    self.assertLess(complexity_key("copula", {"shrinkage": 0.5}),
                    complexity_key("copula", {"shrinkage": 0.05}))
    self.assertLess(complexity_key("kde", {"bandwidth": 1.0}),
                    complexity_key("kde", {"bandwidth": 0.1}))
    self.assertLess(complexity_key("chow_liu", {"n_bins": 8}),
                    complexity_key("chow_liu", {"n_bins": 16}))


  def test_chow_liu_piecewise_continuous_density_integrates_to_one(self):
    X, y = fixture()
    model = make_model("chow_liu", {"n_bins": 3}, seed=1).fit(X, y)
    for c in (0, 1):
        law = model.class_models[c]
        integral = 0.0
        widths = [np.diff(e) for e in law.edges]
        for bins in itertools.product(range(law.bins), repeat=6):
            center = np.array([law.edges[j][b] + widths[j][b] / 2 for j, b in enumerate(bins)])[None, :]
            density = np.exp(law.logpdf(center)[0])
            integral += density * np.prod([widths[j][b] for j, b in enumerate(bins)])
        np.testing.assert_allclose(integral, 1.0, atol=1e-10)


  def test_all_zero_density_fallback_is_visible_and_uses_empirical_priors(self):
    rng = np.random.default_rng(4)
    X = rng.normal(size=(20, 6))
    y = np.r_[np.zeros(15, dtype=int), np.ones(5, dtype=int)]
    model = make_model("chow_liu", {"n_bins": 4}, seed=1).fit(X, y)
    query = np.full((2, 6), 1e6)
    assert np.isneginf(model.class_logpdf(query)).all()
    scores = model.score_matrix(query)
    np.testing.assert_allclose(scores, np.tile([0.75, 0.25, 0, 0, 0, 0, 0], (2, 1)))
    assert model.fallback_count == 2
    np.testing.assert_array_equal(model.fallback_mask, [True, True])


if __name__ == "__main__":
    unittest.main()
