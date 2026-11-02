"""Lua: tree-sitter-lua node types mapped to skills and templates, plus windowing.

Node type names come from tree-sitter-lua's node-types.json (grammar 0.5). Lua is not a
brace language: a function, ``if`` or loop body is a ``block`` that ends with a keyword
(``end``, ``else``, ``until``), so the brace drills (``di{``, ``>i{``, ``]}``) only apply to
table constructors ``{ ... }``, and o.indent shifts a block body by a count (``{N}>>``).
The module follows lang/js.py (same names, same order). The differences:

- ``windows`` re-indents each file from two spaces (exercism's style) to four, the
  oracle's ``shiftwidth``. Rows inside a multi-line long string (``[[ ... ]]``) are string
  content and stay as they are. A function longer than a window is cut into windows of
  its body statements; a long table constructor into windows of its fields, each kept
  between the table's header line and its closing ``}`` line.
- Comments start with ``--`` (``--[[ ... ]]`` for block comments). The window edges are
  trimmed of comment rows here, read from the tree, so a block comment's inner rows count too.
- Strings are quoted with ``'`` or ``"`` (both drill t.quote) or long brackets
  ``[[ ... ]]``, which have no text object: long strings and comments are masked (their
  rows are prose, their cells are string cells, their brackets are not delimiters). A
  bracket pair with a bracket character in a string between its ends (``('(' .. c)``,
  common in Lua patterns) makes no ``%``, ``])`` or text-object drill: Vim would pair it.
- ``%`` drills only pair ``( [ {``. The oracle does load matchit, and Neovim's Lua
  ftplugin sets ``b:match_words`` so ``%`` on ``if`` / ``function`` / ``do`` cycles through
  ``return`` / ``else`` / ``elseif`` to ``end``; keyword pairs are not drilled (the drill
  would depend on that plugin), but the cursor probes see them like any other motion.
- ``#`` is the length operator, not a comment; gates.py cuts a Lua line at ``--``. It reads
  pair nesting line by line, without long strings, so a text-object draft whose nesting
  the gate would read differently from the tree is dropped here (``_nesting``).

``generate`` registers the ``lua_*`` templates for the duration of one call, as
``js.generate`` does. Grammar-agnostic templates from templates.py are reused through
wrappers that first prime the window cache with Lua facts (``_prime``).
"""

import contextlib
import functools
import re
import textwrap
from collections.abc import Callable, Iterator
from typing import Final

import tree_sitter
import tree_sitter_lua

from vimtrainer_content import gates, snippets, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, Lua column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    "m.match": 1.2, "t.brace": 1.2, "n.unmatched": 1.2, "t.paren": 1.2, "t.bracket": 0.8, "t.quote": 1.5,
    "o.indent": 1.0, "m.find": 1.0, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0, "m.rel": 1.0,
    "o.change": 1.0, "o.case": 1.0, "x.copymove": 1.0, "x.normal": 1.0,
}
TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove", "x.normal",
)
FOUR: Final = "    "  # the indent unit windows are re-indented to (the oracle's shiftwidth)

STRING_TEXTS: Final = ("not found", "invalid input", "out of range", "unknown", "skipped", "empty", "error: ")
ARG_TEXTS: Final = ("#items", "key, count", "0", "count + 1", "name")
PARAM_TEXTS: Final = ("count", "name, options", "items", "s, n")
EXPR_TEXTS: Final = ("count + 1", "n - 1", "a + b", "i * 2")
INDEX_TEXTS: Final = ("1", "i + 1", "index", "key", "#items")
TABLE_TEXTS: Final = ("0", "1, 2, 3", "count = 0", "name = name")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")

_NOUNS: Final = {
    "string": "string", "arguments": "argument list", "parameters": "parameter list",
    "parenthesized_expression": "parenthesised expression", "bracket_index_expression": "index",
    "table_constructor": "table",
}
_TEXTS: Final = {
    "string": STRING_TEXTS, "arguments": ARG_TEXTS, "parameters": PARAM_TEXTS, "parenthesized_expression": EXPR_TEXTS,
    "bracket_index_expression": INDEX_TEXTS, "table_constructor": TABLE_TEXTS,
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
_DELIM_NAMES: Final = {"(": "parentheses", "[": "square brackets", "{": "braces", '"': "quotes", "'": "quotes"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), '"': (), "'": ()}
_QUOTES: Final = frozenset({'"', "'"})
_MASKED: Final = frozenset({"string", "comment"})  # cells that are not code; long strings included
_FUNCTIONS: Final = frozenset({"function_declaration", "function_definition"})
_LINE_PARENTS: Final = frozenset({"chunk", "block"})
_LAST_ONLY: Final = frozenset({"return_statement", "break_statement", "goto_statement", "label_statement"})
# o.indent: the statements whose body is a block, and the word that names each in a task.
_BLOCK_OWNERS: Final = frozenset({
    "function_declaration", "function_definition", "if_statement", "for_statement", "while_statement",
    "repeat_statement", "do_statement",
})
_CLOSERS: Final = ("end", "else", "elseif", "until")
_CLOSER_LINE: Final = re.compile(r"\}[)\],]*")
_COMMENT_START: Final = re.compile(r"\s*--")
_DELETED: Final = {
    "if_statement": "this `if` statement", "for_statement": "this `for` loop", "while_statement": "this `while` loop",
    "repeat_statement": "this `repeat` loop",
}
_VALUE_ROLES: Final = {
    "table_constructor": "many", "number": "count", "string": "text", "true": "flag", "false": "flag",
    "function_definition": "call",
}
_LITERALS: Final = frozenset({"number", "string", "true", "false"})
# x.normal: one-line statements a `:norm` range runs over, and the prefixes a run can share.
# A run with no shared prefix is commented out with `-- ` instead (function bodies only).
_RUN_ITEMS: Final = frozenset({"variable_declaration", "assignment_statement", "function_call"})
_PREFIXES: Final = ("local ", "self.")
_SNAKE: Final = re.compile(r"[a-z][a-z0-9_]*[a-z0-9]")
_KEYWORDS: Final = frozenset("""
    and break do else elseif end false for function goto if in local nil not or repeat return then true until
    while self _G _ENV
    assert collectgarbage dofile error getmetatable ipairs load loadfile next pairs pcall print rawequal rawget
    rawlen rawset require select setmetatable tonumber tostring type unpack xpcall
    string table math io os coroutine utf8 debug package
    byte char find format gmatch gsub len lower match rep reverse sub upper
    concat insert remove sort pack
    abs ceil floor fmod huge log max maxinteger min mininteger modf pi random sqrt tointeger
""".split())

_PAREN = (
    Use("t.paren", ("lua_change_inner", "lua_delete_inner")),
    Use("m.match", ("lua_jump_match",)),
    Use("n.unmatched", ("lua_jump_block_end",)),
)
_IDENT = (
    Use("t.word", ("lua_rename_here",)),
    Use("o.case", ("lua_upper_word",)),
    Use("x.subst", ("lua_rename_all_subst",)),
)
_DELETE = (Use("o.delete", ("lua_delete_lines",)),)
_LINE = (Use("x.copymove", ("lua_move_line", "lua_copy_line")),)
_ASSIGN = (*_LINE, Use("o.change", ("lua_change_rhs",)))

LANG = Language(
    name="lua",
    short="lua",
    grammar="lua",
    nodes={
        "string": (Use("t.quote", ("lua_change_inner", "lua_delete_inner")), Use("o.case", ("lua_upper_inner",))),
        "arguments": (*_PAREN, Use("o.change", ("lua_change_nth_arg",))),
        "parameters": _PAREN,
        "parenthesized_expression": _PAREN,
        "table_constructor": (
            Use("t.brace", ("lua_change_inner", "lua_delete_inner", "lua_delete_block")),
            Use("m.match", ("lua_jump_match",)),
            Use("n.unmatched", ("lua_jump_block_end",)),
        ),
        "bracket_index_expression": (
            Use("t.bracket", ("lua_change_inner", "lua_delete_inner")), Use("m.match", ("lua_jump_match",)),
        ),
        "block": (Use("o.indent", ("lua_indent_block",)), Use("x.normal", ("lua_prefix_each_line",))),
        "chunk": (Use("x.normal", ("lua_prefix_each_line", "lua_upper_constants")),),
        "comment": (Use("o.delete", ("lua_delete_trailing_comment",)),),
        "function_declaration": _DELETE,
        "if_statement": _DELETE,
        "for_statement": _DELETE,
        "while_statement": _DELETE,
        "repeat_statement": _DELETE,
        "identifier": _IDENT,
        "dot_index_expression": (Use("m.find", ("lua_find_member",)),),
        "method_index_expression": (Use("m.find", ("lua_find_member",)),),
        "variable_declaration": _ASSIGN,
        "assignment_statement": _ASSIGN,
        "function_call": _LINE,
    },
    line_templates=(Use("m.rel", ("lua_goto_line_rel",)), Use("m.find", ("lua_find_char",))),
    find_targets=("(", ")", "{", "}", "[", "]", ",", "=", ".", ":"),
    comment_leader="--",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for Lua."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_lua.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse Lua source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a Lua source file into parseable 8-40 line windows (see ``snippets.windows``).

    Parameters
    ----------
    text
        Whole source file.
    source
        The exercise ``source`` object (repo, path, commit, license).

    Returns
    -------
    list[Window]
        Windows that pass the size, width, ASCII and parse checks. The file is re-indented
        to four spaces first (``reindent``); functions and tables longer than 40 lines are
        split by recursing into their bodies, and a window of table fields keeps the
        table's header and closing lines. Licence/author comments break a window and are
        left out; comment-only lines never start or end one.
    """
    lines = reindent(text.splitlines())
    tree = parse("\n".join(lines))  # keep the tree alive while its nodes are walked
    comments = _comment_rows(tree.root_node, lines)
    out = []
    for start, end, wrap in _spans(tree.root_node.named_children, lines):
        win = _make_window(lines, start, end, wrap, source, comments)
        if win is not None:
            out.append(win)
    return out


def reindent(lines: list[str]) -> list[str]:
    """``lines`` re-indented from two-space to four-space levels.

    Every line's indent ``i`` becomes ``i + 2 * (i // 2)``. Rows inside a multi-line long
    string are string content and stay as they are. A file with no line indented
    ``2 (mod 4)`` is already four-space and comes back unchanged.

    Examples
    --------
    >>> reindent(["if x then", "  y()", "end"])
    ['if x then', '    y()', 'end']
    """
    keep = _long_string_rows(parse("\n".join(lines)).root_node)
    code = [_indent(ln) for r, ln in enumerate(lines) if ln.strip() and r not in keep]
    if all(i % 4 != 2 for i in code):
        return list(lines)
    return [ln if r in keep or not ln.strip() else " " * (_indent(ln) + 2 * (_indent(ln) // 2)) + ln.lstrip()
            for r, ln in enumerate(lines)]


def generate(win: Window, lang: Language = LANG) -> list[Draft]:
    """``templates.generate`` for a Lua window, with the ``lua_*`` templates registered.

    The shared registries only know the Python templates; the ``Use`` entries here name
    ``lua_*`` ones, added for the duration of the call and removed again.
    """
    with registered():
        return templates.generate(win, lang)


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``lua_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(LUA_NODE_TEMPLATES, LUA_LINE_TEMPLATES)


def node_frequency(texts: list[str]) -> dict[str, object]:
    """``snippets.node_frequency`` for Lua (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, parse)


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>`` on a single-line string, argument list, table or index."""
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None or (o in _QUOTES and "%" in inner):
        return  # a Lua pattern ('%d+') is not text to replace with prose
    which = _nesting(win, node, row, oc, inner)
    if which is None:
        return
    text = _inner_text(win, node, inner)
    c, noun = _PAIR[o], _noun(node)
    yield Draft(
        template="change_inner", skill=skill, kind="edit",
        task=f"Change {templates._inside_phrase(noun, _DELIM_NAMES[o], inner, which)} to `{text}`",
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
    """``di{delim}``: empty a single-line string, argument list, table or index."""
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    which = _nesting(win, node, row, oc, inner)
    if col is None or which is None:
        return
    c, noun, delims = _PAIR[o], _noun(node), _DELIM_NAMES[o]
    yield Draft(
        template="delete_inner", skill=skill, kind="edit",
        task=f"Delete {templates._inside_phrase(noun, delims, inner, which)}, keeping the {delims}",
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, oc + 1, cc, "")},
        variants=[f"di{o}"], alternates=[f"di{a}" for a in _ALIASES[o]],
        idioms=["diw", "diW", "dw", "dW", "de", "dE", f"dt{c}", f"dT{o}", "bdt" + c, f"F{o}ldt{c}", f"T{o}dt{c}", "D"],
        params={"open": o, "close": c}, target=[_range(row, oc, row, cc)], window=win, tags=[node.type, "delete"],
        hints=[
            {"trigger": "^[0-9]*[hlwbeWBEfFtT]", "text": f"di{o} works from anywhere inside the {noun}."},
            {"trigger": "x{2,}|d[wWeE]", "text": f"di{o} empties the {delims} in one command, whatever is inside."},
            {"trigger": None, "text": f"di{o}: delete inside the {delims} around the cursor."},
        ],
    )


def delete_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``di{``: empty a multi-line table whose braces sit at line end / line start."""
    pair = _bracket_pair(node)
    if pair is None or pair[0][2] != "{":
        return
    (orow, ocol, _), (crow, ccol, _) = pair
    lines = win.lines
    n = crow - orow - 1
    if not 4 <= n <= 15 or lines[orow][ocol + 1:].strip() or lines[crow][:ccol].strip():
        return
    if _delims(win).get("{", 0) < 2:
        return
    strings = win.cache["strings"]
    cols = [p for p in _depth0_positions(win, (orow, ocol), (crow, ccol), "{", "}") if p not in strings]
    if not cols:
        return
    row, col = pick(cols, win.key, node.start_point, "blk")
    header = _header(win, node, orow)
    yield Draft(
        template="delete_inner", skill=skill, kind="edit",
        task=f"Delete the {n} lines inside the braces of {templates._quote(header)}, keeping the `{{` and `}}` lines",
        lines=lines, cursor=[row + 1, col], expect={"lines": lines[:orow + 1] + lines[crow:]},
        variants=["di{", "diB"], alternates=["di}"],
        idioms=["dap", "dip", "d}", "d{", "d]}", "d[{", f"{n}dd", "dd", "D"],
        params={"open": "{", "close": "}"}, target=[_range(orow + 1, 0, crow - 1, max(len(lines[crow - 1]) - 1, 0))],
        window=win, tags=[node.type, "delete", "lines"],
        hints=[
            {"trigger": "^[0-9]*(dd|j|k)", "text": "di{ empties the table from anywhere inside it, however many lines."},
            {"trigger": "^V", "text": "di{ needs no visual selection; it finds the enclosing braces itself."},
            {"trigger": None, "text": "di{ (or diB): delete inside the {} pair around the cursor."},
        ],
    )


def upper_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUi'`` / ``gUi"``: uppercase the text inside a string literal."""
    span = _span(win, node)
    if span is None or span[3] not in _QUOTES:
        return
    row, oc, cc, q = span
    inner = win.lines[row][oc + 1:cc]
    if not (4 <= len(inner) <= 30 and re.fullmatch(r"[a-z][a-z ,.:!?_-]*", inner)):
        return
    col = _cursor_inside(win, node, row, oc, cc, q)
    if col is None:
        return
    which = templates._which_pair(win, row, oc, inner, False)
    yield Draft(
        template="upper_inner", skill=skill, kind="edit",
        task=f"Uppercase {templates._inside_phrase('string', 'quotes', inner, which)}",
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


def change_nth_arg(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}f,wct,X<Esc>``: change the n-th argument of a single-line call from the call start."""
    call = node.parent
    if call is None or call.type != "function_call" or node.start_point.row != node.end_point.row:
        return
    row = node.start_point.row
    kids = node.children
    if call.start_point.row != row or not kids or kids[0].type != "(":
        return
    args = [a for a in node.named_children if a.type != "comment"]
    if len(args) < 2:
        return
    n = pick(range(2, len(args) + 1), win.key, node.start_point, "nth")
    arg = args[n - 1]
    line, a0, a1 = win.lines[row], arg.start_point.column, arg.end_point.column
    value = line[a0:a1]
    if not re.fullmatch(r"[\w.+\-*/ '\":]+", value) or a1 >= len(line) or line[a1] not in ",)":
        return
    cursor, d = call.start_point.column, line[a1]
    k = line[cursor:a0].count(",")
    text = _fit(win, arg, value)
    if k < 1 or text is None:
        return
    fk = f"{k}f," if k > 1 else "f,"
    kd = line[cursor + 1:a1 + 1].count(d)
    fd = f"{kd}f{d}" if kd > 1 else f"f{d}"
    fn = templates._call_name(_text(call.child_by_field_name("name")))
    where = templates.on_this_line(win.lines, row, f"{fn}(")
    if where is None or not re.fullmatch(r"[\w.:]+", fn):
        return  # `self.rep[y + 1]:sub` is no name to quote
    yield Draft(
        template="change_nth_arg", skill=skill, kind="edit",
        task=f"Change the {templates.ordinal(n)} argument of the `{fn}` call{where} from `{value}` to `{text}`",
        lines=win.lines, cursor=[row + 1, cursor], expect={"lines": _replace(win.lines, row, a0, a1, text)},
        variants=[f"{fk}w{m}{text}<Esc>" for m in (f"ct{d}", "cw", "ce", "cE", "cW")],
        alternates=[f"f,{';' * (k - 1)}wct{d}{text}<Esc>"] if k > 1 else [],
        idioms=[f"{fd}cT{line[a0 - 1]}{text}<Esc>", f"{fk}lct{d}{text}<Esc>", f"{fk}wC{text}{line[a1:]}<Esc>"],
        typed=len(text), params={"text": text, "n": n, "char": ","},
        target=[_range(row, a0, row, a1 - 1)], window=win, tags=["call-argument", "find", "change"],
        hints=[
            {"trigger": "^[0-9]*[wWeEl]{3,}", "text": f"{fk} jumps straight to the comma before the {templates.ordinal(n)} argument."},
            *([{"trigger": "^f,;", "text": f"A count on f ({fk}) replaces the ; presses."}] if k > 1 else []),
            {"trigger": "x{2,}|d[wWeE]", "text": f"ct{d} changes up to the next {d} without deleting first."},
            {"trigger": None, "text": f"{fk}w puts you on the argument; ct{d} changes it up to the {d}."},
        ],
    )


def change_rhs(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``C X<Esc>``: replace the value of a one-line ``local x = ...`` / ``x = ...``, cursor on it."""
    if node.start_point.row != node.end_point.row or node.parent is None or node.parent.type not in _LINE_PARENTS:
        return
    assign = node if node.type == "assignment_statement" else next(
        (c for c in node.named_children if c.type == "assignment_statement"), None)
    if assign is None:
        return
    names = [c for c in assign.named_children if c.type == "variable_list"]
    values = [c for c in assign.named_children if c.type == "expression_list"]
    if len(names) != 1 or len(values) != 1 or names[0].named_child_count != 1 or values[0].named_child_count != 1:
        return
    left, right = names[0].named_children[0], values[0].named_children[0]
    if right.type in _FUNCTIONS:
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old = line[r0:r1]
    if line[r1:].strip() or len(old) < 6:
        return
    text = _fit(win, right, old)
    where = templates.on_this_line(win.lines, row, f"{_text(left)} = ")  # `clone[k] = ...` on two lines
    if text is None or where is None:
        return
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to {templates._quote(_text(left), 32)}{where} with `{text}`",
        lines=win.lines, cursor=[row + 1, r0], expect={"lines": _replace(win.lines, row, r0, len(line), text)},
        variants=[f"C{text}<Esc>", f"c${text}<Esc>"], alternates=[f"Da{text}<Esc>"],
        idioms=[f"cW{text}<Esc>", f"cw{text}<Esc>", f"ce{text}<Esc>"],
        typed=len(text), params={"text": text},
        target=[_range(row, r0, row, r1 - 1)], window=win, tags=["assignment", "change"],
        hints=[
            {"trigger": "^(D|d\\$)", "text": "C deletes to the end of the line and enters insert mode in one command."},
            {"trigger": "x{3,}|^c[wWeE]", "text": "C changes everything from the cursor to the end of the line."},
            {"trigger": None, "text": "C (= c$) changes from the cursor to the end of the line."},
        ],
    )


def indent_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{N}>>`` / ``>{N-1}j`` (or ``<``): fix a block body that is one level under- or over-indented.

    The body must have whole lines to itself, between its header line (``function ...``,
    ``if ... then``, ``for ... do``) and a line that starts with ``end``, ``else``,
    ``elseif`` or ``until``. Lua has no ``i{`` for such a body, so the count is the skill.
    """
    owner = node.parent
    if owner is None or owner.type not in _BLOCK_OWNERS:
        return
    lines = win.lines
    start, end = node.start_point.row, node.end_point.row
    n = end - start + 1
    if not 2 <= n <= 12 or start <= owner.start_point.row or end + 1 >= len(lines):
        return
    if node.start_point.column != _indent(lines[start]) or lines[end][node.end_point.column:].strip():
        return
    closer = lines[end + 1].strip()
    if not any(closer == w or closer.startswith(w + " ") for w in _CLOSERS):
        return
    rows = range(start, end + 1)
    if any(not lines[r].strip() for r in rows):
        return  # the highlight skips blank lines, so "these N lines" would not match N>> (QA #26)
    base = _indent(lines[end + 1])
    if min(_indent(lines[r]) for r in rows) != base + len(FOUR) or _indent(lines[owner.start_point.row]) != base:
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    shifted = [(ln[4:] if under else FOUR + ln) if r in rows else ln for r, ln in enumerate(lines)]
    op = ">>" if under else "<<"
    o = op[0]
    yield Draft(
        template="indent_block", skill=skill, kind="edit",
        task=templates.indent_task(lines[owner.start_point.row].strip(), under, n),
        lines=shifted, cursor=[start + 1, _indent(shifted[start])], expect={"lines": lines},
        variants=[f"{n}{op}", f"{o}{n - 1}j"], alternates=[f"V{n - 1}j{o}"],
        idioms=[f"{o}ip", f"{o}ap", f"{o}}}", f"{o}G", f"{o}i{{"],
        target=[_range(start, 0, end, max(len(shifted[end]) - 1, 0))], window=win, tags=["block", "indent"],
        hints=[
            {"trigger": f"({op}j)|({op}\\.)|(j\\.)", "text": f"{n}{op} shifts all {n} lines in one command."},
            {"trigger": "^[0-9]*I|^\\^?i", "text": f"{op} shifts by shiftwidth; there is no need to type spaces."},
            {"trigger": None, "text": f"{n}{op} or {o}{n - 1}j shift the {n} lines of the body."},
        ],
    )


def move_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:m+k<CR>`` / ``:m-k<CR>`` or ``ddp``: move a one-line statement among its one-line siblings."""
    plan = _line_move(win, node, "move")
    if plan is None:
        return
    row, k, down = plan
    lines = win.lines
    other = row + k if down else row - k
    moved = lines[:row] + lines[row + 1:]
    expect = [*moved[:other], lines[row], *moved[other:]]
    if down:
        variants = [f":m+{k}<CR>", f":m{row + k + 1}<CR>", "ddp" if k == 1 else f"dd{k - 1}jp"]
    else:
        variants = [f":m-{k + 1}<CR>", f":m{row - k}<CR>", f"dd{k}kP" if k > 1 else "ddkP"]
    yield Draft(
        template="move_line", skill=skill, kind="edit",
        task=f"Move this line {'below' if down else 'above'} {templates._quote(lines[other].strip())}",
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
    """``:t.<CR>`` / ``:t+k<CR>`` / ``:t-k<CR>`` or ``yyp``: copy a one-line statement."""
    plan = _line_move(win, node, "copy")
    if plan is None:
        return
    row, k, down = plan
    lines = win.lines
    if pick((True, False, False), win.key, node.start_point, "dup"):
        k, down = 0, True
    other = row + k if down else row - k
    dest = other + 1 if down else other
    expect = [*lines[:dest], lines[row], *lines[dest:]]
    if k == 0:
        variants, task = [":t.<CR>", f":t{row + 1}<CR>", "yyp"], "Duplicate this line (the copy goes right below it)"
    elif down:
        variants = [f":t+{k}<CR>", f":t{row + k + 1}<CR>", "yyjp" if k == 1 else f"yy{k}jp"]
        task = f"Copy this line to just below {templates._quote(lines[other].strip())}"
    else:
        variants = [f":t-{k + 1}<CR>", f":t{row - k}<CR>", "yykP" if k == 1 else f"yy{k}kP"]
        task = f"Copy this line to just above {templates._quote(lines[other].strip())}"
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


def find_member(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}f.`` / ``{k}f:``: from the first non-blank, jump to the ``.`` or ``:`` before a field or method."""
    field = node.child_by_field_name("field") or node.child_by_field_name("method")
    op = next((c for c in node.children if c.type in (".", ":")), None)
    if op is None or field is None or op.start_point.row != field.end_point.row:
        return
    ch, row, col = op.type, op.start_point.row, op.start_point.column
    line = win.lines[row]
    start = _indent(line)
    if row in win.cache["prose"] or not line[start:start + 1] or _COMMENT_START.match(line):
        return
    name = _text(field)
    k = line.count(ch, start + 1, col + 1)
    if not 1 <= k <= 3 or col - start < 3 * (2 if k == 1 else 3) + 1 or line.count(f"{ch}{name}") != 1:
        return
    motion = f"{k}f{ch}" if k > 1 else f"f{ch}"
    yield Draft(
        template="find_char", skill=skill, kind="cursor", task=f"Move to the `{ch}` before `{name}`",
        lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
        variants=[motion], alternates=[f"f{ch}" + ";" * (k - 1)] if k > 1 else [],
        idioms=list(templates.CURSOR_IDIOMS), params={"char": ch, "n": k},
        target=[_range(row, col, row, col)], window=win, tags=["find", "member"],
        hints=[
            {"trigger": "l{4,}|w{3,}|e{3,}", "text": f"f{ch} jumps to the next `{ch}` on the line" + (f"; {motion} to the {templates.ordinal(k)}." if k > 1 else ".")},
            *([{"trigger": f"^f{_js_escape(ch)};", "text": f"A count before f replaces the ; presses: {motion}."}] if k > 1 else []),
            {"trigger": None, "text": f"{motion}: find the {templates.ordinal(k)} `{ch}` to the right."},
        ],
    )


def jump_match(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``%``: from one ``(``, ``[`` or ``{`` to its partner (either direction, possibly across lines).

    Pairs with a bracket character in a string or comment between them are skipped (``%``
    would count it), and so are index brackets next to another bracket of their kind
    (matchit reads ``]]`` as the end of a long string).
    """
    pair = _pair(node)
    if pair is None or not _clean_pair(win, pair):
        return
    (orow, ocol, o), (crow, ccol, c) = pair
    if o == "[" and ("[[" in win.lines[orow][ocol - 1:ocol + 2] or "]]" in win.lines[crow][ccol - 1:ccol + 2]):
        return
    forward = pick((True, False), win.key, node.start_point, "dir")
    here, there = ((orow, ocol), (crow, ccol)) if forward else ((crow, ccol), (orow, ocol))
    a, b = (o, c) if forward else (c, o)
    yield Draft(
        template="jump_match", skill=skill, kind="cursor",
        task=f"Jump from this `{a}` to its matching `{b}`",
        lines=win.lines, cursor=[here[0] + 1, here[1]], expect={"cursor": [there[0] + 1, there[1]]},
        variants=["%"], idioms=[*templates.CURSOR_IDIOMS, f"f{b}", f"F{b}", f"2f{b}", f"2F{b}"],
        target=[_range(there[0], there[1], there[0], there[1])], window=win, tags=[node.type, "bracket"],
        hints=[
            {"trigger": "^[0-9]*[fFtT]", "text": "% jumps to the matching bracket in one key, across lines too."},
            {"trigger": "[jklhwb]{3,}", "text": "% finds the partner of the bracket under the cursor."},
            {"trigger": None, "text": "% jumps between matching (), [] and {}."},
        ],
    )


def jump_block_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_block_end`` (``])`` / ``]}``, ``[(`` / ``[{``) with Lua nouns, strings and
    comments masked, and no bracket character in a string between the pair."""
    pair = _bracket_pair(node)
    if pair is None or not _clean_pair(win, pair):
        return
    for draft in templates.jump_block_end(win, node, skill, lang):
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_noun(node)} around the cursor", draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f-D`` (``{k}f-D`` past minus signs): ``templates.delete_trailing_comment`` for one-line comments.

    Comments after a bare ``end`` or ``}`` are skipped: retyping the code is cheaper.
    """
    row = node.start_point.row
    if row != node.end_point.row or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    if win.lines[row][node.end_point.column:].strip():
        return  # a mid-line `--[[ ]]` with code after it is not a trailing comment
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` (``{N}dd``, ``d}``, ``dap``) with Lua task text."""
    what = _DELETED.get(node.type, "this statement")
    if node.type == "function_declaration":
        name = _text(node.child_by_field_name("name"))
        what = f"the function `{name}`" if name and len(name) <= 40 else "this function"
    for draft in templates.delete_lines(win, node, skill, lang):
        n = node.end_point.row - node.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def upper_word(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUiw`` / ``guiw``: change the case of a top-level constant's name (``local max_items = 50``),
    defined once and used nowhere else in the window."""
    name = _text(node)
    upper = bool(re.fullmatch(r"[a-z][a-z0-9_]{4,}", name))
    lower = bool(re.fullmatch(r"[A-Z][A-Z0-9_]{3,}", name)) and any(ch.isalpha() for ch in name)
    if not (upper or lower) or name in lang.keywords or _constant_value(win, node) is None:
        return
    if templates._seen(win, "case", name):
        return
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
        params={"word": name}, target=[_range(row, c0, row, c0 + len(name) - 1)], window=win,
        tags=["identifier", "case"],
        hints=[
            {"trigger": "^~|~~", "text": f"{op}iw changes the whole word in one command; ~ flips one character."},
            {"trigger": "^(b|0|\\^)", "text": "iw works from anywhere in the word; no need to move to its start."},
            {"trigger": "^c|^s|^x", "text": f"{op} changes case without retyping the word."},
            {"trigger": None, "text": f"{op}iw: {verb.lower()} inner word."},
        ],
    )


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here`` (``ciw``) on a primed window, skipping fields, methods,
    table keys and the names of called functions (see ``_renamable``)."""
    if _renamable(node):
        yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst`` (``:%s``) on a primed window; the occurrence that names the
    new name's role must be a variable or a function definition (see ``_renamable``), and no
    occurrence may be a field, method or table key (``:%s`` would rename those too)."""
    if _renamable(node) and _text(node) not in win.cache["members"]:
        yield from templates.rename_all_subst(win, node, skill, lang)


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm I{prefix}<CR>`` over 3-8 consecutive one-line statements (x.normal): put back
    a prefix they all share (``local ``, ``self.``), or, when they share none and they sit in a
    function body, comment them out with ``-- `` (never top-level statements)."""
    for run in _statement_runs(win, node, templates.EX_MIN_LINES):
        rows = [item.start_point.row for item in run[:8]]
        if templates._seen(win, f"prefix:{skill}", str(rows[0])):
            continue
        col = _indent(win.lines[rows[0]])
        prefix = next((p for p in _PREFIXES if all(win.lines[r][col:].startswith(p) for r in rows)), None)
        n = len(rows)
        if prefix is not None:
            start = [ln[:col] + ln[col + len(prefix):] if r in rows else ln for r, ln in enumerate(win.lines)]
            expect, tags = win.lines, ["declaration", "normal", "insert"]
            task = f"Add `{prefix.strip()}` at the start of each of these {n} lines"
            target = [_range(r, col, r, col + min(len(prefix), len(start[r]) - col) - 1) for r in rows]
        elif not _in_function_body(node):
            continue  # commenting out top-level declarations is not an edit anyone drills
        else:
            prefix, start = "-- ", win.lines
            expect = [ln[:col] + prefix + ln[col:] if r in rows else ln for r, ln in enumerate(win.lines)]
            tags = ["comment", "normal", "insert"]
            task = f"Comment out these {n} lines: put `-- ` at the start of each"
            target = [_range(r, col, r, len(start[r]) - 1) for r in rows]
        yield templates.normal_prefix(win, skill, rows, prefix, start, expect, task, target, tags)


def upper_constants(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm f=bgUiw<CR>`` over 3+ consecutive top-level ``local name = literal`` lines:
    uppercase the lower_snake names, each used nowhere else in the window (x.normal)."""
    if node.type != "chunk" or win.indent:
        return  # a dedented function body parses as a chunk too
    for run in _statement_runs(win, node, templates.EX_MIN_LINES):
        names = [_const_name(win, d) for d in run]
        if not all(n is not None and _SNAKE.fullmatch(_text(n)) for n in names):
            continue  # ex kind: gUiwj.j. on fewer lines would be the better drill
        rows, names = [d.start_point.row for d in run][:8], names[:8]
        if templates._seen(win, "constants", str(rows[0])):
            continue
        k = len(rows) - 1
        down = f"{k}j" if k > 1 else "j"
        go = "f=b"
        expect = list(win.lines)
        for r, name in zip(rows, names):
            c0, c1 = name.start_point.column, name.end_point.column
            expect[r] = expect[r][:c0] + expect[r][c0:c1].upper() + expect[r][c1:]
        yield Draft(
            template="upper_constants", skill=skill, kind="ex",
            task=f"Uppercase the names of these {k + 1} constants",
            lines=win.lines, cursor=[rows[0] + 1, _indent(win.lines[rows[0]])], expect={"lines": expect},
            variants=[f"V{down}:norm {go}gUiw<CR>", f"V{down}:norm {go}gUe<CR>", f":.,+{k}norm {go}gUiw<CR>",
                      f":{rows[0] + 1},{rows[-1] + 1}norm {go}gUiw<CR>"],
            alternates=[f":.,+{k}normal {go}gUiw<CR>", f"V{down}:normal {go}gUiw<CR>"],
            idioms=[f"V{down}:s/\\<\\l\\w*\\>/\\U&/<CR>", "gUiwj." + "j." * (k - 1)],
            params={"n": k + 1},
            target=[_range(r, n.start_point.column, r, n.end_point.column - 1) for r, n in zip(rows, names)],
            window=win, tags=[node.type, "normal", "case"],
            hints=[
                {"trigger": "^gU|j\\.", "text": f":norm runs {go}gUiw on every line of the range; V{down} selects the {k + 1} lines."},
                {"trigger": ":[^n]*s/", "text": "A substitute works too, but this drill is about :normal."},
                {"trigger": None, "text": f"V{down}:norm {go}gUiw<CR>: select the lines, then run {go}gUiw on each."},
            ],
        )


# Line templates ===================================================================================


def goto_line_rel(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.goto_line_rel`` (``{k}j`` / ``{k}k``) with Lua comment-only lines and long
    strings excluded as start and target."""
    yield from templates.goto_line_rel(win, skill, lang)


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: from the first non-blank, jump to the n-th X on a code line."""
    rows = sorted(range(len(win.lines)), key=lambda r: snippets.stable_hash(win.key, r, "find"))
    prose = win.cache["prose"]
    made = 0
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("", '"', "'") or _COMMENT_START.match(line):
            continue
        options = []
        for ch in lang.find_targets:
            cols = _occurrences(line, ch, start + 1)
            options += [(ch, n, col) for n, col in enumerate(cols[:3], 1) if col - start >= 3 * (2 if n == 1 else 3) + 1]
        if not options:
            continue
        ch, n, col = pick(options, win.key, row, "opt")
        motion = f"{n}f{ch}" if n > 1 else f"f{ch}"
        yield Draft(
            template="find_char", skill=skill, kind="cursor",
            task=f"Move to the {templates.ordinal(n)} `{ch}` on this line",
            lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
            variants=[motion], alternates=[f"f{ch}" + ";" * (n - 1)] if n > 1 else [],
            idioms=list(templates.CURSOR_IDIOMS), params={"char": ch, "n": n},
            target=[_range(row, col, row, col)], window=win, tags=["find", "punctuation"],
            hints=[
                {"trigger": "l{4,}|w{3,}|e{3,}", "text": f"f{ch} jumps to the next `{ch}` on the line" + (f"; {motion} to the {templates.ordinal(n)}." if n > 1 else ".")},
                *([{"trigger": f"^f{_js_escape(ch)};", "text": f"A count before f replaces the ; presses: {motion}."}] if n > 1 else []),
                {"trigger": None, "text": f"{motion}: find the {templates.ordinal(n)} `{ch}` to the right."},
            ],
        )
        made += 1
        if made >= templates.MAX_PER_WINDOW + 1:
            return


# Private Functions ================================================================================


# Shared with the brace languages (see lang/braces.py).
_text = braces.text
_range = braces.highlight
_indent = braces.indent
_replace = braces.replace
_pick_other = braces.pick_other
_js_escape = braces.js_escape
_cells = braces.cells
_bracket_pair = braces.bracket_pair
_depth0_positions = braces.depth0_positions
_worth_it = braces.worth_it
_merge_short = braces.merge_short
_occurrences = braces.occurrences


def _shipping(fn: Callable[..., Iterator[Draft]], gate5: bool = False) -> Callable[..., Iterator[Draft]]:
    """``fn`` with the window primed first and only drafts that pass gate 6 (``gates.target_problem``,
    the build's own check) kept, and with ``gate5`` also gate 5 ahead of the oracle
    (``braces.worth_it``: short texts such as ``[i]`` never beat ``x``), so the per-window cap
    is spent on drafts that can ship."""
    @functools.wraps(fn)
    def wrapped(win: Window, *args) -> Iterator[Draft]:
        _prime(win)
        lang = args[-1]
        for draft in fn(win, *args):
            if gates.target_problem(draft.exercise(lang.name), draft.target, draft.task) is not None:
                continue
            if not gate5 or _worth_it(draft, lang):
                yield draft
    return wrapped


def _noun(node: tree_sitter.Node) -> str:
    """How a task names a delimited node."""
    return _NOUNS.get(node.type, "bracket pair")


def _header(win: Window, node: tree_sitter.Node, orow: int) -> str:
    """First line of the statement that owns a ``{`` table (``local t = {``), not its last line."""
    up = node
    while up.parent is not None and up.parent.type not in _LINE_PARENTS and up.parent.type != "field":
        up = up.parent
    return win.lines[min(up.start_point.row, orow)].strip()


def _quote_char(win: Window) -> str:
    """The quote the window's strings use most (``'`` on a tie)."""
    delims = _delims(win)
    return '"' if delims.get('"', 0) > delims.get("'", 0) else "'"


def _fit(win: Window, node: tree_sitter.Node, old: str) -> str | None:
    """A replacement for an expression that fits its kind (a number for a number, ...), or None."""
    key = (win.key, node.start_point, "fit")
    kind, text = node.type, old.strip()
    if kind == "number":
        return _pick_other(INT_TEXTS, text, *key)
    if kind == "string":
        q = node.children[0].type if node.children and node.children[0].type in _QUOTES else _quote_char(win)
        return q + _pick_other(STRING_TEXTS, text.strip(q), *key) + q
    if kind in ("true", "false"):
        return "false" if kind == "true" else "true"
    if kind == "identifier":
        return templates._new_name(win, text, node, *key)
    if kind in ("binary_expression", "unary_expression"):
        ops = {c.type for c in node.children if not c.is_named}
        logical = bool(ops & {"==", "~=", "<", ">", "<=", ">=", "and", "or", "not"})
        return "false" if logical else "0"
    if kind in ("function_call", "dot_index_expression", "method_index_expression", "bracket_index_expression"):
        return "nil"
    if kind == "table_constructor":
        return "{}"
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str:
    """Replacement contents for a delimited node, fitted to what is inside it now."""
    key = (win.key, node.start_point, "ci")
    items = [a for a in node.named_children if a.type != "comment"]
    if node.type == "bracket_index_expression":
        items = [node.child_by_field_name("field")]
    if node.type in ("arguments", "bracket_index_expression") and len(items) == 1 and items[0] is not None:
        fitted = _fit(win, items[0], inner)
        if fitted is not None and fitted != inner:
            return fitted
    if node.type == "table_constructor" and inner.strip()[:1] in _QUOTES:
        q = inner.strip()[0]
        return q + _pick_other(STRING_TEXTS, inner, *key) + q
    return _pick_other(_TEXTS[node.type], inner, *key)


def _delims(win: Window) -> dict[str, int]:
    _prime(win)
    return win.cache["delims"]


def _comment_rows(root: tree_sitter.Node, lines: list[str]) -> set[int]:
    """Rows that hold nothing but comment text (or a comment and blanks), over a whole file.
    Points are indexed (``start_point[0]``): the attribute getters crash py-tree-sitter
    0.26.0 past 256 lines (see ``js._spans``)."""
    rows: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type != "comment":
            stack.extend(node.children)
            continue
        (r0, c0), (r1, c1) = node.start_point, node.end_point
        if not lines[r0][:c0].strip() and not lines[r1][c1:].strip():
            rows.update(range(r0, r1 + 1))
    return rows


def _long_string_rows(root: tree_sitter.Node) -> set[int]:
    """Rows after the first of every multi-line long string ``[[ ... ]]``: string content."""
    rows: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "string":
            r0, r1 = node.start_point[0], node.end_point[0]
            rows.update(range(r0 + 1, r1 + 1))
            continue
        stack.extend(node.children)
    return rows


def _spans(
    siblings: list[tree_sitter.Node], lines: list[str], wrap: tuple[int, int] | None = None,
) -> list[tuple[int, int, tuple[int, int] | None]]:
    """Group sibling items into ``(start_row, end_row, wrap)`` spans of about SOFT_LINES lines.

    As ``js._spans``: ``wrap`` is ``(header_row, closing_row)`` for the fields of a long
    table (``_body_items``); short spans are merged only within one nesting level; an item
    that starts on the row the previous one ends on joins its group. Points are indexed.
    """
    limit = snippets.MAX_LINES - (2 if wrap else 0)
    out: list[tuple[int, int, tuple[int, int] | None]] = []
    run: list[tuple[int, int]] = []
    group: list[int] | None = None
    prev_end = -1
    for node in siblings:
        start, end = node.start_point[0], node.end_point[0]
        if start <= prev_end:
            if group is not None:
                group[1] = max(group[1], end)
            prev_end = max(prev_end, end)
            continue
        prev_end = end
        if node.type == "comment" and snippets._HEADER.search(lines[start]):
            if group:
                run.append(tuple(group))
            group = None
            continue
        if end - start + 1 > limit:
            if group:
                run.append(tuple(group))
            group = None
            items, inner_wrap = _body_items(node, lines)
            out += [(s, e, wrap) for s, e in _merge_short(run, limit)] + _spans(items, lines, inner_wrap)
            run = []
            continue
        if group and end - group[0] + 1 > limit:
            run.append(tuple(group))
            group = None
        group = [start, end] if group is None else [group[0], end]
        if group[1] - group[0] + 1 >= snippets.SOFT_LINES:
            run.append(tuple(group))
            group = None
    if group:
        run.append(tuple(group))
    return out + [(s, e, wrap) for s, e in _merge_short(run, limit)]


def _body_items(
    node: tree_sitter.Node, lines: list[str], depth: int = 0,
) -> tuple[list[tree_sitter.Node], tuple[int, int] | None]:
    """The items inside a long function, table or loop, and their wrap (see ``_spans``).

    A body's statements parse on their own (wrap None); a table's fields do not, so they
    come with the table's header and closing rows, or with no items when those lines hold
    anything else. The search looks at most four levels down
    (``return function(...) ... end``, ``local t = { ... }``).
    """
    if node.type == "block":
        return node.named_children, None
    body = node.child_by_field_name("body")
    if node.type in _FUNCTIONS and body is not None:
        return body.named_children, None
    if node.type == "table_constructor":
        wrap = _wrap(node, lines)
        return (node.named_children, wrap) if wrap is not None else ([], None)
    if depth >= 4:
        return [], None
    for child in node.named_children:
        items, wrap = _body_items(child, lines, depth + 1) if child.type != "comment" else ([], None)
        if items:
            return items, wrap
    return [], None


def _wrap(table: tree_sitter.Node, lines: list[str]) -> tuple[int, int] | None:
    """(header row, closing row) of a ``{ ... }`` table, or None (see ``_body_items``)."""
    (orow, ocol), (crow, _) = table.start_point, table.end_point
    header, closer = lines[orow], lines[crow]
    if orow == crow or header[ocol + 1:].strip() or not _CLOSER_LINE.fullmatch(closer.strip()):
        return None
    return (orow, crow) if _indent(header) == _indent(closer) else None


def _make_window(
    lines: list[str], start: int, end: int, wrap: tuple[int, int] | None, source: dict[str, str], comments: set[int],
) -> Window | None:
    if start > 0 and start - 1 in comments:
        while start <= end and start in comments:
            start += 1  # the tail of a comment block that began above the window
    while end >= start and (not lines[end].strip() or end in comments):
        end -= 1
    while start <= end and not lines[start].strip():
        start += 1
    if start > end:
        return None
    rows = list(range(start, end + 1))
    if wrap is not None:
        rows = [wrap[0], *rows, wrap[1]]
    chunk = [lines[r] for r in rows]
    indent = min(_indent(ln) for ln in chunk if ln.strip())
    chunk = [ln.rstrip() for ln in textwrap.dedent("\n".join(chunk)).split("\n")]
    if snippets.size_problem(chunk):
        return None
    tree = parse("\n".join(chunk))
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with Lua facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    Lua template to run fills it, so the shared helpers (``_prose_rows``, ``_string_cells``,
    ``_delim_count``, ``_declared_roles``) find Lua answers: strings and comments (long
    ones included) are masked, multi-line ones and comment-only rows are prose, and a
    long bracket ``[[`` is not a delimiter. ``members`` holds the names used as a field,
    a method (``function Set:difference``) or a table key anywhere in the window.
    """
    if win.cache.get("lua"):
        return
    prose: set[int] = set()
    members: set[str] = set()
    cells: set[tuple[int, int]] = set()
    delims: dict[str, int] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        if n.type in _MASKED:
            cells |= _cells(win, n)
            r0, r1 = n.start_point.row, n.end_point.row
            if r1 > r0 or (n.type == "comment" and not win.lines[r0][:n.start_point.column].strip()):
                prose.update(range(r0, r1 + 1))
            q = n.children[0].type if n.type == "string" and n.children else None
            if q in _QUOTES:
                delims[q] = delims.get(q, 0) + 1
            continue
        if n.type in ("(", "[", "{"):
            delims[n.type] = delims.get(n.type, 0) + 1
        elif n.type == "identifier" and _member(n):
            members.add(_text(n))
        stack.extend(n.children)
    win.cache.update({"lua": True, "prose": prose, "strings": cells, "delims": delims, "members": members,
                      "types": _value_roles(win)})


def _value_roles(win: Window) -> dict[str, str]:
    """Name -> role from what a one-name assignment stores (a table is "many", a number "count",
    a string "text", a function "call"). Read by templates._role through the window cache."""
    roles: dict[str, str] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type != "assignment_statement":
            continue
        names = [c for c in n.named_children if c.type == "variable_list"]
        values = [c for c in n.named_children if c.type == "expression_list"]
        if len(names) != 1 or len(values) != 1 or names[0].named_child_count != 1 or values[0].named_child_count != 1:
            continue
        name, value = names[0].named_children[0], values[0].named_children[0]
        if name.type == "identifier" and value.type in _VALUE_ROLES:
            roles.setdefault(_text(name), _VALUE_ROLES[value.type])
    return roles


def _pair(node: tree_sitter.Node) -> tuple[tuple[int, int, str], tuple[int, int, str]] | None:
    """The bracket pair of a node: its first and last child, or the ``[ ]`` of an index."""
    if node.type != "bracket_index_expression":
        return _bracket_pair(node)
    opens, closes = [k for k in node.children if k.type == "["], [k for k in node.children if k.type == "]"]
    if len(opens) != 1 or len(closes) != 1:
        return None
    o, c = opens[0], closes[0]
    return (o.start_point.row, o.start_point.column, "["), (c.start_point.row, c.start_point.column, "]")


def _clean_pair(win: Window, pair) -> bool:
    """True when no string or comment between the pair holds a bracket character."""
    _prime(win)
    (orow, ocol, _), (crow, ccol, _) = pair
    strings = win.cache["strings"]
    for r in range(orow, crow + 1):
        line = win.lines[r]
        for c in range(ocol + 1 if r == orow else 0, ccol if r == crow else len(line)):
            if line[c] in "()[]{}" and (r, c) in strings:
                return False
    return True


def _span(win: Window, node: tree_sitter.Node) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node."""
    kids = node.children
    if node.start_point.row != node.end_point.row or len(kids) < 2:
        return None
    if node.type == "string":
        q = kids[0].type
        if q not in _QUOTES or kids[-1].type != q:
            return None
        call = node.parent.parent if node.parent is not None and node.parent.type == "arguments" else None
        if call is not None and _text(call.child_by_field_name("name")) == "require":
            return None  # a module path is not text to edit
        row, oc, cc = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column
    else:
        pair = _pair(node)
        if pair is None or pair[0][0] != pair[1][0] or not _clean_pair(win, pair):
            return None  # ci( would pair with a bracket inside a string: `('(' .. c)`
        (row, oc, q), (_, cc, _) = pair
    inner = win.lines[row][oc + 1:cc]
    if len(inner.strip()) < 3 or (q in _QUOTES and (q in inner or "\\" in inner)):
        return None
    if _delims(win).get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _nesting(win: Window, node: tree_sitter.Node, row: int, oc: int, inner: str) -> tuple[bool, bool] | None:
    """``templates._which_pair`` with the nesting read from the tree, or None when gate 6 would
    read it differently (gates.py reads lines, not the tree: a long string or comment can hide a bracket)."""
    o = win.lines[row][oc]
    if o in _QUOTES:
        return templates._which_pair(win, row, oc, inner, False)
    up, nested = node.parent, False
    while up is not None and not nested:
        pair = _pair(up)
        nested = pair is not None and pair[0][2] == o
        up = up.parent
    if gates.nested_in_same_pair(win.lines, row, oc, LANG.name) != nested:
        return None
    return templates._which_pair(win, row, oc, inner, nested)


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace, not in a nested pair or a string."""
    line = win.lines[row]
    if o in _QUOTES:
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        strings = win.cache["strings"]
        cols = [c for r, c in _depth0_positions(win, (row, oc), (row, cc), o, _PAIR[o]) if (r, c) not in strings]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _one_line_items(win: Window, parent: tree_sitter.Node) -> set[int]:
    """Rows of the one-line statements of a chunk or block that are alone on their line and
    may move (not ``return`` / ``break``, which must stay last in their block)."""
    return {s.start_point.row for s in parent.named_children
            if s.type != "comment" and s.type not in _LAST_ONLY and s.end_point.row == s.start_point.row
            and win.lines[s.start_point.row].strip() == _text(s).strip()}


def _line_move(win: Window, node: tree_sitter.Node, salt: str) -> tuple[int, int, bool] | None:
    """(row, distance, down) for moving/copying a one-line statement among one-line siblings."""
    parent = node.parent
    row = node.start_point.row
    if parent is None or parent.type not in _LINE_PARENTS or node.end_point.row != row:
        return None
    rows = _one_line_items(win, parent)
    if row not in rows:
        return None
    options = []
    for k in (1, 2, 3):
        if all(row + i in rows for i in range(1, k + 1)):
            options.append((row, k, True))
        if all(row - i in rows for i in range(1, k + 1)):
            options.append((row, k, False))
    options = [o for o in options if win.lines[o[0] + (o[1] if o[2] else -o[1])].strip() != win.lines[row].strip()]
    return pick(options, win.key, node.start_point, salt) if options else None


def _statement_runs(win: Window, node: tree_sitter.Node, min_len: int) -> Iterator[list[tree_sitter.Node]]:
    """Runs of >= min_len one-line items (``_RUN_ITEMS``) on consecutive rows at one indent, each alone on its line."""
    run: list[tree_sitter.Node] = []
    for kid in [*node.named_children, None]:
        item = None
        if (kid is not None and kid.type in _RUN_ITEMS and kid.end_point.row == kid.start_point.row
                and win.lines[kid.start_point.row].strip() == _text(kid).strip()):
            item = kid
        if item is not None and (not run or (item.start_point.row == run[-1].start_point.row + 1
                                             and item.start_point.column == run[0].start_point.column)):
            run.append(item)
            continue
        if len(run) >= min_len:
            yield run
        run = [item] if item is not None else []


def _constant_value(win: Window, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The literal value when ``node`` is the name in a top-level ``local name = <literal>``
    and the window uses that name nowhere else; else None."""
    decl = node.parent.parent.parent if node.parent is not None and node.parent.parent is not None else None
    if decl is None or decl.type != "variable_declaration" or win.indent or decl.parent is None:
        return None
    if decl.parent.type != "chunk" or len(templates._code_names(win)[0].get(_text(node), [])) != 1:
        return None
    assign = node.parent.parent
    names = [c for c in assign.named_children if c.type == "variable_list"]
    values = [c for c in assign.named_children if c.type == "expression_list"]
    if len(names) != 1 or len(values) != 1 or names[0].named_children != [node] or values[0].named_child_count != 1:
        return None
    value = values[0].named_children[0]
    if value.type == "unary_expression" and value.named_child_count == 1:
        value = value.named_children[0]
    return value if value.type in _LITERALS else None


def _const_name(win: Window, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The name of a one-line top-level ``local name = <literal>`` used nowhere else, when it
    sits right before the line's only ``=`` (so ``f=b`` lands on it), else None."""
    line = win.lines[node.start_point.row]
    if node.type != "variable_declaration" or line.count("=") != 1:
        return None
    assign = next((c for c in node.named_children if c.type == "assignment_statement"), None)
    names = next((c for c in assign.named_children if c.type == "variable_list"), None) if assign else None
    name = names.named_children[0] if names is not None and names.named_child_count == 1 else None
    if name is None or name.type != "identifier" or _constant_value(win, name) is None:
        return None
    return name if line[name.end_point.column:].lstrip().startswith("=") else None


def _in_function_body(node: tree_sitter.Node) -> bool:
    """True for a block that is, or sits inside, the body of a function."""
    up = node
    while up is not None:
        if up.type in _FUNCTIONS:
            return True
        up = up.parent
    return False


def _renamable(node: tree_sitter.Node) -> bool:
    """False for a name a rename in place would not touch alone: a field (``t.name``), a
    method (``obj:name``), a table key (``{ name = 1 }``) or a called function's name
    (``name(x)``; its definition, when in the window, carries the rename)."""
    parent = node.parent
    if parent is None:
        return True
    field = {"dot_index_expression": "field", "method_index_expression": "method", "field": "name",
             "function_call": "name"}.get(parent.type)
    return field is None or parent.child_by_field_name(field) != node


def _member(node: tree_sitter.Node) -> bool:
    """True for a field (``t.name``), a method (``obj:name``, ``function Set:name``) or a table
    key (``{ name = 1 }``)."""
    parent = node.parent
    if parent is None:
        return False
    field = {"dot_index_expression": "field", "method_index_expression": "method", "field": "name"}.get(parent.type)
    return field is not None and parent.child_by_field_name(field) == node


_GATE5_FIRST: Final = (change_inner, delete_inner, upper_inner, rename_here, prefix_each_line)
LUA_NODE_TEMPLATES: Final = {f"lua_{fn.__name__}": _shipping(fn, fn in _GATE5_FIRST) for fn in (
    change_inner, delete_inner, delete_block, upper_inner, change_nth_arg, change_rhs, indent_block, move_line,
    copy_line, find_member, jump_match, jump_block_end, delete_trailing_comment, delete_lines, upper_word,
    rename_here, rename_all_subst, prefix_each_line, upper_constants,
)}
LUA_LINE_TEMPLATES: Final = {f"lua_{fn.__name__}": _shipping(fn) for fn in (goto_line_rel, find_char)}
