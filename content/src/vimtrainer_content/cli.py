"""``vimtrainer-content``: fetch sources, build the corpus, review exercises, ingest player logs, difftest, expect."""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
from collections.abc import Sequence

from vimtrainer_content import build, expect, ingest, review, sources
from vimtrainer_content.difftest import run as difftest


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; see ``vimtrainer-content --help``."""
    args = _parser().parse_args(argv)
    return args.func(args)


# Private Functions ================================================================================


def _fetch(args: argparse.Namespace) -> int:
    for src in sources.load_sources():
        sources.fetch(src)
        print(f"{src.repo}@{src.commit[:12]}: {src.license} ok ({sources.verify_license(src)})")
    return 0


def _build(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    report = build.build(out=args.out, cap=args.cap, workers=args.jobs, skills=args.skills or None,
                         offline=args.offline)
    print(f"\nwrote {args.out} in {time.perf_counter() - t0:.1f}s; {report.replays} replays")
    for lang, skills in report.counts.items():
        print(f"{lang}:")
        for skill, n in skills.items():
            print(f"  {skill:<12} {n:>4}{'  THIN' if n < 20 else ''}")
    thin = {k: v for k, v in report.thin().items() if v}
    if thin:
        print(f"thin: {thin}")
    return 1 if thin and args.strict else 0


def _ingest(args: argparse.Namespace) -> int:
    for path in args.paths:
        ingest.ingest(path, out=args.out)
    return 0


def _review(args: argparse.Namespace) -> int:
    if args.idioms:
        review.list_idioms()
    elif args.list:
        review.list_exercises(args.out, args.skill)
    else:
        review.review(args.out, args.skill, args.all)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vimtrainer-content", description=__doc__)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("fetch", help="clone pinned sources into content/.cache and verify licences")
    p.set_defaults(func=_fetch)

    p = sub.add_parser("build", help="regenerate build/ from scratch")
    p.add_argument("--out", type=pathlib.Path, default=build.DEFAULT_OUT)
    p.add_argument("--cap", type=int, default=build.DEFAULT_CAP, help="max exercises per (lang, skill)")
    p.add_argument("--jobs", type=int, default=None, help="parallel nvim processes (default: CPU count)")
    p.add_argument("--skills", nargs="*", help="only these skills (default: each language's own list)")
    p.add_argument("--offline", action="store_true", help="use the cached checkout without fetching")
    p.add_argument("--strict", action="store_true", help="exit 1 if any (lang, skill) is thin")
    p.set_defaults(func=_build)

    p = sub.add_parser("review", help="show start -> expect -> canonical; accept or reject")
    p.add_argument("--out", type=pathlib.Path, default=build.DEFAULT_OUT)
    p.add_argument("--skill")
    p.add_argument("--all", action="store_true", help="include already reviewed exercises")
    p.add_argument("--list", action="store_true", help="print all, no prompts")
    p.add_argument("--idioms", action="store_true", help="list idioms learned from players (idioms_learned.toml)")
    p.set_defaults(func=_review)

    p = sub.add_parser("ingest", help="verify player key sequences in Neovim; update pars, alternates, review queues")
    p.add_argument("paths", nargs="+", type=pathlib.Path, help="exported progress JSON or a saved '!' issue body")
    p.add_argument("--out", type=pathlib.Path, default=build.DEFAULT_OUT)
    p.set_defaults(func=_ingest)

    difftest.add_parser(sub)
    expect.add_parser(sub)
    return parser


if __name__ == "__main__":
    sys.exit(main())
