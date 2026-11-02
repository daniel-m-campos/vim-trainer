"""Go: tree-sitter-go node types mapped to skills and templates, plus windowing.

Node type names come from tree-sitter-go's node-types.json (grammar 0.25). The module
follows lang/js.py (read that one first), with the same names in the same order. The
differences:

- ``windows`` re-indents each file from gofmt's tabs to four spaces, the oracle's
  ``shiftwidth`` with ``expandtab`` (``reindent``), so ``>>`` shifts by one level of the
  code. The inside of a multi-line raw string is string content and is left alone; a
  window that still holds a tab there is dropped by ``snippets.size_problem``.
- A block's statements sit in a ``statement_list`` child of the ``block``. A function
  body, ``if`` or ``for`` longer than a window is cut into windows of statements (they
  parse on their own: tree-sitter-go accepts statements at the top level). A struct
  body, interface, ``const ( ... )`` / ``var ( ... )`` / ``import ( ... )`` group,
  switch body or composite literal longer than a window is cut into windows of whole
  members kept between the header line and the closing line.
- Strings are ``"interpreted"`` or ```raw``` (backticks); both drill t.quote. A rune
  literal (``'a'``) is masked as a string but never drilled (its inside is one char).
- Conditions have no parentheses, so t.paren / m.match come from calls, parameter lists,
  grouping parentheses and composite literals (``T{a: 1}`` is a brace text object).
- No t.angle: Go's type parameters use square brackets, and generics are rare in the corpus.
- o.case: Go constants are not UPPER_CASE, so the case drill is the export toggle (``b~``
  on a function, method or type defined once in the window) and ``gUi"`` on a string.
- x.normal: ``:norm I...`` puts back a prefix a run of statements shares (a receiver or
  package selector such as ``sb.``, or ``defer ``), or comments a run out with ``// ``.

``generate`` registers the ``go_*`` templates for the duration of one call, as
``js.generate`` does; the grammar-agnostic shared templates (``jump_match``,
``rename_here``, ...) run through thin wrappers that prime the window cache with Go facts
first.
"""

import contextlib
import functools
import re
import textwrap
from collections.abc import Iterator
from typing import Final

import tree_sitter
import tree_sitter_go

from vimtrainer_content import snippets, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, Go column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    "m.match": 1.5, "t.brace": 1.5, "n.unmatched": 1.5, "t.paren": 1.5, "t.bracket": 1.2, "t.quote": 1.2,
    "o.indent": 0.5, "m.find": 1.2, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0, "m.rel": 1.0,
    "o.change": 1.0, "o.case": 1.0, "x.copymove": 1.0, "x.normal": 1.0,
}
TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove", "x.normal",
)
FOUR: Final = "    "  # the indent unit windows are re-indented to (the oracle's shiftwidth)

STRING_TEXTS: Final = ("not found", "invalid input", "out of range", "unknown", "skipped", "empty", "error: ")
ARG_TEXTS: Final = ("len(items)", "key, count", "0", "count + 1", "name")
PARAM_TEXTS: Final = ("n int", "name string", "items []string", "a, b int")
RESULT_TEXTS: Final = ("int, error", "string, bool", "bool, error")
EXPR_TEXTS: Final = ("n - 1", "a + b", "count * 2", "len(items) - 1")
SUBSCRIPT_TEXTS: Final = ("0", "i+1", "index", "key", "n-1")  # gofmt writes no spaces inside an index
SLICE_TEXTS: Final = ("1:", ":n", "i:j", "start:end")
KEYED_TEXTS: Final = ("name: name", "count: 0", "id: 1")
INT_ELEMENT_TEXTS: Final = ("1, 2, 3", "0", "10, 20")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")
FLOAT_TEXTS: Final = ("0.0", "0.5", "1.5", "2.0")
RUNE_TEXTS: Final = ("'a'", "' '", "'0'", "'x'")
# Rename targets by role (see templates.ROLE_NAMES); one word each, so templates._styled
# gives camelCase / MixedCase like the code (it keeps snake_case for a one-word old name).
ROLE_NAMES: Final = {
    "many": ("items", "values"),
    "count": ("count", "total", "size"),
    "index": ("index", "pos"),
    "text": ("name", "label"),
    "flag": ("valid", "ready", "done"),
    "call": ("process", "compute", "update"),
    "class": ("record", "item", "handler"),
    "any": ("value", "result"),
}
# Declared type -> role, first match wins (_type_roles).
_TYPE_ROLES: Final = (
    (re.compile(r"^\[|^map\["), "many"),
    (re.compile(r"^bool$"), "flag"),
    (re.compile(r"^(string|rune|byte)$"), "text"),
    (re.compile(r"^u?int(8|16|32|64)?$|^float(32|64)$"), "count"),
)
_VALUE_ROLES: Final = {
    "int_literal": "count", "float_literal": "count", "interpreted_string_literal": "text",
    "raw_string_literal": "text", "true": "flag", "false": "flag",
}

_NOUNS: Final = {
    "interpreted_string_literal": "string", "raw_string_literal": "raw string", "argument_list": "argument list",
    "parameter_list": "parameter list", "parenthesized_expression": "parenthesised expression",
    "index_expression": "index", "slice_expression": "slice expression", "literal_value": "composite literal",
    "block": "block", "field_declaration_list": "struct body",
}
_TEXTS: Final = {
    "interpreted_string_literal": STRING_TEXTS, "raw_string_literal": STRING_TEXTS, "argument_list": ARG_TEXTS,
    "parameter_list": PARAM_TEXTS, "parenthesized_expression": EXPR_TEXTS, "index_expression": SUBSCRIPT_TEXTS,
    "slice_expression": SLICE_TEXTS,
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", '"': '"', "`": "`"}
_DELIM_NAMES: Final = {"(": "parentheses", "[": "square brackets", "{": "braces", '"': "quotes", "`": "backticks"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), '"': (), "`": ()}
_QUOTES: Final = frozenset({'"', "`"})
_STRING_NODES: Final = frozenset({"interpreted_string_literal", "raw_string_literal"})
_STRINGS: Final = frozenset({*_STRING_NODES, "rune_literal", "comment"})
_FUNCTIONS: Final = frozenset({"function_declaration", "method_declaration", "func_literal"})
_LINE_PARENTS: Final = frozenset({
    "source_file", "statement_list", "field_declaration_list", "var_spec_list", "const_declaration",
    "import_spec_list",
})
_RHS_PARENTS: Final = _LINE_PARENTS | {"var_declaration"}
# Containers whose items do not parse on their own: a window of them keeps the container's
# header and closing lines (_body_items).
_MEMBER_LISTS: Final = frozenset({
    "field_declaration_list", "interface_type", "literal_value", "import_spec_list", "var_spec_list",
    "const_declaration", "expression_switch_statement", "type_switch_statement", "select_statement",
})
_CLOSER_LINE: Final = re.compile(r"[})][)\]},]*")
# x.normal: one-line statements a `:norm` range runs over, and the fixed prefixes a run of
# them can share; a shared `name.` selector (`sb.`, `fmt.`) is found per run (_shared_prefix).
_RUN_ITEMS: Final = frozenset({
    "short_var_declaration", "assignment_statement", "expression_statement", "inc_statement", "dec_statement",
    "var_declaration", "defer_statement", "go_statement", "send_statement",
})
_PREFIXES: Final = ("defer ", "var ", "go ")
_SELECTOR_PREFIX: Final = re.compile(r"[A-Za-z_]\w{0,11}\.(?=[A-Za-z_])")
_EXPORT_NAME: Final = re.compile(r"[A-Za-z][A-Za-z0-9]{3,}")
_KEYWORDS: Final = frozenset("""
    break case chan const continue default defer else fallthrough for func go goto if import interface map
    package range return select struct switch type var
    any bool byte comparable complex64 complex128 error float32 float64 int int8 int16 int32 int64 rune
    string uint uint8 uint16 uint32 uint64 uintptr true false iota nil
    append cap clear close complex copy delete imag len make max min new panic print println real recover
    bufio bytes cmp errors fmt io math maps os rand regexp slices sort strconv strings sync time unicode utf8
    big bits Println Printf Sprintf Sprint Errorf Error String New Itoa Atoi main init err ok
""".split())

_PAREN = (
    Use("t.paren", ("go_change_inner", "go_delete_inner")),
    Use("m.match", ("go_jump_match",)),
    Use("n.unmatched", ("go_jump_block_end",)),
)
_IDENT = (Use("t.word", ("go_rename_here",)), Use("x.subst", ("go_rename_all_subst",)))
_LINE = (Use("x.copymove", ("go_move_line", "go_copy_line")),)
_DELETE = (Use("o.delete", ("go_delete_lines",)),)
_EXPORT = (Use("o.case", ("go_toggle_export",)),)
_ASSIGN = (*_LINE, Use("o.change", ("go_change_rhs",)))

_NODES: Final = {
    "interpreted_string_literal": (
        Use("t.quote", ("go_change_inner", "go_delete_inner")), Use("o.case", ("go_upper_inner",)),
    ),
    "raw_string_literal": (Use("t.quote", ("go_change_inner", "go_delete_inner")),),
    "argument_list": (*_PAREN, Use("o.change", ("go_change_nth_arg",))),
    "parameter_list": _PAREN,
    "parenthesized_expression": _PAREN,
    "block": (
        Use("t.brace", ("go_change_inner", "go_delete_inner", "go_delete_block")),
        Use("m.match", ("go_jump_match",)),
        Use("n.unmatched", ("go_jump_block_end",)),
        Use("o.indent", ("go_indent_block",)),
        Use("x.normal", ("go_prefix_each_line",)),
    ),
    "source_file": (Use("x.normal", ("go_prefix_each_line",)),),
    "literal_value": (
        Use("t.brace", ("go_change_inner", "go_delete_inner", "go_delete_block")),
        Use("m.match", ("go_jump_match",)),
        Use("n.unmatched", ("go_jump_block_end",)),
    ),
    "field_declaration_list": (
        Use("t.brace", ("go_delete_block",)), Use("m.match", ("go_jump_match",)),
        Use("o.indent", ("go_indent_block",)),
    ),
    # index_expression's and slice_expression's `[...]` are not nodes of their own; _span finds them.
    "index_expression": (Use("t.bracket", ("go_change_inner", "go_delete_inner")),),
    "slice_expression": (Use("t.bracket", ("go_change_inner", "go_delete_inner")),),
    "comment": (Use("o.delete", ("go_delete_trailing_comment",)),),
    "function_declaration": (*_DELETE, *_EXPORT),
    "method_declaration": (*_DELETE, *_EXPORT),
    "type_spec": _EXPORT,
    "type_declaration": _DELETE,
    "if_statement": _DELETE,
    "for_statement": _DELETE,
    "expression_switch_statement": _DELETE,
    "type_switch_statement": _DELETE,
    "identifier": _IDENT,
    "field_identifier": _IDENT,
    "selector_expression": (Use("m.find", ("go_find_member",)),),
    "import_spec": _LINE,
    "field_declaration": _LINE,
    "expression_statement": _LINE,
    "inc_statement": _LINE,
    "dec_statement": _LINE,
    "var_declaration": _LINE,
    "const_declaration": _LINE,
    "short_var_declaration": _ASSIGN,
    "assignment_statement": _ASSIGN,
    "var_spec": _ASSIGN,
    "const_spec": _ASSIGN,
}
_LINE_TEMPLATES: Final = (Use("m.rel", ("go_goto_line_rel",)), Use("m.find", ("go_find_char",)))
_FIND_TARGETS: Final = ("(", ")", "{", "}", "[", "]", ",", "=", ".", ":=", ":")

LANG = Language(
    name="go",
    short="go",
    grammar="go",
    nodes=_NODES,
    line_templates=_LINE_TEMPLATES,
    find_targets=_FIND_TARGETS,
    comment_leader="//",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for Go."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_go.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse Go source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a Go source file into parseable 8-40 line windows (see ``snippets.windows``).

    Parameters
    ----------
    text
        The whole file, gofmt style (tab-indented).
    source
        Provenance (``repo``, ``path``, ``commit``, ``license``) stored on each window.

    Returns
    -------
    list[Window]
        Windows re-indented to four spaces (``reindent``). Functions, ``if`` / ``for``
        statements, struct bodies, declaration groups, switches and composite literals
        longer than 40 lines are split by recursing into their bodies; a window of members
        that do not parse alone keeps the header and closing lines around them. Comments
        matching the licence/author pattern break a window and are left out.
    """
    lines = reindent(text.splitlines())
    tree = parse("\n".join(lines))  # keep the tree alive while its nodes are walked
    out = []
    for start, end, wrap in _spans(tree.root_node.named_children, lines):
        win = _make_window(lines, start, end, wrap, source)
        if win is not None:
            out.append(win)
    return out


def reindent(lines: list[str]) -> list[str]:
    """``lines`` with every leading tab turned into four spaces.

    gofmt indents with tabs and aligns with spaces, so only the leading run of tabs is an
    indent; spaces after it (a continuation aligned by hand) are kept. Rows inside a
    multi-line raw string are string content and stay as they are.

    Parameters
    ----------
    lines
        Source lines.

    Returns
    -------
    list[str]
        The re-indented lines, one per input line.
    """
    keep: set[int] = set()
    stack = [parse("\n".join(lines)).root_node]
    while stack:
        node = stack.pop()
        if node.type == "raw_string_literal":
            keep.update(range(node.start_point[0] + 1, node.end_point[0] + 1))
            continue
        stack.extend(node.children)
    return [ln if r in keep else FOUR * (len(ln) - len(ln.lstrip("\t"))) + ln.lstrip("\t")
            for r, ln in enumerate(lines)]


def generate(win: Window, lang: Language = LANG) -> list[Draft]:
    """``templates.generate`` for a Go window, with the ``go_*`` templates registered.

    Parameters
    ----------
    win
        A window from ``windows``.
    lang
        The Go mapping (``LANG``).

    Returns
    -------
    list[Draft]
        At most ``templates.MAX_PER_WINDOW`` drafts per (template, skill).
    """
    with registered():
        return templates.generate(win, lang)


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``go_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(GO_NODE_TEMPLATES, GO_LINE_TEMPLATES)


def node_frequency(texts: list[str]) -> dict[str, object]:
    """``snippets.node_frequency`` for Go (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, parse)


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>`` on a single-line string, bracket or brace pair."""
    _prime(win)
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    text = _inner_text(win, node, inner)
    if col is None or text is None or text == inner:
        return
    c, noun = _PAIR[o], _noun(node)
    draft = Draft(
        template="change_inner", skill=skill, kind="edit",
        task=f"Change {templates._inside_phrase(noun, _DELIM_NAMES[o], inner, _which_pair(win, row, oc, inner))} to `{text}`",
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
    """``di{delim}``: empty a single-line string, bracket or brace pair."""
    _prime(win)
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    col = _cursor_inside(win, node, row, oc, cc, o)
    if col is None:
        return
    c, noun, delims, inner = _PAIR[o], _noun(node), _DELIM_NAMES[o], win.lines[row][oc + 1:cc]
    draft = Draft(
        template="delete_inner", skill=skill, kind="edit",
        task=f"Delete {templates._inside_phrase(noun, delims, inner, _which_pair(win, row, oc, inner))}, keeping the {delims}",
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
    if win.cache["delims"].get("{", 0) < 2:
        return
    strings = win.cache["strings"]
    cols = [p for p in _depth0_positions(win, (orow, ocol), (crow, ccol), "{", "}") if p not in strings]
    if not cols:
        return
    row, col = pick(cols, win.key, node.start_point, "blk")
    yield Draft(
        template="delete_inner", skill=skill, kind="edit",
        task=f"Delete the {n} lines inside the braces of {templates._quote(_header(win, node, orow))}, keeping the `{{` and `}}` lines",
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
    """``gUi"``: uppercase the text inside an interpreted string literal."""
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
        task=f"Uppercase {templates._inside_phrase('string', 'quotes', inner, _which_pair(win, row, oc, inner))}",
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


def toggle_export(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``b~``: export (or unexport) a function, method or type by toggling the case of its
    first letter, cursor inside the name.

    Only a name the window holds once (its own definition), so the edit breaks no use in
    view, and whose other-case spelling is not in the window already.
    """
    _prime(win)
    name_node = node.child_by_field_name("name")
    name = _text(name_node)
    if name_node is None or not _EXPORT_NAME.fullmatch(name) or name in lang.keywords:
        return
    new = name[0].swapcase() + name[1:]
    if new in lang.keywords or len(re.findall(rf"\b(?:{name}|{new})\b", "\n".join(win.lines))) != 1:
        return
    if templates._seen(win, "export", name):
        return
    row, c0 = name_node.start_point.row, name_node.start_point.column
    col = c0 + pick(range(3, len(name)), win.key, node.start_point, "export")
    what = {"function_declaration": "function", "method_declaration": "method"}.get(node.type, "type")
    up = name[0].islower()
    task = (f"Export the {what} `{name}`: capitalise its first letter (`{new}`)" if up
            else f"Unexport the {what} `{name}`: lowercase its first letter (`{new}`)")
    op, v = ("gU", "U") if up else ("gu", "u")
    yield Draft(
        template="toggle_case", skill=skill, kind="edit", task=task,
        lines=win.lines, cursor=[row + 1, col], expect={"lines": _replace(win.lines, row, c0, c0 + 1, new[0])},
        variants=["b~", f"b{op}l"], alternates=[f"bv{v}"],
        idioms=[f"bs{new[0]}<Esc>", f"bxi{new[0]}<Esc>", f"br{new[0]}", "~", "0~", f"F{name[0]}~", f"b{op}iw"],
        params={"word": name, "text": new}, target=[_range(row, c0, row, c0 + len(name) - 1)], window=win,
        tags=[node.type, "case"],
        hints=[
            {"trigger": "^b?(s|x|r|c)", "text": "~ toggles the case of the character under the cursor; nothing to retype."},
            {"trigger": "^[0-9]*h", "text": "b jumps back to the start of the word in one key."},
            {"trigger": None, "text": "b~: back to the start of the name, then ~ toggles the case of its first letter."},
        ],
    )


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
    text = _fit(win, arg, value)
    if k < 1 or text is None:
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
    """``C X<Esc>``: replace the value of a one-line ``x := ...``, ``x = ...``, ``var x = ...``
    or ``const x = ...``, cursor on the value."""
    _prime(win)
    sides = _assignment_sides(node)
    if sides is None or node.start_point.row != node.end_point.row:
        return
    left, right = sides
    if right.type == "func_literal" or node.parent is None or node.parent.type not in _RHS_PARENTS:
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old = line[r0:r1]
    if line[r1:] or len(old) < 6:
        return  # a trailing comment or a closing paren after the value: C would delete it too
    text = _fit(win, right, old)
    if text is None:
        return
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to {templates._quote(_text(left), 32)} with `{text}`",
        lines=win.lines, cursor=[row + 1, r0], expect={"lines": _replace(win.lines, row, r0, r1, text)},
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
    rows = range(start, end + 1)
    if any(not lines[r].strip() for r in rows) or any(r in win.cache["raw_rows"] for r in rows):
        return  # blank lines: the highlight skips them (QA #26); raw string rows: >> would change the string
    base = _indent(lines[crow])
    if min(_indent(lines[r]) for r in rows) != base + len(FOUR):
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    shifted = [(ln[4:] if under else FOUR + ln) if r in rows else ln for r, ln in enumerate(lines)]
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
    """``{k}f.``: from the first non-blank, jump to the ``.`` before a selected field or method."""
    _prime(win)
    op = next((c for c in node.children if c.type == "."), None)
    field = node.child_by_field_name("field")
    if op is None or field is None or op.start_point.row != field.end_point.row:
        return
    row, col = op.start_point.row, op.start_point.column
    line = win.lines[row]
    start = _indent(line)
    if row in win.cache["prose"] or line[start:start + 1] in ("", "/", "*", '"', "`"):
        return
    name = _text(field)
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
    """``templates.jump_block_end`` with Go strings and comments excluded as start positions."""
    _prime(win)
    for draft in templates.jump_block_end(win, node, skill, lang):
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_noun(node)} around the cursor", draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f/D``: ``templates.delete_trailing_comment`` for single-line ``//`` and ``/* */`` comments.

    Comments after a bare ``}`` or ``},`` are skipped: retyping the code is cheaper.
    """
    _prime(win)
    row = node.start_point.row
    if row != node.end_point.row or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    if win.lines[row][node.end_point.column:].strip():
        return  # a mid-line `/* */` with code after it is not a trailing comment
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` with Go task text (functions, methods and types named)."""
    _prime(win)
    what = {
        "if_statement": "this `if` statement", "for_statement": "this `for` loop",
        "expression_switch_statement": "this `switch` statement", "type_switch_statement": "this `switch` statement",
    }.get(node.type, "this statement")
    name = ""
    if node.type in ("function_declaration", "method_declaration"):
        name = _text(node.child_by_field_name("name"))
        kind = "function" if node.type == "function_declaration" else "method"
        what = f"the {kind} `{name}`" if name and len(name) <= 40 else f"this {kind}"
    elif node.type == "type_declaration":
        specs = [k for k in node.named_children if k.type == "type_spec"]
        name = _text(specs[0].child_by_field_name("name")) if len(specs) == 1 else ""
        what = f"the type `{name}`" if name and len(name) <= 40 else "this type declaration"
    for draft in templates.delete_lines(win, node, skill, lang):
        n = node.end_point.row - node.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here`` on a primed window; a selected field or method (``g.rolls``) and a
    composite literal key (``Node{value: v}``) are skipped: renaming one use of a member in place
    is rarely a real edit."""
    _prime(win)
    if _is_member(node):
        return
    with _exported_names(win, node):
        yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst`` on a primed window (``_exported_names`` for the new name),
    for names never used as a field, method or composite literal key in the window: ``:%s``
    would rename those too."""
    _prime(win)
    if _text(node) in win.cache["members"]:
        return
    with _exported_names(win, node):
        yield from templates.rename_all_subst(win, node, skill, lang)


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm I{prefix}<CR>`` over 3-8 consecutive one-line statements (x.normal): put back
    a prefix a stretch of them shares (``sb.``, ``fmt.``, ``defer ``), or, when no stretch of
    three shares one and they are statements of a function body, comment the first eight out
    with ``// ``."""
    _prime(win)
    items = node
    if node.type == "block":
        items = next((k for k in node.named_children if k.type == "statement_list"), None)
        if items is None:
            return
    in_body = _in_function_body(node) or (node.type == "source_file" and win.indent > 0)
    for run in _statement_runs(win, items, templates.EX_MIN_LINES):
        col = _indent(win.lines[run[0].start_point.row])
        rows = [item.start_point.row for item in run]
        plans = _prefix_runs(win, rows, col)
        if not plans and in_body:  # commenting out top-level declarations is not an edit anyone drills
            plans = [(rows[:8], None)]
        for some, prefix in plans:
            if templates._seen(win, f"prefix:{skill}", str(some[0])):
                continue
            draft = _prefix_draft(win, skill, some, col, prefix)
            if _worth_it(draft, lang):
                yield draft


# Line templates ===================================================================================


def goto_line_rel(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.goto_line_rel`` with Go comment-only lines excluded as start and target."""
    _prime(win)
    yield from templates.goto_line_rel(win, skill, lang)


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: jump to the n-th X (``:=`` included: ``f:``) on the line, never into a
    string or comment."""
    _prime(win)
    rows = sorted(range(len(win.lines)), key=lambda r: snippets.stable_hash(win.key, r, "find"))
    prose, strings = win.cache["prose"], win.cache["strings"]
    made = 0
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("", '"', "`", "/", "*"):
            continue
        options = []
        for tok in lang.find_targets:
            cols = _occurrences(line, tok, start + 1)
            for n, col in enumerate(cols[:3], 1):
                k = line.count(tok[0], start + 1, col + 1)  # f counts the first char of the token
                if k == n and col - start >= 3 * (2 if n == 1 else 3) + 1 and (row, col) not in strings:
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


GO_NODE_TEMPLATES: Final = {
    "go_change_inner": change_inner, "go_delete_inner": delete_inner, "go_delete_block": delete_block,
    "go_upper_inner": upper_inner, "go_toggle_export": toggle_export, "go_change_nth_arg": change_nth_arg,
    "go_change_rhs": change_rhs, "go_indent_block": indent_block, "go_move_line": move_line,
    "go_copy_line": copy_line, "go_find_member": find_member, "go_jump_match": jump_match,
    "go_jump_block_end": jump_block_end, "go_delete_trailing_comment": delete_trailing_comment,
    "go_delete_lines": delete_lines, "go_rename_here": rename_here, "go_rename_all_subst": rename_all_subst,
    "go_prefix_each_line": prefix_each_line,
}
GO_LINE_TEMPLATES: Final = {"go_goto_line_rel": goto_line_rel, "go_find_char": find_char}


# Private Functions ================================================================================


# Shared with the other brace languages (see lang/braces.py).
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
    """How a task names a delimited node; the body of ``func(...) { ... }`` is the function literal."""
    if node.type == "block" and node.parent is not None and node.parent.type == "func_literal":
        return "function literal"
    return _NOUNS.get(node.type, "bracket pair")


def _header(win: Window, node: tree_sitter.Node, orow: int) -> str:
    """First line of the statement that owns a ``{`` block (the signature, not its last line);
    an ``else`` block's own line (``} else {``)."""
    parent = node.parent
    row = orow
    if parent is not None and parent.type != "source_file" and parent.child_by_field_name("alternative") != node:
        row = parent.start_point.row
        if parent.type == "struct_type" and parent.parent is not None:
            row = parent.parent.start_point.row  # the type_spec: `type Game struct {`
    return win.lines[min(row, orow)].strip()


def _is_member(node: tree_sitter.Node) -> bool:
    """True for ``rolls`` in ``g.rolls`` (the field of a selector expression) and for ``value`` in
    ``Node{value: v}`` (the key of a composite literal element)."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "selector_expression":
        return parent.child_by_field_name("field") == node
    up = parent.parent
    return parent.type == "literal_element" and up is not None and up.type == "keyed_element" and up.named_children[0] == parent


@contextlib.contextmanager
def _exported_names(win: Window, node: tree_sitter.Node) -> Iterator[None]:
    """For the ``with`` block, rename an exported value (``Count``, ``MaxRolls``) from the
    names of its lowercased spelling's role.

    ``templates._role`` reads a capitalised name as a class, and in Go a capital only means
    exported; types are ``type_identifier`` nodes, which no rename template takes. The
    window cache's ``"class"`` names are swapped for the role's names and put back after.
    """
    name, names = _text(node), win.cache["role_names"]
    if name[:1].isupper() and not name.isupper():
        role = templates._role(node, name[0].lower() + name[1:], win)
        win.cache["role_names"] = {**names, "class": names.get(role, names["any"])}
    try:
        yield
    finally:
        win.cache["role_names"] = names


def _assignment_sides(node: tree_sitter.Node) -> tuple[tree_sitter.Node, tree_sitter.Node] | None:
    """(name, value) of a one-name, one-value ``:=`` / ``=`` / var / const, else None."""
    if node.type in ("short_var_declaration", "assignment_statement"):
        op = node.child_by_field_name("operator")
        if node.type == "assignment_statement" and (op is None or op.type != "="):
            return None
        left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
        if left is None or right is None or left.named_child_count != 1 or right.named_child_count != 1:
            return None
        return left.named_children[0], right.named_children[0]
    names, value = node.children_by_field_name("name"), node.child_by_field_name("value")
    if len(names) != 1 or value is None or value.named_child_count != 1:
        return None
    return names[0], value.named_children[0]


def _fit(win: Window, node: tree_sitter.Node, old: str) -> str | None:
    """A replacement for an expression that fits its kind (a number for a number, ...), or None
    when no replacement keeps the code plausible (a call of unknown type, a selector)."""
    key = (win.key, node.start_point, "fit")
    kind, text = node.type, old.strip()
    if kind == "int_literal":
        return _pick_other(INT_TEXTS, text, *key)
    if kind == "float_literal":
        return _pick_other(FLOAT_TEXTS, text, *key)
    if kind in _STRING_NODES:  # always interpreted: a task quotes the text in backticks
        return '"' + _pick_other(STRING_TEXTS, text.strip('"`'), *key) + '"'
    if kind == "rune_literal":
        return _pick_other(RUNE_TEXTS, text, *key)
    if kind in ("true", "false"):
        return "false" if kind == "true" else "true"
    if kind == "identifier":
        return templates._new_name(win, text, node, *key)
    if kind in ("binary_expression", "unary_expression"):
        op = node.child_by_field_name("operator")
        op = op.type if op is not None else ""
        if op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||", "!"):
            return "false"
        return "0" if op in ("+", "-", "*", "/", "%") else None
    if kind == "call_expression" and _text(node.child_by_field_name("function")) in ("len", "cap"):
        return _pick_other(INT_TEXTS, text, *key)
    if kind == "composite_literal":
        kind_text, body = _text(node.child_by_field_name("type")), node.child_by_field_name("body")
        return f"{kind_text}{{}}" if kind_text and body is not None and body.named_child_count else None
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str | None:
    """Replacement contents for a delimited node, fitted to what is inside it now, or None."""
    key = (win.key, node.start_point, "ci")
    items = [a for a in node.named_children if a.type != "comment"]
    if node.type == "index_expression":
        items = [node.child_by_field_name("index")]
    if node.type in ("argument_list", "index_expression") and len(items) == 1 and items[0] is not None:
        fitted = _fit(win, items[0], inner)
        if fitted is not None:
            return fitted
    if node.type == "literal_value":
        if any(k.type == "keyed_element" for k in items):
            return _pick_other(KEYED_TEXTS, inner, *key)
        values = [k.named_children[0] for k in items if k.type == "literal_element" and k.named_child_count]
        if values and all(v.type in _STRING_NODES for v in values):
            return '"' + _pick_other(STRING_TEXTS, inner, *key) + '"'
        if values and all(v.type == "int_literal" for v in values):
            return _pick_other(INT_ELEMENT_TEXTS, inner, *key)
        return None
    if node.type == "block":
        return None  # gofmt pads a one-line body (`{ return x }`); ci{ would take the spaces too
    if node.type == "argument_list" and len(items) > 1 and items[0].type == "interpreted_string_literal":
        return '"' + _pick_other(STRING_TEXTS, inner, *key) + '"'  # a format call: Errorf("...", x)
    if node.type == "parameter_list":
        field = _field_name(node)
        if field == "receiver":
            return None
        return _pick_other(RESULT_TEXTS if field == "result" else PARAM_TEXTS, inner, *key)
    if node.type in _TEXTS:
        return _pick_other(_TEXTS[node.type], inner, *key)
    return None


def _field_name(node: tree_sitter.Node) -> str | None:
    """The field ``node`` fills in its parent (``receiver``, ``parameters``, ``result``), or None."""
    parent = node.parent
    if parent is None:
        return None
    for i, kid in enumerate(parent.children):
        if kid == node:
            return parent.field_name_for_child(i)
    return None


def _spans(
    siblings: list[tree_sitter.Node], lines: list[str], wrap: tuple[int, int] | None = None,
) -> list[tuple[int, int, tuple[int, int] | None]]:
    """Group sibling items into ``(start_row, end_row, wrap)`` spans of about SOFT_LINES lines.

    ``wrap`` is ``(header_row, closing_row)`` for the members of a long struct, group,
    switch or composite literal (see ``_body_items``); those two lines go into the window
    too, so the limit is two lines lower. Short spans are merged only with spans of the
    same nesting level. An item that starts on a row the previous item ends on joins that
    item's group, or is dropped when that item was split. Points are indexed
    (``start_point[0]``), as in ``js._spans``: the attribute getters crash py-tree-sitter
    0.26.0 past 256 lines.
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
    """The items inside a long function / statement / member list, and their wrap (see ``_spans``).

    A block's statements parse on their own (wrap None); the members of a ``_MEMBER_LISTS``
    container do not, so they come with the container's header and closing rows, or with
    no items when those lines hold anything else (the header must end in the opening
    bracket, the closing line hold only closing punctuation). The fallback looks at most
    three levels down (``type T struct {...}``, ``x := f(func() {...})``).
    """
    if node.type in _MEMBER_LISTS:
        wrap = _wrap(node, lines)
        return (node.named_children, wrap) if wrap is not None else ([], None)
    body = node if node.type == "block" else node.child_by_field_name("body")
    if body is not None and body.type == "block":
        return next((k.named_children for k in body.named_children if k.type == "statement_list"), []), None
    if depth >= 3:
        return [], None
    for child in node.named_children:
        items, wrap = _body_items(child, lines, depth + 1) if child.type != "comment" else ([], None)
        if items:
            return items, wrap
    return [], None


def _wrap(body: tree_sitter.Node, lines: list[str]) -> tuple[int, int] | None:
    """(header row, closing row) of a ``{ ... }`` / ``( ... )`` member list, or None (see ``_body_items``)."""
    opens = [k for k in body.children if k.type in ("{", "(")]
    closes = [k for k in body.children if k.type in ("}", ")")]
    if not opens or not closes:
        return None
    (orow, ocol), crow = opens[0].start_point, closes[-1].start_point[0]
    header, closer = lines[orow], lines[crow]
    if orow == crow or header[ocol + 1:].strip() or not _CLOSER_LINE.fullmatch(closer.strip()):
        return None
    return (orow, crow) if _indent(header) == _indent(closer) else None


def _make_window(
    lines: list[str], start: int, end: int, wrap: tuple[int, int] | None, source: dict[str, str],
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
    tree = parse("\n".join(chunk) + "\n")  # a type declaration at the end of input needs its newline
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with Go facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    Go template to run fills it, so later shared helpers (``_prose_rows``,
    ``_string_cells``, ``_delim_count``, ``_declared_roles``) find Go answers instead of
    Python ones. Go's own key: ``members`` (names used as a field, method or composite
    literal key anywhere in the window).
    """
    if win.cache.get("go"):
        return
    prose: set[int] = set()
    members: set[str] = set()
    raw_rows: set[int] = set()
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
                if n.type == "raw_string_literal":
                    raw_rows.update(range(r0 + 1, r1 + 1))
            if n.type == "comment" and not win.lines[r0][:n.start_point.column].strip():
                prose.update(range(r0, r1 + 1))
            q = _quote_of(n)
            if q is not None:
                delims[q] = delims.get(q, 0) + 1
            continue
        if n.type in ("(", "[", "{"):
            delims[n.type] = delims.get(n.type, 0) + 1
        elif n.type == "field_identifier" or (n.type == "identifier" and _is_member(n)):
            members.add(_text(n))
        stack.extend(n.children)
    win.cache.update({"go": True, "prose": prose, "raw_rows": raw_rows, "strings": cells, "delims": delims,
                      "members": members, "role_names": ROLE_NAMES, "types": _type_roles(win)})


def _quote_of(node: tree_sitter.Node) -> str | None:
    """The quote character of a string or rune literal node, else None."""
    return {"interpreted_string_literal": '"', "raw_string_literal": "`", "rune_literal": "'"}.get(node.type)


def _type_roles(win: Window) -> dict[str, str]:
    """Name -> role from declarations, parameters and struct fields: the declared type first
    (``[]string`` is "many", ``bool`` "flag", ...), else the initial value (a number is
    "count", a string "text", a slice or map literal "many"). Read by templates._role
    through the window cache."""
    roles: dict[str, str] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type in ("var_spec", "const_spec", "parameter_declaration", "field_declaration"):
            names, kind = n.children_by_field_name("name"), _text(n.child_by_field_name("type"))
            value = n.child_by_field_name("value")
        elif n.type == "short_var_declaration":
            left, right = n.child_by_field_name("left"), n.child_by_field_name("right")
            names, kind, value = (left.named_children if left is not None else []), "", right
        else:
            continue
        values = value.named_children if value is not None else []
        role = next((r for rx, r in _TYPE_ROLES if rx.search(kind)), None) if kind else None
        if role is None and len(values) == 1:
            role = _VALUE_ROLES.get(values[0].type)
            if values[0].type == "composite_literal" and re.match(r"\[|map\[", _text(values[0])):
                role = "many"
        for name in names if role is not None and len(names) == 1 else []:
            roles.setdefault(_text(name), role)
    return roles


def _span(win: Window, node: tree_sitter.Node) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node."""
    kids = node.children
    if node.start_point.row != node.end_point.row or len(kids) < 2:
        return None
    if node.type in _STRING_NODES:
        q = _quote_of(node)
        if kids[0].type != kids[-1].type or any(k.type == "escape_sequence" for k in kids):
            return None
        if node.parent is not None and node.parent.type == "import_spec":
            return None  # a package path is not text to edit
        row, oc, cc = node.start_point.row, kids[0].start_point.column, kids[-1].start_point.column
    elif node.type in ("index_expression", "slice_expression"):
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
    if win.cache["delims"].get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace, not in a nested pair or a string."""
    line = win.lines[row]
    if o in _QUOTES:
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        strings = win.cache["strings"]
        cols = [c for r, c in _depth0_positions(win, (row, oc), (row, cc), o, _PAIR[o]) if (r, c) not in strings]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _which_pair(win: Window, row: int, oc: int, inner: str) -> tuple[bool, bool]:
    """``templates._which_pair`` with gate 6's Go reading of the lines (``//`` comments)."""
    return templates._which_pair(win, row, oc, inner, lang=LANG.name)


def _line_move(win: Window, node: tree_sitter.Node, salt: str) -> tuple[int, int, bool] | None:
    """(row, distance, down) for moving/copying a one-line item among one-line siblings."""
    parent = node.parent
    row = node.start_point.row
    if parent is None or parent.type not in _LINE_PARENTS or node.end_point.row != row:
        return None
    if win.lines[row].strip() != _text(node).strip():
        return None  # the line holds more than this item (a trailing comment, a group header)
    rows = {s.start_point.row for s in parent.named_children
            if s.type != "comment" and s.end_point.row == s.start_point.row
            and win.lines[s.start_point.row].strip() == _text(s).strip()}
    options = []
    for k in (1, 2, 3):
        if all(row + i in rows for i in range(1, k + 1)):
            options.append((row, k, True))
        if all(row - i in rows for i in range(1, k + 1)):
            options.append((row, k, False))
    options = [o for o in options if win.lines[o[0] + (o[1] if o[2] else -o[1])].strip() != win.lines[row].strip()
               and "`" not in win.lines[o[0] + (o[1] if o[2] else -o[1])]]  # a task quotes that line in backticks
    return pick(options, win.key, node.start_point, salt) if options else None


def _statement_runs(win: Window, node: tree_sitter.Node, min_len: int) -> Iterator[list[tree_sitter.Node]]:
    """Runs of >= min_len one-line statements (``_RUN_ITEMS``) on consecutive rows at one indent, each alone on its line."""
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


def _shared_prefix(texts: list[str]) -> str | None:
    """A prefix every one of ``texts`` starts with: a fixed one (``defer ``) or one selector
    (``sb.``), else None."""
    fixed = next((p for p in _PREFIXES if all(t.startswith(p) for t in texts)), None)
    if fixed is not None:
        return fixed
    found = _SELECTOR_PREFIX.match(texts[0])
    if found is None or found.group()[:-1] in ("err", "ok"):
        return None
    return found.group() if all(t.startswith(found.group()) for t in texts) else None


def _prefix_runs(win: Window, rows: list[int], col: int) -> list[tuple[list[int], str]]:
    """Sub-runs of ``rows`` (consecutive statement rows at column ``col``) of EX_MIN_LINES to 8
    rows that share a prefix (``_shared_prefix``), longest first from the top, with the prefix."""
    out, i = [], 0
    while i <= len(rows) - templates.EX_MIN_LINES:
        for j in range(min(len(rows), i + 8), i + templates.EX_MIN_LINES - 1, -1):
            prefix = _shared_prefix([win.lines[r][col:] for r in rows[i:j]])
            if prefix is not None:
                out.append((rows[i:j], prefix))
                i = j
                break
        else:
            i += 1
    return out


def _prefix_draft(win: Window, skill: str, rows: list[int], col: int, prefix: str | None) -> Draft:
    """The x.normal draft for ``rows``: put back the shared ``prefix``, or comment them out with
    ``// `` when ``prefix`` is None."""
    n = len(rows)
    if prefix is not None:
        start = [ln[:col] + ln[col + len(prefix):] if r in rows else ln for r, ln in enumerate(win.lines)]
        target = [_range(r, col, r, col + min(len(prefix), len(start[r]) - col) - 1) for r in rows]
        task = f"Add `{prefix.strip()}` at the start of each of these {n} lines"
        return templates.normal_prefix(win, skill, rows, prefix, start, win.lines, task, target,
                                       ["statement", "normal", "insert"])
    expect = [ln[:col] + "// " + ln[col:] if r in rows else ln for r, ln in enumerate(win.lines)]
    target = [_range(r, col, r, len(win.lines[r]) - 1) for r in rows]
    task = f"Comment out these {n} lines: put `// ` at the start of each"
    return templates.normal_prefix(win, skill, rows, "// ", win.lines, expect, task, target, ["comment", "normal", "insert"])


def _in_function_body(node: tree_sitter.Node) -> bool:
    """True for a block that is, or sits inside, the body of a function, method or func literal."""
    up = node
    while up is not None and up.type != "source_file":
        if up.type == "block" and up.parent is not None and up.parent.type in _FUNCTIONS:
            return True
        up = up.parent
    return False
