"""``vimtrainer-content ingest``: verify player key sequences in Neovim and fold them into pars.

The input is either an exported progress file (Settings > export: a ``Saved`` JSON whose
``model.log`` holds attempt records with ``ex``, ``ok``, ``seq``, ``beatPar`` and ``flag``)
or the body of a GitHub issue opened by the app's ``!`` flag (``app/src/feedback.ts``),
saved to a text file. Issue bodies are read leniently as ``label: value`` lines.

What happens to each record:

- ``beatPar``, or ``flag.reason`` ``"wrong-par"`` / ``"emulator"``: the player's ``seq`` is
  replayed in Neovim on the exercise in ``build/`` (``oracle.verify_many``).

  - passes in fewer keys than par: ``seq`` becomes ``par.keys``, the old canonical moves
    to ``alternates``, and the generalised idiom (see ``generalise``) is appended to
    ``content/idioms_learned.toml`` under the skill;
  - passes in as many keys or more: ``seq`` is appended to ``alternates``, and its idiom
    is appended to ``content/idioms_learned.toml`` too, so the alternate survives a rebuild;
  - fails although the app accepted it (or the issue does not say): an entry in
    ``review/emulator-divergences.md``. A ``seq`` that both reject is only logged;
  - passes although the app rejected it: also an emulator divergence (the browser
    rejected a real solution, the copy_line bug class).

- ``flag.reason`` ``"wording"``: ``review/wording-queue.md``, grouped by template.

Every run appends a dated section to ``review/ingest-log.md``.

Durability. ``make content`` regenerates ``build/`` from scratch, so the edits to
``build/`` JSON last until the next rebuild (and ``make content-check`` fails until
``make content`` is run). What survives is ``idioms_learned.toml``. ``build.evaluate``
adds every learned idiom whose status is not ``"rejected"`` (``"new"`` included) to the
template's variants, after the template's own. So on a rebuild a learned idiom that is
shorter than the template's canonical becomes the canonical par, and one that ties or is
longer becomes an alternate. Reviewing the toml diff before ``make content`` is the
safeguard. An idiom counts as already known only when ``idioms_learned.toml`` lists it;
a built-in idiom (``par_search``) is only a candidate in the build, never a variant, so a
player's built-in idiom is written to the toml as well.
"""

from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final

from vimtrainer_content import build, oracle, par_search, sources

REVIEW_DIR: Final = sources.CONTENT_DIR / "review"
VERIFY_REASONS: Final = ("wrong-par", "emulator")
ESCAPES: Final = ("<Esc>", "<C-[>", "<C-c>")
INSERT_KEYS: Final = frozenset("iaIAoOsSCR")  # Normal-mode keys that start typing text
VISUAL_INSERT_KEYS: Final = frozenset("cCsSRIA")
OPERATORS: Final = frozenset("cdy<>=!")
CHAR_ARG_KEYS: Final = frozenset("fFtTrm'`\"@")  # keys whose next key is a character, not a command
NUMERIC_PLACEHOLDERS: Final = frozenset({"k", "n", "down", "up", "line"})

_PLACEHOLDER_SPLIT: Final = re.compile(r"(\{\{\w+\}\})")
_ISSUE_LINE: Final = re.compile(r"^[\s>*-]*([A-Za-z][A-Za-z ]*?)\s*(?:\(([^)]*)\))?\s*:\**\s*(.*)$")
_DIVERGENCES_HEADER: Final = (
    "# Emulator divergences\n\n"
    "Written by `vimtrainer-content ingest`: player key sequences where the browser emulator\n"
    "and real Neovim disagree. Each entry is a candidate bug in `app/src/vimfixes.ts` or in\n"
    "codemirror-vim; delete it once fixed or explained.\n"
)
_WORDING_HEADER: Final = (
    "# Wording queue\n\n"
    "Written by `vimtrainer-content ingest` from players' `wording` flags, grouped by template.\n"
    "Fix the template in `templates.py` (or `lang/*.py`), then delete the entries.\n"
)
_LOG_HEADER: Final = "# Ingest log\n\nOne section per `vimtrainer-content ingest` run.\n"


@dataclass(frozen=True)
class Record:
    """One attempt to ingest; ``ok`` is None when the source does not say."""

    ex: str
    seq: str
    ok: bool | None
    beat_par: bool
    reason: str | None
    note: str

    @property
    def wants_verify(self) -> bool:
        """True when the seq should be replayed in Neovim."""
        return bool(self.seq) and (self.beat_par or self.reason in VERIFY_REASONS)


# Public Functions =================================================================================


def parse(text: str) -> list[Record]:
    """Records from an export (``Saved`` JSON or a bare list of records) or an issue body."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        record = parse_issue(text)
        return [record] if record else []
    log = data.get("model", {}).get("log", []) if isinstance(data, dict) else data
    return [_from_log(r) for r in log if isinstance(r, dict) and r.get("ex")]


def parse_issue(text: str) -> Record | None:
    """One record from a ``!`` flag issue body; None without an exercise id.

    Labels are matched case-insensitively: ``exercise`` (or ``exercise id``, ``id``),
    ``player keys`` (or ``player seq``, ``seq``, ``keys``), ``reason``, ``note``. A
    value in backticks is taken from between the first and last backtick. ``(…,
    correct)`` or ``(…, gave up)`` after ``player keys`` sets ``ok``.
    """
    fields: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        m = _ISSUE_LINE.match(line)
        if m:
            fields.setdefault(m.group(1).strip().lower(), (m.group(2) or "", m.group(3).strip()))
    ex = _first(fields, "exercise", "exercise id", "id")
    if not ex:
        return None
    seq_paren, seq = next((fields[k] for k in ("player keys", "player seq", "seq", "keys") if k in fields), ("", ""))
    ok = True if "correct" in seq_paren else False if "gave up" in seq_paren else None
    note = _first(fields, "note")
    return Record(
        ex=_unquote(ex).split()[0], seq=_unquote(seq), ok=ok, beat_par=False,
        reason=_first(fields, "reason") or None, note="" if note == "(none)" else note,
    )


def generalise(keys: str) -> str:
    """The idiom behind a key sequence: counts become ``{{k}}``, typed text ``{{text}}``.

    A count is a digit run in Normal mode (``0`` alone is a motion) or any digit run on a
    ``:`` line. Text typed after an insert-entering key (``i a I A o O s S C R``, ``c`` plus
    its motion, ``c``/``s``/``I``/``A`` in Visual mode) up to ``<Esc>`` becomes
    ``{{text}}``, unless it holds special keys such as ``<BS>``. Characters after ``f t F
    T r m ' ` " @ q`` and search patterns are kept as typed. Placeholders already in
    ``keys`` are kept; numeric ones (``{{down}}``, ``{{n}}``...) become ``{{k}}``.

    Examples
    --------
    >>> generalise('yy2jp'), generalise('ci"retrying %s<Esc>'), generalise('2f2')
    ('yy{{k}}jp', 'ci"{{text}}<Esc>', '{{k}}f2')
    """
    toks = _tokens(keys)
    out: list[str] = []
    i, visual, recording = 0, False, False
    while i < len(toks):
        t = toks[i]
        if t.isdigit() and t != "0":
            i = _count(toks, i, out)
        elif t.startswith("{{"):
            out.append("{{k}}" if t[2:-2] in NUMERIC_PLACEHOLDERS else t)
            i += 1
        elif t == ":":
            end = _until(toks, i + 1, "<CR>")
            out.append(":" + re.sub(r"\d+", "{{k}}", "".join(toks[i + 1:end])))
            i = end
        elif t in "/?":
            end = _until(toks, i + 1, "<CR>")
            out.extend(toks[i:end])
            i = end
        elif t == "q":
            out.extend(toks[i:i + (1 if recording else 2)])
            i += 1 if recording else 2
            recording = not recording
        elif t in CHAR_ARG_KEYS:
            out.extend(toks[i:i + 2])
            i += 2
        elif t in ("v", "V", "<C-v>"):
            out.append(t)
            visual, i = not visual, i + 1
        elif visual and t in VISUAL_INSERT_KEYS:
            out.append(t)
            visual, i = False, _insert(toks, i + 1, out)
        elif visual and t in "ia":
            out.extend(toks[i:i + 2])
            i += 2
        elif t == "g":
            out.extend(toks[i:i + 2])
            second = toks[i + 1] if i + 1 < len(toks) else ""
            i = _motion(toks, i + 2, "", out) if second in "~uUq?w" and second else i + 2
        elif not visual and t in INSERT_KEYS:
            out.append(t)
            i = _insert(toks, i + 1, out)
        elif not visual and t in OPERATORS:
            out.append(t)
            i = _motion(toks, i + 1, t, out)
            if t == "c":
                i = _insert(toks, i, out)
        else:
            out.append(t)
            visual = visual and t not in ("<Esc>", *"dyx<>~uUJ")
            i += 1
    return "".join(out)


def ingest(
    path: pathlib.Path, out: pathlib.Path = build.DEFAULT_OUT, review_dir: pathlib.Path = REVIEW_DIR,
    learned_toml: pathlib.Path = par_search.LEARNED_TOML, runner: oracle.Runner | None = None,
    today: datetime.date | None = None, log: Callable[[str], None] = print,
) -> list[str]:
    """Ingest one export or issue file; see the module docstring. Returns the log lines."""
    today = today or datetime.date.today()
    records = parse(path.read_text())
    exercises: dict[str, tuple[pathlib.Path, dict[str, Any]] | None] = {}
    for rec in records:
        if rec.ex not in exercises:
            found = _find_exercise(out, rec.ex)
            exercises[rec.ex] = (found, oracle.load_exercise(found)) if found else None

    lines: list[str] = []
    to_verify = list({(r.ex, r.seq): r for r in records if r.wants_verify}.values())
    jobs = [(r, *exercises[r.ex]) for r in to_verify if exercises[r.ex]]
    lines += [f"- `{r.ex}` {_code(r.seq)}: exercise not in {out.name}/ (rebuilt away?)"
              for r in to_verify if not exercises[r.ex]]
    verdicts = oracle.verify_many([(ex, r.seq) for r, _, ex in jobs], runner or oracle.subprocess_runner()) if jobs else []
    stamp = oracle.verified_stamp(today) if jobs else ""
    dirty: set[str] = set()
    divergences: list[str] = []
    known_idioms = _known_idioms(learned_toml)
    for (rec, _, ex), verdict in zip(jobs, verdicts, strict=True):
        line, changed, divergence, idiom = _apply(rec, ex, verdict, stamp, known_idioms)
        lines.append(line)
        if changed:
            dirty.add(rec.ex)
        if divergence:
            divergences.append(divergence)
        if idiom:
            known_idioms.setdefault(ex["skill"], set()).add(idiom)
            _append(learned_toml, "", _idiom_entry(ex["skill"], idiom, rec, today))
    for ex_id in sorted(dirty):
        ex_path, ex = exercises[ex_id]
        ex_path.write_text(json.dumps(ex, indent=2) + "\n")

    wording = [r for r in records if r.reason == "wording"]
    queue = review_dir / "wording-queue.md"
    section = _wording_section(wording, exercises, path, today, _read(queue))
    if section:
        _append(queue, _WORDING_HEADER, section)
    lines += [f"- `{r.ex}`: wording flag -> wording-queue.md" for r in wording]
    lines += [f"- `{r.ex}`: {r.reason} flag ({r.note or 'no note'}), no action" for r in records
              if r.reason and r.reason not in (*VERIFY_REASONS, "wording")]
    known_divergences = _read(review_dir / "emulator-divergences.md")
    divergences = [d for d in dict.fromkeys(divergences) if d not in known_divergences]
    if divergences:
        _append(review_dir / "emulator-divergences.md", _DIVERGENCES_HEADER, "".join(divergences))

    summary = (f"{len(records)} records from `{path.name}`: {len(to_verify)} sequences to verify, "
               f"{len(wording)} wording flags, {len(dirty)} exercises updated, {len(divergences)} divergences")
    _append(review_dir / "ingest-log.md", _LOG_HEADER, f"\n## {today.isoformat()}\n\n{summary}\n\n"
            + "".join(f"{ln}\n" for ln in lines))
    for ln in [summary, *lines]:
        log(ln)
    return lines


# Private Functions ================================================================================


def _from_log(r: dict[str, Any]) -> Record:
    flag = r.get("flag") or {}
    return Record(r["ex"], r.get("seq") or "", r.get("ok"), bool(r.get("beatPar")), flag.get("reason"),
                  flag.get("note") or "")


def _first(fields: dict[str, tuple[str, str]], *labels: str) -> str:
    return next((fields[k][1] for k in labels if k in fields), "")


def _unquote(value: str) -> str:
    """Text between the first and last backtick, else the value itself."""
    first, last = value.find("`"), value.rfind("`")
    return value[first + 1:last] if 0 <= first < last else value


def _tokens(keys: str) -> list[str]:
    """Key tokens, with each ``{{name}}`` placeholder kept as one token."""
    parts = _PLACEHOLDER_SPLIT.split(keys)
    return [tok for n, part in enumerate(parts) for tok in ([part] if n % 2 else oracle.tokenize_keys(part))]


def _until(toks: list[str], i: int, stop: str) -> int:
    """Index just past the first ``stop`` at or after ``i`` (or the end)."""
    while i < len(toks) and toks[i] != stop:
        i += 1
    return min(i + 1, len(toks))


def _count(toks: list[str], i: int, out: list[str]) -> int:
    while i < len(toks) and toks[i].isdigit():
        i += 1
    out.append("{{k}}")
    return i


def _motion(toks: list[str], i: int, op: str, out: list[str]) -> int:
    """Append the motion after an operator (with its count) and return the index past it."""
    if i < len(toks) and toks[i].isdigit() and toks[i] != "0":
        i = _count(toks, i, out)
    if i >= len(toks):
        return i
    t = toks[i]
    if t in ("/", "?"):
        end = _until(toks, i + 1, "<CR>")
    elif t in ("i", "a", "g", *"fFtT'`"):
        end = i + 2
    else:
        end = i + 1  # includes the doubled operator: dd, cc, yy, >>
    out.extend(toks[i:end])
    return end


def _insert(toks: list[str], i: int, out: list[str]) -> int:
    """Append typed text (as ``{{text}}`` when plain) and its ``<Esc>``; return the index past it."""
    end = i
    while end < len(toks) and toks[end] not in ESCAPES:
        end += 1
    text = toks[i:end]
    plain = text and not any(len(t) > 1 and t.startswith("<") for t in text)
    out.extend(["{{text}}"] if plain else text)
    out.extend(toks[end:end + 1])
    return end + 1


def _find_exercise(out: pathlib.Path, ex_id: str) -> pathlib.Path | None:
    """``build/exercises/<lang>/<skill>/<uid>.json`` for an id such as ``py/t.quote/0001``."""
    parts = ex_id.split("/")
    if len(parts) != 3:
        return None
    return next(iter(sorted((out / "exercises").glob(f"*/{parts[1]}/{parts[2]}.json"))), None)


def _apply(
    rec: Record, ex: dict[str, Any], verdict: oracle.Verdict, stamp: str, known: dict[str, set[str]],
) -> tuple[str, bool, str, str]:
    """Fold one verdict into the exercise. Returns (log line, changed, divergence entry, new idiom)."""
    par = ex["par"]["count"]
    head = f"- `{rec.ex}` {_code(rec.seq)} ({verdict.count} keys, par {par})"
    app = "app: ok" if rec.ok else "app: rejected" if rec.ok is False else "app: not stated"
    if not verdict.passed:
        if rec.ok is False:
            return f"{head}: nvim and app both reject it ({verdict.reason})", False, "", ""
        return f"{head}: nvim fails ({verdict.reason}) -> emulator-divergences.md", False, \
            _divergence(rec, ex, verdict, app), ""
    divergence = _divergence(rec, ex, verdict, app) if rec.ok is False else ""
    note = " (app rejected it -> emulator-divergences.md)" if divergence else ""
    if verdict.keys == ex["par"]["keys"] or verdict.keys in ex.get("alternates", []):
        return f"{head}: passes, already known{note}", False, divergence, ""
    idiom = generalise(verdict.keys)
    fresh = idiom not in known.get(ex["skill"], set())
    if verdict.count >= par:
        ex["alternates"] = [*ex.get("alternates", []), verdict.keys]
        dest = f"idiom {_code(idiom)} -> idioms_learned.toml" if fresh else f"idiom {_code(idiom)} already known"
        return f"{head}: passes -> alternates; {dest}{note}", True, divergence, idiom if fresh else ""
    old = ex["par"]["keys"]
    _promote(ex, verdict, stamp)
    if not fresh:
        return f"{head}: new canonical; {_code(old)} -> alternates; idiom {_code(idiom)} already known{note}", \
            True, divergence, ""
    return f"{head}: new canonical; {_code(old)} -> alternates; idiom {_code(idiom)} -> idioms_learned.toml{note}", \
        True, divergence, idiom


def _promote(ex: dict[str, Any], verdict: oracle.Verdict, stamp: str):
    """Make ``verdict.keys`` the canonical; the old canonical becomes the first alternate."""
    old = ex["par"]
    ex["alternates"] = [k for k in dict.fromkeys([old["keys"], *ex.get("alternates", [])]) if k != verdict.keys]
    ex["par"] = {"keys": verdict.keys, "count": verdict.count, "verified": stamp}
    if "best" in old and old["best"]["count"] < verdict.count:
        ex["par"]["best"] = old["best"]
    if "emulator" in ex:
        ex["emulator"]["web"] = "unverified"  # the browser replayed the old canonical


def _known_idioms(learned_toml: pathlib.Path) -> dict[str, set[str]]:
    """Learned idioms per skill, including rejected ones (see Durability in the module docstring)."""
    known: dict[str, set[str]] = {}
    if learned_toml.exists():
        for entry in tomllib.loads(learned_toml.read_text()).get("idiom", []):
            known.setdefault(entry["skill"], set()).add(entry["keys"])
    return known


def _idiom_entry(skill: str, idiom: str, rec: Record, today: datetime.date) -> str:
    fields = {"skill": skill, "keys": idiom, "seq": rec.seq, "from": rec.ex, "added": today.isoformat(), "status": "new"}
    return "\n[[idiom]]\n" + "".join(f"{k} = {json.dumps(v)}\n" for k, v in fields.items())


def _divergence(rec: Record, ex: dict[str, Any], verdict: oracle.Verdict, app: str) -> str:
    out = verdict.outcome
    parts = [
        f"\n## `{rec.ex}` ({ex['lang']}, {ex['kind']})\n",
        f"- seq: {_code(rec.seq)} ({verdict.count} keys; par {_code(ex['par']['keys'])}, {ex['par']['count']})",
        f"- {app}; flag: {rec.reason or 'none'}{f' ({rec.note})' if rec.note else ''}",
        f"- nvim: {'pass' if verdict.passed else 'FAIL'} ({verdict.reason})"
        + (f"; mode {out.mode}, cursor {out.cursor}" if out else ""),
    ]
    if out and not verdict.passed and ex["kind"] != oracle.Kind.CURSOR:
        expect = ex["expect"]["lines"]
        row = next((n for n, (a, b) in enumerate(zip(out.lines, expect)) if a.rstrip() != b.rstrip()),
                   min(len(out.lines), len(expect)))
        got = out.lines[row] if row < len(out.lines) else "(no line)"
        want = expect[row] if row < len(expect) else "(no line)"
        parts.append(f"- first difference, line {row + 1}: nvim {_code(got)}, expected {_code(want)}")
    return "\n".join(parts) + "\n"


def _wording_section(
    records: Iterable[Record], exercises: dict[str, tuple[pathlib.Path, dict[str, Any]] | None],
    path: pathlib.Path, today: datetime.date, existing: str,
) -> str:
    """A dated section of wording entries by template, without entries already in ``existing``."""
    by_template: dict[str, list[str]] = collections.defaultdict(list)
    for rec in records:
        found = exercises.get(rec.ex)
        ex = found[1] if found else {}
        entry = f"- `{rec.ex}`: {ex.get('task', '(exercise not in build/)')}"
        entry += f"\n  - note: {rec.note}" if rec.note else ""
        if entry not in existing:
            by_template[ex.get("template", "(unknown)")].append(entry)
    if not by_template:
        return ""
    body = "".join(f"\n### {t}\n\n" + "\n".join(dict.fromkeys(e)) + "\n" for t, e in sorted(by_template.items()))
    return f"\n## {today.isoformat()} (from `{path.name}`)\n{body}"


def _read(path: pathlib.Path) -> str:
    return path.read_text() if path.exists() else ""


def _code(text: str) -> str:
    """Markdown inline code that survives backticks in ``text``."""
    return f"`` {text} ``" if "`" in text else f"`{text}`"


def _append(path: pathlib.Path, header: str, body: str):
    """Append ``body`` to ``path``, writing ``header`` first when the file is new."""
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(header if new else "")
        fh.write(body)
