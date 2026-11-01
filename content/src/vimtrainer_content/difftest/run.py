"""``vimtrainer-content difftest``: replay random key sequences in Neovim and in the browser.

Flow: generate cases from a seed, replay them in
headless Neovim (``oracle.subprocess_runner``) and in the practice editor
(``web.WebWorker``), compare lines/cursor/mode, keep one finding per key shape, minimise
each to the shortest diverging key string, classify it, and write
``content/.cache/difftest/<seed>/findings.jsonl`` and ``summary.md``. With ``--strict``
the exit status is 1 when a finding is neither known (``content/difftest/known.jsonl``)
nor flaky, or when the run was not healthy enough to judge (``_health``).

Examples
--------
>>> main(["--count", "50", "--buffers", "10", "--no-minimise"])  # doctest: +SKIP
0
"""

import argparse
import concurrent.futures
import datetime
import itertools
import json
import os
import pathlib
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any, Final

from vimtrainer_content import build, oracle, sources
from vimtrainer_content.difftest import compare, generate, shrink, web

NVIM_BATCH: Final = 200
DEFAULT_OUT: Final = sources.CONTENT_DIR / ".cache" / "difftest"
DEFAULT_KNOWN: Final = sources.CONTENT_DIR / "difftest" / "known.jsonl"
EXTRA_BUFFERS: Final = sources.CONTENT_DIR / "difftest" / "buffers"
PAGEERROR: Final = "pageerror"
NVIM_OPTIONS: Final = {"startofline": True}  # see _job
# --strict also fails when the harness itself is broken: more than this fraction of cases
# had no comparable result (an error or timeout on either side), or the browser worker stalled.
MAX_INCOMPLETE: Final = 0.2
STALLED: Final = "worker stalled"

type WebRunner = Callable[[Sequence[generate.Case]], list[compare.Side]]
type NvimRunner = Callable[[Sequence[generate.Case]], list[compare.Side]]


# Public Functions =================================================================================


def nvim_sides(cases: Sequence[generate.Case], timeout_s: float = 5.0) -> list[compare.Side]:
    """Replay cases in headless Neovim, ``NVIM_BATCH`` per process, batches in parallel.

    Uses ``oracle.subprocess_runner`` (not ``PynvimSession``): it has a timeout, bisects a
    batch around a looping job, and ``oracle.lua`` resets registers and marks per job.
    A batch whose nvim crashes is retried one job at a time; a job that still fails gets
    an ``error`` side.
    """
    runner = oracle.subprocess_runner(timeout_s=timeout_s)
    batches = [list(batch) for batch in itertools.batched(cases, NVIM_BATCH)]
    workers = max(1, min(len(batches), os.cpu_count() or 1))
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        results = pool.map(lambda batch: _nvim_batch(batch, runner), batches)
    return [side for batch in results for side in batch]


def main(argv: Sequence[str] | None = None) -> int:
    """Stand-alone entry point; the CLI calls ``run(args)`` through ``add_parser``."""
    parser = argparse.ArgumentParser(prog="vimtrainer-content difftest", description=__doc__.splitlines()[0])
    _add_arguments(parser)
    return run(parser.parse_args(argv))


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``difftest`` subcommand on the ``vimtrainer-content`` parser."""
    p = sub.add_parser("difftest", help="differential test: random key sequences in Neovim vs the browser editor")
    _add_arguments(p)
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace, nvim: NvimRunner | None = None, web_runner: WebRunner | None = None) -> int:
    """Run the subcommand; ``nvim`` and ``web_runner`` replace the real sides in tests."""
    if args.accept:
        return _accept(args)
    if args.to_editor_case:
        return _to_editor_case(args.to_editor_case)
    nvim = nvim or nvim_sides
    if web_runner is not None:
        return _fuzz(args, nvim, web_runner)
    with web.WebWorker(web.APP_DIR, pages=args.web_pages) as worker:
        code = _fuzz(args, nvim, worker.run)
        if worker.restarts:
            print(f"web worker restarted {worker.restarts} time(s)")
        return code


# Private Functions ================================================================================


def _add_arguments(p: argparse.ArgumentParser):
    p.add_argument("--seed", type=int, default=int(datetime.date.today().strftime("%Y%m%d")),
                   help="run seed (default: today as YYYYMMDD)")
    p.add_argument("--count", type=int, default=2000, help="key sequences to generate")
    p.add_argument("--buffers", type=int, default=200, help="start buffers sampled, split across languages")
    p.add_argument("--lang", nargs="+", default=["python", "cpp"], choices=["python", "cpp"])
    p.add_argument("--max-len", type=int, default=24, help="max keystrokes per sequence")
    p.add_argument("--web-pages", type=int, default=4, help="browser pages replaying in parallel")
    p.add_argument("--build", type=pathlib.Path, default=build.DEFAULT_OUT, help="build/ to sample buffers from")
    p.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT, help="results go to OUT/<seed>/")
    p.add_argument("--known", type=pathlib.Path, default=DEFAULT_KNOWN, help="known divergences (jsonl)")
    p.add_argument("--strict", action="store_true", help="exit 1 on findings not in --known")
    p.add_argument("--no-minimise", action="store_true", help="skip minimisation")
    p.add_argument("--minimise-budget-s", type=float, default=240.0, help="wall-clock budget for minimisation")
    p.add_argument("--max-findings", type=int, default=200, help="minimise at most this many distinct shapes")
    p.add_argument("--only-index", type=int, help="replay only the case with this index")
    p.add_argument("--dump", action="store_true", help="also write cases.jsonl")
    p.add_argument("--accept", type=pathlib.Path, metavar="FILE",
                   help="append the findings in FILE (findings.jsonl) to --known and exit")
    p.add_argument("--class", dest="cls", choices=list("abcd"), help="class for --accept (default: the finding's)")
    p.add_argument("--note", default="", help="note for --accept")
    p.add_argument("--include", nargs="*", default=[], choices=["screen"], help="extra key families")
    p.add_argument("--to-editor-case", type=pathlib.Path, metavar="FILE",
                   help="print app/e2e/cases/*.json lines for the findings in FILE and exit")


def _fuzz(args: argparse.Namespace, nvim: NvimRunner, web_runner: WebRunner) -> int:
    out = args.out / str(args.seed)
    out.mkdir(parents=True, exist_ok=True)
    stats: dict[str, Any] = {"seed": args.seed, "langs": args.lang}
    cases = _cases(args)
    stats["cases"] = len(cases)
    if args.dump:
        _write_jsonl(out / "cases.jsonl", [generate.case_to_json(c) for c in cases])

    t0 = time.perf_counter()
    nv = nvim(cases)
    stats["nvim_s"] = round(time.perf_counter() - t0, 1)
    t0 = time.perf_counter()
    wb = web_runner(cases)
    stats["web_s"] = round(time.perf_counter() - t0, 1)

    findings, counts = _diverging(cases, nv, wb)
    stats.update(counts)
    if not args.no_minimise:
        findings = _minimise_all(findings, nvim, web_runner, args, stats)
    known = compare.load_known(args.known) if args.known.exists() else []
    flaky = set(stats.get("flaky_indices", []))
    # A long unminimised sequence almost always has a shape of its own (one sequence hits
    # several bugs), so only minimised findings are triaged; the rest are counted.
    judged = findings if args.no_minimise else [f for f in findings if f.minimised is not None]
    new = [f for f in judged if f.case.index not in flaky and not compare.is_known(f, known)]
    stats["findings"] = len(judged)
    stats["new"] = len(new)
    stats["known"] = len(judged) - len(new)

    _write_jsonl(out / "findings.jsonl", [f.to_json() for f in findings])
    (out / "summary.md").write_text(compare.render_summary(judged, stats))
    print(f"seed {args.seed}: {len(cases)} cases, {counts['diverging']} diverging, {len(judged)} distinct "
          f"{'shapes' if args.no_minimise else 'minimised shapes'}, {len(new)} new; "
          f"nvim {stats['nvim_s']}s, web {stats['web_s']}s -> {out}")
    for f in new[:20]:
        print(f"  [{f.cls}] {f.shape}  keys {f.minimised or f.case.keys!r}  ({', '.join(f.fields)})")
    problems = _health(stats, judged)
    for p in problems:
        print(f"WARNING: {p}")
    return 1 if args.strict and (new or problems) else 0


def _health(stats: dict[str, Any], judged: Sequence[compare.Finding]) -> list[str]:
    """Reasons the run cannot be trusted as a pass (empty when healthy); --strict fails on any."""
    problems = []
    cases = stats["cases"]
    if cases and stats["incomplete"] / cases > MAX_INCOMPLETE:
        problems.append(f"{stats['incomplete']}/{cases} cases incomplete (error or timeout), "
                        f"over {MAX_INCOMPLETE:.0%}")
    if stats["stalled"]:
        problems.append(f"browser worker stalled on {stats['stalled']} case(s)")
    if stats.get("unminimised"):
        # Warned, not failed, while some findings were judged: the nightly would otherwise
        # go red on every slow runner. With none judged, strict would be a no-op.
        print(f"WARNING: {stats['unminimised']} finding(s) left unminimised (--max-findings or "
              "--minimise-budget-s ran out); they are in findings.jsonl but not judged")
        if not judged:
            problems.append("every diverging shape was left unminimised, so none was judged")
    return problems


def _cases(args: argparse.Namespace) -> list[generate.Case]:
    extra = EXTRA_BUFFERS if EXTRA_BUFFERS.is_dir() else None
    per_lang = max(1, args.buffers // len(args.lang))
    buffers = [b for lang in args.lang
               for b in generate.load_buffers(args.build, lang, per_lang, args.seed, extra_dir=extra)]
    cases = generate.generate(args.seed, args.count, buffers, max_len=args.max_len,
                              include_screen="screen" in args.include)
    if args.only_index is not None:
        cases = [c for c in cases if c.index == args.only_index]
    return cases


def _diverging(cases: Sequence[generate.Case], nv: Sequence[compare.Side],
               wb: Sequence[compare.Side]) -> tuple[list[compare.Finding], dict[str, int]]:
    """One finding per shape (the lowest case index), plus counts for the summary."""
    by_shape: dict[str, compare.Finding] = {}
    counts = {"diverging": 0, "incomplete": 0, "equal": 0, "stalled": 0}
    for case, n, w in zip(cases, nv, wb, strict=True):
        counts["stalled"] += w.error == STALLED
        fields = _fields(n, w)
        if not fields and (n.mode in compare.INCOMPLETE or w.mode in compare.INCOMPLETE):
            counts["incomplete"] += 1
            continue
        if not fields:
            counts["equal"] += 1
            continue
        counts["diverging"] += 1
        shape = compare.shape(case.keys)
        if shape not in by_shape:
            by_shape[shape] = compare.Finding(case, n, w, fields, compare.classify(case, n, w), shape, None)
    return list(by_shape.values()), counts


def _minimise_all(findings: list[compare.Finding], nvim: NvimRunner, web_runner: WebRunner,
                  args: argparse.Namespace, stats: dict[str, Any]) -> list[compare.Finding]:
    """Minimise up to ``--max-findings`` within the time budget, shortest keys first (cheaper,
    and more likely to show one bug alone); re-dedupe by the minimised shape."""
    t0 = time.perf_counter()
    flaky: list[int] = []
    out: dict[str, compare.Finding] = {}
    unminimised = 0
    findings = sorted(findings, key=lambda f: (len(generate.tokenize(f.case.keys)), f.case.index))
    for i, f in enumerate(findings):
        over = i >= args.max_findings or time.perf_counter() - t0 > args.minimise_budget_s
        if over:
            unminimised += 1
            out.setdefault(f.shape, f)
            continue
        small = shrink.minimise(f.case, _diverges(nvim, web_runner))
        if small is None:
            flaky.append(f.case.index)
            f.cls = "c"
            out.setdefault(f.shape, f)
            continue
        (n,), (w,) = nvim([small]), web_runner([small])
        # Keep the original case (for --only-index) but show the minimised run's sides.
        f.nvim, f.web, f.fields = n, w, _fields(n, w) or f.fields
        f.minimised = small.keys
        f.shape = compare.shape(small.keys)
        f.cls = compare.classify(small, n, w)
        out.setdefault(f.shape, f)
    stats["minimise_s"] = round(time.perf_counter() - t0, 1)
    stats["flaky"] = len(flaky)
    stats["flaky_indices"] = flaky
    stats["unminimised"] = unminimised
    return list(out.values())


def _diverges(nvim: NvimRunner, web_runner: WebRunner) -> Callable[[list[generate.Case]], list[bool]]:
    def diverges(cases: list[generate.Case]) -> list[bool]:
        nv, wb = nvim(cases), web_runner(cases)
        return [bool(_fields(n, w)) for n, w in zip(nv, wb, strict=True)]

    return diverges


def _fields(nvim: compare.Side, web_side: compare.Side) -> list[str]:
    """Differing fields; a page error in the browser is a finding of its own (field "error")."""
    if web_side.error and web_side.error.startswith(PAGEERROR):
        return ["error"]
    return compare.compare(nvim, web_side)


def _nvim_batch(cases: list[generate.Case], runner: oracle.Runner) -> list[compare.Side]:
    """One nvim process for the batch; on a crash or non-UTF-8 output, bisect down to the bad job."""
    try:
        return [compare.nvim_side(o) for o in runner([_job(c) for c in cases])]
    except (RuntimeError, UnicodeDecodeError) as err:
        if len(cases) == 1:
            return [compare.Side((), (0, 0), "error", f"{type(err).__name__}: {str(err)[-300:]}")]
        mid = len(cases) // 2
        return _nvim_batch(cases[:mid], runner) + _nvim_batch(cases[mid:], runner)


def _job(case: generate.Case) -> oracle.Job:
    """Oracle job for a case. ``startofline`` is on as in Vim (Neovim defaults it off): with it
    off, ``dd``, ``>>``, ``gg``, ``G`` ... keep the column and every such case would diverge
    from codemirror-vim, which follows Vim. Class d (Neovim-specific behaviour we accept)."""
    buf = case.buffer
    exercise = {
        "id": f"difftest/{buf.id}", "lang": buf.lang, "kind": "edit",
        "options": {**NVIM_OPTIONS, **buf.options},
        "start": {"lines": list(buf.lines), "cursor": list(buf.cursor)},
    }
    return exercise, case.keys


def _accept(args: argparse.Namespace) -> int:
    known = compare.load_known(args.known) if args.known.exists() else []
    added = []
    for f in _load_findings(args.accept):
        if compare.is_known(f, known):
            continue
        entry = compare.known_entry(f, args.note, args.cls)
        known.append(entry)
        added.append(entry)
    args.known.parent.mkdir(parents=True, exist_ok=True)
    with args.known.open("a") as fh:
        for entry in added:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"added {len(added)} entr{'y' if len(added) == 1 else 'ies'} to {args.known}")
    return 0


def _to_editor_case(path: pathlib.Path) -> int:
    """Print one app/e2e/cases/*.json line per finding: inputs only, nvim answers at test time."""
    for f in _load_findings(path):
        print(_editor_case_line(_with_keys(f.case, f.minimised) if f.minimised else f.case, f))
    return 0


def _editor_case_line(case: generate.Case, f: compare.Finding) -> str:
    entry = {
        "name": f"difftest seed {case.seed} #{case.index} [{f.cls}] {f.shape}",
        "lang": case.buffer.lang,
        "lines": list(case.buffer.lines),
        "cursor": list(web.web_cursor(case.buffer)),
        "keys": case.keys,
    }
    return json.dumps(entry, ensure_ascii=False)


def _with_keys(case: generate.Case, keys: str) -> generate.Case:
    return generate.Case(case.index, case.seed, case.buffer, keys)


def _load_findings(path: pathlib.Path) -> list[compare.Finding]:
    return [compare.Finding.from_json(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]


def _write_jsonl(path: pathlib.Path, rows: Sequence[dict[str, Any]]):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


if __name__ == "__main__":
    sys.exit(main())
