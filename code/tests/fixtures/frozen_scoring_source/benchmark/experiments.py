"""CLI entry point for sequential checkpointed benchmark experiments."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from benchmark.engine import E1_BUDGETS, METHODS, ExperimentRunner, load_data, validate_manifest


def _ints(text):
    try: return [int(x.strip().replace("_", "")) for x in text.split(",") if x.strip()]
    except ValueError as exc: raise argparse.ArgumentTypeError("expected comma-separated integers") from exc


def build_parser():
    p = argparse.ArgumentParser(description="Run checkpointed LAMOST benchmark cells sequentially.")
    p.add_argument("--experiment", choices=("1", "3", "4", "5"), required=True)
    p.add_argument("--output", type=Path, default=Path("benchmark/results"))
    p.add_argument("--baseline-dir", type=Path, default=Path("lamost_baseline"))
    p.add_argument("--budgets", type=_ints, default=None, help="comma-separated development sizes")
    p.add_argument("--repetitions", type=int, default=None)
    p.add_argument("--methods", type=lambda s: [x.strip() for x in s.split(",") if x.strip()], default=None)
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--trial-timeout", type=int, default=1800,
                   help="soft per-candidate fit/predict timeout in seconds; native calls are hard-capped by the supervisor")
    p.add_argument("--memory-limit-gib", type=float, default=6.0, help="hard RLIMIT_AS virtual-memory headroom above process startup; RSS is also logged")
    p.add_argument("--resource-profile", default="native8gib8cores")
    p.add_argument("--prediction-chunk", type=int, default=50_000)
    p.add_argument("--trials", type=int, default=None)
    p.add_argument("--seed", type=int, default=271828)
    p.add_argument("--rep-start", type=int, default=0, help="zero-based first repetition (for sequential cell orchestration)")
    p.add_argument("--resume", action="store_true")
    p.add_argument("--pilot", action="store_true", help="development-only compatibility/runtime pilot; never computes test outcomes")
    p.add_argument("--verify-manifest", action="store_true", help="verify baseline release checksums before running")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.workers != 1:
        raise SystemExit("The experiment protocol is sequential; pass --workers 1")
    if args.pilot and args.experiment != "1":
        raise SystemExit("--pilot is currently limited to Experiment 1 compatibility cells")
    # The frozen baseline is an input contract, so checksums are always
    # verified before any experiment or pilot cell can start.
    validate_manifest(args.baseline_dir)
    frame, split_col = load_data(args.baseline_dir, include_test=not args.pilot)
    defaults = {"1": (E1_BUDGETS, 5), "3": ([100_000], 3), "4": ([100_000], 3), "5": ([100_000], 3)}
    budgets_default, reps_default = defaults[args.experiment]
    budgets = args.budgets or budgets_default
    repetitions = args.repetitions or reps_default
    runner = ExperimentRunner(args.output, workers=args.workers, trial_timeout=args.trial_timeout,
                              prediction_chunk=args.prediction_chunk, memory_limit_gib=args.memory_limit_gib,
                              resource_profile=args.resource_profile)
    if args.experiment == "1":
        runner.run_e1(frame, split_col, budgets=budgets, repetitions=repetitions,
                      methods=args.methods or METHODS, resume=args.resume, pilot=args.pilot,
                      n_trials=args.trials, seed=args.seed, rep_start=args.rep_start)
    elif args.experiment == "3":
        runner.run_e3(frame, split_col, repetitions=repetitions, methods=args.methods,
                      resume=args.resume, trials=args.trials or 10, seed=args.seed)
    elif args.experiment == "4":
        runner.run_e4(frame, split_col, repetitions=repetitions, methods=args.methods,
                      resume=args.resume, trials=args.trials or 10, seed=args.seed)
    elif args.experiment == "5":
        runner.run_e5(frame, split_col, repetitions=repetitions, methods=args.methods,
                      resume=args.resume, seed=args.seed)
    else:
        raise SystemExit(f"Experiment {args.experiment} runner is being added; E1 is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
