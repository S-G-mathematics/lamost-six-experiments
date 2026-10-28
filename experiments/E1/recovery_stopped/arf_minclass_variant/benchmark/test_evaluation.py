import numpy as np
import pytest

from benchmark.evaluation import balanced_accuracy, conformal_evaluate, conformal_threshold, bootstrap_outcomes
from benchmark.ensembles import equal_weight_posteriors, ensemble_scores, fit_ensemble_weights
from benchmark.fidelity import class_fidelity_report, spearman_by_budget_repetition


def test_balanced_accuracy_is_explicitly_seven_class_macro_recall():
    y = np.repeat(np.arange(7), [8, 1, 1, 1, 1, 1, 1])
    pred = y.copy()
    pred[:4] = 1
    assert balanced_accuracy(y, pred) == pytest.approx((0.5 + 6) / 7)
    with pytest.raises(ValueError, match="every class"):
        balanced_accuracy(np.array([0, 1]), np.array([0, 1]))


def test_conformal_threshold_probability_margin_and_empty_set():
    y = np.arange(7)
    probability = np.eye(7)
    # m=7 and alpha=.1 gives k=ceil(7.2)=8, hence infinity.
    assert conformal_threshold(probability, y) == np.inf
    # With m=9, k=9 and the ninth score is the maximum among truth scores.
    cal = np.tile(np.eye(7), (2, 1))[:9]
    ycal = np.arange(9) % 7
    assert conformal_threshold(cal, ycal) == pytest.approx(0.0)
    margin = np.zeros((7, 7))
    assert conformal_threshold(margin, y, score_kind="margin") == np.inf
    result = conformal_evaluate(np.eye(7), y, threshold=-2.0)
    assert result["sets"].shape == (7, 7)
    assert result["set_sizes"].tolist() == [0] * 7
    assert result["coverage"] == 0


def test_bootstrap_uses_saved_rows_and_returns_paired_difference():
    y = np.arange(7)
    perfect = {"predictions": y.copy(), "covered": np.ones(7, bool), "set_sizes": np.ones(7)}
    shifted = {"predictions": (y + 1) % 7, "covered": np.zeros(7, bool), "set_sizes": np.zeros(7)}
    result = bootstrap_outcomes(y, {"a": perfect, "b": shifted}, n_boot=20, seed=13)
    assert result["conditional_on_fitted_pipelines"] is True
    assert result["point_estimates"]["a"]["balanced_accuracy"] == 1
    assert result["paired_differences"]["coverage"]["a - b"]["estimate"] == 1


def test_ensemble_search_is_five_member_probability_average_and_deterministic():
    y = np.tile(np.arange(7), 3)
    eye = np.eye(7)[y]
    weak = np.full((len(y), 7), 1 / 7)
    inputs = {name: eye if name == "gmm" else weak for name in ("gmm", "copula", "arf", "kde", "chow_liu")}
    assert np.allclose(equal_weight_posteriors(inputs).sum(axis=1), 1)
    assert np.allclose(ensemble_scores(inputs, np.full(5, .2)), equal_weight_posteriors(inputs))
    first = fit_ensemble_weights(inputs, y, seed=91, dirichlet_candidates=30, candidate_cap=200)
    second = fit_ensemble_weights(inputs, y, seed=91, dirichlet_candidates=30, candidate_cap=200)
    assert first["weights"] == second["weights"]
    assert first["candidate_count"] == second["candidate_count"] <= 200
    assert np.isclose(sum(first["weights"]), 1)
    assert first["tuning_balanced_accuracy"] >= 1 / 7


def test_fidelity_runs_all_seven_six_feature_reports_without_undefined_scores():
    class Model:
        def sample_class(self, c, n, seed):
            rng = np.random.default_rng(seed + c)
            latent = rng.normal(size=(n, 1))
            return latent + rng.normal(scale=.12, size=(n, 6)) + c * .1

    rng = np.random.default_rng(120)
    y = np.repeat(np.arange(7), 50)
    X = np.vstack([rng.normal(size=(50, 1)) + rng.normal(scale=.12, size=(50, 6)) + c * .1
                   for c in range(7)])
    report = class_fidelity_report(Model(), X, y, seed=2)
    assert report["status"] == "ok"
    assert report["score"] is not None
    assert all(report["per_class"][c]["status"] == "ok" for c in range(7))
    assert all(report["per_class"][c]["score"] is not None for c in range(7))
    assert all(len(report["per_class"][c]["property_scores"]) == 2 for c in range(7))
    rows = [dict(family=f, budget=3000, repetition=0, fidelity=1., balanced_accuracy=.5)
            for f in ("gmm", "copula", "arf", "kde", "chow_liu")]
    rho = spearman_by_budget_repetition(rows)[0]
    assert rho["spearman_rho"] is None
    assert "fixed-family" in rho["interpretation_limit"]
