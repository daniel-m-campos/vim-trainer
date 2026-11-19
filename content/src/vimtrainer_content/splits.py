r"""Split drill: a line template for x.subst that breaks one line into several with ``:s``.

``:s/, /,\r        /g`` puts every item of a call or a collection on its own line. In the
replacement of ``:s``, ``\r`` is a line break (``:help sub-replace-special``); ``\n`` there
inserts a null byte. The drill is the mirror of ``join_lines``: that one starts from the
wrapped form and joins it, this one starts from the one-line form and wraps it, with the
continuation lines aligned under the first item.

It works on any language: it reads the text of a line and needs no grammar. Importing this
module adds the template to ``templates.LINE_TEMPLATES``. A language turns it on with
``line_templates=(..., *splits.USES)``.
"""

import itertools
from collections.abc import Iterator
from typing import Final

from vimtrainer_content import registers, templates
from vimtrainer_content.lang import Language, Use
from vimtrainer_content.snippets import Window, stable_hash
from vimtrainer_content.templates import MAX_PER_WINDOW, Draft, _indent, _range

ITEMS_MIN: Final = 3  # two breaks at least: with one, `f,` and `r<CR>` is the plainer job
ITEMS_MAX: Final = 6
PAD_MAX: Final = 16  # spaces typed in the replacement; more is a typing test
SHIFT: Final = 4  # one indent level, the oracle's shiftwidth
WIDTH_MAX: Final = 88
GROUP_MIN: Final = 28  # characters from bracket to bracket: nobody wraps `(a, b, c)`
TAIL_MAX: Final = 3  # characters after the closing bracket (`);`, `) {`, `):`): a long tail reads badly on the last line
_OPEN: Final = {"(": ")", "[": "]", "{": "}"}
_QUOTES: Final = "\"'`"


# Public Functions =================================================================================


def split_line(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    r"""``:s/, /,\r{pad}/g<CR>`` (x.subst, ex kind): one item per line.

    The continuation lines line up under the first item when that takes PAD_MAX spaces or
    fewer. Deeper than that they are indented one level more than the statement instead:
    both are common ways to wrap, and nobody types 24 spaces into a command line."""
    rows = [r for r in range(len(win.lines)) if registers._is_code(win, r)]
    rows.sort(key=lambda r: stable_hash(win.key, r, "split"))
    made = 0
    for row in rows:
        line = win.lines[row]
        group = _group(line)
        if group is None or len(line) > WIDTH_MAX:
            continue
        opener, commas = group
        under = opener + 1 <= PAD_MAX
        pad = opener + 1 if under else _indent(line) + SHIFT
        if pad > PAD_MAX or "`" in line:
            continue
        cuts = [0, *(c + 2 for c in commas), len(line)]
        parts = [line[a:b].rstrip() for a, b in itertools.pairwise(cuts)]
        split = [parts[0], *(" " * pad + p for p in parts[1:])]
        n = len(parts)
        where = f"lined up under `{line[opener + 1:commas[0]]}`" if under else "indented one level deeper"
        keys = f":s/, /,\\r{' ' * pad}/g<CR>"
        yield Draft(
            template="split_line", skill=skill, kind="ex",
            task=f"Break this line after each comma: the {n} items go one per line, {where} ({pad} spaces)",
            lines=win.lines, cursor=[row + 1, _indent(line)],
            expect={"lines": [*win.lines[:row], *split, *win.lines[row + 1:]]},
            variants=[keys], typed=pad, params={"n": n, "pad": pad, "style": "under" if under else "deeper"},
            target=[_range(row, 0, row, len(line) - 1)], window=win, tags=["line", "split", "substitute"],
            hints=[
                {"trigger": r"\\n", "text": r"In the replacement of :s, \r is the line break. \n there inserts a null byte."},
                {"trigger": r"^:s/[^/]*/[^/]*/?<CR>", "text": "Without the g flag only the first comma of the line is replaced."},
                {"trigger": r"^:%s", "text": "% runs over every line of the buffer. Plain :s works on the cursor line only."},
                {"trigger": None, "text": rf":s/, /,\r{{{pad} spaces}}/g: each comma and space becomes a comma, a line break (\r) and the indent."},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


TEMPLATES: Final = {split_line.__name__: split_line}
USES: Final = (Use("x.subst", ("split_line",)),)
templates.LINE_TEMPLATES.update(TEMPLATES)


# Private Functions ================================================================================


def _group(line: str) -> tuple[int, list[int]] | None:
    """(column of the opening bracket, columns of its commas) when ``line`` holds one bracket
    group that ``:s/, /../g`` can split: ITEMS_MIN to ITEMS_MAX items directly inside it, each
    comma followed by one space, and no other ``, `` anywhere on the line (in a string, a
    nested call, a second group or a comment), since the substitution would break there too.
    The group is one a person would wrap: GROUP_MIN characters or more, and at most TAIL_MAX
    after its closing bracket, so `let (a, b, c) = long_call();` is left alone.
    None when there is no such group or the brackets and quotes do not pair up on the line."""
    stack: list[tuple[str, int]] = []
    found: dict[int, list[int]] = {}
    closers: dict[int, int] = {}
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in _QUOTES:
            quote = ch
        elif ch in _OPEN:
            stack.append((ch, i))
        elif ch in _OPEN.values():
            if not stack or _OPEN[stack[-1][0]] != ch:
                return None
            closers[stack.pop()[1]] = i
        elif ch == "," and len(stack) == 1:
            found.setdefault(stack[0][1], []).append(i)
        i += 1
    if quote or stack or len(found) != 1:
        return None
    (opener, commas), = found.items()
    if not ITEMS_MIN - 1 <= len(commas) <= ITEMS_MAX - 1 or line.count(", ") != len(commas):
        return None
    if any(line[c + 1:c + 2] != " " or line[c + 2:c + 3] in ("", " ") for c in commas):
        return None
    if not line[opener + 1:commas[0]].strip() or line[opener + 1] == " ":
        return None
    closer = closers[opener]
    items = [line[a:b] for a, b in itertools.pairwise([opener + 1, *(c + 2 for c in commas), closer + 2])]
    if not all(any(ch.isalnum() for ch in item) for item in items):
        return None  # a row of blank or punctuation-only strings is data, not a call to wrap
    if closer - opener + 1 < GROUP_MIN or len(line) - closer - 1 > TAIL_MAX:
        return None
    return opener, commas
