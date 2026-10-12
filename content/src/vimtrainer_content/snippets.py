"""Cut source files into snippet windows and parse them with tree-sitter.

A window is a run of whole sibling statements, 8-40 lines, at most 100 columns wide,
dedented and re-parsed on its own so every exercise buffer is valid code by itself.
Statements longer than 40 lines (big classes and functions) are split by recursing into
their bodies. Licence headers and author comments never enter a window, and multi-line
docstrings are shortened to their summary line so snippets stay code-dense.

Windows are ASCII-only and tab-free. That keeps the oracle's byte columns equal to the
browser's UTF-16 columns and avoids tabstop differences between Neovim and the emulator.
"""

from __future__ import annotations

import collections
import functools
import hashlib
import re
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Final

import tree_sitter
import tree_sitter_python

MIN_LINES: Final = 8
MAX_LINES: Final = 40
MAX_COLS: Final = 100
SOFT_LINES: Final = 16  # flush a window once it reaches this many lines

_HEADER: Final = re.compile(r"(?i)copyright|licen[cs]e|\bauthor\b|@author|spdx")
_SECRETS: Final = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("aws-key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("api-key", re.compile(r"\b(sk|pk|rk)_(live|test)?_?[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("assigned-secret", re.compile(r"(?i)(password|passwd|secret|api_?key|token)\s*=\s*['\"][^'\"]{8,}['\"]")),
)
_BODY_TYPES: Final = frozenset({
    "class_definition", "function_definition", "decorated_definition", "if_statement", "for_statement",
    "while_statement", "with_statement", "try_statement",
})


@dataclass
class Window:
    """A snippet: dedented lines from one source file plus their syntax tree."""

    lines: list[str]
    source: dict[str, str]
    first_line: int  # 1-based line of lines[0] in the source file
    last_line: int  # 1-based line of lines[-1] in the source file
    tree: tree_sitter.Tree = field(repr=False)
    cache: dict = field(default_factory=dict, repr=False)  # per-window memo for templates

    @property
    def root(self) -> tree_sitter.Node:
        """Root node of the window's own parse."""
        return self.tree.root_node

    @property
    def key(self) -> str:
        """Stable identity used for hashing and spreading exercises across windows."""
        return f"{self.source['repo']}:{self.source['path']}:{self.first_line}"


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for Python."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse Python source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a source file into parseable 8-40 line windows.

    Parameters
    ----------
    text
        Whole source file.
    source
        The exercise ``source`` object (repo, path, commit, license).

    Returns
    -------
    list[Window]
        Windows that pass the size, width, ASCII and parse checks. Secret scanning is a
        separate gate (``secret_findings``) so the build can count its rejections.
    """
    lines, origin = shorten_docstrings(text.splitlines())
    spans = _merge_short(list(_spans(parse("\n".join(lines)).root_node.named_children, lines)))
    out = []
    for start, end in spans:
        win = _make_window(lines, origin, start, end, source)
        if win is not None:
            out.append(win)
    return out


def shorten_docstrings(lines: list[str]) -> tuple[list[str], list[int]]:
    """Replace multi-line docstrings with a one-line docstring holding their summary.

    Returns
    -------
    tuple[list[str], list[int]]
        The new lines, and for each new line its 1-based line number in the input.
    """
    tree = parse("\n".join(lines))
    cuts: dict[int, tuple[int, str]] = {}  # start row -> (end row, replacement line)
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in ("module", "block"):
            continue
        first = next((c for c in node.named_children if c.type != "comment"), None)
        if first is None or first.type != "expression_statement" or first.named_child_count != 1:
            continue
        string = first.named_children[0]
        if string.type != "string" or string.start_point.row == string.end_point.row:
            continue
        quote = string.children[0].text.decode() if string.children else '"""'
        body = string.text.decode()[len(quote):]
        summary = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        summary = summary.removesuffix(quote[-3:] if len(quote) >= 3 else quote).strip()
        if not summary or quote[-1] in summary:
            continue
        row = string.start_point.row
        indent = lines[row][:string.start_point.column]
        cuts[row] = (string.end_point.row, f"{indent}{quote}{summary}{quote[-3:] if len(quote) >= 3 else quote}")
    out, origin, row = [], [], 0
    while row < len(lines):
        if row in cuts:
            end, line = cuts[row]
            out.append(line)
            origin.append(row + 1)
            row = end + 1
            continue
        out.append(lines[row])
        origin.append(row + 1)
        row += 1
    return out, origin


def size_problem(lines: list[str]) -> str | None:
    """Quality gate 2: why ``lines`` is not a valid snippet, or None."""
    if not MIN_LINES <= len(lines) <= MAX_LINES:
        return f"{len(lines)} lines (need {MIN_LINES}-{MAX_LINES})"
    if any(len(ln) > MAX_COLS for ln in lines):
        return f"a line is wider than {MAX_COLS} columns"
    if any("\t" in ln for ln in lines):
        return "contains a tab"
    if any(not ln.isascii() for ln in lines):
        return "contains non-ASCII text"
    return None


def secret_findings(lines: list[str]) -> list[str]:
    """Quality gate 7: names of secret patterns found in the snippet."""
    text = "\n".join(lines)
    return [name for name, rx in _SECRETS if rx.search(text)]


def node_frequency(texts: list[str]) -> dict[str, object]:
    """Named node counts per 100 lines over whole files (``stats/node_frequency.json``)."""
    counts: collections.Counter[str] = collections.Counter()
    total_lines = 0
    for text in texts:
        total_lines += len(text.splitlines())
        stack = [parse(text).root_node]
        while stack:
            node = stack.pop()
            if node.is_named:
                counts[node.type] += 1
            stack.extend(node.children)
    per100 = {k: round(v * 100 / max(total_lines, 1), 3) for k, v in sorted(counts.items())}
    return {"files": len(texts), "lines": total_lines, "per100Lines": per100, "counts": dict(sorted(counts.items()))}


def stable_hash(*parts: object) -> str:
    """Short deterministic hash used for ids and for deterministic pseudo-random choices."""
    return hashlib.sha1("\x1f".join(map(str, parts)).encode()).hexdigest()


def pick(seq, *parts: object):
    """Deterministically pick one item of ``seq`` keyed by ``parts``."""
    return seq[int(stable_hash(*parts)[:8], 16) % len(seq)]


# Private Functions ================================================================================


def _spans(siblings: list[tree_sitter.Node], lines: list[str]) -> Iterator[tuple[int, int]]:
    """Group sibling statements into [start_row, end_row] spans of about SOFT_LINES lines."""
    group: list[int] | None = None
    for node in siblings:
        start, end = node.start_point.row, node.end_point.row
        if node.type == "comment" and _HEADER.search(lines[start]):
            if group:
                yield tuple(group)
            group = None
            continue
        if end - start + 1 > MAX_LINES:
            if group:
                yield tuple(group)
            group = None
            yield from _spans(_body_statements(node), lines)
            continue
        if group and end - group[0] + 1 > MAX_LINES:
            yield tuple(group)
            group = None
        group = [start, end] if group is None else [group[0], end]
        if group[1] - group[0] + 1 >= SOFT_LINES:
            yield tuple(group)
            group = None
    if group:
        yield tuple(group)


def _merge_short(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Fold spans shorter than MIN_LINES into the previous span when the result fits."""
    out: list[tuple[int, int]] = []
    for start, end in spans:
        short = end - start + 1 < MIN_LINES or (out and out[-1][1] - out[-1][0] + 1 < MIN_LINES)
        if out and short and end - out[-1][0] + 1 <= MAX_LINES:
            out[-1] = (out[-1][0], end)
        else:
            out.append((start, end))
    return out


def _body_statements(node: tree_sitter.Node) -> list[tree_sitter.Node]:
    if node.type not in _BODY_TYPES:
        return []
    if node.type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        return _body_statements(definition) if definition else []
    body = node.child_by_field_name("body")
    if body is None:
        body = next((c for c in node.named_children if c.type == "block"), None)
    return body.named_children if body else []


def _make_window(
    lines: list[str], origin: list[int], start: int, end: int, source: dict[str, str],
) -> Window | None:
    chunk = lines[start:end + 1]
    while chunk and not chunk[0].strip():
        chunk, start = chunk[1:], start + 1
    while chunk and not chunk[-1].strip():
        chunk, end = chunk[:-1], end - 1
    chunk = [ln.rstrip() for ln in textwrap.dedent("\n".join(chunk)).split("\n")]
    if size_problem(chunk):
        return None
    tree = parse("\n".join(chunk))
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=origin[start], last_line=origin[end], tree=tree)
