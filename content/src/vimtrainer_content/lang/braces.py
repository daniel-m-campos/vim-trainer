"""Helpers shared by the brace languages (lang/cpp.py, lang/js.py).

Only what is the same in both: text and highlight helpers, bracket scanning, span merging,
the gate-5 pre-check, node frequency and the template registration context. Each language
module keeps its own templates, windowing and tables (pairs, nouns, replacement texts).
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterator
from typing import Final

import tree_sitter

from vimtrainer_content import gates, oracle, snippets, templates
from vimtrainer_content.lang import Language
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

_BRACKETS: Final = {"(": ")", "[": "]", "{": "}"}


# Public Functions =================================================================================


def text(node: tree_sitter.Node | None) -> str:
    """The source text of ``node``; empty for None."""
    return node.text.decode() if node is not None and node.text is not None else ""


def highlight(sr: int, sc: int, er: int, ec: int) -> dict[str, list[int]]:
    """A highlight range, [line 1-based, col 0-based] inclusive at both ends."""
    return {"start": [sr + 1, sc], "end": [er + 1, ec]}


def indent(line: str) -> int:
    """Leading whitespace of ``line``, in columns."""
    return len(line) - len(line.lstrip())


def replace(lines: list[str], row: int, c0: int, c1: int, new: str) -> list[str]:
    """``lines`` with ``lines[row][c0:c1]`` replaced by ``new``."""
    out = list(lines)
    out[row] = lines[row][:c0] + new + lines[row][c1:]
    return out


def pick_other(options, current: str, *key: object) -> str:
    """A deterministic pick among ``options`` other than ``current``."""
    return pick([o for o in options if o != current.strip()], *key)


def js_escape(raw: str) -> str:
    """Escape for a regex that must work in both Python and JavaScript."""
    return re.sub(r"([\\^$.*+?()[\]{}|/])", r"\\\1", raw)


def cells(win: Window, node: tree_sitter.Node) -> set[tuple[int, int]]:
    """(row, col) cells ``node`` covers, clipped to the window."""
    (r0, c0), (r1, c1) = node.start_point, node.end_point
    return {(r, c) for r in range(r0, min(r1, len(win.lines) - 1) + 1)
            for c in range(c0 if r == r0 else 0, c1 if r == r1 else len(win.lines[r]))}


def bracket_pair(node: tree_sitter.Node) -> tuple[tuple[int, int, str], tuple[int, int, str]] | None:
    """((row, col, open), (row, col, close)) when a node starts and ends with a (), [] or {} pair."""
    kids = node.children
    if len(kids) < 2 or kids[0].type not in _BRACKETS or _BRACKETS[kids[0].type] != kids[-1].type:
        return None
    o, c = kids[0], kids[-1]
    return (o.start_point.row, o.start_point.column, o.type), (c.start_point.row, c.start_point.column, c.type)


def depth0_positions(win: Window, open_rc, close_rc, o: str, c: str) -> list[tuple[int, int]]:
    """Non-blank, non-bracket cells between an open and close position, outside nested o/c pairs."""
    out, depth = [], 0
    (r0, c0), (r1, c1) = open_rc, close_rc
    for r in range(r0, r1 + 1):
        line = win.lines[r]
        for i in range(c0 + 1 if r == r0 else 0, c1 if r == r1 else len(line)):
            ch = line[i]
            if ch == o:
                depth += 1
            elif ch == c:
                depth -= 1
            elif depth == 0 and not ch.isspace() and ch not in "()[]{}":
                out.append((r, i))
    return out


def worth_it(draft: Draft, lang: Language) -> bool:
    """Gate 5 (anti-shortcut) ahead of the oracle, so the per-window draft cap is spent on
    drafts that can ship (short subscripts such as ``[pos]`` never beat ``x``)."""
    par = oracle.count_keys(draft.variants[0])
    return gates.anti_shortcut_problem(draft.exercise(lang.name), par, draft.typed) is None


def occurrences(line: str, tok: str, start: int) -> list[int]:
    """Columns of every non-overlapping ``tok`` in ``line`` from ``start`` on."""
    out, i = [], line.find(tok, start)
    while i != -1:
        out.append(i)
        i = line.find(tok, i + len(tok))
    return out


def merge_short(spans: list[tuple[int, int]], limit: int = snippets.MAX_LINES) -> list[tuple[int, int]]:
    """Fold spans shorter than MIN_LINES into the previous span when the result fits ``limit`` lines."""
    out: list[tuple[int, int]] = []
    for start, end in spans:
        short = end - start + 1 < snippets.MIN_LINES or (out and out[-1][1] - out[-1][0] + 1 < snippets.MIN_LINES)
        if out and short and end - out[-1][0] + 1 <= limit:
            out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def node_frequency(texts: list[str], parse: Callable[[str], tree_sitter.Tree]) -> dict[str, object]:
    """``snippets.node_frequency`` with another parser (named nodes per 100 lines over whole files)."""
    counts: dict[str, int] = {}
    total = 0
    for source in texts:
        total += len(source.splitlines())
        stack = [parse(source).root_node]
        while stack:
            node = stack.pop()
            if node.is_named:
                counts[node.type] = counts.get(node.type, 0) + 1
            stack.extend(node.children)
    per100 = {k: round(v * 100 / max(total, 1), 3) for k, v in sorted(counts.items())}
    return {"files": len(texts), "lines": total, "per100Lines": per100, "counts": dict(sorted(counts.items()))}


@contextlib.contextmanager
def registered(node_templates: dict, line_templates: dict) -> Iterator[None]:
    """Add a language's templates to ``templates.NODE_TEMPLATES`` / ``LINE_TEMPLATES`` for the
    ``with`` block, then remove them again (the shared registry has no per-language hook)."""
    added = []
    for registry, extra in ((templates.NODE_TEMPLATES, node_templates), (templates.LINE_TEMPLATES, line_templates)):
        for name, fn in extra.items():
            if name not in registry:
                registry[name] = fn
                added.append((registry, name))
    try:
        yield
    finally:
        for registry, name in added:
            registry.pop(name, None)
