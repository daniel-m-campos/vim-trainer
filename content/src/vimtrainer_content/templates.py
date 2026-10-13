"""Templates: turn a (snippet window, syntax node) pair into exercise drafts.

Each template knows the skill it drills, how to phrase the task, how to compute
``expect``, and one or more *variants*: canonical solutions that all use the drilled
skill. The build replays every variant in Neovim and keeps the shortest one that passes
as ``par.keys`` (so a template does not have to guess, for example, whether ``:%s`` needs
``\\<..\\>`` or the ``g`` flag). ``alternates`` are other known-good solutions;
``idioms`` are extra par-search candidates that do not use the skill (``cw`` instead of
``ciw``); ``forbid`` lists shortcuts that make the drill pointless if they pass.

All choices that look random (cursor offset, replacement text, direction) are a
``stable_hash`` of the window and node, so a rebuild produces the same exercises.
"""

from __future__ import annotations

import builtins
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Final

import tree_sitter

from vimtrainer_content.lang import Language
from vimtrainer_content.snippets import Window, pick, stable_hash

MAX_PER_WINDOW: Final = 2  # drafts kept per (window, template, skill), spreads exercises across code
# Kind rule for Ex drills. "ex" (the solution must use a `:` command) only where the
# normal-mode way is a repetition drill rather than a skill: :g, :v and :normal over
# EX_MIN_LINES or more lines, and :%s over more than SUBST_EDIT_MAX occurrences. With
# SUBST_EDIT_MAX or fewer, `cgn` + `.` is a real normal-mode idiom, so the kind is "edit".
EX_MIN_LINES: Final = 3
SUBST_EDIT_MAX: Final = 3

# Replacement text is chosen to fit the node it replaces (see _fit_value and _new_name):
# a string gets a string, a number a number, an identifier a name in the same case style
# and of the same role. Never "value" or "X": a task should read like a real edit.
WORD_STRINGS: Final = ("unknown", "pending", "default", "missing", "skipped", "empty")
MESSAGE_STRINGS: Final = ("not found", "invalid input", "out of range", "already exists", "try again", "no match")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")
FLOAT_TEXTS: Final = ("0.0", "0.5", "1.5", "2.0")
SLICE_TEXTS: Final = ("1:", ":-1", "::2", "2:")
BRACE_TEXTS: Final = ("**defaults", "'id': 0", "'name': name")
RHS_BY_TYPE: Final = {
    "list": "[]", "list_comprehension": "[]", "dictionary": "{}", "dictionary_comprehension": "{}",
    "set": "set()", "set_comprehension": "set()", "tuple": "()", "call": "None", "binary_operator": "0",
    "true": "False", "false": "True", "none": "0", "conditional_expression": "None",
}
# Role -> names, in snake_case; _styled converts them to the old name's case style.
ROLE_NAMES: Final = {
    "many": ("items", "entries", "records", "rows", "parts", "names"),
    "count": ("total", "count", "size", "limit", "offset", "amount"),
    "index": ("pos", "position", "idx", "start", "cursor"),
    "text": ("text", "label", "message", "title", "word"),
    "call": ("process", "handle", "compute", "convert", "build", "parse_input", "load"),
    "class": ("record", "entry", "handler", "builder", "parser", "node"),
    "any": ("item", "result", "entry", "current", "record", "target", "source", "data"),
}
_ROLE_WORDS: Final = {
    "many": {"list", "items", "values", "keys", "rows", "cols", "lines", "words", "names", "dict", "set", "map",
             "nums", "numbers", "chars", "letters", "data", "elements", "entries", "results", "parts"},
    "count": {"count", "num", "number", "total", "size", "len", "length", "n", "max", "min", "limit", "sum",
              "amount", "width", "height", "score", "age", "year", "month", "day", "rate"},
    "index": {"idx", "index", "i", "j", "k", "pos", "position", "start", "end", "offset", "row", "col"},
    "text": {"name", "text", "str", "string", "word", "line", "msg", "message", "label", "title", "char",
             "letter", "sentence", "phrase", "prefix", "suffix"},
}
ORDINAL_WORDS: Final = ("", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
_DELIM_NAMES: Final = {"(": "parentheses", "[": "brackets", "{": "braces", '"': "quotes", "'": "quotes"}
_BUILTINS: Final = frozenset(dir(builtins))
CURSOR_IDIOMS: Final = (
    "w", "b", "e", "W", "B", "E", "ge", "2w", "3w", "4w", "2W", "3W", "2e", "2E", "$", "0", "^", "g_",
    "%", "])", "]}", "[(", "[{", "}", "{", "G", "gg", "H", "M", "L", "+", "-", "j", "k", "2j", "2k",
    "3j", "3k", "*", "#",
)
_NOUNS: Final = {
    "string": "string", "argument_list": "argument list", "parameters": "parameter list",
    "parenthesized_expression": "parenthesised expression", "tuple": "tuple", "list": "list",
    "list_comprehension": "list comprehension", "subscript": "subscript", "dictionary": "dict",
    "set": "set", "dictionary_comprehension": "dict comprehension", "set_comprehension": "set comprehension",
    "interpolation": "f-string field",
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), '"': (), "'": ()}
_ONE_LINE_DOC: Final = re.compile(r"\s*(\"\"\"|\'\'\').*\1")
_REGEXISH: Final = re.compile(r"[\^$|\\]|\(\?|\[\^|[.)\]][*+?]")


@dataclass
class Draft:
    """An exercise before oracle verification."""

    template: str
    skill: str
    kind: str
    task: str
    lines: list[str]
    cursor: list[int]  # [line 1-based, byte column 0-based]
    expect: dict[str, Any]
    variants: list[str]
    target: list[dict[str, list[int]]]
    window: Window = field(repr=False)
    alternates: list[str] = field(default_factory=list)
    idioms: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    typed: int = 0  # characters every solution has to type (inserted text, new names)
    typed_per_line: bool = False  # ``typed`` goes onto every changed line (gates.anti_shortcut_problem)
    params: dict[str, Any] = field(default_factory=dict)
    hints: list[dict[str, str | None]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Stable 10-hex id from the content of the exercise."""
        return stable_hash(self.window.key, self.template, self.skill, self.lines, self.cursor, self.expect)[:10]

    def exercise(self, lang: str) -> dict[str, Any]:
        """Oracle-ready exercise dict (par filled in later by the build)."""
        ex = {
            "skill": self.skill, "lang": lang, "kind": self.kind,
            "start": {"lines": self.lines, "cursor": self.cursor}, "expect": self.expect,
            "par": {"keys": self.variants[0]}, "alternates": self.alternates, "params": self.params,
        }
        if self.typed_per_line:
            ex["typed_per_line"] = True  # read by gate 5; build.evaluate does not ship it
        return ex


NodeTemplate = Callable[[Window, tree_sitter.Node, str, Language], Iterator[Draft]]
LineTemplate = Callable[[Window, str, Language], Iterator[Draft]]


# Public Functions =================================================================================


def generate(win: Window, lang: Language) -> list[Draft]:
    """All drafts for one window, at most MAX_PER_WINDOW per (template, skill), deduplicated."""
    win.cache.clear()  # "seen" sets live here; a second call must start from scratch
    groups: dict[tuple[str, str], dict[str, Draft]] = {}
    for draft in _all_drafts(win, lang):
        groups.setdefault((draft.template, draft.skill), {}).setdefault(draft.uid, draft)
    out = []
    for drafts in groups.values():
        out.extend(sorted(drafts.values(), key=lambda d: d.uid)[:MAX_PER_WINDOW])
    return out


def ordinal(n: int) -> str:
    """1 -> 'first'."""
    return ORDINAL_WORDS[n] if 0 < n < len(ORDINAL_WORDS) else f"{n}th"


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>``: replace the contents of a single-line delimited node."""
    span = _inner_span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    text = _inner_text(win, node, inner)
    if text is None or text == inner:
        return
    c, noun = _PAIR[o], _NOUNS[node.type]
    yield Draft(
        template="change_inner", skill=skill, kind="edit",
        task=f"Change the contents of {_the(win, node, noun)} to `{text}`",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, oc + 1, cc, text)},
        variants=[f"ci{o}{text}<Esc>"], alternates=[f"ci{a}{text}<Esc>" for a in _ALIASES[o]],
        idioms=[f"{m}{text}<Esc>" for m in ("ciw", "ciW", "cw", "cW", "ce", "cE", f"ct{c}", f"cT{o}", "bcw",
                                             f"F{o}lct{c}", f"T{o}ct{c}", f"di{o}i")],
        typed=len(text), params={"text": text, "open": o, "close": c},
        target=[_range(row, oc, row, cc)], window=win, tags=[node.type, "change"],
        hints=[
            {"trigger": "^[0-9]*[hlwbeWBE]", "text": f"ci{o} works from anywhere inside the {noun}; no need to move first."},
            {"trigger": "^[0-9]*[fFtT]", "text": f"ci{o} finds the enclosing {o}{c} by itself; the jump is not needed."},
            {"trigger": "x{2,}|<Del>|(<BS>){2,}", "text": f"ci{o} deletes the whole contents in one command."},
            {"trigger": None, "text": f"ci{o}: change inside the {o}{c} pair around the cursor."},
        ],
    )


def delete_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``di{delim}``: empty a single-line delimited node."""
    span = _inner_span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    c, noun = _PAIR[o], _NOUNS[node.type]
    yield Draft(
        template="delete_inner", skill=skill, kind="edit",
        task=f"Delete everything inside {_the(win, node, noun)}, keeping the {_DELIM_NAMES[o]}",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, oc + 1, cc, "")},
        variants=[f"di{o}"], alternates=[f"di{a}" for a in _ALIASES[o]],
        idioms=["diw", "diW", "dw", "dW", "de", "dE", f"dt{c}", f"dT{o}", "bdt" + c, f"F{o}ldt{c}", f"T{o}dt{c}", "D"],
        params={"open": o, "close": c}, target=[_range(row, oc, row, cc)], window=win, tags=[node.type, "delete"],
        hints=[
            {"trigger": "^[0-9]*[hlwbeWBEfFtT]", "text": f"di{o} works from anywhere inside the {noun}."},
            {"trigger": "x{2,}|d[wWeE]", "text": f"di{o} empties the {o}{c} pair in one command, whatever is inside."},
            {"trigger": None, "text": f"di{o}: delete inside the {o}{c} pair around the cursor."},
        ],
    )


def delete_around(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``da(`` / ``da[``: drop a call's argument list or a subscript, delimiters included."""
    span = _inner_span(win, node)
    if span is None or node.type not in ("subscript", "argument_list"):
        return
    row, oc, cc, o = span
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    c = _PAIR[o]
    head = node.child_by_field_name("value") if node.type == "subscript" else node.parent.child_by_field_name("function")
    if head is None or head.end_point.row != row:
        return
    name = _text(head)
    if node.type == "argument_list" and name in _BUILTINS:
        return  # `len(x)` -> `len` is not an edit anyone makes; user functions passed as callbacks are
    task = (f"Turn `{name}{win.lines[row][oc:cc + 1]}` into `{name}` by deleting the subscript" if node.type == "subscript"
            else f"Turn the call `{name}(...)` into the bare name `{name}`")
    yield Draft(
        template="delete_around", skill=skill, kind="edit", task=task,
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, oc, cc + 1, "")},
        variants=[f"da{o}"], alternates=[f"da{a}" for a in _ALIASES[o]],
        idioms=[f"F{o}d%", f"[{o}d%" if o in "({" else f"F{o}df{c}", f"F{o}df{c}", f"F{o}D", "daw", "daW", "dW", "D"],
        params={"open": o, "close": c}, target=[_range(row, oc, row, cc)], window=win, tags=[node.type, "delete"],
        hints=[
            {"trigger": "^[0-9]*[fFtT]|^%|^\\[", "text": f"da{o} works from anywhere inside and takes the {o}{c} with it."},
            {"trigger": "x{2,}|d[wWeE]", "text": f"da{o} deletes the pair and everything inside in one command."},
            {"trigger": None, "text": f"da{o}: delete around, the {o}{c} pair included."},
        ],
    )


def change_nth_arg(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}f,wct,X<Esc>``: change the n-th argument of a single-line call from the call start."""
    call = node.parent
    if call is None or call.type != "call" or node.start_point.row != node.end_point.row:
        return
    row = node.start_point.row
    if call.start_point.row != row:
        return
    args = [a for a in node.named_children if a.type != "comment"]
    if len(args) < 2:
        return
    n = pick(range(2, len(args) + 1), win.key, node.start_point, "nth")
    arg = args[n - 1]
    line, a0, a1 = win.lines[row], arg.start_point.column, arg.end_point.column
    value = line[a0:a1]
    if not re.fullmatch(r"[\w.+\-*/ '\"]+", value) or a1 >= len(line) or line[a1] not in ",)":
        return
    cursor, d = call.start_point.column, line[a1]
    k = line[cursor:a0].count(",")
    if k < 1:
        return
    text = _fit_value(win, arg, "arg")
    if text is None or text == value:
        return
    fk = f"{k}f," if k > 1 else "f,"
    kd = line[cursor + 1:a1 + 1].count(d)
    fd = f"{kd}f{d}" if kd > 1 else f"f{d}"
    fn = _text(call.child_by_field_name("function"))
    yield Draft(
        template="change_nth_arg", skill=skill, kind="edit",
        task=f"Change the {ordinal(n)} argument of `{fn}(...)` from `{value}` to `{text}`",
        lines=win.lines, cursor=[row + 1, cursor], expect={"lines": _replace(win.lines, row, a0, a1, text)},
        variants=[f"{fk}w{m}{text}<Esc>" for m in (f"ct{d}", "cw", "ce", "cE", "cW")],
        alternates=[f"f,{';' * (k - 1)}wct{d}{text}<Esc>"] if k > 1 else [],
        idioms=[f"{fd}cT{line[a0 - 1]}{text}<Esc>", f"{fk}lct{d}{text}<Esc>", f"{fk}wC{text}{line[a1:]}<Esc>"],
        typed=len(text), params={"text": text, "n": n, "char": ","},
        target=[_range(row, a0, row, a1 - 1)], window=win, tags=["call-argument", "find", "change"],
        hints=[
            {"trigger": "^[0-9]*[wWeEl]{3,}", "text": f"{fk} jumps straight to the comma before the {ordinal(n)} argument."},
            *([{"trigger": "^f,;", "text": f"A count on f ({fk}) replaces the ; presses."}] if k > 1 else []),
            {"trigger": "x{2,}|d[wWeE]", "text": f"ct{d} changes up to the next {d} without deleting first."},
            {"trigger": None, "text": f"{fk}w puts you on the argument; ct{d} changes it up to the {d}."},
        ],
    )


def change_kwarg_value(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ct,X<Esc>`` (or ``cw``/``ce``): change a keyword argument's value, cursor on the value."""
    name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
    if name is None or value is None or value.start_point.row != value.end_point.row:
        return
    row, v0, v1 = value.start_point.row, value.start_point.column, value.end_point.column
    line = win.lines[row]
    old = line[v0:v1]
    if len(old) < 2 or not re.fullmatch(r"[\w.'\"+-]+", old):
        return
    text = _fit_value(win, value, "kw")
    if text is None or text == old:
        return
    d = line[v1] if v1 < len(line) else ""
    if d and d in old:
        return
    motions = [f"ct{d}"] if d in (",", ")") else []
    motions += ["cw", "ce", "cE", "cW"] + (["C"] if v1 == len(line) else [])
    variants = [f"{m}{text}<Esc>" for m in motions]
    if skill == "m.find":
        yield from _kwarg_find(win, name, value, old, text, motions, skill)
        return
    yield Draft(
        template="change_kwarg_value", skill=skill, kind="edit",
        task=f"Change the value of `{_text(name)}=` from `{old}` to `{text}`",
        lines=win.lines, cursor=[row + 1, v0], expect={"lines": _replace(win.lines, row, v0, v1, text)},
        variants=variants, alternates=[f"dt{d}i{text}<Esc>"] if d in (",", ")") else [],
        idioms=[f"s{text}<Esc>", f"S{text}<Esc>", f"v{len(old) - 1}lc{text}<Esc>" if len(old) > 1 else "vc"],
        typed=len(text), params={"text": text},
        target=[_range(row, v0, row, v1 - 1)], window=win, tags=["keyword-argument", "change"],
        hints=[
            {"trigger": "^(x|d)", "text": "c{motion} deletes and enters insert mode in one step."},
            {"trigger": "^v", "text": "An operator plus a motion (ct, cw) needs no visual selection."},
            {"trigger": None, "text": "ct, changes up to the comma; cw is enough when the value is one word."},
        ],
    )


def _kwarg_find(win: Window, name, value, old: str, text: str, motions: list[str], skill: str) -> Iterator[Draft]:
    """m.find form of change_kwarg_value: cursor on the line's first non-blank, ``{k}f=l`` first."""
    row, v0, v1 = value.start_point.row, value.start_point.column, value.end_point.column
    line = win.lines[row]
    start, eq = _indent(line), v0 - 1
    if eq <= start or line[eq] != "=" or row in _prose_rows(win):
        return
    k = line[start:eq + 1].count("=")
    fk = f"{k}f=" if k > 1 else "f="
    d = line[v1] if v1 < len(line) else ""
    yield Draft(
        template="change_kwarg_value", skill=skill, kind="edit",
        task=f"Change the value of `{_text(name)}=` from `{old}` to `{text}`",
        lines=win.lines, cursor=[row + 1, start], expect={"lines": _replace(win.lines, row, v0, v1, text)},
        variants=[f"{fk}l{m}{text}<Esc>" for m in motions],
        alternates=[f"f={';' * (k - 1)}l{motions[0]}{text}<Esc>"] if k > 1 else [],
        idioms=[f"{j}{m}{text}<Esc>" for j in ("W", "2W", "3W", "4W", "5W", "w", "2w", "3w", "4w", "5w", "6w",
                                               f"f{old[0]}", f"2f{old[0]}", f"F{old[0]}", f"{fk}") for m in motions[:1]],
        typed=len(text), params={"text": text, "char": "=", "n": k},
        target=[_range(row, v0, row, v1 - 1)], window=win, tags=["keyword-argument", "find", "change"],
        hints=[
            {"trigger": "^[0-9]*[wWeEl]{2,}", "text": f"{fk} jumps to the `=` of `{_text(name)}=`; l steps onto the value."},
            *([{"trigger": "^f=;", "text": f"A count on f ({fk}) replaces the ; presses."}] if k > 1 else []),
            {"trigger": "x{2,}|d[wWeEt]", "text": "c{motion} deletes and enters insert mode in one step."},
            {"trigger": None, "text": f"{fk}l puts you on the value; {motions[0]} changes it."},
        ],
    )


def change_to_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``CX<Esc>``: replace the right-hand side of a one-line assignment, cursor on it."""
    if node.named_child_count != 1 or node.named_children[0].type != "assignment":
        return
    assign = node.named_children[0]
    left, right = assign.child_by_field_name("left"), assign.child_by_field_name("right")
    if left is None or right is None or node.start_point.row != node.end_point.row:
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old = line[r0:r1]
    if r1 != len(line) or len(old) < 6:
        return
    text = _fit_value(win, right, "rhs")
    if text is None or text == old:
        return
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to `{_text(left)}` with `{text}`",
        lines=win.lines, cursor=[row + 1, r0], expect={"lines": _replace(win.lines, row, r0, r1, text)},
        variants=[f"C{text}<Esc>", f"c${text}<Esc>"], alternates=[f"Da{text}<Esc>"],
        idioms=[f"cW{text}<Esc>", f"cw{text}<Esc>", f"ce{text}<Esc>"],
        typed=len(text), params={"text": text},
        target=[_range(row, r0, row, r1 - 1)], window=win, tags=["assignment", "change"],
        hints=[
            {"trigger": "^(D|d\\$)", "text": "C deletes to the end of the line and enters insert mode in one key."},
            {"trigger": "x{3,}|^c[wWeE]", "text": "C changes everything from the cursor to the end of the line."},
            {"trigger": None, "text": "C = c$: change to the end of the line."},
        ],
    )


def jump_match(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``%``: from one bracket to its partner (either direction, possibly across lines)."""
    pair = _bracket_pair(node)
    if pair is None:
        return
    (orow, ocol, o), (crow, ccol, c) = pair
    forward = pick((True, False), win.key, node.start_point, "dir")
    here, there = ((orow, ocol), (crow, ccol)) if forward else ((crow, ccol), (orow, ocol))
    a, b = (o, c) if forward else (c, o)
    yield Draft(
        template="jump_match", skill=skill, kind="cursor",
        task=f"Jump from this `{a}` to its matching `{b}`",
        lines=win.lines, cursor=[here[0] + 1, here[1]], expect={"cursor": [there[0] + 1, there[1]]},
        variants=["%"], idioms=[*CURSOR_IDIOMS, f"f{b}", f"F{b}", f"2f{b}", f"2F{b}"],
        target=[_range(there[0], there[1], there[0], there[1])], window=win, tags=[node.type, "bracket"],
        hints=[
            {"trigger": "^[0-9]*[fFtT]", "text": "% jumps to the matching bracket in one key, across lines too."},
            {"trigger": "[jklhwb]{3,}", "text": "% finds the partner of the bracket under the cursor."},
            {"trigger": None, "text": "% jumps between matching (), [] and {}."},
        ],
    )


def jump_block_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``])`` / ``]}`` (or ``[(`` / ``[{``): jump to the enclosing unmatched bracket."""
    pair = _bracket_pair(node)
    if pair is None or pair[0][2] not in "({":
        return
    (orow, ocol, o), (crow, ccol, c) = pair
    to_end = pick((True, True, False), win.key, node.start_point, "end")
    strings = _string_cells(win)
    positions = [p for p in _depth0_positions(win, (orow, ocol), (crow, ccol), o, c)
                 if p not in strings and not _first_on_line(win.lines, p, (crow, ccol) if to_end else (orow, ocol), c if to_end else o, to_end)]
    if not positions:
        return
    row, col = pick(positions, win.key, node.start_point, "pos")
    there, keys, ch = ((crow, ccol), f"]{c}", c) if to_end else ((orow, ocol), f"[{o}", o)
    word = "closes" if to_end else "opens"
    yield Draft(
        template="jump_block_end", skill=skill, kind="cursor",
        task=f"Jump to the `{ch}` that {word} the {_NOUNS.get(node.type, 'bracket pair')} around the cursor",
        lines=win.lines, cursor=[row + 1, col], expect={"cursor": [there[0] + 1, there[1]]},
        variants=[keys], idioms=[*CURSOR_IDIOMS, f"f{ch}", f"F{ch}", f"2f{ch}", f"2F{ch}", f"t{ch}l", f"T{ch}h"],
        forbid=[f"f{ch}" if to_end else f"F{ch}"],
        target=[_range(there[0], there[1], there[0], there[1])], window=win, tags=[node.type, "bracket"],
        hints=[
            {"trigger": "^[0-9]*[fFtT]", "text": f"{keys} jumps to the enclosing {ch} even with nested pairs or lines in between."},
            {"trigger": "%", "text": f"% needs the cursor on a bracket; {keys} works from anywhere inside."},
            {"trigger": None, "text": f"{keys}: go to the unmatched {ch} that encloses the cursor."},
        ],
    )


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f#D``: delete the comment at the end of a code line, cursor at the line's first non-blank."""
    row, ccol = node.start_point.row, node.start_point.column
    line = win.lines[row]
    indent = len(line) - len(line.lstrip())
    if not line[indent:ccol].strip():
        return
    lead = lang.comment_leader
    k = line[indent:ccol].count(lead[0])
    fk = f"{k + 1}f{lead[0]}" if k else f"f{lead[0]}"
    yield Draft(
        template="delete_trailing_comment", skill=skill, kind="edit",
        task="Delete the comment at the end of this line",
        lines=win.lines, cursor=[row + 1, indent], expect={"lines": _replace(win.lines, row, ccol, len(line), "")},
        variants=[f"{fk}D", f"{fk}d$"], alternates=[f"{fk}hD"],
        idioms=[f"$F{lead[0]}D", f"$F{lead[0]}hD", f"f{lead[0]}D", "D", "$d0"],
        params={"char": lead[0], "n": k + 1}, target=[_range(row, ccol, row, len(line) - 1)], window=win,
        tags=["comment", "find", "delete"],
        hints=[
            {"trigger": "^[0-9]*[wWeEl]{3,}|^\\$", "text": f"f{lead[0]} jumps to the comment, then D deletes to the end of the line."},
            {"trigger": "x{3,}", "text": "D deletes from the cursor to the end of the line in one key."},
            *([{"trigger": f"^f{_js_escape(lead[0])};", "text": f"A count picks the right {lead[0]} directly: {fk}."}] if k else []),
            {"trigger": None, "text": f"{fk}D: find the comment leader, delete to the end of the line."},
        ],
    )


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{N}dd`` (or ``d}``, ``dap``): delete a whole function / if / for statement."""
    if node.parent is not None and node.parent.type == "decorated_definition":
        node = node.parent
    start, end = node.start_point.row, node.end_point.row
    n = end - start + 1
    if not 4 <= n <= 20 or len(win.lines) - n < 4 or node.start_point.column != _indent(win.lines[start]):
        return
    inner = node.child_by_field_name("definition") or node
    name = inner.child_by_field_name("name")
    what = {"function_definition": f"the function `{_text(name)}`" if name else "this function",
            "if_statement": "this `if` statement", "for_statement": "this `for` loop"}.get(inner.type, "this statement")
    yield Draft(
        template="delete_lines", skill=skill, kind="edit", task=f"Delete {what} ({n} lines)",
        lines=win.lines, cursor=[start + 1, node.start_point.column],
        expect={"lines": win.lines[:start] + win.lines[end + 1:]},
        variants=["d}", "dG", "dap", "dip", f"{n}dd", f"d{n - 1}j"], alternates=[f"V{n - 1}jd"],
        idioms=["dgg", "D"], target=[_range(start, 0, end, max(len(win.lines[end]) - 1, 0))], window=win,
        tags=[inner.type, "delete", "lines"],
        hints=[
            {"trigger": "(dd){2,}|(dd\\.)", "text": f"{n}dd deletes {n} lines in one command; d}} stops at the next blank line."},
            {"trigger": "^V", "text": "A count or a motion after d avoids the visual selection."},
            {"trigger": None, "text": f"{n}dd, d{n - 1}j and d}} all delete the block; pick the shortest that fits."},
        ],
    )


def indent_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{N}>>`` / ``{N}<<``: fix a block body that is one level under- or over-indented."""
    parent = node.parent
    start, end = node.start_point.row, node.end_point.row
    n = end - start + 1
    if parent is None or start == parent.start_point.row or not 2 <= n <= 12:
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    rows = range(start, end + 1)
    if under and any(win.lines[r] and not win.lines[r].startswith("    ") for r in rows):
        return
    lines = [(ln[4:] if under else "    " + ln) if r in rows and ln else ln for r, ln in enumerate(win.lines)]
    op, verb = (">>", "Indent") if under else ("<<", "Dedent")
    header = win.lines[parent.start_point.row].strip()
    problem = "lost one level of indent" if under else "is indented one level too deep"
    yield Draft(
        template="indent_block", skill=skill, kind="edit",
        task=f"The body of `{_clip(header)}` {problem}. {verb} these {n} lines",
        lines=lines, cursor=[start + 1, _indent(lines[start])], expect={"lines": win.lines},
        variants=[f"{op[0]}}}", f"{op[0]}G", f"{op[0]}ip", f"{n}{op}", f"{op[0]}{n - 1}j"],
        alternates=[f"V{n - 1}j{op[0]}"], idioms=[f"{op[0]}ap"],
        target=[_range(start, 0, end, max(len(lines[end]) - 1, 0))], window=win, tags=["block", "indent"],
        hints=[
            {"trigger": f"({op}j)|({op}\\.)|(j\\.)", "text": f"{n}{op} shifts all {n} lines in one command."},
            {"trigger": "^[0-9]*I|^\\^?i", "text": f"{op} shifts by shiftwidth; there is no need to type spaces."},
            {"trigger": None, "text": f"{n}{op} or {op[0]}{n - 1}j shift {n} lines; {op[0]}}} shifts up to the next blank line."},
        ],
    )


def upper_word(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUiw`` / ``guiw``: change the case of one identifier, cursor inside it."""
    name = _text(node)
    upper = bool(re.fullmatch(r"[a-z][a-z0-9_]{4,}", name))
    lower = bool(re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", name)) and any(ch.isalpha() for ch in name)
    if not (upper or lower) or name in lang.keywords or name in _BUILTINS or _seen(win, "case", name):
        return
    parent = node.parent
    module = parent is not None and (parent.type in ("dotted_name", "aliased_import") or (
        parent.type == "attribute" and parent.child_by_field_name("object") == node))
    if upper and (_role(node, name) in ("call", "class") or _is_member(node) or module):
        return  # an uppercased function, attribute or module name reads as a mistake, not an edit
    row, c0 = node.start_point.row, node.start_point.column
    col = c0 + pick(range(1, len(name)), win.key, node.start_point, "case")
    new = name.upper() if upper else name.lower()
    op, verb = ("gU", "Uppercase") if upper else ("gu", "Lowercase")
    yield Draft(
        template="upper_word", skill=skill, kind="edit",
        task=(f"Make `{name}` a constant name: uppercase it to `{new}`" if upper
              else f"Lowercase the constant name `{name}` to `{new}`"),
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, c0, c0 + len(name), new)},
        variants=[f"{op}iw", f"viw{op[1]}"], alternates=["g~iw", f"{op}aw"],
        idioms=[f"b{op}e", f"b{op}w", f"{op}e", f"{op}E", f"b{op}E", f"ciw{new}<Esc>"],
        typed=0, params={"word": name}, target=[_range(row, c0, row, c0 + len(name) - 1)], window=win,
        tags=["identifier", "case"],
        hints=[
            {"trigger": "^~|~~", "text": f"{op}iw changes the whole word in one command; ~ flips one character."},
            {"trigger": "^(b|0|\\^)", "text": "iw works from anywhere in the word; no need to move to its start."},
            {"trigger": "^c|^s|^x", "text": f"{op} changes case without retyping the word."},
            {"trigger": None, "text": f"{op}iw: {verb.lower()} inner word."},
        ],
    )


def upper_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUi"``: uppercase the text inside a string."""
    span = _inner_span(win, node)
    if span is None:
        return
    row, oc, cc, q = span
    inner = win.lines[row][oc + 1:cc]
    if not (4 <= len(inner) <= 30 and re.fullmatch(r"[a-z][a-z ,.:!?_-]*", inner)):
        return
    col = _cursor_inside(win, node, row, oc, cc, q)
    if col is None:
        return
    yield Draft(
        template="upper_inner", skill=skill, kind="edit", task=f"Uppercase the text inside the string `{q}{inner}{q}`",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, oc + 1, cc, inner.upper())},
        variants=[f"gUi{q}"], alternates=[f"vi{q}U", f"g~i{q}"],
        idioms=["gUiw", "gUiW", "gUt" + q, "gUT" + q, f"ci{q}{inner.upper()}<Esc>"],
        params={"text": inner.upper()}, target=[_range(row, oc, row, cc)], window=win, tags=["string", "case"],
        hints=[
            {"trigger": "^gUi?w|^gU[eE]", "text": f"gUi{q} covers the whole string, spaces and punctuation included."},
            {"trigger": "^c|^s", "text": "gU changes case without retyping."},
            {"trigger": None, "text": f"gUi{q}: uppercase inside the quotes."},
        ],
    )


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ciwX<Esc>``: rename one occurrence, cursor in the middle of the word."""
    name = _text(node)
    if len(name) < 4 or name in lang.keywords or not re.fullmatch(r"\w+", name) or _is_member(node):
        return
    if name in _BUILTINS or _is_dunder(name) or _seen(win, "word", name):
        return
    row, c0 = node.start_point.row, node.start_point.column
    col = c0 + pick(range(1, len(name)), win.key, node.start_point, "word")
    new = _new_name(win, name, node, node.start_point)
    yield Draft(
        template="rename_here", skill=skill, kind="edit",
        task=f"Rename the `{name}` under the cursor to `{new}` (only this one)",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, c0, c0 + len(name), new)},
        variants=[f"ciw{new}<Esc>"], alternates=[f"bcw{new}<Esc>", f"viwc{new}<Esc>", f"bce{new}<Esc>"],
        idioms=[f"cw{new}<Esc>", f"ce{new}<Esc>", f"caw{new}<Esc>", f"ciW{new}<Esc>", f"cb{new}<Esc>", f"bcE{new}<Esc>"],
        typed=len(new), params={"text": new}, target=[_range(row, c0, row, c0 + len(name) - 1)], window=win,
        tags=["identifier", "word"],
        hints=[
            {"trigger": "^b", "text": "ciw works from anywhere in the word; the b is not needed."},
            {"trigger": "^c[we]", "text": "cw only changes from the cursor to the end of the word; ciw takes all of it."},
            {"trigger": "x{2,}|^d", "text": "ciw deletes the word and enters insert mode in one command."},
            {"trigger": None, "text": "ciw: change inner word, from anywhere inside it."},
        ],
    )


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:%s/\\<old\\>/new/g<CR>``: rename every whole-word occurrence.

    Ex kind above SUBST_EDIT_MAX occurrences. With SUBST_EDIT_MAX or fewer the kind is
    "edit" and ``/\\<old\\><CR>cgnnew<Esc>..`` is a verified alternate: renaming three
    names with ``cgn`` + ``.`` is a fair answer, not a way around the drill.
    """
    old = _text(node)
    if len(old) < 3 or old in lang.keywords or not re.fullmatch(r"[A-Za-z_]\w*", old) or _seen(win, "subst", old):
        return
    if old in _BUILTINS or _is_dunder(old):
        return
    rx = re.compile(rf"\b{old}\b")
    hits = [(r, m.start()) for r, ln in enumerate(win.lines) for m in rx.finditer(ln)]
    if len(hits) < 3 or len({r for r, _ in hits}) < 2:
        return
    new = _new_name(win, old, node, node.start_point)
    cursor = _away_from(win.lines, hits, len(old))
    if cursor is None:
        return
    patterns = (old, f"{old}\\>", f"\\<{old}", f"\\<{old}\\>")
    variants = [f":%s/{p}/{new}{flag}<CR>" for flag in ("", "/g") for p in patterns]
    few = len(hits) <= SUBST_EDIT_MAX
    dots = "." * (len(hits) - 1)
    yield Draft(
        template="rename_all_subst", skill=skill, kind="edit" if few else "ex",
        task=f"Rename every `{old}` to `{new}` ({len(hits)} occurrences)",
        lines=win.lines, cursor=[cursor[0] + 1, cursor[1]], expect={"lines": [rx.sub(new, ln) for ln in win.lines]},
        variants=sorted(variants, key=len), alternates=[f"/\\<{old}\\><CR>cgn{new}<Esc>{dots}"] if few else [],
        typed=len(new), params={"old": old, "new": new},
        target=[_range(r, c, r, c + len(old) - 1) for r, c in hits], window=win, tags=["identifier", "substitute"],
        hints=[
            {"trigger": "^[*#]|cgn|ciw|cw|\\.", "text": ":%s/old/new/g renames every occurrence in one command."},
            {"trigger": "^:s/", "text": "Without % only the cursor line is substituted; :%s covers the whole buffer."},
            {"trigger": "^:%s/[A-Za-z_]", "text": "\\< and \\> make the pattern match whole words only, if other names contain it."},
            {"trigger": None, "text": f":%s/{old}/{new}/g: substitute in every line; add /g for several per line."},
        ],
    )


def move_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:m+k<CR>`` / ``:m-k<CR>``: move a one-line statement among its one-line siblings (ex kind)."""
    plan = _line_move(win, node, "move")
    if plan is None:
        return
    row, k, down = plan
    lines = win.lines
    other = row + k if down else row - k
    moved = lines[:row] + lines[row + 1:]
    expect = moved[:other] + [lines[row]] + moved[other:]  # `other` is also the landing index in `moved`
    # Normal-mode yank/put is a legitimate idiom here, so the kind is "edit", not "ex":
    # the ex rule exists for :g/:normal drills that retyping would defeat.
    if down:
        variants = [f":m+{k}<CR>", f":m{row + k + 1}<CR>", "ddp" if k == 1 else f"dd{k - 1}jp"]
    else:
        variants = [f":m-{k + 1}<CR>", f":m{row - k}<CR>", f"dd{k}kP" if k > 1 else "ddkP"]
    where = "below" if down else "above"
    yield Draft(
        template="move_line", skill=skill, kind="edit",
        task=f"Move this line {where} `{_clip(lines[other].strip())}`",
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": expect},
        variants=sorted(variants, key=len), alternates=[v.replace(":m", ":move ") for v in variants],
        target=[_range(row, 0, row, len(lines[row]) - 1), _range(other, 0, other, len(lines[other]) - 1)],
        window=win, tags=["line", "move"],
        hints=[
            {"trigger": "^\"?[a-z]?dd\\d*[jk]", "text": ":m+N / :m-N moves the line without touching a register, and the count does not change the key count."},
            {"trigger": None, "text": ":m+N moves the line below the line N lines down; :m-N moves it up N-1 lines."},
        ],
    )


def copy_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:t.<CR>`` / ``:t+k<CR>`` / ``:t-k<CR>``: copy a one-line statement (ex kind)."""
    plan = _line_move(win, node, "copy")
    if plan is None:
        return
    row, k, down = plan
    lines = win.lines
    if pick((True, False, False), win.key, node.start_point, "dup"):
        k, down = 0, True
    other = row + k if down else row - k
    dest = other + 1 if down else other
    expect = lines[:dest] + [lines[row]] + lines[dest:]
    # Normal-mode yank/put is a legitimate idiom here (yyp is 3 keys to :t.'s 4), so the
    # kind is "edit" and the shortest variant becomes the par.
    if k == 0:
        variants, task = [":t.<CR>", f":t{row + 1}<CR>", "yyp"], "Duplicate this line (the copy goes right below it)"
    elif down:
        variants, task = [f":t+{k}<CR>", f":t{row + k + 1}<CR>", "yyjp" if k == 1 else f"yy{k}jp"], f"Copy this line to just below `{_clip(lines[other].strip())}`"
    else:
        variants, task = [f":t-{k + 1}<CR>", f":t{row - k}<CR>", "yykP" if k == 1 else f"yy{k}kP"], f"Copy this line to just above `{_clip(lines[other].strip())}`"
    yield Draft(
        template="copy_line", skill=skill, kind="edit", task=task,
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": expect},
        variants=sorted(variants, key=len), alternates=[v.replace(":t", ":copy ") for v in variants],
        target=[_range(row, 0, row, len(lines[row]) - 1)]
        + ([_range(other, 0, other, len(lines[other]) - 1)] if k else []),
        window=win, tags=["line", "copy"],
        hints=[
            {"trigger": "^(yy|Y)\\d*[jk]", "text": ":t+N / :t-N copies a line without touching a register; yy{N}jp ties it on keys."},
            {"trigger": None, "text": ":t. duplicates the line; :t+N puts the copy below the line N lines down."},
        ],
    )


# Tier 5-8 templates ===============================================================================


def append_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``<C-v>{n}j$A,<Esc>``: restore the trailing commas of a one-item-per-line collection (v.blockedit).

    The start buffer is the source with the commas stripped from the item lines; the
    expect is the source. ``:.,+{n}norm A,`` and ``A,<Esc>j.`` are alternates; with
    four or more lines the block edit is the shortest.
    """
    item_rows = _item_rows(win, node)
    if item_rows is None or not 4 <= len(item_rows) <= 12 or item_rows != list(range(item_rows[0], item_rows[-1] + 1)):
        return
    first, last = item_rows[0], item_rows[-1]
    if _seen(win, f"append:{skill}", first):
        return
    lines = [ln[:-1] if r in item_rows else ln for r, ln in enumerate(win.lines)]
    k = len(item_rows) - 1
    down = f"{k}j" if k > 1 else "j"
    noun = {"argument_list": "argument", "parameters": "parameter", "dictionary": "entry"}.get(node.type, "item")
    yield Draft(
        template="append_each_line", skill=skill, kind="edit",
        task=f"Add the missing `,` at the end of each of these {k + 1} {noun} lines",
        lines=lines, cursor=[first + 1, _indent(lines[first])], expect={"lines": win.lines},
        variants=[f"<C-v>{down}$A,<Esc>"],
        alternates=[f"V{down}:norm A,<CR>", f":.,+{k}norm A,<CR>", f":.,+{k}normal A,<CR>"],
        idioms=["A,<Esc>" + "j." * k, "A,<Esc>" + "+." * k, f":.,+{k}s/$/,<CR>", f"<C-v>{down}A,<Esc>",
                f"<C-v>{k + 1}j$A,<Esc>"],
        typed=1, typed_per_line=True, params={"text": ",", "n": k + 1},
        target=[_range(r, 0, r, max(len(lines[r]) - 1, 0)) for r in item_rows], window=win,
        tags=[node.type, "block-edit", "append"],
        hints=[
            {"trigger": "^A,<Esc>[j+]", "text": f"<C-v>{down}$ selects to the end of all {k + 1} lines; A, appends to each."},
            {"trigger": "^<C-v>[0-9]*jA", "text": "Without $ the block ends at the cursor column; $ extends it to every line's end."},
            {"trigger": "^:|^V", "text": ":norm works too; the block edit is shorter here."},
            {"trigger": None, "text": f"<C-v>{down}$A,<Esc>: block-select to each line's end, append, Esc applies it to all."},
        ],
    )


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``<C-v>{n}jIself.<Esc>`` (v.blockedit) or ``V{n}j:norm Iself.<CR>`` (x.normal): put back the
    ``self.`` that a run of 3+ attribute assignments lost (start = source with ``self.`` removed).
    With three lines the block insert (10 keys) still beats ``Iself.<Esc>j.j.`` (11)."""
    for run in _assignment_runs(win, node, 3):
        run = run[:8]
        rows = [a.start_point.row for a in run]
        lefts = [a.child_by_field_name("left") for a in run]
        col = _indent(win.lines[rows[0]])
        if any(_text(left)[:5] != "self." or left.start_point.column != col for left in lefts):
            continue
        if _seen(win, f"prefix:{skill}", str(rows[0])):
            continue
        lines = [ln[:col] + ln[col + 5:] if r in rows else ln for r, ln in enumerate(win.lines)]
        k = len(rows) - 1
        down = f"{k}j" if k > 1 else "j"
        target = [_range(r, col, r, col + 4) for r in rows]
        task = f"Put `self.` back at the start of each of these {k + 1} assignments"
        if skill == "v.blockedit":
            yield Draft(
                template="prefix_each_line", skill=skill, kind="edit", task=task,
                lines=lines, cursor=[rows[0] + 1, col], expect={"lines": win.lines},
                variants=[f"<C-v>{down}Iself.<Esc>"], alternates=[f"V{down}:norm Iself.<CR>"],
                idioms=["Iself.<Esc>" + "j." * k, "Iself.<Esc>" + "+." * k, f":.,+{k}s/\\S/self.&<CR>"],
                typed=5, typed_per_line=True, params={"text": "self.", "n": k + 1}, target=target, window=win,
                tags=["assignment", "block-edit", "insert"],
                hints=[
                    {"trigger": "^Iself", "text": f"<C-v>{down} selects a column on all {k + 1} lines; I inserts on every one."},
                    {"trigger": "^:|^V", "text": ":norm works too; the block insert is shorter here."},
                    {"trigger": None, "text": f"<C-v>{down}Iself.<Esc>: block-select the column, insert, Esc copies it to every line."},
                ],
            )
        else:
            yield normal_prefix(win, skill, rows, "self.", lines, win.lines, task, target, ["assignment", "normal", "insert"])
        return


def normal_prefix(
    win: Window, skill: str, rows: list[int], prefix: str, lines: list[str], expect: list[str], task: str,
    target: list[dict[str, list[int]]], tags: list[str],
) -> Draft:
    """``V{n}j:norm I{prefix}<CR>``: the x.normal draft that turns ``lines`` into ``expect`` by
    inserting ``prefix`` at the first non-blank of each of ``rows`` (consecutive). Ex kind: the
    rows number 3 or more (EX_MIN_LINES), so ``I...<Esc>j.j.`` would be a repetition drill.
    Used by ``prefix_each_line`` here and in ``lang/cpp.py``."""
    k = len(rows) - 1
    down = f"{k}j" if k > 1 else "j"
    sub = prefix.replace("/", "\\/")
    norm = f"I{prefix}"
    return Draft(
        template="prefix_each_line", skill=skill, kind="ex" if len(rows) >= EX_MIN_LINES else "edit", task=task,
        lines=lines, cursor=[rows[0] + 1, _indent(lines[rows[0]])], expect={"lines": expect},
        variants=[f"V{down}:norm {norm}<CR>", f":.,+{k}norm {norm}<CR>", f":{rows[0] + 1},{rows[-1] + 1}norm {norm}<CR>"],
        alternates=[f":.,+{k}normal {norm}<CR>"],
        idioms=[f"V{down}:s/\\S/{sub}&<CR>", f":.,+{k}s/\\S/{sub}&<CR>"],
        typed=len(prefix), typed_per_line=True, params={"text": prefix, "n": k + 1}, target=target, window=win,
        tags=tags,
        hints=[
            {"trigger": f"^{_js_escape(norm)}|j\\.", "text": f":norm {norm} runs I on every line of the range; V{down} selects the {k + 1} lines."},
            {"trigger": ":[^n]*s/", "text": "A substitute works too, but this drill is about :normal."},
            {"trigger": None, "text": f"V{down}:norm {norm}<CR>: select the lines, then run {norm} on each."},
        ],
    )


def upper_constants(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm gUiw<CR>``: uppercase the names of consecutive module- or class-level assignments (x.normal)."""
    if node.type == "block" and (node.parent is None or node.parent.type != "class_definition"):
        return
    for run in _assignment_runs(win, node, EX_MIN_LINES):  # ex kind: gUiwj.j. would be a repetition drill
        names = [_text(a.child_by_field_name("left")) for a in run]
        if not all(re.fullmatch(r"[a-z][a-z0-9_]*[a-z0-9]", n) for n in names):
            continue
        rows = [a.start_point.row for a in run]
        if _seen(win, "constants", rows[0]):
            continue
        k = len(rows) - 1
        down = f"{k}j" if k > 1 else "j"
        go = "^" if _indent(win.lines[rows[0]]) else ""  # :norm starts each line in column 0
        expect = list(win.lines)
        for r, name in zip(rows, names):
            i = _indent(expect[r])
            expect[r] = expect[r][:i] + name.upper() + expect[r][i + len(name):]
        yield Draft(
            template="upper_constants", skill=skill, kind="ex",
            task=f"Turn these {k + 1} assignments into constants: uppercase each name",
            lines=win.lines, cursor=[rows[0] + 1, _indent(win.lines[rows[0]])], expect={"lines": expect},
            variants=[f"V{down}:norm {go}gUiw<CR>", f"V{down}:norm {go}gUe<CR>", f":.,+{k}norm {go}gUiw<CR>",
                      f":{rows[0] + 1},{rows[-1] + 1}norm {go}gUiw<CR>"],
            alternates=[f":.,+{k}normal {go}gUiw<CR>", f"V{down}:normal {go}gUiw<CR>"],
            idioms=[f":.,+{k}s/\\w\\+/\\U&/<CR>", f":.,+{k}s/\\w\\+/\\U&<CR>", "gUiwj." + "j." * (k - 1)],
            params={"n": k + 1},
            target=[_range(r, _indent(win.lines[r]), r, _indent(win.lines[r]) + len(names[i]) - 1)
                    for i, r in enumerate(rows)],
            window=win, tags=["assignment", "normal", "case"],
            hints=[
                {"trigger": "^gU|j\\.", "text": f":norm runs gUiw on every line of the range; V{down} selects the {k + 1} lines."},
                {"trigger": ":[^n]*s/", "text": "A substitute works too, but this drill is about :normal."},
                {"trigger": None, "text": f"V{down}:norm {go}gUiw<CR>: select the lines, then run {go}gUiw on each."},
            ],
        )
        return


def delete_matching_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:g/pat/d<CR>``: delete every line that calls one function or is a comment (x.global, ex kind)."""
    made = 0
    for label, patterns, rows in _line_groups(win):
        if not EX_MIN_LINES <= len(rows) <= len(win.lines) - 4:  # ex kind: fewer is just dd and j
            continue
        valid = [p for p in patterns if _matching_rows(win.lines, p) == rows]
        if not valid:
            continue
        variants = sorted((f":g/{p}/d<CR>" for p in valid), key=len)
        pattern, shortest = patterns[-1], min(map(len, valid))
        yield Draft(
            template="delete_matching_lines", skill=skill, kind="ex",
            task=f"Delete every {label} ({len(rows)} lines)",
            lines=win.lines, cursor=[1, _indent(win.lines[0])],
            expect={"lines": [ln for r, ln in enumerate(win.lines) if r not in rows]},
            variants=variants, alternates=[v.replace(":g/", ":global/", 1) for v in variants[:1]],
            typed=shortest, params={"pattern": pattern, "n": len(rows)},
            target=[_range(r, 0, r, max(len(win.lines[r]) - 1, 0)) for r in rows], window=win,
            tags=["global", "delete", "lines"],
            hints=[
                {"trigger": "dd|^[0-9]*[jk]", "text": f":g/pattern/d deletes all {len(rows)} lines in one command."},
                {"trigger": "^:%?s/", "text": ":s edits text inside lines; :g/pattern/d removes the matching lines."},
                {"trigger": None, "text": f"{variants[0][:-4]}: run :d on every line that matches the pattern."},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


def keep_matching_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:v/pat/d<CR>``: keep only the lines that match, e.g. an outline of ``def`` lines (x.global)."""
    made = 0
    for label, pattern in _keep_patterns(win):
        rows = _matching_rows(win.lines, pattern)
        drop = [r for r in range(len(win.lines)) if r not in rows]
        if len(rows) < 2 or len(drop) < 4:  # ex kind: 4+ deleted lines (>= EX_MIN_LINES) are the repetition
            continue
        valid = [pattern[:i] for i in range(1, len(pattern) + 1) if _matching_rows(win.lines, pattern[:i]) == rows]
        variants = sorted((f":v/{p}/d<CR>" for p in valid), key=len)
        shortest = min(map(len, valid))
        yield Draft(
            template="keep_matching_lines", skill=skill, kind="ex",
            task=f"Delete every line except the {len(rows)} {label}",
            lines=win.lines, cursor=[1, _indent(win.lines[0])],
            expect={"lines": [win.lines[r] for r in rows]},
            variants=variants, alternates=[v.replace(":v/", ":g!/", 1) for v in variants[:1]],
            typed=shortest, params={"pattern": pattern, "n": len(rows)},
            target=[_range(r, 0, r, max(len(win.lines[r]) - 1, 0)) for r in drop], window=win,
            tags=["global", "invert", "lines"],
            hints=[
                {"trigger": "dd|^[0-9]*[jk]", "text": ":v/pattern/d deletes every line that does not match, in one command."},
                {"trigger": "^:g/", "text": ":g runs on matching lines; :v (or :g!) runs on the lines that do not match."},
                {"trigger": None, "text": f"{variants[0][:-4]}: delete every line that does not contain the pattern."},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


def rename_all_dot(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``*cgnNEW<Esc>`` then ``.`` per remaining match: rename every occurrence (x.lastsearch, a.dot)."""
    old = _text(node)
    if len(old) < 3 or old in lang.keywords or old in _BUILTINS or _is_dunder(old) or not re.fullmatch(r"[A-Za-z_]\w*", old):
        return
    if _seen(win, f"dot:{skill}", old):
        return
    rx = re.compile(rf"\b{old}\b")
    hits = [(r, m.start()) for r, ln in enumerate(win.lines) for m in rx.finditer(ln)]
    if not 3 <= len(hits) <= 8 or len({r for r, _ in hits}) < 2 or (node.start_point.row, node.start_point.column) != hits[0]:
        return
    new = _new_name(win, old, node, node.start_point, "dot")
    row, c0 = hits[0]
    col = c0 + pick(range(len(old)), win.key, node.start_point, "dotcur")
    dots = "." * (len(hits) - 1)
    yield Draft(
        template="rename_all_dot", skill=skill, kind="edit",
        task=f"Rename every `{old}` to `{new}` ({len(hits)} occurrences), one match at a time",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": [rx.sub(new, ln) for ln in win.lines]},
        variants=[f"*cgn{new}<Esc>{dots}", f"#cgn{new}<Esc>{dots}", f"*Ncgn{new}<Esc>{dots}"],
        alternates=[f"*ciw{new}<Esc>" + "n." * (len(hits) - 1), f"/\\<{old}\\><CR>cgn{new}<Esc>{dots}"],
        idioms=[f":%s/{old}/{new}/g<CR>", f":%s/\\<{old}\\>/{new}/g<CR>", f"ciw{new}<Esc>" + "n." * (len(hits) - 1),
                f"*Nciw{new}<Esc>" + "n." * (len(hits) - 1)],
        typed=len(new), params={"old": old, "new": new, "n": len(hits)},
        target=[_range(r, c, r, c + len(old) - 1) for r, c in hits], window=win, tags=["identifier", "gn", "dot"],
        hints=[
            {"trigger": "ciw|cw", "text": "cgn changes the next match of the last search, so . alone repeats it on the next one."},
            {"trigger": "n\\.", "text": "With cgn the . finds the next match itself; no n needed between repeats."},
            {"trigger": "^:", "text": ":%s works too; this drill is about * + cgn + ."},
            {"trigger": None, "text": f"* searches for the word under the cursor; cgn{new}<Esc> changes a match; . repeats on the next."},
        ],
    )


def join_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}J``: join a hanging-indent continuation (``foo(a,`` / ``    b)``) into one line (o.join)."""
    r0, r1 = node.start_point.row, node.end_point.row
    if r0 == r1:
        yield from _join_split(win, node, skill)
        return
    n = r1 - r0 + 1
    if not 2 <= n <= 6 or _seen(win, "join", str(r0)):
        return
    lines = win.lines
    prose = _prose_rows(win)
    if any(r in prose or "#" in lines[r] for r in range(r0, r1 + 1)):
        return
    if any(lines[r].rstrip().endswith(("(", "[", "{", "\\")) for r in range(r0, r1)):
        return
    if any(not lines[r].strip() or lines[r].lstrip()[0] in "]}" for r in range(r0 + 1, r1 + 1)):
        return
    joined = lines[r0]
    for r in range(r0 + 1, r1 + 1):
        nxt = lines[r].lstrip()
        joined += nxt if nxt.startswith(")") or joined.endswith(" ") else " " + nxt
    if len(joined) > 88:
        return
    keys = "J" if n == 2 else f"{n}J"
    yield Draft(
        template="join_lines", skill=skill, kind="edit",
        task=f"Join these {n} lines into one",
        lines=lines, cursor=[r0 + 1, _indent(lines[r0])], expect={"lines": lines[:r0] + [joined] + lines[r1 + 1:]},
        variants=[keys], alternates=[*(["J" * (n - 1)] if n > 2 else ["2J"]), f"V{n - 1 if n > 2 else ''}jJ",
                                     f":.,+{n - 1}j<CR>"],
        idioms=["gJ", f"{n}gJ", "A<Del><Esc>", "$x"],
        params={"n": n}, target=[_range(r, 0, r, max(len(lines[r]) - 1, 0)) for r in range(r0, r1 + 1)],
        window=win, tags=[node.type, "join"],
        hints=[
            {"trigger": "^J+$", "text": f"A count joins them all at once: {n}J joins {n} lines."},
            {"trigger": "<Del>|x|<BS>", "text": "J removes the line break and the indent and puts one space in between."},
            {"trigger": None, "text": f"{keys}: join {n} lines, starting at the cursor line."},
        ],
    )


def _join_split(win: Window, node: tree_sitter.Node, skill: str) -> Iterator[Draft]:
    """join_lines on a one-line call or collection: the start buffer wraps it after commas
    (hanging indent under the opening bracket); the expect is the source line."""
    pair = _bracket_pair(node)
    items = [c for c in node.named_children if c.type != "comment"]
    row = node.start_point.row
    line = win.lines[row]
    if pair is None or len(items) < 2 or len(line) > 88 or "#" in line or row in _prose_rows(win):
        return
    if any(line[a.end_point.column:b.start_point.column] != ", " for a, b in zip(items, items[1:])):
        return
    if _seen(win, "join", str(row)):
        return
    oc = pair[0][1]
    n = min(len(items), pick((2, 3, 3, 4), win.key, node.start_point, "joinn"))
    cuts = [items[i].start_point.column for i in range(len(items) - n + 1, len(items))]
    pad = " " * (oc + 1)
    parts = [line[:cuts[0]].rstrip()] + [pad + line[a:b].rstrip() for a, b in zip(cuts, cuts[1:])] + [pad + line[cuts[-1]:]]
    joined = parts[0]
    for part in parts[1:]:
        joined += " " + part.lstrip()
    if joined != line or max(map(len, parts)) > 100:
        return
    lines = win.lines[:row] + parts + win.lines[row + 1:]
    keys = "J" if n == 2 else f"{n}J"
    yield Draft(
        template="join_lines", skill=skill, kind="edit",
        task=f"Join these {n} lines back into one",
        lines=lines, cursor=[row + 1, _indent(line)], expect={"lines": win.lines},
        variants=[keys], alternates=[*(["J" * (n - 1)] if n > 2 else ["2J"]), f"V{n - 1 if n > 2 else ''}jJ",
                                     f":.,+{n - 1}j<CR>"],
        idioms=["gJ", f"{n}gJ", "A<Del><Esc>", "$x"],
        params={"n": n}, target=[_range(r, 0, r, max(len(lines[r]) - 1, 0)) for r in range(row, row + n)],
        window=win, tags=[node.type, "join"],
        hints=[
            {"trigger": "^J+$", "text": f"A count joins them all at once: {n}J joins {n} lines."},
            {"trigger": "<Del>|x|<BS>", "text": "J removes the line break and the indent and puts one space in between."},
            {"trigger": None, "text": f"{keys}: join {n} lines, starting at the cursor line."},
        ],
    )


def increment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}<C-a>`` / ``{n}<C-x>``: change a number by a count, cursor before it on the line (o.number)."""
    text = _text(node)
    if not re.fullmatch(r"[1-9]\d{0,3}|0", text):
        return
    row, c0, c1 = node.start_point.row, node.start_point.column, node.end_point.column
    line = win.lines[row]
    if row in _prose_rows(win) or (c0 and (line[c0 - 1].isalnum() or line[c0 - 1] in "_-.")):
        return
    if c1 < len(line) and (line[c1].isalnum() or line[c1] in "_."):
        return
    digits_before = [i for i in range(c0) if line[i].isdigit()]
    col = max(_indent(line), digits_before[-1] + 1 if digits_before else 0)
    if c0 - col < 3 or _seen(win, "number", f"{row}:{c0}"):
        return
    value, delta = int(text), pick(range(2, 10), win.key, node.start_point, "delta")
    up = pick((True, True, False), win.key, node.start_point, "up") or value - delta < 0
    new = str(value + delta if up else value - delta)
    key = "<C-a>" if up else "<C-x>"
    parent = node.parent
    context = _text(parent) if parent is not None else ""
    if parent is not None and parent.start_point.row == parent.end_point.row and len(context) <= 32 and context.count(text) == 1 and "`" not in context:
        rel = c0 - parent.start_point.column
        task = f"Change `{context}` to `{context[:rel]}{new}{context[rel + len(text):]}`"
    elif len(re.findall(rf"(?<![\w.]){text}(?![\w.])", line)) == 1:
        task = f"Change the `{text}` on this line to `{new}`"
    else:
        return
    yield Draft(
        template="increment", skill=skill, kind="edit", task=task,
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, c0, c1, new)},
        variants=[f"{delta}{key}"], alternates=[key * delta],
        idioms=[f"f{text[0]}r{new}" if len(new) == len(text) == 1 else f"f{text[0]}ciw{new}<Esc>",
                f"f{text[0]}cw{new}<Esc>", f"f{text[0]}s{new}<Esc>", f"t{text[0]}lr{new}" if len(new) == 1 else "w"],
        params={"n": delta, "old": text, "new": new},
        target=[_range(row, c0, row, c1 - 1)], window=win, tags=["number", "increment"],
        hints=[
            {"trigger": "^[0-9]*[fFtTwbe]", "text": f"{key} finds the next number on the line by itself; no need to move first."},
            {"trigger": "r[0-9]|c[iw]|s[0-9]", "text": f"{delta}{key} does the arithmetic: no retyping, works for any number of digits."},
            {"trigger": f"^({_js_escape(key)}){{2,}}", "text": f"A count does it in one go: {delta}{key}."},
            {"trigger": None, "text": f"{delta}{key}: {'add' if up else 'subtract'} {delta} to the number at or after the cursor."},
        ],
    )


def duplicate_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``yy{k}jp`` (o.yank) / ``yy{k}kP`` (o.put): copy a one-line statement near its siblings."""
    options = _line_options(win, node)
    if options is None:
        return
    if skill == "o.put":
        options = [o for o in options if not o[2]]
    else:
        options = [o for o in options if o[2]]
        if node.start_point.row + 1 < len(win.lines):  # a copy below the last line has nothing to highlight
            options.append((node.start_point.row, 0, True))
    if not options:
        return
    row, k, down = pick(options, win.key, node.start_point, f"yank:{skill}")
    lines = win.lines
    other = row + k if down else row - k
    dest = other + 1 if down else other
    expect = lines[:dest] + [lines[row]] + lines[dest:]
    quote = _clip(lines[other].strip())
    if k == 0:
        variants, task = ["yyp"], "Duplicate this line (the copy goes right below it)"
        alternates = [":t.<CR>", "yyjP"]
    elif down:
        move = f"{k}j" if k > 1 else "j"
        variants, task = [f"yy{move}p", f"yy{k}+p"], f"Copy this line to just below `{quote}`"
        alternates = [f":t+{k}<CR>", f"yy{k + 1}jP"]
    else:
        move = f"{k}k" if k > 1 else "k"
        variants, task = [f"yy{move}P", f"yy{k}-P"], f"Copy this line to just above `{quote}`"
        alternates = [f":t-{k + 1}<CR>", f"yy{k + 1}kp"]
    yield Draft(
        template="duplicate_line", skill=skill, kind="edit", task=task,
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": expect},
        variants=variants, alternates=alternates, idioms=["Yp", "YP", "ddpP", "ddPp"],
        target=[_range(r, 0, r, max(len(lines[r]) - 1, 0)) for r in sorted({row, other, min(dest, len(lines) - 1)})],
        window=win, tags=["line", "yank", "put"],
        hints=[
            {"trigger": "^Y", "text": "In Neovim Y yanks to the end of the line (y$), not the whole line; yy yanks the line."},
            {"trigger": "^dd", "text": "yy copies without deleting the original."},
            {"trigger": "^o|^O", "text": "yy then p copies the line exactly; no retyping."},
            {"trigger": None, "text": "yy yanks the line; p puts it below the cursor line, P above."},
        ],
    )


def record_macro(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``qa f=Wi{w}(<Esc>A)<Esc>+ q {n-1}@a``: wrap the value of 4+ sibling assignments in a call (a.macro)."""
    for run in _assignment_runs(win, node, 4):
        run = run[:8]
        rows = [a.start_point.row for a in run]
        rights = [a.child_by_field_name("right") for a in run]
        ok = True
        for a, right, r in zip(run, rights, rows):
            line = win.lines[r]
            eq = line.find("=", _indent(line))
            if (right is None or right.end_point.column != len(line) or right.start_point.column != eq + 2
                    or line[eq + 1] != " " or line[eq - 1] != " "):
                ok = False
        if not ok or _seen(win, "macro", rows[0]):
            continue
        kinds = {r.type for r in rights}
        wrapper = "float" if kinds <= {"integer"} else "_" if kinds <= {"string"} else "str"
        if any(_text(r).startswith(f"{wrapper}(") for r in rights):
            continue
        n = len(rows)
        expect = list(win.lines)
        for right, r in zip(rights, rows):
            c0 = right.start_point.column
            expect[r] = expect[r][:c0] + f"{wrapper}({expect[r][c0:]})"
        body = f"f=Wi{wrapper}(<Esc>A)<Esc>+"
        what = "string" if wrapper == "_" else "value"
        yield Draft(
            template="record_macro", skill=skill, kind="edit",
            task=f"Wrap the {what} of each of these {n} assignments in `{wrapper}(...)`",
            lines=win.lines, cursor=[rows[0] + 1, _indent(win.lines[rows[0]])], expect={"lines": expect},
            variants=[f"qa{body}q{n - 1}@a", f"qq{body}q{n - 1}@q"],
            alternates=[f"qa{body}q@a" + "@@" * (n - 2), f"qa{body}q:.,+{n - 2}norm @a<CR>"],
            idioms=[f":.,+{n - 1}s/= \\zs.*/{wrapper}(&)/<CR>", f":.,+{n - 1}s/= \\(.*\\)/= {wrapper}(\\1)/<CR>"],
            typed=len(wrapper) + 2, params={"n": n, "text": wrapper},
            target=[_range(r, right.start_point.column, r, len(win.lines[r]) - 1) for right, r in zip(rights, rows)],
            window=win, tags=["assignment", "macro"],
            hints=[
                {"trigger": "^f=W?i.*<Esc>A.*<Esc>[+j]f", "text": f"Record the edit once (qa ... q) and replay it: {n - 1}@a does the other {n - 1} lines."},
                {"trigger": "^qa[^+j]*q", "text": "End the recording on the next line (+) so each replay starts where it should."},
                {"trigger": "^:", "text": "A substitute works too; this drill is about recording a macro."},
                {"trigger": None, "text": f"qa{body}q records one line's edit; {n - 1}@a replays it on the rest."},
            ],
        )
        return


def delete_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``dap`` on a paragraph-shaped statement (t.para), or ``di{`` / ``di[`` / ``di(`` on a multi-line
    collection whose brackets sit on their own lines (t.brace, t.bracket, t.paren)."""
    if skill == "t.para":
        yield from _delete_paragraph(win, node, skill)
        return
    pair = _bracket_pair(node)
    if pair is None:
        return
    (orow, ocol, o), (crow, ccol, c) = pair
    lines = win.lines
    if crow - orow < 3 or lines[orow].rstrip()[-1:] != o or _indent(lines[crow]) != ccol or orow in _prose_rows(win):
        return
    strings = _string_cells(win)
    cols = [(r, cc) for r, cc in _depth0_positions(win, (orow, ocol), (crow, ccol), o, c)
            if orow < r < crow and (r, cc) not in strings]
    if not cols:
        return
    row, col = pick(cols, win.key, node.start_point, "blk")
    n = crow - orow - 1
    noun = {"(": "argument", "[": "item", "{": "entry"}[o]
    yield Draft(
        template="delete_block", skill=skill, kind="edit",
        task=f"Delete the {_plural(n, noun + ' line')} of this {_NOUNS.get(node.type, 'block')}, keeping the `{o}` and `{c}` lines",
        lines=lines, cursor=[row + 1, col], expect={"lines": lines[:orow + 1] + lines[crow:]},
        variants=[f"di{o}"], alternates=[f"di{a}" for a in _ALIASES[o]],
        idioms=["dap", "dip", "d}", "d{", f"{n}dd", "dd", f"[{o}jd]{c}" if o in "({" else "dd", f"d{n - 1}j", f"d{n - 1}k"],
        params={"open": o, "close": c, "n": n}, target=[_range(orow + 1, 0, crow - 1, max(len(lines[crow - 1]) - 1, 0))],
        window=win, tags=[node.type, "delete", "block"],
        hints=[
            {"trigger": "^[0-9]*dd|^d[0-9]*[jk]|^V", "text": f"di{o} deletes every line between the brackets from anywhere inside."},
            {"trigger": "^\\[|^[0-9]*[jk]", "text": f"No need to move: di{o} finds the enclosing {o}{c} itself."},
            {"trigger": None, "text": f"di{o}: when the {o} ends its line and the {c} starts its own, the inner lines are deleted whole."},
        ],
    )


def _delete_paragraph(win: Window, node: tree_sitter.Node, skill: str) -> Iterator[Draft]:
    if node.parent is not None and node.parent.type == "decorated_definition":
        node = node.parent
    lines = win.lines
    r0, r1 = node.start_point.row, node.end_point.row
    n = r1 - r0 + 1
    blank = [not ln.strip() for ln in lines]
    if not 3 <= n <= 20 or len(lines) - n < 4 or any(blank[r0:r1 + 1]):
        return
    if (r0 > 0 and not blank[r0 - 1]) or (r1 + 1 < len(lines) and not blank[r1 + 1]) or r1 + 1 >= len(lines):
        return
    if _seen(win, "para", str(r0)):
        return
    end = r1 + 1
    while end < len(lines) and blank[end]:
        end += 1
    row = pick(range(r0 + 1, r1 + 1), win.key, node.start_point, "para")
    blanks = "blank line" if end - r1 == 2 else f"{end - r1 - 1} blank lines"
    first = r0  # the highlight takes in the blank lines above too: a diff may show those as deleted
    while first > 0 and blank[first - 1]:
        first -= 1
    inner = node.child_by_field_name("definition") or node
    name = inner.child_by_field_name("name")
    what = {"function_definition": f"the function `{_text(name)}`" if name else "this function",
            "class_definition": f"the class `{_text(name)}`" if name else "this class",
            "if_statement": "this `if` statement", "for_statement": "this `for` loop",
            "while_statement": "this `while` loop", "with_statement": "this `with` block"}.get(inner.type, "this block")
    yield Draft(
        template="delete_block", skill=skill, kind="edit",
        task=f"Delete {what} ({n} lines) and the {blanks} after it, from where the cursor is",
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": lines[:r0] + lines[end:]},
        variants=["dap"], alternates=["Vapd"],
        idioms=["{d}", "d}", "{dap", "dip", f"{n}dd", "dd", f"d{n}j", f"d{row - r0}k", "d{"],
        params={"n": n}, target=[_range(first, 0, end - 1, max(len(lines[end - 1]) - 1, 0))], window=win,
        tags=[inner.type, "paragraph", "delete"],
        hints=[
            {"trigger": "^[0-9]*[jk{]|^gg", "text": "ap works from any line of the paragraph; no need to move to its start."},
            {"trigger": "^[0-9]*dd|^d[0-9]*[jk]", "text": "dap deletes the whole paragraph plus the blank line after it, without counting lines."},
            {"trigger": "^dip", "text": "ip leaves the blank line behind; ap takes it too."},
            {"trigger": None, "text": "dap: delete a paragraph (the lines between blank lines) and the blank line after it."},
        ],
    )


# Line templates ===================================================================================


def goto_line_rel(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}j`` / ``{k}k``: jump to a line 7-25 lines away with the same indent."""
    lines = win.lines
    prose = _prose_rows(win)
    pairs = [
        (s, t) for s in range(len(lines)) for t in range(1, len(lines) - 1)
        if lines[s].strip() and lines[t].strip() and 7 <= abs(t - s) <= 25 and t not in prose and s not in prose
        and _indent(lines[s]) == _indent(lines[t]) and lines[t].strip() != lines[s].strip()
    ]
    pairs.sort(key=lambda p: stable_hash(win.key, p))
    for s, t in pairs[:MAX_PER_WINDOW]:
        k, col = abs(t - s), _indent(lines[s])
        down = t > s
        motion, alt = (f"{k}j", f"{k}+") if down else (f"{k}k", f"{k}-")
        dup = sum(ln.strip() == lines[t].strip() for ln in lines) > 1
        yield Draft(
            template="goto_line_rel", skill=skill, kind="cursor",
            task=("Move the cursor to the highlighted line" if dup or "`" in lines[t]
                  else f"Move the cursor to the highlighted line `{_clip(lines[t].strip())}`"),
            lines=lines, cursor=[s + 1, col], expect={"cursor": [t + 1, col]},
            variants=[motion], alternates=[alt], idioms=list(CURSOR_IDIOMS),
            target=[_range(t, 0, t, len(lines[t]) - 1)], window=win, tags=["relative-line"],
            hints=[
                {"trigger": "j{3,}|k{3,}", "text": f"Relative numbers show {k} next to the target: {motion} gets there in two keys."},
                {"trigger": "^[0-9]+G|^:[0-9]|^[0-9]+gg", "text": f"Absolute numbers work too, but {motion} is shorter with relativenumber on."},
                {"trigger": "^[{}]", "text": "Paragraph jumps stop at blank lines; a counted j/k lands exactly."},
                {"trigger": None, "text": f"{motion}: the relative number of the target line, then j or k."},
            ],
        )


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: from the first non-blank, jump to the n-th X on the line."""
    rows = sorted(range(len(win.lines)), key=lambda r: stable_hash(win.key, r, "find"))
    made = 0
    prose = _prose_rows(win)
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("#", "", '"', "'"):
            continue
        options = []
        for ch in lang.find_targets:
            cols = [i for i in range(start + 1, len(line)) if line[i] == ch]
            options += [(ch, n, col) for n, col in enumerate(cols[:3], 1)
                        if col - start >= 3 * (2 if n == 1 else 3) + 1]
        if not options:
            continue
        ch, n, col = pick(options, win.key, row, "opt")
        motion = f"{n}f{ch}" if n > 1 else f"f{ch}"
        yield Draft(
            template="find_char", skill=skill, kind="cursor", task=f"Move to the {ordinal(n)} `{ch}` on this line",
            lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
            variants=[motion], alternates=[f"f{ch}" + ";" * (n - 1)] if n > 1 else [],
            idioms=list(CURSOR_IDIOMS), params={"char": ch, "n": n},
            target=[_range(row, col, row, col)], window=win, tags=["find", "punctuation"],
            hints=[
                {"trigger": "l{4,}|w{3,}|e{3,}", "text": f"f{ch} jumps to the next `{ch}` on the line" + (f"; {motion} to the {ordinal(n)}." if n > 1 else ".")},
                *([{"trigger": f"^f{_js_escape(ch)};", "text": f"A count before f replaces the ; presses: {motion}."}] if n > 1 else []),
                {"trigger": None, "text": f"{motion}: find the {ordinal(n)} `{ch}` to the right."},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW + 1:
            return


NODE_TEMPLATES: Final[dict[str, NodeTemplate]] = {
    "change_inner": change_inner, "delete_inner": delete_inner, "delete_around": delete_around,
    "change_nth_arg": change_nth_arg, "change_kwarg_value": change_kwarg_value, "change_to_end": change_to_end,
    "jump_match": jump_match, "jump_block_end": jump_block_end, "delete_trailing_comment": delete_trailing_comment,
    "delete_lines": delete_lines, "indent_block": indent_block, "upper_word": upper_word, "upper_inner": upper_inner,
    "rename_here": rename_here, "rename_all_subst": rename_all_subst, "move_line": move_line, "copy_line": copy_line,
    "append_each_line": append_each_line, "prefix_each_line": prefix_each_line, "upper_constants": upper_constants,
    "delete_matching_lines": delete_matching_lines, "keep_matching_lines": keep_matching_lines,
    "rename_all_dot": rename_all_dot, "join_lines": join_lines, "increment": increment,
    "duplicate_line": duplicate_line, "record_macro": record_macro, "delete_block": delete_block,
}
LINE_TEMPLATES: Final[dict[str, LineTemplate]] = {"goto_line_rel": goto_line_rel, "find_char": find_char}


# Private Functions ================================================================================


def _all_drafts(win: Window, lang: Language) -> Iterator[Draft]:
    stack = [win.root]
    while stack:
        node = stack.pop()
        for use in lang.nodes.get(node.type, ()):
            for name in use.templates:
                yield from NODE_TEMPLATES[name](win, node, use.skill, lang)
        stack.extend(reversed(node.children))
    for use in lang.line_templates:
        for name in use.templates:
            yield from LINE_TEMPLATES[name](win, use.skill, lang)


def _js_escape(text: str) -> str:
    """Escape for a regex that must work in both Python and JavaScript (``u`` flag safe)."""
    return re.sub(r"([\\^$.*+?()[\]{}|/])", r"\\\1", text)


def _text(node: tree_sitter.Node | None) -> str:
    return node.text.decode() if node is not None and node.text is not None else ""


def _range(sr: int, sc: int, er: int, ec: int) -> dict[str, list[int]]:
    """A highlight range, [line 1-based, col 0-based] inclusive at both ends."""
    return {"start": [sr + 1, sc], "end": [er + 1, ec]}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _clip(text: str, width: int = 48) -> str:
    return text if len(text) <= width else text[:width - 3] + "..."


def _excerpt(win: Window, node: tree_sitter.Node) -> str:
    text = _text(node)
    return f"`{_clip(text, 40)}`" if "\n" not in text and "`" not in text else ""


def _replace(lines: list[str], row: int, c0: int, c1: int, text: str) -> list[str]:
    out = list(lines)
    out[row] = lines[row][:c0] + text + lines[row][c1:]
    return out


def _pick_other(options, current: str, *key: object) -> str:
    choices = [o for o in options if o != current.strip()]
    return pick(choices, *key)


def _prose_rows(win: Window) -> set[int]:
    """Rows inside multi-line strings or holding only a comment: not code to drill on."""
    rows = win.cache.get("prose")
    if rows is None:
        rows = win.cache["prose"] = set()
        stack = [win.root]
        while stack:
            n = stack.pop()
            if n.type == "string" and n.start_point.row != n.end_point.row:
                rows.update(range(n.start_point.row, n.end_point.row + 1))
            elif n.type == "comment" and win.lines[n.start_point.row].lstrip().startswith("#"):
                rows.add(n.start_point.row)
            else:
                stack.extend(n.children)
    return rows


def _string_cells(win: Window) -> set[tuple[int, int]]:
    """(row, col) cells inside string literals, quotes included."""
    cells = win.cache.get("strings")
    if cells is None:
        cells = win.cache["strings"] = set()
        stack = [win.root]
        while stack:
            n = stack.pop()
            if n.type == "string":
                cells |= _cells(win, n)
                for part in n.children:
                    if part.type == "interpolation":  # f-string {...} is code, not string
                        cells -= _cells(win, part)
            else:
                stack.extend(n.children)
    return cells


def _cells(win: Window, node: tree_sitter.Node) -> set[tuple[int, int]]:
    (r0, c0), (r1, c1) = node.start_point, node.end_point
    return {(r, c) for r in range(r0, r1 + 1)
            for c in range(c0 if r == r0 else 0, c1 if r == r1 else len(win.lines[r]))}


def _is_member(node: tree_sitter.Node) -> bool:
    """True for ``b`` in ``a.b`` (``a->b`` in C++): renaming one member use in place is rarely a real edit."""
    parent = node.parent
    if parent is None:
        return False
    field = {"attribute": "attribute", "field_expression": "field"}.get(parent.type)
    return field is not None and parent.child_by_field_name(field) == node


def _seen(win: Window, kind: str, name: str) -> bool:
    seen = win.cache.setdefault(f"seen:{kind}", set())
    if name in seen:
        return True
    seen.add(name)
    return False


def _new_name(win: Window, old: str, node: tree_sitter.Node | None, *key: object) -> str:
    """A fresh name for ``old``: same role (callable, collection, count, ...) and case style."""
    words = win.cache.get("words")
    if words is None:
        words = win.cache["words"] = set(re.findall(r"\w+", "\n".join(win.lines)))
    role = _role(node, old)
    for pool in (ROLE_NAMES[role], ROLE_NAMES["any"]):
        choices = [n for n in (_styled(w, old) for w in pool) if n not in words and n != old and n not in _BUILTINS]
        if choices:
            return pick(choices, win.key, old, *key)
    return _styled("new_" + old.lower().strip("_"), old)


def _role(node: tree_sitter.Node | None, name: str) -> str:
    """What an identifier names, for picking a replacement that reads like a real rename."""
    parent = node.parent if node is not None else None
    if parent is not None:
        if parent.type in ("function_definition", "class_definition") and parent.child_by_field_name("name") == node:
            return "call" if parent.type == "function_definition" else "class"
        if parent.type == "function_declarator" and parent.child_by_field_name("declarator") == node:
            return "call"  # C++: the name in `int area(int w)`, definition or declaration
        if parent.type in ("call", "call_expression") and parent.child_by_field_name("function") == node:
            return "class" if name[:1].isupper() and not name.isupper() else "call"
        if (parent.type == "field_expression" and parent.child_by_field_name("field") == node and parent.parent is not None
                and parent.parent.type == "call_expression" and parent.parent.child_by_field_name("function") == parent):
            return "call"  # C++: the method in `obj.size()`
    if name[:1].isupper() and not name.isupper():
        return "class"
    parts = [p.lower() for p in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z0-9]+", name)]
    last = parts[-1] if parts else ""
    for role, vocabulary in _ROLE_WORDS.items():
        if last in vocabulary:
            return role
    if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        return "many"
    return "any"


def _styled(snake: str, old: str) -> str:
    """``snake`` in the case style of ``old`` (UPPER_CASE, CamelCase, camelCase, snake_case)."""
    lead = old[:len(old) - len(old.lstrip("_"))]
    core = old.lstrip("_")
    parts = snake.split("_")
    if core.isupper():
        out = snake.upper()
    elif core[:1].isupper():
        out = "".join(p.capitalize() for p in parts)
    elif "_" not in core and any(ch.isupper() for ch in core):
        out = parts[0] + "".join(p.capitalize() for p in parts[1:])
    else:
        out = snake
    return lead + out


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def _the(win: Window, node: tree_sitter.Node, noun: str) -> str:
    """'the string `'abc'`' when the node can be quoted, else 'this string' (the highlight shows it)."""
    excerpt = _excerpt(win, node)
    return f"the {noun} {excerpt}" if excerpt else f"this {noun}"


def _fit_string(inner: str, *key: object) -> str:
    if "%s" in inner or "{}" in inner:
        pool = ("missing %s", "unknown %s", "bad value: %s") if "%s" in inner else ("missing {}", "unknown {}")
    elif " " in inner.strip():
        pool = MESSAGE_STRINGS
    else:
        pool = WORD_STRINGS
    return _pick_other(pool, inner, *key)


def _fit_value(win: Window, node: tree_sitter.Node, salt: str) -> str | None:
    """Replacement source text of the same kind as ``node``: a string for a string, a name for a name."""
    t, text, key = node.type, _text(node), (win.key, node.start_point, salt)
    if "\n" in text:
        return None
    if t == "string":
        kids = node.children
        if not kids or kids[0].type != "string_start" or any(k.type == "interpolation" for k in kids):
            return None
        start = _text(kids[0])
        q = start[-1:]
        if q not in "'\"" or start.endswith(q * 3) or "\\" in text:
            return None
        return f"{start}{_fit_string(text[len(start):-1], *key)}{q}"
    if t == "integer" or (t == "unary_operator" and re.fullmatch(r"-\d+", text)):
        return _pick_other(INT_TEXTS, text, *key)
    if t == "float":
        return _pick_other(FLOAT_TEXTS, text, *key)
    if t == "identifier":
        return None if text in _BUILTINS or _is_dunder(text) else _new_name(win, text, node, *key)
    if t == "attribute":
        obj, attr = node.child_by_field_name("object"), node.child_by_field_name("attribute")
        if obj is None or attr is None or obj.type != "identifier":
            return None
        return f"{_text(obj)}.{_new_name(win, _text(attr), attr, *key)}"
    return RHS_BY_TYPE.get(t)


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str | None:
    """New contents for change_inner that fit the node, or None when nothing reads naturally."""
    t, key = node.type, (win.key, node.start_point, "ci")
    items = [c for c in node.named_children if c.type != "comment"]
    if t == "string":
        return None if _REGEXISH.search(inner) else _fit_string(inner, *key)
    if t in ("interpolation", "parenthesized_expression"):
        if len(items) != 1 or (t == "interpolation" and items[0].type not in ("identifier", "attribute")):
            return None  # an f-string field holding a call reads oddly as "change it to None"
        if items[0].type == "attribute":  # `{self.numer}` -> `{total}`: `self.x` -> `self.y` is a partial edit
            attr = items[0].child_by_field_name("attribute")
            return _new_name(win, _text(attr), attr, *key) if attr is not None else None
        return _fit_value(win, items[0], "ci")
    if t == "subscript":
        index = node.child_by_field_name("subscript")
        if index is None or len(items) != 2:
            return None
        return _pick_other(SLICE_TEXTS, inner, *key) if index.type == "slice" else _fit_value(win, index, "ci")
    if t == "parameters":
        names = [_text(i) for i in items]
        if len(items) < 2 or any(i.type != "identifier" for i in items) or names[0] in ("self", "cls"):
            return None
        return ", ".join(reversed(names))
    if t in ("argument_list", "tuple", "list", "set", "dictionary"):
        kinds = {i.type == "keyword_argument" for i in items}
        if any(i.type in ("list_splat", "dictionary_splat", "parenthesized_list_splat") for i in items) or len(kinds) > 1:
            return None
        texts = [_text(i) for i in items]
        if len(items) >= 2 and len(set(texts)) == len(texts):
            return ", ".join(reversed(texts))
        if len(items) == 1 and t != "dictionary":
            return _fit_value(win, items[0], "ci")
        return _pick_other(BRACE_TEXTS, inner, *key) if t == "dictionary" else None
    if t in ("dictionary_comprehension", "set_comprehension"):
        return _pick_other(BRACE_TEXTS, inner, *key)
    return None


def _inner_span(win: Window, node: tree_sitter.Node) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node."""
    if node.type == "string":
        kids = node.children
        if len(kids) < 2 or kids[0].type != "string_start" or kids[-1].type != "string_end":
            return None
        start = _text(kids[0])
        q = start[-1:]
        if q not in "\"'" or start.endswith(q * 3) or any(k.type == "interpolation" for k in kids):
            return None
        row, oc, cc = node.start_point.row, kids[0].end_point.column - 1, kids[-1].start_point.column
        inner = win.lines[row][oc + 1:cc] if node.end_point.row == row else ""
        if len(inner.strip()) < 3 or "\\" in inner or q in inner:
            return None
    else:
        pair = _bracket_pair(node)
        if pair is None or pair[0][0] != pair[1][0]:
            return None
        (row, oc, q), (_, cc, _) = pair
        inner = win.lines[row][oc + 1:cc]
        if len(inner.strip()) < 3:
            return None
    if _delim_count(win, q) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _bracket_pair(node: tree_sitter.Node) -> tuple[tuple[int, int, str], tuple[int, int, str]] | None:
    kids = node.children
    if node.type == "subscript":
        opens = [k for k in kids if k.type == "["]
        closes = [k for k in kids if k.type == "]"]
        if not opens or not closes:
            return None
        o, c = opens[0], closes[-1]
    elif node.type == "string" or len(kids) < 2:
        return None
    else:
        o, c = kids[0], kids[-1]
    if o.type not in "([{" or _PAIR.get(o.type) != c.type:
        return None
    return (o.start_point.row, o.start_point.column, o.type), (c.start_point.row, c.start_point.column, c.type)


def _delim_count(win: Window, ch: str) -> int:
    counts = win.cache.get("delims")
    if counts is None:
        counts = win.cache["delims"] = {}
        stack = [win.root]
        while stack:
            n = stack.pop()
            if n.type == "string" and n.children and n.children[0].type == "string_start":
                q = _text(n.children[0])[-1:]
                counts[q] = counts.get(q, 0) + 1
            elif n.type in "([{":
                counts[n.type] = counts.get(n.type, 0) + 1
            stack.extend(n.children)
    return counts.get(ch, 0)


def _cursor_inside(win: Window, node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace and not inside a nested same pair."""
    line = win.lines[row]
    if o in "\"'":
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        strings = _string_cells(win)
        cols = [c for r, c in _depth0_positions(win, (row, oc), (row, cc), o, _PAIR[o]) if (r, c) not in strings]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _depth0_positions(win: Window, open_rc, close_rc, o: str, c: str) -> list[tuple[int, int]]:
    out, depth = [], 0
    (r0, c0), (r1, c1) = open_rc, close_rc
    for r in range(r0, r1 + 1):
        line = win.lines[r]
        lo = c0 + 1 if r == r0 else 0
        hi = c1 if r == r1 else len(line)
        for i in range(lo, hi):
            ch = line[i]
            if ch == o:
                depth += 1
            elif ch == c:
                depth -= 1
            elif depth == 0 and not ch.isspace() and ch not in "()[]{}":
                out.append((r, i))
    return out


def _first_on_line(lines: list[str], pos, target, ch: str, forward: bool) -> bool:
    """True when a plain f/F jump from ``pos`` would already land on ``target``."""
    (r, c), (tr, tc) = pos, target
    if r != tr:
        return False
    segment = lines[r][c + 1:tc] if forward else lines[r][tc + 1:c]
    return ch not in segment


def _away_from(lines: list[str], hits: list[tuple[int, int]], width: int) -> tuple[int, int] | None:
    covered = {(r, c + i) for r, c in hits for i in range(width)}
    for r, ln in enumerate(lines):
        for c, ch in enumerate(ln):
            if not ch.isspace() and (r, c) not in covered:
                return r, c
    return None


def _line_move(win: Window, node: tree_sitter.Node, salt: str) -> tuple[int, int, bool] | None:
    """(row, distance, down) for moving/copying a one-line statement among one-line siblings."""
    options = _line_options(win, node)
    return pick(options, win.key, node.start_point, salt) if options else None


def _line_options(win: Window, node: tree_sitter.Node) -> list[tuple[int, int, bool]] | None:
    """Every (row, distance 1-3, down) move of a one-line statement past one-line siblings;
    None when the node is not a one-line statement in a block."""
    parent = node.parent
    if parent is None or parent.type not in ("block", "module", "decorated_definition"):
        return None
    if node.start_point.row != node.end_point.row:
        return None
    siblings = [s for s in parent.named_children if s.type != "comment"]
    rows = {s.start_point.row for s in siblings if s.start_point.row == s.end_point.row}
    row = node.start_point.row
    options = []
    for k in (1, 2, 3):
        if all(row + i in rows for i in range(1, k + 1)):
            options.append((row, k, True))
        if all(row - i in rows for i in range(1, k + 1)):
            options.append((row, k, False))
    return [o for o in options if win.lines[o[0] + (o[1] if o[2] else -o[1])].strip() != win.lines[row].strip()
            and "`" not in win.lines[o[0] + (o[1] if o[2] else -o[1])]]


def _item_rows(win: Window, node: tree_sitter.Node) -> list[int] | None:
    """Rows of a collection written one item per line, each line ``item,``, brackets on their own lines."""
    pair = _bracket_pair(node)
    if pair is None:
        return None
    (orow, _, o), (crow, ccol, _) = pair
    lines = win.lines
    if crow - orow < 2 or lines[orow].rstrip()[-1:] != o or _indent(lines[crow]) != ccol:
        return None
    items = node.named_children
    rows = []
    for i, item in enumerate(items):
        r = item.start_point.row
        if item.type == "comment" or item.end_point.row != r or item.start_point.column != _indent(lines[r]):
            return None
        rest = lines[r][item.end_point.column:]
        if rest == ",":
            rows.append(r)
        elif i < len(items) - 1 or rest:
            return None
    item_rows = [it.start_point.row for it in items]
    return rows if item_rows == list(range(orow + 1, crow)) else None


def _assignment_runs(win: Window, node: tree_sitter.Node, min_len: int) -> Iterator[list[tree_sitter.Node]]:
    """Runs of >= min_len one-line ``name = value`` statements on consecutive rows, as assignment nodes."""
    run: list[tree_sitter.Node] = []
    for kid in [*node.named_children, None]:
        assign = None
        if kid is not None and kid.type == "expression_statement" and kid.named_child_count == 1:
            a = kid.named_children[0]
            left = a.child_by_field_name("left")
            if (a.type == "assignment" and left is not None and left.type in ("identifier", "attribute")
                    and a.child_by_field_name("right") is not None and kid.start_point.row == kid.end_point.row
                    and "#" not in win.lines[kid.start_point.row]):
                assign = a
        if assign is not None and (not run or assign.start_point.row == run[-1].start_point.row + 1):
            run.append(assign)
            continue
        if len(run) >= min_len:
            yield run
        run = [assign] if assign is not None else []


def _vim_regex(pattern: str) -> re.Pattern:
    """Python equivalent of a small magic-mode Vim pattern: literals, ``.``, ``*``, ``^``, ``\\s``."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            out.append({"s": r"\s", "<": r"\b", ">": r"\b"}.get(pattern[i + 1], re.escape(pattern[i + 1])))
            i += 2
            continue
        if ch == "$" and i == len(pattern) - 1:
            out.append("$")
        else:
            out.append("." if ch == "." else "*" if ch == "*" else "^" if ch == "^" and i == 0 else re.escape(ch))
        i += 1
    return re.compile("".join(out))


def _matching_rows(lines: list[str], pattern: str) -> list[int]:
    rx = _vim_regex(pattern)
    return [r for r, ln in enumerate(lines) if rx.search(ln)]


def _line_groups(win: Window) -> list[tuple[str, list[str], list[int]]]:
    """(label, candidate patterns with the full one last, rows) for :g drills: lines that are one
    call statement of the same function, and comment-only lines."""
    groups: dict[str, list[int]] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type != "expression_statement" or n.named_child_count != 1 or n.start_point.row != n.end_point.row:
            continue
        call = n.named_children[0]
        fn = call.child_by_field_name("function") if call.type == "call" else None
        row = n.start_point.row
        if fn is None or not re.fullmatch(r"[A-Za-z_][\w.]*", _text(fn)) or n.end_point.column != len(win.lines[row]):
            continue
        groups.setdefault(_text(fn), []).append(row)
    out = [(f"line that calls `{fn}(...)`", [fn[:i] for i in range(1, len(fn) + 1)], sorted(rows))
           for fn, rows in sorted(groups.items())]
    lines = win.lines
    comments = [r for r, ln in enumerate(lines) if ln.lstrip().startswith("#")]
    if comments:
        out.append(("comment-only line", ["#", "^#", "^ *#", "^\\s*#"], comments))
    blank = [r for r, ln in enumerate(lines) if not ln]
    if blank and all(ln == ln.rstrip() for ln in lines):
        out.append(("blank line", ["^$"], blank))
    prose = _prose_rows(win)
    docs = [r for r, ln in enumerate(lines) if _ONE_LINE_DOC.fullmatch(ln) and r not in prose]
    if docs:
        q = lines[docs[0]].strip()[:3]
        out.append(("one-line docstring", [q[:i] for i in range(1, 4)], docs))
    for word in ("assert", "import"):
        rows = [r for r, ln in enumerate(lines) if ln.lstrip().startswith(word + " ")]
        if rows:
            out.append((f"`{word}` line", [word[:i] for i in range(1, len(word) + 1)], rows))
    return out


def _keep_patterns(win: Window) -> list[tuple[str, str]]:
    """(label, pattern) for :v drills: keep an outline of definitions, returns or one call."""
    out = [("`def` lines", "def "), ("`return` lines", "return "), ("`import` lines", "import "),
           ("`class` lines", "class ")]
    out += [(label.replace("line that calls", "lines that call"), patterns[-1])
            for label, patterns, rows in _line_groups(win) if label.startswith("line that calls") and len(rows) >= 2]
    return out

