"""Classical Gaussian and discriminative benchmark models.

All inputs are already transformed by the benchmark's fitting-only scaler when
appropriate.  Generative models retain their fitted Gaussian parameters so
their class-conditional log densities and samples use exactly the same model as
their direct predictions.
"""
from __future__ import annotations

import numpy as np
from scipy.special import logsumexp
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC, LinearSVC
from sklearn.tree import DecisionTreeClassifier

N_CLASSES = 7
CLASS_IDS = np.arange(N_CLASSES)
GENERATIVE = {"gaussian_nb", "shared_diagonal", "lda", "qda"}
DISCRIMINATIVE = {"logistic", "linear_svm", "rbf_svm", "knn", "cart", "random_forest", "extra_trees", "hist_gb"}
METHODS = GENERATIVE | DISCRIMINATIVE


def _array(X):
    x = np.asarray(X, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 6 or not np.isfinite(x).all():
        raise ValueError("X must be a finite float64-compatible (N, 6) matrix")
    return x


def _logpdf(X, means, covs):
    x = _array(X)
    out = np.empty((len(x), N_CLASSES), dtype=np.float64)
    d = x.shape[1]
    for c in CLASS_IDS:
        delta = x - means[c]
        sign, logdet = np.linalg.slogdet(covs[c])
        if sign <= 0 or not np.isfinite(logdet):
            raise ValueError(f"class {c} covariance is not positive definite")
        sol = np.linalg.solve(covs[c], delta.T).T
        out[:, c] = -0.5 * (d * np.log(2 * np.pi) + logdet + np.einsum("ij,ij->i", delta, sol))
    return out


class GaussianDensityModel:
    """A class Gaussian model with normalized densities and empirical priors."""
    score_kind = "probability"

    def __init__(self, method, params):
        self.method = method
        self.params = dict(params)

    def fit(self, X, y):
        x = _array(X)
        y = np.asarray(y)
        if y.ndim != 1 or len(y) != len(x) or not np.issubdtype(y.dtype, np.integer):
            raise ValueError("y must be an integer vector matching X")
        if not np.array_equal(np.unique(y), CLASS_IDS):
            raise ValueError("all labels 0..6 must be present")
        groups = [x[y == c] for c in CLASS_IDS]
        if any(len(z) < 2 for z in groups):
            raise ValueError("each Gaussian class requires at least two fitting rows")
        self.priors_ = np.array([len(z) for z in groups], dtype=float) / len(x)
        self.means_ = np.stack([z.mean(axis=0) for z in groups])
        p = self.params
        if self.method == "gaussian_nb":
            floor = float(p["var_smoothing"]) * max(float(np.var(x, axis=0).max()), np.finfo(float).tiny)
            variances = np.stack([np.mean((z - z.mean(axis=0)) ** 2, axis=0) for z in groups])
            variances = np.maximum(variances, floor)
            self.covs_ = np.array([np.diag(v) for v in variances])
        elif self.method == "shared_diagonal":
            floor = float(p["variance_floor"])
            within = sum(((z - z.mean(axis=0)) ** 2).sum(axis=0) for z in groups) / (len(x) - N_CLASSES)
            self.covs_ = np.repeat(np.diag(np.maximum(within, floor))[None, :, :], N_CLASSES, axis=0)
        elif self.method == "lda":
            # Pooled within-class MLE covariance, shrunk toward its diagonal.
            residuals = np.concatenate([z - z.mean(axis=0) for z in groups], axis=0)
            raw = residuals.T @ residuals / len(x)
            shrink = p["shrinkage"]
            if shrink == "auto":
                # Ledoit-Wolf is the standard data-adaptive LDA shrinkage rule.
                from sklearn.covariance import ledoit_wolf
                common, _ = ledoit_wolf(residuals, assume_centered=True)
            else:
                a = float(shrink)
                common = (1 - a) * raw + a * np.diag(np.diag(raw))
            self.covs_ = np.repeat(_positive_cov(common, float(p.get("variance_floor", 1e-8)))[None, :, :], N_CLASSES, axis=0)
        elif self.method == "qda":
            alpha, floor = float(p["reg_param"]), float(p["variance_floor"])
            covs = []
            for z in groups:
                centered = z - z.mean(axis=0)
                cov = centered.T @ centered / len(z)
                scale = max(float(np.trace(cov) / cov.shape[0]), floor)
                shrunk = (1 - alpha) * cov + alpha * scale * np.eye(cov.shape[0])
                covs.append(_positive_cov(shrunk, floor))
            self.covs_ = np.stack(covs)
        else:
            raise ValueError(f"unsupported Gaussian method: {self.method}")
        self.class_logpdf(x[:1])  # fail early if a numerical issue remains
        return self

    def class_logpdf(self, X):
        return _logpdf(X, self.means_, self.covs_)

    def score_matrix(self, X):
        joint = self.class_logpdf(X) + np.log(self.priors_)
        return np.exp(joint - logsumexp(joint, axis=1, keepdims=True))

    def predict(self, X):
        return np.argmax(self.class_logpdf(X) + np.log(self.priors_), axis=1)

    def predict_proba(self, X):
        return self.score_matrix(X)

    def sample_class(self, class_id, n, seed):
        c, n = int(class_id), int(n)
        if c not in CLASS_IDS or n < 0:
            raise ValueError("class_id must be 0..6 and n must be nonnegative")
        return np.random.default_rng(seed).multivariate_normal(self.means_[c], self.covs_[c], size=n)


def _positive_cov(cov, floor):
    vals, vecs = np.linalg.eigh((cov + cov.T) * 0.5)
    vals = np.maximum(vals, floor)
    return (vecs * vals) @ vecs.T


class ClassifierModel:
    def __init__(self, estimator, score_kind):
        self.estimator, self.score_kind = estimator, score_kind

    def fit(self, X, y):
        x = _array(X)
        y = np.asarray(y)
        if y.ndim != 1 or len(y) != len(x) or not np.issubdtype(y.dtype, np.integer):
            raise ValueError("y must be an integer vector matching X")
        if not np.array_equal(np.unique(y), CLASS_IDS):
            raise ValueError("all labels 0..6 must be present")
        self.estimator.fit(x, y)
        if not np.array_equal(self.estimator.classes_, CLASS_IDS):
            raise ValueError("estimator did not preserve all classes 0..6")
        return self

    def predict(self, X):
        # Use the same fixed-order score argmax for every family.  In
        # particular, libsvm's multiclass prediction is based on pairwise
        # voting and can disagree with its returned OVR-shaped margins.
        return np.argmax(self.score_matrix(X), axis=1).astype(np.int64)

    def score_matrix(self, X):
        x = _array(X)
        if self.score_kind == "probability":
            result = self.estimator.predict_proba(x)
        else:
            result = self.estimator.decision_function(x)
            # LinearSVC and SVC expose OVR matrices with the configured API.
        result = np.asarray(result, dtype=np.float64)
        if result.shape != (len(x), N_CLASSES) or not np.isfinite(result).all():
            raise ValueError("classifier returned invalid or non-7-column scores")
        return result

    def predict_proba(self, X):
        if self.score_kind != "probability":
            raise AttributeError("this SVM has margins, not native probabilities")
        return self.score_matrix(X)


def make_model(method, params, seed, n_jobs=4):
    """Construct one of the 12 requested methods; no hidden substitutions."""
    params = dict(params)
    seed = int(seed)
    jobs = int(n_jobs)
    if jobs < 1:
        raise ValueError("n_jobs must be positive")
    if method in GENERATIVE:
        required = {
            "gaussian_nb": {"var_smoothing"},
            "shared_diagonal": {"variance_floor"},
            "lda": {"shrinkage"},
            "qda": {"reg_param", "variance_floor"},
        }[method]
        if not required.issubset(params):
            raise ValueError(f"{method} requires parameters {sorted(required)}")
        return GaussianDensityModel(method, params)
    if method not in DISCRIMINATIVE:
        raise ValueError(f"unsupported method: {method}")
    if method == "logistic":
        est = LogisticRegression(C=float(params["C"]), solver="lbfgs", max_iter=2000, random_state=seed)
    elif method == "linear_svm":
        est = LinearSVC(C=float(params["C"]), random_state=seed, max_iter=10000)
    elif method == "rbf_svm":
        est = SVC(C=float(params["C"]), gamma=float(params["gamma"]), kernel="rbf", decision_function_shape="ovr", break_ties=True, cache_size=float(params.get("cache_size_mb", 512)), random_state=seed)
    elif method == "knn":
        est = KNeighborsClassifier(n_neighbors=int(params["n_neighbors"]), weights=params["weights"], algorithm="auto", metric="euclidean", n_jobs=jobs)
    elif method == "cart":
        est = DecisionTreeClassifier(max_depth=params["max_depth"], min_samples_leaf=int(params["min_samples_leaf"]), random_state=seed)
    elif method == "random_forest":
        est = RandomForestClassifier(n_estimators=int(params["n_estimators"]), max_depth=params["max_depth"], min_samples_leaf=int(params["min_samples_leaf"]), max_features=params["max_features"], n_jobs=jobs, random_state=seed)
    elif method == "extra_trees":
        est = ExtraTreesClassifier(n_estimators=int(params["n_estimators"]), max_depth=params["max_depth"], min_samples_leaf=int(params["min_samples_leaf"]), max_features=params["max_features"], n_jobs=jobs, random_state=seed)
    else:
        est = HistGradientBoostingClassifier(max_iter=int(params["max_iter"]), learning_rate=float(params["learning_rate"]), max_leaf_nodes=int(params["max_leaf_nodes"]), min_samples_leaf=int(params["min_samples_leaf"]), l2_regularization=float(params["l2_regularization"]), random_state=seed)
    kind = "margin" if method in {"linear_svm", "rbf_svm"} else "probability"
    return ClassifierModel(est, kind)


def suggest_parameters(trial, method, n_fit, min_class):
    """Draw one adaptive-trial configuration from the frozen initial domains."""
    n_fit, min_class = int(n_fit), int(min_class)
    if n_fit < 1 or min_class < 0:
        raise ValueError("n_fit must be positive and min_class nonnegative")
    if method == "gaussian_nb":
        return {"var_smoothing": trial.suggest_float("var_smoothing", 1e-10, 1e-2, log=True)}
    if method == "shared_diagonal":
        return {"variance_floor": trial.suggest_float("variance_floor", 1e-8, 1e-2, log=True)}
    if method == "lda":
        return {"shrinkage": trial.suggest_categorical("shrinkage", ["auto", 0.01, 0.1, 0.5, 0.9])}
    if method == "qda":
        if min_class < 2:
            raise ValueError("unsupported: QDA requires at least two rows per class")
        return {"reg_param": trial.suggest_float("reg_param", 0.01, 0.99), "variance_floor": trial.suggest_float("variance_floor", 1e-8, 1e-2, log=True)}
    if method in {"logistic", "linear_svm"}:
        return {"C": trial.suggest_float("C", 1e-3, 1e3, log=True)}
    if method == "rbf_svm":
        return {"C": trial.suggest_float("C", 1e-2, 1e3, log=True), "gamma": trial.suggest_float("gamma", 1e-3, 1.0, log=True), "cache_size_mb": 512}
    if method == "knn":
        ks = [k for k in (3, 5, 15, 50, 100) if k <= n_fit]
        if not ks:
            raise ValueError("unsupported: fitting count is below smallest kNN neighbor count")
        return {"n_neighbors": trial.suggest_categorical("n_neighbors", ks), "weights": trial.suggest_categorical("weights", ["uniform", "distance"])}
    if method == "cart":
        leaves = [v for v in (1, 5, 20, 100) if v <= n_fit]
        return {"max_depth": trial.suggest_categorical("max_depth", [3, 6, 12, None]), "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", leaves)}
    if method in {"random_forest", "extra_trees"}:
        return {"n_estimators": trial.suggest_categorical("n_estimators", [200, 500]), "max_depth": trial.suggest_categorical("max_depth", [10, 20, None]), "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", [v for v in (1, 5, 20) if v <= n_fit]), "max_features": trial.suggest_categorical("max_features", ["sqrt", 1.0])}
    if method == "hist_gb":
        return {"max_iter": trial.suggest_categorical("max_iter", [100, 300]), "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.3, log=True), "max_leaf_nodes": trial.suggest_categorical("max_leaf_nodes", [15, 31, 63]), "min_samples_leaf": trial.suggest_categorical("min_samples_leaf", [v for v in (10, 20, 50) if v <= n_fit]), "l2_regularization": trial.suggest_float("l2_regularization", 0.0, 10.0)}
    raise ValueError(f"unsupported method: {method}")


def complexity_key(method, params):
    """Stable, lower-is-simpler tie-break key for configurations."""
    p = params
    if method == "gaussian_nb":
        return (-float(p["var_smoothing"]),)
    if method == "shared_diagonal":
        return (-float(p["variance_floor"]),)
    if method == "lda":
        return (0.0 if p["shrinkage"] == "auto" else -float(p["shrinkage"]),)
    if method == "qda":
        return (-float(p["reg_param"]), -float(p["variance_floor"]))
    if method in {"logistic", "linear_svm"}:
        return (float(p["C"]),)
    if method == "rbf_svm":
        return (float(p["C"]), float(p["gamma"]))
    if method == "knn":
        return (0 if p["weights"] == "uniform" else 1, -int(p["n_neighbors"]))
    if method == "cart":
        return (float("inf") if p["max_depth"] is None else int(p["max_depth"]), -int(p["min_samples_leaf"]))
    if method in {"random_forest", "extra_trees"}:
        return (int(p["n_estimators"]), float("inf") if p["max_depth"] is None else int(p["max_depth"]), -int(p["min_samples_leaf"]), 0 if p["max_features"] == "sqrt" else 1)
    if method == "hist_gb":
        return (int(p["max_iter"]), int(p["max_leaf_nodes"]), -int(p["min_samples_leaf"]), float(p["learning_rate"]), -float(p["l2_regularization"]))
    raise ValueError(f"unsupported method: {method}")
