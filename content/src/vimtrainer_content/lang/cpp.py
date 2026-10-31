"""C++: tree-sitter-cpp node types mapped to skills and templates, plus C++ windowing.

Node type names come from tree-sitter-cpp's node-types.json (grammar 0.23).

The shared pipeline (``snippets.windows``, ``templates``) was written for Python, so this
module carries what C++ needs on top of it:

- ``parse`` / ``windows``: the C++ counterparts of ``snippets.parse`` / ``snippets.windows``.
  Windows recurse into namespace, class and function bodies and into header guards.
- C++ node templates under ``cpp_*`` names. ``generate`` registers them in
  ``templates.NODE_TEMPLATES`` / ``LINE_TEMPLATES`` for the duration of one call (the
  shared registry has no per-language hook), so use ``cpp.generate`` for C++ windows.
  Templates whose logic already works on any grammar
  (``jump_match``, ``rename_here``, ...) are reused through thin wrappers that first prime
  the window cache with C++ facts (comment-only rows, string cells, delimiter counts),
  which the shared helpers read instead of looking for Python ``string`` / ``#`` nodes.
  Templates that assume Python syntax (string_start/string_end children, ``call`` nodes,
  indentation-only blocks, ``block``/``module`` parents) have C++ versions here; the
  drafts they emit keep the shared template names (``change_inner``, ``move_line``, ...).
- Grammar-agnostic helpers shared with lang/js.py live in lang/braces.py.
"""

from __future__ import annotations

import contextlib
import functools
import re
import textwrap
from collections.abc import Iterator
from typing import Final

import tree_sitter
import tree_sitter_cpp

from vimtrainer_content import snippets, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, C/C++ column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    "m.match": 1.5, "t.brace": 1.5, "n.unmatched": 1.5, "t.paren": 1.5, "t.bracket": 1.2, "t.quote": 1.0,
    "t.angle": 1.5, "o.indent": 1.0, "m.find": 1.5, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0,
    "m.rel": 1.0, "o.change": 1.0, "o.case": 1.0, "x.copymove": 1.0, "x.normal": 1.0,
}
TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.angle", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove", "x.normal",
)

STRING_TEXTS: Final = ("not found", "invalid input", "out of range", "unknown", "skipped", "empty", "error: ")
ARG_TEXTS: Final = ("items.size()", "key, count", "0", "count + 1", "std::move(name)")
PARAM_TEXTS: Final = ("int count", "const std::string& name", "std::size_t n", "char c")
COND_TEXTS: Final = ("count > 0", "!items.empty()", "i < n", "found", "count == 0")
SUBSCRIPT_TEXTS: Final = ("0", "i + 1", "index", "key", "n - 1")
ANGLE_TEXTS: Final = ("int", "std::string", "double", "char", "std::size_t", "bool", "long long", "T")
TPARAM_TEXTS: Final = ("typename T", "class T", "typename K, typename V", "int N")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")
# Rename targets by role (see templates.ROLE_NAMES); _prime puts this list in the window cache.
ROLE_NAMES: Final = {
    "many": ("items", "values"),
    "count": ("count", "total", "size"),
    "index": ("index", "pos"),
    "text": ("name", "label"),
    "ptr": ("ptr", "node"),
    "buffer": ("buffer", "buf"),
    "flag": ("is_valid", "is_ready", "has_value"),
    "call": ("process", "compute", "update"),
    "class": ("record", "item", "handler"),
    "any": ("value", "result"),
}
# Declared type -> role, first match wins (_type_roles).
_TYPE_ROLES: Final = (
    (re.compile(r"\b(vector|list|map|set|array|deque|unordered_\w+|multiset|multimap)\b"), "many"),
    (re.compile(r"\bbool\b"), "flag"),
    (re.compile(r"\b(string|string_view)\b"), "text"),
    (re.compile(r"\b(size_t|int|long|short|unsigned|u?int\d+_t)\b"), "count"),
)

_NOUNS: Final = {
    "string_literal": "string", "argument_list": "argument list", "parameter_list": "parameter list",
    "condition_clause": "condition", "parenthesized_expression": "parenthesised expression",
    "subscript_argument_list": "subscript", "initializer_list": "initializer list",
    "compound_statement": "block", "template_argument_list": "template argument list",
    "template_parameter_list": "template parameter list", "lambda_capture_specifier": "lambda capture list",
    "field_declaration_list": "class body",
}
_TEXTS: Final = {
    "string_literal": STRING_TEXTS, "argument_list": ARG_TEXTS, "parameter_list": PARAM_TEXTS,
    "condition_clause": COND_TEXTS, "parenthesized_expression": ARG_TEXTS, "subscript_argument_list": SUBSCRIPT_TEXTS,
    "template_argument_list": ANGLE_TEXTS,
    "template_parameter_list": TPARAM_TEXTS, "lambda_capture_specifier": ("&", "this", "=", "&total"),
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", "<": ">", '"': '"'}
_DELIM_NAMES: Final = {"(": "parentheses", "[": "square brackets", "{": "braces", "<": "angle brackets", '"': "quotes"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), "<": (">",), '"': ()}
_STRINGS: Final = frozenset({"string_literal", "raw_string_literal", "char_literal", "system_lib_string", "comment"})
_ANGLES: Final = frozenset({"template_argument_list", "template_parameter_list"})
_LINE_PARENTS: Final = frozenset({
    "translation_unit", "compound_statement", "declaration_list", "field_declaration_list",
    "preproc_ifdef", "preproc_if", "preproc_else",
})
# x.normal: one-line items a `:norm` range runs over, and the line prefixes a run of them can
# share (longest first). A run with no shared prefix is commented out with `// ` instead.
# No `std::`: typing `std:` at the start of a line in a C++ buffer re-indents it as a label
# (cinkeys), so `:norm Istd::` does not produce the source line.
_RUN_ITEMS: Final = frozenset({
    "declaration", "field_declaration", "expression_statement", "using_declaration", "alias_declaration",
})
_PREFIXES: Final = ("static constexpr ", "constexpr ", "static const ", "const ", "static ", "this->")
_SNAKE: Final = re.compile(r"[a-z][a-z0-9_]*[a-z0-9]")
_KEYWORDS: Final = frozenset("""
    alignas alignof and and_eq asm auto bitand bitor bool break case catch char char8_t char16_t char32_t
    class compl concept const consteval constexpr constinit const_cast continue co_await co_return co_yield
    decltype default delete do double dynamic_cast else enum explicit export extern false final float for
    friend goto if inline int long mutable namespace new noexcept not not_eq nullptr operator or or_eq
    override private protected public register reinterpret_cast requires return short signed sizeof static
    static_assert static_cast struct switch template this thread_local throw true try typedef typeid typename
    union unsigned using virtual void volatile wchar_t while xor xor_eq
    std string vector map set size_t cout cin cerr endl main npos first second begin end size empty
    push_back emplace_back insert erase find count length substr front back move swap sort min max abs
""".split())

_PAREN = (
    Use("t.paren", ("cpp_change_inner", "cpp_delete_inner")),
    Use("m.match", ("cpp_jump_match",)),
    Use("n.unmatched", ("cpp_jump_block_end",)),
)
_ANGLE = (Use("t.angle", ("cpp_change_inner", "cpp_delete_inner")),)
_IDENT = (
    Use("t.word", ("cpp_rename_here",)),
    Use("o.case", ("cpp_upper_word",)),
    Use("x.subst", ("cpp_rename_all_subst",)),
)
_LINE = (Use("x.copymove", ("cpp_move_line", "cpp_copy_line")),)
_DELETE = (Use("o.delete", ("cpp_delete_lines",)),)
_NORMAL = (Use("x.normal", ("cpp_prefix_each_line", "cpp_upper_constants")),)

LANG = Language(
    name="cpp",
    short="cpp",
    grammar="cpp",
    nodes={
        "string_literal": (Use("t.quote", ("cpp_change_inner", "cpp_delete_inner")), Use("o.case", ("cpp_upper_inner",))),
        # raw_string_literal: R"(...)" has no `"`-delimited inner text that ci" can target cleanly;
        # mapped for completeness, _span() skips it.
        "raw_string_literal": (Use("t.quote", ("cpp_change_inner", "cpp_delete_inner")),),
        "argument_list": (*_PAREN, Use("o.change", ("cpp_change_nth_arg",))),
        "parameter_list": _PAREN,
        "condition_clause": _PAREN,
        "parenthesized_expression": _PAREN,
        "compound_statement": (
            Use("t.brace", ("cpp_change_inner", "cpp_delete_inner", "cpp_delete_block")),
            Use("m.match", ("cpp_jump_match",)),
            Use("n.unmatched", ("cpp_jump_block_end",)),
            Use("o.indent", ("cpp_indent_block",)),
            *_NORMAL,
        ),
        "translation_unit": _NORMAL,
        "declaration_list": _NORMAL,
        "enumerator_list": (Use("x.normal", ("cpp_upper_constants",)),),
        # `{1, 2, 3}` is a brace pair, so it drills t.brace (not t.bracket).
        "initializer_list": (
            Use("t.brace", ("cpp_change_inner", "cpp_delete_inner", "cpp_delete_block")),
            Use("m.match", ("cpp_jump_match",)),
            Use("n.unmatched", ("cpp_jump_block_end",)),
        ),
        "field_declaration_list": (
            Use("t.brace", ("cpp_delete_block",)), Use("m.match", ("cpp_jump_match",)),
            Use("o.indent", ("cpp_indent_block",)), *_NORMAL,
        ),
        "template_argument_list": _ANGLE,
        "template_parameter_list": _ANGLE,
        # subscript_expression's `[...]` is its subscript_argument_list child in grammar 0.23.
        "subscript_argument_list": (
            Use("t.bracket", ("cpp_change_inner", "cpp_delete_inner")), Use("m.match", ("cpp_jump_match",)),
        ),
        "lambda_capture_specifier": (Use("t.bracket", ("cpp_change_inner",)),),
        "comment": (Use("o.delete", ("cpp_delete_trailing_comment",)),),
        "function_definition": _DELETE,
        "if_statement": _DELETE,
        "for_statement": _DELETE,
        "for_range_loop": _DELETE,
        "while_statement": _DELETE,
        "identifier": _IDENT,
        "field_identifier": _IDENT,
        "field_expression": (Use("m.find", ("cpp_find_member",)),),
        "preproc_include": _LINE,
        "using_declaration": _LINE,
        "field_declaration": _LINE,
        "expression_statement": (*_LINE, Use("o.change", ("cpp_change_rhs",))),
        "declaration": (*_LINE, Use("o.change", ("cpp_change_rhs",))),
    },
    line_templates=(Use("m.rel", ("cpp_goto_line_rel",)), Use("m.find", ("cpp_find_char",))),
    find_targets=("(", ")", "{", "}", ";", ",", "=", "<", ">", ".", "->", "::"),
    comment_leader="//",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for C++."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_cpp.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse C++ source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a C++ source file into parseable 8-40 line windows (see ``snippets.windows``).

    Namespaces, classes, functions and header guards longer than 40 lines are split by
    recursing into their bodies. Comments matching the licence/author pattern break a
    window and are left out.
    """
    lines = text.splitlines()
    tree = parse("\n".join(lines))  # keep the tree alive while its nodes are walked
    spans = _spans(tree.root_node.named_children, lines)
    out = []
    for start, end in spans:
        win = _make_window(lines, start, end, source)
        if win is not None:
            out.append(win)
    return out


def generate(win: Window, lang: Language = LANG) -> list[Draft]:
    """``templates.generate`` for a C++ window, with the ``cpp_*`` templates registered.

    The shared registries (``templates.NODE_TEMPLATES`` / ``LINE_TEMPLATES``) only know the
    Python templates, and ``LANG``'s ``Use`` entries name ``cpp_*`` ones. They are added for
    the duration of the call and removed again, so the Python registry stays as it was.
    """
    with registered():
        return templates.generate(win, lang)


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``cpp_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(CPP_NODE_TEMPLATES, CPP_LINE_TEMPLATES)


def node_frequency(texts: list[str]) -> dict[str, object]:
    """``snippets.node_frequency`` for C++ (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, parse)


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
    text = _inner_text(win, node, inner)
    c, noun = _PAIR[o], _NOUNS[node.type]
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
    c, noun, delims, inner = _PAIR[o], _NOUNS[node.type], _DELIM_NAMES[o], win.lines[row][oc + 1:cc]
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
    """``gUi"``: uppercase the text inside a string literal."""
    _prime(win)
    span = _span(win, node)
    if span is None or span[3] != '"':
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
    """``C X;<Esc>`` / ``ct;X<Esc>``: replace the value of a one-line ``x = ...;``, cursor on it."""
    _prime(win)
    if node.start_point.row != node.end_point.row:
        return
    if node.type == "declaration":
        inits = [c for c in node.named_children if c.type == "init_declarator"]
        if len(inits) != 1:
            return
        left, right = _declared_name(inits[0].child_by_field_name("declarator")), inits[0].child_by_field_name("value")
    else:
        kids = node.named_children
        if len(kids) != 1 or kids[0].type != "assignment_expression":
            return
        left, right = kids[0].child_by_field_name("left"), kids[0].child_by_field_name("right")
    if left is None or right is None or right.type == "initializer_list":
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old = line[r0:r1]
    if line[r1:] != ";" or len(old) < 6 or ";" in old or node.parent is None or node.parent.type not in _LINE_PARENTS:
        return
    text = _fit(win, right, old)
    if text is None or (node.type == "declaration" and "auto" in _text(node.child_by_field_name("type")) and text == "{}"):
        return
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to {templates._quote(_text(left), 32)} with `{text}`",
        lines=win.lines, cursor=[row + 1, r0], expect={"lines": _replace(win.lines, row, r0, r1, text)},
        variants=[f"C{text};<Esc>", f"ct;{text}<Esc>", f"c${text};<Esc>"], alternates=[f"Da{text};<Esc>"],
        idioms=[f"cW{text}<Esc>", f"cw{text}<Esc>", f"ce{text}<Esc>"],
        typed=len(text), params={"text": text},
        target=[_range(row, r0, row, r1 - 1)], window=win, tags=["assignment", "change"],
        hints=[
            {"trigger": "^(D|d\\$|dt;)", "text": "C and ct; delete and enter insert mode in one command."},
            {"trigger": "x{3,}|^c[wWeE]", "text": "ct; changes everything up to the semicolon; C changes to the end of the line."},
            {"trigger": None, "text": "ct; changes up to the `;`; C (= c$) changes to the end of the line, `;` included."},
        ],
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
    if min(_indent(ln) for ln in body) != base + 4:
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    shifted = [(ln[4:] if under else "    " + ln) if r in rows and ln.strip() else ln for r, ln in enumerate(lines)]
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
    expect = moved[:other] + [lines[row]] + moved[other:]
    # Normal-mode yank/put is a legitimate idiom here, so the kind is "edit", as in
    # templates.move_line (players typing ddp were marked wrong while this was "ex").
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
    expect = lines[:dest] + [lines[row]] + lines[dest:]
    # Normal-mode yank/put is a legitimate idiom here (yyp is 3 keys to :t.'s 4), so the
    # kind is "edit" and the shortest variant becomes the par, as in templates.copy_line.
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
    """``{k}f.`` / ``{k}f-``: from the first non-blank, jump to the ``.``/``->`` before a field."""
    _prime(win)
    op, field = node.child_by_field_name("operator"), node.child_by_field_name("field")
    if op is None or field is None or op.type not in (".", "->") or op.start_point.row != field.end_point.row:
        return
    row, col = op.start_point.row, op.start_point.column
    line = win.lines[row]
    start = _indent(line)
    if row in win.cache["prose"] or line[start:start + 1] in ("#", ""):
        return
    c, name = op.type[0], _text(field)
    k = line.count(c, start + 1, col + 1)
    if not 1 <= k <= 3 or col - start < 3 * (2 if k == 1 else 3) + 1 or line.count(f"{op.type}{name}") != 1:
        return
    motion = f"{k}f{c}" if k > 1 else f"f{c}"
    yield Draft(
        template="find_char", skill=skill, kind="cursor", task=f"Move to the `{op.type}` before `{name}`",
        lines=win.lines, cursor=[row + 1, start], expect={"cursor": [row + 1, col]},
        variants=[motion], alternates=[f"f{c}" + ";" * (k - 1)] if k > 1 else [],
        idioms=list(templates.CURSOR_IDIOMS), params={"char": c, "n": k},
        target=[_range(row, col, row, col + len(op.type) - 1)], window=win, tags=["find", "member"],
        hints=[
            {"trigger": "l{4,}|w{3,}|e{3,}", "text": f"f{c} jumps to the next `{c}` on the line" + (f"; {motion} to the {templates.ordinal(k)}." if k > 1 else ".")},
            *([{"trigger": f"^f{_js_escape(c)};", "text": f"A count before f replaces the ; presses: {motion}."}] if k > 1 else []),
            {"trigger": None, "text": f"{motion}: find the {templates.ordinal(k)} `{c}` to the right."},
        ],
    )


def jump_match(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_match`` (grammar-agnostic) on a primed window."""
    _prime(win)
    yield from templates.jump_match(win, node, skill, lang)


def jump_block_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_block_end`` with C++ strings and comments excluded as start positions."""
    _prime(win)
    for draft in templates.jump_block_end(win, node, skill, lang):
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_NOUNS.get(node.type, 'bracket pair')} around the cursor",
                            draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f/D``: ``templates.delete_trailing_comment`` for single-line ``//`` and ``/* */`` comments.

    Comments after a bare ``}`` (``}  // namespace x``) are skipped: retyping ``}`` is cheaper.
    """
    _prime(win)
    row = node.start_point.row
    if row != node.end_point.row or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    if win.lines[row][node.end_point.column:].strip():
        return  # a mid-line `/* */` with code after it is not a trailing comment
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` with C++ task text (function names live in the declarator)."""
    _prime(win)
    target = node.parent if node.parent is not None and node.parent.type == "template_declaration" else node
    what = {
        "if_statement": "this `if` statement", "for_statement": "this `for` loop",
        "for_range_loop": "this `for` loop", "while_statement": "this `while` loop",
    }.get(node.type, "this statement")
    if node.type == "function_definition":
        name = _function_name(node)
        what = f"the function `{name}`" if name else "this function"
    for draft in templates.delete_lines(win, target, skill, lang):
        n = target.end_point.row - target.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def upper_word(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.upper_word``, skipping names qualified by a namespace (``std::move``)."""
    _prime(win)
    if not _qualified(node):
        yield from templates.upper_word(win, node, skill, lang)


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here``, skipping namespace-qualified names."""
    _prime(win)
    if not _qualified(node):
        yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst``, skipping namespace-qualified names."""
    _prime(win)
    if not _qualified(node):
        yield from templates.rename_all_subst(win, node, skill, lang)


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm I{prefix}<CR>`` over 3-8 consecutive one-line declarations or statements
    (x.normal): put back a prefix they all share (``const ``, ``static ``, ``this->``), or, when
    they share none and they are statements in a function body, comment them out with ``// ``
    (never class members, prototypes or namespace-level declarations)."""
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
            continue  # commenting out member declarations or prototypes is not an edit anyone drills (QA #53)
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
    """``V{n}j:norm ^gUiw<CR>`` over one-per-line enumerators, ``V{n}j:norm f=bgUiw<CR>`` over
    consecutive ``const`` / ``constexpr`` declarations: uppercase 3+ lower_snake names (x.normal)."""
    _prime(win)
    if node.type == "enumerator_list":
        items = [c for c in node.named_children if c.type == "enumerator"]
        names = [c.child_by_field_name("name") for c in items]
        rows = [c.start_point.row for c in items]
        one_per_line = rows and rows == list(range(rows[0], rows[0] + len(rows))) and _enum_lines(win, items)
        runs = [(rows, names, "^")] if one_per_line else []
    else:
        runs = [([d.start_point.row for d in run], [_const_name(win, d) for d in run], "f=b")
                for run in _statement_runs(win, node, templates.EX_MIN_LINES)]
    for rows, names, go in runs:
        if len(rows) < templates.EX_MIN_LINES or not all(n is not None and _SNAKE.fullmatch(_text(n)) for n in names):
            continue  # ex kind: gUiwj.j. on fewer lines would be the better drill
        rows, names = rows[:8], names[:8]
        if templates._seen(win, "constants", rows[0]):
            continue
        k = len(rows) - 1
        down = f"{k}j" if k > 1 else "j"
        go = "" if go == "^" and not _indent(win.lines[rows[0]]) else go  # :norm starts each line in column 0
        expect = list(win.lines)
        for r, name in zip(rows, names):
            c0, c1 = name.start_point.column, name.end_point.column
            expect[r] = expect[r][:c0] + expect[r][c0:c1].upper() + expect[r][c1:]
        what = "enumerators" if node.type == "enumerator_list" else "constants"
        yield Draft(
            template="upper_constants", skill=skill, kind="ex",
            task=f"Uppercase the names of these {k + 1} {what}",
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
    """``templates.goto_line_rel`` with C++ comment-only lines excluded as start and target."""
    _prime(win)
    yield from templates.goto_line_rel(win, skill, lang)


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: jump to the n-th X (``->`` and ``::`` included: ``f-`` / ``f:``) on the line."""
    _prime(win)
    rows = sorted(range(len(win.lines)), key=lambda r: snippets.stable_hash(win.key, r, "find"))
    prose = win.cache["prose"]
    made = 0
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("#", "", '"', "'"):
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


CPP_NODE_TEMPLATES: Final = {
    "cpp_change_inner": change_inner, "cpp_delete_inner": delete_inner, "cpp_delete_block": delete_block,
    "cpp_upper_inner": upper_inner, "cpp_change_nth_arg": change_nth_arg, "cpp_change_rhs": change_rhs,
    "cpp_indent_block": indent_block, "cpp_move_line": move_line, "cpp_copy_line": copy_line,
    "cpp_find_member": find_member, "cpp_jump_match": jump_match, "cpp_jump_block_end": jump_block_end,
    "cpp_delete_trailing_comment": delete_trailing_comment, "cpp_delete_lines": delete_lines,
    "cpp_upper_word": upper_word, "cpp_rename_here": rename_here, "cpp_rename_all_subst": rename_all_subst,
    "cpp_prefix_each_line": prefix_each_line, "cpp_upper_constants": upper_constants,
}
CPP_LINE_TEMPLATES: Final = {"cpp_goto_line_rel": goto_line_rel, "cpp_find_char": find_char}


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


def _header(win: Window, node: tree_sitter.Node, orow: int) -> str:
    """First line of the statement that owns a ``{`` block (the signature, not its last line)."""
    parent = node.parent
    row = parent.start_point.row if parent is not None and parent.type != "translation_unit" else orow
    return win.lines[min(row, orow)].strip()


def _fit(win: Window, node: tree_sitter.Node, old: str) -> str | None:
    """A replacement for an expression that fits its kind (a number for a number, ...), or None."""
    key = (win.key, node.start_point, "fit")
    kind, text = node.type, old.strip()
    if kind == "number_literal":
        return _pick_other(INT_TEXTS, text, *key)
    if kind in ("string_literal", "concatenated_string"):
        return '"' + _pick_other(STRING_TEXTS, text.strip('"'), *key) + '"'
    if kind in ("true", "false"):
        return "false" if kind == "true" else "true"
    if kind == "char_literal":
        return _pick_other(("' '", "'0'", "'a'", "'-'"), text, *key)
    if kind == "identifier":
        return templates._new_name(win, text, node, *key)
    if kind in ("binary_expression", "unary_expression"):
        op = node.child_by_field_name("operator")
        logical = op is not None and op.type in ("==", "!=", "<", ">", "<=", ">=", "&&", "||", "!", "and", "or", "not")
        return "false" if logical else "0"
    if kind in ("call_expression", "field_expression", "qualified_identifier", "conditional_expression",
                "subscript_expression"):
        return "{}"
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str:
    """Replacement contents for a delimited node, fitted to what is inside it now."""
    key = (win.key, node.start_point, "ci")
    args = [a for a in node.named_children if a.type != "comment"]
    if node.type in ("argument_list", "subscript_argument_list") and len(args) == 1:
        fitted = _fit(win, args[0], inner)
        if fitted is not None and fitted != "{}":
            return fitted
    if node.type in ("initializer_list", "subscript_argument_list") and '"' in inner:
        return '"' + _pick_other(STRING_TEXTS, inner, *key) + '"'
    if node.type == "initializer_list":
        return _pick_other(("0", "1, 2, 3") if "'" not in inner else ("' '", "'a', 'b'"), inner, *key)
    if node.type == "compound_statement":
        return "return {};" if inner.strip().startswith("return") else "++count;"
    return _pick_other(_TEXTS[node.type], inner, *key)


def _delims(win: Window) -> dict[str, int]:
    _prime(win)
    return win.cache["delims"]


def _end_row(node: tree_sitter.Node) -> int:
    """Last row a node occupies: preprocessor lines end at column 0 of the next row.

    Points are indexed, not read as ``.row`` / ``.column``: in py-tree-sitter 0.26.0 the
    attribute getters drop a reference they do not own, which frees ints above 256 (the
    non-immortal ones) and crashes the interpreter on files longer than 256 lines.
    """
    (r0, _), (r1, c1) = node.start_point, node.end_point
    return r1 - 1 if c1 == 0 and r1 > r0 else r1


def _spans(siblings: list[tree_sitter.Node], lines: list[str]) -> list[tuple[int, int]]:
    """Group sibling items into [start_row, end_row] spans of about SOFT_LINES lines.

    Short spans are merged only with spans of the same nesting level: a merge across a
    recursed-into body would swallow its closing ``}`` and leave the window unparseable.
    An item that starts on a row the previous item ends on (``}  // namespace x``) joins
    that item's group, or is dropped when that item was split.
    """
    out: list[tuple[int, int]] = []
    run: list[tuple[int, int]] = []
    group: list[int] | None = None
    prev_end = -1
    for node in siblings:
        start, end = node.start_point[0], _end_row(node)
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
        if end - start + 1 > snippets.MAX_LINES:
            if group:
                run.append(tuple(group))
            group = None
            out += _merge_short(run) + _spans(_body_items(node), lines)
            run = []
            continue
        if group and end - group[0] + 1 > snippets.MAX_LINES:
            run.append(tuple(group))
            group = None
        group = [start, end] if group is None else [group[0], end]
        if group[1] - group[0] + 1 >= snippets.SOFT_LINES:
            run.append(tuple(group))
            group = None
    if group:
        run.append(tuple(group))
    return out + _merge_short(run)


def _body_items(node: tree_sitter.Node, depth: int = 0) -> list[tree_sitter.Node]:
    """The items inside a long namespace / class / function / header guard.

    The fallback looks at most two levels down (``template <...> class X {...};``):
    walking a whole expression tree recursively overflows the C stack on long
    ``<<`` / ``+`` chains.
    """
    if node.type in ("preproc_ifdef", "preproc_if", "preproc_else", "preproc_elif"):
        skip = {node.child_by_field_name("name"), node.child_by_field_name("condition"),
                node.child_by_field_name("alternative")}
        return [c for c in node.named_children if c not in skip]
    if node.type in ("linkage_specification",):
        body = node.child_by_field_name("body")
        return body.named_children if body is not None and body.type == "declaration_list" else []
    body = node.child_by_field_name("body")
    if body is not None:
        return body.named_children
    if depth >= 2:
        return []
    for child in node.named_children:  # template_declaration, `class X {...};` declarations
        items = _body_items(child, depth + 1) if child.type != "comment" else []
        if items:
            return items
    return []


def _make_window(lines: list[str], start: int, end: int, source: dict[str, str]) -> Window | None:
    start, end = snippets.trim_comment_edges(lines, start, end)
    chunk = lines[start:end + 1]
    while chunk and not chunk[0].strip():
        chunk, start = chunk[1:], start + 1
    while chunk and not chunk[-1].strip():
        chunk, end = chunk[:-1], end - 1
    indent = min(len(ln) - len(ln.lstrip()) for ln in chunk if ln.strip()) if chunk else 0
    chunk = [ln.rstrip() for ln in textwrap.dedent("\n".join(chunk)).split("\n")]
    if snippets.size_problem(chunk):
        return None
    tree = parse("\n".join(chunk))
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with C++ facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    C++ template to run fills it, so later shared helpers (``_prose_rows``,
    ``_string_cells``, ``_delim_count``) find C++ answers instead of Python ones.
    """
    if win.cache.get("cpp"):
        return
    prose: set[int] = set()
    cells: set[tuple[int, int]] = set()
    delims: dict[str, int] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        if n.type in _STRINGS:
            cells |= _cells(win, n)
            r0, r1 = n.start_point.row, _end_row(n)
            if r1 > r0 and n.type != "system_lib_string":
                prose.update(range(r0, r1 + 1))
            if n.type == "comment" and not win.lines[r0][:n.start_point.column].strip():
                prose.update(range(r0, r1 + 1))
            if n.type == "string_literal" and n.children and n.children[0].type == '"':
                delims['"'] = delims.get('"', 0) + 1
            continue
        if n.type in ("(", "[", "{"):
            delims[n.type] = delims.get(n.type, 0) + 1
        elif n.type in _ANGLES:
            delims["<"] = delims.get("<", 0) + 1
        stack.extend(n.children)
    win.cache.update({"cpp": True, "prose": prose, "strings": cells, "delims": delims, "role_names": ROLE_NAMES,
                      "types": _type_roles(win)})


def _type_roles(win: Window) -> dict[str, str]:
    """Name -> role from C++ declarations and parameters: a pointer is "ptr", a char array
    "buffer", a container "many", a bool "flag", a string "text", an integer "count".
    Read by templates._role through the window cache."""
    roles: dict[str, str] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type not in ("declaration", "field_declaration", "parameter_declaration"):
            continue
        type_text = _text(n.child_by_field_name("type"))
        for decl in n.children_by_field_name("declarator"):
            name = _declared_name(decl)
            if name is None:
                continue
            inner = decl.child_by_field_name("declarator") if decl.type == "init_declarator" else decl
            if inner is not None and inner.type == "pointer_declarator":
                role = "ptr"
            elif inner is not None and inner.type == "array_declarator" and "char" in type_text:
                role = "buffer"
            else:
                role = next((r for rx, r in _TYPE_ROLES if rx.search(type_text)), None)
            if role is not None:
                roles.setdefault(_text(name), role)
    return roles


def _declared_name(decl: tree_sitter.Node | None) -> tree_sitter.Node | None:
    """The identifier a declarator declares: ``next`` in ``* next``, ``buf`` in ``buf[64]``, ``x`` in ``x = 1``.
    Called by change_rhs (so the task never shows ``* next``, QA #54) and _type_roles."""
    while decl is not None and decl.type not in ("identifier", "field_identifier"):
        if decl.type not in ("init_declarator", "pointer_declarator", "reference_declarator", "array_declarator"):
            return None
        decl = decl.child_by_field_name("declarator") or next(
            (k for k in decl.named_children if k.type in ("identifier", "field_identifier")), None)
    return decl


def _span(win: Window, node: tree_sitter.Node) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node."""
    kids = node.children
    if node.type == "string_literal":
        if len(kids) < 2 or kids[0].type != '"' or kids[-1].type != '"' or node.start_point.row != node.end_point.row:
            return None
        if node.parent is not None and node.parent.type == "preproc_include":
            return None  # an #include path is not text to edit (QA #27)
        if any(k.type == "escape_sequence" for k in kids):
            return None
        row, oc, cc, q = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column, '"'
    elif node.type in _ANGLES:
        if len(kids) < 2 or kids[0].type != "<" or kids[-1].type != ">" or node.start_point.row != node.end_point.row:
            return None
        row, oc, cc, q = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column, "<"
    elif node.type == "raw_string_literal":
        return None
    else:
        pair = _bracket_pair(node)
        if pair is None or pair[0][0] != pair[1][0]:
            return None
        (row, oc, q), (_, cc, _) = pair
    inner = win.lines[row][oc + 1:cc]
    if len(inner.strip()) < 3 or (q == '"' and ('"' in inner or "\\" in inner)):
        return None
    if _delims(win).get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace, not in a nested pair or a string."""
    line = win.lines[row]
    if o == '"':
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
    if parent is None or parent.type not in _LINE_PARENTS or _end_row(node) != row:
        return None
    if win.lines[row].strip() != _text(node).strip():
        return None  # the line holds more than this statement (a trailing comment, a second statement)
    rows = {s.start_point.row for s in parent.named_children
            if s.type != "comment" and _end_row(s) == s.start_point.row
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
        if kid is not None and kid.type in _RUN_ITEMS and _end_row(kid) == kid.start_point.row:
            if win.lines[kid.start_point.row].strip() == _text(kid).strip():
                item = kid
        if item is not None and (not run or (item.start_point.row == run[-1].start_point.row + 1
                                             and item.start_point.column == run[0].start_point.column)):
            run.append(item)
            continue
        if len(run) >= min_len:
            yield run
        run = [item] if item is not None else []


def _const_name(win: Window, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The name of a one-line ``const``/``constexpr T name = value;``, when it sits right
    before the line's only ``=`` (so ``f=b`` lands on it), else None."""
    line = win.lines[node.start_point.row]
    if node.type not in ("declaration", "field_declaration") or line.count("=") != 1:
        return None
    if not any(c.type == "type_qualifier" and _text(c) in ("const", "constexpr") for c in node.children):
        return None
    inits = [c for c in node.named_children if c.type == "init_declarator"]
    name = inits[0].child_by_field_name("declarator") if len(inits) == 1 else None
    if name is None or name.type not in ("identifier", "field_identifier"):
        return None
    return name if line[name.end_point.column:].lstrip().startswith("=") else None


def _enum_lines(win: Window, items: list[tree_sitter.Node]) -> bool:
    """True when every enumerator is alone on its line (``name,`` or ``name = value,``)."""
    return all(win.lines[c.start_point.row].strip().rstrip(",") == _text(c) for c in items)


def _in_function_body(node: tree_sitter.Node) -> bool:
    """True for a ``{}`` block that is, or sits inside, the body of a function or lambda."""
    while node is not None and node.type == "compound_statement":
        parent = node.parent
        if parent is not None and parent.type in ("function_definition", "lambda_expression"):
            return True
        node = parent
        while node is not None and node.type not in ("compound_statement", "function_definition",
                                                       "lambda_expression", "translation_unit"):
            node = node.parent
    return False


def _which_pair(win: Window, node: tree_sitter.Node, row: int, oc: int, inner: str) -> tuple[bool, bool]:
    """``templates._which_pair`` with angle brackets nested by the tree (``vector<vector<int>>``):
    a text-only count would read every less-than as an opening angle."""
    nested = None
    if node.type in _ANGLES:
        up = node.parent
        while up is not None and up.type not in _ANGLES:
            up = up.parent
        nested = up is not None
    return templates._which_pair(win, row, oc, inner, nested)


def _qualified(node: tree_sitter.Node) -> bool:
    """True for ``move`` in ``std::move``: renaming one half of a qualified name is not an edit."""
    parent = node.parent
    return parent is not None and parent.type == "qualified_identifier"


def _function_name(node: tree_sitter.Node) -> str:
    decl = node.child_by_field_name("declarator")
    while decl is not None and decl.type != "function_declarator":
        decl = decl.child_by_field_name("declarator")
    name = decl.child_by_field_name("declarator") if decl is not None else None
    text = _text(name)
    return text if text and len(text) <= 40 and "\n" not in text else ""
