"""Plain-text review of built exercises: start -> expect -> canonical, then accept/reject.

Accepted ids are appended to ``content/reviewed.txt`` and rejected ids to
``content/rejected.txt``. The build marks reviewed exercises with ``"reviewed": true`` and
drops rejected ones. Both files are plain id-per-line allowlists and can be edited by hand.

``list_idioms`` prints the idioms ``ingest`` learned from players (``idioms_learned.toml``);
they are reviewed by setting each entry's ``status`` in that file.
"""

from __future__ import annotations

import difflib
import json
import pathlib
import tomllib
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from vimtrainer_content import build, par_search

PROMPT = "[a]ccept  [r]eject  [s]kip  [q]uit > "


# Public Functions =================================================================================


def iter_exercises(out: pathlib.Path, skill: str | None = None) -> Iterator[dict[str, Any]]:
    """Exercises in a build directory, sorted by id, optionally one skill only."""
    for path in sorted((out / "exercises").glob("*/*/*.json")):
        ex = json.loads(path.read_text())
        if skill is None or ex["skill"] == skill:
            yield ex


def render(ex: dict[str, Any]) -> str:
    """Text view: task, start buffer with cursor and target marks, expected result, solution."""
    start = ex["start"]
    lines = start["lines"]
    width = len(str(len(lines)))
    cur_line, cur_col = start["cursor"]
    marks = _target_marks(ex.get("target", []))
    out = [
        f"== {ex['id']}  [{ex['kind']}]  template={ex.get('template', '?')}  reviewed={ex.get('reviewed', False)}",
        f"   {ex['task']}",
        f"   source: {ex['source']['repo']}/{ex['source']['path']}"
        f" lines {ex['source'].get('lines', '?')} ({ex['source']['license']})",
        "-- start (> cursor line, ^ cursor column, ~ target)",
    ]
    for i, line in enumerate(lines, 1):
        out.append(f"{'>' if i == cur_line else ' '} {i:>{width}} | {line}")
        under = [" "] * (max(len(line), cur_col + 1))
        for col in marks.get(i, ()):
            if col < len(under):
                under[col] = "~"
        if i == cur_line:
            under[cur_col] = "^"
        if "".join(under).strip():
            out.append(f"  {' ' * width} | {''.join(under).rstrip()}")
    if ex["kind"] == "cursor":
        line, col = ex["expect"]["cursor"]
        out.append(f"-- expect cursor at line {line}, column {col}: {lines[line - 1][col:col + 20]!r}")
    else:
        out.append("-- expect (diff)")
        diff = difflib.unified_diff(lines, ex["expect"]["lines"], "start", "expect", n=1, lineterm="")
        out.extend("   " + d for d in list(diff)[2:])
    par = ex["par"]
    best = f"  (best found: {par['best']['keys']!r}, {par['best']['count']})" if "best" in par else ""
    out.append(f"-- canonical: {par['keys']!r}  = {par['count']} keys{best}")
    if ex.get("alternates"):
        out.append(f"   alternates: {', '.join(repr(a) for a in ex['alternates'])}")
    for hint in ex.get("hints", []):
        trig = hint.get("trigger") if isinstance(hint, dict) else None
        text = hint.get("text") if isinstance(hint, dict) else hint
        out.append(f"   hint{' /' + trig + '/' if trig else ''}: {text}")
    return "\n".join(out)


def review(
    out: pathlib.Path = build.DEFAULT_OUT, skill: str | None = None, show_all: bool = False,
    ask: Callable[[str], str] = input, echo: Callable[[str], None] = print,
    reviewed_txt: pathlib.Path = build.REVIEWED_TXT, rejected_txt: pathlib.Path = build.REJECTED_TXT,
) -> tuple[int, int]:
    """Interactive loop. Returns (accepted, rejected) counts for this session."""
    done = build._read_ids(reviewed_txt) | build._read_ids(rejected_txt)
    accepted = rejected = 0
    for ex in iter_exercises(out, skill):
        if ex["id"] in done and not show_all:
            continue
        echo(render(ex))
        answer = ask(PROMPT).strip().lower()[:1]
        if answer == "q":
            break
        if answer == "a":
            _append(reviewed_txt, ex["id"])
            accepted += 1
        elif answer == "r":
            _append(rejected_txt, ex["id"])
            rejected += 1
        echo("")
    echo(f"accepted {accepted}, rejected {rejected}; lists: {reviewed_txt.name}, {rejected_txt.name}")
    return accepted, rejected


def list_exercises(out: pathlib.Path, skill: str | None, echo: Callable[[str], None] = print) -> int:
    """Non-interactive: print every exercise view."""
    n = 0
    for ex in iter_exercises(out, skill):
        echo(render(ex) + "\n")
        n += 1
    return n


def list_idioms(path: pathlib.Path = par_search.LEARNED_TOML, echo: Callable[[str], None] = print) -> int:
    """Print the idioms learned from players; review them by editing ``status`` in the file."""
    entries = tomllib.loads(path.read_text()).get("idiom", []) if path.exists() else []
    for e in entries:
        echo(f"{e['status']:<9} {e['skill']:<12} {e['keys']!r}  (from {e['from']}, seq {e['seq']!r}, {e['added']})")
    echo(f"{len(entries)} learned idioms in {path.name}; set status to \"ok\" or \"rejected\" there")
    return len(entries)


# Private Functions ================================================================================


def _target_marks(target: Sequence[dict[str, list[int]]]) -> dict[int, set[int]]:
    marks: dict[int, set[int]] = {}
    for rng in target:
        (sl, sc), (el, ec) = rng["start"], rng["end"]
        if sl == el:
            marks.setdefault(sl, set()).update(range(sc, ec + 1))
    return marks


def _append(path: pathlib.Path, ex_id: str):
    with path.open("a") as fh:
        fh.write(ex_id + "\n")
