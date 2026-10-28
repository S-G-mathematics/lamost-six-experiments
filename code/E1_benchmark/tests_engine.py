import pytest

from benchmark.engine import (ExperimentRunner, METHODS, E1_BUDGETS, _score_metrics,
                              _timeout, _clear_timeout, _canonical_frame)
from benchmark.run_e1_sequential import (cell_timeout_seconds, planned_cells,
                                         should_skip_cell, _freeze_master,
                                         _master_config, build_parser,
                                         heartbeat_timed_out)
from benchmark.sampling import sample_nested_roles


def test_e1_protocol_grid_and_method_count():
    assert E1_BUDGETS == [100, 300, 1_000, 3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000]
    assert len(METHODS) == 17 and len(set(METHODS)) == 17


def test_balanced_accuracy_is_mean_class_recall():
    y = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    pred = [0, 1, 1, 1, 2, 0, 3, 3, 4, 0, 5, 5, 6, 0]
    got = _score_metrics(__import__("numpy").asarray(y), __import__("numpy").asarray(pred))
    assert got["balanced_accuracy"] == pytest.approx((.5 + 1 + .5 + 1 + .5 + 1 + .5) / 7)


def test_runner_refuses_parallel_workers():
    with pytest.raises(ValueError, match="sequential"):
        ExperimentRunner("/tmp/lamost-test", workers=2)


def test_timeout_cleanup_accepts_signal_module_token():
    token, exception_type = _timeout(2)
    assert token is not None and issubclass(exception_type, TimeoutError)
    _clear_timeout(token)


def test_canonical_source_order_ignores_parquet_scan_order():
    pd = pytest.importorskip("pandas")
    first = pd.DataFrame({"sample_id": ["c", "a", "b"], "value": [3, 1, 2]})
    second = first.iloc[[2, 0, 1]].reset_index(drop=True)
    assert _canonical_frame(first).equals(_canonical_frame(second))


def test_supervisor_wall_cap_covers_trials_and_selected_stages():
    assert cell_timeout_seconds(5, 180) == 5 * 210 + 4 * 180 + 180
    assert cell_timeout_seconds(10, 180) > cell_timeout_seconds(5, 180)


def test_supervisor_ignores_stale_heartbeat_but_detects_live_stall():
    stale = {"status": "started", "epoch_seconds": 90}
    live = {"status": "started", "epoch_seconds": 101, "phase": "trial_0"}
    assert not heartbeat_timed_out(stale, child_started_epoch=100, timeout_seconds=10,
                                   grace_seconds=2, now=200)
    assert heartbeat_timed_out(live, child_started_epoch=100, timeout_seconds=10,
                               grace_seconds=2, now=114)


def test_supervisor_orders_budget_then_repetition_then_method():
    assert planned_cells([100, 300], 2, ["a", "b"]) == [
        (100, 0, "a"), (100, 0, "b"), (100, 1, "a"), (100, 1, "b"),
        (300, 0, "a"), (300, 0, "b"), (300, 1, "a"), (300, 1, "b"),
    ]


def test_supervisor_skips_terminal_failure_and_master_config_is_immutable(tmp_path):
    assert should_skip_cell(False, "terminal_failure")
    assert not should_skip_cell(False, "terminal_failure", retry_failed=True)
    assert should_skip_cell(True, "terminal_failure", retry_failed=True)
    cfg = {"seed": 1}
    _freeze_master(tmp_path, cfg, resume=False)
    with pytest.raises(RuntimeError, match="immutable"):
        _freeze_master(tmp_path, {"seed": 2}, resume=True)
    _freeze_master(tmp_path, cfg, resume=True)


def test_master_provenance_freezes_sources_dependencies_trials_and_threshold(tmp_path):
    import json
    base = tmp_path / "base"
    base.mkdir()
    (base / "manifest.json").write_text(json.dumps({"files": {}, "release": "fixture"}))
    args = build_parser().parse_args(["--baseline-dir", str(base), "--methods", "arf,gaussian_nb"])
    config = _master_config(args)
    assert "engine.py" in config["benchmark_python_source_sha256"]
    assert config["dependency_freeze_sha256"]
    assert config["per_method_trial_counts"] == {"arf": 5, "gaussian_nb": 10}
    assert config["practical_improvement_threshold_percentage_points"] == 0.2


def test_small_nonpilot_runner_completes_and_evaluates_test_after_selection(tmp_path):
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    pytest.importorskip("sklearn")
    pytest.importorskip("optuna")
    import resource
    previous_limit = resource.getrlimit(resource.RLIMIT_AS)
    rng = np.random.default_rng(7)
    rows = []
    for partition, n in (("development", 140), ("test", 70)):
        labels = np.tile(np.arange(7), n // 7)
        values = rng.normal(size=(n, 6))
        for i, label in enumerate(labels):
            row = {"sample_id": f"{partition}-{i}", "label_id": int(label), "partition": partition}
            row.update(dict(zip(("mag_ps_g", "mag_ps_r", "mag_ps_i", "mag_ps_z", "mag_ps_y", "gaia_g_mean_mag"), values[i])))
            rows.append(row)
    out = tmp_path / "pilot"
    try:
        runner = ExperimentRunner(out, trial_timeout=30, prediction_chunk=20, memory_limit_gib=5.5)
        runner.run_e1(pd.DataFrame(rows), "partition", budgets=[100], repetitions=1,
                      methods=["gaussian_nb"], pilot=False, n_trials=2, seed=77, rep_start=2)
    finally:
        resource.setrlimit(resource.RLIMIT_AS, previous_limit)
    cell = out / "e1/rep_3/n_100/gaussian_nb"
    assert (cell / "complete.json").exists()
    assert (cell / "test_predictions.npz").exists()
    result = __import__("json").loads((cell / "complete.json").read_text())
    assert 0 <= result["test_metrics"]["balanced_accuracy"] <= 1
    assert result["test_coverage"] is not None
    assert (out / "e1_run_summary.json").exists()
    manifest = __import__("json").loads((cell / "manifest.json").read_text())
    roles = __import__("numpy").load(cell / "role_positions.npz")
    assert manifest["seed"] == 79
    assert len(roles["fit"]) + len(roles["tuning"]) + len(roles["calibration"]) == 100
    canonical = pd.DataFrame(rows).sort_values("sample_id", kind="mergesort").reset_index(drop=True)
    y = canonical.label_id.to_numpy()
    pool = np.flatnonzero(canonical.partition.to_numpy() != "test")
    expected = sample_nested_roles(y, [100, E1_BUDGETS[-1]], 79, pool_indices=pool)[100]
    assert np.array_equal(roles["fit"], expected.fit)
    assert np.array_equal(roles["tuning"], expected.tune)
    assert np.array_equal(roles["calibration"], expected.calibration)
