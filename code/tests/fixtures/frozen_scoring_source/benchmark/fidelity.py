"""Class-balanced SDMetrics diagnostics and descriptive fidelity associations."""
from __future__ import annotations

import importlib.metadata
import argparse
import json
from pathlib import Path
import numpy as np

N_CLASSES = 7
N_FEATURES = 6
PRIMARY_FAMILIES = ("gmm", "copula", "arf", "kde", "chow_liu")
CLASSICAL_FAMILIES = ("gaussian_nb", "shared_diagonal", "lda", "qda")
E2_BUDGETS = (3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000)
FEATURES = ("mag_ps_g", "mag_ps_r", "mag_ps_i", "mag_ps_z", "mag_ps_y", "gaia_g_mean_mag")


def _version():
    try:
        return importlib.metadata.version("sdmetrics")
    except importlib.metadata.PackageNotFoundError:
        return None


def _quality_components(real, synthetic):
    """Run the official QualityReport API, returning property/pair evidence."""
    try:
        import pandas as pd
        from sdmetrics.reports.single_table import QualityReport
    except ImportError as exc:
        raise RuntimeError("SDMetrics is unavailable; install the pinned benchmark dependency") from exc
    names = [f"feature_{i}" for i in range(N_FEATURES)]
    real_df, synth_df = pd.DataFrame(real, columns=names), pd.DataFrame(synthetic, columns=names)
    metadata = {"columns": {name: {"sdtype": "numerical"} for name in names}}
    report = QualityReport()
    report.generate(real_df, synth_df, metadata, verbose=False)
    properties = report.get_properties()
    prop_score = {}
    if "Score" in properties.columns:
        for _, row in properties.iterrows():
            value = float(row["Score"])
            if not np.isfinite(value):
                raise ValueError(f"SDMetrics property {row['Property']} has an undefined score")
            prop_score[str(row["Property"])] = value
    if set(prop_score) != {"Column Shapes", "Column Pair Trends"}:
        raise ValueError("SDMetrics did not return both required property scores")
    details = {}
    for prop in ("Column Shapes", "Column Pair Trends"):
        try:
            rows = report.get_details(prop)
            details[prop] = rows.to_dict(orient="records")
        except Exception:
            details[prop] = []
    return float(report.get_score()), prop_score, details


def class_fidelity_report(model, X_reference, y_reference, seed=0, max_rows=2000,
                          keep_samples=False) -> dict:
    """Measure all seven class-conditional samples against held-out real rows.

    Uses only the six numerical predictors. Class aggregation is an equal
    arithmetic mean and is unavailable if any class report is invalid.
    """
    X = np.asarray(X_reference, dtype=np.float64)
    y = np.asarray(y_reference)
    if X.ndim != 2 or X.shape[1] != N_FEATURES or y.shape != (len(X),):
        raise ValueError("expected X_reference (N,6) and matching y_reference")
    if not np.isfinite(X).all() or not np.issubdtype(y.dtype, np.integer) or np.any((y < 0) | (y >= N_CLASSES)):
        raise ValueError("fidelity inputs must be finite with integer labels 0..6")
    if int(max_rows) < 1:
        raise ValueError("max_rows must be positive")
    version = _version()
    result = {"status": "ok", "score": None, "n_classes": N_CLASSES, "sdmetrics_version": version,
              "aggregation": "equal arithmetic mean of all seven class QualityReport scores",
              "feature_columns": [f"feature_{i}" for i in range(N_FEATURES)], "per_class": {}}
    if keep_samples:
        result["diagnostic_samples"] = {"real_by_class": {}, "synthetic_by_class": {}}
    rng = np.random.default_rng(seed)
    if version is None:
        result.update(status="unavailable", reason="SDMetrics is not installed")
        for c in range(N_CLASSES):
            count = int(np.sum(y == c))
            n = min(int(max_rows), count)
            result["per_class"][c] = {"status": "unavailable", "n_reference_available": count,
                                      "n": n, "low_precision": bool(n < 20)}
        return result
    scores = []
    for c in range(N_CLASSES):
        indices = np.flatnonzero(y == c)
        n = min(int(max_rows), len(indices))
        item = {"status": "unavailable", "n_reference_available": int(len(indices)), "n": int(n),
                "low_precision": bool(n < 20), "score": None, "property_scores": {}, "evaluated_pairs": []}
        if n < 2:
            item["reason"] = "fewer than two held-out real rows"
            result["per_class"][c] = item
            continue
        chosen = rng.choice(indices, size=n, replace=False)
        real = X[chosen]
        try:
            synth = np.asarray(model.sample_class(c, n, seed=int(seed) + c + 1), dtype=np.float64)
            if synth.shape != (n, N_FEATURES) or not np.isfinite(synth).all():
                raise ValueError("generator returned invalid sample shape or values")
            if keep_samples:
                result["diagnostic_samples"]["real_by_class"][c] = real.copy()
                result["diagnostic_samples"]["synthetic_by_class"][c] = synth.copy()
            total, props, details = _quality_components(real, synth)
            if not np.isfinite(total):
                raise ValueError("SDMetrics returned a non-finite score")
            item.update(status="ok", score=float(total), property_scores=props,
                        evaluated_pairs=details.get("Column Pair Trends", []),
                        property_details=details)
            scores.append(float(total))
        except Exception as exc:
            item["reason"] = f"{type(exc).__name__}: {exc}"
        result["per_class"][c] = item
    if len(scores) == N_CLASSES and all(result["per_class"][c]["status"] == "ok" for c in range(N_CLASSES)):
        result["score"] = float(np.mean(scores))
    else:
        result["status"] = "unavailable"
        result["reason"] = "at least one required class score is unavailable; no zero imputation or six-class averaging"
    return result


def spearman_by_budget_repetition(records, primary_families=PRIMARY_FAMILIES,
                                  classical_families=CLASSICAL_FAMILIES) -> list[dict]:
    """Separate descriptive Spearman associations at each budget/repetition.

    `records` contain family, budget, repetition, fidelity and balanced_accuracy.
    The five (or four sensitivity) method families are a fixed, small set; these
    coefficients are not treated as draws from a population of algorithms.
    """
    from scipy.stats import spearmanr
    groups = {}
    for row in records:
        key = (row["budget"], row["repetition"])
        groups.setdefault(key, []).append(row)
    results = []
    for (budget, repetition), rows in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1])):
        for label, members in (("primary_five", primary_families), ("classical_sensitivity", classical_families)):
            selected = [r for r in rows if r.get("family") in members and
                        r.get("fidelity") is not None and r.get("balanced_accuracy") is not None and
                        np.isfinite(r["fidelity"]) and np.isfinite(r["balanced_accuracy"])]
            rho = p = None
            if len(selected) >= 2:
                fx = [r["fidelity"] for r in selected]
                ay = [r["balanced_accuracy"] for r in selected]
                if len(set(fx)) > 1 and len(set(ay)) > 1:
                    stat = spearmanr(fx, ay)
                    rho, p = (float(stat.statistic), float(stat.pvalue))
                    if not np.isfinite(rho):
                        rho, p = None, None
            results.append({"budget": budget, "repetition": repetition, "analysis": label,
                            "families": [r.get("family") for r in selected], "n_valid": len(selected),
                            "spearman_rho": rho, "p_value_descriptive_only": p,
                            "status": "ok" if rho is not None else "undefined (insufficient data or ties)",
                            "interpretation_limit": "descriptive fixed-family comparison; not independent algorithm-family evidence"})
    return results


def bootstrap_fidelity_scores(real_by_class, synthetic_by_method, n_boot=1000,
                              seed=0, confidence=0.95) -> dict:
    """Bootstrap saved fidelity samples without refitting any generator.

    `real_by_class` maps class ids to the held-out reference rows used for the
    reports. `synthetic_by_method` maps method names to a class-id mapping of
    saved generated rows. Each replicate resamples real rows once per class and
    shares those indices across methods; generated rows are resampled separately
    per method. An interval is conditional on the saved fitted models and the
    diagnostic samples. This does not make the small family set independent.
    """
    if int(n_boot) < 1 or not 0 < confidence < 1:
        raise ValueError("n_boot and confidence are out of range")
    if set(real_by_class) != set(range(N_CLASSES)) or not synthetic_by_method:
        raise ValueError("real and synthetic diagnostic samples must cover classes 0..6")
    real = {}
    for c in range(N_CLASSES):
        a = np.asarray(real_by_class[c], dtype=np.float64)
        if a.ndim != 2 or a.shape[1] != N_FEATURES or not np.isfinite(a).all() or len(a) < 2:
            raise ValueError(f"invalid saved real diagnostics for class {c}")
        real[c] = a
    synth = {}
    for method, by_class in synthetic_by_method.items():
        if set(by_class) != set(range(N_CLASSES)):
            raise ValueError(f"{method} synthetic samples must cover classes 0..6")
        synth[method] = {}
        for c in range(N_CLASSES):
            a = np.asarray(by_class[c], dtype=np.float64)
            if a.ndim != 2 or a.shape[1] != N_FEATURES or not np.isfinite(a).all() or len(a) < 2:
                raise ValueError(f"invalid {method} synthetic diagnostics for class {c}")
            if len(a) != len(real[c]):
                raise ValueError(f"{method} class {c} synthetic count must match the shared real diagnostic count")
            synth[method][c] = a
    names = list(synth)
    rng = np.random.default_rng(seed)
    draws = {name: np.full(int(n_boot), np.nan) for name in names}
    for b in range(int(n_boot)):
        # Share each real resample across methods; synthetic rows remain independently sampled.
        sampled_real = {c: x[rng.integers(0, len(x), size=len(x))] for c, x in real.items()}
        for name in names:
            class_scores = []
            for c in range(N_CLASSES):
                x = synth[name][c]
                sampled_synth = x[rng.integers(0, len(x), size=len(x))]
                try:
                    score, _, _ = _quality_components(sampled_real[c], sampled_synth)
                    if not np.isfinite(score):
                        raise ValueError("non-finite SDMetrics score")
                    class_scores.append(float(score))
                except Exception:
                    class_scores = []
                    break
            if len(class_scores) == N_CLASSES:
                draws[name][b] = float(np.mean(class_scores))
    tail = (1 - confidence) / 2
    summary = {}
    for name, values in draws.items():
        valid = values[np.isfinite(values)]
        summary[name] = {"valid_replicates": int(len(valid)), "n_boot": int(n_boot),
                         "ci": ([float(np.quantile(valid, tail)), float(np.quantile(valid, 1 - tail))]
                                if len(valid) else None)}
    return {"confidence": float(confidence), "seed": int(seed), "n_boot": int(n_boot),
            "conditional_on_fitted_models_and_saved_diagnostic_samples": True,
            "real_resampling_shared_across_methods": True,
            "synthetic_resampling_independent_by_method": True,
            "family_independence_claim": False, "intervals": summary,
            "bootstrap_scores": {k: v.tolist() for k, v in draws.items()}}


def run_e2(results_dir="benchmark/results", baseline_dir="lamost_baseline",
           repetitions=5, budgets=E2_BUDGETS, methods=None) -> dict:
    """Run fidelity analysis from cached E1 fits only; never trains a model.

    It writes E2 reports and saved diagnostic samples below `results_dir/e2`.
    Missing/incomplete E1 artifacts are reported as unavailable. QualityReport
    bootstrap intervals are explicitly staged for runtime profiling, not
    approximated or silently omitted.
    """
    import joblib
    from benchmark.engine import load_data, validate_manifest, atomic_json
    from benchmark.evaluation import balanced_accuracy

    root = Path(results_dir)
    e2 = root / "e2"
    e2.mkdir(parents=True, exist_ok=True)
    validate_manifest(baseline_dir)
    frame, _ = load_data(baseline_dir)
    by_id = frame.set_index("sample_id", drop=False)
    methods = list(methods or (PRIMARY_FAMILIES + CLASSICAL_FAMILIES))
    if set(methods) - set(PRIMARY_FAMILIES + CLASSICAL_FAMILIES):
        raise ValueError("E2 accepts the five flexible primary and four classical sensitivity families")
    rows = []
    unavailable = []
    saved_test_outcomes = {}
    bootstrap_y = None
    bootstrap_test_ids = None
    from benchmark.evaluation import bootstrap_outcomes
    for rep in range(1, int(repetitions) + 1):
        for budget in budgets:
            for method in methods:
                cell = root / f"e1/rep_{rep}/n_{int(budget)}/{method}"
                done_path = cell / "complete.json"
                pipeline_path = cell / "pipeline.joblib"
                pred_path = cell / "test_predictions.npz"
                role_path = cell / "role_membership.npz"
                dest = e2 / f"rep_{rep}/n_{int(budget)}/{method}"
                dest.mkdir(parents=True, exist_ok=True)
                if not all(p.exists() for p in (done_path, pipeline_path, pred_path, role_path)):
                    entry = {"repetition": rep, "budget": int(budget), "family": method,
                             "status": "unavailable", "reason": "required completed E1 cache artifact is missing"}
                    atomic_json(dest / "status.json", entry); unavailable.append(entry); continue
                done = json.loads(done_path.read_text())
                if done.get("status") != "complete":
                    entry = {"repetition": rep, "budget": int(budget), "family": method,
                             "status": "unavailable", "reason": "E1 cell is not complete"}
                    atomic_json(dest / "status.json", entry); unavailable.append(entry); continue
                pipeline = joblib.load(pipeline_path)
                with np.load(role_path, allow_pickle=False) as roles:
                    cal_ids = roles["calibration_ids"]
                try:
                    cal = by_id.loc[cal_ids]
                except KeyError as exc:
                    raise ValueError("E1 calibration IDs are absent from the frozen baseline") from exc
                Xraw = cal[list(FEATURES)].to_numpy(dtype=np.float64)
                Xcal = pipeline["scaler"].transform(pipeline["imputer"].transform(Xraw))
                ycal = cal["label_id"].to_numpy(dtype=np.int64)
                test = np.load(pred_path, allow_pickle=False)
                test_ids = test["sample_id"]
                ytest = by_id.loc[test_ids, "label_id"].to_numpy(dtype=np.int64)
                ypred = test["y_pred"].astype(np.int8, copy=False)
                acc = balanced_accuracy(ytest, ypred)
                sets = test["prediction_sets"].astype(bool)
                if sets.shape != (len(ytest), N_CLASSES):
                    raise ValueError(f"saved test conformal sets have invalid shape for {method}")
                if bootstrap_y is None:
                    bootstrap_y = ytest.copy()
                    bootstrap_test_ids = test_ids.copy()
                elif not np.array_equal(bootstrap_test_ids, test_ids) or not np.array_equal(bootstrap_y, ytest):
                    raise ValueError("paired E2 methods/budgets/repetitions must use identical test IDs and order")
                saved_test_outcomes[f"rep_{rep}_n_{int(budget)}_{method}"] = {
                    "predictions": ypred, "covered": sets[np.arange(len(ytest)), ytest],
                    "set_sizes": sets.sum(axis=1).astype(np.uint8)}
                diagnostic_seed = int(1_000_003 * rep + int(budget))
                report = class_fidelity_report(pipeline["model"], Xcal, ycal,
                                               seed=diagnostic_seed, max_rows=2000,
                                               keep_samples=True)
                sample_payload = report.pop("diagnostic_samples", None)
                report.update({"experiment": 2, "repetition": rep, "budget": int(budget),
                               "family": method, "direct_balanced_accuracy": acc,
                               "test_metrics_source": "saved E1 test predictions",
                               "fit_reused": True, "diagnostic_role": "E1 conformal calibration",
                               "diagnostic_seed": diagnostic_seed})
                atomic_json(dest / "fidelity.json", report)
                if sample_payload:
                    fields = {}
                    for c in range(N_CLASSES):
                        if c in sample_payload["real_by_class"] and c in sample_payload["synthetic_by_class"]:
                            fields[f"real_c{c}"] = sample_payload["real_by_class"][c].astype(np.float32)
                            fields[f"synthetic_c{c}"] = sample_payload["synthetic_by_class"][c].astype(np.float32)
                    np.savez_compressed(dest / "diagnostic_samples.npz", **fields)
                rows.append({"family": method, "budget": int(budget), "repetition": rep,
                             "fidelity": report.get("score"), "balanced_accuracy": acc,
                             "status": report.get("status")})
    association = spearman_by_budget_repetition(rows)
    test_bootstrap = None
    if saved_test_outcomes and bootstrap_y is not None:
        test_bootstrap = bootstrap_outcomes(bootstrap_y, saved_test_outcomes,
                                             n_boot=1000, seed=271828, confidence=.95)
        atomic_json(e2 / "paired_test_bootstrap.json", test_bootstrap)
    summary = {"experiment": 2, "budgets": list(map(int, budgets)), "repetitions": int(repetitions),
               "methods": methods, "status": "complete_with_unavailable_cells" if unavailable else "complete",
               "unavailable_cells": unavailable, "records": rows, "associations": association,
               "paired_test_bootstrap": "e2/paired_test_bootstrap.json" if test_bootstrap else None,
               "uncertainty": {"test_predictions": "paired saved-outcome bootstrap with shared exact row-resampling weights across methods, budgets, and repetitions",
                               "quality_report": "staged_pending_runtime_profiling",
                               "quality_report_bootstrap_interval": None,
                               "reason": "1000-replicate SDMetrics resampling across all E2 cells is deferred until runtime profiling; no substitute interval is reported"},
               "family_independence_claim": False}
    atomic_json(e2 / "summary.json", summary)
    return summary


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Run Experiment 2 fidelity analysis from cached E1 fits.")
    parser.add_argument("--results", type=Path, default=Path("benchmark/results"))
    parser.add_argument("--baseline", type=Path, default=Path("lamost_baseline"))
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--budgets", type=lambda s: [int(x) for x in s.split(",")], default=list(E2_BUDGETS))
    args = parser.parse_args(argv)
    run_e2(args.results, args.baseline, args.repetitions, args.budgets)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
