"""Probability-averaging ensembles with protocol-bounded weight search."""
from __future__ import annotations

import numpy as np
import argparse
import json
from pathlib import Path

MEMBERS = ("gmm", "copula", "arf", "kde", "chow_liu")
N_CLASSES = 7


def _matrix(scores, name):
    x = np.asarray(scores, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != N_CLASSES or not np.isfinite(x).all() or np.any(x < 0):
        raise ValueError(f"{name} must be a finite nonnegative N x 7 posterior matrix")
    if not np.allclose(x.sum(axis=1), 1.0, atol=1e-6):
        raise ValueError(f"{name} rows must sum to one")
    return x


def _member_stack(score_matrices, member_names=None):
    if isinstance(score_matrices, dict):
        names = tuple(MEMBERS if member_names is None else member_names)
        if set(score_matrices) != set(names):
            raise ValueError(f"all five required members are required: {names}")
        stack = np.stack([_matrix(score_matrices[name], name) for name in names])
    else:
        stack = np.asarray(score_matrices, dtype=np.float64)
        if stack.ndim != 3 or stack.shape[0] != 5 or stack.shape[2] != N_CLASSES:
            raise ValueError("score_matrices must have shape (5,N,7)")
        names = tuple(MEMBERS if member_names is None else member_names)
        if len(names) != 5:
            raise ValueError("exactly five member names are required")
        stack = np.stack([_matrix(x, name) for x, name in zip(stack, names)])
    if len({x.shape for x in stack}) != 1:
        raise ValueError("all member posterior matrices must have identical shapes")
    if len(names) != 5 or set(names) != set(MEMBERS):
        raise ValueError(f"member names must be the five required flexible families: {MEMBERS}")
    return names, stack


def equal_weight_posteriors(score_matrices, member_names=None) -> np.ndarray:
    """Average the five members' posterior vectors using fixed weight 0.2."""
    _, stack = _member_stack(score_matrices, member_names)
    return stack.mean(axis=0)


def ensemble_scores(score_matrices, weights, member_names=None) -> np.ndarray:
    """Return a weighted posterior average; raw class densities are not mixed."""
    _, stack = _member_stack(score_matrices, member_names)
    w = np.asarray(weights, dtype=np.float64)
    if w.shape != (5,) or not np.isfinite(w).all() or np.any(w < 0) or not np.isclose(w.sum(), 1.0, atol=1e-10):
        raise ValueError("weights must be a nonnegative five-vector summing to one")
    return np.einsum("m,mnc->nc", w, stack, optimize=True)


def _balanced_accuracy(y, pred):
    return float(np.mean([np.mean(pred[y == c] == c) for c in range(7)]))


def fit_ensemble_weights(tuning_scores_by_member, y_tuning, seed=0,
                         dirichlet_candidates=1000, candidate_cap=2000) -> dict:
    """Select one global simplex weight vector by tuning balanced accuracy.

    Candidate order is equal weights, five vertices, seeded Dirichlet draws,
    then neighborhood transfers around the current ten best candidates.
    Exact score ties prefer Euclidean proximity to equal weights and then the
    earlier candidate. No stacking, calibration labels or class-specific gates
    are used.
    """
    names, stack = _member_stack(tuning_scores_by_member)
    y = np.asarray(y_tuning)
    if y.ndim != 1 or len(y) != stack.shape[1] or not np.issubdtype(y.dtype, np.integer) or np.any((y < 0) | (y >= 7)):
        raise ValueError("y_tuning must be an integer N-vector matching the posterior rows")
    if np.any(np.bincount(y, minlength=7) == 0):
        raise ValueError("tuning balanced accuracy requires all seven classes")
    if int(candidate_cap) < 6 or int(dirichlet_candidates) < 0:
        raise ValueError("candidate limits are invalid")
    cap = min(2000, int(candidate_cap))
    equal = np.full(5, 0.2, dtype=np.float64)
    candidates = [equal]
    candidates.extend(np.eye(5, dtype=np.float64))
    rng = np.random.default_rng(seed)
    n_random = min(int(dirichlet_candidates), max(0, cap - len(candidates)))
    candidates.extend(rng.dirichlet(np.ones(5), size=n_random))

    def scores_for(weights):
        # Score candidates in batches to bound memory for a 10k-row tuning set.
        w = np.asarray(weights)
        result = np.empty(len(w), dtype=np.float64)
        row_masks = [y == c for c in range(7)]
        for start in range(0, len(w), 32):
            stop = min(start + 32, len(w))
            posterior = np.einsum("bm,mnc->bnc", w[start:stop], stack, optimize=True)
            pred = posterior.argmax(axis=2)
            result[start:stop] = np.stack([np.mean(pred[:, mask] == c, axis=1)
                                            for c, mask in enumerate(row_masks)]).mean(axis=0)
        return result

    # Add refinements in deterministic order, stopping at the frozen candidate cap.
    base_scores = scores_for(candidates)
    order = sorted(range(len(candidates)), key=lambda i: (-base_scores[i], np.linalg.norm(candidates[i] - equal), i))
    for base_index in order[:10]:
        base = candidates[base_index]
        for step in (0.10, 0.05, 0.01):
            for donor in range(5):
                for receiver in range(5):
                    if donor == receiver:
                        continue
                    amount = min(step, base[donor])
                    if amount <= 0:
                        continue
                    weight = base.copy()
                    weight[donor] -= amount
                    weight[receiver] += amount
                    if len(candidates) >= cap:
                        break
                    candidates.append(weight)
                if len(candidates) >= cap:
                    break
            if len(candidates) >= cap:
                break
        if len(candidates) >= cap:
            break
    scores = scores_for(candidates)
    best = min(range(len(candidates)), key=lambda i: (-scores[i], np.linalg.norm(candidates[i] - equal), i))
    rows = [{"candidate": i, "weights": np.asarray(w).tolist(), "balanced_accuracy": float(scores[i])}
            for i, w in enumerate(candidates)]
    return {"weights": np.asarray(candidates[best]).tolist(), "tuning_balanced_accuracy": float(scores[best]),
            "selected_candidate": int(best), "candidate_count": len(candidates), "candidate_cap": cap,
            "member_order": list(names), "search": "equal + five vertices + seeded Dirichlet + top-ten bounded pairwise transfers",
            "seed": int(seed), "candidates": rows,
            "selection_limit": "bounded search for a discontinuous tuning objective; not globally optimal"}


def run_e6(results_dir="benchmark/results", baseline_dir="lamost_baseline",
           repetitions=3, seed=271828) -> dict:
    """Run E6 from matching cached E1 member fits; never trains base models.

    Tuning and calibration posteriors are computed from cached member models;
    test posteriors are loaded from their saved E1 predictions. Every required
    member must be present and have matching role and test memberships.
    """
    import joblib
    from benchmark.engine import load_data, validate_manifest, atomic_json
    from benchmark.evaluation import balanced_accuracy, conformal_threshold, conformal_evaluate, bootstrap_outcomes
    from benchmark.fidelity import FEATURES

    if int(repetitions) != 3:
        raise ValueError("Experiment 6 is specified for three paired repetitions")
    root = Path(results_dir)
    out_root = root / "e6"
    out_root.mkdir(parents=True, exist_ok=True)
    validate_manifest(baseline_dir)
    frame, _ = load_data(baseline_dir)
    by_id = frame.set_index("sample_id", drop=False)
    summary = {"experiment": 6, "budget": 100_000, "repetition_count": 3,
               "members": list(MEMBERS), "status": "complete_with_unavailable_repetitions",
               "runs": [],
               "protocol": "posterior averaging; global nonnegative simplex weights; no stacking or class-specific weights"}
    bootstrap_outcomes_across_runs = {}
    bootstrap_y = None
    for rep in range(1, 4):
        cell_out = out_root / f"rep_{rep}"
        cell_out.mkdir(parents=True, exist_ok=True)
        cells = {name: root / f"e1/rep_{rep}/n_100000/{name}" for name in MEMBERS}
        missing = [name for name, cell in cells.items()
                   if not all((cell / p).exists() for p in ("complete.json", "pipeline.joblib", "role_membership.npz", "test_predictions.npz"))]
        if missing:
            status = {"repetition": rep, "status": "unavailable", "reason": "required full five-member E1 cache is missing", "missing_members": missing}
            atomic_json(cell_out / "status.json", status)
            summary["runs"].append(status)
            continue
        pipelines = {}
        tune_score = {}
        cal_score = {}
        test_score = {}
        member_test_ids = {}
        role_ids = {}
        for name, cell in cells.items():
            done = json.loads((cell / "complete.json").read_text())
            if done.get("status") != "complete":
                missing.append(name); continue
            pipelines[name] = joblib.load(cell / "pipeline.joblib")
            with np.load(cell / "role_membership.npz", allow_pickle=False) as roles:
                role_ids[name] = {key: roles[key].copy() for key in ("tuning_ids", "calibration_ids")}
            with np.load(cell / "test_predictions.npz", allow_pickle=False) as pred:
                member_test_ids[name] = pred["sample_id"].copy()
                test_score[name] = _matrix(pred["scores"], f"{name} test scores")
        if missing:
            status = {"repetition": rep, "status": "unavailable", "reason": "one or more E1 member cells are incomplete", "missing_members": sorted(set(missing))}
            atomic_json(cell_out / "status.json", status)
            summary["runs"].append(status)
            continue
        ref_tune = role_ids[MEMBERS[0]]["tuning_ids"]
        ref_cal = role_ids[MEMBERS[0]]["calibration_ids"]
        for name in MEMBERS[1:]:
            if not np.array_equal(role_ids[name]["tuning_ids"], ref_tune) or not np.array_equal(role_ids[name]["calibration_ids"], ref_cal):
                raise ValueError(f"E1 role memberships differ for ensemble members in repetition {rep}")
            if not np.array_equal(member_test_ids[name], member_test_ids[MEMBERS[0]]):
                raise ValueError(f"E1 test memberships differ for ensemble members in repetition {rep}")
        tune = by_id.loc[ref_tune]
        cal = by_id.loc[ref_cal]
        y_tune = tune["label_id"].to_numpy(dtype=np.int64)
        y_cal = cal["label_id"].to_numpy(dtype=np.int64)
        for name in MEMBERS:
            pipeline = pipelines[name]
            Xtune_raw = tune[list(FEATURES)].to_numpy(dtype=np.float64)
            Xcal_raw = cal[list(FEATURES)].to_numpy(dtype=np.float64)
            Xtune = pipeline["scaler"].transform(pipeline["imputer"].transform(Xtune_raw))
            Xcal = pipeline["scaler"].transform(pipeline["imputer"].transform(Xcal_raw))
            model = pipeline["model"]
            kind = getattr(model, "score_kind", "probability")
            if kind != "probability":
                raise ValueError(f"E6 member {name} lacks native posterior probabilities")
            tune_score[name] = _matrix(model.score_matrix(Xtune), f"{name} tuning scores")
            cal_score[name] = _matrix(model.score_matrix(Xcal), f"{name} calibration scores")
        member_tuning_ba = {name: balanced_accuracy(y_tune, tune_score[name].argmax(axis=1)) for name in MEMBERS}
        weights = fit_ensemble_weights(tune_score, y_tune, seed=seed + rep)
        equal_w = np.full(5, 0.2)
        cal_ensemble = {
            "equal": ensemble_scores(cal_score, equal_w),
            "learned": ensemble_scores(cal_score, weights["weights"]),
        }
        test_ensemble = {
            "equal": ensemble_scores(test_score, equal_w),
            "learned": ensemble_scores(test_score, weights["weights"]),
        }
        test_ids = member_test_ids[MEMBERS[0]]
        y_test = by_id.loc[test_ids, "label_id"].to_numpy(dtype=np.int64)
        outcomes = {}
        result_json = {}
        for name in MEMBERS:
            q = conformal_threshold(cal_score[name], y_cal, score_kind="probability", alpha=.1)
            outcome = conformal_evaluate(test_score[name], y_test, q, score_kind="probability")
            outcomes[name] = outcome
            result_json[name] = {k: outcome[k] for k in ("balanced_accuracy", "set_size", "coverage", "per_class")}
            result_json[name]["conformal_threshold"] = q
        for mode in ("equal", "learned"):
            q = conformal_threshold(cal_ensemble[mode], y_cal, score_kind="probability", alpha=.1)
            outcome = conformal_evaluate(test_ensemble[mode], y_test, q, score_kind="probability")
            outcomes[f"ensemble_{mode}"] = outcome
            result_json[f"ensemble_{mode}"] = {k: outcome[k] for k in ("balanced_accuracy", "set_size", "coverage", "per_class")}
            result_json[f"ensemble_{mode}"]["conformal_threshold"] = q
            result_json[f"ensemble_{mode}"]["weights"] = equal_w.tolist() if mode == "equal" else weights["weights"]
        best_member = min(MEMBERS, key=lambda name: (-member_tuning_ba[name], MEMBERS.index(name)))
        if bootstrap_y is None:
            bootstrap_y = y_test.copy()
        elif not np.array_equal(bootstrap_y, y_test):
            raise ValueError("test labels/order changed across E6 repetitions")
        for method_name, outcome in outcomes.items():
            bootstrap_outcomes_across_runs[f"rep_{rep}:{method_name}"] = outcome
        npz_fields = {"sample_id": test_ids}
        for name, outcome in outcomes.items():
            npz_fields[f"{name}_predictions"] = outcome["predictions"].astype(np.int16)
            npz_fields[f"{name}_sets"] = outcome["sets"].astype(np.uint8)
            npz_fields[f"{name}_covered"] = outcome["covered"].astype(np.uint8)
            npz_fields[f"{name}_set_sizes"] = outcome["set_sizes"].astype(np.uint8)
        np.savez_compressed(cell_out / "test_outcomes.npz", **npz_fields)
        atomic_json(cell_out / "weights.json", {"weight_search": weights, "member_tuning_balanced_accuracy": member_tuning_ba,
                    "best_individual_by_tuning": best_member,
                    "note": "best member is one of the five individual-member comparisons"})
        run = {"repetition": rep, "status": "complete", "member_order": list(MEMBERS),
               "best_individual_by_tuning": best_member, "member_tuning_balanced_accuracy": member_tuning_ba,
               "outcomes": result_json, "paired_bootstrap": "shared across all E6 repetitions; see e6/paired_bootstrap.json",
               "uncertainty_scope": "95% intervals condition on fitted E1 pipelines, fixed calibration thresholds and saved test objects"}
        atomic_json(cell_out / "results.json", run)
        summary["runs"].append({"repetition": rep, "status": "complete", "best_individual_by_tuning": best_member,
                                       "outcomes": result_json})
    if bootstrap_outcomes_across_runs and bootstrap_y is not None:
        paired_bootstrap = bootstrap_outcomes(bootstrap_y, bootstrap_outcomes_across_runs,
                                               n_boot=1000, seed=seed, confidence=.95)
        atomic_json(out_root / "paired_bootstrap.json", paired_bootstrap)
    summary["status"] = "complete" if len(summary["runs"]) == 3 and all(x["status"] == "complete" for x in summary["runs"]) else "complete_with_unavailable_repetitions"
    atomic_json(out_root / "summary.json", summary)
    return summary


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Run Experiment 6 ensemble analysis from cached E1 fits.")
    parser.add_argument("--results", type=Path, default=Path("benchmark/results"))
    parser.add_argument("--baseline", type=Path, default=Path("lamost_baseline"))
    parser.add_argument("--seed", type=int, default=271828)
    args = parser.parse_args(argv)
    run_e6(args.results, args.baseline, repetitions=3, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
