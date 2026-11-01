"""Benchmark the oracle backends on N replays of the example exercises.

Backends compared:

- ``subprocess``: one ``nvim -l oracle.lua`` process per exercise.
- ``batch``: one ``nvim -l oracle.lua`` process for all N exercises.
- ``pynvim``: one long-lived embedded Neovim over RPC (startup reported separately).

Examples
--------
$ uv run vimtrainer-bench examples/*.json -n 50
"""

import argparse
import itertools
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

from vimtrainer_content import oracle


@dataclass(frozen=True)
class Timing:
    """Wall time of one backend over N jobs."""

    backend: str
    jobs: int
    total_ms: float
    startup_ms: float
    passed: int

    @property
    def per_job_ms(self) -> float:
        """Mean wall time per job, startup included."""
        return self.total_ms / self.jobs


# Public Functions =================================================================================


def bench(exercises: Sequence[oracle.Exercise], n: int = 50) -> list[Timing]:
    """Replay the canonical solutions of ``exercises`` cyclically ``n`` times per backend."""
    jobs = [(ex, ex["par"]["keys"]) for ex in itertools.islice(itertools.cycle(exercises), n)]
    return [_bench_subprocess(jobs), _bench_batch(jobs), _bench_pynvim(jobs)]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; prints one row per backend (median of ``--trials`` runs)."""
    parser = argparse.ArgumentParser(prog="vimtrainer-bench", description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("-n", type=int, default=50, help="jobs per backend")
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args(argv)
    exercises = [oracle.load_exercise(p) for p in args.files]
    trials = [bench(exercises, args.n) for _ in range(args.trials)]
    print(f"nvim {oracle.nvim_version()}, {args.n} jobs per backend, median of {args.trials} trials")
    print(f"{'backend':<11} {'total ms':>9} {'per job ms':>11} {'startup ms':>11} {'passed':>7}")
    for rows in zip(*trials):
        total = statistics.median(r.total_ms for r in rows)
        startup = statistics.median(r.startup_ms for r in rows)
        r = rows[0]
        print(f"{r.backend:<11} {total:>9.1f} {total / r.jobs:>11.2f} {startup:>11.1f} {r.passed:>4}/{r.jobs}")
    return 0


# Private Functions ================================================================================


def _bench_subprocess(jobs: Sequence[oracle.Job]) -> Timing:
    runner = oracle.subprocess_runner()
    start = time.perf_counter()
    verdicts = [oracle.verify(ex, k, runner) for ex, k in jobs]
    return Timing("subprocess", len(jobs), _since(start), 0.0, sum(v.passed for v in verdicts))


def _bench_batch(jobs: Sequence[oracle.Job]) -> Timing:
    start = time.perf_counter()
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    return Timing("batch", len(jobs), _since(start), 0.0, sum(v.passed for v in verdicts))


def _bench_pynvim(jobs: Sequence[oracle.Job]) -> Timing:
    start = time.perf_counter()
    with oracle.PynvimSession() as session:
        startup = _since(start)
        verdicts = [oracle.verify(ex, k, session.run) for ex, k in jobs]
        total = _since(start)
    return Timing("pynvim", len(jobs), total, startup, sum(v.passed for v in verdicts))


def _since(start: float) -> float:
    return (time.perf_counter() - start) * 1000


if __name__ == "__main__":
    sys.exit(main())
