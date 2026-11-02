"""Flexible class-conditional density models used by the LAMOST benchmark.

All methods use the six-dimensional fitting coordinate system supplied by the
engine. Chow--Liu is a piecewise-constant continuous density: its class-wise
histogram bins have bounded support, smoothed categorical conditional masses,
and a uniform density within each selected bin. The same law is used for
scoring and sampling. The 8/16/32-bin Chow--Liu choices remain valid when a
class has fewer rows than bins because positive Laplace smoothing supports all
cells. These configurations have weak class support and high variance, but are
not silently changed or treated as invalid density fits.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.special import log_ndtr, logsumexp, ndtr, ndtri, ndtri_exp
from sklearn.mixture import GaussianMixture

N_FEATURES = 6
N_CLASSES = 7
LABELS = np.arange(N_CLASSES)


def suggest_parameters(trial: Any, method: str, n_fit: int, min_class: int) -> dict:
    """Suggest one valid configuration, restricting class-wise model size."""
    if method == "gmm":
        choices = [k for k in (1, 2, 4, 8, 16) if k <= min_class]
        if not choices:
            raise ValueError("GMM requires at least one fitting observation per class")
        return {
            "n_components": trial.suggest_categorical("n_components", choices),
            "covariance_type": trial.suggest_categorical("covariance_type", ["diag", "full"]),
            "reg_covar": trial.suggest_float("reg_covar", 1e-6, 1e-2, log=True),
        }
    if method == "copula":
        return {
            "marginal": trial.suggest_categorical("marginal", ["histogram_tail"]),
            "shrinkage": trial.suggest_categorical("shrinkage", [0.0, 0.05, 0.2, 0.5]),
        }
    if method == "kde":
        return {"bandwidth": trial.suggest_float("bandwidth", 0.05, 2.0, log=True)}
    if method == "chow_liu":
        # Laplace-smoothed conditional histograms are normalized for any
        # positive sample count, including counts below the number of bins.
        # In that regime the model is valid but weakly supported; retain the
        # frozen 8/16/32 search domain and report class counts with results.
        choices = [8, 16, 32]
        return {"n_bins": trial.suggest_categorical("n_bins", choices)}
    raise ValueError(f"unknown flexible density method: {method}")


def complexity_key(method: str, params: dict) -> tuple:
    """Frozen simple-first tie-break order within each flexible family."""
    if method == "gmm":
        # Lower component count, diagonal covariance and stronger regularization
        # each reduce effective model complexity.
        return (int(params["n_components"]), 0 if params["covariance_type"] == "diag" else 1,
                -float(params["reg_covar"]))
    if method == "copula":
        return (-float(params["shrinkage"]), params.get("marginal", "histogram_tail"))
    if method == "kde":
        return (-float(params["bandwidth"]),)
    if method == "chow_liu":
        return (int(params["n_bins"]),)
    raise ValueError(f"unknown flexible density method: {method}")


def make_model(method: str, params: dict, seed: int, n_jobs: int = 4):
    del n_jobs  # These exact density implementations do not use worker pools.
    params = dict(params)
    if method == "gmm":
        return _FlexibleModel(method, params, seed)
    if method == "copula":
        if params.get("marginal", "histogram_tail") not in {"histogram_tail", "smoothed"}:
            raise ValueError("copula marginal must be 'histogram_tail'")
        return _FlexibleModel(method, params, seed)
    if method == "kde":
        return _FlexibleModel(method, params, seed)
    if method == "chow_liu":
        return _FlexibleModel(method, params, seed)
    raise ValueError(f"unknown flexible density method: {method}")


def _check_x(X):
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != N_FEATURES or not np.isfinite(X).all():
        raise ValueError("X must be a finite N x 6 float64 matrix")
    return X


class _FlexibleModel:
    score_kind = "probability"

    def __init__(self, method, params, seed):
        self.method, self.params, self.seed = method, params, int(seed)
        self.class_models = [None] * N_CLASSES
        self.priors = np.zeros(N_CLASSES, dtype=np.float64)
        self.fallback_count = 0
        self.fallback_mask = None

    def fit(self, X, y):
        X = _check_x(X)
        y = np.asarray(y, dtype=np.int64)
        if y.shape != (len(X),) or np.any((y < 0) | (y >= N_CLASSES)):
            raise ValueError("y must be an N-vector of labels 0..6")
        counts = np.bincount(y, minlength=N_CLASSES)
        if not len(y):
            raise ValueError("cannot fit an empty sample")
        self.priors = counts.astype(float) / len(y)
        for c in LABELS:
            rows = X[y == c]
            if not len(rows):
                self.class_models[c] = None  # unsupported: exactly zero density
                continue
            if self.method == "gmm":
                k = int(self.params["n_components"])
                if k > len(rows):
                    raise ValueError(f"GMM components {k} exceed class {c} support {len(rows)}")
                model = GaussianMixture(
                    n_components=k,
                    covariance_type=self.params["covariance_type"],
                    reg_covar=float(self.params["reg_covar"]),
                    random_state=self.seed + int(c),
                    n_init=1,
                ).fit(rows)
            elif self.method == "kde":
                model = _KDE(rows, float(self.params["bandwidth"]))
            elif self.method == "copula":
                model = _Copula(rows, float(self.params["shrinkage"]))
            else:
                model = _ChowLiu(rows, int(self.params["n_bins"]))
            self.class_models[c] = model
        self.fallback_count = 0
        self.fallback_mask = None
        return self

    def class_logpdf(self, X):
        X = _check_x(X)
        out = np.full((len(X), N_CLASSES), -np.inf, dtype=np.float64)
        for c, model in enumerate(self.class_models):
            if model is not None:
                out[:, c] = model.score_samples(X) if self.method == "gmm" else model.logpdf(X)
        return out

    def score_matrix(self, X):
        lp = self.class_logpdf(X)
        log_joint = lp + np.where(self.priors > 0, np.log(np.maximum(self.priors, 1e-300)), -np.inf)
        norm = logsumexp(log_joint, axis=1)
        bad = ~np.isfinite(norm)
        self.fallback_mask = bad.copy()
        self.fallback_count = int(bad.sum())
        scores = np.zeros_like(log_joint)
        good = ~bad
        scores[good] = np.exp(log_joint[good] - norm[good, None])
        # Only when every prior-weighted density is zero: use empirical priors.
        scores[bad] = self.priors
        return scores

    def predict_proba(self, X):
        return self.score_matrix(X)

    def predict(self, X):
        return np.argmax(self.score_matrix(X), axis=1)

    def sample_class(self, c, n, seed):
        c, n = int(c), int(n)
        if not 0 <= c < N_CLASSES or n < 0:
            raise ValueError("class must be 0..6 and sample size nonnegative")
        model = self.class_models[c]
        if model is None:
            raise ValueError(f"class {c} has no fitting support")
        if self.method == "gmm":
            rng = np.random.default_rng(seed)
            components = rng.choice(model.n_components, size=n, p=model.weights_)
            out = np.empty((n, N_FEATURES))
            for k in range(model.n_components):
                mask = components == k
                if not mask.any():
                    continue
                if model.covariance_type == "diag":
                    out[mask] = rng.normal(model.means_[k], np.sqrt(model.covariances_[k]), (mask.sum(), N_FEATURES))
                else:
                    out[mask] = rng.multivariate_normal(model.means_[k], model.covariances_[k], size=mask.sum())
            return out
        return model.sample(n, np.random.default_rng(seed))


class _KDE:
    def __init__(self, rows, bandwidth):
        if bandwidth <= 0:
            raise ValueError("bandwidth must be positive")
        self.rows, self.bandwidth = rows.copy(), bandwidth
        self.log_norm = -N_FEATURES * np.log(bandwidth * np.sqrt(2 * np.pi)) - np.log(len(rows))

    def logpdf(self, X):
        # Exact Gaussian-mixture KDE, accumulated in bounded blocks. The
        # quadratic identity avoids an N_query x N_reference x 6 tensor.
        out = np.empty(len(X), dtype=np.float64)
        row_sq = np.einsum("ij,ij->i", self.rows, self.rows)
        q_block, ref_block = 128, 16_384
        for q0 in range(0, len(X), q_block):
            q = X[q0:q0 + q_block]
            q_sq = np.einsum("ij,ij->i", q, q)
            accum = np.full(len(q), -np.inf)
            for r0 in range(0, len(self.rows), ref_block):
                refs = self.rows[r0:r0 + ref_block]
                d2 = q_sq[:, None] + row_sq[None, r0:r0 + ref_block] - 2.0 * (q @ refs.T)
                np.maximum(d2, 0.0, out=d2)
                part = logsumexp(-0.5 * d2 / (self.bandwidth * self.bandwidth), axis=1)
                accum = np.logaddexp(accum, part)
            out[q0:q0 + len(q)] = self.log_norm + accum
        return out

    def sample(self, n, rng):
        if n == 0:
            return np.empty((0, N_FEATURES))
        return self.rows[rng.integers(len(self.rows), size=n)] + rng.normal(0, self.bandwidth, (n, N_FEATURES))


class _Copula:
    """Gaussian copula with normalized histogram-and-exponential marginals."""
    def __init__(self, rows, shrinkage):
        if not 0 <= shrinkage <= 1:
            raise ValueError("shrinkage must be between 0 and 1")
        self.marginals = [_HistogramTailMarginal(rows[:, j]) for j in range(N_FEATURES)]
        z = self._normal_scores(rows)
        corr = np.corrcoef(z, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0)
        np.fill_diagonal(corr, 1.0)
        corr = (1 - shrinkage) * corr + shrinkage * np.eye(N_FEATURES)
        # A fixed numerical nugget keeps the Gaussian law positive definite,
        # including the explicitly requested zero-shrinkage case.
        corr = corr + np.eye(N_FEATURES) * 1e-10
        d = np.sqrt(np.diag(corr))
        self.corr = corr / np.outer(d, d)
        self.chol = np.linalg.cholesky(self.corr)
        self.inv = np.linalg.inv(self.corr)
        self.logdet = 2 * np.log(np.diag(self.chol)).sum()

    def _normal_scores(self, X):
        Z = np.empty_like(X)
        for j in range(N_FEATURES):
            Z[:, j] = self.marginals[j].normal_score(X[:, j])
        return Z

    def logpdf(self, X):
        z = self._normal_scores(X)
        copula = -0.5 * self.logdet - 0.5 * np.einsum("ni,ij,nj->n", z, self.inv - np.eye(N_FEATURES), z)
        marginal = sum(self.marginals[j].logpdf(X[:, j]) for j in range(N_FEATURES))
        return copula + marginal

    def sample(self, n, rng):
        if n == 0:
            return np.empty((0, N_FEATURES))
        z = rng.normal(size=(n, N_FEATURES)) @ self.chol.T
        out = np.empty_like(z)
        for j in range(N_FEATURES):
            out[:, j] = self.marginals[j].ppf_from_normal(z[:, j])
        return out


class _HistogramTailMarginal:
    """Piecewise-constant histogram density with exponential tail masses.

    Half a count is added to every histogram bin. Each tail receives epsilon =
    1/(2*n+2) mass; the remaining mass is spread according to smoothed bin
    probabilities. Tail scale equals the common interior bin width. CDF, PDF,
    normal-score and inverse-normal-score operations are analytic and mutually
    consistent, with full real support and no CDF clipping.
    """
    def __init__(self, values):
        values = np.asarray(values, dtype=np.float64)
        n = len(values)
        bins = min(256, max(8, int(np.ceil(n ** (1 / 3)))))
        lo, hi = float(values.min()), float(values.max())
        if lo == hi:
            delta = max(abs(lo), 1.0) * 1e-6
            lo, hi = lo - delta, hi + delta
        self.edges = np.linspace(lo, hi, bins + 1)
        counts, _ = np.histogram(values, bins=self.edges)
        probs = counts.astype(np.float64) + 0.5
        probs /= probs.sum()
        self.eps = 1.0 / (2 * n + 2)
        self.mass = probs * (1 - 2 * self.eps)
        self.cum = np.r_[0.0, np.cumsum(self.mass)]
        self.widths = np.diff(self.edges)
        self.tail_scale = float(self.widths[0])

    def cdf(self, x):
        x = np.asarray(x, dtype=np.float64)
        out = np.empty_like(x)
        left = x < self.edges[0]
        right = x > self.edges[-1]
        mid = ~(left | right)
        out[left] = self.eps * np.exp((x[left] - self.edges[0]) / self.tail_scale)
        out[right] = 1 - self.eps * np.exp(-(x[right] - self.edges[-1]) / self.tail_scale)
        if mid.any():
            xb = x[mid]
            ix = np.clip(np.searchsorted(self.edges, xb, side="right") - 1, 0, len(self.mass) - 1)
            out[mid] = self.eps + self.cum[ix] + self.mass[ix] * (xb - self.edges[ix]) / self.widths[ix]
        return out

    def logpdf(self, x):
        x = np.asarray(x, dtype=np.float64)
        out = np.empty_like(x)
        left = x < self.edges[0]
        right = x > self.edges[-1]
        mid = ~(left | right)
        out[left] = np.log(self.eps / self.tail_scale) + (x[left] - self.edges[0]) / self.tail_scale
        out[right] = np.log(self.eps / self.tail_scale) - (x[right] - self.edges[-1]) / self.tail_scale
        if mid.any():
            ix = np.clip(np.searchsorted(self.edges, x[mid], side="right") - 1, 0, len(self.mass) - 1)
            out[mid] = np.log(self.mass[ix] / self.widths[ix])
        return out

    def normal_score(self, x):
        x = np.asarray(x, dtype=np.float64)
        z = np.empty_like(x)
        left = x < self.edges[0]
        right = x > self.edges[-1]
        mid = ~(left | right)
        if left.any():
            z[left] = ndtri_exp(np.log(self.eps) + (x[left] - self.edges[0]) / self.tail_scale)
        if right.any():
            logsf = np.log(self.eps) - (x[right] - self.edges[-1]) / self.tail_scale
            z[right] = -ndtri_exp(logsf)
        if mid.any():
            z[mid] = ndtri(self.cdf(x[mid]))
        return z

    def ppf_from_normal(self, z):
        z = np.asarray(z, dtype=np.float64)
        x = np.empty_like(z)
        left = z < ndtri(self.eps)
        right = z > -ndtri(self.eps)
        mid = ~(left | right)
        if left.any():
            x[left] = self.edges[0] + self.tail_scale * (log_ndtr(z[left]) - np.log(self.eps))
        if right.any():
            x[right] = self.edges[-1] - self.tail_scale * (log_ndtr(-z[right]) - np.log(self.eps))
        if mid.any():
            u = ndtr(z[mid]) - self.eps
            ix = np.searchsorted(self.cum[1:], u, side="right")
            ix = np.clip(ix, 0, len(self.mass) - 1)
            x[mid] = self.edges[ix] + (u - self.cum[ix]) / self.mass[ix] * self.widths[ix]
        return x


class _ChowLiu:
    """Discrete Chow--Liu tree with continuous uniform-within-bin densities."""
    def __init__(self, rows, n_bins):
        if n_bins < 1:
            raise ValueError("Chow-Liu bin count must be positive")
        self.bins = int(n_bins)
        self.edges = []
        for j in range(N_FEATURES):
            a, b = np.min(rows[:, j]), np.max(rows[:, j])
            if a == b:
                delta = max(abs(a), 1.0) * 1e-6
                a, b = a - delta, b + delta
            self.edges.append(np.linspace(a, b, self.bins + 1))
        idx = self._indices(rows)
        alpha = 0.5
        pair_mi = np.zeros((N_FEATURES, N_FEATURES))
        for i in range(N_FEATURES):
            for j in range(i):
                counts = np.full((self.bins, self.bins), alpha)
                np.add.at(counts, (idx[:, i], idx[:, j]), 1)
                p = counts / counts.sum()
                pi, pj = p.sum(1), p.sum(0)
                pair_mi[i, j] = pair_mi[j, i] = np.sum(p * np.log(p / (pi[:, None] * pj[None, :])))
        self.parent = np.full(N_FEATURES, -2, dtype=int)
        self.parent[0] = -1
        included = {0}
        # Prim maximum spanning tree, deterministic under equal weights.
        while len(included) < N_FEATURES:
            best = None
            for child in range(N_FEATURES):
                if child in included:
                    continue
                for par in sorted(included):
                    key = (pair_mi[child, par], -child, -par)
                    if best is None or key > best[0]:
                        best = (key, child, par)
            _, child, par = best
            self.parent[child] = par
            included.add(child)
        self.order = [0]
        while len(self.order) < N_FEATURES:
            self.order.extend(j for j in range(N_FEATURES) if self.parent[j] in self.order and j not in self.order)
        self.probs = {}
        counts = np.full(self.bins, alpha)
        np.add.at(counts, idx[:, 0], 1)
        self.probs[0] = counts / counts.sum()
        for child in range(1, N_FEATURES):
            par = self.parent[child]
            counts = np.full((self.bins, self.bins), alpha)
            np.add.at(counts, (idx[:, par], idx[:, child]), 1)
            self.probs[child] = counts / counts.sum(axis=1, keepdims=True)

    def _indices(self, X):
        return np.column_stack([np.clip(np.searchsorted(e, X[:, j], side="right") - 1, 0, self.bins - 1)
                                for j, e in enumerate(self.edges)])

    def logpdf(self, X):
        inside = np.column_stack([(X[:, j] >= e[0]) & (X[:, j] <= e[-1]) for j, e in enumerate(self.edges)]).all(axis=1)
        out = np.full(len(X), -np.inf)
        if not inside.any():
            return out
        idx = self._indices(X[inside])
        val = np.log(self.probs[0][idx[:, 0]]) - np.log(np.diff(self.edges[0])[idx[:, 0]])
        for child in self.order[1:]:
            par = self.parent[child]
            val += np.log(self.probs[child][idx[:, par], idx[:, child]]) - np.log(np.diff(self.edges[child])[idx[:, child]])
        out[inside] = val
        return out

    def sample(self, n, rng):
        if n == 0:
            return np.empty((0, N_FEATURES))
        idx = np.zeros((n, N_FEATURES), dtype=int)
        idx[:, 0] = rng.choice(self.bins, size=n, p=self.probs[0])
        for child in self.order[1:]:
            par = self.parent[child]
            for parent_bin in range(self.bins):
                mask = idx[:, par] == parent_bin
                if mask.any():
                    idx[mask, child] = rng.choice(self.bins, mask.sum(), p=self.probs[child][parent_bin])
        X = np.empty((n, N_FEATURES))
        for j, e in enumerate(self.edges):
            X[:, j] = e[idx[:, j]] + rng.random(n) * (e[idx[:, j] + 1] - e[idx[:, j]])
        return X
