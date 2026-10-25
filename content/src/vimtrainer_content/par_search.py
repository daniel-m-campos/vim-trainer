"""Best-par search: try a small library of idioms per skill and keep the shortest that passes.

Idioms are key templates with ``{{name}}`` placeholders. ``{{...}}`` is used instead of
``str.format`` braces or ``$name`` because ``{``, ``}`` and ``$`` are Vim motions.
Values come from the exercise's optional ``params`` object plus a few derived from the
exercise itself (see ``_context``). A list value expands into one candidate per item.
A template whose placeholder has no value is skipped.

Derived first characters let one idiom serve every sibling exercise: ``{{old0}}`` is the
first character of ``old``, the text the first ``target`` range covers on the start lines,
and ``{{text0}}`` the first character of ``params["text"]``. ``ingest.generalise`` writes
them for the character after ``f t F T``, so a player's ``fTcwFalse<Esc>`` is learned as
``f{{old0}}cw{{text}}<Esc>``.

Player-found idioms in ``content/idioms_learned.toml`` (written by ``vimtrainer-content
ingest``) are merged into ``IDIOMS`` at import, after the built-in ones. A learned
idiom's ``{{k}}`` stands for a count and expands to 1-9, the same count at every
``{{k}}``. Entries with ``status = "rejected"`` are skipped.

The canonical solution and its alternates are always candidates. If a candidate beats
the canonical by more than ``FLAG_MARGIN`` keystrokes, the result is flagged for review
(quality gate 4); the canonical is never replaced silently.

Examples
--------
>>> from vimtrainer_content import oracle
>>> ex = oracle.load_exercise("examples/py_t.paren_0001.json")
>>> best_par(ex, oracle.subprocess_runner()).best.keys
'$di('
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import re
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from vimtrainer_content import oracle, sources

FLAG_MARGIN: Final = 1
LEARNED_TOML: Final = sources.CONTENT_DIR / "idioms_learned.toml"
LEARNED_COUNTS: Final = range(1, 10)
_PLACEHOLDER: Final = re.compile(r"\{\{(\w+)\}\}")

_BUILTIN_IDIOMS: Final[dict[str, tuple[str, ...]]] = {
    "t.quote": (
        'ci"{{text}}<Esc>', "ci'{{text}}<Esc>", 'f"ci"{{text}}<Esc>', 'F"ci"{{text}}<Esc>',
        'di"i{{text}}<Esc>', 'f"lct"{{text}}<Esc>',
    ),
    "t.paren": (
        "di(", "dib", "f(di(", "$di(", "%di(", "f(%di(", "f(ldt)", "f)di(", "t)di(",
        "ci({{text}}<Esc>", "f(ci({{text}}<Esc>", "$ci({{text}}<Esc>", "f(lct){{text}}<Esc>",
    ),
    "m.rel": (
        "{{down}}j", "{{up}}k", "{{down}}+", "{{up}}-", "{{down}}<CR>", "{{line}}G", "{{line}}gg",
        ":{{line}}<CR>", "}", "{", "G", "gg", "L", "M", "H", "]]", "[[",
    ),
    "m.find": (
        "{{n}}f{{char}}", "f{{char}}{{repeat}}", "{{n}}t{{char}}l", "t{{char}}{{repeat}}l",
        "F{{char}}", "$F{{char}}", "/{{char_escaped}}<CR>{{nrepeat}}",
    ),
    "x.global": (":g/{{pattern_prefix}}/d<CR>", ":g/{{pattern_prefix}}/d_<CR>"),
    # Skill-level libraries for the generated corpus. Templates add their own concrete
    # idioms (templates.Draft.idioms); these are the shared, skill-wide alternatives.
    # Patterns are whole identifiers only: prefix golf (`:%s/cou/n/g` for `count`) is not
    # tried, so a canonical is never rejected for using a readable pattern.
    "x.subst": (
        ":%s/{{old}}/{{new}}/g<CR>", ":%s/\\<{{old}}\\>/{{new}}/g<CR>", ":%s/{{old}}/{{new}}<CR>",
        ":s/{{old}}/{{new}}/g<CR>", ":g/{{old}}/s//{{new}}/g<CR>",
    ),
    "t.word": ("ciw{{text}}<Esc>", "cw{{text}}<Esc>", "bcw{{text}}<Esc>", "caw{{text}}<Esc>"),
    "t.bracket": ("ci[{{text}}<Esc>", "di[", "da[", "f[ci[{{text}}<Esc>", "F[ci[{{text}}<Esc>"),
    "t.brace": ("ci{{{text}}<Esc>", "di{", "f{ci{{{text}}<Esc>", "F{ci{{{text}}<Esc>"),
    "o.case": ("gUiw", "guiw", "g~iw", "gUe", "bgUe", "gue", "bgue"),
    "o.change": ("C{{text}}<Esc>", "cw{{text}}<Esc>", "ce{{text}}<Esc>", "cW{{text}}<Esc>"),
    "o.delete": ("D", "dd", "dap", "dip", "d}"),
    "o.indent": (">>", "<<", ">}", "<}", ">ip", "<ip"),
    "m.match": ("%",),
    "n.unmatched": ("])", "]}", "[(", "[{", "%"),
    "x.copymove": (":m+1<CR>", ":m-2<CR>", ":t.<CR>", "yyp", "yyP", "ddp", "ddkP", "yyjp", "yykP", "yy2jp", "yy2kP", "dd2jp", "dd2kP"),
}


def load_learned(path: pathlib.Path = LEARNED_TOML) -> dict[str, tuple[str, ...]]:
    """Learned idioms per skill from ``idioms_learned.toml``, with ``{{k}}`` expanded to counts."""
    if not path.exists():
        return {}
    learned: dict[str, list[str]] = {}
    for entry in tomllib.loads(path.read_text()).get("idiom", []):
        if entry.get("status") == "rejected":
            continue
        keys = entry["keys"]
        expanded = [keys.replace("{{k}}", str(k)) for k in LEARNED_COUNTS] if "{{k}}" in keys else [keys]
        learned.setdefault(entry["skill"], []).extend(expanded)
    return {skill: tuple(dict.fromkeys(keys)) for skill, keys in learned.items()}


def merge_idioms(builtin: dict[str, tuple[str, ...]], learned: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """Built-in idioms first, then learned ones, de-duplicated per skill."""
    skills = dict.fromkeys([*builtin, *learned])
    return {s: tuple(dict.fromkeys([*builtin.get(s, ()), *learned.get(s, ())])) for s in skills}


LEARNED: Final = load_learned()
IDIOMS: Final = merge_idioms(_BUILTIN_IDIOMS, LEARNED)


@dataclass(frozen=True)
class ParResult:
    """Outcome of a best-par search for one exercise."""

    exercise_id: str
    canonical: oracle.Verdict
    best: oracle.Verdict | None
    passing: list[oracle.Verdict]
    tried: int

    @property
    def flagged(self) -> bool:
        """True when a candidate beats a passing canonical by more than FLAG_MARGIN keys."""
        if self.best is None or not self.canonical.passed:
            return self.best is not None
        return self.canonical.count - self.best.count > FLAG_MARGIN


# Public Functions =================================================================================


def learned_keys(exercise: oracle.Exercise) -> list[str]:
    """Learned idioms of the exercise's skill, expanded for it; build.evaluate adds them as canonical variants."""
    ctx = _context(exercise)
    return list(dict.fromkeys(k for t in LEARNED.get(exercise["skill"], ()) for k in _expand(t, ctx)))


def target_text(exercise: oracle.Exercise) -> str:
    """The start-lines text under the exercise's first ``target`` range, or ``""``.

    Ranges are ``{"start": [line, col], "end": [line, col]}`` with 1-based lines and
    0-based columns, inclusive at both ends (``templates._range``). A range spanning
    several lines yields its first line from the start column on.

    Examples
    --------
    >>> target_text({"start": {"lines": ["f(reverse=True)"]},
    ...              "target": [{"start": [1, 10], "end": [1, 13]}]})
    'True'
    """
    target = exercise.get("target") or []
    lines = (exercise.get("start") or {}).get("lines") or []
    if not target or not 1 <= target[0]["start"][0] <= len(lines):
        return ""
    (sl, sc), (el, ec) = target[0]["start"], target[0]["end"]
    line = lines[sl - 1]
    return line[sc:ec + 1] if el == sl else line[sc:]


def candidates(exercise: oracle.Exercise) -> list[str]:
    """Candidate key strings for an exercise: canonical, alternates, then expanded idioms.

    Returns
    -------
    list[str]
        De-duplicated, in first-seen order, canonical first.
    """
    seeds = [exercise["par"]["keys"], *exercise.get("alternates", [])]
    ctx = _context(exercise)
    expanded = (k for t in IDIOMS.get(exercise["skill"], ()) for k in _expand(t, ctx))
    return list(dict.fromkeys(itertools.chain(seeds, expanded)))


def best_par(exercise: oracle.Exercise, runner: oracle.Runner) -> ParResult:
    """Replay every candidate and return the shortest passing one.

    Parameters
    ----------
    exercise
        Exercise dict with ``skill``, ``par.keys`` and optional ``params``.
    runner
        An oracle runner; ``oracle.subprocess_runner()`` replays all candidates in one
        Neovim process, ``PynvimSession.run`` reuses a long-lived one.

    Returns
    -------
    ParResult
        ``best`` is the shortest passing candidate; ties keep the earlier candidate,
        so the canonical wins ties.
    """
    keys = candidates(exercise)
    verdicts = oracle.verify_many([(exercise, k) for k in keys], runner)
    passing = [v for v in verdicts if v.passed]
    best = min(passing, key=lambda v: v.count, default=None)
    return ParResult(exercise.get("id", "?"), verdicts[0], best, passing, len(keys))


def main(argv: Sequence[str] | None = None) -> int:
    """CLI: search best pars; ``--write`` stores the canonical count and verified stamp."""
    args = _parse_args(argv)
    runner = oracle.subprocess_runner()
    flagged = 0
    for path in args.files:
        exercise = oracle.load_exercise(path)
        result = best_par(exercise, runner)
        flagged += result.flagged
        _report(result)
        if args.write and result.canonical.passed:
            _write_par(pathlib.Path(path), exercise, result.canonical)
    return 1 if flagged and args.strict else 0


# Private Functions ================================================================================


def _context(exercise: oracle.Exercise) -> dict[str, Any]:
    """Placeholder values: exercise params plus values derived from start/expect/target."""
    ctx: dict[str, Any] = dict(exercise.get("params") or {})
    old = target_text(exercise)
    if old:
        ctx["old0"] = old[0]
    if isinstance(ctx.get("text"), str) and ctx["text"]:
        ctx["text0"] = ctx["text"][0]
    target = (exercise.get("expect") or {}).get("cursor")
    if target:
        delta = target[0] - exercise["start"]["cursor"][0]
        ctx["line"] = target[0]
        ctx.update({"down": delta} if delta > 0 else {"up": -delta} if delta < 0 else {})
    if "n" in ctx:
        ctx["repeat"] = ";" * (ctx["n"] - 1)
        ctx["nrepeat"] = "n" * (ctx["n"] - 1)
    if "char" in ctx:
        ctx["char_escaped"] = "\\" + ctx["char"] if ctx["char"] in r".*[]~\/^$" else ctx["char"]
    if "pattern" in ctx:
        pattern = ctx["pattern"]
        ctx["pattern_prefix"] = [pattern[:i] for i in range(1, len(pattern) + 1)]
    return ctx


def _expand(template: str, ctx: dict[str, Any]) -> list[str]:
    names = list(dict.fromkeys(_PLACEHOLDER.findall(template)))
    if any(n not in ctx for n in names):
        return []
    choices = [ctx[n] if isinstance(ctx[n], list) else [ctx[n]] for n in names]
    return [_fill(template, dict(zip(names, combo))) for combo in itertools.product(*choices)]


def _fill(template: str, values: dict[str, Any]) -> str:
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), template)


def _report(result: ParResult):
    canon = result.canonical
    best = result.best
    best_txt = f"{best.keys!r} ({best.count})" if best else "none"
    flag = "  FLAG: canonical beaten" if result.flagged else ""
    status = "ok" if canon.passed else f"CANONICAL FAILS: {canon.reason}"
    print(f"{result.exercise_id:<20} canonical {canon.keys!r} ({canon.count}) {status}; "
          f"best {best_txt}; {len(result.passing)}/{result.tried} pass{flag}")


def _write_par(path: pathlib.Path, exercise: oracle.Exercise, canonical: oracle.Verdict):
    exercise["par"]["count"] = canonical.count
    exercise["par"]["verified"] = oracle.verified_stamp()
    path.write_text(json.dumps(exercise, indent=2) + "\n")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vimtrainer-par", description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", help="exercise JSON files")
    parser.add_argument("--write", action="store_true", help="store par.count and par.verified")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any canonical is beaten")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
