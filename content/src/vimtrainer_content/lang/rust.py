"""Rust: tree-sitter-rust node types mapped to skills and templates, plus windowing.

Node type names come from tree-sitter-rust's node-types.json (grammar 0.24).

This module follows lang/js.py (read lang/cpp.py first), with the same names in the same
order. The differences:

- rustfmt code is already four-space indented, so ``windows`` does not re-indent.
- A function, ``impl`` / ``trait`` / ``mod`` body, struct, enum or ``match`` longer than a
  window is cut into windows of whole items kept between the header line and the closing
  line, as js.py does for classes: a tail expression or a match arm does not parse on its own.
- An attribute (``#[derive(...)]``) stays with the item below it, and no drill edits,
  moves or targets an attribute line.
- Strings are ``"..."`` and raw strings ``r"..."`` / ``r#"..."#``; both drill t.quote with
  ``ci"`` (a raw string only without a ``"`` or backslash inside). A format string with
  ``{}`` placeholders is left alone: the replacement would drop them. A char literal
  ``'x'`` is string text to the cache; a lifetime ``'a`` is code and never a quote.
- Macro arguments (``vec![...]``, ``println!(...)``) are a ``token_tree``: one node type for
  ``()``, ``[]`` and ``{}``, so its templates check that the delimiter fits the skill.
- Constants are SCREAMING_SNAKE_CASE already. The o.case and x.normal constant drills start
  from the name lowercased and ask for it uppercased again.
- ``gates.nested_in_same_pair`` reads lines, not the tree (``//`` comments, lifetimes
  skipped), so it can still see a pair as nested where the tree does not (a bracket in a
  raw string or a block comment); such a draft would fail gate 6 and is not made.

``generate`` registers the ``rust_*`` templates for the duration of one call, as
``cpp.generate`` does. The grammar-agnostic helpers are shared through lang/braces.py.
"""

import contextlib
import functools
import re
import textwrap
from collections.abc import Iterator
from typing import Final

import tree_sitter
import tree_sitter_rust

from vimtrainer_content import gates, registers, snippets, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, Rust column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    **dict.fromkeys(registers.SKILLS, 1.0),
    "m.match": 1.5, "t.brace": 1.5, "n.unmatched": 1.5, "t.paren": 1.5, "t.bracket": 1.2, "t.quote": 1.2,
    "t.angle": 1.5, "o.indent": 0.8, "m.find": 1.5, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0,
    "m.rel": 1.0, "o.change": 1.0, "o.case": 1.0, "x.copymove": 1.0, "x.normal": 1.0,
}
TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.angle", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove", "x.normal",
    *registers.SKILLS,
)

STRING_TEXTS: Final = ("not found", "invalid input", "out of range", "unknown", "skipped", "empty", "error: ")
ARG_TEXTS: Final = ("items.len()", "key, count", "0", "count + 1", "&name")
PARAM_TEXTS: Final = ("count: usize", "name: &str", "items: &[u32]", "n: u64")
EXPR_TEXTS: Final = ("count + 1", "n - 1", "total * 2", "x % 10")
TUPLE_TEXTS: Final = ("0, 0", "count, total", "x + 1, y")
TUPLE_TYPE_TEXTS: Final = ("u32, u32", "usize, char", "String, i64")
SUBSCRIPT_TEXTS: Final = ("0", "i + 1", "index", "n - 1", "1..")
ARRAY_TEXTS: Final = ("0; 4", "1, 2, 3", "0, 0")
ARRAY_TYPE_TEXTS: Final = ("u8; 4", "char; 26", "u32; 10")
STRUCT_TEXTS: Final = ("count: 0", "name, count", "..Default::default()")
FIELD_TEXTS: Final = ("count: u32", "name: String")
USE_TEXTS: Final = ("HashMap, HashSet", "Display, Formatter", "self, Write")
ANGLE_TEXTS: Final = ("u32", "String", "usize", "i64", "char", "bool", "T", "&str")
ANGLE_PAIR_TEXTS: Final = ("String, usize", "char, u32", "K, V", "&str, i32")
TPARAM_TEXTS: Final = ("T", "T: Clone", "K, V", "T: Display")
FORMAT_TEXTS: Final = ('"done"', '"{}", count', '"{:?}", items')
MACRO_ARG_TEXTS: Final = ("count, 0", "items.len(), 3", "a, b")
BLOCK_TEXTS: Final = ("count + 1", "None", "Vec::new()")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")
# Rename targets by role (see templates.ROLE_NAMES), snake_case like the code; _prime puts
# this list in the window cache.
ROLE_NAMES: Final = {
    "many": ("items", "values"),
    "count": ("count", "total", "size"),
    "index": ("index", "pos"),
    "text": ("name", "label"),
    "flag": ("is_valid", "is_ready", "has_value"),
    "call": ("process", "compute", "update"),
    "class": ("record", "item", "handler"),
    "any": ("value", "result"),
}
# Declared type -> role, first match wins (_type_roles).
_TYPE_ROLES: Final = (
    (re.compile(r"\b(Vec|VecDeque|HashMap|HashSet|BTreeMap|BTreeSet)\b|^&?(mut )?\["), "many"),
    (re.compile(r"\bbool\b"), "flag"),
    (re.compile(r"\b(String|str|char)\b"), "text"),
    (re.compile(r"\b(usize|isize|u8|u16|u32|u64|u128|i8|i16|i32|i64|i128)\b"), "count"),
)
_VALUE_ROLES: Final = {
    "array_expression": "many", "integer_literal": "count", "string_literal": "text", "boolean_literal": "flag",
}
# A call's replacement by what the call builds (_fit); anything else becomes _DEFAULT, or in
# change_rhs the value the assigned name's role suggests (_ROLE_VALUES).
_DEFAULT: Final = "Default::default()"
_ROLE_VALUES: Final = {"count": "0", "index": "0", "many": "Vec::new()", "text": "String::new()", "flag": "false"}
_CALL_FITS: Final = (
    (re.compile(r"\.(len|count)\(\)$"), "0"),
    (re.compile(r"\.is_\w+\([^()]*\)$"), "false"),
    (re.compile(r"^(Vec::|vec!)|Vec<"), "Vec::new()"),
    (re.compile(r"^String::|\.to_string\(\)$|^format!|\.to_owned\(\)$"), "String::new()"),
    (re.compile(r"^HashMap::|HashMap<"), "HashMap::new()"),
    (re.compile(r"^HashSet::|HashSet<"), "HashSet::new()"),
)
_MANY_CALL: Final = re.compile(r"(Vec|VecDeque|HashMap|HashSet|BTreeMap|BTreeSet)::|^vec!")

_NOUNS: Final = {
    "string_literal": "string", "raw_string_literal": "string", "arguments": "argument list",
    "parameters": "parameter list", "parenthesized_expression": "parenthesised expression",
    "tuple_expression": "tuple", "tuple_type": "tuple type", "index_expression": "index",
    "array_expression": "array", "array_type": "array type", "block": "block",
    "field_initializer_list": "struct literal", "field_declaration_list": "struct body", "use_list": "use list",
    "declaration_list": "body", "match_block": "match body", "enum_variant_list": "enum body",
    "type_arguments": "type argument list", "type_parameters": "type parameter list",
}
_TEXTS: Final = {
    "string_literal": STRING_TEXTS, "raw_string_literal": STRING_TEXTS, "arguments": ARG_TEXTS,
    "parameters": PARAM_TEXTS, "parenthesized_expression": EXPR_TEXTS, "tuple_expression": TUPLE_TEXTS,
    "tuple_type": TUPLE_TYPE_TEXTS, "index_expression": SUBSCRIPT_TEXTS, "array_expression": ARRAY_TEXTS,
    "array_type": ARRAY_TYPE_TEXTS, "field_initializer_list": STRUCT_TEXTS, "field_declaration_list": FIELD_TEXTS,
    "use_list": USE_TEXTS, "type_arguments": ANGLE_TEXTS, "type_parameters": TPARAM_TEXTS,
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", "<": ">", '"': '"'}
_DELIM_NAMES: Final = {"(": "parentheses", "[": "square brackets", "{": "braces", "<": "angle brackets", '"': "quotes"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), "<": (">",), '"': ()}
# The delimiter each text-object skill drills; a token_tree serves t.paren and t.bracket.
_SKILL_DELIM: Final = {"t.paren": "(", "t.bracket": "[", "t.brace": "{", "t.angle": "<", "t.quote": '"'}
_STRINGS: Final = frozenset({"string_literal", "raw_string_literal", "char_literal", "line_comment", "block_comment"})
_COMMENTS: Final = frozenset({"line_comment", "block_comment"})
_ATTRIBUTES: Final = frozenset({"attribute_item", "inner_attribute_item"})
_ANGLES: Final = frozenset({"type_arguments", "type_parameters"})
_LINE_PARENTS: Final = frozenset({"source_file", "block", "declaration_list", "field_declaration_list"})
# Items whose line ends in a comma that is not part of the node (rustfmt writes it on every item).
_COMMA_LISTS: Final = frozenset({"field_declaration_list", "enum_variant_list"})
# Containers whose items do not parse on their own (or lose their context): a window of them
# keeps the container's header and closing lines (_body_items).
_MEMBER_LISTS: Final = frozenset({
    "block", "declaration_list", "field_declaration_list", "enum_variant_list", "match_block",
})
_CLOSER_LINE: Final = re.compile(r"\}[)\];,]*")
# One-line items a line move, a `:norm` range or a neighbour row may be.
_RUN_ITEMS: Final = frozenset({
    "let_declaration", "expression_statement", "field_declaration", "use_declaration", "const_item", "static_item",
})
_PREFIXES: Final = ("pub(crate) ", "let mut ", "pub const ", "pub ", "const ", "let ", "self.", "use ")
_CONSTS: Final = frozenset({"const_item", "static_item"})
_SCREAMING: Final = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z][A-Z0-9]{3,}")
# Identifiers that name a path segment, a macro or a lifetime: renaming one is not an edit.
_PATHS: Final = frozenset({
    "scoped_identifier", "scoped_type_identifier", "scoped_use_list", "use_list", "use_declaration",
    "use_as_clause", "use_wildcard", "lifetime", "macro_invocation",
})
_FUNCTIONS: Final = frozenset({"function_item", "closure_expression"})
_KEYWORDS: Final = frozenset("""
    as async await break const continue crate dyn else enum extern false fn for if impl in let loop match mod
    move mut pub ref return self Self static struct super trait true type unsafe use where while union
    bool char str u8 u16 u32 u64 u128 usize i8 i16 i32 i64 i128 isize f32 f64
    String Vec Option Some None Result Ok Err Box Rc RefCell Cell Arc HashMap HashSet BTreeMap BTreeSet VecDeque
    Default Debug Display Clone Copy PartialEq Eq PartialOrd Ord Hash Iterator IntoIterator From Into fmt std
    println print eprintln format write writeln vec panic assert assert_eq assert_ne unreachable todo matches
    len push pop iter into_iter map filter fold collect unwrap expect clone to_string as_str chars bytes sum
    new default insert remove get contains is_empty first last next rev zip enumerate count min max abs
""".split())

_PAREN = (
    Use("t.paren", ("rust_change_inner", "rust_delete_inner")),
    Use("m.match", ("rust_jump_match",)),
    Use("n.unmatched", ("rust_jump_block_end",)),
)
_BRACKET = (Use("t.bracket", ("rust_change_inner", "rust_delete_inner")), Use("m.match", ("rust_jump_match",)))
_ANGLE = (Use("t.angle", ("rust_change_inner", "rust_delete_inner")),)
_IDENT = (
    Use("t.word", ("rust_rename_here",)),
    Use("x.subst", ("rust_rename_all_subst",)),
)
_LINE = (Use("x.copymove", ("rust_move_line", "rust_copy_line")),)
_DELETE = (Use("o.delete", ("rust_delete_lines",)),)
_NORMAL = (Use("x.normal", ("rust_prefix_each_line", "rust_upper_constants")),)
_ASSIGN = (*_LINE, Use("o.change", ("rust_change_rhs",)))
_BODY = (
    Use("t.brace", ("rust_delete_block",)), Use("m.match", ("rust_jump_match",)),
    Use("o.indent", ("rust_indent_block",)),
)

LANG = Language(
    name="rust",
    short="rs",
    grammar="rust",
    nodes={
        "string_literal": (
            Use("t.quote", ("rust_change_inner", "rust_delete_inner")), Use("o.case", ("rust_upper_inner",)),
        ),
        "raw_string_literal": (Use("t.quote", ("rust_change_inner", "rust_delete_inner")),),
        "arguments": (*_PAREN, Use("o.change", ("rust_change_nth_arg",))),
        "parameters": _PAREN,
        "parenthesized_expression": _PAREN,
        "tuple_expression": _PAREN,
        "tuple_type": (Use("t.paren", ("rust_change_inner", "rust_delete_inner")),),
        # Macro arguments: `vec![...]` drills t.bracket, `println!(...)` t.paren (_SKILL_DELIM).
        "token_tree": (
            Use("t.paren", ("rust_change_inner", "rust_delete_inner")),
            Use("t.bracket", ("rust_change_inner", "rust_delete_inner")),
            Use("m.match", ("rust_jump_match",)),
            Use("n.unmatched", ("rust_jump_block_end",)),
        ),
        "block": (
            Use("t.brace", ("rust_change_inner", "rust_delete_inner", "rust_delete_block")),
            Use("m.match", ("rust_jump_match",)),
            Use("n.unmatched", ("rust_jump_block_end",)),
            Use("o.indent", ("rust_indent_block",)),
            *_NORMAL,
        ),
        "source_file": _NORMAL,
        "declaration_list": (*_BODY, *_NORMAL),
        "field_declaration_list": (
            Use("t.brace", ("rust_change_inner", "rust_delete_inner")), *_BODY, *_NORMAL,
        ),
        "enum_variant_list": _BODY,
        "match_block": (*_BODY, Use("n.unmatched", ("rust_jump_block_end",))),
        "field_initializer_list": (
            Use("t.brace", ("rust_change_inner", "rust_delete_inner", "rust_delete_block")),
            Use("m.match", ("rust_jump_match",)),
            Use("n.unmatched", ("rust_jump_block_end",)),
        ),
        "use_list": (Use("t.brace", ("rust_change_inner", "rust_delete_inner")),),
        "array_expression": _BRACKET,
        # index_expression's `[...]` is not a node of its own; _span finds the brackets.
        "index_expression": (Use("t.bracket", ("rust_change_inner", "rust_delete_inner")),),
        "array_type": (Use("t.bracket", ("rust_change_inner",)),),
        "type_arguments": _ANGLE,
        "type_parameters": _ANGLE,
        "line_comment": (Use("o.delete", ("rust_delete_trailing_comment",)),),
        "block_comment": (Use("o.delete", ("rust_delete_trailing_comment",)),),
        "function_item": _DELETE,
        "impl_item": _DELETE,
        "struct_item": _DELETE,
        "enum_item": _DELETE,
        "if_expression": _DELETE,
        "for_expression": _DELETE,
        "while_expression": _DELETE,
        "loop_expression": _DELETE,
        "match_expression": _DELETE,
        "identifier": _IDENT,
        "field_identifier": _IDENT,
        "field_expression": (Use("m.find", ("rust_find_member",)),),
        "use_declaration": _LINE,
        "field_declaration": _LINE,
        "const_item": (*_LINE, Use("o.case", ("rust_upper_word",))),
        "static_item": (*_LINE, Use("o.case", ("rust_upper_word",))),
        "expression_statement": _ASSIGN,
        "let_declaration": _ASSIGN,
    },
    line_templates=(Use("m.rel", ("rust_goto_line_rel",)), Use("m.find", ("rust_find_char",)), *registers.USES),
    find_targets=("(", ")", "{", "}", "[", "]", ";", ",", "=", ".", "->", "=>", "::", ":"),
    comment_leader="//",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for Rust."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_rust.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse Rust source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a Rust source file into parseable 8-40 line windows (see ``snippets.windows``).

    Functions, ``impl`` / ``trait`` / ``mod`` blocks, structs, enums and ``match``
    expressions longer than 40 lines are split by recursing into their bodies; a window of
    their items keeps the header and closing lines around them. An attribute goes into the
    window of the item below it. Comments matching the licence/author pattern break a window
    and are left out.
    """
    lines = text.splitlines()
    tree = parse("\n".join(lines))  # keep the tree alive while its nodes are walked
    out = []
    for start, end, wrap in _spans(tree.root_node.named_children, lines):
        win = _make_window(lines, start, end, wrap, source)
        if win is not None:
            out.append(win)
    return out


def generate(win: Window, lang: Language = LANG) -> list[Draft]:
    """``templates.generate`` for a Rust window, with the ``rust_*`` templates registered.

    The shared registries (``templates.NODE_TEMPLATES`` / ``LINE_TEMPLATES``) only know the
    Python templates, and ``LANG``'s ``Use`` entries name ``rust_*`` ones. They are added for
    the duration of the call and removed again, so the Python registry stays as it was.
    """
    with registered():
        return templates.generate(win, lang)


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``rust_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(RUST_NODE_TEMPLATES, RUST_LINE_TEMPLATES)


def node_frequency(texts: list[str]) -> dict[str, object]:
    """``snippets.node_frequency`` for Rust (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, parse)


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>`` on a single-line string, bracket, brace or angle pair."""
    _prime(win)
    span = _span(win, node, skill)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col, which = _cursor_inside(win, node, row, oc, cc, o), _which_pair(win, node, row, oc, inner)
    if col is None or which is None:
        return
    text = _inner_text(win, node, inner)
    c, noun = _PAIR[o], _noun(node)
    draft = Draft(
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
    if _worth_it(draft, lang):
        yield draft


def delete_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``di{delim}``: empty a single-line string, bracket, brace or angle pair."""
    _prime(win)
    span = _span(win, node, skill)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col, which = _cursor_inside(win, node, row, oc, cc, o), _which_pair(win, node, row, oc, inner)
    if col is None or which is None:
        return
    c, noun, delims = _PAIR[o], _noun(node), _DELIM_NAMES[o]
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
    if pair is None or pair[0][2] != "{" or not _usable(win, node):
        return
    (orow, ocol, _), (crow, ccol, _) = pair
    lines = win.lines
    n = crow - orow - 1
    if not 4 <= n <= 15 or lines[orow][ocol + 1:].strip() or lines[crow][:ccol].strip():
        return
    if _delims(win).get("{", 0) < 2:
        return
    strings = win.cache["strings"]
    cols = [p for p in _depth0_positions(win, (orow, ocol), (crow, ccol), "{") if p not in strings]
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
    span = _span(win, node, "t.quote")
    if span is None:
        return
    row, oc, cc, q = span
    inner = win.lines[row][oc + 1:cc]
    if not (4 <= len(inner) <= 30 and re.fullmatch(r"[a-z][a-z ,.:!?_-]*", inner)):
        return
    col, which = _cursor_inside(win, node, row, oc, cc, q), _which_pair(win, node, row, oc, inner)
    if col is None or which is None:
        return
    draft = Draft(
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
    if _worth_it(draft, lang):
        yield draft


def upper_word(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``gUiw``: a ``const`` / ``static`` whose name was lowercased; uppercase it again."""
    _prime(win)
    name = _const_name(win, node)
    if name is None or templates._seen(win, "case", _text(name)):
        return
    old = _text(name)
    new, row, c0 = old.lower(), name.start_point.row, name.start_point.column
    lines = _replace(win.lines, row, c0, c0 + len(old), new)
    col = c0 + pick(range(1, len(old)), win.key, node.start_point, "case")
    yield Draft(
        template="upper_word", skill=skill, kind="edit",
        task=f"Make `{new}` a constant name: uppercase it to `{old}`",
        lines=lines, cursor=[row + 1, col], expect={"lines": win.lines},
        variants=["gUiw", "viwU"], alternates=["g~iw", "gUaw"],
        idioms=["bgUe", "bgUw", "gUe", "gUE", "bgUE", f"ciw{old}<Esc>"],
        typed=0, params={"word": new}, target=[_range(row, c0, row, c0 + len(old) - 1)], window=win,
        tags=["identifier", "case"],
        hints=[
            {"trigger": "^~|~~", "text": "gUiw changes the whole word in one command; ~ flips one character."},
            {"trigger": "^(b|0|\\^)", "text": "iw works from anywhere in the word; no need to move to its start."},
            {"trigger": "^c|^s|^x", "text": "gU changes case without retyping the word."},
            {"trigger": None, "text": "gUiw: uppercase inner word."},
        ],
    )


def change_nth_arg(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``{k}f,wct,X<Esc>``: change the n-th argument of a single-line call from the call start."""
    _prime(win)
    call = node.parent
    if call is None or call.type != "call_expression" or node.start_point.row != node.end_point.row:
        return
    row = node.start_point.row
    if call.start_point.row != row or not _usable(win, node):
        return
    args = [a for a in node.named_children if a.type not in _COMMENTS]
    if len(args) < 2:
        return
    n = pick(range(2, len(args) + 1), win.key, node.start_point, "nth")
    arg = args[n - 1]
    line, a0, a1 = win.lines[row], arg.start_point.column, arg.end_point.column
    value = line[a0:a1]
    if not re.fullmatch(r"[\w.+\-*/ '\":&]+", value) or a1 >= len(line) or line[a1] not in ",)":
        return
    cursor, d = call.start_point.column, line[a1]
    k = line[cursor:a0].count(",")
    if k < 1:
        return
    text = _fit(win, arg, value)
    if text is None or text == _DEFAULT:
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
    """``C X;<Esc>`` / ``ct;X<Esc>``: replace the value of a one-line ``let x = ...;`` or
    ``x = ...;`` (``x += ...;``), cursor on it."""
    _prime(win)
    if node.start_point.row != node.end_point.row or not _usable(win, node):
        return
    if node.type == "let_declaration":
        if node.child_by_field_name("alternative") is not None:
            return  # let-else
        left, right = node.child_by_field_name("pattern"), node.child_by_field_name("value")
    else:
        kids = node.named_children
        if len(kids) != 1 or kids[0].type not in ("assignment_expression", "compound_assignment_expr"):
            return
        left, right = kids[0].child_by_field_name("left"), kids[0].child_by_field_name("right")
    if left is None or right is None or left.type not in ("identifier", "field_expression", "index_expression"):
        return
    if right.type in ("closure_expression", "block", "if_expression", "match_expression"):
        return
    row, r0, r1 = right.start_point.row, right.start_point.column, right.end_point.column
    line = win.lines[row]
    old, semi = line[r0:r1], line[r1:]
    if semi != ";" or len(old) < 6 or ";" in old or node.parent is None or node.parent.type not in _LINE_PARENTS:
        return
    text = _fit(win, right, old)
    if text == _DEFAULT and left.type == "identifier":
        text = _ROLE_VALUES.get(templates._role(left, _text(left), win), _DEFAULT)
    if text is None:
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
    if min(_indent(lines[r]) for r in rows) != base + 4 or any(r in win.cache["multiline"] for r in rows):
        return
    under = pick((True, False), win.key, node.start_point, "indent")
    shifted = [(ln[4:] if under else "    " + ln) if r in rows else ln for r, ln in enumerate(lines)]
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
    """``{k}f.``: from the first non-blank, jump to the ``.`` before a field or method."""
    _prime(win)
    op = next((c for c in node.children if c.type == "."), None)
    field = node.child_by_field_name("field")
    if op is None or field is None or op.start_point.row != field.end_point.row:
        return
    row, col = op.start_point.row, op.start_point.column
    line = win.lines[row]
    start = _indent(line)
    if row in win.cache["prose"] or line[start:start + 1] in ("", "/", "*", "#"):
        return
    name = _text(field)
    k = line.count(".", start + 1, col + 1)
    if not 1 <= k <= 3 or col - start < 3 * (2 if k == 1 else 3) + 1 or line.count(f".{name}") != 1:
        return
    if any((row, c) in win.cache["strings"] for c in range(start, col)):
        return  # a `.` inside a string before it would be counted by f too
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
    """``templates.jump_match`` (grammar-agnostic) on a primed window, attributes left alone."""
    _prime(win)
    if _usable(win, node):
        yield from templates.jump_match(win, node, skill, lang)


def jump_block_end(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.jump_block_end`` with Rust strings and comments excluded as start positions."""
    _prime(win)
    if not _usable(win, node):
        return
    for draft in templates.jump_block_end(win, node, skill, lang):
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_noun(node)} around the cursor", draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f/D``: ``templates.delete_trailing_comment`` for single-line ``//`` and ``/* */`` comments.

    Comments after a bare ``}`` or ``});`` are skipped: retyping the code is cheaper.
    """
    _prime(win)
    row = node.start_point.row
    if row != _end_row(node) or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    if (node.end_point.row == row and win.lines[row][node.end_point.column:].strip()) or row in win.cache["attrs"]:
        return  # a mid-line `/* */` with code after it is not a trailing comment
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` with Rust task text (items named, statements by keyword).

    An item with an attribute right above it is skipped: deleting it would leave the
    attribute on whatever follows.
    """
    _prime(win)
    target = node.parent if node.parent is not None and node.parent.type == "expression_statement" else node
    end_row, end_col = target.end_point.row, target.end_point.column
    if win.lines[end_row][end_col:].strip() not in ("", ";", ","):
        return
    prev = target.prev_named_sibling
    if prev is not None and prev.type in _ATTRIBUTES and prev.end_point.row == target.start_point.row - 1:
        return
    name = _text(node.child_by_field_name("name"))
    what = {
        "if_expression": "this `if` expression", "for_expression": "this `for` loop",
        "while_expression": "this `while` loop", "loop_expression": "this `loop`",
        "match_expression": "this `match` expression", "impl_item": "this `impl` block",
        "struct_item": f"the struct `{name}`", "enum_item": f"the enum `{name}`",
    }.get(node.type, "this statement")
    if node.type == "function_item":
        kind = "method" if node.parent is not None and node.parent.type == "declaration_list" else "function"
        what = f"the {kind} `{name}`" if name and len(name) <= 40 else f"this {kind}"
    for draft in templates.delete_lines(win, target, skill, lang):
        n = target.end_point.row - target.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here`` on a primed window; path segments, macro names, lifetimes and
    attribute contents are skipped (``self.x`` fields are skipped there)."""
    _prime(win)
    if _renamable(win, node):
        yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst`` on a primed window, for names never used as a path
    segment, macro name, lifetime, field or method and never on an attribute line."""
    _prime(win)
    if not _renamable(win, node) or _text(node) in win.cache["members"]:
        return
    attrs = win.cache["attrs"]
    for draft in templates.rename_all_subst(win, node, skill, lang):
        if not any(t["start"][0] - 1 in attrs for t in draft.target):
            yield draft


def prefix_each_line(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``V{n}j:norm I{prefix}<CR>`` over 3-8 consecutive one-line items (x.normal): put back a
    prefix they all share (``let ``, ``pub ``, ``self.``, ...), or, when they share none and they
    are statements in a function body, comment them out with ``// ``."""
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
            continue  # commenting out struct fields or top-level items is not an edit anyone drills
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
    """``V{n}j:norm f:bgUiw<CR>`` over 3+ consecutive one-line ``const`` / ``static`` items whose
    names were lowercased: uppercase them again (x.normal)."""
    _prime(win)
    for named in _const_runs(win, node):
        rows, names = [r for r, _ in named[:8]], [n for _, n in named[:8]]
        if templates._seen(win, "constants", str(rows[0])):
            continue
        k = len(rows) - 1
        down = f"{k}j" if k > 1 else "j"
        go = "f:b"
        start = list(win.lines)
        for r, name in zip(rows, names, strict=True):
            c0, c1 = name.start_point.column, name.end_point.column
            start[r] = start[r][:c0] + start[r][c0:c1].lower() + start[r][c1:]
        yield Draft(
            template="upper_constants", skill=skill, kind="ex",
            task=f"Uppercase the names of these {k + 1} constants",
            lines=start, cursor=[rows[0] + 1, _indent(start[rows[0]])], expect={"lines": win.lines},
            variants=[f"V{down}:norm {go}gUiw<CR>", f"V{down}:norm {go}gUe<CR>", f":.,+{k}norm {go}gUiw<CR>",
                      f":{rows[0] + 1},{rows[-1] + 1}norm {go}gUiw<CR>"],
            alternates=[f":.,+{k}normal {go}gUiw<CR>", f"V{down}:normal {go}gUiw<CR>"],
            idioms=[f"V{down}:s/\\<\\l\\w*\\>/\\U&/<CR>", "gUiwj." + "j." * (k - 1)],
            params={"n": k + 1},
            target=[_range(r, n.start_point.column, r, n.end_point.column - 1) for r, n in zip(rows, names, strict=True)],
            window=win, tags=[node.type, "normal", "case"],
            hints=[
                {"trigger": "^gU|j\\.", "text": f":norm runs {go}gUiw on every line of the range; V{down} selects the {k + 1} lines."},
                {"trigger": ":[^n]*s/", "text": "A substitute works too, but this drill is about :normal."},
                {"trigger": None, "text": f"V{down}:norm {go}gUiw<CR>: select the lines, then run {go}gUiw on each."},
            ],
        )


# Line templates ===================================================================================


def goto_line_rel(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.goto_line_rel`` with comment-only and attribute lines excluded as start and target."""
    _prime(win)
    yield from templates.goto_line_rel(win, skill, lang)


def find_char(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``{n}fX``: jump to the n-th X (``->`` / ``=>`` / ``::`` included: ``f-``, ``f=``, ``f:``) on the line."""
    _prime(win)
    rows = sorted(range(len(win.lines)), key=lambda r: snippets.stable_hash(win.key, r, "find"))
    prose = win.cache["prose"]
    made = 0
    for row in rows:
        line = win.lines[row]
        start = _indent(line)
        if row in prose or line[start:start + 1] in ("", '"', "'", "/", "*", "#"):
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


RUST_NODE_TEMPLATES: Final = {
    "rust_change_inner": change_inner, "rust_delete_inner": delete_inner, "rust_delete_block": delete_block,
    "rust_upper_inner": upper_inner, "rust_upper_word": upper_word, "rust_change_nth_arg": change_nth_arg,
    "rust_change_rhs": change_rhs, "rust_indent_block": indent_block, "rust_move_line": move_line,
    "rust_copy_line": copy_line, "rust_find_member": find_member, "rust_jump_match": jump_match,
    "rust_jump_block_end": jump_block_end, "rust_delete_trailing_comment": delete_trailing_comment,
    "rust_delete_lines": delete_lines, "rust_rename_here": rename_here, "rust_rename_all_subst": rename_all_subst,
    "rust_prefix_each_line": prefix_each_line, "rust_upper_constants": upper_constants,
}
RUST_LINE_TEMPLATES: Final = {"rust_goto_line_rel": goto_line_rel, "rust_find_char": find_char}


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
_worth_it = braces.worth_it
_merge_short = braces.merge_short
_occurrences = braces.occurrences


def _noun(node: tree_sitter.Node) -> str:
    """How a task names a delimited node: macro arguments by their macro (``vec!``)."""
    if node.type == "token_tree" and node.parent is not None and node.parent.type == "macro_invocation":
        return f"`{_text(node.parent.child_by_field_name('macro'))}!` macro call"
    if node.type == "declaration_list" and node.parent is not None:
        return {"impl_item": "impl body", "trait_item": "trait body", "mod_item": "module body"}.get(node.parent.type, "body")
    return _NOUNS.get(node.type, "bracket pair")


def _header(win: Window, node: tree_sitter.Node, orow: int) -> str:
    """First line of the item or expression that owns a ``{`` block (the signature, not its last line)."""
    parent = node.parent
    row = parent.start_point.row if parent is not None and parent.type != "source_file" else orow
    return win.lines[min(row, orow)].strip()


def _fit(win: Window, node: tree_sitter.Node, old: str) -> str | None:
    """A replacement for an expression that fits its kind (a number for a number, ...), or None."""
    key = (win.key, node.start_point, "fit")
    kind, text = node.type, old.strip()
    if kind == "integer_literal":
        return _pick_other(INT_TEXTS, text, *key)
    if kind == "string_literal":
        return '"' + _pick_other(STRING_TEXTS, text.strip('"'), *key) + '"'
    if kind == "boolean_literal":
        return "false" if text == "true" else "true"
    if kind == "char_literal":
        return _pick_other(("' '", "'0'", "'a'", "'-'"), text, *key)
    if kind == "identifier":
        return templates._new_name(win, text, node, *key)
    if kind == "reference_expression":
        value = node.child_by_field_name("value")
        if value is not None and value.type == "identifier" and text.startswith("&") and "mut" not in text:
            new = templates._new_name(win, _text(value), value, *key)
            return "&" + new if new is not None else None
        return None
    if kind in ("binary_expression", "unary_expression"):
        op = next((c.type for c in node.children if not c.is_named), "")
        return "false" if op in ("==", "!=", "<", ">", "<=", ">=", "&&", "||", "!") else "0"
    if kind in ("call_expression", "field_expression", "macro_invocation", "index_expression", "struct_expression",
                "scoped_identifier", "try_expression", "type_cast_expression"):
        return next((new for rx, new in _CALL_FITS if rx.search(text)), _DEFAULT)
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str:
    """Replacement contents for a delimited node, fitted to what is inside it now."""
    key = (win.key, node.start_point, "ci")
    kind = node.type
    items = [a for a in node.named_children if a.type not in _COMMENTS]
    if kind == "index_expression":
        items = items[-1:]
    if kind in ("arguments", "index_expression") and len(items) == 1:
        fitted = _fit(win, items[0], inner)
        if fitted is not None and fitted != _DEFAULT:
            return fitted
    if kind == "token_tree":
        o = node.children[0].type
        texts = ARRAY_TEXTS if o == "[" else FORMAT_TEXTS if inner.startswith('"') else MACRO_ARG_TEXTS
        return _pick_other(texts, inner, *key)
    if kind == "block":
        return "return None;" if inner.strip().startswith("return") else _pick_other(BLOCK_TEXTS, inner, *key)
    if kind == "parameters" and items and items[0].type == "self_parameter":
        return _text(items[0]) + ", " + _pick_other(PARAM_TEXTS, inner, *key)
    if kind == "type_arguments" and "," in inner:
        return _pick_other(ANGLE_PAIR_TEXTS, inner, *key)
    if kind == "array_expression" and inner.startswith('"'):
        return '"' + _pick_other(STRING_TEXTS, inner, *key) + '"'
    return _pick_other(_TEXTS[kind], inner, *key)


def _delims(win: Window) -> dict[str, int]:
    _prime(win)
    return win.cache["delims"]


def _spans(
    siblings: list[tree_sitter.Node], lines: list[str], wrap: tuple[int, int] | None = None,
) -> list[tuple[int, int, tuple[int, int] | None]]:
    """Group sibling items into ``(start_row, end_row, wrap)`` spans of about SOFT_LINES lines.

    ``wrap`` is ``(header_row, closing_row)`` for the items of a long function, impl, struct,
    enum or match (see ``_body_items``); those two lines go into the window too, so the limit
    is two lines lower. An attribute starts the span of the item below it. Short spans are
    merged only with spans of the same nesting level: a merge across a recursed-into body
    would swallow its closing ``}``. An item that starts on a row the previous item ends on
    joins that item's group, or is dropped when that item was split. Points are indexed
    (``start_point[0]``), as in ``cpp._end_row``: the attribute getters crash py-tree-sitter
    0.26.0 past 256 lines.
    """
    limit = snippets.MAX_LINES - (2 if wrap else 0)
    out: list[tuple[int, int, tuple[int, int] | None]] = []
    run: list[tuple[int, int]] = []
    group: list[int] | None = None
    prev_end = -1
    lead: int | None = None  # first row of the attributes above the next item
    for node in siblings:
        start, end = node.start_point[0], _end_row(node)
        if start <= prev_end:
            if group is not None:
                group[1] = max(group[1], end)
            prev_end = max(prev_end, end)
            continue
        prev_end = end
        if node.type in _COMMENTS and snippets._HEADER.search(lines[start]):
            if group:
                run.append(tuple(group))
            group, lead = None, None
            continue
        if node.type in _ATTRIBUTES:
            lead = start if lead is None else lead
            continue
        start, lead = (lead if lead is not None else start), None
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
    """The items inside a long function / impl / struct / enum / match, and their wrap (see ``_spans``).

    The items come with the container's header and closing rows when those lines hold
    nothing else (the header must be one line ending in ``{``, the closing line only ``}``
    and punctuation). A function body's statements also come without them (they parse on
    their own unless the last one is a tail expression); the other containers' items then
    come not at all. The fallback looks at most three levels down
    (``let x = match y {...};``).
    """
    body = node if node.type in _MEMBER_LISTS else node.child_by_field_name("body")
    if body is not None and body.type in _MEMBER_LISTS:
        wrap = _wrap(body, lines)
        if wrap is not None or body.type == "block":
            return body.named_children, wrap
        return [], None
    if depth >= 3:
        return [], None
    for child in node.named_children:
        items, wrap = _body_items(child, lines, depth + 1) if child.type not in _COMMENTS else ([], None)
        if items:
            return items, wrap
    return [], None


def _wrap(body: tree_sitter.Node, lines: list[str]) -> tuple[int, int] | None:
    """(header row, closing row) of a ``{ ... }`` body, or None (see ``_body_items``). The owner
    must start on the header row: the last line of a multi-line signature does not parse alone."""
    (orow, ocol), (crow, _) = body.start_point, body.end_point
    header, closer = lines[orow], lines[crow]
    if orow == crow or header[ocol + 1:].strip() or not _CLOSER_LINE.fullmatch(closer.strip()):
        return None
    owner = body.parent
    while owner is not None and owner.type in ("match_expression", "let_declaration", "expression_statement") \
            and owner.parent is not None and owner.parent.start_point[0] == orow:
        owner = owner.parent
    if owner is None or owner.start_point[0] != orow:
        return None
    return (orow, crow) if _indent(header) == _indent(closer) and closer.strip()[0] == "}" else None


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
    tree = parse("\n".join(chunk))
    if tree.root_node.has_error:
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with Rust facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    Rust template to run fills it, so later shared helpers (``_prose_rows``,
    ``_string_cells``, ``_delim_count``) find Rust answers instead of Python ones. String
    cells cover string, raw string and char literals and comments, never a lifetime's
    ``'``; only ``"`` strings count as quote pairs. Rust's own keys: ``attrs`` (attribute
    rows), ``multiline`` (rows inside a multi-line string), ``paths`` (names used as a path
    segment, macro name, lifetime or loop label), ``members`` (names used as a field, a
    struct literal key or a method definition).
    """
    if win.cache.get("rust"):
        return
    prose: set[int] = set()
    multiline: set[int] = set()
    attrs: set[int] = set()
    paths: set[str] = set()
    members: set[str] = set()
    cells: set[tuple[int, int]] = set()
    delims: dict[str, int] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        if n.type in _STRINGS:
            cells |= _cells(win, n)
            r0, r1 = n.start_point.row, _end_row(n)
            if r1 > r0:
                prose.update(range(r0, r1 + 1))
                if n.type not in _COMMENTS:
                    multiline.update(range(r0 + 1, r1 + 1))
            if n.type in _COMMENTS and not win.lines[r0][:n.start_point.column].strip():
                prose.update(range(r0, r1 + 1))
            if n.type in ("string_literal", "raw_string_literal"):
                delims['"'] = delims.get('"', 0) + 1
            continue
        if n.type in _ATTRIBUTES:
            rows = range(n.start_point.row, n.end_point.row + 1)
            attrs.update(rows)
            prose.update(rows)
        elif n.type in ("(", "[", "{"):
            delims[n.type] = delims.get(n.type, 0) + 1
        elif n.type in _ANGLES:
            delims["<"] = delims.get("<", 0) + 1
        elif n.type == "identifier" and _path_segment(n):
            paths.add(_text(n))
        elif _member(n):
            members.add(_text(n))
        stack.extend(n.children)
    win.cache.update({"rust": True, "prose": prose, "multiline": multiline, "attrs": attrs, "paths": paths,
                      "members": members,
                      "strings": cells, "delims": delims, "role_names": ROLE_NAMES, "types": _type_roles(win)})


def _type_roles(win: Window) -> dict[str, str]:
    """Name -> role from ``let`` bindings, parameters and struct fields: the declared type first
    (``Vec<_>`` is "many", ``bool`` "flag", ``String`` "text", ``usize`` "count"), else the
    initial value (an array or ``vec![]`` is "many", a number "count", a string "text"). A
    function's name is "call". Read by templates._role through the window cache."""
    roles: dict[str, str] = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type == "function_item":
            roles.setdefault(_text(n.child_by_field_name("name")), "call")
            continue
        if n.type in ("let_declaration", "parameter"):
            name = n.child_by_field_name("pattern")
        elif n.type == "field_declaration":
            name = n.child_by_field_name("name")
        else:
            continue
        if name is None or name.type not in ("identifier", "field_identifier"):
            continue
        declared, value = _text(n.child_by_field_name("type")), n.child_by_field_name("value")
        role = next((r for rx, r in _TYPE_ROLES if rx.search(declared)), None) if declared else None
        if role is None and value is not None:
            role = _VALUE_ROLES.get(value.type) or ("many" if _MANY_CALL.search(_text(value)) else None)
        if role is not None:
            roles.setdefault(_text(name), role)
    return roles


def _end_row(node: tree_sitter.Node) -> int:
    """Last row a node occupies: a line comment ends at column 0 of the next row. Points are
    indexed (see ``_spans``)."""
    (r0, _), (r1, c1) = node.start_point, node.end_point
    return r1 - 1 if c1 == 0 and r1 > r0 else r1


def _usable(win: Window, node: tree_sitter.Node) -> bool:
    """False for a node on an attribute line, and for a ``token_tree`` that is not a macro's
    own argument list (attribute arguments, nested macro tokens)."""
    if node.start_point.row in win.cache["attrs"]:
        return False
    return node.type != "token_tree" or (node.parent is not None and node.parent.type == "macro_invocation")


def _renamable(win: Window, node: tree_sitter.Node) -> bool:
    """True for an identifier that a rename can target: not on an attribute line, not a field
    or method after ``.`` in macro arguments, and not a name the window also uses as a path
    segment, macro name or lifetime."""
    prev = node.prev_sibling
    if node.parent is not None and node.parent.type == "token_tree" and prev is not None and prev.type == ".":
        return False
    return _usable(win, node) and _text(node) not in win.cache["paths"]


def _path_segment(node: tree_sitter.Node) -> bool:
    """True for an identifier in a path (``std::fmt``, ``Self::new``), a ``use`` list, a macro
    name, a lifetime or a loop label (``'outer``), also among a macro's argument tokens (``a::b``, ``inner!``)."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "token_tree":
        prev, nxt = node.prev_sibling, node.next_sibling
        return (prev is not None and prev.type == "::") or (nxt is not None and nxt.type in ("::", "!"))
    return parent.type in _PATHS or parent.type == "label"


def _member(node: tree_sitter.Node) -> bool:
    """True for a field (``ll.tail``, a struct field declaration), a struct literal key
    (``Node { value: v }``, shorthand ``Node { value }``) and a method's name in an
    ``impl`` or ``trait`` block."""
    parent = node.parent
    if node.type == "field_identifier":
        return True
    if node.type != "identifier" or parent is None:
        return False
    if parent.type == "shorthand_field_initializer":
        return True
    return parent.type == "function_item" and parent.parent is not None and parent.parent.type == "declaration_list"


def _span(win: Window, node: tree_sitter.Node, skill: str) -> tuple[int, int, int, str] | None:
    """(row, open col, close col, open char) for a single-line, non-empty delimited node whose
    delimiter is the one ``skill`` drills."""
    kids = node.children
    if node.start_point.row != node.end_point.row or len(kids) < 1 or not _usable(win, node):
        return None
    row = node.start_point.row
    line = win.lines[row]
    if node.type in ("string_literal", "raw_string_literal"):
        raw = _text(node)
        if '"' not in raw or any(k.type == "escape_sequence" for k in kids):
            return None
        oc, cc, q = node.start_point.column + raw.index('"'), node.start_point.column + raw.rindex('"'), '"'
        if cc <= oc or line[:oc].count('"') % 2 or "'\"'" in line:
            return None  # ci" pairs the quotes from the line start
        if "{" in raw or "}" in raw:
            return None  # a format string: the replacement would drop its placeholders
    elif node.type in _ANGLES:
        if kids[0].type != "<" or kids[-1].type != ">":
            return None
        oc, cc, q = kids[0].start_point.column, kids[-1].start_point.column, "<"
        if "->" in line[oc:cc] or "=>" in line[oc:cc]:
            return None  # i< would pair the `>` of the arrow
    elif node.type == "index_expression":
        opens, closes = [k for k in kids if k.type == "["], [k for k in kids if k.type == "]"]
        if len(opens) != 1 or len(closes) != 1:
            return None
        oc, cc, q = opens[0].start_point.column, closes[0].start_point.column, "["
    else:
        pair = _bracket_pair(node)
        if pair is None or pair[0][0] != pair[1][0]:
            return None
        (_, oc, q), (_, cc, _) = pair
    if _SKILL_DELIM.get(skill, q) != q:
        return None
    inner = line[oc + 1:cc]
    if len(inner.strip()) < 3 or (q == '"' and ('"' in inner or "\\" in inner)):
        return None
    if _delims(win).get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _depth0_positions(win: Window, open_rc, close_rc, o: str) -> list[tuple[int, int]]:
    """``braces.depth0_positions`` with string, char-literal and comment cells skipped, and the
    ``>`` of ``->`` / ``=>`` not read as a closing angle."""
    c = _PAIR[o]
    strings = win.cache["strings"]
    out, depth = [], 0
    (r0, c0), (r1, c1) = open_rc, close_rc
    for r in range(r0, r1 + 1):
        line = win.lines[r]
        for i in range(c0 + 1 if r == r0 else 0, c1 if r == r1 else len(line)):
            ch = line[i]
            if (r, i) in strings or (ch == ">" and i and line[i - 1] in "-="):
                continue
            if ch == o:
                depth += 1
            elif ch == c:
                depth -= 1
            elif depth == 0 and not ch.isspace() and ch not in "()[]{}<>":
                out.append((r, i))
    return out


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace, not in a nested pair or a string."""
    line = win.lines[row]
    if o == '"':
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        cols = [c for _, c in _depth0_positions(win, (row, oc), (row, cc), o)]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _alone(win: Window, node: tree_sitter.Node) -> bool:
    """True when a one-line item is all its line holds (with its comma in a field or variant list)."""
    row = node.start_point.row
    if node.end_point.row != row:
        return False
    line, text = win.lines[row].strip(), _text(node).strip()
    if node.parent is not None and node.parent.type in _COMMA_LISTS:
        return line == text + ","
    return line == text


def _line_move(win: Window, node: tree_sitter.Node, salt: str) -> tuple[int, int, bool] | None:
    """(row, distance, down) for moving/copying a one-line item among one-line sibling items
    (never across an attribute, a comment or a block's tail expression)."""
    parent = node.parent
    row = node.start_point.row
    if parent is None or parent.type not in _LINE_PARENTS or node.type not in _RUN_ITEMS or not _alone(win, node):
        return None
    if row in win.cache["attrs"]:
        return None
    rows = {s.start_point.row for s in parent.named_children if s.type in _RUN_ITEMS and _alone(win, s)}
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
        item = kid if kid is not None and kid.type in _RUN_ITEMS and _alone(win, kid) else None
        if item is not None and (not run or (item.start_point.row == run[-1].start_point.row + 1
                                             and item.start_point.column == run[0].start_point.column)):
            run.append(item)
            continue
        if len(run) >= min_len:
            yield run
        run = [item] if item is not None else []


def _const_runs(win: Window, node: tree_sitter.Node) -> Iterator[list[tuple[int, tree_sitter.Node]]]:
    """Runs of >= EX_MIN_LINES consecutive one-line constants (``_const_name``) as (row, name)."""
    for run in _statement_runs(win, node, templates.EX_MIN_LINES):
        named: list[tuple[int, tree_sitter.Node]] = []
        for item in [*run, None]:
            name = _const_name(win, item) if item is not None else None
            if name is not None:
                named.append((item.start_point.row, name))
                continue
            if len(named) >= templates.EX_MIN_LINES:
                yield named
            named = []


def _const_name(win: Window, node: tree_sitter.Node) -> tree_sitter.Node | None:
    """The SCREAMING_SNAKE name of a one-line ``const`` / ``static`` item, when it sits right
    before the line's first ``:`` (so ``f:b`` lands on it), else None."""
    if node.type not in _CONSTS or not _alone(win, node) or node.start_point.row in win.cache["attrs"]:
        return None
    name = node.child_by_field_name("name")
    if name is None or not _SCREAMING.fullmatch(_text(name)):
        return None
    line = win.lines[node.start_point.row]
    return name if line.find(":") == name.end_point.column else None


def _in_function_body(node: tree_sitter.Node) -> bool:
    """True for a ``{}`` block that is, or sits inside, the body of a function or closure."""
    up = node
    while up is not None and up.type not in ("source_file", "declaration_list"):
        if up.type == "block" and up.parent is not None and up.parent.type in _FUNCTIONS:
            return True
        up = up.parent
    return False


def _nested(node: tree_sitter.Node, o: str) -> bool:
    """True when an ancestor of ``node`` holds a pair of the same delimiter around it (the tree's
    answer; the text cannot tell a lifetime or a comment from a quote)."""
    if o == '"':
        return False
    c = _PAIR[o]
    start, end = node.start_point, node.end_point
    up = node.parent
    while up is not None:
        kids = up.children
        if any(k.type == o and k.start_point < start for k in kids) and any(k.type == c and k.end_point > end for k in kids):
            return True
        up = up.parent
    return False


def _which_pair(win: Window, node: tree_sitter.Node, row: int, oc: int, inner: str) -> tuple[bool, bool] | None:
    """``templates._which_pair`` with nesting read from the tree, or None when gate 6 would read
    the pair as nested and the tree does not (gates.nested_in_same_pair reads lines, so a bracket
    in a raw string or a block comment still counts)."""
    o = win.lines[row][oc]
    nested = _nested(node, o)
    if o in "([{" and not nested and gates.nested_in_same_pair(win.lines, row, oc, LANG.name):
        return None
    return templates._which_pair(win, row, oc, inner, nested)
