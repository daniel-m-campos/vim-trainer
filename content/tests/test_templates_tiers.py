"""Tier 5-8 templates and task wording: every draft's expect must match real Neovim.

Each template gets a few handmade snippets. For each draft the canonical (first passing)
variant and every alternate are replayed in Neovim, and the shortcuts a template rules
out are checked to fail where that matters.
"""

import re

import pytest

from vimtrainer_content import build, oracle, snippets, templates
from vimtrainer_content.lang.python import LANG

SOURCE = {"repo": "fixture/tiers", "path": "tiers.py", "commit": None, "license": "MIT"}


def _window(text: str) -> snippets.Window:
    lines = text.strip("\n").splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                           tree=snippets.parse("\n".join(lines)))


def _drafts(text: str, template: str, skill: str | None = None) -> list[templates.Draft]:
    return [d for d in templates.generate(_window(text), LANG)
            if d.template == template and (skill is None or d.skill == skill)]


def _verdicts(draft, keys, runner):
    return [oracle.verify(draft.exercise("python"), k, runner) for k in keys]


def _assert_solvable(draft, runner, alternates=True):
    variants = _verdicts(draft, draft.variants, runner)
    assert any(v.passed for v in variants), (draft.task, [(v.keys, v.reason) for v in variants])
    if alternates:
        for v in _verdicts(draft, draft.alternates, runner):
            assert v.passed, (draft.task, v.keys, v.reason)


def _accepted(draft) -> tuple[dict | None, str, str]:
    """Run the build's gates 3-6 on one draft."""
    report = build.Report()
    verdicts = build._replay([draft], LANG, workers=1, report=report)
    return build.evaluate(draft, LANG, verdicts[id(draft)], "nvim test")


# Snippets =========================================================================================

COLLECTIONS = '''
WEEKDAYS = [
    'monday',
    'tuesday',
    'wednesday',
    'thursday',
    'friday',
]

SCORES = {
    'ones': 1,
    'twos': 2,
    'threes': 3,
    'fours': 4,
    'fives': 5
}


def lookup(day):
    return WEEKDAYS.index(day)
'''

CALL_ARGS = '''
def build_report(rows, title):
    table = render_table(
        rows,
        title,
        width=80,
        align='left',
    )
    return table


def other(value):
    print(value)
    return value
'''

LOGGING = '''
import logging

logger = logging.getLogger(__name__)


def handle(event):
    print('handling', event)
    payload = event['payload']
    print('payload', payload)
    result = process(payload)
    print('result', result)
    return result


def process(payload):
    return payload.strip()
'''

RENAMES = '''
def total_price(prices, discount):
    subtotal = sum(prices)
    if subtotal > 100:
        subtotal = subtotal - discount
    return round(subtotal, 2)


def count_items(items):
    return len(items)
'''

NUMBERS = '''
MAX_RETRIES = 3
TIMEOUT = 30


def retry(task, attempts=5):
    for attempt in range(10):
        if attempt > attempts:
            break
        task.run(timeout=15)
    return task
'''

ASSIGNMENTS = '''
class Config:
    host = 'localhost'
    port = 8080
    user = 'admin'
    path = '/tmp'

    def __init__(self, data):
        self.name = data.name
        self.size = data.size
        self.kind = data.kind
        self.owner = data.owner
        self.check()

    def check(self):
        return True
'''

PARAGRAPHS = '''
import math


def area(radius):
    squared = radius ** 2
    result = math.pi * squared
    return result


def circumference(radius):
    diameter = 2 * radius
    return math.pi * diameter


def unused():
    return None
'''

WRAPPED = '''
def describe(item, count):
    message = format_message(item.name, count, item.unit,
                             item.price)
    total = compute_total(item.price, count, item.discount, item.tax)
    return message, total


def format_message(name, count, unit, price):
    return f'{name}: {count} {unit} at {price}'
'''

THREE_USES = '''
def scale(values, factor):
    scaled = [v * factor for v in values]
    return scaled, factor


def describe(values):
    return len(values)
'''

CLASS_CONSTANTS = '''
class Limits:
    lowest_level = 1
    middle_level = 5
    highest_level = 10
    default_level = 3
    warning_level = 8

    def clamp(self, x):
        return max(self.lowest_level, min(self.highest_level, x))


def make():
    return Limits()
'''


# append_each_line (v.blockedit) ===================================================================


def test_append_each_line_restores_commas_with_a_block_append(runner):
    drafts = _drafts(COLLECTIONS, "append_each_line")
    assert drafts
    for d in drafts:
        assert d.skill == "v.blockedit" and d.kind == "edit"
        assert d.variants[0].startswith("<C-v>") and d.variants[0].endswith("$A,<Esc>")
        assert d.expect["lines"] != d.lines
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert all(d.expect["lines"][r] == d.lines[r] + "," for r in changed)
        assert len(changed) >= 4
        _assert_solvable(d, runner)


def test_append_each_line_skips_short_or_mixed_collections():
    assert not _drafts("X = [\n    1,\n    2,\n]\n\n\ndef f():\n    return X\n\n\nY = 1\nZ = 2\n", "append_each_line")
    assert not _drafts("X = [1, 2, 3, 4]\n\n\ndef f():\n    return X\n\n\nY = 1\nZ = 2\nW = 3\n", "append_each_line")


# upper_constants (x.normal) =======================================================================


def test_upper_constants_needs_an_ex_command(runner):
    drafts = _drafts(CLASS_CONSTANTS, "upper_constants")
    assert drafts
    for d in drafts:
        assert d.kind == "ex" and ":norm" in d.variants[0]
        assert any(ln.lstrip().startswith("LOWEST_LEVEL = 1") for ln in d.expect["lines"])
        _assert_solvable(d, runner)
        dot = _verdicts(d, ["gUiw" + "j." * (d.params["n"] - 1)], runner)[0]
        assert not dot.passed and "':'" in dot.reason


# delete_matching_lines / keep_matching_lines (x.global) ===========================================


def test_delete_matching_lines_uses_global_delete(runner):
    drafts = _drafts(LOGGING, "delete_matching_lines")
    labels = {d.task for d in drafts}
    assert any("print(...)" in t for t in labels), labels
    for d in drafts:
        assert d.kind == "ex" and d.variants[0].startswith(":g/")
        assert len(d.expect["lines"]) < len(d.lines)
        _assert_solvable(d, runner)
    d = next(d for d in drafts if "print" in d.task)
    assert all("print(" not in ln for ln in d.expect["lines"])
    assert not _verdicts(d, ["jjjjjjjdd"], runner)[0].passed


def test_delete_matching_lines_canonical_is_the_shortest_unique_prefix():
    (d, *_) = [d for d in _drafts(LOGGING, "delete_matching_lines") if "print" in d.task]
    pattern = d.variants[0][3:-6]
    assert "print".startswith(pattern)
    rows = templates._matching_rows(d.lines, pattern)
    assert all("print(" in d.lines[r] for r in rows)


def test_keep_matching_lines_uses_v(runner):
    drafts = _drafts(PARAGRAPHS, "keep_matching_lines")
    assert drafts
    for d in drafts:
        assert d.kind == "ex" and d.variants[0].startswith(":v/")
        assert d.alternates[0].startswith(":g!/")
        _assert_solvable(d, runner)
    d = next(d for d in drafts if "`def`" in d.task)
    assert all(ln.startswith("def ") for ln in d.expect["lines"])


def test_vim_regex_subset():
    assert templates._matching_rows(["", "x", "  # c", "# d"], "^$") == [0]
    assert templates._matching_rows(["a.b", "axb", "ab"], "a.b") == [0, 1]
    assert templates._matching_rows(["  # c", "x = 1  # d", "# e"], "^ *#") == [0, 2]
    assert templates._matching_rows(["  # c", "x = 1  # d"], "^\\s*#") == [0]


# rename_all_dot (x.lastsearch, a.dot) =============================================================


def test_rename_all_dot_counts_one_dot_per_remaining_match(runner):
    drafts = _drafts(RENAMES, "rename_all_dot")
    assert {d.skill for d in drafts} == {"x.lastsearch", "a.dot"}
    for d in drafts:
        n = d.params["n"]
        assert d.variants[0].endswith("<Esc>" + "." * (n - 1))
        assert "cgn" in d.variants[0]
        assert d.expect["lines"] != d.lines
        _assert_solvable(d, runner)
        assert d.params["new"] not in ("value", "X")


# join_lines (o.join) ==============================================================================


def test_join_lines_natural_and_split(runner):
    drafts = _drafts(WRAPPED, "join_lines")
    assert len(drafts) >= 2
    for d in drafts:
        n = d.params["n"]
        assert d.variants[0] == ("J" if n == 2 else f"{n}J")
        assert len(d.lines) - len(d.expect["lines"]) == n - 1
        _assert_solvable(d, runner)
    natural = [d for d in drafts if d.lines == _window(WRAPPED).lines]
    assert natural and "item.unit, item.price)" in "\n".join(natural[0].expect["lines"])


def test_join_lines_never_joins_after_an_open_bracket():
    assert not [d for d in _drafts(CALL_ARGS, "join_lines") if d.lines == _window(CALL_ARGS).lines]


# increment (o.number) =============================================================================


def test_increment_uses_a_count_and_starts_before_the_number(runner):
    drafts = _drafts(NUMBERS, "increment")
    assert drafts
    for d in drafts:
        row, col = d.cursor
        line = d.lines[row - 1]
        new, old = d.params["new"], d.params["old"]
        assert re.fullmatch(r"[2-9]<C-[ax]>", d.variants[0])
        assert not any(ch.isdigit() for ch in line[col:line.index(old, col)])
        assert old in d.task and new in d.task
        _assert_solvable(d, runner)


# duplicate_line (o.yank, o.put) ===================================================================


def test_duplicate_line_yank_and_put(runner):
    drafts = _drafts(RENAMES + LOGGING, "duplicate_line")
    skills = {d.skill for d in drafts}
    assert skills == {"o.yank", "o.put"}
    for d in drafts:
        assert d.variants[0].startswith("yy")
        assert d.variants[0][-1] == ("P" if d.skill == "o.put" else "p")
        assert len(d.expect["lines"]) == len(d.lines) + 1
        variants = _verdicts(d, d.variants, runner)
        assert any(v.passed for v in variants), (d.task, [(v.keys, v.reason) for v in variants])
        assert not _verdicts(d, ["Yp"], runner)[0].passed  # Neovim's Y is y$


# record_macro (a.macro) ===========================================================================


def test_record_macro_wraps_each_value(runner):
    drafts = _drafts(ASSIGNMENTS, "record_macro")
    assert drafts
    for d in drafts:
        n = d.params["n"]
        assert n >= 4
        assert d.variants[0].startswith("qa") and d.variants[0].endswith(f"q{n - 1}@a")
        wrapper = d.params["text"]
        changed = [b for a, b in zip(d.lines, d.expect["lines"]) if a != b]
        assert len(changed) == n and all(f"= {wrapper}(" in b and b.endswith(")") for b in changed)
        _assert_solvable(d, runner)


def test_record_macro_picks_wrapper_by_value_type():
    wrappers = {d.params["text"] for d in _drafts(ASSIGNMENTS, "record_macro")}
    assert wrappers <= {"str", "_", "float"}


# delete_block (t.para, t.brace, t.bracket, t.paren) ===============================================


def test_delete_block_paragraph_dap_from_inside(runner):
    drafts = _drafts(PARAGRAPHS, "delete_block", "t.para")
    assert drafts
    for d in drafts:
        assert d.variants == ["dap"]
        row = d.cursor[0] - 1
        assert d.lines[row - 1].strip(), "cursor must be inside the paragraph, not on its first line"
        _assert_solvable(d, runner)


def test_delete_block_multiline_braces(runner):
    drafts = _drafts(COLLECTIONS, "delete_block")
    assert {d.skill for d in drafts} >= {"t.brace", "t.bracket"}
    for d in drafts:
        o = d.params["open"]
        assert d.variants == [f"di{o}"]
        assert any(ln.rstrip().endswith(o) for ln in d.expect["lines"])
        _assert_solvable(d, runner)


# change_kwarg_value (m.find) ======================================================================


def test_change_kwarg_value_find_variant(runner):
    drafts = _drafts(CALL_ARGS + NUMBERS, "change_kwarg_value", "m.find")
    assert drafts
    for d in drafts:
        line = d.lines[d.cursor[0] - 1]
        assert d.cursor[1] == len(line) - len(line.lstrip())
        assert re.match(r"[2-9]?f=l", d.variants[0])
        _assert_solvable(d, runner, alternates=False)


# wording ==========================================================================================


WORDING_SNIPPETS = [COLLECTIONS, CALL_ARGS, LOGGING, RENAMES, NUMBERS, ASSIGNMENTS, PARAGRAPHS, WRAPPED]
_BAD_WORDS = re.compile(r"\b1st\b|\b2nd\b|\b3rd\b|keeping the [()\[\]{}'\"]")
_PLACEHOLDERS = {"value", "X", "x + 1", "*args", "self", "*args, **kwargs"}


@pytest.mark.parametrize("snippet", range(len(WORDING_SNIPPETS)))
def test_tasks_avoid_placeholder_wording(snippet):
    for d in templates.generate(_window(WORDING_SNIPPETS[snippet]), LANG):
        assert d.task.isascii()
        assert not _BAD_WORDS.search(d.task), (d.template, d.task)
        assert not {d.params.get("text"), d.params.get("new")} & _PLACEHOLDERS, (d.template, d.task)
        assert d.task.count("`") % 2 == 0, (d.template, d.task)
        assert any(h["trigger"] is None for h in d.hints), d.template
        for h in d.hints:
            if h["trigger"]:
                re.compile(h["trigger"])


def test_new_names_keep_case_style_and_role():
    win = _window(RENAMES)
    assert templates._styled("parse_input", "MAX_SIZE") == "PARSE_INPUT"
    assert templates._styled("parse_input", "MyClass") == "ParseInput"
    assert templates._styled("parse_input", "myVar") == "parseInput"
    assert templates._styled("item", "_hidden") == "_item"
    assert templates._new_name(win, "prices", None, "k") in templates.ROLE_NAMES["many"]
    assert templates._new_name(win, "discount", None, "k") in templates.ROLE_NAMES["any"] + templates.ROLE_NAMES["count"]
    assert templates._new_name(win, "SCORE_LIMIT", None, "k").isupper()


def test_fit_value_matches_node_kind():
    win = _window(NUMBERS + CALL_ARGS)
    kinds = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.named_children)
        if n.type in ("string", "integer", "identifier") and n.type not in kinds:
            kinds[n.type] = (n, templates._fit_value(win, n, "t"))
    string, new = kinds["string"]
    assert new and new[0] == templates._text(string)[0] and new[-1] == templates._text(string)[-1]
    assert kinds["integer"][1].lstrip("-").isdigit()
    assert re.fullmatch(r"\w+", kinds["identifier"][1] or "x")


def test_ordinal_words():
    assert templates.ordinal(1) == "first" and templates.ordinal(3) == "third" and templates.ordinal(12) == "12th"


# gates on the new templates =======================================================================


@pytest.mark.parametrize("template,snippet", [
    ("append_each_line", COLLECTIONS), ("delete_matching_lines", LOGGING), ("rename_all_dot", RENAMES),
    ("increment", NUMBERS), ("record_macro", ASSIGNMENTS), ("delete_block", PARAGRAPHS),
    ("duplicate_line", LOGGING), ("join_lines", WRAPPED), ("prefix_each_line", ASSIGNMENTS),
    ("keep_matching_lines", PARAGRAPHS), ("upper_constants", CLASS_CONSTANTS),
])
def test_some_draft_passes_every_gate(template, snippet):
    results = [_accepted(d) for d in _drafts(snippet, template)]
    assert any(ex is not None for ex, _, _ in results), [(g, detail) for _, g, detail in results]


# prefix_each_line (v.blockedit, x.normal) =========================================================


def test_prefix_each_line_block_insert_and_normal(runner):
    drafts = _drafts(ASSIGNMENTS, "prefix_each_line")
    assert {d.skill for d in drafts} == {"v.blockedit", "x.normal"}
    for d in drafts:
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert len(changed) == d.params["n"] >= 3
        assert all(d.expect["lines"][r].lstrip().startswith("self.") for r in changed)
        assert all(not d.lines[r].lstrip().startswith("self.") for r in changed)
        if d.skill == "v.blockedit":
            assert d.kind == "edit" and d.variants[0].startswith("<C-v>") and "Iself.<Esc>" in d.variants[0]
        else:
            assert d.kind == "ex" and ":norm Iself." in d.variants[0]
        _assert_solvable(d, runner)


# kind rule (templates.EX_MIN_LINES, templates.SUBST_EDIT_MAX) ======================================
# "ex" only where the normal-mode way would be a repetition drill: :norm, :g and :v over
# EX_MIN_LINES or more lines, :%s over more than SUBST_EDIT_MAX occurrences.


def _deleted(d):
    return len(d.lines) - len(d.expect["lines"])


@pytest.mark.parametrize("template,snippet,skill,count", [
    ("prefix_each_line", ASSIGNMENTS, "x.normal", lambda d: d.params["n"]),
    ("upper_constants", CLASS_CONSTANTS, "x.normal", lambda d: d.params["n"]),
    ("delete_matching_lines", LOGGING, "x.global", _deleted),
    ("keep_matching_lines", PARAGRAPHS, "x.global", _deleted),
], ids=["prefix_each_line", "upper_constants", "delete_matching_lines", "keep_matching_lines"])
def test_line_range_drills_are_ex_from_ex_min_lines(template, snippet, skill, count):
    drafts = _drafts(snippet, template, skill)
    assert drafts
    for d in drafts:
        assert count(d) >= templates.EX_MIN_LINES and d.kind == "ex", (d.task, count(d), d.kind)


def test_rename_all_subst_kind_follows_the_occurrence_count(runner):
    drafts = _drafts(THREE_USES, "rename_all_subst") + _drafts(RENAMES, "rename_all_subst")
    assert {len(d.target) <= templates.SUBST_EDIT_MAX for d in drafts} == {True, False}
    for d in drafts:
        few = len(d.target) <= templates.SUBST_EDIT_MAX
        assert d.kind == ("edit" if few else "ex"), (d.task, d.kind)
        assert any("cgn" in a for a in d.alternates) == few
        _assert_solvable(d, runner)  # the cgn + . alternate passes in Neovim
        if not few:
            dots = "." * (len(d.target) - 1)
            normal = _verdicts(d, [f"/\\<{d.params['old']}\\><CR>cgn{d.params['new']}<Esc>{dots}"], runner)[0]
            assert not normal.passed and "':'" in normal.reason
