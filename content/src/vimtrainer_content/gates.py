"""Quality gates for generated exercises, all automated.

Gates 1 (licence), 2 (size) and 7 (secrets) live next to the data they check, in
``sources`` and ``snippets``. This module holds the per-exercise gates:

- gate 3, oracle pass, and gate 4, no shorter par: ``judge_par``, plus, for cursor
  drills, ``cursor_probes`` / ``cursor_probe_problem`` (every 1- and 2-key motion);
- gate 5, anti-shortcut: ``naive_cost`` and ``anti_shortcut_problem``;
- gate 6, unambiguous target: ``target_problem``. Besides the highlight checks, a target
  the task quotes must be the only one of its kind: an inner text object's quoted text
  (``the text `x` inside the quotes``) that occurs more than once in the window needs
  "under the cursor", one nested in a pair of the same kind needs "inner", and a quoted
  call, keyword or expression (``the `f` call``, ```name=```, ``Change `x = 1` to``)
  that occurs more than once needs "on this line" and must occur once on that line;
- gate 8, per-(language, skill) minimum: ``is_thin``.

Anti-shortcut model. ``naive_cost`` estimates the keystrokes of someone who only knows
hjkl, x, dd, i/S and typing: for a cursor drill, one key per line and per column moved;
for an edit, per changed line the cheaper of a character strategy (move to the first
changed column, ``x`` per char of the changed middle, ``i`` + new middle + ``<Esc>``) and
a line strategy (``S`` + retyped line + ``<Esc>``); deleted lines cost ``dd`` each and
inserted lines ``o`` + text + ``<Esc>``. Text that every solution must type (the new
string, the new name) is subtracted from both sides, so a long replacement does not hide
a pointless drill. The gate is ``par.count < retype_cost / 3``.

Multi-line drafts. When the same text goes onto every changed line (``:norm Iself.``,
``<C-v>3jA,``), the naive baseline types it once per line while par types it once. A
template declares this with ``typed_per_line`` (``Draft.exercise`` passes it on). The
honest subtraction (``typed`` once from par, ``typed * changed lines`` from naive) rejects
every such drill: a 3-line ``:norm`` drill is par 16 vs naive 23, and ``16-5 < (23-15)/3``
fails, because the drill's whole payoff is the retyping it avoids, which the ratio over
untyped keys cannot see. So these drafts use a different rule on purpose: par must beat
the naive cost outright, ``par.count < naive`` (``16 < 23`` passes; a 1-line ``:norm``
drill, par 12 vs naive 7, still fails).
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Collection, Sequence
from typing import Any, Final

from vimtrainer_content import oracle

RATIO: Final = 3.0
FLAG_MARGIN: Final = 1
MIN_PER_SKILL: Final = 20

# Cursor probes: every 1-key motion, the 2-key g/[/] motions, f/t/F/T + each buffer char,
# every pair of 1-key motions and a count with each 1-key motion.
PROBE_MOTIONS: Final = (
    "h", "j", "k", "l", "w", "b", "e", "W", "B", "E", "$", "0", "^", "%", "(", ")", "{", "}", "G", "H",
    "M", "L", "+", "-", "_", "|", "<CR>", "<BS>", "<Space>", "*", "#",
)
PROBE_PREFIXED: Final = ("gg", "ge", "gE", "g_", "gm", "gM", "go", "[(", "[{", "])", "]}", "[[", "]]", "[]", "][")
# Ties. A probe that ties the canonical and drills the same skill (``9+`` for ``9j``,
# ``t)`` for ``f(``) is fine. A tying 1-key motion (``$`` for ``%``) makes the drill moot,
# and so does a tying ``f``/``t``/``F``/``T`` + char outside m.find (``t.`` for ``])``):
# both are what a user reaches for first, so the drill no longer needs its skill. Other
# 2-key ties (``ww`` landing on the ``(`` that ``f(`` finds) are coincidences: they cost
# the same and do not make the drill easier, so they ship.
SKILL_MOTIONS: Final = {
    "m.find": re.compile(r"[1-9]?[fFtT].+"),
    "m.rel": re.compile(r"[1-9]\d*(?:j|k|\+|-|<CR>|_|G)|gg|G"),
    "m.match": re.compile(r"%"),
    "n.unmatched": re.compile(r"\[\(|\[\{|\]\)|\]\}"),
}
_FIND_CHAR: Final = re.compile(r"[fFtT].+")


# Public Functions =================================================================================


def naive_cost(exercise: dict[str, Any]) -> int:
    """Keystrokes of the hjkl/x/dd/typing baseline for an exercise (see module docstring)."""
    start = exercise["start"]
    row, col = start["cursor"][0] - 1, start["cursor"][1]
    if exercise["kind"] == oracle.Kind.CURSOR:
        trow, tcol = exercise["expect"]["cursor"][0] - 1, exercise["expect"]["cursor"][1]
        return abs(trow - row) + abs(tcol - col)
    return _edit_cost(start["lines"], exercise["expect"]["lines"], row, col)


def anti_shortcut_problem(exercise: dict[str, Any], par_count: int, typed: int) -> str | None:
    """Gate 5: why the drill is not worth it against the naive baseline, or None.

    With ``exercise["typed_per_line"]`` set, the rule is ``par_count < naive`` instead
    (see the module docstring).
    """
    naive = naive_cost(exercise)
    if exercise.get("typed_per_line"):
        return None if par_count < naive else f"par {par_count} vs naive {naive}: per-line text needs par < naive"
    if par_count - typed < (naive - typed) / RATIO:
        return None
    return f"par {par_count} vs naive {naive} (typed {typed}): needs par-typed < (naive-typed)/{RATIO:g}"


def target_problem(exercise: dict[str, Any], target: Sequence[dict[str, list[int]]], task: str = "") -> str | None:
    """Gate 6: the highlight must exist, be in bounds and cover what changes or where to go,
    and a destination line the task quotes ("below `...`") must name exactly one line."""
    lines = exercise["start"]["lines"]
    if not target:
        return "no target highlight"
    problem = _destination_problem(lines, task) or ambiguity_problem(exercise, target, task)
    if problem:
        return problem
    rows = set()
    for rng in target:
        (sl, sc), (el, ec) = rng["start"], rng["end"]
        if not (1 <= sl <= el <= len(lines)) or sc < 0 or ec < 0:
            return f"target {rng} out of bounds"
        if sc > max(len(lines[sl - 1]) - 1, 0) or ec > max(len(lines[el - 1]) - 1, 0):
            return f"target {rng} past end of line"
        rows.update(range(sl, el + 1))
    if exercise["kind"] == oracle.Kind.CURSOR:
        line, col = exercise["expect"]["cursor"]
        if not any(_inside(rng, line, col) for rng in target):
            return "expect.cursor is outside the target highlight"
        if exercise["expect"]["cursor"] == exercise["start"]["cursor"]:
            return "cursor already on target"
        return None
    changed = _changed_rows(lines, exercise["expect"]["lines"])
    if not changed:
        return "expect equals start"
    if exercise["kind"] == oracle.Kind.EDIT and not changed <= rows:
        return f"rows {sorted(changed - rows)} change outside the highlight"
    return None


def ambiguity_problem(exercise: dict[str, Any], target: Sequence[dict[str, list[int]]], task: str) -> str | None:
    """Gate 6, quoted targets: why the task does not single out its target, or None.

    See the module docstring. ``target[0]`` is where the target starts; for an inner text
    object it starts on the opening delimiter.
    """
    lines = exercise["start"]["lines"]
    row, col = target[0]["start"][0] - 1, target[0]["start"][1]
    inner = _INNER.search(task)
    if inner:
        return _inner_problem(lines, row, col, inner, exercise.get("lang", "python"))
    for rx, needle in _QUOTED:
        found = rx.search(task)
        if found:
            return _repeat_problem(lines, row, needle(found.group(1)), task)
    return None


def nested_in_same_pair(lines: Sequence[str], row: int, col: int, lang: str = "python") -> bool:
    """True when the bracket at ``(row, col)`` sits inside another pair of the same kind.

    Strings and trailing comments are skipped; a character that is not ``(``, ``[`` or ``{``
    is never nested. Templates use it to say "the inner parentheses"; gate 6
    requires that word.
    """
    o = lines[row][col] if row < len(lines) and col < len(lines[row]) else ""
    c = _BRACKETS.get(o)
    if c is None:
        return False
    depth = 0
    for r, line in enumerate(lines[:row + 1]):
        for ch in _code_chars(line[:col] if r == row else line, lang):
            if ch == o:
                depth += 1
            elif ch == c:
                depth = max(depth - 1, 0)
    return depth > 0


def occurrences(lines: Sequence[str], needle: str) -> tuple[int, dict[int, int]]:
    """(occurrences of ``needle`` in the window, row -> occurrences on that row)."""
    rows = {r: ln.count(needle) for r, ln in enumerate(lines) if needle in ln}
    return sum(rows.values()), rows


def judge_par(
    variants: Sequence[str], verdicts: dict[str, oracle.Verdict], forbid: Sequence[str] = (),
    margin: int = FLAG_MARGIN,
) -> tuple[oracle.Verdict | None, oracle.Verdict | None, str | None]:
    """Gates 3 and 4: pick the canonical among skill variants and compare to the best candidate.

    Returns
    -------
    tuple
        ``(canonical, best, problem)``. ``canonical`` is the shortest passing variant (ties
        go to the earlier variant); ``best`` is the shortest passing candidate of any kind.
        ``problem`` is None when the exercise may ship. ``margin`` is how many keys a
        non-canonical candidate may win by (gate 4 uses 1; cursor drills use 0, because a
        1-key motion such as ``$`` or ``w`` that lands on the target makes the drill moot).
    """
    passing = [verdicts[k] for k in variants if verdicts[k].passed]
    if not passing:
        reasons = "; ".join(f"{k!r}: {verdicts[k].reason}" for k in variants[:2])
        return None, None, f"no canonical variant passes ({reasons})"
    canonical = min(passing, key=lambda v: v.count)
    best = min((v for v in verdicts.values() if v.passed), key=lambda v: v.count)
    shortcut = [k for k in forbid if verdicts[k].passed]
    if shortcut:
        return canonical, best, f"shortcut {shortcut[0]!r} also solves it"
    if canonical.count - best.count > margin:
        return canonical, best, f"canonical {canonical.keys!r} ({canonical.count}) beaten by {best.keys!r} ({best.count})"
    return canonical, best, None


def cursor_probes(exercise: dict[str, Any]) -> list[tuple[str, int]]:
    """Every 1- and 2-key motion to replay on a cursor drill, as ``(keys, count)``."""
    chars = sorted(set("".join(exercise["start"]["lines"])))
    finds = [(f + ("<lt>" if c == "<" else c), 2) for f in "fFtT" for c in chars]
    singles = [(m, 1) for m in PROBE_MOTIONS]
    pairs = [(a + b, 2) for a in PROBE_MOTIONS for b in PROBE_MOTIONS]
    counts = [(d + m, 2) for d in "123456789" for m in PROBE_MOTIONS]
    probes = singles + [(m, 2) for m in PROBE_PREFIXED] + finds + pairs + counts
    return list(dict.fromkeys(probes))


def cursor_probe_problem(
    exercise: dict[str, Any], canonical_count: int, probes: Sequence[tuple[str, int]],
    landed: Sequence[list[int] | None], allowed: Collection[str] = (),
) -> str | None:
    """Gate 4 for cursor drills: no probe motion reaches the target in fewer keys than the
    canonical, and no 1-key or find-char motion ties it unless it is a known candidate
    (``allowed``) or a motion of the drilled skill (see ``SKILL_MOTIONS``)."""
    target = list(exercise["expect"]["cursor"])
    same_skill = SKILL_MOTIONS.get(exercise["skill"])
    for (keys, count), pos in zip(probes, landed, strict=True):
        if pos != target or count > canonical_count:
            continue
        if count < canonical_count:
            return f"motion {keys!r} ({count}) beats the canonical ({canonical_count})"
        if keys in allowed or (same_skill and same_skill.fullmatch(keys)):
            continue
        if count == 1 or _FIND_CHAR.fullmatch(keys):
            return f"motion {keys!r} ties the canonical ({count} keys)"
    return None


def is_thin(count: int) -> bool:
    """Gate 8: fewer than MIN_PER_SKILL exercises for a (language, skill)."""
    return count < MIN_PER_SKILL


# Private Functions ================================================================================


_DESTINATION: Final = re.compile(r"\b(?:below|above) `([^`]+)`\s*$")


def _destination_problem(lines: Sequence[str], task: str) -> str | None:
    """A quoted destination must match one line; a clipped quote ("...") its prefix only."""
    found = _DESTINATION.search(task)
    if not found:
        return None
    quote = found.group(1)
    if quote.endswith("..."):
        stem = quote[:-3]
        hits = sum(1 for ln in lines if ln.strip().startswith(stem))
    else:
        hits = sum(1 for ln in lines if ln.strip() == quote)
    if hits != 1:
        return f"destination `{quote}` matches {hits} lines"
    return None


_BRACKETS: Final = {"(": ")", "[": "]", "{": "}"}  # not "<": a less-than would read as an opening angle
_CLOSER: Final = {**_BRACKETS, "<": ">"}  # for the inner-text needle only, where the task already says "angle"
_INNER: Final = re.compile(r"\bthe text(?: `([^`]+)`)? inside the (inner )?(quotes|parentheses|square brackets|braces|"
                           r"angle brackets)")
# Quoted targets other than inner text objects: (task pattern, needle to count in the window).
_QUOTED: Final = (
    (re.compile(r"argument of the `([^`]+)` call"), lambda name: f"{name}("),
    (re.compile(r"the value of `([^`]+=)`"), lambda name: name),
    (re.compile(r"^Turn (?:the call )?`([^`]+)`(?: on this line)? into"), lambda whole: whole),
    (re.compile(r"^Turn the `([^`]+)` call(?: on this line)? into"), lambda name: f"{name}("),
    (re.compile(r"^Delete the subscript after `([^`]+)`"), lambda name: f"{name}["),
    (re.compile(r"^Change `([^`]+)`(?: on this line)? to `"), lambda old: old),
)
_STRING_LITERAL: Final = re.compile(r"'(?:\\.|[^'\\])*'?|\"(?:\\.|[^\"\\])*\"?")


def _inner_problem(lines: Sequence[str], row: int, col: int, found: re.Match, lang: str) -> str | None:
    quoted, inner_word, delims = found.groups()
    cursor = "under the cursor" in found.string
    if delims != "quotes" and not inner_word and nested_in_same_pair(lines, row, col, lang):
        return f"target {lines[row][col]!r} is nested in a pair of the same kind: say \"inner\""
    if quoted is None or col >= len(lines[row]):
        return None
    o = lines[row][col]
    total, _ = occurrences(lines, f"{o}{quoted}{_CLOSER.get(o, o)}")
    if total > 1 and not cursor:
        return f"`{quoted}` inside the {delims} occurs {total} times: say \"under the cursor\""
    return None


def _repeat_problem(lines: Sequence[str], row: int, needle: str, task: str) -> str | None:
    total, rows = occurrences(lines, needle)
    if total <= 1:
        return None
    if "on this line" in task and rows.get(row, 0) == 1:
        return None
    return f"`{needle}` occurs {total} times ({rows.get(row, 0)} on the target line): say \"on this line\""


def _code_chars(line: str, lang: str) -> str:
    """``line`` without its string literals and its trailing comment."""
    code = _STRING_LITERAL.sub("", line)
    return code.split("//" if lang == "cpp" else "#", 1)[0]


def _inside(rng: dict[str, list[int]], line: int, col: int) -> bool:
    (sl, sc), (el, ec) = rng["start"], rng["end"]
    after_start = (line, col) >= (sl, sc)
    before_end = (line, col) <= (el, ec)
    return after_start and before_end


def _changed_rows(before: Sequence[str], after: Sequence[str]) -> set[int]:
    rows = set()
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, list(before), list(after), autojunk=False).get_opcodes():
        if tag != "equal":
            rows.update(range(i1 + 1, max(i2, i1 + 1) + 1))
    return rows


def _edit_cost(before: Sequence[str], after: Sequence[str], row: int, col: int) -> int:
    """Per changed hunk, the cheaper of retyping lines and x-ing/typing the changed middle."""
    cost, pos = 0, (row, col)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, list(before), list(after), autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:
            for r, (a, b) in enumerate(zip(before[i1:i2], after[j1:j2]), i1):
                p, deleted, inserted = _middle(a, b)
                char = abs(r - pos[0]) + abs(p - pos[1]) + deleted + (2 + inserted if inserted else 0)
                line = abs(r - pos[0]) + 2 + len(b.strip())
                cost += min(char, line)
                pos = (r, p)
            continue
        retyped = [2 + len(t.strip()) for t in after[j1:j2]]
        deleted = i2 - i1
        paired = min(deleted, len(retyped))
        cost += abs(i1 - pos[0]) + sum(retyped[:paired]) + 2 * (deleted - paired) + sum(retyped[paired:])
        pos = (i1, 0)
    return cost


def _middle(a: str, b: str) -> tuple[int, int, int]:
    """(common prefix length, chars to delete, chars to insert) turning ``a`` into ``b``."""
    p = 0
    while p < min(len(a), len(b)) and a[p] == b[p]:
        p += 1
    s = 0
    while s < min(len(a), len(b)) - p and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1
    return p, len(a) - p - s, len(b) - p - s
