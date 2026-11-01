"""Neovim par oracle: replay keystrokes on an exercise in headless Neovim and grade them.

The Lua side (``oracle.lua``) loads ``start.lines``, places the cursor, feeds the keys with
``nvim_feedkeys(keys, "mtx")`` and reports the buffer, cursor, mode and whether a ``:``
command line was entered. This module drives it and grades the outcome per exercise kind.

Neovim is started as ``nvim --headless --clean -u NONE``. ``oracle.lua`` then applies the
documented option set ``ORACLE_OPTIONS`` on top of the filetype plugin for ``lang``:
``number relativenumber expandtab shiftwidth=4 tabstop=4 softtabstop=0 autoindent nowrap``.
The filetype's ``indentexpr`` and ``commentstring`` stay active, so ``o`` indents like
real Neovim and ``gcc`` uses the language comment leader. Default mappings are used
(remap on), because ``gc``/``gcc`` and ``Y`` are default mappings in Neovim 0.10+.

Three backends exist:

- ``subprocess`` per exercise: one ``nvim -l oracle.lua`` per job. Simplest, isolated.
- ``batch``: one ``nvim -l oracle.lua`` process replays a list of jobs.
- ``pynvim``: one long-lived ``nvim --embed`` driven over msgpack-RPC.

Examples
--------
>>> ex = load_exercise("examples/py_t.quote_0001.json")
>>> verdict = verify(ex)
>>> verdict.passed, verdict.count
(True, 15)
"""

import argparse
import datetime
import functools
import importlib.resources
import json
import logging
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Self

import pynvim

ORACLE_LUA: Final = pathlib.Path(str(importlib.resources.files("vimtrainer_content") / "oracle.lua"))
NVIM_BASE_ARGS: Final = ("--headless", "--clean", "-u", "NONE")
MARKER: Final = "@@ORACLE "
DEFAULT_TIMEOUT_S: Final = 10.0
ORACLE_OPTIONS: Final = (
    "number relativenumber expandtab shiftwidth=4 tabstop=4 softtabstop=0 autoindent nowrap"
)

_KEY_NAMES: Final = (
    "Esc|CR|Enter|Return|NL|BS|Tab|Space|lt|Bar|Bslash|Del|Insert|Home|End|PageUp|PageDown"
    "|Up|Down|Left|Right|Nul|F[0-9]{1,2}"
)
_KEY_TOKEN: Final = re.compile(rf"<(?:(?:[CSMAD]-)+(?:{_KEY_NAMES}|[^<>\s])|{_KEY_NAMES})>|.", re.I | re.S)

type Exercise = dict[str, Any]
type Job = tuple[Exercise, str]


class Kind:
    """Exercise kinds."""

    EDIT: Final = "edit"
    CURSOR: Final = "cursor"
    EX: Final = "ex"


@dataclass(frozen=True, slots=True)
class Outcome:
    """Raw state reported by oracle.lua after replaying one key string."""

    keys: str
    lines: list[str]
    cursor: list[int]
    mode: str
    used_ex: bool
    recording: bool
    errmsg: str
    done: bool = True  # False: the keys swallowed oracle.lua's end marker (ended mid-command)


@dataclass(frozen=True, slots=True)
class Verdict:
    """Graded result of one replay."""

    exercise_id: str
    keys: str
    count: int
    passed: bool
    reason: str
    wall_ms: float
    outcome: Outcome | None = field(default=None, repr=False)


type Runner = Callable[[Sequence[Job]], list[Outcome]]


# Public Functions =================================================================================


def load_exercise(path: str | pathlib.Path) -> Exercise:
    """Read one exercise JSON file."""
    return json.loads(pathlib.Path(path).read_text())


def tokenize_keys(keys: str) -> list[str]:
    """Split a key string in Vim angle-bracket notation into keystrokes.

    Parameters
    ----------
    keys
        Keys such as ``ci"x<Esc>`` or ``<C-v>2j$A;<Esc>``.

    Returns
    -------
    list[str]
        One entry per keystroke. Named keys and modifier chords are single tokens;
        ``<`` not followed by a known key name is a literal ``<``.

    Examples
    --------
    >>> tokenize_keys("3<C-a>:w<CR>")
    ['3', '<C-a>', ':', 'w', '<CR>']
    """
    return _KEY_TOKEN.findall(keys)


def count_keys(keys: str) -> int:
    """Keystroke count after normalisation (each notation token is one key)."""
    return len(tokenize_keys(keys))


def grade(exercise: Exercise, outcome: Outcome) -> tuple[bool, str]:
    """Apply the pass condition for the exercise kind.

    Every kind also requires that the keys end in Normal mode with no macro recording,
    so a solution missing its final ``<Esc>`` or ``<CR>`` fails (the par counts it).

    Returns
    -------
    tuple[bool, str]
        Pass flag and a short reason (``"ok"`` on pass).
    """
    if outcome.mode == "timeout":
        return False, outcome.errmsg
    if outcome.mode != "n":
        return False, f"ended in mode {outcome.mode!r}, not Normal (missing <Esc> or <CR>?)"
    if outcome.recording:
        return False, "macro recording left open"
    kind = exercise["kind"]
    if kind == Kind.CURSOR:
        return _grade_cursor(exercise, outcome)
    if not _lines_match(outcome.lines, exercise["expect"]["lines"]):
        return False, "buffer differs from expect.lines"
    if kind == Kind.EX and not outcome.used_ex:
        return False, "no ':' command was executed"
    return True, "ok"


def subprocess_runner(timeout_s: float = DEFAULT_TIMEOUT_S, nvim: str | None = None) -> Runner:
    """Runner that replays all given jobs in one fresh ``nvim -l oracle.lua`` process."""
    return functools.partial(_run_subprocess, timeout_s=timeout_s, nvim=nvim or _nvim_path())


class PynvimSession:
    """Long-lived embedded Neovim driven over msgpack-RPC; use as a context manager.

    Each job runs in a fresh buffer with registers, search, char-search, global marks and
    the jumplist cleared. The ``.`` repeat and ``@:`` registers cannot be reset and carry
    over between jobs; keys that start with ``.`` or ``@:`` must use the subprocess runner.
    """

    def __init__(self, nvim: str | None = None):
        logging.getLogger("asyncio").setLevel(logging.ERROR)  # pynvim child-watcher noise on close
        argv = [nvim or _nvim_path(), "--embed", *NVIM_BASE_ARGS]
        self._nvim = pynvim.attach("child", argv=argv)
        self._nvim.exec_lua("Oracle = dofile(...)", str(ORACLE_LUA))

    def __repr__(self) -> str:
        return f"PynvimSession(channel={self._nvim.channel_id})"

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object):
        self.close()

    def run(self, jobs: Sequence[Job]) -> list[Outcome]:
        """Replay jobs in order. TODO: no timeout; a looping key string hangs the session."""
        return [_outcome(self._nvim.exec_lua("return Oracle.run(...)", ex, keys)) for ex, keys in jobs]

    def close(self):
        """Stop the embedded Neovim."""
        self._nvim.close()


def verify(exercise: Exercise, keys: str | None = None, runner: Runner | None = None) -> Verdict:
    """Replay ``keys`` (default: the canonical ``par.keys``) and grade it, timing the call."""
    keys = keys if keys is not None else exercise["par"]["keys"]
    start = time.perf_counter()
    (outcome,) = (runner or subprocess_runner())([(exercise, keys)])
    wall_ms = (time.perf_counter() - start) * 1000
    return _verdict(exercise, keys, outcome, wall_ms)


def verify_many(jobs: Sequence[Job], runner: Runner) -> list[Verdict]:
    """Replay many jobs through one runner call; ``wall_ms`` is the batch mean per job."""
    start = time.perf_counter()
    outcomes = runner(jobs)
    mean_ms = (time.perf_counter() - start) * 1000 / max(len(jobs), 1)
    return [_verdict(ex, keys, out, mean_ms) for (ex, keys), out in zip(jobs, outcomes, strict=True)]


def probe_cursors(
    jobs: Sequence[tuple[Exercise, Sequence[str]]], timeout_s: float = DEFAULT_TIMEOUT_S, nvim: str | None = None,
) -> list[list[list[int] | None]]:
    """Replay many short motions per exercise in one Neovim and report where each lands.

    The buffer is set up once per exercise; each probe starts from ``start.cursor`` with
    the char search cleared. A probe that does not end in Normal mode or changes the
    buffer reports None.

    Returns
    -------
    list[list[list[int] | None]]
        Per job, one ``[line, col]`` (or None) per probe, in order.
    """
    if not jobs:
        return []
    payload = [{"exercise": ex, "probes": list(probes)} for ex, probes in jobs]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
    budget = timeout_s * len(jobs) + 0.01 * sum(len(p) for _, p in jobs)
    try:
        proc = subprocess.run(
            [nvim or _nvim_path(), *NVIM_BASE_ARGS, "-l", str(ORACLE_LUA), fh.name],
            capture_output=True, text=True, timeout=budget, stdin=subprocess.DEVNULL,
        )
    finally:
        pathlib.Path(fh.name).unlink(missing_ok=True)
    results = [json.loads(line[len(MARKER):])["probes"] for line in proc.stdout.splitlines() if line.startswith(MARKER)]
    if len(results) != len(jobs):
        raise RuntimeError(f"oracle returned {len(results)}/{len(jobs)} probe results: {proc.stderr.strip()[-500:]}")
    return [[list(c) if isinstance(c, list) else None for c in res] for res in results]


@functools.cache
def nvim_version(nvim: str | None = None) -> str:
    """Neovim version string such as ``0.12.5``."""
    out = subprocess.run([nvim or _nvim_path(), "--version"], capture_output=True, text=True, check=True)
    return out.stdout.split()[1].lstrip("v")


def verified_stamp(today: datetime.date | None = None) -> str:
    """Value for ``par.verified``, e.g. ``nvim 0.12.5 2026-10-11``."""
    return f"nvim {nvim_version()} {(today or datetime.date.today()).isoformat()}"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: verify the canonical (and optionally alternate) solutions of exercise files."""
    args = _parse_args(argv)
    exercises = [load_exercise(p) for p in args.files]
    jobs = [(ex, k) for ex in exercises for k in _keys_to_check(ex, args.keys, args.alternates)]
    verdicts = _verify_with_backend(jobs, args.backend)
    for v in verdicts:
        status = "PASS" if v.passed else "FAIL"
        print(f"{status} {v.exercise_id:<20} {v.count:>3} keys {v.wall_ms:7.1f} ms  {v.keys!r}  {v.reason}")
    print(f"{sum(v.passed for v in verdicts)}/{len(verdicts)} passed; {verified_stamp()}")
    return 0 if all(v.passed for v in verdicts) else 1


# Private Functions ================================================================================


def _nvim_path() -> str:
    path = shutil.which("nvim")
    if path is None:
        raise FileNotFoundError("nvim not found on PATH")
    return path


def _run_subprocess(jobs: Sequence[Job], timeout_s: float, nvim: str) -> list[Outcome]:
    """Run jobs in one nvim; on timeout, bisect so only the looping job is lost.

    ``timeout_s`` is the budget for a single job; a batch gets ``timeout_s`` plus 50 ms
    per job. A job that times out on its own gets mode ``"timeout"`` and fails grading.
    """
    try:
        return _run_batch(jobs, timeout_s + 0.05 * len(jobs), nvim)
    except subprocess.TimeoutExpired:
        if len(jobs) == 1:
            _, keys = jobs[0]
            return [Outcome(keys, [], [0, 0], "timeout", False, False, f"timed out after {timeout_s}s")]
        mid = len(jobs) // 2
        return _run_subprocess(jobs[:mid], timeout_s, nvim) + _run_subprocess(jobs[mid:], timeout_s, nvim)


def _run_batch(jobs: Sequence[Job], timeout_s: float, nvim: str) -> list[Outcome]:
    payload = [{"exercise": ex, "keys": keys} for ex, keys in jobs]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
    try:
        proc = subprocess.run(
            [nvim, *NVIM_BASE_ARGS, "-l", str(ORACLE_LUA), fh.name],
            capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL,
        )
    finally:
        pathlib.Path(fh.name).unlink(missing_ok=True)
    outcomes = [_outcome(json.loads(line[len(MARKER):])) for line in proc.stdout.splitlines() if line.startswith(MARKER)]
    if len(outcomes) != len(jobs):
        raise RuntimeError(f"oracle returned {len(outcomes)}/{len(jobs)} results: {proc.stderr.strip()[-500:]}")
    return outcomes


def _outcome(raw: dict[str, Any]) -> Outcome:
    lines = raw["lines"] if isinstance(raw["lines"], list) else []
    return Outcome(
        keys=raw["keys"], lines=lines, cursor=list(raw["cursor"]), mode=raw["mode"],
        used_ex=bool(raw["used_ex"]), recording=bool(raw["recording"]), errmsg=raw.get("errmsg") or "",
        done=bool(raw.get("done", True)),
    )


def _verdict(exercise: Exercise, keys: str, outcome: Outcome, wall_ms: float) -> Verdict:
    passed, reason = grade(exercise, outcome)
    return Verdict(exercise.get("id", "?"), keys, count_keys(keys), passed, reason, wall_ms, outcome)


def _lines_match(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return [s.rstrip() for s in actual] == [s.rstrip() for s in expected]


def _grade_cursor(exercise: Exercise, outcome: Outcome) -> tuple[bool, str]:
    if outcome.lines != exercise["start"]["lines"]:
        return False, "buffer changed in a cursor exercise"
    expected = list(exercise["expect"]["cursor"])
    if outcome.cursor != expected:
        return False, f"cursor {outcome.cursor} != expected {expected}"
    return True, "ok"


def _keys_to_check(exercise: Exercise, keys: str | None, alternates: bool) -> list[str]:
    if keys is not None:
        return [keys]
    return [exercise["par"]["keys"], *(exercise.get("alternates", []) if alternates else [])]


def _verify_with_backend(jobs: Sequence[Job], backend: str) -> list[Verdict]:
    if backend == "batch":
        return verify_many(jobs, subprocess_runner())
    if backend == "pynvim":
        with PynvimSession() as session:
            return [verify(ex, k, session.run) for ex, k in jobs]
    runner = subprocess_runner()
    return [verify(ex, k, runner) for ex, k in jobs]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vimtrainer-oracle", description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", help="exercise JSON files")
    parser.add_argument("--keys", help="replay these keys instead of par.keys")
    parser.add_argument("--alternates", action="store_true", help="also check alternates")
    parser.add_argument("--backend", choices=("subprocess", "batch", "pynvim"), default="subprocess")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
