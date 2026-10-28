"""Protocol-defined classification and split-conformal evaluation helpers."""
from __future__ import annotations

import math
from typing import Mapping

import numpy as np

N_CLASSES = 7
CLASS_IDS = np.arange(N_CLASSES)


def _labels(y, name="y"):
    a = np.asarray(y)
    if a.ndim != 1 or not np.issubdtype(a.dtype, np.integer):
        raise ValueError(f"{name} must be a one-dimensional integer label array")
    if np.any((a < 0) | (a >= N_CLASSES)):
        raise ValueError(f"{name} labels must be in 0..6")
    return a.astype(np.int64, copy=False)


def balanced_accuracy(y_true, y_pred) -> float:
    """Mean of the seven class recalls; missing true classes are an error."""
    y = _labels(y_true, "y_true")
    p = _labels(y_pred, "y_pred")
    if y.shape != p.shape or not len(y):
        raise ValueError("y_true and y_pred must have the same nonzero length")
    counts = np.bincount(y, minlength=N_CLASSES)
    if np.any(counts == 0):
        raise ValueError("balanced accuracy requires at least one true row in every class")
    recalls = np.array([np.mean(p[y == c] == c) for c in CLASS_IDS], dtype=float)
    return float(recalls.mean())


def _scores(scores, score_kind):
    a = np.asarray(scores, dtype=np.float64)
    if a.ndim != 2 or a.shape[1] != N_CLASSES or not np.isfinite(a).all():
        raise ValueError("scores must be a finite N x 7 matrix")
    if score_kind not in {"probability", "margin"}:
        raise ValueError("score_kind must be 'probability' or 'margin'")
    if score_kind == "probability" and (np.any(a < 0) or not np.allclose(a.sum(axis=1), 1, atol=1e-6)):
        raise ValueError("probability rows must be nonnegative and sum to one")
    return a


def _nonconformity(scores, score_kind):
    return 1.0 - scores if score_kind == "probability" else -scores


def _patterns(matrix):
    """Exact row-pattern frequency table with a compact byte-key sort."""
    a = np.ascontiguousarray(matrix)
    key_dtype = np.dtype((np.void, a.dtype.itemsize * a.shape[1]))
    _, first, counts = np.unique(a.view(key_dtype).reshape(-1), return_index=True,
                                 return_counts=True)
    return a[first], counts


def conformal_threshold(scores_cal, y_cal, score_kind="probability", alpha=0.1) -> float:
    """Return the finite-sample split-conformal order statistic."""
    s = _scores(scores_cal, score_kind)
    y = _labels(y_cal, "y_cal")
    if len(y) != len(s) or not len(y):
        raise ValueError("calibration labels must match a nonempty score matrix")
    if not (0 < alpha < 1):
        raise ValueError("alpha must be between zero and one")
    cal = _nonconformity(s, score_kind)[np.arange(len(y)), y]
    k = int(math.ceil((len(y) + 1) * (1 - float(alpha))))
    return float(np.inf if k > len(y) else np.partition(cal, k - 1)[k - 1])


def conformal_evaluate(scores_test, y_test, threshold, score_kind="probability") -> dict:
    """Evaluate argmax predictions and unforced conformal label sets."""
    s = _scores(scores_test, score_kind)
    y = _labels(y_test, "y_test")
    if len(y) != len(s) or not len(y):
        raise ValueError("test labels must match a nonempty score matrix")
    if np.isnan(threshold):
        raise ValueError("threshold cannot be NaN")
    pred = np.argmax(s, axis=1).astype(np.int8)
    sets = _nonconformity(s, score_kind) <= float(threshold)
    sizes = sets.sum(axis=1).astype(np.int64)
    covered = sets[np.arange(len(y)), y]
    per_class = {}
    for c in CLASS_IDS:
        mask = y == c
        per_class[int(c)] = {
            "n": int(mask.sum()),
            "recall": float(np.mean(pred[mask] == c)) if mask.any() else None,
            "coverage": float(np.mean(covered[mask])) if mask.any() else None,
            "set_size": float(np.mean(sizes[mask])) if mask.any() else None,
        }
    return {
        "balanced_accuracy": balanced_accuracy(y, pred),
        "set_size": float(sizes.mean()),
        "coverage": float(covered.mean()),
        "per_class": per_class,
        "predictions": pred,
        "sets": sets,
        "covered": covered.astype(bool),
        "set_sizes": sizes,
    }


def bootstrap_outcomes(y_true, outcomes_by_method: Mapping[str, Mapping], n_boot=1000,
                      seed=0, confidence=0.95) -> dict:
    """Paired, no-retraining percentile intervals from saved per-row outcomes.

    Balanced accuracy uses class-stratified object resampling. Coverage and set
    size use population row resampling. Every method receives the same indices
    for a given metric and replicate. Intervals condition on fitted pipelines
    and fixed conformal thresholds.
    """
    y = _labels(y_true, "y_true")
    if not len(y) or np.any(np.bincount(y, minlength=N_CLASSES) == 0):
        raise ValueError("bootstrap requires nonempty test rows from all seven classes")
    if int(n_boot) < 1 or not 0 < confidence < 1:
        raise ValueError("n_boot and confidence are out of range")
    names = list(outcomes_by_method)
    if not names:
        raise ValueError("at least one method is required")
    parsed = {}
    for name, outcome in outcomes_by_method.items():
        pred_input = np.asarray(outcome["predictions"])
        _labels(pred_input, f"{name}.predictions")  # validate while keeping the compact saved dtype
        pred = pred_input.astype(np.int8, copy=False)
        covered = np.asarray(outcome["covered"], dtype=bool)
        sizes_raw = np.asarray(outcome["set_sizes"])
        sizes = sizes_raw.astype(np.uint8, copy=False)
        if pred.shape != y.shape or covered.shape != y.shape or sizes.shape != y.shape:
            raise ValueError(f"saved row outcomes for {name} must match y_true")
        if (not np.issubdtype(sizes_raw.dtype, np.integer) and
                (not np.isfinite(sizes_raw).all() or not np.all(sizes_raw == np.floor(sizes_raw)))):
            raise ValueError(f"invalid set sizes for {name}")
        if np.any(sizes_raw < 0) or np.any(sizes_raw > N_CLASSES):
            raise ValueError(f"invalid set sizes for {name}")
        parsed[name] = (pred, covered, sizes)
    rng = np.random.default_rng(seed)
    groups = [np.flatnonzero(y == c) for c in CLASS_IDS]
    alpha = (1 - confidence) / 2
    point = {}
    boot = {metric: {name: np.empty(int(n_boot)) for name in names}
            for metric in ("balanced_accuracy", "coverage", "set_size")}
    for name, (pred, covered, sizes) in parsed.items():
        point[name] = {
            "balanced_accuracy": balanced_accuracy(y, pred),
            "coverage": float(covered.mean()),
            "set_size": float(sizes.mean()),
        }
    # Collapse rows with identical saved outcome vectors. A multinomial draw
    # over these exact outcome-pattern counts is algebraically equivalent to
    # resampling the original rows, while avoiding repeated 500k-index arrays.
    correct = np.column_stack([parsed[name][0] == y for name in names]).astype(np.uint8)
    covered_matrix = np.column_stack([parsed[name][1] for name in names]).astype(np.uint8)
    sizes_matrix = np.column_stack([parsed[name][2] for name in names]).astype(np.uint8, copy=False)
    class_recall_draws = np.zeros((int(n_boot), len(names), N_CLASSES), dtype=np.float64)
    for c, group in enumerate(groups):
        patterns, counts = _patterns(correct[group])
        probabilities = counts / counts.sum()
        for b in range(int(n_boot)):
            multiplicities = rng.multinomial(len(group), probabilities)
            class_recall_draws[b, :, c] = (multiplicities @ patterns) / len(group)
    for j, name in enumerate(names):
        boot["balanced_accuracy"][name][:] = class_recall_draws[:, j, :].mean(axis=1)

    for metric, matrix in (("coverage", covered_matrix), ("set_size", sizes_matrix)):
        patterns, counts = _patterns(matrix)
        probabilities = counts / counts.sum()
        for b in range(int(n_boot)):
            multiplicities = rng.multinomial(len(y), probabilities)
            means = (multiplicities @ patterns) / len(y)
            for j, name in enumerate(names):
                boot[metric][name][b] = means[j]
    intervals = {metric: {name: [float(np.quantile(v, alpha)), float(np.quantile(v, 1 - alpha))]
                          for name, v in by_name.items()} for metric, by_name in boot.items()}
    # Paired differences preserve the same bootstrap object indices.
    differences = {metric: {} for metric in boot}
    for metric, by_name in boot.items():
        for i, left in enumerate(names):
            for right in names[i + 1:]:
                delta = by_name[left] - by_name[right]
                differences[metric][f"{left} - {right}"] = {
                    "estimate": float(point[left][metric] - point[right][metric]),
                    "ci": [float(np.quantile(delta, alpha)), float(np.quantile(delta, 1 - alpha))],
                }
    return {"confidence": float(confidence), "n_boot": int(n_boot), "n_test": int(len(y)),
            "conditional_on_fitted_pipelines": True, "point_estimates": point,
            "row_resampling": "exact outcome-pattern multinomial compression; identical object-row resamples for all methods are preserved for these saved metrics",
            "intervals": intervals, "paired_differences": differences}
