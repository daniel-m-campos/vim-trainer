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

LANG = Language(
    name="python",
    short="py",
    grammar="python",
    nodes={
        "string": (Use("t.quote", ("change_inner", "delete_inner")), Use("o.case", ("upper_inner",))),
        "argument_list": (*_PAREN, Use("o.change", ("change_nth_arg",)), Use("t.paren", ("delete_around",))),
        "parameters": _PAREN,
        "parenthesized_expression": _PAREN,
        "tuple": _PAREN,
        "keyword_argument": (Use("o.change", ("change_kwarg_value",)),),
        "list": _BRACKET,
        "list_comprehension": _BRACKET,
        "subscript": (Use("t.bracket", ("change_inner", "delete_around")), Use("m.match", ("jump_match",))),
        "dictionary": _BRACE,
        "set": _BRACE,
        "dictionary_comprehension": _BRACE,
        "set_comprehension": _BRACE,
        "interpolation": (Use("t.brace", ("change_inner",)),),
        "block": (Use("o.indent", ("indent_block",)),),
        "function_definition": (Use("o.delete", ("delete_lines",)),),
        "if_statement": (Use("o.delete", ("delete_lines",)),),
        "for_statement": (Use("o.delete", ("delete_lines",)),),
        "comment": (Use("o.delete", ("delete_trailing_comment",)),),
        "identifier": (
            Use("t.word", ("rename_here",)),
            Use("o.case", ("upper_word",)),
            Use("x.subst", ("rename_all_subst",)),
        ),
        "decorator": (Use("x.copymove", ("move_line",)),),
        "import_from_statement": (Use("x.copymove", ("move_line", "copy_line")),),
        "import_statement": (Use("x.copymove", ("move_line", "copy_line")),),
        "expression_statement": (Use("x.copymove", ("move_line", "copy_line")), Use("o.change", ("change_to_end",))),
        "return_statement": (Use("x.copymove", ("move_line",)),),
    },
    line_templates=(Use("m.rel", ("goto_line_rel",)), Use("m.find", ("find_char",))),
    find_targets=("(", ")", "=", ":", ",", ".", "["),
    comment_leader="#",
    keywords=frozenset(keyword.kwlist) | frozenset({"self", "cls", "print", "len", "range", "str", "int", "list"}),
)
