"""Checkpointed experiment engine. It never starts work at import time."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import signal
import sys
import time
import traceback
import resource
import threading
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE / ".deps") not in sys.path:
    sys.path.insert(0, str(HERE / ".deps"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FEATURES = ["mag_ps_g", "mag_ps_r", "mag_ps_i", "mag_ps_z", "mag_ps_y", "gaia_g_mean_mag"]
METHODS = ["gaussian_nb", "shared_diagonal", "lda", "qda", "gmm", "copula", "arf", "kde", "chow_liu",
           "logistic", "linear_svm", "rbf_svm", "knn", "cart", "random_forest", "extra_trees", "hist_gb"]
E1_BUDGETS = [100, 300, 1_000, 3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000]
EXPENSIVE = {"rbf_svm", "kde", "knn", "arf"}


def _json_default(value):
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return float(value)
    if isinstance(value, (np.ndarray,)): return value.tolist()
    if isinstance(value, Path): return str(value)
    return repr(value)


def atomic_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=_json_default) + "\n")
    tmp.replace(path)


def _cell_heartbeat(cell, phase, status):
    now = time.time()
    atomic_json(Path(cell) / "heartbeat.json", {
        "phase": str(phase), "status": str(status), "epoch_seconds": now,
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    })


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def load_data(base_dir=None, include_test=True):
    """Load baseline + frozen split and return frame, positions, labels, IDs."""
    import pandas as pd
    base_dir = Path(base_dir or ROOT / "lamost_baseline")
    splits = pd.read_parquet(base_dir / "data/splits.parquet")
    if "sample_id" not in splits:
        raise ValueError("baseline and split table must share sample_id")
    split_col = next((c for c in ("reference_partition", "partition", "split") if c in splits.columns), None)
    if split_col is None:
        raise ValueError("could not identify frozen split column")
    if include_test:
        frame = pd.read_parquet(base_dir / "data/baseline.parquet")
        if "sample_id" not in frame: raise ValueError("baseline lacks sample_id")
        frame = frame.merge(splits[["sample_id", split_col]], on="sample_id", validate="one_to_one")
    else:
        # For the development-only runtime pilot, push the test exclusion into
        # DuckDB's Parquet scan so test feature and label values never enter
        # the Python frame.
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("development-only pilot requires DuckDB scan support") from exc
        base_path=str((base_dir/"data/baseline.parquet").resolve()).replace("'","''")
        split_path=str((base_dir/"data/splits.parquet").resolve()).replace("'","''")
        col='"'+split_col.replace('"','""')+'"'
        query=f"SELECT b.*, s.{col} AS {col} FROM read_parquet('{base_path}') b JOIN read_parquet('{split_path}') s USING(sample_id) WHERE lower(CAST(s.{col} AS VARCHAR)) <> 'test'"
        frame=duckdb.query(query).to_df()
    if "label_id" not in frame or any(c not in frame for c in FEATURES):
        raise ValueError("baseline does not satisfy the six-feature, label_id contract")
    return frame, split_col


def validate_manifest(base_dir=None):
    """Verify every file entry in the baseline release manifest before runs."""
    base_dir = Path(base_dir or ROOT / "lamost_baseline")
    manifest = json.loads((base_dir / "manifest.json").read_text())
    failures = []
    for rel, item in manifest["files"].items():
        path = base_dir / rel
        if not path.exists() or path.stat().st_size != item["size_bytes"] or sha256_file(path) != item["sha256"]:
            failures.append(rel)
    if failures: raise RuntimeError(f"baseline manifest verification failed: {failures}")
    return manifest


def _canonical_frame(frame):
    """Return rows in stable ID order for reproducible role sampling."""
    if "sample_id" not in frame:
        raise ValueError("baseline frame must include sample_id for reproducible roles")
    return frame.sort_values("sample_id", kind="mergesort").reset_index(drop=True)


def _model_module(method):
    if method in {"gaussian_nb", "shared_diagonal", "lda", "qda", "logistic", "linear_svm", "rbf_svm", "knn", "cart", "random_forest", "extra_trees", "hist_gb"}:
        return importlib.import_module("benchmark.models_basic")
    if method in {"gmm", "copula", "kde", "chow_liu"}:
        return importlib.import_module("benchmark.models_flexible")
    if method == "arf":
        for name in ("benchmark.models_arf", "benchmark.arf"):
            try: return importlib.import_module(name)
            except ModuleNotFoundError: pass
    raise ModuleNotFoundError(f"no model factory available for {method}")


def _timeout(seconds):
    class TrialTimeout(TimeoutError): pass
    def handler(_sig, _frame): raise TrialTimeout(f"trial exceeded {seconds}s timeout")
    if seconds and hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, handler); signal.alarm(int(seconds))
        return signal, TrialTimeout
    return None, TimeoutError


def _clear_timeout(token):
    if token and hasattr(signal, "SIGALRM"): token.alarm(0)


class _RSSGuard:
    """Stop the sequential runner before a fit exceeds its declared RSS cap."""
    def __init__(self, limit_gib, marker_path, cell_label):
        self.limit=int(float(limit_gib)*(1024**3)); self.marker=Path(marker_path); self.label=cell_label
        self.stop=threading.Event(); self.thread=None
    @staticmethod
    def rss_bytes():
        try:
            for line in open("/proc/self/status",encoding="ascii"):
                if line.startswith("VmRSS:"): return int(line.split()[1])*1024
        except OSError: return 0
        return 0
    def __enter__(self):
        def watch():
            while not self.stop.wait(.1):
                current=self.rss_bytes()
                if current>self.limit:
                    atomic_json(self.marker,{"status":"terminated_memory_limit","cell":self.label,
                        "rss_bytes":current,"limit_bytes":self.limit,"time_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())})
                    os.kill(os.getpid(),signal.SIGTERM)
        self.thread=threading.Thread(target=watch,name="benchmark-rss-guard",daemon=True); self.thread.start()
        return self
    def __exit__(self,*exc):
        self.stop.set()
        if self.thread: self.thread.join(timeout=.5)


def _score_metrics(y, pred):
    recalls = []
    for c in range(7):
        mask = y == c
        recalls.append(float((pred[mask] == c).mean()) if mask.any() else float("nan"))
    return {"balanced_accuracy": float(np.nanmean(recalls)), "class_recall": recalls}


def _predict_chunks(model, X, chunk=50_000, diagnostics=False):
    pred, scores, fallbacks = [], [], []
    for start in range(0, len(X), chunk):
        x = X[start:start + chunk]
        sc = np.asarray(model.score_matrix(x), dtype=np.float32)
        pred.append(np.asarray(np.argmax(sc, axis=1), dtype=np.int16))
        scores.append(sc)
        mask = getattr(model, "fallback_mask", None)
        fallbacks.append(np.asarray(mask, dtype=bool) if mask is not None else np.zeros(len(x), dtype=bool))
    result = (np.concatenate(pred), np.concatenate(scores))
    if diagnostics: return (*result, np.concatenate(fallbacks))
    return result


def _fit_classifier(mod, method, params, seed, X, y, n_jobs=1, sample_weight=None):
    model = mod.make_model(method, params, seed, n_jobs=n_jobs)
    if sample_weight is None:
        return model.fit(X, y)
    # The public factory wrapper validates classes and owns score/predict
    # methods; the fitted sklearn estimator accepts the explicit row weights.
    model.estimator.fit(X, y, sample_weight=np.asarray(sample_weight, dtype=np.float64))
    if not np.array_equal(model.estimator.classes_, np.arange(7)):
        raise ValueError("weighted estimator did not preserve labels 0..6")
    return model


def _tune_evaluate_cell(cell, method, Xfit, yfit, Xtune, ytune, Xcal, ycal, Xtest, ytest,
                        sample_weight=None, trials=10, seed=0, n_jobs=1, timeout=1800,
                        prediction_chunk=50_000, test_ids=None):
    """Run one sequential Optuna cell and save selected pipeline + test rows."""
    import joblib
    import optuna
    from sklearn.metrics import balanced_accuracy_score
    from benchmark.evaluation import conformal_threshold, conformal_evaluate
    cell = Path(cell); cell.mkdir(parents=True, exist_ok=True)
    mod = _model_module(method)
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed, n_startup_trials=3))
    seen, best, rows = {}, None, []
    complexity = getattr(mod, "complexity_key", lambda m, p: (json.dumps(p, sort_keys=True),))
    for ti in range(int(trials)):
        tr = study.ask(); start = time.monotonic(); params = {}; error = None; score = None
        try:
            params = mod.suggest_parameters(tr, method, len(yfit), int(np.bincount(yfit, minlength=7).min()))
            key = json.dumps(params, sort_keys=True, default=_json_default)
            if key in seen:
                score = seen[key]; study.tell(tr, score); status = "duplicate"
            else:
                alarm, _ = _timeout(timeout)
                try:
                    model = _fit_classifier(mod, method, params, seed+ti, Xfit, yfit, n_jobs, sample_weight)
                    pred = np.asarray(model.predict(Xtune), dtype=np.int64)
                finally: _clear_timeout(alarm)
                score = float(balanced_accuracy_score(ytune, pred)); seen[key] = score
                study.tell(tr, score); status = "complete"
                comp = tuple(complexity(method, params)); elapsed = time.monotonic()-start
                cand = (score, comp, elapsed, ti, params)
                if best is None or score > best[0] or (score == best[0] and (comp < best[1] or (comp == best[1] and (elapsed, ti) < (best[2], best[3])))):
                    best = cand
        except Exception as exc:
            status = "failed"; error = f"{type(exc).__name__}: {exc}"
            try: study.tell(tr, state=optuna.trial.TrialState.FAIL)
            except Exception: pass
        row = {"number": ti, "status": status, "params": params, "tuning_balanced_accuracy": score,
               "seconds": time.monotonic()-start, "error": error}
        rows.append(row)
        with open(cell / "trials.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=_json_default)+"\n")
    if best is None: raise RuntimeError(f"all trials failed for {method}")
    alarm,_=_timeout(timeout)
    try:
        final = _fit_classifier(mod, method, best[4], seed+900, Xfit, yfit, n_jobs, sample_weight)
        _, cal_scores, fallback_cal = _predict_chunks(final, Xcal, prediction_chunk, diagnostics=True)
    finally:_clear_timeout(alarm)
    kind = getattr(final, "score_kind", "probability")
    q = conformal_threshold(cal_scores, ycal, kind, .1)
    test_pred, test_scores, fallback_test = _predict_chunks(final, Xtest, prediction_chunk, diagnostics=True)
    evaluation = conformal_evaluate(test_scores, ytest, q, kind)
    pred_payload = {"y_pred":test_pred.astype(np.int16),
                    "scores":test_scores.astype(np.float32),
                    "prediction_sets":evaluation["sets"].astype(np.uint8),
                    "invalid_support_fallback":fallback_test.astype(np.uint8)}
    if test_ids is not None: pred_payload["sample_id"] = np.asarray(test_ids)
    np.savez_compressed(cell / "test_predictions.npz", **pred_payload)
    joblib.dump({"model": final, "params": best[4], "seed": seed+900}, cell / "pipeline.joblib", compress=3)
    result = {"status": "complete", "method": method, "selected_params": best[4],
              "best_tuning_balanced_accuracy": best[0], "score_kind": kind, "conformal_threshold": q,
              "balanced_accuracy": evaluation["balanced_accuracy"], "set_size": evaluation["set_size"],
              "coverage": evaluation["coverage"], "per_class": evaluation["per_class"],
              "invalid_support_fallback_count": {"calibration": int(fallback_cal.sum()), "test": int(fallback_test.sum())},
              "trial_log": rows, "fit_seconds": float(sum(r["seconds"] for r in rows)),
              "effective_fit_rows": int(len(yfit)), "compute_reused": False}
    atomic_json(cell / "complete.json", result)
    return result


def _evaluate_fixed_config(cell, method, params, Xfit, yfit, Xcal, ycal, Xtest, ytest,
                           seed=0, n_jobs=1, prediction_chunk=50_000, timeout=1800, test_ids=None):
    """Refit one frozen configuration, recalibrate on clean calibration data."""
    import joblib
    from benchmark.evaluation import conformal_threshold, conformal_evaluate
    cell = Path(cell); cell.mkdir(parents=True, exist_ok=True)
    mod = _model_module(method)
    start=time.monotonic()
    alarm,_=_timeout(timeout)
    try: model=mod.make_model(method,dict(params),seed,n_jobs=n_jobs).fit(Xfit,yfit)
    finally:_clear_timeout(alarm)
    fit_seconds=time.monotonic()-start
    alarm,_=_timeout(timeout)
    try:
        _,cal_scores,fallback_cal=_predict_chunks(model,Xcal,prediction_chunk,diagnostics=True)
        pred,scores,fallback_test=_predict_chunks(model,Xtest,prediction_chunk,diagnostics=True)
    finally:_clear_timeout(alarm)
    kind=getattr(model,"score_kind","probability")
    q=conformal_threshold(cal_scores,ycal,kind,.1)
    outcome=conformal_evaluate(scores,ytest,q,kind)
    pred_payload={"y_pred":pred.astype(np.int16),"scores":scores.astype(np.float32),
        "prediction_sets":outcome["sets"].astype(np.uint8),"invalid_support_fallback":fallback_test.astype(np.uint8)}
    if test_ids is not None: pred_payload["sample_id"]=np.asarray(test_ids)
    np.savez_compressed(cell/"test_predictions.npz",**pred_payload)
    joblib.dump({"model":model,"params":dict(params),"seed":seed},cell/"pipeline.joblib",compress=3)
    result={"status":"complete","method":method,"selected_params":dict(params),"frozen_configuration":True,
        "score_kind":kind,"conformal_threshold":q,"balanced_accuracy":outcome["balanced_accuracy"],
        "set_size":outcome["set_size"],"coverage":outcome["coverage"],"per_class":outcome["per_class"],
        "invalid_support_fallback_count":{"calibration":int(fallback_cal.sum()),"test":int(fallback_test.sum())},
        "fit_seconds":fit_seconds,"effective_fit_rows":int(len(yfit)),"compute_reused":False}
    atomic_json(cell/"complete.json",result)
    return result


class ExperimentRunner:
    def __init__(self, output_dir, workers=1, trial_timeout=1800, prediction_chunk=50_000,
                 memory_limit_gib=7.0, resource_profile="native8gib8cores"):
        if workers != 1:
            # The sequential protocol intentionally serializes trials/cells.
            raise ValueError("protocol runner is sequential; workers must be 1")
        self.output = Path(output_dir); self.output.mkdir(parents=True, exist_ok=True)
        self.workers, self.trial_timeout = workers, int(trial_timeout)
        self.prediction_chunk, self.memory_limit_gib = int(prediction_chunk), float(memory_limit_gib)
        self.resource_profile = resource_profile
        self.memory_cap = self._apply_memory_cap(self.memory_limit_gib)
        try:
            from threadpoolctl import threadpool_limits
            self.thread_limiter = threadpool_limits(limits=1)
        except ImportError:
            self.thread_limiter = None

    @staticmethod
    def _apply_memory_cap(limit_gib):
        """Apply a hard address-space headroom ceiling to this sequential worker."""
        if not hasattr(resource, "RLIMIT_AS"):
            return {"enforced": False, "reason": "RLIMIT_AS unavailable"}
        current_kib = None
        try:
            with open("/proc/self/status", encoding="ascii") as f:
                for line in f:
                    if line.startswith("VmSize:"):
                        current_kib = int(line.split()[1]); break
            if current_kib is None: raise RuntimeError("cannot read current virtual memory size")
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            ceiling = current_kib * 1024 + int(limit_gib * (1024 ** 3))
            if hard != resource.RLIM_INFINITY:
                ceiling = min(ceiling, hard)
            if soft == resource.RLIM_INFINITY or soft > ceiling:
                resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
            actual, actual_hard = resource.getrlimit(resource.RLIMIT_AS)
            return {"enforced": actual != resource.RLIM_INFINITY,
                    "limit_gib_headroom": float(limit_gib), "soft_bytes": int(actual),
                    "hard_bytes": None if actual_hard == resource.RLIM_INFINITY else int(actual_hard),
                    "initial_vmsize_kib": current_kib}
        except Exception as exc:
            raise RuntimeError(f"unable to enforce declared {limit_gib:g} GiB memory ceiling: {exc}") from exc

    def run_e1(self, frame, split_col, budgets=None, repetitions=5, methods=None, resume=False,
               pilot=False, n_trials=None, seed=271828, rep_start=0):
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import balanced_accuracy_score
        from benchmark.sampling import sample_nested_roles, role_manifest
        import joblib
        # A stable source order makes role membership identical across fresh
        # child processes and between the pandas full-data and DuckDB pilot
        # loaders, whose parquet joins may return rows in different orders.
        frame = _canonical_frame(frame)
        methods = list(methods or METHODS)
        budgets = list(budgets or ([100, 300, 1_000] if pilot else E1_BUDGETS))
        repetitions = int(repetitions)
        rep_start=int(rep_start)
        if rep_start<0: raise ValueError("rep_start must be nonnegative")
        if repetitions < 1: raise ValueError("repetitions must be positive")
        # Pilot runs are explicitly development-only and can never score test.
        if pilot and any(int(b) > 10_000 for b in budgets): raise ValueError("pilot budget cap is 10,000")
        allowed = frame[split_col].astype(str).str.lower()
        test_mask = allowed.eq("test")
        pool = np.flatnonzero(~test_mask.to_numpy())
        test_pos = np.flatnonzero(test_mask.to_numpy())
        y_all = frame.label_id.to_numpy(dtype=np.int64)
        if set(np.unique(y_all)) - set(range(7)): raise ValueError("labels must be integer IDs 0..6")
        X_raw = frame[FEATURES].to_numpy(dtype=np.float64)
        run_config = {"experiment": 1, "budgets": budgets, "repetitions": repetitions, "methods": methods,
                      "pilot_development_only": bool(pilot), "trials": n_trials, "resource_profile": self.resource_profile,
                      "seed": int(seed),
                      "repetition_start":rep_start,
                      "workers": 1, "trial_timeout_seconds": self.trial_timeout, "memory_limit_gib": self.memory_limit_gib,
                      "memory_cap": self.memory_cap,
                      "native_thread_limit": 1,
                      "prediction_chunk_rows": self.prediction_chunk, "features": FEATURES,
                      "test_rows": 0 if pilot else len(test_pos),
                      "protocol_sha256": sha256_file(HERE/"protocol_source.txt"),
                      "baseline_manifest_sha256": sha256_file(ROOT/"lamost_baseline/manifest.json") if (ROOT/"lamost_baseline/manifest.json").exists() else None,
                      "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if (self.output/"master_run_config.json").exists():
            inv=self.output/"invocation_configs"; inv.mkdir(parents=True,exist_ok=True)
            invname=f"rep_{rep_start+1}_to_{rep_start+repetitions}_n_{'-'.join(map(str,budgets))}_{'-'.join(methods)}.json"
            atomic_json(inv/invname,run_config)
        else:
            atomic_json(self.output / "run_config.json", run_config)
        atomic_json(self.output / "environment.json", {"python": sys.version, "platform": platform.platform(),
                    "numpy": np.__version__, "rss_peak_start_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
        # Test features/labels remain inaccessible to tuning: only selected,
        # frozen models reach the one-time final evaluation below.
        if not pilot:
            test_ids = frame.loc[test_pos, "sample_id"].to_numpy() if "sample_id" in frame else test_pos
            test_X_raw = X_raw[test_pos]
            test_y = y_all[test_pos]
        # Build every repetition's roles from the same maximum-budget anchor,
        # then execute in ascending budget order so early curves become
        # reviewable before the next, more expensive budget starts.
        anchored = sorted(set(int(b) for b in budgets) | {E1_BUDGETS[-1]})
        rep_numbers=range(rep_start,rep_start+repetitions)
        roles_by_rep = {rep: sample_nested_roles(y_all, anchored, seed + rep, pool_indices=pool)
                        for rep in rep_numbers}
        for budget in budgets:
            for rep in rep_numbers:
                role = roles_by_rep[rep][int(budget)]
                role_root=self.output/f"e1/rep_{rep+1}/n_{budget}"
                role_root.mkdir(parents=True,exist_ok=True)
                roleinfo=role_manifest(role,y_all,frame["sample_id"].to_numpy() if "sample_id" in frame else None)
                shared_role_ids=role_root/"role_membership.npz"
                if "sample_id" in frame and not shared_role_ids.exists():
                    np.savez_compressed(shared_role_ids,fit_ids=frame.iloc[role.fit].sample_id.to_numpy(),
                        tuning_ids=frame.iloc[role.tune].sample_id.to_numpy(),calibration_ids=frame.iloc[role.calibration].sample_id.to_numpy())
                shared_positions=role_root/"role_positions.npz"
                if not shared_positions.exists(): np.savez_compressed(shared_positions,fit=role.fit,tuning=role.tune,calibration=role.calibration)
                for method in methods:
                    cell = self.output / f"e1/rep_{rep+1}/n_{budget}/{method}"
                    done = cell / "complete.json"
                    if resume and done.exists(): continue
                    cell.mkdir(parents=True, exist_ok=True)
                    manifest_path=cell/"manifest.json"
                    if resume and manifest_path.exists():
                        record=json.loads(manifest_path.read_text())
                        if (record.get("method")!=method or record.get("budget")!=role.budget or
                            record.get("repetition")!=rep+1 or record.get("seed")!=seed+rep or record.get("roles")!=roleinfo):
                            raise RuntimeError(f"checkpoint metadata mismatch at {cell}")
                        record["status"]="started"; record.pop("error",None); record.pop("traceback",None)
                    else:
                        record = {"experiment": 1, "repetition": rep+1, "budget": role.budget,
                                  "method": method, "status": "started", "seed": seed + rep,
                                  "roles": roleinfo,
                                  "trials": []}
                    atomic_json(cell / "manifest.json", record)
                    try:
                        fit_idx, tune_idx, cal_idx = role.fit, role.tune, role.calibration
                        # Hard-link shared per-budget memberships so each cell
                        # has the familiar artifact name without storing 17
                        # duplicate copies of large ID arrays.
                        for source in (shared_role_ids,shared_positions):
                            if not source.exists(): continue
                            dest=cell/source.name
                            if not dest.exists():
                                try: os.link(source,dest)
                                except OSError:
                                    import shutil; shutil.copy2(source,dest)
                        yfit, ytune = y_all[fit_idx], y_all[tune_idx]
                        counts = np.bincount(yfit, minlength=7)
                        # A missing fit class is a transparent unsupported cell.
                        if np.any(counts == 0): raise ValueError("unsupported: fitting role lacks one or more classes")
                        imputer = SimpleImputer(strategy="median").fit(X_raw[fit_idx])
                        scaler = StandardScaler().fit(imputer.transform(X_raw[fit_idx]))
                        Xfit = scaler.transform(imputer.transform(X_raw[fit_idx])).astype(np.float64)
                        Xtune = scaler.transform(imputer.transform(X_raw[tune_idx])).astype(np.float64)
                        Xcal = scaler.transform(imputer.transform(X_raw[cal_idx])).astype(np.float64)
                        trials = int(n_trials or (5 if method in EXPENSIVE else 10))
                        if record.get("trial_budget",trials)!=trials:
                            raise RuntimeError(f"checkpoint trial budget mismatch: saved={record.get('trial_budget')} requested={trials}")
                        record["trial_budget"]=trials
                        atomic_json(manifest_path,record)
                        mod = _model_module(method)
                        if not hasattr(mod, "suggest_parameters"):
                            raise RuntimeError(f"{method} model module lacks suggest_parameters")
                        study_path=cell/"study.joblib"
                        try:
                            import optuna
                            optuna.logging.set_verbosity(optuna.logging.WARNING)
                            if resume and study_path.exists():
                                study=joblib.load(study_path)
                            else:
                                study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed + rep + int(budget), n_startup_trials=3))
                            if len(study.trials)>trials:
                                raise RuntimeError("checkpoint has more tuning trials than requested")
                        except Exception as exc: raise RuntimeError(f"Optuna unavailable: {exc}")
                        seen = {json.dumps(t.params,sort_keys=True,default=_json_default):float(t.value)
                                for t in study.trials if t.value is not None and t.state.name=="COMPLETE"}
                        complexity = getattr(mod, "complexity_key", lambda m, p: (json.dumps(p, sort_keys=True),))
                        best = None
                        row_by_number={int(r["number"]):r for r in record.get("trials",[])}
                        for tr_num, trial_row in sorted(row_by_number.items()):
                            if trial_row.get("status") not in {"complete","duplicate"} or trial_row.get("tuning_balanced_accuracy") is None: continue
                            prm=trial_row.get("params",{}); val=float(trial_row["tuning_balanced_accuracy"])
                            candidate=(val,tuple(complexity(method,prm)),float(trial_row.get("seconds",0)),tr_num,prm)
                            if (best is None or candidate[0]>best[0] or (candidate[0]==best[0] and
                                (candidate[1]<best[1] or (candidate[1]==best[1] and (candidate[2],candidate[3])<(best[2],best[3]))))): best=candidate
                        for ti in range(len(study.trials), trials):
                            tr = study.ask()
                            started = time.monotonic(); status = "failed"; err = None; score = None
                            params = {}
                            try:
                                params = mod.suggest_parameters(tr, method, len(fit_idx), int(counts.min()))
                                key = json.dumps(params, sort_keys=True, default=_json_default)
                                if key in seen:
                                    score = seen[key]; status = "duplicate"
                                    study.tell(tr, score)
                                else:
                                    model = mod.make_model(method, params, seed + rep * 1000 + ti, n_jobs=1)
                                    timeout_token, timeout_type = _timeout(self.trial_timeout)
                                    tune_prediction_started=time.monotonic()
                                    _cell_heartbeat(cell, f"trial_{ti}_fit_and_tune", "started")
                                    try:
                                        with _RSSGuard(self.memory_limit_gib,cell/"resource_limit_failure.json",f"rep={rep+1},budget={budget},method={method},trial={ti}"):
                                            model.fit(Xfit, yfit)
                                            pred, _, fallback_tune = _predict_chunks(model, Xtune, self.prediction_chunk, diagnostics=True)
                                    finally:
                                        _clear_timeout(timeout_token)
                                        _cell_heartbeat(cell, f"trial_{ti}_fit_and_tune", "finished")
                                    tune_prediction_seconds=time.monotonic()-tune_prediction_started
                                    score = float(balanced_accuracy_score(ytune, pred))
                                    seen[key] = score; status = "complete"
                                    study.tell(tr, score)
                                    candidate = (score, tuple(complexity(method, params)), time.monotonic()-started, ti, params)
                                    if (best is None or candidate[0] > best[0] or
                                        (candidate[0] == best[0] and (candidate[1] < best[1] or
                                         (candidate[1] == best[1] and (candidate[2] < best[2] or
                                          (candidate[2] == best[2] and candidate[3] < best[3])))))):
                                        best = candidate
                            except Exception as exc:
                                err = f"{type(exc).__name__}: {exc}"
                                err_traceback = traceback.format_exc()
                                try: study.tell(tr, state=optuna.trial.TrialState.FAIL)
                                except Exception: pass
                            else:
                                err_traceback = None
                            row = {"number": ti, "status": status, "params": locals().get("params", {}),
                                   "tuning_balanced_accuracy": score, "seconds": time.monotonic()-started,
                                   "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "error": err,
                                   "error_traceback": err_traceback}
                            record["trials"].append(row)
                            with open(cell / "trials.jsonl", "a", encoding="utf-8") as f:
                                f.write(json.dumps(row, default=_json_default) + "\n")
                            atomic_json(cell / "manifest.json", record)
                            joblib.dump(study,study_path,compress=3)
                            try: study.trials_dataframe().to_csv(cell/"study_trials.csv",index=False)
                            except Exception: pass
                        if best is None: raise RuntimeError("all hyperparameter trials failed")
                        params = best[4]
                        final_timeout, _ = _timeout(self.trial_timeout)
                        final_fit_started=time.monotonic()
                        _cell_heartbeat(cell, "final_fit", "started")
                        try:
                            with _RSSGuard(self.memory_limit_gib,cell/"resource_limit_failure.json",f"rep={rep+1},budget={budget},method={method},final_fit"):
                                model = mod.make_model(method, params, seed + rep * 1000 + 900, n_jobs=1).fit(Xfit, yfit)
                        finally:
                            _clear_timeout(final_timeout)
                            _cell_heartbeat(cell, "final_fit", "finished")
                        final_fit_seconds=time.monotonic()-final_fit_started
                        # Calibration threshold uses only held-out calibration
                        # labels and the already selected model.
                        selected_tune_alarm, _ = _timeout(self.trial_timeout)
                        selected_tune_prediction_started=time.monotonic()
                        _cell_heartbeat(cell, "selected_tuning_inference", "started")
                        try:
                            with _RSSGuard(self.memory_limit_gib,cell/"resource_limit_failure.json",f"rep={rep+1},budget={budget},method={method},selected_tuning"):
                                tune_pred, _, fallback_tune = _predict_chunks(model, Xtune, self.prediction_chunk, diagnostics=True)
                        finally:
                            _clear_timeout(selected_tune_alarm)
                            _cell_heartbeat(cell, "selected_tuning_inference", "finished")
                        selected_tuning_prediction_seconds=time.monotonic()-selected_tune_prediction_started
                        calibration_alarm, _ = _timeout(self.trial_timeout)
                        cal_prediction_started=time.monotonic()
                        _cell_heartbeat(cell, "calibration_inference", "started")
                        try:
                            with _RSSGuard(self.memory_limit_gib,cell/"resource_limit_failure.json",f"rep={rep+1},budget={budget},method={method},calibration"):
                                cal_pred, cal_scores, fallback_cal = _predict_chunks(model, Xcal, self.prediction_chunk, diagnostics=True)
                        finally:
                            _clear_timeout(calibration_alarm)
                            _cell_heartbeat(cell, "calibration_inference", "finished")
                        calibration_prediction_seconds=time.monotonic()-cal_prediction_started
                        score_kind = getattr(model, "score_kind", "probability")
                        # Native negative one-vs-rest margins are the declared
                        # conformal score for SVMs; no label-fit map is applied.
                        score_map = None
                        cal_scores = cal_scores.astype(np.float32)
                        alpha = 0.10
                        from benchmark.evaluation import conformal_threshold, conformal_evaluate
                        threshold = conformal_threshold(cal_scores, y_all[cal_idx], score_kind=score_kind, alpha=alpha)
                        joblib.dump({"model": model, "imputer": imputer, "scaler": scaler, "score_map": score_map,
                                     "params": params, "seed": seed + rep * 1000 + 900}, cell / "pipeline.joblib", compress=3)
                        # Pilot is strictly development-only: it neither loads
                        # test features nor predicts/evaluates test outcomes.
                        if not pilot:
                            test_model_X = scaler.transform(imputer.transform(test_X_raw))
                            test_prediction_started=time.monotonic()
                            test_alarm, _ = _timeout(self.trial_timeout)
                            _cell_heartbeat(cell, "test_inference", "started")
                            try:
                                with _RSSGuard(self.memory_limit_gib,cell/"resource_limit_failure.json",f"rep={rep+1},budget={budget},method={method},test_inference"):
                                    test_pred, test_scores, fallback_test = _predict_chunks(model, test_model_X, self.prediction_chunk, diagnostics=True)
                            finally:
                                _clear_timeout(test_alarm)
                                _cell_heartbeat(cell, "test_inference", "finished")
                            test_prediction_seconds=time.monotonic()-test_prediction_started
                            outcome = conformal_evaluate(test_scores, test_y, threshold, score_kind=score_kind)
                            test_sets = outcome["sets"]
                            np.savez_compressed(cell / "test_predictions.npz", sample_id=test_ids, y_pred=test_pred.astype(np.int16),
                                                scores=test_scores.astype(np.float32), prediction_sets=test_sets.astype(np.uint8),
                                                invalid_support_fallback=fallback_test.astype(np.uint8))
                        rec = {"status": "complete", "selected_params": params, "best_tuning_balanced_accuracy": best[0],
                               "score_kind": score_kind, "conformal_alpha": alpha, "conformal_nonconformity_threshold": threshold,
                               "calibration_n": len(cal_idx), "successful_trials": sum(t["status"] == "complete" for t in record["trials"]),
                               "failed_trials": sum(t["status"] == "failed" for t in record["trials"]),
                               "duplicate_trials": sum(t["status"] == "duplicate" for t in record["trials"]),
                               "fit_seconds_total": sum(t["seconds"] for t in record["trials"]),
                               "final_fit_seconds": final_fit_seconds,
                               "calibration_prediction_seconds": calibration_prediction_seconds,
                               "test_prediction_seconds": None if pilot else test_prediction_seconds,
                               "selected_tuning_prediction_seconds": selected_tuning_prediction_seconds,
                               "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                               "test_metrics": None if pilot else {"balanced_accuracy": outcome["balanced_accuracy"], "per_class": outcome["per_class"]},
                               "mean_prediction_set_size": None if pilot else outcome["set_size"],
                               "test_coverage": None if pilot else outcome["coverage"],
                               "invalid_support_fallback_count": {"tuning": int(fallback_tune.sum()),
                                   "calibration": int(fallback_cal.sum()),
                                   "test": None if pilot else int(fallback_test.sum())},
                               "memory_limit_exceeded": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > self.memory_limit_gib * 1024 * 1024,
                               "resource_profile": self.resource_profile}
                        atomic_json(done, rec)
                        artifact_paths=[cell/"complete.json",cell/"pipeline.joblib",
                            cell/"trials.jsonl",cell/"study.joblib",cell/"study_trials.csv",cell/"role_membership.npz",cell/"role_positions.npz"]
                        if not pilot: artifact_paths.append(cell/"test_predictions.npz")
                        atomic_json(cell/"artifact_hashes.json",{str(p.name):sha256_file(p) for p in artifact_paths if p.exists()})
                        record.update(rec); atomic_json(cell / "manifest.json", record)
                    except Exception as exc:
                        record.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
                        atomic_json(cell / "manifest.json", record)
        statuses=[]
        for manifest_path in (self.output/"e1").glob("rep_*/n_*/*/manifest.json"):
            try: statuses.append(json.loads(manifest_path.read_text()).get("status","unknown"))
            except Exception: statuses.append("unreadable")
        summary={"complete_cells":statuses.count("complete"),"failed_cells":statuses.count("failed"),
                 "other_cells":len(statuses)-statuses.count("complete")-statuses.count("failed"),
                 "pilot_development_only":bool(pilot),"cell_count":len(statuses)}
        atomic_json(self.output/"e1_run_summary.json",summary)
        if summary["complete_cells"]==0:
            raise RuntimeError(f"Experiment 1 produced zero complete cells; see {self.output/'e1_run_summary.json'}")
        return run_config

    def run_e3(self, frame, split_col, repetitions=3, methods=None, resume=False,
               trials=10, seed=271828):
        """Run direct Bayes, synthetic-only, and real-only routes at N=100k."""
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import balanced_accuracy_score
        import joblib
        import shutil
        from benchmark.sampling import sample_nested_roles, role_manifest
        from benchmark.evaluation import conformal_threshold, conformal_evaluate
        frame = frame.reset_index(drop=True)
        frame = frame
        methods = list(methods or ["gmm", "copula", "arf", "kde", "chow_liu"])
        learners = ["logistic", "random_forest", "hist_gb"]
        if repetitions != 3:
            raise ValueError("Experiment 3 is specified for three paired repetitions")
        if int(trials) < 3: raise ValueError("each downstream route requires at least three tuning trials")
        split = frame[split_col].astype(str).str.lower()
        test_pos = np.flatnonzero(split.eq("test").to_numpy())
        pool = np.flatnonzero(~split.eq("test").to_numpy())
        y = frame.label_id.to_numpy(dtype=np.int64)
        Xraw = frame[FEATURES].to_numpy(dtype=np.float64)
        test_Xraw = Xraw[test_pos]
        test_y = y[test_pos]
        test_ids = frame.iloc[test_pos].sample_id.to_numpy() if "sample_id" in frame else test_pos
        cfg = {"experiment": 3, "budget": 100_000, "roles": [80_000, 10_000, 10_000],
               "repetitions": repetitions, "methods": methods, "downstream_learners": learners,
               "synthetic_rows": 400_000, "trials_per_route": trials, "seed": seed,
               "resource_profile": self.resource_profile, "workers": 1,
               "trial_timeout_seconds": self.trial_timeout, "memory_limit_gib": self.memory_limit_gib}
        atomic_json(self.output / "e3_run_config.json", cfg)
        for rep in range(repetitions):
            roles = sample_nested_roles(y, [100_000, E1_BUDGETS[-1]], seed + rep, pool_indices=pool)[100_000]
            fit_idx, tune_idx, cal_idx = roles.fit, roles.tune, roles.calibration
            rep_dir = self.output / f"e3/rep_{rep+1}"
            rep_dir.mkdir(parents=True, exist_ok=True)
            if "sample_id" in frame:
                np.savez_compressed(rep_dir / "role_membership.npz", fit_ids=frame.iloc[fit_idx].sample_id.to_numpy(),
                    tuning_ids=frame.iloc[tune_idx].sample_id.to_numpy(), calibration_ids=frame.iloc[cal_idx].sample_id.to_numpy())
            atomic_json(rep_dir / "roles.json", role_manifest(roles, y, frame["sample_id"].to_numpy() if "sample_id" in frame else None))
            imp = SimpleImputer(strategy="median").fit(Xraw[fit_idx])
            scaler = StandardScaler().fit(imp.transform(Xraw[fit_idx]))
            Xfit = scaler.transform(imp.transform(Xraw[fit_idx])).astype(np.float64)
            Xtune = scaler.transform(imp.transform(Xraw[tune_idx])).astype(np.float64)
            Xcal = scaler.transform(imp.transform(Xraw[cal_idx])).astype(np.float64)
            Xtest = scaler.transform(imp.transform(test_Xraw)).astype(np.float64)
            yfit, ytune = y[fit_idx], y[tune_idx]
            for generator in methods:
                base_cell = self.output / f"e1/rep_{rep+1}/n_100000/{generator}"
                base_done = base_cell / "complete.json"
                pipeline_path = base_cell / "pipeline.joblib"
                cell_base = self.output / f"e3/rep_{rep+1}/{generator}"
                cell_base.mkdir(parents=True, exist_ok=True)
                if not base_done.exists() or not pipeline_path.exists():
                    atomic_json(cell_base / "status.json", {"status": "unavailable", "reason": "matching Experiment 1 selected fit is not cached"})
                    continue
                try:
                    base_manifest = json.loads(base_done.read_text())
                    if base_manifest.get("status") != "complete": raise RuntimeError("cached Experiment 1 fit is incomplete")
                    cached = joblib.load(pipeline_path)
                    model = cached["model"]
                    # Reuse requires exact role memberships and coordinate transform.
                    base_roles = json.loads((base_cell / "manifest.json").read_text())["roles"]
                    current_roles = role_manifest(roles, y, frame["sample_id"].to_numpy() if "sample_id" in frame else None)
                    if base_roles["roles"] != current_roles["roles"]:
                        raise RuntimeError("cached generator role IDs do not match Experiment 3")
                    if not np.array_equal(cached["imputer"].statistics_, imp.statistics_) or not np.allclose(cached["scaler"].mean_, scaler.mean_) or not np.allclose(cached["scaler"].scale_, scaler.scale_):
                        raise RuntimeError("cached generator preprocessing does not match Experiment 3")
                    _, direct_scores = _predict_chunks(model, Xtest, self.prediction_chunk)
                    _, direct_cal = _predict_chunks(model, Xcal, self.prediction_chunk)
                    direct_kind = getattr(model, "score_kind", "probability")
                    direct_q = conformal_threshold(direct_cal, y[cal_idx], direct_kind, .1)
                    direct_eval = conformal_evaluate(direct_scores, test_y, direct_q, direct_kind)
                    np.savez_compressed(cell_base / "direct_test_predictions.npz", sample_id=test_ids,
                        y_pred=direct_eval["predictions"].astype(np.int16), scores=direct_scores,
                        prediction_sets=direct_eval["sets"].astype(np.uint8))
                    atomic_json(cell_base / "direct.json", {"status": "complete", "source": "reused_e1_fit",
                        "balanced_accuracy": direct_eval["balanced_accuracy"], "set_size": direct_eval["set_size"],
                        "coverage": direct_eval["coverage"], "per_class": direct_eval["per_class"],
                        "logical_fit_seconds": None, "compute_reused": True})
                    # Deterministic class counts sum to exactly 5x fit n.
                    counts = np.bincount(yfit, minlength=7)
                    raw = counts * 5.0
                    synth_counts = np.floor(raw).astype(int)
                    remainder = 5 * len(yfit) - int(synth_counts.sum())
                    order = np.argsort(-(raw - synth_counts), kind="stable")
                    synth_counts[order[:remainder]] += 1
                    sx, sy = [], []
                    for c, count in enumerate(synth_counts):
                        if count:
                            sx.append(model.sample_class(c, int(count), seed + rep * 10_000 + c))
                            sy.append(np.full(int(count), c, dtype=np.int64))
                    Xsyn, ysyn = np.vstack(sx).astype(np.float64), np.concatenate(sy)
                    np.savez_compressed(cell_base / "synthetic_training_data.npz", X=Xsyn.astype(np.float32), y=ysyn.astype(np.int8), counts=synth_counts)
                    for route in ("synthetic", "real"):
                        for learner in learners:
                            cell = cell_base / f"{learner}_{route}"
                            done = cell / "complete.json"
                            if resume and done.exists(): continue
                            cell.mkdir(parents=True, exist_ok=True)
                            shared_cell = rep_dir / "shared_real" / learner
                            if route == "real" and shared_cell.joinpath("complete.json").exists():
                                for artifact in ("complete.json", "test_predictions.npz", "pipeline.joblib", "trials.jsonl"):
                                    source = shared_cell / artifact
                                    if source.exists(): shutil.copy2(source, cell / artifact)
                                reused = json.loads(done.read_text())
                                reused.update(generator=generator, compute_reused=True, reused_from=str(shared_cell.relative_to(self.output)))
                                atomic_json(done, reused)
                                continue
                            route_X, route_y = (Xsyn, ysyn) if route == "synthetic" else (Xfit, yfit)
                            mod = importlib.import_module("benchmark.models_basic")
                            import optuna
                            optuna.logging.set_verbosity(optuna.logging.WARNING)
                            study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed + rep))
                            trial_rows=[]; best=None; seen={}
                            for ti in range(int(trials)):
                                tr=study.ask(); params={}; err=None; start=time.monotonic()
                                try:
                                    params=mod.suggest_parameters(tr, learner, len(route_y), int(np.bincount(route_y,minlength=7).min()))
                                    key=json.dumps(params,sort_keys=True,default=_json_default)
                                    if key in seen:
                                        score=seen[key]; study.tell(tr,score); status="duplicate"
                                    else:
                                        candidate=mod.make_model(learner,params,seed+rep*1000+ti,n_jobs=1)
                                        alarm,_=_timeout(self.trial_timeout)
                                        try:
                                            candidate.fit(route_X,route_y)
                                            tune_pred,_,_=_predict_chunks(candidate,Xtune,self.prediction_chunk,diagnostics=True)
                                        finally:_clear_timeout(alarm)
                                        score=float(balanced_accuracy_score(ytune,tune_pred))
                                        seen[key]=score; study.tell(tr,score); status="complete"
                                        comp=tuple(mod.complexity_key(learner,params))
                                        cand=(score,comp,time.monotonic()-start,ti,params)
                                        if best is None or score>best[0] or (score==best[0] and (comp<best[1] or (comp==best[1] and (cand[2],ti)<(best[2],best[3])))): best=cand
                                except Exception as exc:
                                    score=None; status="failed"; err=f"{type(exc).__name__}: {exc}"
                                    try: study.tell(tr,state=optuna.trial.TrialState.FAIL)
                                    except Exception: pass
                                row={"number":ti,"status":status,"params":params,"tuning_balanced_accuracy":score,"seconds":time.monotonic()-start,"error":err}
                                trial_rows.append(row)
                                with open(cell/"trials.jsonl","a",encoding="utf-8") as f:f.write(json.dumps(row,default=_json_default)+"\n")
                            if best is None: raise RuntimeError(f"all trials failed for {learner}/{route}")
                            alarm,_=_timeout(self.trial_timeout)
                            try:
                                final=mod.make_model(learner,best[4],seed+rep*1000+900,n_jobs=1).fit(route_X,route_y)
                                _, cal_scores=_predict_chunks(final,Xcal,self.prediction_chunk)
                                test_pred,test_scores=_predict_chunks(final,Xtest,self.prediction_chunk)
                            finally:_clear_timeout(alarm)
                            kind=getattr(final,"score_kind","probability")
                            q=conformal_threshold(cal_scores,y[cal_idx],kind,.1)
                            evaluation=conformal_evaluate(test_scores,test_y,q,kind)
                            np.savez_compressed(cell/"test_predictions.npz",sample_id=test_ids,y_pred=test_pred.astype(np.int16),scores=test_scores.astype(np.float32),prediction_sets=evaluation["sets"].astype(np.uint8))
                            joblib.dump({"model":final,"params":best[4],"route":route,"generator":generator,"seed":seed+rep*1000+900},cell/"pipeline.joblib",compress=3)
                            atomic_json(done,{"status":"complete","route":route,"learner":learner,"generator":generator,
                                "selected_params":best[4],"best_tuning_balanced_accuracy":best[0],"trials":trial_rows,
                                "effective_fit_rows":int(len(route_y)),"unique_real_fit_rows":int(len(yfit)),
                                "balanced_accuracy":evaluation["balanced_accuracy"],"set_size":evaluation["set_size"],
                                "coverage":evaluation["coverage"],"per_class":evaluation["per_class"],
                                "logical_fit_seconds":sum(r["seconds"] for r in trial_rows),"compute_reused":False})
                            if route == "real":
                                shared_cell.mkdir(parents=True, exist_ok=True)
                                for artifact in ("complete.json", "test_predictions.npz", "pipeline.joblib", "trials.jsonl"):
                                    source = cell / artifact
                                    if source.exists(): shutil.copy2(source, shared_cell / artifact)
                except Exception as exc:
                    atomic_json(cell_base / "failure.json", {"status":"failed","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
        return cfg

    def run_e4(self, frame, split_col, repetitions=3, methods=None, resume=False,
               trials=10, seed=271828):
        """Run class-wise 0.5x/0.1x support reductions and restoration arms."""
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        import joblib
        frame = frame.reset_index(drop=True)
        generators = ["gmm", "copula", "arf", "kde", "chow_liu"]
        learners = ["logistic", "random_forest", "hist_gb"]
        methods = list(methods or METHODS)
        if repetitions != 3: raise ValueError("Experiment 4 is specified for three paired repetitions")
        split = frame[split_col].astype(str).str.lower()
        pool = np.flatnonzero(~split.eq("test").to_numpy()); test_pos = np.flatnonzero(split.eq("test").to_numpy())
        y = frame.label_id.to_numpy(dtype=np.int64); Xraw = frame[FEATURES].to_numpy(dtype=np.float64)
        Xtest_raw, ytest = Xraw[test_pos], y[test_pos]
        cfg = {"experiment":4,"budget":100_000,"roles":[80_000,10_000,10_000],"repetitions":repetitions,
               "class_ratios":[1.0,.5,.1],"direct_methods":methods,"restoration_learners":learners,
               "generators":generators,"treatments":["untreated","class_weight","random_oversample","smote","generated_restore"],
               "trials_per_cell":trials,"seed":seed,"workers":1,"resource_profile":self.resource_profile,
               "trial_timeout_seconds":self.trial_timeout,"memory_limit_gib":self.memory_limit_gib}
        atomic_json(self.output/"e4_run_config.json",cfg)
        for rep in range(repetitions):
            roles = sample_nested_roles(y,[100_000,E1_BUDGETS[-1]],seed+rep,pool_indices=pool)[100_000]
            tune_idx, cal_idx = roles.tune, roles.calibration
            excluded = set(tune_idx.tolist()+cal_idx.tolist())
            eligible = np.asarray([i for i in pool if i not in excluded],dtype=np.int64)
            yfit0=y[roles.fit]; counts0=np.bincount(yfit0,minlength=7); p0=counts0/counts0.sum()
            repdir=self.output/f"e4/rep_{rep+1}"; repdir.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(repdir/"role_membership.npz",fit_ids=frame.iloc[roles.fit].sample_id.to_numpy() if "sample_id" in frame else roles.fit,
                tuning_ids=frame.iloc[tune_idx].sample_id.to_numpy() if "sample_id" in frame else tune_idx,
                calibration_ids=frame.iloc[cal_idx].sample_id.to_numpy() if "sample_id" in frame else cal_idx)
            # Shared deterministic class-wise permutations let each target arm
            # draw nested target subsets and identical other-class prefixes.
            rng=np.random.default_rng(seed+rep); class_perm={}
            for c in range(7):
                candidates=eligible[y[eligible]==c]
                class_perm[c]=candidates[rng.permutation(len(candidates))]
            def condition_indices(target=None,ratio=1.0):
                N=80_000
                target_counts=counts0.copy()
                if target is not None:
                    desired=int(round(p0[target]*ratio*N))
                    target_counts[target]=desired
                    remain=N-desired; other=np.array([c for c in range(7) if c!=target])
                    weights=p0[other]/p0[other].sum(); raw=weights*remain
                    alloc=np.floor(raw).astype(int); residual=remain-int(alloc.sum())
                    alloc[np.argsort(-(raw-alloc),kind="stable")[:residual]]+=1
                    target_counts[other]=alloc
                # Cap to eligible class support and redistribute only if a
                # class pool is unexpectedly short; this is logged by counts.
                picked=[]
                for c in range(7):
                    n=int(target_counts[c])
                    if n>len(class_perm[c]): raise ValueError(f"class {c} lacks eligible rows for required E4 condition")
                    picked.extend(class_perm[c][:n].tolist())
                return np.asarray(picked,dtype=np.int64),target_counts
            # Repetition-level untouched control is shared across all class studies.
            control_idx=roles.fit
            conditions=[("control",None,1.0,control_idx,counts0)]
            for c in range(7):
                for ratio in (.5,.1):
                    ix,cc=condition_indices(c,ratio); conditions.append((f"class_{c}_ratio_{ratio:g}",c,ratio,ix,cc))
            for name,target,ratio,fit_idx,condition_counts in conditions:
                cond_dir=repdir/name; cond_dir.mkdir(parents=True,exist_ok=True)
                yfit=y[fit_idx]
                imp=SimpleImputer(strategy="median").fit(Xraw[fit_idx]); scaler=StandardScaler().fit(imp.transform(Xraw[fit_idx]))
                Xfit=scaler.transform(imp.transform(Xraw[fit_idx])).astype(np.float64)
                Xtune=scaler.transform(imp.transform(Xraw[tune_idx])).astype(np.float64)
                Xcal=scaler.transform(imp.transform(Xraw[cal_idx])).astype(np.float64)
                Xtest=scaler.transform(imp.transform(Xtest_raw)).astype(np.float64)
                atomic_json(cond_dir/"condition.json",{"target_class":target,"target_ratio":ratio,"fit_rows":len(fit_idx),
                    "counts":condition_counts.tolist(),"original_proportions":p0.tolist(),"role_counts":{"fit":len(fit_idx),"tune":len(tune_idx),"calibration":len(cal_idx)}})
                for method in methods:
                    cell=cond_dir/f"direct_{method}"
                    if resume and (cell/"complete.json").exists(): continue
                    try:
                        result=_tune_evaluate_cell(cell,method,Xfit,yfit,Xtune,y[tune_idx],Xcal,y[cal_idx],Xtest,ytest,
                            trials=5 if method in EXPENSIVE else trials,seed=seed+rep*10000+int((target or 0)*13)+len(method),
                            timeout=self.trial_timeout,prediction_chunk=self.prediction_chunk)
                        result.update(condition=name,target_class=target,target_ratio=ratio)
                        atomic_json(cell/"complete.json",result)
                    except Exception as exc:
                        atomic_json(cell/"failure.json",{"status":"failed","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
                if target is None: continue
                # Restoration targets the original target-class share; it does
                # not balance all seven classes.
                n=int(condition_counts[target]); N=len(fit_idx); p=float(p0[target])
                add=max(0,int(round((p*N-n)/(1-p)))) if p<1 else 0
                if add==0: continue
                base_X,base_y=Xfit,yfit
                for learner in learners:
                    # Untreated, weighting, ROS, and SMOTE arms use matching
                    # final histograms where rows are added.
                    arms=[]
                    arms.append(("untreated",base_X,base_y,None))
                    weights=np.array([p0[c]/max(np.mean(yfit==c),1e-12) for c in yfit],dtype=np.float64)
                    weights/=weights.mean(); arms.append(("class_weight",base_X,base_y,weights))
                    rg=np.random.default_rng(seed+rep*100000+target*100+int(ratio*10))
                    ro_idx=rg.choice(np.flatnonzero(yfit==target),size=add,replace=True)
                    arms.append(("random_oversample",np.vstack([base_X,base_X[ro_idx]]),np.r_[base_y,np.full(add,target)],None))
                    try:
                        if n<2: raise ValueError("SMOTE unsupported: fewer than two target-class examples")
                        from imblearn.over_sampling import SMOTE
                        sm=SMOTE(sampling_strategy={target:n+add},k_neighbors=min(5,n-1),random_state=seed+rep+target)
                        Xsm,ysm=sm.fit_resample(base_X,base_y)
                        arms.append(("smote",np.asarray(Xsm),np.asarray(ysm,dtype=np.int64),None))
                    except Exception as exc:
                        arms.append(("smote",None,None,None))
                        atomic_json(cond_dir/f"{learner}_smote_status.json",{"status":"unsupported","reason":str(exc)})
                    for generator in generators:
                        gen_name=f"generated_{generator}"
                        try:
                            cached=self.output/f"e1/rep_{rep+1}/n_100000/{generator}"
                            selected=json.loads((cached/"complete.json").read_text())["selected_params"]
                            genmod=_model_module(generator)
                            gen=genmod.make_model(generator,selected,seed+rep+target,n_jobs=1).fit(Xfit,yfit)
                            generated=gen.sample_class(target,add,seed+rep*10000+target*100+len(generator))
                            arms.append((gen_name,np.vstack([base_X,generated]),np.r_[base_y,np.full(add,target)],None))
                        except Exception as exc:
                            arms.append((gen_name,None,None,None))
                            atomic_json(cond_dir/f"{learner}_{gen_name}_status.json",{"status":"unsupported","reason":f"{type(exc).__name__}: {exc}"})
                    for arm_name,arm_X,arm_y,arm_w in arms:
                        if arm_X is None: continue
                        arm_cell=cond_dir/f"{learner}_{arm_name}"
                        if resume and (arm_cell/"complete.json").exists(): continue
                        try:
                            out=_tune_evaluate_cell(arm_cell,learner,arm_X,arm_y,Xtune,y[tune_idx],Xcal,y[cal_idx],Xtest,ytest,
                                sample_weight=arm_w,trials=trials,seed=seed+rep*10000+target*101+len(arm_name),
                                timeout=self.trial_timeout,prediction_chunk=self.prediction_chunk)
                            out.update(condition=name,target_class=target,target_ratio=ratio,treatment=arm_name,
                                final_rows=int(len(arm_y)),unique_real_rows=int(len(yfit)),added_target_rows=add)
                            atomic_json(arm_cell/"complete.json",out)
                        except Exception as exc:
                            atomic_json(arm_cell/"failure.json",{"status":"failed","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
        return cfg

    def run_e5(self, frame, split_col, repetitions=3, methods=None, resume=False,
               seed=271828):
        """Run frozen-configuration feature, missingness, and label corruption."""
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        import joblib
        generators=["gmm","copula","arf","kde","chow_liu"]
        learners=["logistic","random_forest","hist_gb"]
        methods=list(methods or METHODS)
        if repetitions!=3: raise ValueError("Experiment 5 is specified for three paired repetitions")
        split=frame[split_col].astype(str).str.lower()
        pool=np.flatnonzero(~split.eq("test").to_numpy()); test_pos=np.flatnonzero(split.eq("test").to_numpy())
        y=frame.label_id.to_numpy(dtype=np.int64); Xraw=frame[FEATURES].to_numpy(dtype=np.float64)
        Xtest_raw,ytest=Xraw[test_pos],y[test_pos]
        rates=[0,.05,.10,.20]
        cfg={"experiment":5,"budget":100000,"fit_rows":80000,"repetitions":repetitions,
            "corruptions":["feature_noise","missingness","label_noise"],"rates":rates,
            "direct_methods":methods,"generators":generators,"downstream_learners":learners,
            "route_methods":["direct_bayes","synthetic_only","real_only"],
            "hyperparameters":"frozen from clean E1/E3 selected configurations","seed":seed,
            "resource_profile":self.resource_profile,"workers":1,"trial_timeout_seconds":self.trial_timeout,
            "memory_limit_gib":self.memory_limit_gib}
        atomic_json(self.output/"e5_run_config.json",cfg)
        for rep in range(repetitions):
            roles=sample_nested_roles(y,[100_000,E1_BUDGETS[-1]],seed+rep,pool_indices=pool)[100_000]
            fit_idx,tune_idx,cal_idx=roles.fit,roles.tune,roles.calibration
            base_y=y[fit_idx].copy(); base_X=Xraw[fit_idx].copy()
            robust_scales=np.empty(len(FEATURES),dtype=np.float64)
            for f in range(len(FEATURES)):
                q25,q75=np.quantile(base_X[:,f],[.25,.75]); robust_scales[f]=(q75-q25)/1.349
                if robust_scales[f]<=0: robust_scales[f]=float(np.std(base_X[:,f]))
                if robust_scales[f]<=0: robust_scales[f]=1e-8
            Xtune_raw=Xraw[tune_idx]; Xcal_raw=Xraw[cal_idx]; Xtest_raw_rep=Xtest_raw
            repdir=self.output/f"e5/rep_{rep+1}"; repdir.mkdir(parents=True,exist_ok=True)
            if "sample_id" in frame:
                np.savez_compressed(repdir/"role_membership.npz",fit_ids=frame.iloc[fit_idx].sample_id.to_numpy(),
                    tuning_ids=frame.iloc[tune_idx].sample_id.to_numpy(),calibration_ids=frame.iloc[cal_idx].sample_id.to_numpy())
            rng=np.random.default_rng(seed+rep*1000)
            # Exact rate masks are prefixes of shared permutations for each
            # corruption family, making masks nested across the sweep.
            affected_order={kind:rng.permutation(len(fit_idx)) for kind in ("feature_noise","missingness","label_noise")}
            feature_choice=rng.integers(0,len(FEATURES),size=len(fit_idx))
            feature_delta=rng.normal(size=len(fit_idx))
            missing_choice=rng.integers(0,len(FEATURES),size=len(fit_idx))
            label_replacement=rng.integers(0,6,size=len(fit_idx))
            for corruption in ("feature_noise","missingness","label_noise"):
                for rate in rates:
                    nchange=int(round(rate*len(fit_idx)))
                    local_rows=affected_order[corruption][:nchange]
                    Xcor=base_X.copy(); ycor=base_y.copy()
                    changed_features=np.empty((nchange,2),dtype=np.int32); perturbations=np.empty(nchange,dtype=np.float64)
                    transitions=None
                    if corruption=="feature_noise" and nchange:
                        for j,row in enumerate(local_rows):
                            f=int(feature_choice[row]); delta=float(feature_delta[row]*robust_scales[f])
                            Xcor[row,f]+=delta; changed_features[j]=(int(row),f); perturbations[j]=delta
                    elif corruption=="missingness" and nchange:
                        for row in local_rows:
                            Xcor[row,int(missing_choice[row])]=np.nan
                    elif corruption=="label_noise" and nchange:
                        old=base_y[local_rows]
                        replacement=label_replacement[local_rows]
                        new=replacement+(replacement>=old)
                        ycor[local_rows]=new
                        transitions=np.zeros((7,7),dtype=np.int64)
                        for a,b in zip(old,new): transitions[int(a),int(b)]+=1
                    cellbase=repdir/corruption/f"rate_{int(round(rate*100)):02d}"
                    cellbase.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(cellbase/"corruption_audit.npz",changed_rows=local_rows.astype(np.int32),
                        changed_cells=changed_features if corruption=="feature_noise" else np.empty((0,2),dtype=np.int32),
                        perturbations=perturbations if corruption=="feature_noise" else np.empty(0),
                        missing_features=np.column_stack((local_rows,missing_choice[local_rows])).astype(np.int32) if corruption=="missingness" else np.empty((0,2),dtype=np.int32),
                        original_labels=base_y[local_rows] if corruption=="label_noise" else np.empty(0,dtype=np.int8),
                        corrupted_labels=ycor[local_rows] if corruption=="label_noise" else np.empty(0,dtype=np.int8),
                        transition_counts=transitions if transitions is not None else np.zeros((7,7),dtype=np.int64))
                    imp=SimpleImputer(strategy="median").fit(Xcor); scaler=StandardScaler().fit(imp.transform(Xcor))
                    Xfit=scaler.transform(imp.transform(Xcor)).astype(np.float64)
                    Xtune=scaler.transform(imp.transform(Xtune_raw)).astype(np.float64)
                    Xcal=scaler.transform(imp.transform(Xcal_raw)).astype(np.float64)
                    Xtest=scaler.transform(imp.transform(Xtest_raw_rep)).astype(np.float64)
                    atomic_json(cellbase/"condition.json",{"corruption":corruption,"rate":rate,"requested_rows":nchange,
                        "realized_rows":int(len(local_rows)),"fit_rows":len(fit_idx),"label_counts_original":np.bincount(base_y,minlength=7).tolist(),
                        "label_counts_corrupted":np.bincount(ycor,minlength=7).tolist(),"imputation":"training-only median",
                        "scaling":"training-only standard"})
                    if rate==0:
                        # Save the clean reference once so each corruption curve
                        # can compare against the same fitted pipeline.
                        pass
                    for method in methods:
                        base=self.output/f"e1/rep_{rep+1}/n_100000/{method}"
                        try:
                            selected=json.loads((base/"complete.json").read_text())["selected_params"]
                            result=_evaluate_fixed_config(cellbase/f"direct_{method}",method,selected,Xfit,ycor,Xcal,y[cal_idx],Xtest,ytest,
                                seed=seed+rep*100000+int(rate*1000)+len(method),prediction_chunk=self.prediction_chunk)
                            result.update(corruption=corruption,rate=rate,fit_label_counts=np.bincount(ycor,minlength=7).tolist())
                            atomic_json(cellbase/f"direct_{method}"/"complete.json",result)
                        except Exception as exc:
                            atomic_json(cellbase/f"direct_{method}"/"failure.json",{"status":"failed","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
                    for generator in generators:
                        try:
                            gbase=self.output/f"e1/rep_{rep+1}/n_100000/{generator}"
                            gparams=json.loads((gbase/"complete.json").read_text())["selected_params"]
                            gmod=_model_module(generator)
                            gen=gmod.make_model(generator,gparams,seed+rep*100000+int(rate*1000),n_jobs=1).fit(Xfit,ycor)
                            direct_scores=np.asarray(gen.score_matrix(Xtest),dtype=np.float32)
                            direct_cal=np.asarray(gen.score_matrix(Xcal),dtype=np.float32)
                            gkind=getattr(gen,"score_kind","probability")
                            from benchmark.evaluation import conformal_threshold,conformal_evaluate
                            q=conformal_threshold(direct_cal,y[cal_idx],gkind,.1)
                            ev=conformal_evaluate(direct_scores,ytest,q,gkind)
                            dcell=cellbase/f"routes/{generator}/direct_bayes"; dcell.mkdir(parents=True,exist_ok=True)
                            np.savez_compressed(dcell/"test_predictions.npz",y_pred=ev["predictions"].astype(np.int16),scores=direct_scores,
                                prediction_sets=ev["sets"].astype(np.uint8))
                            atomic_json(dcell/"complete.json",{"status":"complete","route":"direct_bayes","generator":generator,
                                "balanced_accuracy":ev["balanced_accuracy"],"set_size":ev["set_size"],"coverage":ev["coverage"],"per_class":ev["per_class"],
                                "fit_seconds":None,"compute_reused":False})
                            counts=np.bincount(ycor,minlength=7); synth_counts=counts*5
                            # Largest remainder to exactly 5x the real fit size.
                            ideal=counts.astype(float)*5; synth_counts=np.floor(ideal).astype(int)
                            rem=5*len(ycor)-int(synth_counts.sum()); synth_counts[np.argsort(-(ideal-synth_counts),kind="stable")[:rem]]+=1
                            sx=[];sy=[]
                            for c,n in enumerate(synth_counts):
                                if n:sx.append(gen.sample_class(c,int(n),seed+rep*100000+int(rate*1000)+c));sy.append(np.full(int(n),c,dtype=np.int64))
                            Xsyn=np.vstack(sx).astype(np.float64); ysyn=np.concatenate(sy)
                            for learner in learners:
                                for route,train_X,train_y,cache_route in (("synthetic_only",Xsyn,ysyn,"synthetic"),("real_only",Xfit,ycor,"real")):
                                    e3=self.output/f"e3/rep_{rep+1}/{generator}/{learner}_{cache_route}"
                                    params=json.loads((e3/"complete.json").read_text())["selected_params"]
                                    mod=importlib.import_module("benchmark.models_basic")
                                    clf=mod.make_model(learner,params,seed+rep*100000+int(rate*1000)+len(route),n_jobs=1).fit(train_X,train_y)
                                    _,cs=_predict_chunks(clf,Xcal,self.prediction_chunk); kind=getattr(clf,"score_kind","probability")
                                    cq=conformal_threshold(cs,y[cal_idx],kind,.1)
                                    pp,ss=_predict_chunks(clf,Xtest,self.prediction_chunk); route_eval=conformal_evaluate(ss,ytest,cq,kind)
                                    rcell=cellbase/f"routes/{generator}/{learner}_{route}"; rcell.mkdir(parents=True,exist_ok=True)
                                    np.savez_compressed(rcell/"test_predictions.npz",y_pred=pp.astype(np.int16),scores=ss.astype(np.float32),prediction_sets=route_eval["sets"].astype(np.uint8))
                                    atomic_json(rcell/"complete.json",{"status":"complete","route":route,"generator":generator,"learner":learner,
                                        "selected_params":params,"balanced_accuracy":route_eval["balanced_accuracy"],"set_size":route_eval["set_size"],
                                        "coverage":route_eval["coverage"],"per_class":route_eval["per_class"],"effective_fit_rows":len(train_y),
                                        "unique_real_fit_rows":len(ycor),"logical_fit_seconds":None,"compute_reused":False})
                        except Exception as exc:
                            atomic_json(cellbase/f"routes/{generator}/failure.json",{"status":"failed","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()})
        return cfg
