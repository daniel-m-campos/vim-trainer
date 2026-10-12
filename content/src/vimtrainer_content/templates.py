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

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Final

import tree_sitter

from vimtrainer_content.lang import Language
from vimtrainer_content.snippets import Window, pick, stable_hash

MAX_PER_WINDOW: Final = 2  # drafts kept per (window, template, skill), spreads exercises across code

STRING_TEXTS: Final = ("retrying", "not found", "done", "invalid input", "unknown", "skipped", "empty", "error: %s")
ARG_TEXTS: Final = ("value", "self.items", "None", "key, value", "data", "x + 1", "*args", "0")
LIST_TEXTS: Final = ("1, 2, 3", "None", "'a', 'b'", "x for x in items", "0", "key")
SUBSCRIPT_TEXTS: Final = ("0", "-1", "1:", "key", "i + 1", "index")
BRACE_TEXTS: Final = ("'key': value", "**defaults", "'name': name", "1, 2")
INTERP_TEXTS: Final = ("name", "value!r", "count:>3", "len(items)", "self.name")
KW_VALUES: Final = ("None", "True", "10", "'utf-8'", "1.5", "[]", "key")
RHS_VALUES: Final = ("None", "0", "[]", "{}", "''", "False", "set()", "len(items)")
NAMES: Final = (
    "value", "item", "result", "total", "entry", "current", "number", "text", "letters", "words",
    "size", "index", "record", "amount", "label", "buffer", "target", "source",
)
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
_TEXTS: Final = {
    "string": STRING_TEXTS, "argument_list": ARG_TEXTS, "parameters": ("self", "*args, **kwargs", "value"),
    "parenthesized_expression": ARG_TEXTS, "tuple": ARG_TEXTS, "list": LIST_TEXTS,
    "list_comprehension": LIST_TEXTS, "subscript": SUBSCRIPT_TEXTS, "dictionary": BRACE_TEXTS,
    "set": BRACE_TEXTS, "dictionary_comprehension": BRACE_TEXTS, "set_comprehension": BRACE_TEXTS,
    "interpolation": INTERP_TEXTS,
}
_ORDINALS: Final = ("", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th")


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
    params: dict[str, Any] = field(default_factory=dict)
    hints: list[dict[str, str | None]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Stable 10-hex id from the content of the exercise."""
        return stable_hash(self.window.key, self.template, self.skill, self.lines, self.cursor, self.expect)[:10]

    def exercise(self, lang: str) -> dict[str, Any]:
        """Oracle-ready exercise dict (par filled in later by the build)."""
        return {
            "skill": self.skill, "lang": lang, "kind": self.kind,
            "start": {"lines": self.lines, "cursor": self.cursor}, "expect": self.expect,
            "par": {"keys": self.variants[0]}, "alternates": self.alternates, "params": self.params,
        }


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
    """1 -> '1st'."""
    return _ORDINALS[n] if n < len(_ORDINALS) else f"{n}th"


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>``: replace the contents of a single-line delimited node."""
    span = _inner_span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    line, inner = win.lines[row], win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    text = _pick_other(_TEXTS[node.type], inner, win.key, node.start_point, "ci")
    c, noun = _PAIR[o], _NOUNS[node.type]
    yield Draft(
        template="change_inner", skill=skill, kind="edit",
        task=f"Change the contents of this {noun} {_excerpt(win, node)} to `{text}`",
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
        task=f"Delete everything inside this {noun} {_excerpt(win, node)}, keeping the {o}{c}",
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
    text = _pick_other(ARG_TEXTS, value, win.key, node.start_point, "arg")
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
    text = _pick_other(KW_VALUES, old, win.key, node.start_point, "kw")
    d = line[v1] if v1 < len(line) else ""
    if d and d in old:
        return
    variants = [f"ct{d}{text}<Esc>"] if d in (",", ")") else []
    variants += [f"{m}{text}<Esc>" for m in ("cw", "ce", "cE", "cW")]
    if v1 == len(line):
        variants.append(f"C{text}<Esc>")
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
    text = _pick_other(RHS_VALUES, old, win.key, node.start_point, "rhs")
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
    if not (upper or lower) or name in lang.keywords or _seen(win, "case", name):
        return
    row, c0 = node.start_point.row, node.start_point.column
    col = c0 + pick(range(1, len(name)), win.key, node.start_point, "case")
    new = name.upper() if upper else name.lower()
    op, verb = ("gU", "Uppercase") if upper else ("gu", "Lowercase")
    yield Draft(
        template="upper_word", skill=skill, kind="edit", task=f"{verb} the identifier `{name}` under the cursor",
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
    if _seen(win, "word", name):
        return
    row, c0 = node.start_point.row, node.start_point.column
    col = c0 + pick(range(1, len(name)), win.key, node.start_point, "word")
    new = _new_name(win, name, node.start_point)
    yield Draft(
        template="rename_here", skill=skill, kind="edit", task=f"Rename this `{name}` to `{new}` (only this one)",
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
    """``:%s/\\<old\\>/new/g<CR>``: rename every whole-word occurrence (ex kind)."""
    old = _text(node)
    if len(old) < 3 or old in lang.keywords or not re.fullmatch(r"[A-Za-z_]\w*", old) or _seen(win, "subst", old):
        return
    rx = re.compile(rf"\b{old}\b")
    hits = [(r, m.start()) for r, ln in enumerate(win.lines) for m in rx.finditer(ln)]
    if len(hits) < 3 or len({r for r, _ in hits}) < 2:
        return
    new = _new_name(win, old, node.start_point)
    cursor = _away_from(win.lines, hits, len(old))
    if cursor is None:
        return
    patterns = (old, f"{old}\\>", f"\\<{old}", f"\\<{old}\\>")
    variants = [f":%s/{p}/{new}{flag}<CR>" for flag in ("", "/g") for p in patterns]
    yield Draft(
        template="rename_all_subst", skill=skill, kind="ex",
        task=f"Rename every `{old}` to `{new}` ({len(hits)} occurrences)",
        lines=win.lines, cursor=[cursor[0] + 1, cursor[1]], expect={"lines": [rx.sub(new, ln) for ln in win.lines]},
        variants=sorted(variants, key=len), typed=len(new), params={"old": old, "new": new},
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
    if down:
        variants = [f":m+{k}<CR>", f":m{row + k + 1}<CR>"]
    else:
        variants = [f":m-{k + 1}<CR>", f":m{row - k}<CR>"]
    where = "below" if down else "above"
    yield Draft(
        template="move_line", skill=skill, kind="ex",
        task=f"Move this line {where} `{_clip(lines[other].strip())}`",
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": expect},
        variants=sorted(variants, key=len), alternates=[v.replace(":m", ":move ") for v in variants],
        target=[_range(row, 0, row, len(lines[row]) - 1), _range(other, 0, other, len(lines[other]) - 1)],
        window=win, tags=["line", "move"],
        hints=[
            {"trigger": "^\"?[a-z]?dd", "text": ":m moves the line without touching any register; this drill wants the Ex command."},
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
    if k == 0:
        variants, task = [":t.<CR>", f":t{row + 1}<CR>"], "Duplicate this line (the copy goes right below it)"
    elif down:
        variants, task = [f":t+{k}<CR>", f":t{row + k + 1}<CR>"], f"Copy this line to just below `{_clip(lines[other].strip())}`"
    else:
        variants, task = [f":t-{k + 1}<CR>", f":t{row - k}<CR>"], f"Copy this line to just above `{_clip(lines[other].strip())}`"
    yield Draft(
        template="copy_line", skill=skill, kind="ex", task=task,
        lines=lines, cursor=[row + 1, _indent(lines[row])], expect={"lines": expect},
        variants=sorted(variants, key=len), alternates=[v.replace(":t", ":copy ") for v in variants],
        target=[_range(row, 0, row, len(lines[row]) - 1)]
        + ([_range(other, 0, other, len(lines[other]) - 1)] if k else []),
        window=win, tags=["line", "copy"],
        hints=[
            {"trigger": "^(yy|Y)", "text": ":t copies a line without yank and put; :t. duplicates it in place."},
            {"trigger": None, "text": ":t. duplicates the line; :t+N puts the copy below the line N lines down."},
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
            task=f"Move the cursor to the highlighted line `{_clip(lines[t].strip())}`" + (" (the highlighted one)" if dup else ""),
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
    """True for ``b`` in ``a.b``: renaming one attribute use in place is rarely a real edit."""
    parent = node.parent
    return parent is not None and parent.type == "attribute" and parent.child_by_field_name("attribute") == node


def _seen(win: Window, kind: str, name: str) -> bool:
    seen = win.cache.setdefault(f"seen:{kind}", set())
    if name in seen:
        return True
    seen.add(name)
    return False


def _new_name(win: Window, old: str, *key: object) -> str:
    words = win.cache.get("words")
    if words is None:
        words = win.cache["words"] = set(re.findall(r"\w+", "\n".join(win.lines)))
    return pick([n for n in NAMES if n not in words and n != old], win.key, old, *key)


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
    options = [o for o in options if win.lines[o[0] + (o[1] if o[2] else -o[1])].strip() != win.lines[row].strip()]
    return pick(options, win.key, node.start_point, salt) if options else None
