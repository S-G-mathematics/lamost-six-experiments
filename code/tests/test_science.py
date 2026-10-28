import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source"))
import science


def test_largest_remainder_is_exact_and_deterministic():
    a = science._alloc([10, 20, 30, 40, 10, 20, 30], 101)
    b = science._alloc([10, 20, 30, 40, 10, 20, 30], 101)
    assert a.sum() == 101
    assert np.array_equal(a, b)
    assert np.all(a >= 0)


def test_setmask_one_byte_roundtrip():
    sets = np.array([[1, 0, 1, 0, 0, 1, 1], [0, 1, 0, 0, 1, 0, 0]], dtype=bool)
    packed = np.packbits(sets, axis=1, bitorder="little")[:, 0]
    unpacked = np.unpackbits(packed[:, None], axis=1, bitorder="little")[:, :7]
    assert np.array_equal(unpacked.astype(bool), sets)


def test_gmm_fit_eval_generate_small_fixture(tmp_path):
    rng = np.random.default_rng(1207)
    runtime = tmp_path / "runtime"
    (runtime / "cache" / "roles").mkdir(parents=True)
    rows = []
    labels = []
    for c in range(7):
        rows.append(rng.normal(c * 1.3, 0.6, size=(12, 6)))
        labels.append(np.full(12, c, dtype=np.int8))
    X = np.vstack(rows)
    y = np.concatenate(labels)
    fit_idx = np.concatenate([np.arange(c * 12, c * 12 + 8) for c in range(7)])
    tune_idx = np.concatenate([np.arange(c * 12 + 8, c * 12 + 10) for c in range(7)])
    cal_idx = np.concatenate([np.arange(c * 12 + 10, c * 12 + 11) for c in range(7)])
    test_idx = np.concatenate([np.arange(c * 12 + 11, c * 12 + 12) for c in range(7)])
    X[fit_idx[0], 0] = np.nan  # Missingness is valid fitting input; median is fit-only.
    np.savez(runtime / "cache" / "roles" / "rep_0.npz",
             X_fit=X[fit_idx], y_fit=y[fit_idx], fit_ids=fit_idx,
             X_tune=X[tune_idx], y_tune=y[tune_idx], tuning_ids=tune_idx,
             X_cal=X[cal_idx], y_cal=y[cal_idx], calibration_ids=cal_idx)
    np.savez(runtime / "cache" / "test.npz", X=X[test_idx], y=y[test_idx], ids=test_idx)
    selected = tmp_path / "selection"
    selected.mkdir()
    (selected / "selection.json").write_text(json.dumps({
        "selected_params": {"n_components": 1, "covariance_type": "diag", "reg_covar": 1e-3}
    }))
    fit = science.execute({
        "key": "fixture/gmm", "kind": "fit", "experiment": "fixture", "rep": 0,
        "method": "gmm", "seed": 4, "selection_source": str(selected)
    }, runtime)
    assert fit["status"] == "successful", fit
    assert (runtime / "artifacts" / "fixture" / "gmm" / "pipeline.joblib").is_file()
    ev = science.execute({
        "key": "fixture/eval", "kind": "eval", "experiment": "fixture", "rep": 0,
        "fit_key": "fixture/gmm"
    }, runtime)
    assert ev["status"] == "successful", ev
    result = ev["result"]
    assert 0 <= result["balanced_accuracy"] <= 1
    assert len(result["per_class"]) == 7
    assert (runtime / "artifacts" / "fixture" / "eval" / "test_outcomes.npz").is_file()
    gen = science.execute({
        "key": "fixture/gen", "kind": "generate", "experiment": "fixture",
        "fit_key": "fixture/gmm", "n_rows": 31, "target_class": None, "generation_seed": 991
    }, runtime)
    assert gen["status"] == "successful", gen
    with np.load(runtime / "artifacts" / "fixture" / "gen" / "data.npz") as d:
        assert d["X"].shape == (31, 6)
        assert d["X"].dtype == np.float64
        assert d["y"].dtype == np.int8
        assert np.bincount(d["y"], minlength=7).sum() == 31

def test_optuna_trial_dispatch_completes(tmp_path):
    rng = np.random.default_rng(42)
    runtime = tmp_path / "runtime_tune"
    (runtime / "cache" / "roles").mkdir(parents=True)
    Xfit=[]; yfit=[]; Xtune=[]; ytune=[]; Xcal=[]; ycal=[]
    for c in range(7):
        Xfit.append(rng.normal(c, .4, size=(8, 6))); yfit.extend([c]*8)
        Xtune.append(rng.normal(c, .4, size=(2, 6))); ytune.extend([c]*2)
        Xcal.append(rng.normal(c, .4, size=(2, 6))); ycal.extend([c]*2)
    Xf=np.vstack(Xfit); Xtu=np.vstack(Xtune); Xc=np.vstack(Xcal)
    np.savez(runtime / "cache" / "roles" / "rep_0.npz",
             X_fit=Xf,y_fit=np.asarray(yfit,dtype=np.int8),fit_ids=np.arange(len(yfit)),
             X_tune=Xtu,y_tune=np.asarray(ytune,dtype=np.int8),tuning_ids=np.arange(len(ytune)),
             X_cal=Xc,y_cal=np.asarray(ycal,dtype=np.int8),calibration_ids=np.arange(len(ycal)))
    result=science.execute({"key":"tune/logistic","kind":"fit","experiment":"fixture","rep":0,
                            "method":"logistic","seed":3,"optimizer_seed":7,"trials":1},runtime)
    assert result["status"]=="successful", result
    taskdir=runtime/"artifacts"/"tune"/"logistic"/"checkpoints"
    ledgers=list(taskdir.rglob("trial_history.json"))
    assert len(ledgers)==1
    with ledgers[0].open() as f: history=json.load(f)
    assert len(history)==1 and history[0]["status"] in {"success","duplicate_cached"}
    assert list(taskdir.rglob("optuna.sqlite3"))


def test_interrupted_optuna_trial_resumes_same_slot(tmp_path, monkeypatch):
    rng=np.random.default_rng(88)
    runtime=tmp_path/"resume_runtime"; roles=runtime/"cache"/"roles"; roles.mkdir(parents=True)
    xs=[]; ys=[]; xt=[]; yt=[]; xc=[]; yc=[]
    for c in range(7):
        xs.append(rng.normal(c,.5,(8,6))); ys.extend([c]*8)
        xt.append(rng.normal(c,.5,(2,6))); yt.extend([c]*2)
        xc.append(rng.normal(c,.5,(2,6))); yc.extend([c]*2)
    Xf=np.vstack(xs); Xu=np.vstack(xt); Xc=np.vstack(xc)
    np.savez(roles/"rep_0.npz",X_fit=Xf,y_fit=np.asarray(ys,dtype=np.int8),fit_ids=np.arange(len(ys)),
        X_tune=Xu,y_tune=np.asarray(yt,dtype=np.int8),tuning_ids=np.arange(len(yt)),
        X_cal=Xc,y_cal=np.asarray(yc,dtype=np.int8),calibration_ids=np.arange(len(yc)))
    task={"key":"resume/logistic","kind":"fit","experiment":"fixture","rep":0,
          "method":"logistic","seed":17,"optimizer_seed":19,"trials":1}
    original=science._run_phase
    def interrupted(runtime_arg,task_arg,phase,out,params=None,**kwargs):
        if phase.startswith("trial_"):
            raise science.PhaseExecutionError("operationally_interrupted","fixture phase interruption")
        return original(runtime_arg,task_arg,phase,out,params=params,**kwargs)
    monkeypatch.setattr(science,"_run_phase",interrupted)
    stopped=science.execute(task,runtime)
    assert stopped["status"]=="operationally_interrupted"
    monkeypatch.setattr(science,"_run_phase",original)
    resumed=science.execute(task,runtime)
    assert resumed["status"]=="successful", resumed
    ledger=list((runtime/"artifacts"/"resume"/"logistic"/"checkpoints").rglob("trial_history.json"))[0]
    history=json.loads(ledger.read_text())
    assert len(history)==1 and history[0]["number"]==0 and history[0]["status"]=="success"

