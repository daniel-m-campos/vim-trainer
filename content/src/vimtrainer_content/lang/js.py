"""JavaScript and TypeScript: tree-sitter node types mapped to skills and templates, plus windowing.

Node type names come from tree-sitter-javascript's node-types.json (grammar 0.25) and
tree-sitter-typescript's (grammar 0.23). TypeScript's node types are a superset of
JavaScript's, so one mapping serves both languages (``LANG_JS``, ``LANG_TS``); the
TypeScript-only nodes (``type_arguments``, ``type_parameters``) never occur in JavaScript.

This module follows lang/cpp.py (read that one first), with the same names in the same
order. The differences:

- ``windows`` re-indents each file from two spaces (exercism's style) to four, the
  oracle's ``shiftwidth``, so ``>>`` shifts by one level of the code. The inside of a
  multi-line template string is left alone (it is string content).
- A class body or object literal longer than a window is cut into windows of whole
  members, each kept between the class (or object) header line and its closing line: a
  method or a ``key: value`` pair does not parse on its own. Such a window's
  ``first_line`` / ``last_line`` are those of its members.
- Strings are quoted with ``'``, ``"`` or backticks; all three drill t.quote.
- Semicolons are optional: ``change_rhs`` keeps whatever ends the line.

``generate`` registers the ``js_*`` templates for the duration of one call, as
``cpp.generate`` does. The grammar-agnostic helpers are shared with cpp.py through
lang/braces.py; the templates mirror cpp.py's rather than sharing them, because cpp's
templates read cpp's module tables (pairs, nouns, texts, spans), and sharing them would
mean rewriting cpp.py around a syntax record.
"""

import contextlib
import functools
import re
import textwrap
from collections.abc import Iterator
from typing import Final

import tree_sitter
import tree_sitter_javascript
import tree_sitter_typescript

from vimtrainer_content import snippets, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, JS/TS column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    "m.match": 1.5, "t.brace": 1.5, "n.unmatched": 1.5, "t.paren": 1.5, "t.bracket": 1.5, "t.quote": 1.5,
    "t.angle": 1.0, "o.indent": 1.0, "m.find": 1.5, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0,
    "m.rel": 1.0, "o.change": 1.0, "o.case": 1.0, "x.copymove": 1.0, "x.normal": 1.0,
}
JS_TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove", "x.normal",
)
TS_TARGET_SKILLS: Final = (*JS_TARGET_SKILLS[:4], "t.angle", *JS_TARGET_SKILLS[4:])  # generics: Array<string>
FOUR: Final = "    "  # the indent unit windows are re-indented to (the oracle's shiftwidth)

STRING_TEXTS: Final = ("not found", "invalid input", "out of range", "unknown", "skipped", "empty", "error: ")
ARG_TEXTS: Final = ("items.length", "key, count", "0", "count + 1", "name")
PARAM_TEXTS: Final = ("count", "name, options", "items", "n = 0")
TS_PARAM_TEXTS: Final = ("count: number", "name: string", "items: string[]", "n = 0")
COND_TEXTS: Final = ("count > 0", "items.length > 0", "i < n", "found", "count === 0")
SUBSCRIPT_TEXTS: Final = ("0", "i + 1", "index", "key", "n - 1")
ARRAY_TEXTS: Final = ("0", "1, 2, 3", "...items")
OBJECT_TEXTS: Final = ("count: 0", "name, count", "...defaults")
ANGLE_TEXTS: Final = ("number", "string", "boolean", "T", "string[]", "number[]")
TPARAM_TEXTS: Final = ("T", "K, V", "T extends object", "T = unknown")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")
# Rename targets by role (see templates.ROLE_NAMES), camelCase like the code; _prime puts
# this list in the window cache.
ROLE_NAMES: Final = {
    "many": ("items", "values"),
    "count": ("count", "total", "size"),
    "index": ("index", "pos"),
    "text": ("name", "label"),
    "flag": ("isValid", "isReady", "hasValue"),
    "call": ("process", "compute", "update"),
    "class": ("record", "item", "handler"),
    "any": ("value", "result"),
}
# TypeScript annotation -> role, first match wins (_type_roles).
_TYPE_ROLES: Final = (
    (re.compile(r"\[\]|\b(Array|ReadonlyArray|Map|Set|Record)\b"), "many"),
    (re.compile(r"\bboolean\b"), "flag"),
    (re.compile(r"\bstring\b"), "text"),
    (re.compile(r"\b(number|bigint)\b"), "count"),
)
_VALUE_ROLES: Final = {
    "array": "many", "number": "count", "string": "text", "template_string": "text", "true": "flag", "false": "flag",
}

_NOUNS: Final = {
    "string": "string", "template_string": "string", "arguments": "argument list",
    "formal_parameters": "parameter list", "parenthesized_expression": "parenthesised expression",
    "subscript_expression": "subscript", "array": "array", "object": "object", "statement_block": "block",
    "class_body": "class body", "type_arguments": "type argument list", "type_parameters": "type parameter list",
}
_TEXTS: Final = {
    "string": STRING_TEXTS, "template_string": STRING_TEXTS, "arguments": ARG_TEXTS, "formal_parameters": PARAM_TEXTS,
    "parenthesized_expression": ARG_TEXTS, "subscript_expression": SUBSCRIPT_TEXTS, "array": ARRAY_TEXTS,
    "object": OBJECT_TEXTS, "type_arguments": ANGLE_TEXTS, "type_parameters": TPARAM_TEXTS,
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", "<": ">", '"': '"', "'": "'", "`": "`"}
_DELIM_NAMES: Final = {
    "(": "parentheses", "[": "square brackets", "{": "braces", "<": "angle brackets", '"': "quotes", "'": "quotes",
    "`": "backticks",
}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), "<": (">",), '"': (), "'": (), "`": ()}
_QUOTES: Final = frozenset({'"', "'", "`"})
_STRINGS: Final = frozenset({"string", "template_string", "regex", "comment"})
_ANGLES: Final = frozenset({"type_arguments", "type_parameters"})
_CONDITIONS: Final = frozenset({"if_statement", "while_statement", "do_statement", "switch_statement"})
_FUNCTIONS: Final = frozenset({
    "function_declaration", "function_expression", "arrow_function", "method_definition",
    "generator_function_declaration", "generator_function",
})
_LINE_PARENTS: Final = frozenset({"program", "statement_block", "class_body", "switch_case", "switch_default"})
# Containers whose items do not parse on their own: a window of them keeps the container's
# header and closing lines (_body_items).
_MEMBER_LISTS: Final = frozenset({"class_body", "object", "interface_body", "object_type", "enum_body"})
_CLOSER_LINE: Final = re.compile(r"\}[)\];,]*")
# x.normal: one-line items a `:norm` range runs over, and the line prefixes a run of them can
# share (longest first). A run with no shared prefix is commented out with `// ` instead.
_RUN_ITEMS: Final = frozenset({
    "lexical_declaration", "variable_declaration", "expression_statement", "public_field_definition",
    "field_definition",
})
_PREFIXES: Final = (
    "private readonly ", "export const ", "readonly ", "private ", "public ", "static ", "export ", "const ",
    "this.", "let ",
)
_SNAKE: Final = re.compile(r"[a-z][a-z0-9_]*[a-z0-9]")
_KEYWORDS: Final = frozenset("""
    async await break case catch class const continue debugger default delete do else export extends false
    finally for from function get if import in instanceof let new null of return set static super switch
    this throw true try typeof undefined var void while with yield
    abstract any as asserts bigint boolean declare enum implements infer interface is keyof namespace never
    number object private protected public readonly string symbol type unknown
    Array Boolean Date Error Infinity JSON Map Math NaN Number Object Promise RegExp Set String Symbol
    console log length push pop shift unshift map filter reduce forEach find some every includes indexOf
    slice splice join split concat keys values entries toString parseInt parseFloat require module exports
    prototype constructor
""".split())

_PAREN = (
    Use("t.paren", ("js_change_inner", "js_delete_inner")),
    Use("m.match", ("js_jump_match",)),
    Use("n.unmatched", ("js_jump_block_end",)),
)
_ANGLE = (Use("t.angle", ("js_change_inner", "js_delete_inner")),)
_IDENT = (
    Use("t.word", ("js_rename_here",)),
    Use("o.case", ("js_upper_word",)),
    Use("x.subst", ("js_rename_all_subst",)),
)
_LINE = (Use("x.copymove", ("js_move_line", "js_copy_line")),)
_DELETE = (Use("o.delete", ("js_delete_lines",)),)
_NORMAL = (Use("x.normal", ("js_prefix_each_line", "js_upper_constants")),)
_ASSIGN = (*_LINE, Use("o.change", ("js_change_rhs",)))

_NODES: Final = {
    "string": (Use("t.quote", ("js_change_inner", "js_delete_inner")), Use("o.case", ("js_upper_inner",))),
    "template_string": (Use("t.quote", ("js_change_inner", "js_delete_inner")),),
    "arguments": (*_PAREN, Use("o.change", ("js_change_nth_arg",))),
    "formal_parameters": _PAREN,
    "parenthesized_expression": _PAREN,  # also the condition of if / while
    "statement_block": (
        Use("t.brace", ("js_change_inner", "js_delete_inner", "js_delete_block")),
        Use("m.match", ("js_jump_match",)),
        Use("n.unmatched", ("js_jump_block_end",)),
        Use("o.indent", ("js_indent_block",)),
        *_NORMAL,
    ),
    "program": _NORMAL,
    "class_body": (
        Use("t.brace", ("js_delete_block",)), Use("m.match", ("js_jump_match",)),
        Use("o.indent", ("js_indent_block",)), *_NORMAL,
    ),
    "object": (
        Use("t.brace", ("js_change_inner", "js_delete_inner", "js_delete_block")),
        Use("m.match", ("js_jump_match",)),
        Use("n.unmatched", ("js_jump_block_end",)),
    ),
    "array": (Use("t.bracket", ("js_change_inner", "js_delete_inner")), Use("m.match", ("js_jump_match",))),
    # subscript_expression's `[...]` is not a node of its own; _span finds the brackets.
    "subscript_expression": (Use("t.bracket", ("js_change_inner", "js_delete_inner")),),
    "type_arguments": _ANGLE,
    "type_parameters": _ANGLE,
    "comment": (Use("o.delete", ("js_delete_trailing_comment",)),),
    "function_declaration": _DELETE,
    "method_definition": _DELETE,
    "if_statement": _DELETE,
    "for_statement": _DELETE,
    "for_in_statement": _DELETE,
    "while_statement": _DELETE,
    "identifier": _IDENT,
    "property_identifier": _IDENT,
    "member_expression": (Use("m.find", ("js_find_member",)),),
    "import_statement": _LINE,
    "public_field_definition": _LINE,
    "field_definition": _LINE,
    "expression_statement": _ASSIGN,
    "lexical_declaration": _ASSIGN,
    "variable_declaration": _ASSIGN,
}
_LINE_TEMPLATES: Final = (Use("m.rel", ("js_goto_line_rel",)), Use("m.find", ("js_find_char",)))
_FIND_TARGETS: Final = ("(", ")", "{", "}", "[", "]", ";", ",", "=", ".", "=>", ":")

LANG_JS = Language(
    name="javascript",
    short="js",
    grammar="javascript",
    nodes=_NODES,
    line_templates=_LINE_TEMPLATES,
    find_targets=_FIND_TARGETS,
    comment_leader="//",
    keywords=_KEYWORDS,
)
LANG_TS = Language(
    name="typescript",
    short="ts",
    grammar="typescript",
    nodes=_NODES,
    line_templates=_LINE_TEMPLATES,
    find_targets=_FIND_TARGETS,
    comment_leader="//",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser(grammar: str = "javascript") -> tree_sitter.Parser:
    """A tree-sitter parser for ``"javascript"`` or ``"typescript"``."""
    language = tree_sitter_typescript.language_typescript() if grammar == "typescript" else tree_sitter_javascript.language()
    return tree_sitter.Parser(tree_sitter.Language(language))


def parse(text: str, grammar: str = "javascript") -> tree_sitter.Tree:
    """Parse JavaScript or TypeScript source text."""
    return parser(grammar).parse(text.encode())


def windows(text: str, source: dict[str, str], grammar: str = "javascript") -> list[Window]:
    """Cut a JS or TS source file into parseable 8-40 line windows (see ``snippets.windows``).

    The file is re-indented to four spaces first (``reindent``). Classes, functions and
    object literals longer than 40 lines are split by recursing into their bodies; a
    window of class members or object entries keeps the header and closing lines around
    them. Comments matching the licence/author pattern break a window and are left out.
    """
    lines = reindent(text.splitlines(), grammar)
    tree = parse("\n".join(lines), grammar)  # keep the tree alive while its nodes are walked
    out = []
    for start, end, wrap in _spans(tree.root_node.named_children, lines):
        win = _make_window(lines, start, end, wrap, source, grammar)
        if win is not None:
            out.append(win)
    return out


def windows_js(text: str, source: dict[str, str]) -> list[Window]:
    """``windows`` with the JavaScript grammar (``build.LANGS["javascript"]``)."""
    return windows(text, source, "javascript")


def windows_ts(text: str, source: dict[str, str]) -> list[Window]:
    """``windows`` with the TypeScript grammar (``build.LANGS["typescript"]``)."""
    return windows(text, source, "typescript")


def reindent(lines: list[str], grammar: str = "javascript") -> list[str]:
    """``lines`` re-indented from two-space to four-space levels.

    Every line's indent ``i`` becomes ``i + 2 * (i // 2)``: code at ``2k`` goes to ``4k``,
    and a block comment's `` * `` line at ``2k + 1`` to ``4k + 1``. Rows inside a
    multi-line template string are string content and stay as they are. A file with no
    line indented ``2 (mod 4)`` is already four-space and comes back unchanged.
    """
    keep: set[int] = set()
    stack = [parse("\n".join(lines), grammar).root_node]
    while stack:
        node = stack.pop()
        if node.type == "template_string":
            (r0, _), (r1, _) = node.start_point, node.end_point
            keep.update(range(r0 + 1, r1 + 1))
            continue
        stack.extend(node.children)
    code = [(r, _indent(ln)) for r, ln in enumerate(lines) if ln.strip() and r not in keep]
    if all(i % 4 != 2 for _, i in code):
        return list(lines)
    return [ln if r in keep or not ln.strip() else " " * (_indent(ln) + 2 * (_indent(ln) // 2)) + ln.lstrip()
            for r, ln in enumerate(lines)]


def generate(win: Window, lang: Language = LANG_JS) -> list[Draft]:
    """``templates.generate`` for a JS or TS window, with the ``js_*`` templates registered.

    The shared registries (``templates.NODE_TEMPLATES`` / ``LINE_TEMPLATES``) only know the
    Python templates, and the ``Use`` entries here name ``js_*`` ones. They are added for
    the duration of the call and removed again, so the Python registry stays as it was.
    """
    with registered():
        return templates.generate(win, lang)


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``js_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(JS_NODE_TEMPLATES, JS_LINE_TEMPLATES)


def node_frequency(texts: list[str], grammar: str = "javascript") -> dict[str, object]:
    """``snippets.node_frequency`` for JS or TS (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, functools.partial(parse, grammar=grammar))


def node_frequency_js(texts: list[str]) -> dict[str, object]:
    """``node_frequency`` with the JavaScript grammar."""
    return node_frequency(texts, "javascript")


def node_frequency_ts(texts: list[str]) -> dict[str, object]:
    """``node_frequency`` with the TypeScript grammar."""
    return node_frequency(texts, "typescript")


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>`` on a single-line string, bracket, brace or angle pair."""
    _prime(win)
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    text = _inner_text(win, node, inner, lang)
    c, noun = _PAIR[o], _noun(node)
    draft = Draft(
        template="change_inner", skill=skill, kind="edit",
        task=f"Change {templates._inside_phrase(noun, _DELIM_NAMES[o], inner, _which_pair(win, node, row, oc, inner))} to `{text}`",
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
    if _worth_it(draft, lang):
        yield draft


def delete_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``di{delim}``: empty a single-line string, bracket, brace or angle pair."""
    _prime(win)
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    c, noun, delims, inner = _PAIR[o], _noun(node), _DELIM_NAMES[o], win.lines[row][oc + 1:cc]
    which = _which_pair(win, node, row, oc, inner)
    draft = Draft(
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
    if _worth_it(draft, lang):
        yield draft


def delete_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``di{``: empty a multi-line ``{ ... }`` body whose braces sit at line end / line start."""
    _prime(win)
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
            {"trigger": "^[0-9]*(dd|j|k)", "text": "di{ empties the block from anywhere inside it, however many lines."},
            {"trigger": "^V", "text": "di{ needs no visual selection; it finds the enclosing braces itself."},
            {"trigger": None, "text": "di{ (or diB): delete inside the {} block around the cursor."},
        ],
    )


def upper_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUi'`` / ``gUi"``: uppercase the text inside a string literal."""
    _prime(win)
    span = _span(win, node)
    if span is None or span[3] not in ('"', "'"):
        return
    row, oc, cc, q = span
    inner = win.lines[row][oc + 1:cc]
    if not (4 <= len(inner) <= 30 and re.fullmatch(r"[a-z][a-z ,.:!?_-]*", inner)):
        return
    col = _cursor_inside(win, node, row, oc, cc, q)
    if col is None:
        return
    draft = Draft(
        template="upper_inner", skill=skill, kind="edit",
        task=f"Uppercase {templates._inside_phrase('string', 'quotes', inner, _which_pair(win, node, row, oc, inner))}",
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
    if _worth_it(draft, lang):
        yield draft


def change_nth_arg(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}f,wct,X<Esc>``: change the n-th argument of a single-line call from the call start."""
    _prime(win)
    call = node.parent
    if call is None or call.type != "call_expression" or node.start_point.row != node.end_point.row:
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
    if not re.fullmatch(r"[\w.+\-*/ '\":]+", value) or a1 >= len(line) or line[a1] not in ",)":
        return
    cursor, d = call.start_point.column, line[a1]
    k = line[cursor:a0].count(",")
    if k < 1:
        return
    text = _fit(win, arg, value)
    if text is None:
        return
    fk = f"{k}f," if k > 1 else "f,"
    kd = line[cursor + 1:a1 + 1].count(d)
    fd = f"{kd}f{d}" if kd > 1 else f"f{d}"
    fn = templates._call_name(_text(call.child_by_field_name("function")))
    where = templates.on_this_line(win.lines, row, f"{fn}(")
    if where is None:
        return
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
    """``C X;<Esc>`` / ``ct;X<Esc>`` (``C X<Esc>`` without a semicolon): replace the value of a
    one-line ``x = ...``, cursor on it."""
    _prime(win)
    if node.start_point.row != node.end_point.row:
        return
    if node.type in ("lexical_declaration", "variable_declaration"):
        decls = [c for c in node.named_children if c.type == "variable_declarator"]
        if len(decls) != 1:
            return
        left, right = decls[0].child_by_field_name("name"), decls[0].child_by_field_name("value")
    else:
        kids = node.named_children
        if len(kids) != 1 or kids[0].type != "assignment_expression":
            return
        left, right = kids[0].child_by_field_name("left"), kids[0].child_by_field_name("right")
    if left is None or right is None or right.type in _FUNCTIONS:
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old, semi = line[r0:r1], line[r1:]
    if semi not in (";", "") or len(old) < 6 or ";" in old or node.parent is None or node.parent.type not in _LINE_PARENTS:
        return
    text = _fit(win, right, old)
    if text is None:
        return
    if semi:
        variants, alternates = [f"C{text};<Esc>", f"ct;{text}<Esc>", f"c${text};<Esc>"], [f"Da{text};<Esc>"]
        hints = [
            {"trigger": "^(D|d\\$|dt;)", "text": "C and ct; delete and enter insert mode in one command."},
            {"trigger": "x{3,}|^c[wWeE]", "text": "ct; changes everything up to the semicolon; C changes to the end of the line."},
            {"trigger": None, "text": "ct; changes up to the `;`; C (= c$) changes to the end of the line, `;` included."},
        ]
    else:
        variants, alternates = [f"C{text}<Esc>", f"c${text}<Esc>"], [f"Da{text}<Esc>"]
        hints = [
            {"trigger": "^(D|d\\$)", "text": "C deletes to the end of the line and enters insert mode in one command."},
            {"trigger": "x{3,}|^c[wWeE]", "text": "C changes everything from the cursor to the end of the line."},
            {"trigger": None, "text": "C (= c$) changes from the cursor to the end of the line."},
        ]
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to {templates._quote(_text(left), 32)} with `{text}`",
        lines=win.lines, cursor=[row + 1, r0], expect={"lines": _replace(win.lines, row, r0, r1, text)},
        variants=variants, alternates=alternates,
        idioms=[f"cW{text}<Esc>", f"cw{text}<Esc>", f"ce{text}<Esc>"],
        typed=len(text), params={"text": text},
        target=[_range(row, r0, row, r1 - 1)], window=win, tags=["assignment", "change"], hints=hints,
    )


def indent_block(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``>i{`` / ``{N}>>`` (or ``<``): fix a brace body that is one level under- or over-indented."""
    _prime(win)
    pair = _bracket_pair(node)
    if pair is None or pair[0][2] != "{":
        return
    (orow, ocol, _), (crow, ccol, _) = pair
    lines = win.lines
    start, end = orow + 1, crow - 1
    n = end - start + 1
    if not 2 <= n <= 12 or lines[orow][ocol + 1:].strip() or lines[crow][:ccol].strip():
        return
    if any(not lines[r].strip() for r in range(start, end + 1)):
        return  # the highlight skips blank lines, so "these N lines" would not match N>> (QA #26)
    rows = range(start, end + 1)
    base = _indent(lines[crow])
    body = [lines[r] for r in rows if lines[r].strip()]
    if min(_indent(ln) for ln in body) != base + len(FOUR):
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    shifted = [(ln[4:] if under else FOUR + ln) if r in rows and ln.strip() else ln for r, ln in enumerate(lines)]
    op = ">>" if under else "<<"
    o = op[0]
    yield Draft(
        template="indent_block", skill=skill, kind="edit", task=templates.indent_task(_header(win, node, orow), under, n),
        lines=shifted, cursor=[start + 1, _indent(shifted[start])], expect={"lines": lines},
        variants=[f"{o}i{{", f"{o}iB", f"{n}{op}", f"{o}{n - 1}j"],
        alternates=[f"{o}i}}", f"V{n - 1}j{o}"], idioms=[f"{o}ip", f"{o}ap", f"{o}}}", f"{o}G"],
        target=[_range(start, 0, end, max(len(shifted[end]) - 1, 0))], window=win, tags=["block", "indent"],
        hints=[
            {"trigger": f"({op}j)|({op}\\.)|(j\\.)", "text": f"{o}i{{ shifts the whole block body in one command."},
            {"trigger": "^[0-9]*I|^\\^?i", "text": f"{op} shifts by shiftwidth; there is no need to type spaces."},
            {"trigger": None, "text": f"{o}i{{ shifts every line inside the braces; {n}{op} works too."},
        ],
    )


def move_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``:m+k<CR>`` / ``:m-k<CR>`` or ``ddp``: move a one-line statement among its one-line siblings."""
    _prime(win)
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
    _prime(win)
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
        variants, task = [f":t+{k}<CR>", f":t{row + k + 1}<CR>", "yyjp" if k == 1 else f"yy{k}jp"], f"Copy this line to just below {templates._quote(lines[other].strip())}"
    else:
        variants, task = [f":t-{k + 1}<CR>", f":t{row - k}<CR>", "yykP" if k == 1 else f"yy{k}kP"], f"Copy this line to just above {templates._quote(lines[other].strip())}"
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
    """``{k}f.``: from the first non-blank, jump to the ``.`` before a property."""
    _prime(win)
    op = next((c for c in node.children if c.type == "."), None)
    prop = node.child_by_field_name("property")
    if op is None or prop is None or op.start_point.row != prop.end_point.row:
        return
    row, col = op.start_point.row, op.start_point.column
    line = win.lines[row]
    start = _indent(line)
    if row in win.cache["prose"] or line[start:start + 1] in ("", "/", "*"):
        return
    name = _text(prop)
    k = line.count(".", start + 1, col + 1)
    if not 1 <= k <= 3 or col - start < 3 * (2 if k == 1 else 3) + 1 or line.count(f".{name}") != 1:
        return
    motion = f"{k}f." if k > 1 else "f."
    yield Draft(
        template="find_char", skill=skill, kind="cursor", task=f"Move to the `.` before `{name}`",
        lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
        variants=[motion], alternates=["f." + ";" * (k - 1)] if k > 1 else [],
        idioms=list(templates.CURSOR_IDIOMS), params={"char": ".", "n": k},
        target=[_range(row, col, row, col)], window=win, tags=["find", "member"],
        hints=[
            {"trigger": "l{4,}|w{3,}|e{3,}", "text": "f. jumps to the next `.` on the line" + (f"; {motion} to the {templates.ordinal(k)}." if k > 1 else ".")},
            *([{"trigger": "^f\\.;", "text": f"A count before f replaces the ; presses: {motion}."}] if k > 1 else []),
            {"trigger": None, "text": f"{motion}: find the {templates.ordinal(k)} `.` to the right."},
        ],
    )


def jump_match(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_match`` (grammar-agnostic) on a primed window."""
    _prime(win)
    yield from templates.jump_match(win, node, skill, lang)


def jump_block_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_block_end`` with JS strings and comments excluded as start positions."""
    _prime(win)
    for draft in templates.jump_block_end(win, node, skill, lang):
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_noun(node)} around the cursor", draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f/D``: ``templates.delete_trailing_comment`` for single-line ``//`` and ``/* */`` comments.

    Comments after a bare ``}`` or ``});`` are skipped: retyping the code is cheaper.
    """
    _prime(win)
    row = node.start_point.row
    if row != node.end_point.row or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    if win.lines[row][node.end_point.column:].strip():
        return  # a mid-line `/* */` with code after it is not a trailing comment
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` with JS task text (``export`` included, methods named)."""
    _prime(win)
    target = node.parent if node.parent is not None and node.parent.type == "export_statement" else node
    what = {
        "if_statement": "this `if` statement", "for_statement": "this `for` loop",
        "for_in_statement": "this `for` loop", "while_statement": "this `while` loop",
    }.get(node.type, "this statement")
    if node.type in ("function_declaration", "method_definition"):
        kind = "function" if node.type == "function_declaration" else "method"
        name = _text(node.child_by_field_name("name"))
        what = f"the {kind} `{name}`" if name and len(name) <= 40 else f"this {kind}"
    for draft in templates.delete_lines(win, target, skill, lang):
        n = target.end_point.row - target.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def upper_word(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.upper_word`` on a primed window (constants: top-level ``const`` literals)."""
    _prime(win)
    yield from templates.upper_word(win, node, skill, lang)


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here`` on a primed window (``this.x`` members are skipped there)."""
    _prime(win)
    yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst`` on a primed window."""
    _prime(win)
    yield from templates.rename_all_subst(win, node, skill, lang)


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm I{prefix}<CR>`` over 3-8 consecutive one-line declarations or statements
    (x.normal): put back a prefix they all share (``const ``, ``this.``, ``private ``), or, when
    they share none and they are statements in a function body, comment them out with ``// ``
    (never class members or top-level declarations)."""
    _prime(win)
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
            continue  # commenting out class members or top-level declarations is not an edit anyone drills
        else:
            prefix, start = "// ", win.lines
            expect = [ln[:col] + prefix + ln[col:] if r in rows else ln for r, ln in enumerate(win.lines)]
            tags = ["comment", "normal", "insert"]
            task = f"Comment out these {n} lines: put `// ` at the start of each"
            target = [_range(r, col, r, len(start[r]) - 1) for r in rows]
        draft = templates.normal_prefix(win, skill, rows, prefix, start, expect, task, target, tags)
        if _worth_it(draft, lang):
            yield draft


def upper_constants(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm f=bgUiw<CR>`` over consecutive top-level ``const name = literal`` lines:
    uppercase 3+ lower_snake names (x.normal)."""
    _prime(win)
    if node.type != "program" or win.indent:
        return  # a dedented function body parses as a program too
    runs = [([d.start_point.row for d in run], [_const_name(win, d) for d in run])
            for run in _statement_runs(win, node, templates.EX_MIN_LINES)]
    for rows, names in runs:
        if len(rows) < templates.EX_MIN_LINES or not all(n is not None and _SNAKE.fullmatch(_text(n)) for n in names):
            continue  # ex kind: gUiwj.j. on fewer lines would be the better drill
        rows, names = rows[:8], names[:8]
        if templates._seen(win, "constants", rows[0]):
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
    """``templates.goto_line_rel`` with JS comment-only lines excluded as start and target."""
    _prime(win)
    yield from templates.goto_line_rel(win, skill, lang)


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: jump to the n-th X (``=>`` included: ``f=``) on the line."""
    _prime(win)
    rows = sorted(range(len(win.lines)), key=lambda r: snippets.stable_hash(win.key, r, "find"))
    prose = win.cache["prose"]
    made = 0
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("", '"', "'", "`", "/", "*"):
            continue
        options = []
        for tok in lang.find_targets:
            cols = _occurrences(line, tok, start + 1)
            for n, col in enumerate(cols[:3], 1):
                k = line.count(tok[0], start + 1, col + 1)  # f counts the first char of the token
                if k == n and col - start >= 3 * (2 if n == 1 else 3) + 1:
                    options.append((tok, n, col))
        if not options:
            continue
        tok, n, col = pick(options, win.key, row, "opt")
        ch = tok[0]
        motion = f"{n}f{ch}" if n > 1 else f"f{ch}"
        yield Draft(
            template="find_char", skill=skill, kind="cursor",
            task=f"Move to the {templates.ordinal(n)} `{tok}` on this line",
            lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
            variants=[motion], alternates=[f"f{ch}" + ";" * (n - 1)] if n > 1 else [],
            idioms=list(templates.CURSOR_IDIOMS), params={"char": ch, "n": n},
            target=[_range(row, col, row, col + len(tok) - 1)], window=win, tags=["find", "punctuation"],
            hints=[
                {"trigger": "l{4,}|w{3,}|e{3,}", "text": f"f{ch} jumps to the next `{ch}` on the line" + (f"; {motion} to the {templates.ordinal(n)}." if n > 1 else ".")},
                *([{"trigger": f"^f{_js_escape(ch)};", "text": f"A count before f replaces the ; presses: {motion}."}] if n > 1 else []),
                {"trigger": None, "text": f"{motion}: find the {templates.ordinal(n)} `{ch}` to the right."},
            ],
        )
        made += 1
        if made >= templates.MAX_PER_WINDOW + 1:
            return


JS_NODE_TEMPLATES: Final = {
    "js_change_inner": change_inner, "js_delete_inner": delete_inner, "js_delete_block": delete_block,
    "js_upper_inner": upper_inner, "js_change_nth_arg": change_nth_arg, "js_change_rhs": change_rhs,
    "js_indent_block": indent_block, "js_move_line": move_line, "js_copy_line": copy_line,
    "js_find_member": find_member, "js_jump_match": jump_match, "js_jump_block_end": jump_block_end,
    "js_delete_trailing_comment": delete_trailing_comment, "js_delete_lines": delete_lines,
    "js_upper_word": upper_word, "js_rename_here": rename_here, "js_rename_all_subst": rename_all_subst,
    "js_prefix_each_line": prefix_each_line, "js_upper_constants": upper_constants,
}
JS_LINE_TEMPLATES: Final = {"js_goto_line_rel": goto_line_rel, "js_find_char": find_char}


# Private Functions ================================================================================


# Shared with the other brace language (see lang/braces.py).
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


def _noun(node: tree_sitter.Node) -> str:
    """How a task names a delimited node: an if / while condition is a "condition"."""
    if node.type == "parenthesized_expression" and node.parent is not None and node.parent.type in _CONDITIONS:
        return "condition"
    return _NOUNS.get(node.type, "bracket pair")


def _header(win: Window, node: tree_sitter.Node, orow: int) -> str:
    """First line of the statement that owns a ``{`` block (the signature, not its last line)."""
    parent = node.parent
    row = parent.start_point.row if parent is not None and parent.type != "program" else orow
    return win.lines[min(row, orow)].strip()


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
    if kind in ("string", "template_string"):
        q = node.children[0].type if kind == "string" and node.children else _quote_char(win)
        return q + _pick_other(STRING_TEXTS, text.strip(q + "`"), *key) + q
    if kind in ("true", "false"):
        return "false" if kind == "true" else "true"
    if kind == "identifier":
        return templates._new_name(win, text, node, *key)
    if kind in ("binary_expression", "unary_expression"):
        op = node.child_by_field_name("operator")
        logical = op is not None and op.type in ("===", "!==", "==", "!=", "<", ">", "<=", ">=", "&&", "||", "!")
        return "false" if logical else "0"
    if kind in ("call_expression", "member_expression", "ternary_expression", "subscript_expression",
                "new_expression", "await_expression"):
        return "null"
    if kind == "array":
        return "[]"
    if kind == "object":
        return "{}"
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str, lang: Language) -> str:
    """Replacement contents for a delimited node, fitted to what is inside it now."""
    key = (win.key, node.start_point, "ci")
    items = [a for a in node.named_children if a.type != "comment"]
    if node.type == "subscript_expression":
        items = [node.child_by_field_name("index")]
    if node.type in ("arguments", "subscript_expression") and len(items) == 1 and items[0] is not None:
        fitted = _fit(win, items[0], inner)
        if fitted is not None:
            return fitted
    if node.type == "array" and inner[:1] in ('"', "'"):
        q = inner[0]
        return q + _pick_other(STRING_TEXTS, inner, *key) + q
    if node.type == "statement_block":
        semi = ";" if any(ln.rstrip().endswith(";") for ln in win.lines) else ""
        return ("return null" if inner.strip().startswith("return") else "count += 1") + semi
    if node.type == "parenthesized_expression" and _noun(node) == "condition":
        return _pick_other(COND_TEXTS, inner, *key)
    if node.type == "formal_parameters" and lang.name == "typescript":
        return _pick_other(TS_PARAM_TEXTS, inner, *key)
    return _pick_other(_TEXTS[node.type], inner, *key)


def _delims(win: Window) -> dict[str, int]:
    _prime(win)
    return win.cache["delims"]


def _spans(
    siblings: list[tree_sitter.Node], lines: list[str], wrap: tuple[int, int] | None = None,
) -> list[tuple[int, int, tuple[int, int] | None]]:
    """Group sibling items into ``(start_row, end_row, wrap)`` spans of about SOFT_LINES lines.

    ``wrap`` is ``(header_row, closing_row)`` for the members of a long class or object
    (see ``_body_items``); those two lines go into the window too, so the limit is two lines
    lower. Short spans are merged only with spans of the same nesting level: a merge across
    a recursed-into body would swallow its closing ``}`` and leave the window unparseable.
    An item that starts on a row the previous item ends on joins that item's group, or is
    dropped when that item was split. Points are indexed (``start_point[0]``), as in
    ``cpp._end_row``: the attribute getters crash py-tree-sitter 0.26.0 past 256 lines.
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
    """The items inside a long class / function / object, and their wrap (see ``_spans``).

    A function body's statements parse on their own (wrap None); a class body's members and
    an object's entries do not, so they come with the container's header and closing rows,
    or with no items when those lines hold anything else (the header must be one line
    ending in ``{``, the closing line only ``}`` and punctuation). The fallback looks at most
    three levels down (``export const x = () => {...}``).
    """
    if node.type == "export_statement":
        decl = node.child_by_field_name("declaration") or node.child_by_field_name("value")
        return _body_items(decl, lines, depth) if decl is not None else ([], None)
    body = node if node.type in _MEMBER_LISTS or node.type == "statement_block" else node.child_by_field_name("body")
    if body is not None and body.type == "statement_block":
        return body.named_children, None
    if body is not None and body.type in _MEMBER_LISTS:
        wrap = _wrap(body, lines)
        return (body.named_children, wrap) if wrap is not None else ([], None)
    if depth >= 3:
        return [], None
    for child in node.named_children:
        items, wrap = _body_items(child, lines, depth + 1) if child.type != "comment" else ([], None)
        if items:
            return items, wrap
    return [], None


def _wrap(body: tree_sitter.Node, lines: list[str]) -> tuple[int, int] | None:
    """(header row, closing row) of a ``{ ... }`` member list, or None (see ``_body_items``)."""
    (orow, ocol), (crow, _) = body.start_point, body.end_point
    header, closer = lines[orow], lines[crow]
    if orow == crow or header[ocol + 1:].strip() or not _CLOSER_LINE.fullmatch(closer.strip()):
        return None
    return (orow, crow) if _indent(header) == _indent(closer) and closer.strip()[0] == "}" else None


def _make_window(
    lines: list[str], start: int, end: int, wrap: tuple[int, int] | None, source: dict[str, str], grammar: str,
) -> Window | None:
    start, end = snippets.trim_comment_edges(lines, start, end)
    while start <= end and not lines[start].strip():
        start += 1
    while end >= start and not lines[end].strip():
        end -= 1
    if start > end:
        return None
    rows = list(range(start, end + 1))
    if wrap is not None:
        rows = [wrap[0], *rows, wrap[1]]
    chunk = [lines[r] for r in rows]
    indent = min(len(ln) - len(ln.lstrip()) for ln in chunk if ln.strip())
    chunk = [ln.rstrip() for ln in textwrap.dedent("\n".join(chunk)).split("\n")]
    if snippets.size_problem(chunk):
        return None
    tree = parse("\n".join(chunk), grammar)
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with JS facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    JS template to run fills it, so later shared helpers (``_prose_rows``,
    ``_string_cells``, ``_delim_count``) find JS answers instead of Python ones.
    """
    if win.cache.get("js"):
        return
    prose: set[int] = set()
    cells: set[tuple[int, int]] = set()
    delims: dict[str, int] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        if n.type in _STRINGS:
            cells |= _cells(win, n)
            r0, r1 = n.start_point.row, n.end_point.row
            if r1 > r0:
                prose.update(range(r0, r1 + 1))
            if n.type == "comment" and not win.lines[r0][:n.start_point.column].strip():
                prose.update(range(r0, r1 + 1))
            q = _quote_of(n)
            if q is not None:
                delims[q] = delims.get(q, 0) + 1
            continue
        if n.type in ("(", "[", "{"):
            delims[n.type] = delims.get(n.type, 0) + 1
        elif n.type in _ANGLES:
            delims["<"] = delims.get("<", 0) + 1
        stack.extend(n.children)
    win.cache.update({"js": True, "prose": prose, "strings": cells, "delims": delims, "role_names": ROLE_NAMES,
                      "types": _type_roles(win)})


def _quote_of(node: tree_sitter.Node) -> str | None:
    """The quote character of a string or template string node, else None."""
    if node.type == "template_string":
        return "`"
    if node.type == "string" and node.children and node.children[0].type in ('"', "'"):
        return node.children[0].type
    return None


def _type_roles(win: Window) -> dict[str, str]:
    """Name -> role from declarations, parameters and class fields: a TypeScript annotation
    first (``string[]`` is "many", ``boolean`` "flag", ...), else the initial value (an array
    is "many", a number "count", a string "text"). Read by templates._role through the window cache."""
    roles: dict[str, str] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type == "variable_declarator":
            name = n.child_by_field_name("name")
        elif n.type in ("required_parameter", "optional_parameter"):
            name = n.child_by_field_name("pattern")
        elif n.type in ("public_field_definition", "field_definition"):
            name = n.child_by_field_name("name") or n.child_by_field_name("property")
        else:
            continue
        if name is None or name.type not in ("identifier", "property_identifier"):
            continue
        annotation, value = _text(n.child_by_field_name("type")), n.child_by_field_name("value")
        role = next((r for rx, r in _TYPE_ROLES if rx.search(annotation)), None) if annotation else None
        if role is None and value is not None:
            role = _VALUE_ROLES.get(value.type)
            if value.type == "new_expression" and _text(value.child_by_field_name("constructor")) in ("Map", "Set", "Array"):
                role = "many"
        if role is not None:
            roles.setdefault(_text(name), role)
    return roles


def _span(win: Window, node: tree_sitter.Node) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node."""
    kids = node.children
    if node.start_point.row != node.end_point.row or len(kids) < 2:
        return None
    if node.type in ("string", "template_string"):
        q = _quote_of(node)
        if q is None or kids[0].type != kids[-1].type or any(k.type == "escape_sequence" for k in kids):
            return None
        if node.parent is not None and node.parent.type in ("import_statement", "export_statement"):
            return None  # a module path is not text to edit
        row, oc, cc = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column
    elif node.type in _ANGLES:
        if kids[0].type != "<" or kids[-1].type != ">":
            return None
        row, oc, cc, q = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column, "<"
    elif node.type == "subscript_expression":
        opens, closes = [k for k in kids if k.type == "["], [k for k in kids if k.type == "]"]
        if len(opens) != 1 or len(closes) != 1:
            return None
        row, oc, cc, q = node.start_point.row, opens[0].start_point.column, closes[0].start_point.column, "["
    else:
        pair = _bracket_pair(node)
        if pair is None or pair[0][0] != pair[1][0]:
            return None
        (row, oc, q), (_, cc, _) = pair
    inner = win.lines[row][oc + 1:cc]
    if len(inner.strip()) < 3 or (q in _QUOTES and (q in inner or "\\" in inner)):
        return None
    if _delims(win).get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace, not in a nested pair or a string."""
    line = win.lines[row]
    if o in _QUOTES:
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        strings = win.cache["strings"]
        cols = [c for r, c in _depth0_positions(win, (row, oc), (row, cc), o, _PAIR[o])
                if (r, c) not in strings and line[c] not in "<>"]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _line_move(win: Window, node: tree_sitter.Node, salt: str) -> tuple[int, int, bool] | None:
    """(row, distance, down) for moving/copying a one-line item among one-line siblings."""
    parent = node.parent
    row = node.start_point.row
    if parent is None or parent.type not in _LINE_PARENTS or node.end_point.row != row:
        return None
    if win.lines[row].strip() != _text(node).strip():
        return None  # the line holds more than this statement (a trailing comment, a second statement)
    rows = {s.start_point.row for s in parent.named_children
            if s.type != "comment" and s.end_point.row == s.start_point.row
            and win.lines[s.start_point.row].strip() == _text(s).strip()}
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


def _const_name(win: Window, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The name of a one-line ``const name = <literal>``, when it sits right before the line's
    only ``=`` (so ``f=b`` lands on it), else None."""
    line = win.lines[node.start_point.row]
    if node.type != "lexical_declaration" or line.count("=") != 1 or not node.children or node.children[0].type != "const":
        return None
    decls = [c for c in node.named_children if c.type == "variable_declarator"]
    name = decls[0].child_by_field_name("name") if len(decls) == 1 else None
    value = decls[0].child_by_field_name("value") if len(decls) == 1 else None
    if name is None or name.type != "identifier" or value is None or value.type not in ("number", "string", "true", "false"):
        return None
    return name if line[name.end_point.column:].lstrip().startswith("=") else None


def _in_function_body(node: tree_sitter.Node) -> bool:
    """True for a ``{}`` block that is, or sits inside, the body of a function, method or arrow."""
    up = node
    while up is not None and up.type not in ("program", "class_body"):
        if up.type == "statement_block" and up.parent is not None and up.parent.type in _FUNCTIONS:
            return True
        up = up.parent
    return False


def _which_pair(win: Window, node: tree_sitter.Node, row: int, oc: int, inner: str) -> tuple[bool, bool]:
    """``templates._which_pair`` with angle brackets nested by the tree (``Map<string, Array<number>>``):
    a text-only count would read every less-than as an opening angle."""
    nested = None
    if node.type in _ANGLES:
        up = node.parent
        while up is not None and up.type not in _ANGLES:
            up = up.parent
        nested = up is not None
    return templates._which_pair(win, row, oc, inner, nested)
