"""Deterministic, nested real-data role allocation for the LAMOST experiments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class RoleSample:
    budget: int
    fit: np.ndarray
    tune: np.ndarray
    calibration: np.ndarray
    requested_budget: int
    status: str = "ok"


def _largest_remainder(counts: np.ndarray, total: int, minimum: int = 0) -> np.ndarray:
    """Proportional integer allocation, respecting feasible per-class minima."""
    counts = np.asarray(counts, dtype=np.int64)
    if total < 0 or total > counts.sum():
        raise ValueError("allocation total outside available support")
    out = np.zeros(len(counts), dtype=np.int64)
    active = counts > 0
    if minimum:
        out[active] = np.minimum(counts[active], minimum)
        if out.sum() > total:
            out[:] = 0
    remaining = total - int(out.sum())
    capacity = counts - out
    if remaining == 0:
        return out
    weights = capacity.astype(float)
    raw = remaining * weights / weights.sum()
    base = np.minimum(np.floor(raw).astype(np.int64), capacity)
    out += base
    remaining = total - int(out.sum())
    if remaining:
        fractional = raw - np.floor(raw)
        order = np.argsort(-fractional, kind="stable")
        for i in order:
            if remaining == 0:
                break
            if out[i] < counts[i]:
                out[i] += 1
                remaining -= 1
    if remaining:
        for i in np.flatnonzero(out < counts):
            take = min(remaining, int(counts[i] - out[i]))
            out[i] += take
            remaining -= take
            if not remaining:
                break
    return out


def sample_nested_roles(labels, budgets: Iterable[int], seed: int,
                        pool_indices=None) -> dict[int, RoleSample]:
    """Create nested 80/10/10 roles from a non-test pool.

    `pool_indices` are row positions in the caller's frame. The largest budget
    is capped by available rows and the returned entry records that cap. Each
    role has a saved class-wise permutation, so smaller budgets are prefixes.
    Calibration is sampled as a population-proportional random role; the
    one-per-class minimum is applied only to fit and tune when feasible.
    """
    y = np.asarray(labels, dtype=np.int64)
    ids = np.arange(len(y), dtype=np.int64) if pool_indices is None else np.asarray(pool_indices, dtype=np.int64)
    if ids.ndim != 1 or np.any(ids < 0) or np.any(ids >= len(y)):
        raise ValueError("pool_indices must be valid row positions")
    if len(np.unique(ids)) != len(ids):
        raise ValueError("pool_indices must not contain duplicates")
    requested = sorted({int(b) for b in budgets})
    if not requested or requested[0] < 1:
        raise ValueError("budgets must be positive")
    cap = min(requested[-1], len(ids))
    rng = np.random.default_rng(seed)
    # First carve three disjoint nested role pools at maximum requested size.
    nf, nt, nc = int(.8 * cap), int(.1 * cap), cap - int(.8 * cap) - int(.1 * cap)
    shuffled = ids[rng.permutation(len(ids))]
    # Calibration is a simple random population sample; no class quotas.
    cal_pool = shuffled[:nc]
    work_pool = shuffled[nc:]
    classes = np.unique(y[ids])
    # Build fit/tune role pools proportionally within classes, preserving
    # support for every class where feasible. Per-role ordered prefixes below
    # then make each budget nested.
    remaining_counts = np.array([np.sum(y[work_pool] == c) for c in classes], dtype=np.int64)
    fit_counts = _largest_remainder(remaining_counts, nf, 1 if nf >= len(classes) else 0)
    left_counts = remaining_counts - fit_counts
    tune_counts = _largest_remainder(left_counts, nt, 1 if nt >= len(classes) else 0)
    fit_pool, tune_pool = [], []
    for c, nfit, ntune in zip(classes, fit_counts, tune_counts):
        members = work_pool[y[work_pool] == c]
        members = members[rng.permutation(len(members))]
        fit_pool.extend(members[:nfit].tolist())
        tune_pool.extend(members[nfit:nfit + ntune].tolist())
    fit_pool = np.asarray(fit_pool, dtype=np.int64)
    tune_pool = np.asarray(tune_pool, dtype=np.int64)
    def class_permutations(role_ids):
        per = {}
        cs = np.unique(y[ids])
        for c in cs:
            members = role_ids[y[role_ids] == c]
            per[int(c)] = members[rng.permutation(len(members))]
        return per
    fit_perm, tune_perm, cal_perm = map(class_permutations, (fit_pool, tune_pool, cal_pool))

    def nested_order(perms, min_each=False):
        classes = sorted(perms)
        avail = np.array([len(perms[c]) for c in classes], dtype=np.int64)
        total = int(avail.sum())
        if total == 0: return np.empty(0, np.int64)
        class_ids = np.asarray(classes, dtype=np.int64)
        remaining = avail.copy()
        prefix = []
        if min_each and total >= len(classes):
            for j, c in enumerate(classes):
                if remaining[j]:
                    prefix.append(int(perms[c][0])); remaining[j] -= 1
        if not remaining.sum(): return np.asarray(prefix, dtype=np.int64)
        # Merge ideal proportional event times in NumPy instead of appending
        # one million rows in Python. Each class's kth event is k / p_c;
        # sorting these streams yields a deterministic, nested weighted weave.
        props = remaining / remaining.sum()
        event_times = np.concatenate([np.arange(1, int(n)+1, dtype=np.float64) / props[j]
                                      for j, n in enumerate(remaining) if n])
        event_classes = np.concatenate([np.full(int(n), j, dtype=np.int16)
                                        for j, n in enumerate(remaining) if n])
        event_ranks = np.concatenate([np.arange(int(n), dtype=np.int64)
                                      for n in remaining if n])
        sorted_order = np.argsort(event_times, kind="stable")
        codes = event_classes[sorted_order]
        ranks = event_ranks[sorted_order]
        output = np.empty(len(codes), dtype=np.int64)
        for j, c in enumerate(classes):
            mask = codes == j
            if mask.any(): output[mask] = perms[c][(avail[j] - remaining[j]) + ranks[mask]]
        return np.concatenate((np.asarray(prefix, dtype=np.int64), output))

    fit_order = nested_order(fit_perm, True)
    tune_order = nested_order(tune_perm, True)
    # Random ordering preserves population-proportional calibration roles.
    cal_order = cal_pool[rng.permutation(len(cal_pool))]

    result = {}
    for budget in requested:
        b = min(budget, cap)
        nfit, ntune, ncal = int(.8 * b), int(.1 * b), b - int(.8 * b) - int(.1 * b)
        # Per-role prefixes are nested, with natural class proportions.
        fit = fit_order[:nfit]
        tune = tune_order[:ntune]
        calibration = cal_order[:ncal]
        if len(np.unique(np.concatenate((fit, tune, calibration)))) != b:
            raise AssertionError("role allocation is not disjoint")
        status = "ok" if b == budget else f"capped_to_available_{b}"
        result[budget] = RoleSample(b, fit, tune, calibration, budget, status)
    return result


def role_manifest(sample: RoleSample, labels, ids=None) -> dict:
    """Compact JSON-ready role counts and membership digests."""
    import hashlib
    y = np.asarray(labels, dtype=np.int64)
    ids = np.arange(len(y), dtype=np.int64) if ids is None else np.asarray(ids)
    out = {"budget": sample.budget, "requested_budget": sample.requested_budget,
           "status": sample.status, "roles": {}}
    for role in ("fit", "tune", "calibration"):
        rows = getattr(sample, role)
        vals = np.asarray(ids[rows]).astype("U")
        digest = hashlib.sha256("\n".join(vals.tolist()).encode()).hexdigest()
        out["roles"][role] = {"n": int(len(rows)), "counts": np.bincount(y[rows], minlength=7).tolist(), "ids_sha256": digest}
    return out
