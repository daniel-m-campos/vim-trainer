"""Normalise Neovim and browser results to one ``Side``, diff them, and triage the differences.

Both sides report ``cursor`` as [line 1-based, column 0-based]. Neovim counts the column in
UTF-8 bytes and CodeMirror in UTF-16 code units, so ``nvim_side`` converts. A side whose mode
is in ``INCOMPLETE`` (operator pending, command line open, timeout, harness error ...) is
not comparable and never yields a finding.

Classes (docs/design/differential-testing.md): ``a`` emulator bug to fix in vimfixes.ts,
``b`` emulator limitation, ``c`` oracle or harness artefact, ``d`` Neovim-specific
behaviour we accept. ``classify`` only guesses; a human confirms.

Examples
--------
>>> shape("3dwfxciwhello<Esc>")
'Ndwf{c}ciw{text}<Esc>'
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from vimtrainer_content import oracle
from vimtrainer_content.difftest.generate import Case, case_from_json, case_to_json, tokenize

MODES: Final = frozenset({
    "normal", "insert", "replace", "visual", "visual-line", "visual-block",
    "pending", "cmdline", "select", "other", "timeout", "error",
})
INCOMPLETE: Final = frozenset({"pending", "cmdline", "select", "other", "timeout", "error"})
FIELDS: Final = ("lines", "cursor", "mode")
CLASSES: Final = {
    "a": "emulator bug (fix in vimfixes.ts)",
    "b": "emulator limitation (supported_commands.md)",
    "c": "oracle or harness artefact",
    "d": "Neovim-specific, accepted",
}

# Exact codemirror-vim names, as the worker reports them (app/src/recorder.ts Mode, plus
# "pending" and "cmdline"), and a few spellings codemirror-vim itself uses.
_WEB_MODES: Final = {
    **{m: m for m in MODES},
    "visual line": "visual-line", "visualLine": "visual-line", "linewise": "visual-line",
    "visual block": "visual-block", "visualBlock": "visual-block", "blockwise": "visual-block",
}
# Shape regexes of keys codemirror-vim is known not to support (classify -> "b").
_LIMITATIONS: Final = re.compile(
    r"(?<![gv])U|g@|g[nN]|\"[1-9]"
    r"|(?:v|V|<C-v>)N?[ia][{}()\[\]bB]"
    r"|<C-v>.*[IAcCsS](?:\{text\}|<Tab>|<C-w>)*(?:<BS>|<CR>)"
)
_INDENT_ENTRY: Final = re.compile(r"[oO]|<CR>")
_OPERATORS: Final = frozenset({"d", "c", "y", "<", ">", "=", "g~", "gu", "gU", "g@", "gq", "gw", "gc", "!"})
_INSERTS: Final = frozenset({"i", "a", "I", "A", "o", "O", "s", "S", "C", "R", "gi", "gI"})
_ARG_KEYS: Final = frozenset({"f", "F", "t", "T", "r", "gr"})
_REG_KEYS: Final = frozenset({'"', "@", "m", "'", "`"})
_PREFIXES: Final = frozenset({"g", "z", "Z", "[", "]", "<C-w>"})
_LEAVE_INSERT: Final = frozenset({"<Esc>", "<C-c>", "<C-[>"})
_LEAVE_CMDLINE: Final = frozenset({"<CR>", "<Esc>", "<C-c>", "<NL>"})
_WORDS: Final = re.compile(r"[^\W\d]\w*")
_DIGITS: Final = re.compile(r"\d+")


@dataclass(frozen=True)
class Side:
    """One side's final state; ``cursor`` column in UTF-16 units, ``error`` an errmsg or harness error."""

    lines: tuple[str, ...]
    cursor: tuple[int, int]
    mode: str
    error: str | None = None


@dataclass
class Finding:
    """One divergence: the case, both sides, which fields differ, and its triage."""

    case: Case
    nvim: Side
    web: Side
    fields: list[str]
    cls: str
    shape: str
    minimised: str | None

    def to_json(self) -> dict[str, Any]:
        """Plain-JSON form for ``findings.jsonl``."""
        return {
            "case": case_to_json(self.case), "nvim": _side_to_json(self.nvim), "web": _side_to_json(self.web),
            "fields": list(self.fields), "class": self.cls, "shape": self.shape, "minimised": self.minimised,
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> Finding:
        """Inverse of ``to_json``."""
        return Finding(
            case_from_json(d["case"]), _side_from_json(d["nvim"]), _side_from_json(d["web"]),
            list(d["fields"]), d["class"], d["shape"], d.get("minimised"),
        )


# Public Functions =================================================================================


def nvim_side(outcome: oracle.Outcome) -> Side:
    """Side from an oracle outcome: map Neovim's raw mode and convert the byte column to UTF-16.

    Examples
    --------
    >>> o = oracle.Outcome("x", ["é1"], [1, 2], "n", False, False, "")
    >>> nvim_side(o)
    Side(lines=('é1',), cursor=(1, 1), mode='normal', error=None)
    """
    mode = nvim_mode(outcome.mode) if outcome.done else "pending"  # keys swallowed the end marker
    line, byte_col = int(outcome.cursor[0]), int(outcome.cursor[1])
    text = outcome.lines[line - 1] if 0 < line <= len(outcome.lines) else ""
    return Side(tuple(outcome.lines), (line, utf16_col(text, byte_col)), mode, outcome.errmsg or None)


def nvim_mode(raw: str) -> str:
    """Map ``nvim_get_mode().mode`` to a ``MODES`` name (``timeout`` passes through)."""
    if raw == "n":
        return "normal"
    if raw.startswith("no"):
        return "pending"
    if raw in ("i", "ic", "ix"):
        return "insert"
    if raw.startswith("R"):
        return "replace"
    if raw[:1] == "v":
        return "visual"
    if raw[:1] == "V":
        return "visual-line"
    if raw[:1] == "\x16":
        return "visual-block"
    if raw[:1] in ("s", "S", "\x13"):
        return "select"
    if raw[:1] == "c":
        return "cmdline"
    if raw == "timeout":
        return "timeout"
    return "other"


def utf16_col(line: str, byte_col: int) -> int:
    """UTF-16 code units in the first ``byte_col`` UTF-8 bytes of ``line``.

    Examples
    --------
    >>> utf16_col("a😀b", 5)
    3
    """
    prefix = line.encode()[:byte_col].decode(errors="ignore")
    return len(prefix.encode("utf-16-le")) // 2


def web_side(reply: dict[str, Any]) -> Side:
    """Side from a worker reply ``{"lines", "cursor", "mode"}`` or ``{"error"}``."""
    error = reply.get("error")
    if error:
        mode = "timeout" if str(error).startswith("timeout") else "error"
        return Side((), (0, 0), mode, str(error))
    line, col = reply["cursor"]
    return Side(tuple(reply["lines"]), (int(line), int(col)), _WEB_MODES.get(reply["mode"], "other"))


def compare(nvim: Side, web: Side) -> list[str]:
    """Names of the differing fields among ``lines/cursor/mode``; [] if equal or not comparable."""
    if nvim.mode in INCOMPLETE or web.mode in INCOMPLETE:
        return []
    return [f for f in FIELDS if getattr(nvim, f) != getattr(web, f)]


def classify(case: Case, nvim: Side, web: Side) -> str:
    """Guess the class of a divergence: ``c`` for errors and indent-only diffs, ``b`` for limitations, else ``a``."""
    if web.error and web.error.startswith("pageerror"):
        return "a"  # the emulator threw: a bug whatever Neovim did
    if nvim.error or web.error:
        return "c"
    if _LIMITATIONS.search(shape(case.keys)):
        return "b"
    if _is_indent_only(case.keys, nvim, web):
        return "c"
    return "a"


def shape(keys: str) -> str:
    """Normalise keys so similar findings collapse: counts -> ``N``, char args -> ``{c}``,
    insert text -> ``{text}``, words in search and ``:`` patterns -> ``{word}``.

    Registers, marks and named keys are kept. The mode tracking is approximate.

    Examples
    --------
    >>> shape(":s/foo/bar/g<CR>2@a")
    ':s/{word}/{word}/g<CR>N@a'
    """
    out: list[str] = []
    for role, tok in _scan(tokenize(keys)):
        if role == "count":
            if not out or out[-1] != "N":
                out.append("N")
        elif role == "arg":
            out.append("{c}")
        elif role == "text":
            if not out or out[-1] != "{text}":
                out.append("{text}")
        elif role in ("cmd", "search"):
            out.append(_shape_cmdline(tok, role))
        else:
            out.append(tok)
    return "".join(out)


def load_known(path: str | Path) -> list[dict[str, Any]]:
    """Read ``known.jsonl`` (one ``{shape, class, note, added, match?}`` per line); missing -> []."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def is_known(finding: Finding, known: list[dict[str, Any]]) -> bool:
    """True if a known entry covers the finding.

    An entry matches when its ``shape`` equals the shape of the finding's keys (the
    minimised keys when there are some, else the original), or when its optional ``match``
    regex is found in that shape. An entry with a ``fields`` list covers only findings whose
    differing fields are all in it, so a cursor-only entry cannot hide a lines or mode diff.
    """
    # Once minimised, the original keys no longer matter: they may contain a known shape
    # (a `U` somewhere) that has nothing to do with the divergence the minimiser isolated.
    if finding.minimised is not None:
        shapes = {finding.shape, shape(finding.minimised)}
    else:
        shapes = {finding.shape, shape(finding.case.keys)}
    for entry in known:
        if "fields" in entry and not set(finding.fields) <= set(entry["fields"]):
            continue
        if entry.get("shape") in shapes:
            return True
        pattern = entry.get("match")
        if pattern and any(re.search(pattern, s) for s in shapes):
            return True
    return False


def known_entry(finding: Finding, note: str, cls: str | None = None, today: datetime.date | None = None) -> dict:
    """A ``known.jsonl`` entry for a finding (``--accept``); dated today."""
    added = (today or datetime.date.today()).isoformat()
    return {"shape": finding.shape, "class": cls or finding.cls, "note": note, "added": added}


def render_summary(findings: list[Finding], stats: dict[str, Any]) -> str:
    """Markdown report: run stats, counts per class, then one row per finding grouped by class."""
    parts = ["# difftest summary", "", "| stat | value |", "|---|---|"]
    parts += [f"| {_cell(k)} | {_cell(v)} |" for k, v in stats.items()]
    parts.append("")
    if not findings:
        return "\n".join([*parts, "No findings.", ""])
    for cls, label in CLASSES.items():
        group = [f for f in findings if f.cls == cls]
        if not group:
            continue
        parts += [f"## Class {cls}: {label} ({len(group)})", "",
                  "| case | shape | keys | minimised | differs | buffer | nvim | web |",
                  "|---|---|---|---|---|---|---|---|"]
        parts += [_finding_row(f) for f in group]
        parts.append("")
    return "\n".join(parts)


# Private Functions ================================================================================


def _side_to_json(side: Side) -> dict[str, Any]:
    return {"lines": list(side.lines), "cursor": list(side.cursor), "mode": side.mode, "error": side.error}


def _side_from_json(d: dict[str, Any]) -> Side:
    return Side(tuple(d["lines"]), tuple(d["cursor"]), d["mode"], d.get("error"))


def _is_indent_only(keys: str, nvim: Side, web: Side) -> bool:
    """Lines differ only in leading whitespace after a key that opens a new line (o, O, <CR>)."""
    if not _INDENT_ENTRY.search(keys) or len(nvim.lines) != len(web.lines) or nvim.lines == web.lines:
        return False
    return all(a.lstrip() == b.lstrip() for a, b in zip(nvim.lines, web.lines))


def _scan(tokens: list[str]) -> list[tuple[str, str]]:
    """Label each token with a role (``key count arg reg text cmd search``) by tracking the mode.

    Insert text and command-line text come back as one token per run. Approximate: enough
    for shapes and limitation matching, not a Vim parser.
    """
    out: list[tuple[str, str]] = []
    state = {"mode": "normal", "op": False, "obj": False, "count": False, "recording": False}
    pending_arg: str | None = None
    prefix = ""
    for tok in tokens:
        mode = state["mode"]
        if mode == "insert":
            _scan_insert(tok, out, state)
            continue
        if mode in ("cmd", "search"):
            _scan_cmdline(tok, out, state)
            continue
        if pending_arg is not None:
            role = pending_arg if not (tok.startswith("<") and len(tok) > 1) else "key"
            out.append((role, tok))
            pending_arg = None
            if state["op"]:
                _finish_operator(state)
            continue
        if prefix:
            tok, prefix = prefix + tok, ""
        elif tok in _PREFIXES and not state["obj"]:
            prefix = tok
            continue
        pending_arg = _scan_normal(tok, out, state)
    if prefix:
        out.append(("key", prefix))
    return out


def _scan_insert(tok: str, out: list[tuple[str, str]], state: dict):
    if tok in _LEAVE_INSERT:
        state["mode"] = "normal"
        out.append(("key", tok))
    elif len(tok) == 1:
        out.append(("text", tok))
    else:
        out.append(("key", tok))


def _scan_cmdline(tok: str, out: list[tuple[str, str]], state: dict):
    role = state["mode"]
    if tok in _LEAVE_CMDLINE:
        state["mode"] = "normal"
        out.append(("key", tok))
        if state["op"] and tok != "<Esc>":
            _finish_operator(state)
        state["op"] = False
    elif out and out[-1][0] == role:
        out[-1] = (role, out[-1][1] + tok)
    else:
        out.append((role, tok))


def _scan_normal(tok: str, out: list[tuple[str, str]], state: dict) -> str | None:
    """Label one normal/visual/operator-pending token; returns the role of a following argument."""
    if state["obj"]:
        state["obj"] = False
        out[-1] = ("key", out[-1][1] + tok)
        if state["op"]:
            _finish_operator(state)
        return None
    if tok.isdigit() and (tok != "0" or state["count"]):
        state["count"] = True
        out.append(("count", tok))
        return None
    state["count"] = False
    out.append(("key", tok))
    visual = state["mode"].startswith("visual")
    if tok in ("v", "V", "<C-v>"):
        state["mode"] = "normal" if visual else "visual"
        return None
    if tok in ("<Esc>", "<C-c>"):
        state.update(mode="normal", op=False)
        return None
    if tok == ":":
        state.update(mode="cmd", op=False)
        return None
    if tok in ("/", "?"):
        state["mode"] = "search"
        return None
    if tok == "q":
        state["recording"] = not state["recording"]
        return "reg" if state["recording"] else None
    if tok in _ARG_KEYS:
        return "arg"
    if tok in _REG_KEYS:
        return "reg"
    if tok in ("i", "a") and (state["op"] or visual):
        state["obj"] = True
        return None
    if tok in _OPERATORS or (tok in ("~", "u", "U", "J") and visual):
        if visual or state["op"]:
            state["op"] = tok
            _finish_operator(state)
        else:
            state["op"] = tok
        return None
    if state["op"]:
        _finish_operator(state)
        return None
    if tok in _INSERTS or (visual and tok in ("I", "A")):
        state["mode"] = "insert"
    return None


def _finish_operator(state: dict):
    """The pending operator got its motion: ``c`` enters insert mode, the rest return to normal."""
    op = state["op"]
    state["op"] = False
    state["mode"] = "insert" if op == "c" else "normal"


def _shape_cmdline(text: str, role: str) -> str:
    """Search text -> ``{word}`` per word; ``:`` text keeps commands but patterns between ``/`` become words."""
    if role == "search":
        return _DIGITS.sub("N", _WORDS.sub("{word}", text))
    parts = text.split("/")
    patterns = 2 if parts[0].endswith("s") else 1  # :s/pat/rep/flags vs :g/pat/cmd
    shaped = [_WORDS.sub("{word}", p) if 0 < i <= patterns else p for i, p in enumerate(parts)]
    return _DIGITS.sub("N", "/".join(shaped))


def _finding_row(f: Finding) -> str:
    nvim = f"{f.nvim.mode} {list(f.nvim.cursor)}"
    web = f"{f.web.mode} {list(f.web.cursor)}"
    minimised = _code(f.minimised) if f.minimised is not None else "-"
    cells = [f"{f.case.seed}/{f.case.index}", _code(f.shape), _code(f.case.keys), minimised,
             ", ".join(f.fields), f.case.buffer.id, nvim, web]
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _code(text: str) -> str:
    """Inline code that survives backticks in the keys."""
    fence = "``" if "`" in text else "`"
    pad = " " if "`" in text else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")

