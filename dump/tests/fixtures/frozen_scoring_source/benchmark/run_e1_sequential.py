"""Run E1 as isolated, checkpointed method cells under per-cell wall limits.

This supervisor intentionally launches one benchmark cell per child process so
native-library hangs and process-wide memory caps cannot stop later cells.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from benchmark.engine import E1_BUDGETS, EXPENSIVE, METHODS, atomic_json, sha256_file


def _ints(text):
    try:
        return [int(x.strip().replace("_", "")) for x in text.split(",") if x.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc


def _strings(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def build_parser():
    p = argparse.ArgumentParser(description="Run E1 in sequential, resource-capped subprocess cells.")
    p.add_argument("--output", type=Path, default=Path("benchmark/results"))
    p.add_argument("--baseline-dir", type=Path, default=Path("lamost_baseline"))
    p.add_argument("--budgets", type=_ints, default=E1_BUDGETS)
    p.add_argument("--repetitions", type=int, default=5)
    p.add_argument("--methods", type=_strings, default=METHODS)
    p.add_argument("--seed", type=int, default=271828)
    p.add_argument("--trial-timeout", type=int, default=1800,
                   help="soft in-process timeout; heartbeat watchdog hard-kills a stalled phase after timeout plus grace")
    p.add_argument("--phase-timeout-grace", type=int, default=30,
                   help="hard-kill a child after its heartbeat phase exceeds trial timeout plus this grace")
    p.add_argument("--memory-limit-gib", type=float, default=6.0)
    p.add_argument("--prediction-chunk", type=int, default=50_000)
    p.add_argument("--resource-profile", default="native8gib8cores")
    p.add_argument("--trials", type=int, default=None, help="override per-method trial count for development")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--retry-failed", action="store_true", help="retry cells recorded as terminal failures")
    p.add_argument("--dry-run", action="store_true", help="write/freeze master config and print ordered cells")
    return p


def cell_timeout_seconds(trials: int, trial_timeout: int) -> int:
    """Allow all bounded trial stages plus selected refit and held-out scoring."""
    # Each candidate covers fit + tuning inference. The selected model has a
    # separate refit, selected-tuning diagnostic, calibration, and test call.
    return int(trials * (trial_timeout + 30) + 4 * trial_timeout + 180)


def planned_cells(budgets, repetitions, methods):
    return [(budget, rep, method) for budget in budgets
            for rep in range(repetitions) for method in methods]


def should_skip_cell(complete_exists, prior_status, retry_failed=False):
    return bool(complete_exists or (prior_status == "terminal_failure" and not retry_failed))


def heartbeat_timed_out(heartbeat, child_started_epoch, timeout_seconds, grace_seconds, now=None):
    """Ignore old child heartbeats and detect only a live, over-age phase."""
    if heartbeat.get("status") != "started":
        return False
    epoch = float(heartbeat.get("epoch_seconds", 0))
    if epoch < float(child_started_epoch):
        return False
    now = time.time() if now is None else float(now)
    return now - epoch > int(timeout_seconds) + int(grace_seconds)


def _master_config(args):
    base = args.baseline_dir.resolve()
    manifest = json.loads((base / "manifest.json").read_text())
    bench_dir = Path(__file__).resolve().parent
    source_hashes = {p.name: sha256_file(p) for p in sorted(bench_dir.glob("*.py"))}
    freeze_path = bench_dir / "dependencies.freeze.txt"
    dependency_freeze = [line.strip() for line in freeze_path.read_text().splitlines() if line.strip()]
    per_method_trials = {method: int(args.trials or (5 if method in EXPENSIVE else 10))
                         for method in args.methods}
    cfg = {
        "experiment": 1,
        "protocol_sha256": sha256_file(Path(__file__).with_name("protocol_source.txt")),
        "benchmark_python_source_sha256": source_hashes,
        "dependency_freeze_file": freeze_path.name,
        "dependency_freeze_sha256": sha256_file(freeze_path),
        "dependency_freeze": dependency_freeze,
        "baseline_manifest_sha256": sha256_file(base / "manifest.json"),
        "budgets": args.budgets,
        "repetitions": args.repetitions,
        "methods": args.methods,
        "trials_override": args.trials,
        "per_method_trial_counts": per_method_trials,
        "practical_improvement_threshold_percentage_points": 0.2,
        "seed": args.seed,
        "trial_timeout_seconds": args.trial_timeout,
        "phase_timeout_grace_seconds": args.phase_timeout_grace,
        "memory_limit_gib": args.memory_limit_gib,
        "resource_profile": args.resource_profile,
        "prediction_chunk_rows": args.prediction_chunk,
        "workers": 1,
        "model_n_jobs": 1,
        "baseline_release": manifest.get("release", manifest.get("version")),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return cfg


def _freeze_master(output: Path, cfg, resume):
    path = output / "master_run_config.json"
    output.mkdir(parents=True, exist_ok=True)
    if path.exists():
        previous = json.loads(path.read_text())
        comparable = {k: v for k, v in previous.items() if k != "created_utc"}
        current = {k: v for k, v in cfg.items() if k != "created_utc"}
        if comparable != current:
            raise RuntimeError("master run config is immutable; requested settings do not match the existing run")
        if not resume:
            raise RuntimeError("master run config already exists; pass --resume to continue it")
    else:
        atomic_json(path, cfg)
    return path


def _kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def run(args):
    if args.repetitions < 1 or args.trial_timeout < 1 or args.phase_timeout_grace < 1 or args.memory_limit_gib <= 0:
        raise ValueError("repetitions, timeout, and memory limit must be positive")
    if args.budgets != sorted(set(args.budgets)) or any(n not in E1_BUDGETS for n in args.budgets):
        raise ValueError(f"budgets must be a unique ascending subset of {E1_BUDGETS}")
    if len(set(args.methods)) != len(args.methods) or any(m not in METHODS for m in args.methods):
        raise ValueError("methods must be unique known E1 methods")
    if not args.methods:
        raise ValueError("at least one method is required")
    _freeze_master(args.output, _master_config(args), args.resume)
    state_path = args.output / "supervisor_state.json"
    state = json.loads(state_path.read_text()) if args.resume and state_path.exists() else {"cells": {}}
    def _stop_on_term(_sig, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _stop_on_term)
    cells = planned_cells(args.budgets, args.repetitions, args.methods)
    if args.dry_run:
        for budget, rep, method in cells:
            trials = args.trials or (5 if method in EXPENSIVE else 10)
            print(json.dumps({"budget": budget, "repetition": rep + 1, "method": method,
                              "trials": trials, "wall_timeout_seconds": cell_timeout_seconds(trials, args.trial_timeout)}))
        return 0

    for budget, rep, method in cells:
        key = f"n_{budget}/rep_{rep + 1}/{method}"
        cell_dir = args.output / "e1" / f"rep_{rep + 1}" / f"n_{budget}" / method
        complete = cell_dir / "complete.json"
        old = state["cells"].get(key, {})
        if complete.exists():
            old.update(status="complete", skipped=True)
            state["cells"][key] = old
            continue
        if should_skip_cell(complete.exists(), old.get("status"), args.retry_failed):
            continue

        trials = args.trials or (5 if method in EXPENSIVE else 10)
        wall_timeout = cell_timeout_seconds(trials, args.trial_timeout)
        cell_dir.mkdir(parents=True, exist_ok=True)
        log = cell_dir / "supervisor.log"
        invocation = [sys.executable, "-m", "benchmark.experiments", "--experiment", "1",
                      "--output", str(args.output.resolve()), "--baseline-dir", str(args.baseline_dir.resolve()),
                      "--budgets", str(budget), "--repetitions", "1", "--rep-start", str(rep),
                      "--methods", method, "--seed", str(args.seed), "--trial-timeout", str(args.trial_timeout),
                      "--memory-limit-gib", str(args.memory_limit_gib), "--resource-profile", args.resource_profile,
                      "--prediction-chunk", str(args.prediction_chunk), "--resume"]
        if args.trials is not None:
            invocation.extend(("--trials", str(args.trials)))
        started = time.time()
        status = "crashed"
        returncode = None
        timed_out = False
        phase_timeout = False
        timed_out_phase = None
        with log.open("ab", buffering=0) as out:
            out.write((f"\n[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] START {json.dumps(invocation)}\n").encode())
            proc = subprocess.Popen(invocation, stdout=out, stderr=subprocess.STDOUT,
                                    start_new_session=True, cwd=Path(__file__).resolve().parents[1])
            deadline = time.monotonic() + wall_timeout
            try:
                while proc.poll() is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        _kill_group(proc)
                        break
                    heartbeat_path = cell_dir / "heartbeat.json"
                    try:
                        heartbeat = json.loads(heartbeat_path.read_text())
                        if heartbeat_timed_out(heartbeat, started, args.trial_timeout,
                                               args.phase_timeout_grace):
                            timed_out = True
                            phase_timeout = True
                            timed_out_phase = heartbeat.get("phase")
                            _kill_group(proc)
                            break
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                    try:
                        proc.wait(timeout=min(1.0, remaining))
                    except subprocess.TimeoutExpired:
                        continue
                returncode = proc.returncode
            except KeyboardInterrupt:
                _kill_group(proc)
                returncode = proc.returncode
                status = "interrupted"
            if complete.exists():
                status = "complete"
            elif status == "interrupted":
                pass
            elif timed_out:
                status = "terminal_failure"
            elif returncode != 0:
                status = "terminal_failure"
            else:
                status = "terminal_failure"
            out.write((f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] END status={status} "
                       f"returncode={returncode} timed_out={timed_out} phase_timeout={phase_timeout} "
                       f"phase={timed_out_phase} elapsed={time.time()-started:.1f}s\n").encode())
        row = {"status": status, "returncode": returncode, "timed_out": timed_out,
               "phase_timeout": phase_timeout, "timed_out_phase": timed_out_phase,
               "started_epoch": started, "elapsed_seconds": time.time() - started,
               "wall_timeout_seconds": wall_timeout, "trial_timeout_seconds": args.trial_timeout,
               "trials": trials, "log": str(log.relative_to(args.output)), "invocation": invocation}
        state["cells"][key] = row
        atomic_json(state_path, state)
        if status == "interrupted":
            break
    failed = [k for k, v in state["cells"].items() if v.get("status") == "terminal_failure"]
    complete_n = sum(1 for k in [f"n_{b}/rep_{r+1}/{m}" for b, r, m in cells]
                     if (args.output / "e1" / f"rep_{int(k.split('/')[1].split('_')[1])}" / k.split('/')[0] / k.split('/')[2] / "complete.json").exists())
    summary = {"scheduled_cells": len(cells), "complete_cells": complete_n,
               "terminal_failure_cells": len(failed), "failed_keys": failed}
    atomic_json(args.output / "supervisor_summary.json", summary)
    return 1 if failed else 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        print(f"E1 supervisor error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
