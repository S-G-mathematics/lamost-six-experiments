"""Adversarial Random Forest density models backed by ``arfpy`` FORDE/FORGE.

ARF is fitted independently within each class.  FORDE's continuous marginal
truncated-normal densities are evaluated for every forest tree and mixed with
the same uniform tree weights used by FORGE.  No classifier surrogate score is
used as a likelihood.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager

import numpy as np
from scipy.special import logsumexp
from scipy.stats import truncnorm

N_CLASSES = 7
CLASS_IDS = np.arange(N_CLASSES)
METHODS = {"arf"}
score_kind = "probability"

_RNG_LOCK = threading.Lock()
_FEATURES = [f"feature_{j}" for j in range(6)]


class UnsupportedARFError(RuntimeError):
    """Raised when the installed ARF implementation cannot fit valid FORDE."""


def _array(X):
    x = np.asarray(X, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 6 or not np.isfinite(x).all():
        raise ValueError("X must be a finite float64-compatible (N, 6) matrix")
    return x


@contextmanager
def _legacy_rng(seed):
    """Seed arfpy's pandas/NumPy global draws without leaking RNG state."""
    with _RNG_LOCK:
        state = np.random.get_state()
        np.random.seed(int(seed) % (2**32 - 1))
        try:
            yield
        finally:
            np.random.set_state(state)


class ARFDensityModel:
    """Seven class-conditional ARF/FORDE continuous density estimators."""

    score_kind = "probability"

    def __init__(self, params, seed=0, n_jobs=4):
        self.params = dict(params)
        self.seed = int(seed)
        self.n_jobs = int(n_jobs)
        if self.n_jobs < 1:
            raise ValueError("n_jobs must be positive")
        if self.params.get("finite_bounds", "no") != "no":
            raise ValueError("arfpy FORDE uses full-support outer leaf bounds; finite_bounds must be 'no'")

    def fit(self, X, y):
        x = _array(X)
        labels = np.asarray(y)
        if labels.ndim != 1 or len(labels) != len(x) or not np.issubdtype(labels.dtype, np.integer):
            raise ValueError("y must be an integer vector matching X")
        if not np.array_equal(np.unique(labels), CLASS_IDS):
            raise ValueError("all labels 0..6 must be present")

        trees = int(self.params["num_trees"])
        leaf = int(self.params["min_samples_leaf"])
        depth = self.params["max_depth"]
        if trees < 1 or leaf < 1:
            raise ValueError("num_trees and min_samples_leaf must be positive")
        if depth is not None and int(depth) < 1:
            raise ValueError("max_depth must be positive or None")

        try:
            import pandas as pd
            from arfpy import arf as arf_module
        except ImportError as exc:
            raise UnsupportedARFError("the real arfpy package is required for ARF density estimation") from exc

        self.priors_ = np.bincount(labels, minlength=N_CLASSES).astype(float) / len(labels)
        self.models_ = []
        self._param_maps = []
        for c in CLASS_IDS:
            xc = x[labels == c]
            if len(xc) < leaf:
                raise UnsupportedARFError(
                    f"class {c} has {len(xc)} rows, below ARF minimum leaf support {leaf}"
                )
            frame = pd.DataFrame(xc, columns=_FEATURES)
            # arfpy forwards these options to sklearn's RandomForestClassifier.
            # Its pandas resampling uses the NumPy legacy RNG; fence that state.
            with _legacy_rng(self.seed + int(c)):
                model = arf_module.arf(
                    x=frame,
                    num_trees=trees,
                    min_node_size=leaf,
                    max_depth=depth,
                    random_state=self.seed + int(c),
                    n_jobs=self.n_jobs,
                    verbose=False,
                )
                model.forde(dist="truncnorm", oob=False, alpha=0)

            params = model.params
            needed = {"tree", "nodeid", "variable", "mean", "sd", "min", "max"}
            if not needed.issubset(params.columns):
                raise UnsupportedARFError("arfpy FORDE returned an unexpected continuous parameter table")
            # A zero-variance FORDE marginal is a point mass, not a normalized
            # continuous density. Fail explicitly instead of inventing a floor.
            if params.empty or (params["sd"].to_numpy(dtype=float) <= 0).any():
                raise UnsupportedARFError(f"class {c} has a singular FORDE continuous marginal")
            if not np.isfinite(params[["mean", "sd"]].to_numpy(dtype=float)).all():
                raise UnsupportedARFError(f"class {c} FORDE parameters are non-finite")
            if np.isnan(params[["min", "max"]].to_numpy(dtype=float)).any():
                raise UnsupportedARFError(f"class {c} FORDE bounds contain NaN")

            # Store compact per-tree / leaf / feature arrays for fast batched scoring.
            maps = {}
            leaf_coverage = (
                model.bnds[["tree", "nodeid", "cvg"]]
                .drop_duplicates(["tree", "nodeid"])
                .set_index(["tree", "nodeid"])["cvg"]
            )
            for (tree_id, leaf_id), group in params.groupby(["tree", "nodeid"], sort=False):
                group = group.set_index("variable").reindex(_FEATURES)
                if group["mean"].isna().any():
                    raise UnsupportedARFError(f"class {c} FORDE omitted a feature parameter")
                coverage = float(leaf_coverage.get((tree_id, leaf_id), 0.0))
                if not np.isfinite(coverage) or coverage < 0:
                    raise UnsupportedARFError(f"class {c} FORDE returned invalid leaf coverage")
                maps[(int(tree_id), int(leaf_id))] = tuple(
                    group[col].to_numpy(dtype=float) for col in ("mean", "sd", "min", "max")
                ) + (coverage,)
            self.models_.append(model)
            self._param_maps.append(maps)

        self._validate_density(x[: min(8, len(x))])
        return self

    def _one_class_logpdf(self, X, class_id):
        x = _array(X)
        model = self.models_[class_id]
        maps = self._param_maps[class_id]
        # Preserve the feature names used to fit arfpy's sklearn discriminator.
        import pandas as pd
        leaves = model.clf.apply(pd.DataFrame(x, columns=_FEATURES))
        if leaves.ndim == 1:
            leaves = leaves[:, None]
        total = np.full(len(x), -np.inf, dtype=np.float64)
        for tree_id in range(model.num_trees):
            node_ids = leaves[:, tree_id]
            tree_logpdf = np.full(len(x), -np.inf, dtype=np.float64)
            for node_id in np.unique(node_ids):
                entry = maps.get((tree_id, int(node_id)))
                if entry is None:
                    continue
                mean, sd, low, high, coverage = entry
                if coverage <= 0:
                    continue
                rows = node_ids == node_id
                a = (low - mean) / sd
                b = (high - mean) / sd
                # FORDE uses the same leaf-specific truncated normal as FORGE.
                vals = truncnorm.logpdf(x[rows], a=a, b=b, loc=mean, scale=sd)
                tree_logpdf[rows] = np.log(coverage) + np.sum(vals, axis=1)
            total = np.logaddexp(total, tree_logpdf)
        return total - np.log(model.num_trees)

    def _validate_density(self, X):
        values = self.class_logpdf(X)
        if np.isnan(values).any() or np.isposinf(values).any():
            raise UnsupportedARFError("ARF/FORDE produced invalid continuous log densities")
        # Each tree component is a normalized product of truncated normals and
        # tree weights sum to one. Explicitly require finite mass on the fixture.
        if not np.isfinite(values).any():
            raise UnsupportedARFError("ARF/FORDE assigns zero density to all validation observations")

    def class_logpdf(self, X):
        x = _array(X)
        return np.column_stack([self._one_class_logpdf(x, c) for c in CLASS_IDS])

    def score_matrix(self, X):
        joint = self.class_logpdf(X) + np.log(self.priors_)
        normalizer = logsumexp(joint, axis=1, keepdims=True)
        if not np.isfinite(normalizer).all():
            raise UnsupportedARFError("all ARF class densities are zero for at least one query row")
        return np.exp(joint - normalizer)

    def predict(self, X):
        joint = self.class_logpdf(X) + np.log(self.priors_)
        if not np.isfinite(logsumexp(joint, axis=1)).all():
            raise UnsupportedARFError("all ARF class densities are zero for at least one query row")
        return np.argmax(joint, axis=1)

    def predict_proba(self, X):
        return self.score_matrix(X)

    def sample_class(self, class_id, n, seed):
        c, n = int(class_id), int(n)
        if c not in CLASS_IDS or n < 0:
            raise ValueError("class_id must be 0..6 and n must be nonnegative")
        if not hasattr(self, "models_"):
            raise RuntimeError("fit the ARF model before sampling")
        with _legacy_rng(seed):
            sample = self.models_[c].forge(n=n)
        result = np.asarray(sample[_FEATURES], dtype=np.float64)
        if result.shape != (n, 6) or not np.isfinite(result).all():
            raise UnsupportedARFError("arfpy FORGE returned invalid samples")
        return result


def make_model(method="arf", params=None, seed=0, n_jobs=4):
    if method != "arf":
        raise ValueError(f"unsupported method: {method}")
    params = {} if params is None else dict(params)
    required = {"num_trees", "min_samples_leaf", "max_depth"}
    if not required.issubset(params):
        raise ValueError(f"arf requires parameters {sorted(required)}")
    return ARFDensityModel(params, seed=seed, n_jobs=n_jobs)


def suggest_parameters(trial, method, n_fit, min_class):
    if method != "arf":
        raise ValueError(f"unsupported method: {method}")
    n_fit, min_class = int(n_fit), int(min_class)
    if n_fit < 1 or min_class < 1:
        raise ValueError("ARF requires positive fitting and per-class support")
    leaves = [min_class] if min_class < 5 else [v for v in (5, 20, 100) if v <= min_class]
    if not leaves:
        raise ValueError("unsupported: ARF requires at least five observations per class")
    return {
        "num_trees": trial.suggest_categorical("num_trees", [100, 300]),
        "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", leaves),
        "max_depth": trial.suggest_categorical("max_depth", [None, 10]),
        "finite_bounds": "no",
        "density_dist": "truncnorm",
    }


def complexity_key(method, params):
    if method != "arf":
        raise ValueError(f"unsupported method: {method}")
    p = params
    return (
        int(p["num_trees"]),
        float("inf") if p["max_depth"] is None else int(p["max_depth"]),
        -int(p["min_samples_leaf"]),
    )
