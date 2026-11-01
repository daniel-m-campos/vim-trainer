"""Seeded key sequences for the differential fuzzer, and the buffers they start from.

A sequence is a list of statements drawn from a weighted grammar over the drilled command
set (model/skill-graph.md tiers 0-9)::

    stmt := edit 45 | motion 20 | visual 10 | ex 8 | insert 7 | undo 4 | dot 3 | macro 2 | register 1

Each case gets its own ``random.Random(seed * 1_000_003 + index)``, so one case replays
without generating the others. ``.`` is only emitted after a change, a macro body never
contains ``@`` (no recursion), and no sequence matches ``FORBIDDEN`` (keys that quit, write,
open files, shells, windows or the clipboard). Screen motions (``H M L <C-d>`` ...) are
left out unless ``include_screen`` is set, because the two window heights differ.

Examples
--------
>>> buf = Buffer("demo", "python", ["def f(a, b):", "    return a + b"], (1, 0), {})
>>> [c.keys for c in generate(7, 2, [buf])] == [c.keys for c in generate(7, 2, [buf])]
True
"""

import copy
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

CONTENT_DIR: Final = Path(__file__).resolve().parents[3]
ADVERSARIAL_DIR: Final = CONTENT_DIR / "difftest" / "buffers"

_KEY_NAMES: Final = (
    "Esc|CR|Enter|Return|NL|BS|Tab|Space|lt|Bar|Bslash|Del|Insert|Home|End|PageUp|PageDown"
    "|Up|Down|Left|Right|Nul|F[0-9]{1,2}"
)
# Mirror of TOKEN in app/e2e/keys.mjs (and oracle._KEY_TOKEN); test_difftest checks they agree.
_TOKEN: Final = re.compile(rf"<(?:(?:[CSMAD]-)+(?:{_KEY_NAMES}|[^<>\s])|{_KEY_NAMES})>|.", re.I | re.S)

FORBIDDEN: Final = re.compile(
    r"""
      :[\s\d.,$%+\-'<>]*(?:q|wq?|x|e|so|lua|h|b|sp|vs|vi|vne|new|tab|r|sh|te|cq|mk|up|sav)
    | !                               # filters and :! shell commands
    | ZZ | ZQ | gQ | gx | K
    | (?<!g)(?:gg)*g[fF]              # an odd run of g before f is gf (ggfx is gg then fx)
    | q[:/?]                          # command-line window
    | <C-\]> | <C-\^> | <C-z> | <C-i>
    | "[+*=] | <C-r>=                 # clipboard and expression registers
    | <C-w>(?:[qQcCoOnNsSvVxXfFT^]|<C-[qcosnvxf^]>|g[fFt]|\])   # window commands that close, split or open files
    """,
    re.X,
)

WEIGHTS: Final = {
    "edit": 45, "motion": 20, "visual": 10, "ex": 8, "insert": 7, "undo": 4, "dot": 3, "macro": 2, "register": 1,
}
CHANGES: Final = frozenset({"edit", "insert", "visual", "macro", "register"})

_MOTIONS: Final = (
    "h", "j", "k", "l", "w", "b", "e", "ge", "W", "B", "E", "gE", "0", "^", "$", "_", "+", "-",
    "gg", "G", "{", "}", "%", "(", ")", "[{", "]}", "[(", "])", ";", ",", "n", "N", "*", "#",
)
_SCREEN: Final = ("H", "M", "L", "<C-d>", "<C-u>", "<C-f>", "<C-b>", "<C-e>", "<C-y>", "zz", "zt", "zb")
_FINDS: Final = ("f", "F", "t", "T")
_OBJECTS: Final = (
    "iw", "aw", "iW", "aW", 'i"', 'a"', "i'", "a'", "i(", "a(", "ib", "ab", "i[", "a[",
    "i{", "a{", "iB", "aB", "i<", "a<", "ip", "ap", "is", "as", "it", "at",
)
_OPERATORS: Final = ("d", "d", "c", "c", "y", ">", "<", "=", "g~", "gu", "gU")
_DOUBLED: Final = ("dd", "dd", "yy", ">>", "<<", "==", "g~~", "guu", "gUU")
_SIMPLE: Final = (
    "x", "X", "D", "Y", "p", "P", "~", "J", "gJ", "<C-a>", "<C-x>", "xp", "ddp", "]p", "gp", "gP",
)
_PUTS: Final = frozenset({"p", "P", "]p", "gp", "gP"})
_INSERT_ENTRY: Final = ("i", "a", "I", "A", "o", "O")
_INSERT_KEYS: Final = ("<CR>", "<BS>", "<Tab>", "<C-w>")
_PUNCT: Final = "(){}[],;=._ "
_REPLACEMENTS: Final = ("x", "foo", "_", "", "y2")
_REGISTERS: Final = "abc"
_WORD: Final = re.compile(r"[^\W\d]\w*")
_MAX_TRIES: Final = 50


@dataclass(frozen=True)
class Buffer:
    """Start state for one case: ``cursor`` is [line 1-based, column 0-based] as in exercises."""

    id: str
    lang: str
    lines: list[str]
    cursor: tuple[int, int]
    options: dict


@dataclass(frozen=True, slots=True)
class Case:
    """One generated sequence on one buffer; ``(seed, index)`` regenerates it."""

    index: int
    seed: int
    buffer: Buffer
    keys: str


# Public Functions =================================================================================


def tokenize(keys: str) -> list[str]:
    """Split keys in Vim notation into keystrokes, exactly like ``oracle.tokenize_keys``.

    Examples
    --------
    >>> tokenize("ci(x<Esc>")
    ['c', 'i', '(', 'x', '<Esc>']
    """
    return _TOKEN.findall(keys)


def generate(seed: int, count: int, buffers: list[Buffer], max_len: int = 24,
             include_screen: bool = False) -> list[Case]:
    """Generate ``count`` cases, each on a buffer drawn from ``buffers``.

    Parameters
    ----------
    seed
        Run seed; case ``i`` uses ``random.Random(seed * 1_000_003 + i)``.
    count
        Number of cases.
    buffers
        Start buffers (``load_buffers``); must not be empty.
    max_len
        Upper bound on keystrokes per case (tokens, as ``tokenize`` counts them).
    include_screen
        Also emit screen motions (``H M L <C-d> zz`` ...).

    Returns
    -------
    list[Case]
        Cases with ``index`` 0..count-1.
    """
    cases = []
    for i in range(count):
        rng = random.Random(seed * 1_000_003 + i)
        buffer = buffers[rng.randrange(len(buffers))]
        stmts = sequence(rng, buffer, max_len, include_screen)
        cases.append(Case(i, seed, buffer, "".join(keys for _, keys in stmts)))
    return cases


def sequence(rng: random.Random, buffer: Buffer, max_len: int = 24,
             include_screen: bool = False) -> list[tuple[str, str]]:
    """One key sequence as ``(statement kind, keys)`` pairs; ``generate`` joins the keys.

    Re-rolls until the joined keys avoid ``FORBIDDEN``; falls back to ``j``.
    """
    for _ in range(_MAX_TRIES):
        stmts = _statements(rng, buffer, max_len, include_screen)
        if stmts and not FORBIDDEN.search("".join(k for _, k in stmts)):
            return stmts
    return [("motion", "j")]


def load_buffers(build_dir: Path, lang: str, n: int, seed: int, extra_dir: Path | None = None) -> list[Buffer]:
    """A seeded sample of ``n`` distinct exercise start buffers plus every adversarial buffer.

    Parameters
    ----------
    build_dir
        The build output (``build/``, holding ``exercises/<lang>/<skill>/*.json``) or the
        ``exercises`` directory itself. A missing directory contributes no buffers.
    lang
        ``python`` or ``cpp``; adversarial buffers are reused for every language.
    n
        Number of exercise buffers to sample (fewer if the build has fewer distinct ones).
    seed
        Sampling seed.
    extra_dir
        Directory of adversarial ``*.json`` buffers; None means ``content/difftest/buffers``.

    Returns
    -------
    list[Buffer]
        Sampled exercise buffers (ids are exercise ids) then adversarial ones (``adv/<id>``).
    """
    exercises_dir = build_dir / "exercises" if (build_dir / "exercises").is_dir() else build_dir
    sampled = _sample_exercises(exercises_dir / lang, lang, n, seed)
    return sampled + _adversarial(extra_dir or ADVERSARIAL_DIR, lang)


def case_to_json(case: Case) -> dict[str, Any]:
    """Plain-JSON form of a case (``cases.jsonl``, ``findings.jsonl``)."""
    b = case.buffer
    buffer = {"id": b.id, "lang": b.lang, "lines": list(b.lines), "cursor": list(b.cursor), "options": b.options}
    return {"index": case.index, "seed": case.seed, "keys": case.keys, "buffer": buffer}


def case_from_json(d: dict[str, Any]) -> Case:
    """Inverse of ``case_to_json``."""
    b = d["buffer"]
    buffer = Buffer(b["id"], b["lang"], list(b["lines"]), tuple(b["cursor"]), dict(b.get("options") or {}))
    return Case(d["index"], d["seed"], buffer, d["keys"])


# Private Functions ================================================================================


@dataclass
class _State:
    """What earlier statements did, so later ones stay meaningful (``.``, ``@a``, ``'a``)."""

    rng: random.Random
    words: list[str]
    chars: list[str]
    include_screen: bool
    changed: bool = False
    registers: set[str] = field(default_factory=set)
    marks: set[str] = field(default_factory=set)
    searched: bool = False


def _statements(rng: random.Random, buffer: Buffer, max_len: int, include_screen: bool) -> list[tuple[str, str]]:
    words, chars = _vocabulary(buffer.lines)
    st = _State(rng, words, chars, include_screen)
    target = rng.randint(1, max_len)
    stmts: list[tuple[str, str]] = []
    used = 0
    for _ in range(_MAX_TRIES):
        if used >= target:
            break
        saved = copy.copy(st.__dict__)
        saved.update(registers=set(st.registers), marks=set(st.marks))
        kind = _pick_kind(st, WEIGHTS)
        keys = _PRODUCTIONS[kind](st)
        size = len(tokenize(keys))
        if used + size > max_len:
            st.__dict__.update(saved)
            continue
        stmts.append((kind, keys))
        used += size
    return stmts


def _pick_kind(st: _State, weights: dict[str, int]) -> str:
    kinds = [k for k in weights if k != "dot" or st.changed]
    return st.rng.choices(kinds, [weights[k] for k in kinds])[0]


def _vocabulary(lines: list[str]) -> tuple[list[str], list[str]]:
    """Identifier words and single non-space characters in the buffer (minus ``< ! @``)."""
    text = "\n".join(lines)
    words = sorted(set(_WORD.findall(text))) or ["x"]
    chars = sorted({c for c in text if not c.isspace() and c not in "<!@"}) or ["x"]
    return words, chars


def _count(st: _State, p: float = 0.25) -> str:
    return str(st.rng.randint(2, 9)) if st.rng.random() < p else ""


def _word(st: _State, max_chars: int = 6) -> str:
    return st.rng.choice(st.words)[:max_chars]


def _text(st: _State) -> str:
    """Insert-mode text: 0-4 pieces of words, punctuation and editing keys."""
    pieces = []
    for _ in range(st.rng.randint(0, 4)):
        roll = st.rng.random()
        if roll < 0.45:
            pieces.append(_word(st))
        elif roll < 0.75:
            pieces.append(st.rng.choice(_PUNCT))
        else:
            pieces.append(st.rng.choice(_INSERT_KEYS))
    return "".join(pieces)


def _motion(st: _State) -> str:
    rng = st.rng
    roll = rng.random()
    if roll < 0.15:
        return rng.choice(_FINDS) + rng.choice(st.chars)
    if roll < 0.2:
        st.searched = True
        return rng.choice("/?") + _word(st, 4) + "<CR>"
    if roll < 0.24 and st.marks:
        return rng.choice("'`") + rng.choice(sorted(st.marks))
    if roll < 0.3 and st.include_screen:
        return rng.choice(_SCREEN)
    motion = rng.choice(_MOTIONS)
    if motion == "0":
        return motion
    return _count(st) + motion


def _target(st: _State) -> str:
    """What an operator acts on: a motion (with a count) or a text object."""
    if st.rng.random() < 0.4:
        return _count(st, 0.15) + st.rng.choice(_OBJECTS)
    return _motion(st)


def _edit(st: _State) -> str:
    rng = st.rng
    register_filled, st.changed = st.changed, True
    roll = rng.random()
    if roll < 0.4:
        op = rng.choice(_OPERATORS)
        keys = _count(st) + op + _target(st)
        return keys + _text(st) + "<Esc>" if op == "c" else keys
    if roll < 0.55:
        return _count(st) + rng.choice(_DOUBLED)
    if roll < 0.65:
        return _count(st) + rng.choice(("cc", "C", "s", "S")) + _text(st) + "<Esc>"
    if roll < 0.72:
        return _count(st) + "r" + rng.choice(st.chars)
    if roll < 0.77:
        return "R" + _text(st) + "<Esc>"
    simple = rng.choice(_SIMPLE)
    if simple in _PUTS and not register_filled:
        simple = "x"  # E353 "Nothing in register" would make the case an artefact (class c)
    return _count(st) + simple


def _motion_stmt(st: _State) -> str:
    if st.rng.random() < 0.05:
        mark = st.rng.choice(_REGISTERS)
        st.marks.add(mark)
        return "m" + mark
    return _motion(st)


def _visual(st: _State) -> str:
    rng = st.rng
    start = rng.choice(("v", "v", "V", "<C-v>"))
    keys = start
    for _ in range(rng.randint(1, 2)):
        use_object = start != "<C-v>" and rng.random() < 0.3
        keys += rng.choice(_OBJECTS) if use_object else _motion(st)
    roll = rng.random()
    if roll < 0.1:
        return keys + "<Esc>"
    st.changed = True
    if roll < 0.15:
        return keys + "o" + _motion(st) + "d"
    if roll < 0.25 and start == "<C-v>":
        return keys + rng.choice("IA") + _text(st) + "<Esc>"
    if roll < 0.3:
        return keys + ":s/" + _word(st, 3) + "/" + rng.choice(_REPLACEMENTS) + "/<CR>"
    if roll < 0.4:
        return keys + "r" + rng.choice(st.chars)
    end = rng.choice(("d", "d", "c", "y", ">", "<", "~", "u", "U", "J", "gU", "gu", "="))
    return keys + end + _text(st) + "<Esc>" if end == "c" else keys + end


def _ex(st: _State) -> str:
    rng = st.rng
    pat, rep, n = _word(st, 4), rng.choice(_REPLACEMENTS), str(rng.randint(1, 4))
    command = rng.choice((
        f"s/{pat}/{rep}/", f"s/{pat}/{rep}/g", f"%s/{pat}/{rep}/g", f"g/{pat}/d", f"v/{pat}/d",
        f"g/{pat}/norm A;", "%norm A;", "m+1", "m-2", "m0", "m$", "t.", "t0",
        f".,+{n}j", f".,+{n}d", f".,+{n}>", f".,+{n}t.", n,
    ))
    return ":" + command + "<CR>"


def _insert(st: _State) -> str:
    st.changed = True
    return st.rng.choice(_INSERT_ENTRY) + _text(st) + "<Esc>"


def _undo(st: _State) -> str:
    return st.rng.choices(("u", "<C-r>", "U"), (6, 3, 1))[0] if st.rng.random() < 0.85 else _count(st, 1.0) + "u"


def _dot(st: _State) -> str:
    return _count(st, 0.2) + "."


def _macro(st: _State) -> str:
    """Record ``q{r}`` with 1-2 body statements (never ``@``), then replay ``[N]@{r}``."""
    rng = st.rng
    reg = rng.choice(_REGISTERS)
    body_weights = {"edit": 6, "motion": 3, "insert": 2}
    body = "".join(_PRODUCTIONS[_pick_kind(st, body_weights)](st) for _ in range(rng.randint(1, 2)))
    st.registers.add(reg)
    return "q" + reg + body + "q" + _count(st, 0.3) + "@" + reg


def _register(st: _State) -> str:
    rng = st.rng
    roll = rng.random()
    if roll < 0.15:
        st.changed = True
        return '"_' + rng.choice(("dd", "dw", "x"))
    st.changed = True
    if roll < 0.25:
        return '"0' + rng.choice("pP")
    if roll < 0.3:
        return '"' + str(rng.randint(1, 9)) + "p"
    if st.registers and roll < 0.55:
        reg = rng.choice(sorted(st.registers))
        if rng.random() < 0.3:
            return "i<C-r>" + reg + "<Esc>"
        return '"' + reg + rng.choice("pP")
    reg = rng.choice(_REGISTERS)
    prefix = reg.upper() if reg in st.registers and rng.random() < 0.3 else reg
    st.registers.add(reg)
    return '"' + prefix + rng.choice(("yy", "yiw", "dd", "dw", "y$"))


_PRODUCTIONS: Final = {
    "edit": _edit, "motion": _motion_stmt, "visual": _visual, "ex": _ex, "insert": _insert,
    "undo": _undo, "dot": _dot, "macro": _macro, "register": _register,
}


def _sample_exercises(lang_dir: Path, lang: str, n: int, seed: int) -> list[Buffer]:
    """Distinct start buffers under ``lang_dir``, sampled with ``random.Random(seed)``."""
    seen: dict[tuple[str, ...], Buffer] = {}
    for path in sorted(lang_dir.glob("**/*.json")):
        ex = json.loads(path.read_text())
        lines = ex["start"]["lines"]
        seen.setdefault(tuple(lines), Buffer(ex["id"], lang, list(lines), tuple(ex["start"]["cursor"]), {}))
    pool = list(seen.values())
    return random.Random(seed).sample(pool, min(n, len(pool)))


def _adversarial(directory: Path, lang: str) -> list[Buffer]:
    buffers = []
    for path in sorted(directory.glob("*.json")):
        d = json.loads(path.read_text())
        buffers.append(Buffer(f"adv/{d['id']}", lang, list(d["lines"]), tuple(d["cursor"]), dict(d.get("options") or {})))
    return buffers
