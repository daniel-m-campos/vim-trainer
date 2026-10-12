"""Python: tree-sitter-python node types mapped to skills and templates.

Node type names come from tree-sitter-python's node-types.json (grammar 0.25).
"""

from __future__ import annotations

import keyword

from vimtrainer_content.lang import Language, Use

_PAREN = (
    Use("t.paren", ("change_inner", "delete_inner")),
    Use("m.match", ("jump_match",)),
    Use("n.unmatched", ("jump_block_end",)),
)
_BRACKET = (Use("t.bracket", ("change_inner", "delete_inner")), Use("m.match", ("jump_match",)))
_BRACE = (
    Use("t.brace", ("change_inner", "delete_inner")),
    Use("m.match", ("jump_match",)),
    Use("n.unmatched", ("jump_block_end",)),
)
# Tiers 5-8: multi-line collections, whole-window line groups, repeated siblings.
_MULTILINE = (Use("v.blockedit", ("append_each_line",)), Use("o.join", ("join_lines",)))
_PARAGRAPH = (Use("t.para", ("delete_block",)),)
_WINDOW = (
    Use("x.global", ("delete_matching_lines", "keep_matching_lines")),
    Use("x.normal", ("upper_constants",)),
    Use("a.macro", ("record_macro",)),
)
_LINE_COPY = (Use("o.yank", ("duplicate_line",)), Use("o.put", ("duplicate_line",)))

LANG = Language(
    name="python",
    short="py",
    grammar="python",
    nodes={
        "string": (Use("t.quote", ("change_inner", "delete_inner")), Use("o.case", ("upper_inner",))),
        "argument_list": (
            *_PAREN, Use("o.change", ("change_nth_arg",)), Use("t.paren", ("delete_around", "delete_block")),
            *_MULTILINE,
        ),
        "parameters": (*_PAREN, *_MULTILINE),
        "parenthesized_expression": (*_PAREN, Use("o.join", ("join_lines",))),
        "tuple": (*_PAREN, *_MULTILINE),
        "keyword_argument": (Use("o.change", ("change_kwarg_value",)), Use("m.find", ("change_kwarg_value",))),
        "list": (*_BRACKET, Use("t.bracket", ("delete_block",)), *_MULTILINE),
        "list_comprehension": _BRACKET,
        "subscript": (Use("t.bracket", ("change_inner", "delete_around")), Use("m.match", ("jump_match",))),
        "dictionary": (*_BRACE, Use("t.brace", ("delete_block",)), *_MULTILINE),
        "set": (*_BRACE, Use("t.brace", ("delete_block",)), *_MULTILINE),
        "dictionary_comprehension": _BRACE,
        "set_comprehension": _BRACE,
        "interpolation": (Use("t.brace", ("change_inner",)),),
        "integer": (Use("o.number", ("increment",)),),
        "module": _WINDOW,
        "block": (
            Use("o.indent", ("indent_block",)), Use("a.macro", ("record_macro",)),
            Use("x.normal", ("upper_constants", "prefix_each_line")), Use("v.blockedit", ("prefix_each_line",)),
        ),
        "function_definition": (Use("o.delete", ("delete_lines",)), *_PARAGRAPH),
        "class_definition": _PARAGRAPH,
        "if_statement": (Use("o.delete", ("delete_lines",)), *_PARAGRAPH),
        "for_statement": (Use("o.delete", ("delete_lines",)), *_PARAGRAPH),
        "while_statement": _PARAGRAPH,
        "with_statement": _PARAGRAPH,
        "comment": (Use("o.delete", ("delete_trailing_comment",)),),
        "identifier": (
            Use("t.word", ("rename_here",)),
            Use("o.case", ("upper_word",)),
            Use("x.subst", ("rename_all_subst",)),
            Use("x.lastsearch", ("rename_all_dot",)),
            Use("a.dot", ("rename_all_dot",)),
        ),
        "decorator": (Use("x.copymove", ("move_line",)),),
        "import_from_statement": (Use("x.copymove", ("move_line", "copy_line")), *_LINE_COPY),
        "import_statement": (Use("x.copymove", ("move_line", "copy_line")), *_LINE_COPY),
        "expression_statement": (
            Use("x.copymove", ("move_line", "copy_line")), Use("o.change", ("change_to_end",)), *_LINE_COPY,
        ),
        "return_statement": (Use("x.copymove", ("move_line",)),),
    },
    line_templates=(Use("m.rel", ("goto_line_rel",)), Use("m.find", ("find_char",))),
    find_targets=("(", ")", "=", ":", ",", ".", "["),
    comment_leader="#",
    keywords=frozenset(keyword.kwlist) | frozenset({"self", "cls", "print", "len", "range", "str", "int", "list"}),
)
