"""Register drills: line templates for r.yank0, r.blackhole, r.named, r.insert and o.put.

They work on any language. A drill needs lines and identifiers only, so the facts come from
node type names (``*string*``, ``*comment*``, ``*identifier``) and not from a grammar.

Most of these drills start in the middle of a job: something is already yanked or cut.
``Draft.registers`` (``start.registers``) loads that state before the first key. Two
drills are graded on a register as well as on the buffer (``expect.registers``), because
on the buffer alone the register is never the shortest route: ``dd`` beats ``"_dd``, and
plain ``yy`` three times leaves the buffer as untouched as ``"ayy`` ``"Ayy`` ``"Ayy``.

Importing this module adds its templates to ``templates.LINE_TEMPLATES``. A language
turns them on with ``line_templates=(..., *registers.USES)`` and ``registers.SKILLS``.
"""

import itertools
import re
from collections.abc import Iterator
from typing import Final

from vimtrainer_content import templates
from vimtrainer_content.lang import Language, Use
from vimtrainer_content.snippets import Window, pick, stable_hash
from vimtrainer_content.templates import MAX_PER_WINDOW, Draft, _indent, _range

LINE_MIN: Final = 14  # a line shorter than this is quicker to retype than a register is to name
LINE_MAX: Final = 44  # a register's text is quoted whole in the task
NAME_MIN: Final = 6  # shorter and typing the name ties ``<C-r>a``
COLLECT_GAPS: Final = range(2, 6)  # rows between two collected lines
# First words of a line that opens or closes a block, and last words of one that opens it:
# such a line is not a statement that can be cut and put somewhere else.
_BLOCK_HEADS: Final = frozenset({
    "if", "elif", "else", "elseif", "for", "while", "def", "class", "function", "func", "fn", "switch", "case",
    "try", "except", "catch", "finally", "match", "loop", "impl", "struct", "enum", "do", "repeat", "until",
    "end", "with", "namespace", "template", "public", "private", "protected", "default", "local", "pub", "async",
    "type", "interface", "trait", "mod", "export", "static", "unsafe",
})
_BLOCK_TAILS: Final = frozenset({"then", "do", "else"})
# Words that may come right before a call: `return f(x)` is a call, `void f(int x)` is not.
_CALL_HEADS: Final = frozenset({
    "return", "await", "yield", "not", "and", "or", "in", "new", "go", "defer", "throw", "raise", "if", "elif",
    "elseif", "while", "until", "assert", "del", "case",
})
# Words that make the line a declaration wherever they stand: `local function f(x)`, `pub fn f(x)`.
_DECLARES: Final = frozenset({"def", "function", "func", "fn", "class", "struct", "impl", "interface", "type", "macro_rules!"})
_CALL: Final = re.compile(r"([A-Za-z_]\w*)\($")
# How an attribute or decorator line starts: Rust `#[derive(..)]` and `#![..]`, a Python or
# TypeScript `@decorator`, a C++ `[[nodiscard]]`.
_ATTRIBUTE_STARTS: Final = ("#[", "#![", "@", "[[")
_TYPE_ENDS: Final = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_>*&]")  # a type or a name ends so
# What may sit between two swapped names: a comma or a binary operator. Not `=` or `:`,
# where swapping the two sides makes no sense.
_SEPARATOR: Final = re.compile(r"\s*(,|\+|-|\*|/|%|==|!=|~=|&&|\|\||&|\||\^)\s*")


# Public Functions =================================================================================


def put_yanked_line(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``"0p`` / ``"0P`` (r.yank0): a line was yanked, another was deleted since; put the yank."""
    lines = win.lines
    whole = set(_whole_rows(win, lang))
    rows = sorted(whole, key=lambda r: stable_hash(win.key, r, "yank0"))
    made = 0
    for y in rows:
        for d in rows:
            if abs(d - y) < 2:
                continue
            buf, at = _without(lines, d)
            here = at.index(y)
            # After a whole statement at the yank's indent, so the result still reads as code.
            uppers = [
                u for u in range(len(buf) - 1)
                if at[u] in whole and _is_code(win, at[u + 1]) and min(abs(u - here), abs(u + 1 - here)) >= 3
                and _indent(lines[y]) == _indent(buf[u])
            ]
            if not uppers:
                continue
            u = pick(uppers, win.key, y, d, "dest")
            below = pick((True, False), win.key, y, d, "side")
            start = u if below else u + 1
            yank, cut = lines[y] + "\n", lines[d] + "\n"
            yield Draft(
                template="put_yanked_line", skill=skill, kind="edit",
                task=(f"You yanked the line `{lines[y].strip()}`, then deleted another line. "
                      "Put the yanked line between the two highlighted lines"),
                lines=buf, cursor=[start + 1, _indent(buf[start])],
                expect={"lines": [*buf[:u + 1], lines[y], *buf[u + 1:]]},
                registers={'"': cut, "0": yank, "1": cut},
                variants=['"0p'] if below else ['"0P'], alternates=['j"0P'] if below else ['k"0p'],
                plain=[f":{here + 1}t{'.' if below else '-'}<CR>"],
                target=[_range(u, 0, u, len(buf[u]) - 1), _range(u + 1, 0, u + 1, len(buf[u + 1]) - 1)],
                window=win, tags=["register", "yank", "line"],
                hints=[
                    {"trigger": "^[jk]?[pP]", "text": "p puts the unnamed register, and the delete replaced what was in it. A yank also goes to register 0, which a delete never touches."},
                    {"trigger": "^:|yy", "text": 'The line is still in register 0: "0p puts it without yanking again.'},
                    {"trigger": None, "text": '"0p puts your last yank, whatever you deleted since. P puts above the cursor line.'},
                ],
            )
            made += 1
            break
        if made >= MAX_PER_WINDOW:
            return


def put_yanked_word(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``viw"0p`` (r.yank0): replace a word with the last yank after a delete took the unnamed register."""
    sites, names = _word_sites(win, lang)
    sites.sort(key=lambda s: stable_hash(win.key, s, "yank0w"))
    made = 0
    for row, col, word in sites:
        if len(word) < 4:
            continue
        yanks = [n for n in names if len(n) >= NAME_MIN and n != word]
        if not yanks:
            continue
        name = pick(yanks, win.key, row, col, "name")
        others = [n for n in names if n not in (word, name) and len(n) >= 3]
        if not others:
            continue
        other = pick(others, win.key, row, col, "other")
        yield Draft(
            template="put_yanked_word", skill=skill, kind="edit",
            task=(f"You yanked `{name}`, then deleted `{other}`, so the unnamed register now holds `{other}`. "
                  "Replace the highlighted word with the yank"),
            lines=win.lines, cursor=[row + 1, col + len(word) // 2],
            expect={"lines": templates._replace(win.lines, row, col, col + len(word), name)},
            registers={'"': other, "-": other, "0": name},
            variants=['viw"0p', "ciw<C-r>0<Esc>"], idioms=['bve"0p', '"_diw"0P'],
            plain=[f"ciw{name}<Esc>", f"bcw{name}<Esc>"],
            target=[_range(row, col, row, col + len(word) - 1)], window=win, tags=["register", "yank", "word"],
            hints=[
                {"trigger": "viw[pP]", "text": 'p over a selection puts the unnamed register, which holds the deleted word. "0 is the last yank: viw"0p.'},
                {"trigger": f"[cs].*{name}", "text": 'The name is already in register 0: viw"0p puts it over the word without typing it.'},
                {"trigger": None, "text": 'A yank goes to register 0 and stays there through deletes: viw"0p, or Ctrl-r 0 while inserting.'},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


def swap_words(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``diw`` .. ``viwp`` .. ``P`` (o.put): swap two names, using that a put over a selection
    leaves the replaced text in the unnamed register."""
    sites, _ = _word_sites(win, lang)
    by_row: dict[int, list[tuple[int, str]]] = {}
    for row, col, word in sites:
        by_row.setdefault(row, []).append((col, word))
    pairs = []
    for row, words in by_row.items():
        words.sort()
        line = win.lines[row]
        for (a, first), (b, second) in itertools.pairwise(words):
            if first != second and len(first) + len(second) >= 10 and _SEPARATOR.fullmatch(line[a + len(first):b]):
                pairs.append((row, a, first, b, second))
    pairs.sort(key=lambda p: stable_hash(win.key, p, "swap"))
    for row, a, first, b, second in pairs[:MAX_PER_WINDOW]:
        line = win.lines[row]
        swapped = line[:a] + second + line[a + len(first):b] + first + line[b + len(second):]
        yield Draft(
            template="swap_words", skill=skill, kind="edit", task=f"Swap `{first}` and `{second}` on this line",
            lines=win.lines, cursor=[row + 1, a], expect={"lines": [*win.lines[:row], swapped, *win.lines[row + 1:]]},
            variants=_swap_routes(line, a, first, b, second), plain=[_retype_route(line, a, first, b, second)],
            target=[_range(row, a, row, a + len(first) - 1), _range(row, b, row, b + len(second) - 1)],
            window=win, tags=["register", "put", "swap"],
            hints=[
                {"trigger": "^c", "text": "No retyping needed: diw on one name, viwp on the other, then P back where the first one was."},
                {"trigger": None, "text": "p over a selection swaps: the selection goes to the unnamed register. diw, viwp on the other name, go back, P."},
            ],
        )


def delete_keep_register(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``"_dd`` / ``"_dj`` / ``"_3dd`` (r.blackhole): delete lines while a cut line waits in
    the unnamed register. Graded on that register too."""
    lines = win.lines
    whole = set(_whole_rows(win, lang))
    rows = sorted(whole, key=lambda r: stable_hash(win.key, r, "hole"))
    made = 0
    for c in rows:
        buf, at = _without(lines, c)
        # Whole statements only, so the delete does not break a block. Two or three when the window has such a run.
        for n in pick(((1,), (2, 1), (3, 2, 1), (2, 1)), win.key, c, "count"):
            starts = [
                s for s in range(len(buf) - n + 1)
                if all(at[s + i] in whole for i in range(n)) and min(abs(at[s] - c), abs(at[s + n - 1] - c)) >= 2
            ]
            if starts:
                break
        if not starts:
            continue
        s = pick(starts, win.key, c, "start")
        cut = lines[c] + "\n"
        routes = {1: ['"_dd'], 2: ['"_dj', '"_2dd', '2"_dd'], 3: ['"_3dd', '"_d2j', '3"_dd']}[n]
        what = "the highlighted line" if n == 1 else f"the {n} highlighted lines"
        yield Draft(
            template="delete_keep_register", skill=skill, kind="edit",
            task=f"You cut the line `{lines[c].strip()}` to put it somewhere else. Delete {what} without losing it",
            lines=buf, cursor=[s + 1, _indent(buf[s])],
            expect={"lines": buf[:s] + buf[s + n:], "registers": {'"': cut}}, registers={'"': cut, "1": cut},
            variants=routes, alternates=['V"_d'] if n == 1 else [f'V{n - 1}j"_d'],
            plain=[r.replace('"_', "") for r in routes],
            target=[_range(r, 0, r, len(buf[r]) - 1) for r in range(s, s + n)],
            window=win, tags=["register", "blackhole", "line"],
            hints=[
                {"trigger": "^(\\d*dd|d\\d*j)", "text": 'A plain delete overwrites the unnamed register, so the cut line is gone from p. "_ is the black hole register: "_dd deletes and keeps every register as it was.'},
                {"trigger": None, "text": '"_dd deletes the line into the black hole register; the unnamed register still holds the cut line.'},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


def put_two_registers(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``"aP`` .. ``"bP`` (r.named): two cut lines wait in registers a and b; put each above its line."""
    lines = win.lines
    rows = sorted(_whole_rows(win, lang))
    pairs = [
        (x, y) for x in rows for y in rows
        if y - x >= 3 and all(r + 1 < len(lines) and _is_code(win, r + 1) and r + 1 not in (x, y) for r in (x, y))
    ]
    pairs.sort(key=lambda p: stable_hash(win.key, p, "two"))
    for x, y in pairs[:MAX_PER_WINDOW]:
        buf = [ln for r, ln in enumerate(lines) if r not in (x, y)]
        top, low = x, y - 1  # rows in buf of the lines that followed x and y
        a_first = pick((True, True, False), win.key, x, y, "order")
        here, there = ("a", "b") if a_first else ("b", "a")
        held = {here: lines[x], there: lines[y]}
        expect = [*buf[:top], held[here], *buf[top:low], held[there], *buf[low:]]
        down = low - top + 1
        yield Draft(
            template="put_two_registers", skill=skill, kind="edit",
            task=(f"Register `a` holds the line `{held['a'].strip()}` and register `b` holds `{held['b'].strip()}`. "
                  f"Put {here} above this line and {there} above the other highlighted line"),
            lines=buf, cursor=[top + 1, _indent(buf[top])], expect={"lines": expect},
            registers={"a": held["a"] + "\n", "b": held["b"] + "\n"},
            variants=[f'"{here}P{down}j"{there}P', f'"{here}P{down}+"{there}P'],
            alternates=[f'{down - 1}j"{there}P{down - 1}k"{here}P'],
            target=[_range(r, 0, r, len(buf[r]) - 1) for r in (top, low)],
            window=win, tags=["register", "named", "line"],
            hints=[
                {"trigger": "^[pP]|[jk][pP]", "text": 'p alone puts the unnamed register. Name the register first: "aP puts register a above the cursor line.'},
                {"trigger": "^[oOiIaA]", "text": 'Both lines are already in registers: "aP and "bP put them without typing.'},
                {"trigger": None, "text": 'A lowercase register keeps its text until you write to it again: "aP here, move down, "bP there.'},
            ],
        )


def collect_lines(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``"ayy`` .. ``"Ayy`` .. ``"Ayy`` (r.named): collect three scattered lines in register a,
    in half of the drafts then put them as a block. Graded on register a too."""
    lines = win.lines
    rows = set(_whole_rows(win, lang))
    triples = [
        (r, r + g, r + g + h) for r in sorted(rows) for g in COLLECT_GAPS for h in COLLECT_GAPS
        if r + g in rows and r + g + h in rows and _indent(lines[r]) == _indent(lines[r + g]) == _indent(lines[r + g + h])
    ]
    triples.sort(key=lambda t: stable_hash(win.key, t, "collect"))
    for one, two, three in triples[:MAX_PER_WINDOW]:
        text = "".join(lines[r] + "\n" for r in (one, two, three))
        collect = f'"ayy{two - one}j"Ayy{three - two}j"Ayy'
        dests = [t for t in range(three + 2, min(three + 6, len(lines))) if _is_code(win, t)]
        target = [_range(r, 0, r, len(lines[r]) - 1) for r in (one, two, three)]
        hints = [
            {"trigger": '"ayy.*"ayy', "text": 'A lowercase register is overwritten by every yank. The uppercase name appends: "Ayy adds the line to register a.'},
            {"trigger": "^:|^yy|[jk]yy", "text": 'The task is graded on register a: "ayy starts it, "Ayy appends to it.'},
            {"trigger": None, "text": '"ayy yanks the line into register a; "Ayy on the next lines appends them, so a holds all three.'},
        ]
        if dests and pick((True, False), win.key, one, two, three, "put"):
            dest = pick(dests, win.key, one, "dest")
            yield Draft(
                template="collect_lines", skill=skill, kind="edit",
                task=("The top three highlighted lines belong together. Collect them in register `a` (yank the first, "
                      "append the other two), then put all three above the last highlighted line"),
                lines=lines, cursor=[one + 1, _indent(lines[one])],
                expect={"lines": [*lines[:dest], *(lines[r] for r in (one, two, three)), *lines[dest:]], "registers": {"a": text}},
                variants=[f'{collect}{dest - three}j"aP'],
                plain=[f":{one + 1}t{dest}<CR>:{two + 1}t{dest + 1}<CR>:{three + 1}t{dest + 2}<CR>"],
                target=[*target, _range(dest, 0, dest, len(lines[dest]) - 1)],
                window=win, tags=["register", "named", "append", "put"], hints=hints,
            )
        else:
            yield Draft(
                template="collect_lines", skill=skill, kind="edit",
                task="Collect the three highlighted lines in register `a`, top to bottom: yank the first, append the other two",
                lines=lines, cursor=[one + 1, _indent(lines[one])], expect={"lines": lines, "registers": {"a": text}},
                variants=[collect], plain=[f"yy{two - one}jyy{three - two}jyy"],
                target=target, window=win, tags=["register", "named", "append"], hints=hints,
            )


def insert_register_arg(win: Window, skill: str, lang: Language) -> Iterator[Draft]:
    """``f)i, <C-r>a<Esc>`` (r.insert): add the name register a holds as a call's last argument."""
    _, names = _word_sites(win, lang)
    prose = _facts(win)[0]
    calls = []
    for row, line in enumerate(win.lines):
        if row in prose or line.lstrip().startswith(_ATTRIBUTE_STARTS) or not line.isascii() or line.count("(") != 1 or line.count(")") != 1 or re.search("[\"'`]", line):
            continue
        open_, close = line.index("("), line.index(")")
        fn = _CALL.search(line[:open_ + 1])
        if not fn or close <= open_ + 1 or not line[open_ + 1:close].strip() or fn.group(1) in lang.keywords:
            continue
        before = line[:fn.start()].split()
        if _DECLARES.intersection(before) or (before and before[-1][-1] in _TYPE_ENDS and before[-1] not in _CALL_HEADS):
            continue  # `def f(x)`, `void f(int x)`, `std::vector<int> f(int x)`: a declaration
        if not before and line.rstrip().endswith(("{", ":")):
            continue  # `run(cell) {`: a method
        calls.append((row, close, fn.group(1)))
    calls.sort(key=lambda c: stable_hash(win.key, c, "insert"))
    made = 0
    for row, close, fn in calls:
        line = win.lines[row]
        fresh = [n for n in names if NAME_MIN <= len(n) <= 20 and n != fn and not re.search(rf"\b{n}\b", line)]
        if not fresh:
            continue
        name = pick(fresh, win.key, row, "arg")
        yield Draft(
            template="insert_register_arg", skill=skill, kind="edit",
            task=(f"Register `a` holds `{name}`. Add it as the last argument of the `{fn}` call on this line, "
                  "without leaving insert mode to paste"),
            lines=win.lines, cursor=[row + 1, _indent(line)],
            expect={"lines": templates._replace(win.lines, row, close, close, f", {name}")}, registers={"a": name},
            variants=["f)i, <C-r>a<Esc>", "$i, <C-r>a<Esc>", "t)a, <C-r>a<Esc>"], typed=2,
            plain=[f"f)i, {name}<Esc>", f"$i, {name}<Esc>", 'f)i, <Esc>"ap', '$i, <Esc>"ap'],
            target=[_range(row, close, row, close)], window=win, tags=["register", "insert"],
            hints=[
                {"trigger": '<Esc>"ap', "text": "Ctrl-r a pastes register a while you are still typing, so there is no need to leave insert mode."},
                {"trigger": f", {name}", "text": "The name is in register a: Ctrl-r a in insert mode pastes it."},
                {"trigger": None, "text": "In insert mode, Ctrl-r and a register name pastes that register at the cursor."},
            ],
        )
        made += 1
        if made >= MAX_PER_WINDOW:
            return


TEMPLATES: Final = {
    fn.__name__: fn for fn in (
        put_yanked_line, put_yanked_word, swap_words, delete_keep_register, put_two_registers, collect_lines,
        insert_register_arg,
    )
}
USES: Final = (
    Use("r.yank0", ("put_yanked_line", "put_yanked_word")),
    Use("r.blackhole", ("delete_keep_register",)),
    Use("r.named", ("put_two_registers", "collect_lines")),
    Use("r.insert", ("insert_register_arg",)),
    Use("o.put", ("swap_words",)),
)
SKILLS: Final = tuple(use.skill for use in USES)
templates.LINE_TEMPLATES.update(TEMPLATES)


# Private Functions ================================================================================


def _facts(win: Window) -> tuple[set[int], list[tuple[int, int, str]]]:
    """(prose rows, code identifiers as (row, col, name)). Prose is a comment-only row or a row
    of a string or comment that spans rows; an identifier inside a string or comment is not code."""
    cached = win.cache.get("registers")
    if cached is not None:
        return cached
    prose: set[int] = set()
    idents: list[tuple[int, int, str]] = []
    stack = [win.root]
    while stack:
        n = stack.pop()
        if "string" in n.type or "comment" in n.type or n.type in ("char_literal", "preproc_include"):
            first, last = n.start_point.row, n.end_point.row
            if first != last:
                prose.update(range(first, last + 1))
            elif "comment" in n.type and not win.lines[first][:n.start_point.column].strip():
                prose.add(first)
            continue
        if not n.children and n.type.endswith("identifier"):
            idents.append((n.start_point.row, n.start_point.column, templates._text(n)))
        stack.extend(n.children)
    cached = win.cache["registers"] = (prose, sorted(idents))
    return cached


def _is_code(win: Window, row: int) -> bool:
    """A non-blank ASCII row that is not prose: fit to be a cursor line or a highlight.
    An attribute or decorator line and the line it belongs to are left alone, so no drill
    edits `#[derive(...)]` or puts a line between `@property` and its `def`."""
    line = win.lines[row]
    if not line.strip() or not line.isascii() or "\t" in line or row in _facts(win)[0]:
        return False
    return not any(win.lines[r].lstrip().startswith(_ATTRIBUTE_STARTS) for r in (row - 1, row) if r >= 0)


def _whole_rows(win: Window, lang: Language) -> list[int]:
    """Rows holding one whole statement that can be yanked, cut and put elsewhere: code, not
    a block opener or closer, brackets balanced, LINE_MIN to LINE_MAX characters, quotable
    in a task and the only such line in the window."""
    texts = [ln.strip() for ln in win.lines]
    rows = []
    for row, text in enumerate(texts):
        if not _is_code(win, row) or not LINE_MIN <= len(text) <= LINE_MAX or "`" in text or texts.count(text) > 1:
            continue
        words = text.split()
        if words[0].rstrip(":({") in _BLOCK_HEADS or words[-1] in _BLOCK_TAILS:
            continue
        if text.startswith((lang.comment_leader, "#", "/*", "*", ")", "]", "}", ".", "@")) or text[-1] in "{([,\\:=+-*/&|.<":
            continue
        if all(text.count(o) == text.count(c) for o, c in ("()", "[]", "{}")):
            rows.append(row)
    return rows


def _without(lines: list[str], row: int) -> tuple[list[str], list[int]]:
    """(``lines`` without ``row``, for each remaining line its row in ``lines``)."""
    at = [r for r in range(len(lines)) if r != row]
    return [lines[r] for r in at], at


def _word_sites(win: Window, lang: Language) -> tuple[list[tuple[int, int, str]], list[str]]:
    """(identifiers to drill on as (row, col, name), every usable name in the window, sorted).

    A site sits on a code row and its name appears once on that row as a whole word, so the
    highlight and the task name the same thing. Keywords and dunder names are left out."""
    sites, names = [], set()
    for row, col, name in _facts(win)[1]:
        line = win.lines[row]
        if (not _is_code(win, row) or name in lang.keywords or name.startswith("__")
                or not re.fullmatch(r"[A-Za-z_]\w*", name) or line[col:col + len(name)] != name):
            continue
        names.add(name)
        if len(re.findall(rf"\b{re.escape(name)}\b", line)) == 1:
            sites.append((row, col, name))
    return sites, sorted(names)


def _starts(line: str) -> list[int]:
    """Columns where ``w`` and ``b`` stop: the first character of each word or punctuation run."""
    cls = [0 if ch.isspace() else 1 if ch.isalnum() or ch == "_" else 2 for ch in line]
    return [i for i, c in enumerate(cls) if c and (i == 0 or cls[i - 1] != c)]


def _count(n: int, motion: str) -> str:
    return motion if n == 1 else f"{n}{motion}"


def _key(ch: str) -> str:
    return "<lt>" if ch == "<" else ch


def _swap_routes(line: str, a: int, first: str, b: int, second: str) -> list[str]:
    """Candidate keys that swap ``first`` (at ``a``, under the cursor) and ``second`` (at ``b``).

    ``diw`` leaves a gap at ``a``; a forward motion reaches ``second``; ``viwp`` puts
    ``first`` there and takes ``second`` into the unnamed register; a backward motion
    returns to the gap and ``P`` (or ``p`` from the column before it) fills it. The motions
    are computed from the line, and the oracle keeps the ones that work."""
    cut = line[:a] + line[a + len(first):]
    there = b - len(first)
    forward = [_count(sum(a < s <= there for s in _starts(cut)), "w")]
    if cut[a + 1:there + 1].count(second[0]) == 1:
        forward.append(f"f{second[0]}")
    put = cut[:there] + first + cut[there + len(second):]
    cursor = there + len(first) - 1
    starts = _starts(put)
    back = []
    if a in starts:
        back.append(_count(sum(a <= s < cursor for s in starts), "b") + "P")
    if a and a - 1 in starts:
        back.append(_count(sum(a - 1 <= s < cursor for s in starts), "b") + "p")
    if a and a + 1 in starts:  # the gap is the space before an operator: back to the operator, one left
        back.append(_count(sum(a + 1 <= s < cursor for s in starts), "b") + "hP")
    if not put[a].isspace():
        back.append(_count(put[a:cursor].count(put[a]), f"F{_key(put[a])}") + "P")
    if a:
        back.append(_count(put[a - 1:cursor].count(put[a - 1]), f"T{_key(put[a - 1])}") + "P")
    if a == 0:
        back.append("0P")
    if a == _indent(line):
        back.append("^P")
    return [f"diw{f}viwp{k}" for f in forward for k in back]


def _retype_route(line: str, a: int, first: str, b: int, second: str) -> str:
    """The swap done by typing both names: ``ciw``, the other name, over each."""
    typed = line[:a] + second + line[a + len(first):]
    there = b - len(first) + len(second)
    hops = sum(a + len(second) - 1 < s <= there for s in _starts(typed))
    return f"ciw{second}<Esc>{_count(hops, 'w')}ciw{first}<Esc>"
