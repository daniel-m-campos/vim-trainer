r"""Bash: tree-sitter-bash node types mapped to skills and templates, plus windowing.

Node type names come from tree-sitter-bash's node-types.json (grammar 0.25). The module
follows lang/lua.py (same names, same order). Like Lua, Bash closes most blocks with a
keyword (``fi``, ``done``, ``esac``); only a function body or a group is a ``{ ... }`` pair.
The differences:

- ``windows`` skips a file that does not parse. ``reindent`` turns each leading tab into four
  spaces and re-indents a two-space file to four, the oracle's ``shiftwidth``. A window
  with a heredoc is left out: its body and end marker must not be shifted or dedented.
- Comments start with ``#`` at the start of a word. ``$#``, ``${#name}`` and ``${name#x}``
  are code, and gates.py cuts a Bash line accordingly. A ``# shellcheck`` directive is not
  a comment to delete.
- A double-quoted string is not all text: its ``$name``, ``${...}`` and ``$(...)`` are code.
  Only the literal parts (``string_content``), raw strings, ANSI-C strings and comments are
  masked. A string is drilled with ``ci"`` / ``di"`` (``ci'`` for a raw string) when it has
  no quote of its own kind and no backslash inside. Its new text fits what it held: words
  for words, ``$1`` for ``$name``. A format or a pattern is only ever emptied.
- The pairs are spelled ``${ }``, ``$( )``, ``$(( ))`` and ``( )`` (an array). ``_pair``
  finds the bracket inside the opening token. ``di{`` on an expansion and ``di[`` on a
  subscript would leave ``${}`` and ``name[]``, which Bash rejects, so those two are only
  changed, never emptied; a function body is never emptied either (``name() { }`` is a
  syntax error). The cursor of a bracket drill is never placed inside a quoted string
  nested in the pair: from inside quotes Vim only pairs brackets within the quotes.
- A variable is a ``variable_name`` (``name=``, ``$name``, ``${name}``, ``local name``, a
  ``for`` variable), a bare name inside ``(( ))`` / ``$(( ))``, or an argument of ``read``,
  ``mapfile``, ``readarray`` or ``getopts``. A function name is the ``word`` of its
  definition and of each command that calls it. ``_prime`` records both, so ``:%s`` only
  renames a name whose every whole-word hit in the window is one of those: a hit in
  literal text, in a comment, as a plain argument or as an array key makes no drill.
- ``%`` drills only pair ``( [ {``. Neovim's sh ftplugin sets ``b:match_words``, so matchit
  also cycles ``if`` / ``else`` / ``fi``, ``for`` / ``done`` and ``case`` / ``esac``; those
  are not drilled. o.indent shifts a function body with ``>i{`` and a ``then`` / ``else`` /
  ``do`` body by a count (``{N}>>``), as in Lua.
- ``split_pipeline`` is Bash's own split drill: ``:s/ | / |\r    /g`` breaks a pipeline of
  three or more commands after each ``|`` (a line ending in ``|`` continues on the next).
- The shared register templates read ``win.cache["registers"]``. ``_prime`` fills it with
  Bash facts: the identifiers are the variable and function names, and rows that are not a
  statement of their own (``fi``, ``done``, ``;;``, a case pattern, the continuation of a
  wrapped command or array) count as prose, so no drill yanks, cuts or puts one of them.

The oracle sets ``filetype=bash``: Neovim's ``ftplugin/bash.vim`` and ``indent/bash.vim``
load the sh files with ``b:is_bash``. ``indentexpr`` is ``GetShIndent()``, and its
``indentkeys`` re-indent the line when a ``)`` is typed, so no replacement text holds one.

``generate`` registers the ``bash_*`` templates for the duration of one call, as
``lua.generate`` does. Grammar-agnostic templates from templates.py are reused through
wrappers that first prime the window cache with Bash facts (``_prime``).
"""

import contextlib
import functools
import itertools
import re
import textwrap
from collections.abc import Callable, Iterator
from typing import Final

import tree_sitter
import tree_sitter_bash

from vimtrainer_content import gates, registers, snippets, splits, templates
from vimtrainer_content.lang import Language, Use, braces
from vimtrainer_content.snippets import Window, pick
from vimtrainer_content.templates import Draft

# Per-language weights, Bash column of the model/skill-graph.md table (also in skill-graph.json).
WEIGHTS: Final = {
    **dict.fromkeys(registers.SKILLS, 1.0),
    "t.quote": 1.5, "t.brace": 1.0, "t.paren": 1.0, "t.bracket": 1.0, "m.match": 1.0, "n.unmatched": 1.0,
    "o.indent": 1.0, "m.find": 1.2, "x.subst": 1.0, "o.delete": 1.0, "t.word": 1.0, "m.rel": 1.0,
    "o.change": 1.0, "x.copymove": 1.0,
}
TARGET_SKILLS: Final = (
    "t.quote", "t.paren", "t.brace", "t.bracket", "t.word", "m.find", "m.match", "m.rel",
    "n.unmatched", "o.delete", "o.change", "o.indent", "x.subst", "x.copymove",
    *registers.SKILLS,
)
FOUR: Final = "    "  # the indent unit windows are re-indented to (the oracle's shiftwidth)
PIPES_MIN: Final = 2  # split_pipeline: two breaks at least, as splits.ITEMS_MIN
PIPES_MAX: Final = 5

MESSAGE_TEXTS: Final = ("not found", "invalid input", "out of range", "no match", "try again", "missing argument")
WORD_TEXTS: Final = ("unknown", "pending", "default", "missing", "skipped", "empty")
VALUE_TEXTS: Final = ("$1", "$2", "$@", "$input", "$name")
LENGTH_TEXTS: Final = ("#1", "#name", "#items[@]")
ELEMENT_TEXTS: Final = ("items[@]", "values[i]", "args[0]")
EXPANSION_TEXTS: Final = ("1:-", "name:-default", "input,,", "value%.*")
COMMAND_TEXTS: Final = ('lookup "$1"', 'compute "$1" "$2"', 'count_items "$@"', "read_input", 'parse "$input"')
EXPR_TEXTS: Final = ("count + 1", "n - 1", "a + b", "i * 2")
ARRAY_TEXTS: Final = ("1 2 3", "a b c", '"$@"', "0 1")
KEYED_TEXTS: Final = ("[name]=none [size]=0", "[key]=value", "[id]=1 [count]=0")  # for `declare -A map=(...)`
INDEX_TEXTS: Final = ("0", "i + 1", "i - 1", "n - 1")
KEY_TEXTS: Final = ("key", "name", "index", "total")  # a bare word: an associative key or an index variable
KEY_VALUE_TEXTS: Final = ("$key", "$name", "$index", "$1")
INT_TEXTS: Final = ("0", "1", "10", "100", "-1", "3")

_NOUNS: Final = {
    "string": "string", "raw_string": "string", "expansion": "expansion", "subscript": "subscript",
    "command_substitution": "command substitution", "arithmetic_expansion": "arithmetic expansion",
    "array": "array", "compound_statement": "brace group",
}
_PAIR: Final = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
_DELIM_NAMES: Final = {"(": "parentheses", "[": "square brackets", "{": "braces", '"': "quotes", "'": "quotes"}
_ALIASES: Final = {"(": (")", "b"), "[": ("]",), "{": ("}", "B"), '"': (), "'": ()}
_QUOTES: Final = frozenset({'"', "'"})
# Where the bracket sits in a node's opening token: (node type, token) -> (offset, bracket).
_OPEN_AT: Final = {
    ("expansion", "${"): (1, "{"), ("command_substitution", "$("): (1, "("),
    ("arithmetic_expansion", "$(("): (2, "("), ("array", "("): (0, "("), ("compound_statement", "{"): (0, "{"),
}
# Every token that opens or closes a pair of a kind, for counting pairs and reading nesting.
_OPENERS: Final = {"(": "(", "$(": "(", "$((": "(", "((": "(", "<(": "(", ">(": "(", "${": "{", "{": "{", "[": "[", "[[": "["}
_CLOSERS: Final = {")": "(", "))": "(", "}": "{", "]": "[", "]]": "["}
_MASKED: Final = frozenset({"comment", "raw_string", "ansi_c_string", "string_content", "heredoc_body", "regex"})
_QUOTED_NODES: Final = frozenset({"string", "raw_string", "ansi_c_string", "translated_string"})
_ARITHMETIC: Final = frozenset({
    "binary_expression", "unary_expression", "postfix_expression", "parenthesized_expression", "ternary_expression",
})
_NAME_READERS: Final = frozenset({"read", "mapfile", "readarray", "getopts"})  # commands whose arguments name variables
_NAME: Final = re.compile(r"[A-Za-z_]\w*")
_PLAIN: Final = re.compile(r"[A-Za-z][\w ,.:!?-]*")  # text that reads as words: not a format, a pattern or a path
_PLAIN_PART: Final = re.compile(r"[\w ,.:!?-]+")
# Statement lists: a one-line child of one of these is a statement that can move or be deleted.
_LINE_PARENTS: Final = frozenset({
    "program", "compound_statement", "do_group", "if_statement", "elif_clause", "else_clause", "case_item", "subshell",
})
_LAST_ONLY: Final = frozenset({"return", "exit", "break", "continue", "shift"})  # commands that stay where they are
# Nodes that span rows without being a block: rows after their first continue a statement.
_WRAPPED: Final = frozenset({"command", "variable_assignment", "declaration_command", "array", "test_command"})
# Tokens that open or close a block: a row starting with one is not a statement of its own.
_BLOCK_TOKENS: Final = frozenset({"then", "do", "else", "elif", "fi", "done", "esac", ";;", "}", ")", "))", "]]"})
_BODY_CLOSERS: Final = ("fi", "else", "elif", "done", "}")
# The token after which a block's statements start (see ``_statements``).
_BLOCK_OPENERS: Final = {
    "compound_statement": "{", "do_group": "do", "if_statement": "then", "elif_clause": "then", "else_clause": "else",
    "subshell": "(",
}
_COMMENT_START: Final = re.compile(r"\s*#")
_DIRECTIVE: Final = re.compile(r"#\s*shellcheck\b")
_DELETED: Final = {
    "if_statement": "this `if` statement", "for_statement": "this `for` loop", "c_style_for_statement": "this `for` loop",
    "while_statement": "this `while` loop", "case_statement": "this `case` statement",
}
_VALUE_ROLES: Final = {"array": "many", "number": "count", "arithmetic_expansion": "count", "raw_string": "text"}
_KEYWORDS: Final = frozenset("""
    if then else elif fi for while until do done case esac in function select time coproc
    local declare typeset readonly export unset read echo printf return exit break continue shift set shopt trap
    source eval exec test true false let getopts mapfile readarray cd pwd wait kill type command builtin hash alias
    IFS PATH HOME PWD OLDPWD REPLY OPTARG OPTIND OPTERR BASH_REMATCH BASH_SOURCE BASH_VERSION BASH_VERSINFO
    FUNCNAME LINENO RANDOM SECONDS PIPESTATUS LC_ALL LANG TMPDIR USER HOSTNAME EUID UID SHELL TERM COLUMNS LINES
""".split())

_MATCH = (Use("m.match", ("bash_jump_match",)),)
_QUOTE = (Use("t.quote", ("bash_change_inner", "bash_delete_inner")),)
_PAREN = (Use("t.paren", ("bash_change_inner", "bash_delete_inner")),)
_BLOCK_END = (Use("n.unmatched", ("bash_jump_block_end",)),)
_INDENT = (Use("o.indent", ("bash_indent_block",)),)
_DELETE = (Use("o.delete", ("bash_delete_lines",)),)
_LINE = (Use("x.copymove", ("bash_move_line", "bash_copy_line")),)
_RENAME_ALL = (Use("x.subst", ("bash_rename_all_subst",)),)

LANG = Language(
    name="bash",
    short="sh",
    grammar="bash",
    nodes={
        "string": _QUOTE,
        "raw_string": _QUOTE,
        "expansion": (Use("t.brace", ("bash_change_inner",)), *_MATCH),
        "command_substitution": (*_PAREN, *_MATCH),
        "arithmetic_expansion": _PAREN,
        "array": (*_PAREN, *_MATCH, *_BLOCK_END),
        "subscript": (Use("t.bracket", ("bash_change_inner",)), *_MATCH),
        "compound_statement": (*_MATCH, *_BLOCK_END, *_INDENT, *_LINE),
        "do_group": _INDENT,
        "elif_clause": _INDENT,
        "else_clause": _INDENT,
        "comment": (Use("o.delete", ("bash_delete_trailing_comment",)),),
        "function_definition": (*_DELETE, *_RENAME_ALL),
        "if_statement": (*_DELETE, *_INDENT),
        "for_statement": _DELETE,
        "c_style_for_statement": _DELETE,
        "while_statement": _DELETE,
        "case_statement": _DELETE,
        "variable_name": (Use("t.word", ("bash_rename_here",)), *_RENAME_ALL),
        "variable_assignment": (*_LINE, Use("o.change", ("bash_change_rhs",))),
        "command": _LINE,
        "declaration_command": _LINE,
        "redirected_statement": _LINE,
        "pipeline": _LINE,
        "list": _LINE,
    },
    line_templates=(
        Use("m.rel", ("bash_goto_line_rel",)), Use("m.find", ("bash_find_char",)),
        Use("x.subst", ("bash_split_pipeline",)), *registers.USES, *splits.USES,
    ),
    find_targets=("(", ")", "{", "}", "[", "]", "=", "$", ";", ":", '"'),
    comment_leader="#",
    keywords=_KEYWORDS,
)


# Public Functions =================================================================================


@functools.cache
def parser() -> tree_sitter.Parser:
    """A tree-sitter parser for Bash."""
    return tree_sitter.Parser(tree_sitter.Language(tree_sitter_bash.language()))


def parse(text: str) -> tree_sitter.Tree:
    """Parse Bash source text."""
    return parser().parse(text.encode())


def windows(text: str, source: dict[str, str]) -> list[Window]:
    """Cut a Bash script into parseable 8-40 line windows (see ``snippets.windows``).

    Parameters
    ----------
    text
        Whole source file.
    source
        The exercise ``source`` object (repo, path, commit, license).

    Returns
    -------
    list[Window]
        Windows that pass the size, width, ASCII and parse checks; none for a file that
        does not parse as a whole. The file is re-indented to four spaces first
        (``reindent``); a function longer than 40 lines is split by recursing into its
        body. Licence and copyright comments break a window and are left out; comment-only lines
        never end one, and a window with a heredoc is dropped.
    """
    lines = reindent(text.splitlines())
    tree = parse("\n".join(lines))  # keep the tree alive while its nodes are walked
    if tree.root_node.has_error:
        return []
    comments = _comment_rows(tree.root_node, lines)
    out = []
    for start, end in _spans(tree.root_node.named_children, lines):
        win = _make_window(lines, start, end, source, comments)
        if win is not None:
            out.append(win)
    return out


def reindent(lines: list[str]) -> list[str]:
    """``lines`` with leading tabs as four spaces each and two-space levels as four-space ones.

    A file is two-space when a quarter or more of its indented lines sit at ``2 (mod 4)``
    columns; every indent ``i`` of such a file becomes ``i + 2 * (i // 2)``. A four-space
    file with a few lines aligned by hand comes back as it is. Rows inside a multi-line
    string or a heredoc are content and are never touched.

    Examples
    --------
    >>> reindent(["if true; then", "  echo hi", "fi"])
    ['if true; then', '    echo hi', 'fi']
    """
    keep = _content_rows(parse("\n".join(lines)).root_node)
    out = []
    for r, ln in enumerate(lines):
        tabs = len(ln) - len(ln.lstrip("\t"))
        out.append(ln if r in keep else FOUR * tabs + ln[tabs:])
    indents = [_indent(ln) for r, ln in enumerate(out) if ln.strip() and r not in keep and _indent(ln)]
    if 4 * sum(i % 4 == 2 for i in indents) < max(len(indents), 1):
        return out
    return [ln if r in keep or not ln.strip() else " " * (_indent(ln) + 2 * (_indent(ln) // 2)) + ln.lstrip()
            for r, ln in enumerate(out)]


def generate(win: Window, lang: Language = LANG) -> list[Draft]:
    """``templates.generate`` for a Bash window, with the ``bash_*`` templates registered.

    The shared registries only know the Python templates; the ``Use`` entries here name
    ``bash_*`` ones, added for the duration of the call and removed again. A draft of a
    shared register template that makes no sense in a shell is dropped (``_shell_sense``).
    """
    with registered():
        return [d for d in templates.generate(win, lang) if d.template not in registers.TEMPLATES or _shell_sense(d)]


def registered() -> contextlib.AbstractContextManager[None]:
    """Register the ``bash_*`` templates in the shared registries for the ``with`` block."""
    return braces.registered(BASH_NODE_TEMPLATES, BASH_LINE_TEMPLATES)


def node_frequency(texts: list[str]) -> dict[str, object]:
    """``snippets.node_frequency`` for Bash (named nodes per 100 lines over whole files)."""
    return braces.node_frequency(texts, parse)


# Node templates ===================================================================================


def change_inner(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``ci{delim}X<Esc>`` on a single-line string, expansion, command substitution, arithmetic
    expansion, array or subscript. The new text fits the old one (``_inner_text``)."""
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    which = _nesting(win, node, row, oc, inner)
    text = _inner_text(win, node, inner)
    if col is None or which is None or text is None:
        return
    c, noun = _PAIR[o], _NOUNS[node.type]
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
    """``di{delim}``: empty a single-line string, command substitution, arithmetic expansion or
    array. What is left (``""``, ``$()``, ``$(())``, ``()``) is still valid Bash."""
    span = _span(win, node)
    if span is None:
        return
    row, oc, cc, o = span
    inner = win.lines[row][oc + 1:cc]
    col = _cursor_inside(win, node, row, oc, cc, o)
    which = _nesting(win, node, row, oc, inner)
    if col is None or which is None:
        return
    c, noun, delims = _PAIR[o], _NOUNS[node.type], _DELIM_NAMES[o]
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


def change_rhs(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``C X<Esc>``: replace the value of a one-line ``name=...`` / ``local name=...``, cursor on it.
    The assignment is a statement of its own or the last word of a declaration, never the
    ``IFS=,`` in front of a command."""
    name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
    owner = node.parent.parent if node.parent is not None and node.parent.type == "declaration_command" else node.parent
    if name is None or value is None or owner is None or owner.type not in _LINE_PARENTS:
        return
    if node.start_point.row != node.end_point.row or not any(k.type == "=" for k in node.children):
        return
    row, r0, r1 = value.start_point.row, value.start_point.column, value.end_point.column
    line = win.lines[row]
    old = line[r0:r1]
    if line[r1:].strip() or len(old) < 5:
        return
    text = _fit(win, value, old)
    where = templates.on_this_line(win.lines, row, f"{_text(name)}=")
    if text is None or where is None:
        return
    yield Draft(
        template="change_to_end", skill=skill, kind="edit",
        task=f"Replace the value assigned to {templates._quote(_text(name), 32)}{where} with `{text}`",
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
    """``>i{`` or ``{N}>>`` / ``>{N-1}j`` (or ``<``): fix a body that is one level under- or over-indented.

    A function body sits between a ``{`` line and a ``}`` line and takes ``>i{``. A ``then``,
    ``else`` or ``do`` body ends at a line starting with ``fi``, ``else``, ``elif`` or ``done``;
    Vim has no text object for it, so the count is the skill there (see ``_bodies``).
    """
    lines = win.lines
    prose = win.cache["prose"]
    for header, start, end, braced in _bodies(node, lines):
        n = end - start + 1
        rows = range(start, end + 1)
        if not 2 <= n <= 12 or any(not lines[r].strip() or r in prose for r in rows):
            continue  # blank rows: the highlight skips them (QA #26); prose rows: a shifted string is another string
        base = _indent(lines[end + 1])
        if min(_indent(lines[r]) for r in rows) != base + len(FOUR) or _indent(lines[header]) != base:
            continue
        under = pick((True, False), win.key, (start, end), "indent")
        shifted = [(ln[4:] if under else FOUR + ln) if r in rows else ln for r, ln in enumerate(lines)]
        op = ">>" if under else "<<"
        o = op[0]
        counted = [f"{n}{op}", f"{o}{n - 1}j"]
        inside = [f"{o}i{{", f"{o}iB"]
        yield Draft(
            template="indent_block", skill=skill, kind="edit",
            task=templates.indent_task(lines[header].strip(), under, n),
            lines=shifted, cursor=[start + 1, _indent(shifted[start])], expect={"lines": lines},
            variants=[*inside, *counted] if braced else counted,
            alternates=[f"V{n - 1}j{o}", *([f"{o}i}}"] if braced else [])],
            idioms=[f"{o}ip", f"{o}ap", f"{o}}}", f"{o}G", *([] if braced else inside)],
            target=[_range(start, 0, end, max(len(shifted[end]) - 1, 0))], window=win, tags=["block", "indent"],
            hints=[
                {"trigger": f"({op}j)|({op}\\.)|(j\\.)", "text": f"{n}{op} shifts all {n} lines in one command."},
                {"trigger": "^[0-9]*I|^\\^?i", "text": f"{op} shifts by shiftwidth; there is no need to type spaces."},
                {"trigger": None, "text": (f"{o}i{{ shifts every line inside the braces; {n}{op} works too." if braced
                                           else f"{n}{op} or {o}{n - 1}j shift the {n} lines of the body.")},
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


def jump_match(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``%``: from one ``(``, ``[`` or ``{`` to its partner (either direction, possibly across lines).

    The pairs are the braces of ``${...}`` and of a function body, the parentheses of
    ``$(...)`` and of an array, and the brackets of a subscript. A pair with a bracket
    character in literal text or a comment between its ends is skipped (``%`` could count it).
    """
    pair = _pair(node)
    if pair is None or not _clean_pair(win, pair) or node.type == "arithmetic_expansion":
        return
    (orow, ocol, o), (crow, ccol, c) = pair
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
    """``templates.jump_block_end`` (``]}`` / ``[{``, ``])`` / ``[(``) on a function body, a brace
    group or an array, with Bash nouns and no bracket character in literal text between the pair."""
    pair = _bracket_pair(node)
    if pair is None or not _clean_pair(win, pair):
        return
    masked = win.cache["strings"]
    win.cache["strings"] = masked | _quoted_cells(win, node)  # from inside quotes Vim only pairs brackets within them
    try:
        found = list(templates.jump_block_end(win, node, skill, lang))
    finally:
        win.cache["strings"] = masked
    for draft in found:
        draft.task = re.sub(r"the [\w -]+ around the cursor$", f"the {_noun(node)} around the cursor", draft.task)
        yield draft


def delete_trailing_comment(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``f#D`` (``{k}f#D`` past ``$#`` or ``${#name}``): ``templates.delete_trailing_comment`` for a
    comment after code. A shellcheck directive is left alone, and so is a comment after a
    bare ``fi`` or ``}``: retyping the code is cheaper."""
    row = node.start_point.row
    if _DIRECTIVE.match(_text(node)) or len(win.lines[row][:node.start_point.column].strip()) < 6:
        return
    yield from templates.delete_trailing_comment(win, node, skill, lang)


def delete_lines(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.delete_lines`` (``{N}dd``, ``d}``, ``dap``) with Bash task text, on a function, an
    ``if``, a loop or a ``case`` that is a statement of its own: one that feeds a pipe or
    sits in a ``&&`` list is left alone. A loop with a redirect (``done < "$file"``) goes whole."""
    whole = node
    while whole.parent is not None and whole.parent.type == "redirected_statement" and whole.parent.start_point == node.start_point:
        whole = whole.parent
    if whole.parent is None or whole.parent.type not in _LINE_PARENTS:
        return
    if len(_statements(whole.parent) or (None, None)) < 2:
        return  # the only statement of its block: `then fi` and `name() { }` are syntax errors
    tail = win.lines[whole.end_point.row][whole.end_point.column:].strip()
    if tail and not tail.startswith("#"):
        return
    what = _DELETED.get(node.type, "this statement")
    if node.type == "function_definition":
        name = _text(node.child_by_field_name("name"))
        what = f"the function `{name}`" if _NAME.fullmatch(name) and len(name) <= 40 else "this function"
    for draft in templates.delete_lines(win, whole, skill, lang):
        n = whole.end_point.row - whole.start_point.row + 1
        draft.task = f"Delete {what} ({n} lines)"
        draft.tags = [node.type, "delete", "lines"]
        yield draft


def rename_here(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_here`` (``ciw``) on a variable name, on a primed window."""
    yield from templates.rename_here(win, node, skill, lang)


def rename_all_subst(win: Window, node: tree_sitter.Node, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.rename_all_subst`` (``:%s``) on a primed window, for a variable or for the name
    of a function. Every whole-word hit in the window must be a use of that variable or
    function (``_prime`` lists them), so the command renames nothing else."""
    name = node.child_by_field_name("name") if node.type == "function_definition" else node
    if name is not None:
        yield from templates.rename_all_subst(win, name, skill, lang)


# Line templates ===================================================================================


def goto_line_rel(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``templates.goto_line_rel`` (``{k}j`` / ``{k}k``) with Bash comment-only lines and multi-line
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


def split_pipeline(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    r"""``:s/ | / |\r{pad}/g<CR>`` (x.subst, ex kind): one command of a pipeline per line.

    The shell version of ``splits.split_line``. A line ending in ``|`` continues on the next
    one, so the result runs as before. The continuation lines are indented one level deeper
    than the line (see ``_pipelines`` for the lines that qualify)."""
    found = sorted(_pipelines(win).items(), key=lambda item: snippets.stable_hash(win.key, item[0], "pipe"))
    for row, pipes in found[:templates.MAX_PER_WINDOW]:
        line = win.lines[row]
        pad = _indent(line) + len(FOUR)
        cuts = [0, *(c + 2 for c in pipes), len(line)]
        parts = [line[a:b].rstrip() for a, b in itertools.pairwise(cuts)]
        split = [parts[0], *(" " * pad + p for p in parts[1:])]
        n = len(parts)
        keys = f":s/ | / |\\r{' ' * pad}/g<CR>"
        yield Draft(
            template="split_pipeline", skill=skill, kind="ex",
            task=(f"Break this pipeline after each `|`: the {n} commands go one per line, "
                  f"the new lines indented one level deeper ({pad} spaces)"),
            lines=win.lines, cursor=[row + 1, _indent(line)],
            expect={"lines": [*win.lines[:row], *split, *win.lines[row + 1:]]},
            variants=[keys], typed=pad, params={"n": n, "pad": pad},
            target=[_range(row, 0, row, len(line) - 1)], window=win, tags=["line", "split", "substitute", "pipeline"],
            hints=[
                {"trigger": r"\\n", "text": r"In the replacement of :s, \r is the line break. \n there inserts a null byte."},
                {"trigger": r"^:s/[^/]*/[^/]*/?<CR>", "text": "Without the g flag only the first pipe of the line is replaced."},
                {"trigger": r"^:%s", "text": "% runs over every line of the buffer. Plain :s works on the cursor line only."},
                {"trigger": None, "text": rf":s/ | / |\r{{{pad} spaces}}/g: each pipe keeps its place at the end of a line, and a line break (\r) and the indent follow it."},
            ],
        )


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


def _shell_sense(draft: Draft) -> bool:
    """False for a register draft a shell script would not survive. Called by ``generate``.

    - A block left without a statement, at the start or at the end: the templates cut and
      delete whole lines, and Bash rejects ``then fi``, ``do done`` and ``name() { }``.
    - ``swap_words`` outside arithmetic: between two commands ``&&``, ``||`` and ``|`` are
      not operators with two operands to swap (``$verbose && prefix+=x``)."""
    buffers = [draft.lines, draft.expect.get("lines", draft.lines)]
    if any(_hollow(parse("\n".join(lines)).root_node) for lines in buffers):
        return False
    if draft.template != "swap_words":
        return True
    root = draft.window.root
    return all(_in_arithmetic(root.descendant_for_point_range((r["start"][0] - 1, r["start"][1]),
                                                               (r["start"][0] - 1, r["start"][1])))
               for r in draft.target)


def _statements(block: tree_sitter.Node) -> list[tree_sitter.Node] | None:
    """The statements of a block (the inside of ``{ }``, ``( )``, ``do ... done``, a ``then`` or
    ``else`` part), comments left out; None for a node that is not such a block."""
    opener = next((k for k in block.children if k.type == _BLOCK_OPENERS.get(block.type)), None)
    if opener is None:
        return None
    return [k for k in block.children if k.is_named and k.start_byte >= opener.end_byte
            and k.type not in ("comment", "elif_clause", "else_clause")]


def _hollow(root: tree_sitter.Node) -> bool:
    """True when some block under ``root`` holds no statement. tree-sitter-bash parses it; Bash does not."""
    stack = [root]
    while stack:
        n = stack.pop()
        if _statements(n) == []:
            return True
        stack.extend(n.named_children)
    return False


def _in_arithmetic(node: tree_sitter.Node | None) -> bool:
    """True for a node inside ``(( ))``, ``$(( ))`` or the header of a C-style ``for``."""
    while node is not None:
        if node.type in ("arithmetic_expansion", "c_style_for_statement") or (
                node.type == "compound_statement" and node.children[0].type == "(("):
            return True
        node = node.parent
    return False


def _noun(node: tree_sitter.Node) -> str:
    """How a task names a delimited node; a ``{ }`` right under a function is its body."""
    if node.type == "compound_statement" and node.parent is not None and node.parent.type == "function_definition":
        return "function body"
    return _NOUNS.get(node.type, "bracket pair")


def _plain_string(node: tree_sitter.Node, inner: str) -> str | None:
    """What a quoted string holds: ``"words"`` (text that reads as words, with or without
    expansions in it), ``"value"`` (one expansion and nothing else, ``"$name"``) or None
    (a format, a pattern, a path, a command substitution: nothing to replace with prose)."""
    parts = node.named_children if node.type == "string" else []
    code = [k for k in parts if k.type != "string_content"]
    if any(k.type not in ("simple_expansion", "expansion") for k in code):
        return None
    if len(parts) == 1 and code and _text(code[0]) == inner:
        return "value"
    if code:
        literal = [_text(k) for k in parts if k.type == "string_content"]
        return "words" if literal and all(_PLAIN_PART.fullmatch(t) for t in literal) and inner[:1].isalpha() else None
    return "words" if _PLAIN.fullmatch(inner) else None


def _fit(win: Window, node: tree_sitter.Node, old: str) -> str | None:
    """A replacement for an assigned value that fits its kind (a number for a number, a quoted
    message for a quoted message, ``"$1"`` for a computed value), or None."""
    key = (win.key, node.start_point, "fit")
    kind = node.type
    if kind == "number":
        return _pick_other(INT_TEXTS, old, *key)
    if kind in ("string", "raw_string"):
        q, inner = old[0], old[1:-1]
        holds = _plain_string(node, inner)
        if holds == "words":
            return q + _pick_other(MESSAGE_TEXTS if " " in inner else WORD_TEXTS, inner, *key) + q
        return None if kind == "raw_string" else '"$2"' if old == '"$1"' else '"$1"'
    if kind == "command_substitution":
        return '"$1"'
    if kind in ("simple_expansion", "expansion"):
        return "$2" if old == "$1" else "$1"
    if kind == "arithmetic_expansion":
        return "0"
    if kind == "word" and old in ("true", "false"):
        return "false" if old == "true" else "true"
    return None


def _inner_text(win: Window, node: tree_sitter.Node, inner: str) -> str | None:
    """Replacement contents for a delimited node, fitted to what is inside it now; None when
    nothing fits (a format string, a pattern)."""
    key = (win.key, node.start_point, "ci")
    kind = node.type
    if kind in ("string", "raw_string"):
        holds = _plain_string(node, inner)
        if holds == "value":
            return _pick_other(VALUE_TEXTS, inner, *key)
        return _pick_other(MESSAGE_TEXTS if " " in inner else WORD_TEXTS, inner, *key) if holds else None
    if kind == "expansion":
        pool = LENGTH_TEXTS if inner.startswith("#") else ELEMENT_TEXTS if "[" in inner else EXPANSION_TEXTS
        return _pick_other(pool, inner, *key)
    if kind == "array":
        return _pick_other(KEYED_TEXTS if "]=" in inner else ARRAY_TEXTS, inner, *key)
    if kind == "subscript":
        pool = KEY_TEXTS if _NAME.fullmatch(inner) else KEY_VALUE_TEXTS if inner.startswith("$") else INDEX_TEXTS
        return _pick_other(pool, inner, *key)
    return _pick_other(COMMAND_TEXTS if kind == "command_substitution" else EXPR_TEXTS, inner, *key)


def _delims(win: Window) -> dict[str, int]:
    _prime(win)
    return win.cache["delims"]


def _comment_rows(root: tree_sitter.Node, lines: list[str]) -> set[int]:
    """Rows that hold nothing but a comment, over a whole file. Points are indexed
    (``start_point[0]``): the attribute getters crash py-tree-sitter 0.26.0 past 256 lines
    (see ``js._spans``)."""
    rows: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type != "comment":
            stack.extend(node.children)
            continue
        (r0, c0), (r1, _) = node.start_point, node.end_point
        if not lines[r0][:c0].strip():
            rows.update(range(r0, r1 + 1))
    return rows


def _content_rows(root: tree_sitter.Node) -> set[int]:
    """Rows after the first of every multi-line string, and every row of a heredoc body:
    content, whose leading whitespace is not indentation."""
    rows: set[int] = set()
    stack = [root]
    while stack:
        node = stack.pop()
        r0, r1 = node.start_point[0], node.end_point[0]
        if node.type in _QUOTED_NODES:
            rows.update(range(r0 + 1, r1 + 1))
        elif node.type == "heredoc_redirect":
            rows.update(range(r0 + 1, r1 + 1))
            continue
        stack.extend(node.children)
    return rows


def _spans(siblings: list[tree_sitter.Node], lines: list[str]) -> list[tuple[int, int]]:
    """Group sibling items into ``(start_row, end_row)`` spans of about SOFT_LINES lines.

    As ``lua._spans`` without the wrap: an item longer than a window is replaced by spans
    of its body statements (``_body_items``); short spans are merged only within one
    nesting level; an item that starts on the row the previous one ends on joins its
    group. Points are indexed.
    """
    limit = snippets.MAX_LINES
    out: list[tuple[int, int]] = []
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
            out += _merge_short(run, limit) + _spans(_body_items(node), lines)
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
    return out + _merge_short(run, limit)


def _body_items(node: tree_sitter.Node, depth: int = 0) -> list[tree_sitter.Node]:
    """The statements inside a long function, group, loop or ``if``: they parse on their own.
    An ``if`` gives the statements of its ``then`` part. The search looks at most three
    levels down (``name() { ... }``, ``while ...; do ... done < file``)."""
    if node.type in ("compound_statement", "do_group", "subshell"):
        return node.named_children
    if node.type == "if_statement":
        return [k for k in node.named_children
                if k.start_point[0] > node.start_point[0] and k.type not in ("elif_clause", "else_clause")]
    if depth >= 3:
        return []
    for child in node.named_children:
        items = _body_items(child, depth + 1) if child.type != "comment" else []
        if items:
            return items
    return []


def _make_window(lines: list[str], start: int, end: int, source: dict[str, str], comments: set[int]) -> Window | None:
    if start > 0 and start - 1 in comments:
        while start <= end and start in comments:
            start += 1  # the tail of a comment block that began above the window
    while end >= start and (not lines[end].strip() or end in comments):
        end -= 1
    while start <= end and not lines[start].strip():
        start += 1
    if start > end:
        return None
    chunk = lines[start:end + 1]
    indent = min(_indent(ln) for ln in chunk if ln.strip())
    chunk = [ln.rstrip() for ln in textwrap.dedent("\n".join(chunk)).split("\n")]
    if snippets.size_problem(chunk):
        return None
    tree = parse("\n".join(chunk))
    if tree.root_node.has_error or _has_heredoc(tree.root_node):
        return None
    return Window(lines=chunk, source=source, first_line=start + 1, last_line=end + 1, tree=tree, indent=indent)


def _has_heredoc(root: tree_sitter.Node) -> bool:
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "heredoc_redirect":
            return True
        stack.extend(node.children)
    return False


def _prime(win: Window):
    """Fill the window cache the shared template helpers read, with Bash facts.

    ``templates.generate`` clears ``win.cache`` once before running templates; the first
    Bash template to run fills it, so the shared helpers find Bash answers:

    - ``prose`` (``_prose_rows``): comment-only rows and the rows of a multi-line string.
    - ``strings`` (``_string_cells``): the cells of literal text and comments (``_MASKED``).
      The ``$name`` and ``${...}`` inside a double-quoted string are code and stay out.
    - ``delims`` (``_delim_count``): pairs per kind, ``${`` and ``$(`` counted as ``{`` and ``(``.
    - ``code_names`` (``_code_names``): every use of each variable and function, as
      (row, col). A name that is both a variable and a function is left out.
    - ``types`` (``_declared_roles``): name -> role from the value a variable is given.
    - ``registers`` (``registers._facts``): prose rows plus the rows that are not a
      statement of their own (see ``_fixed_rows``), and the uses of the variables as
      identifiers. Function names stay out: no drill puts a variable's name over one.
    """
    if win.cache.get("bash"):
        return
    lines = win.lines
    prose: set[int] = set()
    fixed: set[int] = set()
    cells: set[tuple[int, int]] = set()
    delims: dict[str, int] = {}
    roles: dict[str, str] = {}
    variables: dict[str, list[tuple[int, int]]] = {}
    functions: dict[str, list[tuple[int, int]]] = {}
    defined = _function_names(win.root)
    stack = [win.root]
    while stack:
        n = stack.pop()
        kind = n.type
        (r0, c0), (r1, _) = n.start_point, n.end_point
        if kind in _MASKED:
            cells |= _cells(win, n)
            if r1 > r0 or (kind == "comment" and not lines[r0][:c0].strip()):
                prose.update(range(r0, r1 + 1))
            if kind == "raw_string":
                delims["'"] = delims.get("'", 0) + 1
            continue
        if kind == "string":
            delims['"'] = delims.get('"', 0) + 1
            if r1 > r0:
                prose.update(range(r0, r1 + 1))
        elif kind in _OPENERS:
            delims[_OPENERS[kind]] = delims.get(_OPENERS[kind], 0) + 1
        elif kind == "variable_name" or (kind == "word" and _variable_word(n)):
            variables.setdefault(_text(n), []).append((r0, c0))
        elif kind == "word" and _text(n) in defined and _function_word(n):
            functions.setdefault(_text(n), []).append((r0, c0))
        elif kind == "variable_assignment":
            name, value = n.child_by_field_name("name"), n.child_by_field_name("value")
            if name is not None and value is not None and name.type == "variable_name" and value.type in _VALUE_ROLES:
                roles.setdefault(_text(name), _VALUE_ROLES[value.type])
        fixed.update(_fixed_rows(n, lines))
        stack.extend(n.children)
    names = {k: sorted(v) for k, v in {**variables, **functions}.items() if not (k in variables and k in functions)}
    idents = sorted((r, c, name) for name, hits in variables.items() if name not in functions for r, c in hits)
    win.cache.update({
        "bash": True, "prose": prose, "strings": cells, "delims": delims, "types": roles,
        "code_names": (names, set()), "registers": (prose | fixed, idents),
    })


def _fixed_rows(node: tree_sitter.Node, lines: list[str]) -> Iterator[int]:
    """Rows that ``node`` makes part of something larger, so that the row alone is not a
    statement the register drills may yank, cut or put next to: the continuation rows of a
    wrapped command, assignment, array or test; a later operand of a wrapped pipeline or
    ``&&`` / ``||`` list; the first and last row of a ``case`` item (its pattern and its
    ``;;``); a row that starts with a block token (``then``, ``fi``, ``done``, ``}``)."""
    kind = node.type
    (r0, c0), (r1, _) = node.start_point, node.end_point
    if kind in _BLOCK_TOKENS and not lines[r0][:c0].strip():
        yield r0
    elif kind == "case_item":
        yield from (r0, r1)
    elif r1 > r0 and kind in _WRAPPED:
        yield from range(r0 + 1, r1 + 1)
    elif r1 > r0 and kind in ("pipeline", "list"):
        yield from (k.start_point.row for k in node.named_children if k.start_point.row > r0)


def _function_names(root: tree_sitter.Node) -> set[str]:
    """Names of the functions the window defines."""
    names: set[str] = set()
    stack = [root]
    while stack:
        n = stack.pop()
        if n.type == "function_definition":
            names.add(_text(n.child_by_field_name("name")))
        stack.extend(n.named_children)
    return names


def _variable_word(node: tree_sitter.Node) -> bool:
    """True for a ``word`` that names a variable: a bare name in ``(( ))``, ``$(( ))`` or a
    C-style ``for`` header, or an argument of ``read``, ``mapfile``, ``readarray`` or ``getopts``.
    A bare array key (``${map[key]}``) is not one: in an associative array it is literal text."""
    if not _NAME.fullmatch(_text(node)):
        return False
    up = node.parent
    if up is not None and up.type == "command":
        return _text(up.child_by_field_name("name")) in _NAME_READERS
    while up is not None and up.type in _ARITHMETIC:
        up = up.parent
    if up is None:
        return False
    return up.type in ("arithmetic_expansion", "c_style_for_statement") or (
        up.type == "compound_statement" and up.children[0].type == "((")


def _function_word(node: tree_sitter.Node) -> bool:
    """True for the ``word`` that names a function in its definition or in a command that calls it."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type == "function_definition":
        return parent.child_by_field_name("name") == node
    return parent.type == "command_name"


def _pair(node: tree_sitter.Node) -> tuple[tuple[int, int, str], tuple[int, int, str]] | None:
    """The bracket pair of a node as ((row, col, open), (row, col, close)): the ``{ }`` of
    ``${...}`` or of a group, the ``( )`` of ``$(...)`` or of an array, the inner ``( )`` of
    ``$((...))``, the ``[ ]`` of a subscript. None for anything else (``(( ))``, a backtick
    substitution)."""
    kids = node.children
    if len(kids) < 2:
        return None
    if node.type == "subscript":
        opens, closes = [k for k in kids if k.type == "["], [k for k in kids if k.type == "]"]
        if len(opens) != 1 or len(closes) != 1:
            return None
        o, c = opens[0], closes[0]
        return (o.start_point.row, o.start_point.column, "["), (c.start_point.row, c.start_point.column, "]")
    first, last = kids[0], kids[-1]
    at = _OPEN_AT.get((node.type, first.type))
    if at is None or _CLOSERS.get(last.type) != at[1]:
        return None
    offset, o = at
    return (first.start_point.row, first.start_point.column + offset, o), (last.start_point.row, last.start_point.column, _PAIR[o])


def _quoted_cells(win: Window, node: tree_sitter.Node) -> set[tuple[int, int]]:
    """The cells of every quoted string nested in ``node``, quotes included. A bracket drill
    never starts there: from inside quotes Vim only pairs brackets within the quotes."""
    cells: set[tuple[int, int]] = set()
    stack = list(node.children)
    while stack:
        n = stack.pop()
        if n.type in _QUOTED_NODES:
            cells |= _cells(win, n)
        else:
            stack.extend(n.children)
    return cells


def _clean_pair(win: Window, pair) -> bool:
    """True when no literal text or comment between the pair holds a bracket character."""
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
    if node.start_point.row != node.end_point.row:
        return None
    row = node.start_point.row
    if node.type in ("string", "raw_string"):
        q = win.lines[row][node.start_point.column]
        oc, cc = node.start_point.column, node.end_point.column - 1
        if q not in _QUOTES or cc <= oc or win.lines[row][cc] != q:
            return None  # `$"..."` is a translated string
    else:
        pair = _pair(node)
        if pair is None or pair[0][0] != pair[1][0] or not _clean_pair(win, pair):
            return None
        (_, oc, q), (_, cc, _) = pair
    inner = win.lines[row][oc + 1:cc]
    if len(inner.strip()) < 3 or (q in _QUOTES and (q in inner or "\\" in inner)):
        return None
    if q not in _QUOTES and inner != inner.strip():
        return None  # padded contents (`$(( n + 1 ))`, `( a b )`) would lose their padding to ci(
    if _delims(win).get(q, 0) < 2:  # anti-shortcut: another pair of the same kind must exist
        return None
    return row, oc, cc, q


def _nesting(win: Window, node: tree_sitter.Node, row: int, oc: int, inner: str) -> tuple[bool, bool] | None:
    """``templates._which_pair`` with the nesting read from the tree, or None when gate 6 would
    read it differently (gates.py reads lines, not the tree). A pair is nested when an
    ancestor opens a pair of the same kind before it and closes it after it; the inner
    parentheses of ``$((...))`` always are."""
    o = win.lines[row][oc]
    if o in _QUOTES:
        return templates._which_pair(win, row, oc, inner, False)
    nested = node.type == "arithmetic_expansion"
    up = node.parent
    while up is not None and not nested:
        nested = (any(_OPENERS.get(k.type) == o and k.end_byte <= node.start_byte for k in up.children)
                  and any(_CLOSERS.get(k.type) == o and k.start_byte >= node.end_byte for k in up.children))
        up = up.parent
    if gates.nested_in_same_pair(win.lines, row, oc, LANG.name) != nested:
        return None
    return templates._which_pair(win, row, oc, inner, nested)


def _cursor_inside(win: Window, node: tree_sitter.Node, row: int, oc: int, cc: int, o: str) -> int | None:
    """A column strictly inside (oc, cc), not on whitespace; for a bracket pair also not in a
    nested pair of its kind, in literal text or in a quoted string (``_quoted_cells``)."""
    line = win.lines[row]
    if o in _QUOTES:
        cols = [i for i in range(oc + 1, cc) if not line[i].isspace()]
    else:
        skip = win.cache["strings"] | _quoted_cells(win, node)
        cols = [c for r, c in _depth0_positions(win, (row, oc), (row, cc), o, _PAIR[o]) if (r, c) not in skip]
    return pick(cols, win.key, node.start_point, "cur") if cols else None


def _bodies(node: tree_sitter.Node, lines: list[str]) -> Iterator[tuple[int, int, int, bool]]:
    """(header row, first body row, last body row, braced) for each body ``node`` owns that has
    whole lines to itself: the inside of a ``{ }`` group whose braces end and start their
    lines, the ``then`` part of an ``if`` or ``elif``, an ``else`` part, the inside of
    ``do ... done``. The row after the body starts with ``}``, ``fi``, ``else``, ``elif`` or ``done``."""
    kids = node.children
    opener = {"compound_statement": "{", "do_group": "do", "if_statement": "then", "elif_clause": "then",
              "else_clause": "else"}.get(node.type)
    first = next((k for k in kids if k.type == opener), None)
    if first is None:
        return
    start = first.start_point.row + 1
    if lines[start - 1][first.end_point.column:].strip():
        return
    after = [k for k in kids if k.start_byte >= first.end_byte and k.is_named and k.type not in ("elif_clause", "else_clause")]
    if not after:
        return
    end = max(k.end_point.row for k in after)
    if end < start or end + 1 >= len(lines) or min(k.start_point.row for k in after) < start:
        return
    closer = lines[end + 1].strip()
    if not any(closer == w or closer.startswith((w + " ", w + ";")) for w in _BODY_CLOSERS):
        return
    header = node.start_point.row if node.type in ("if_statement", "elif_clause", "else_clause") else start - 1
    yield header, start, end, node.type == "compound_statement"


def _one_line_items(win: Window, parent: tree_sitter.Node) -> set[int]:
    """Rows of the one-line statements of a statement list that are alone on their line and
    may move (not ``return`` / ``exit`` / ``break`` / ``continue`` / ``shift``, which stay put)."""
    rows = set()
    for s in parent.named_children:
        row = s.start_point.row
        if s.type == "comment" or s.end_point.row != row or win.lines[row].strip() != _text(s).strip():
            continue
        if _text(s).split()[0] not in _LAST_ONLY:
            rows.add(row)
    return rows


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


def _pipelines(win: Window) -> dict[int, list[int]]:
    """Row -> columns of its pipes, for each line ``:s/ | / |\\r.../g`` splits into one command
    per line: the line holds one pipeline of PIPES_MIN + 1 to PIPES_MAX + 1 commands, whole on
    that line, each ``|`` with one space on both sides, and no other `` | `` (in a string, in
    a second pipeline), since the substitution would break there too. No backtick (a task
    cannot quote one), no trailing comment, at most ``splits.WIDTH_MAX`` columns and a
    continuation indent of at most ``splits.PAD_MAX`` spaces."""
    _prime(win)
    found: dict[int, list[list[int]]] = {}
    commented: set[int] = set()
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type == "comment":
            commented.add(n.start_point.row)
        elif n.type == "pipeline" and n.start_point.row == n.end_point.row:
            pipes = [k.start_point.column for k in n.children if k.type in ("|", "|&")]
            found.setdefault(n.start_point.row, []).append(pipes)
    out = {}
    for row, groups in found.items():
        line = win.lines[row]
        if len(groups) != 1 or row in commented or "`" in line or len(line) > splits.WIDTH_MAX:
            continue
        (pipes,) = groups
        spaced = all(line[c - 1:c + 2] == " | " and line[c - 2:c - 1] != " " and line[c + 2:c + 3] not in ("", " ")
                     for c in pipes)
        if not PIPES_MIN <= len(pipes) <= PIPES_MAX or not spaced or line.count(" | ") != len(pipes):
            continue
        if _indent(line) + len(FOUR) <= splits.PAD_MAX:
            out[row] = pipes
    return out


_GATE5_FIRST: Final = (change_inner, delete_inner, rename_here)
BASH_NODE_TEMPLATES: Final = {f"bash_{fn.__name__}": _shipping(fn, fn in _GATE5_FIRST) for fn in (
    change_inner, delete_inner, change_rhs, indent_block, move_line, copy_line, jump_match, jump_block_end,
    delete_trailing_comment, delete_lines, rename_here, rename_all_subst,
)}
BASH_LINE_TEMPLATES: Final = {f"bash_{fn.__name__}": _shipping(fn) for fn in (goto_line_rel, find_char, split_pipeline)}
