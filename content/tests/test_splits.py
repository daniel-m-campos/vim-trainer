r"""Split drill: ``:s`` with ``\r`` in the replacement, one item per line.

Drafts are replayed in Neovim, so the wrapped lines are Neovim's answer.
"""

import pytest

from vimtrainer_content import build, oracle, snippets, splits
from vimtrainer_content.lang import cpp, lua
from vimtrainer_content.lang.python import LANG

SOURCE = {"repo": "fixture/splits", "path": "splits.py", "commit": None, "license": "MIT"}
UNDER = "    notify(orders.owner, ledger.name, clock.now())"
DEEPER = "    total = ledger.record(orders, clock.now(), ledger.currency)"
SETTLE = f'''
def settle(orders, ledger, clock):
{UNDER}
    pair = (a, b, c)
    first, second, third = unpack(orders)
    label = format_row("a, b", orders, ledger.name, clock)
    return summarise(total, pair, clock)
'''
BRACES = {
    "cpp": '''
int settle(Ledger& ledger, int amount) {
    ledger.transfer(amount, ledger.source(), ledger.target());
    return amount;
}
''',
    "lua": '''
local function settle(ledger, amount)
    ledger.transfer(amount, ledger.source(), ledger.target())
    return amount
end
''',
}


def _window(text: str, parse=snippets.parse) -> snippets.Window:
    lines = text.strip("\n").splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines), tree=parse("\n".join(lines)))


def _evaluate(draft, lang=LANG):
    verdicts = build._replay([draft], lang, workers=1, report=build.Report())
    return build.evaluate(draft, lang, verdicts[id(draft)], "nvim test")


def _one(line: str):
    """The one draft made for a function holding just ``line``."""
    drafts = list(splits.split_line(_window(f"def settle(orders, ledger, clock):\n{line}\n    return orders\n"), "x.subst", LANG))
    assert len(drafts) == 1, drafts
    return drafts[0]


# The group ========================================================================================


@pytest.mark.parametrize(("line", "why"), [
    ("    pair = (a, b, c)", "too short to wrap"),
    ("    first, second, third = unpack(orders)", "the commas are not in a bracket"),
    ('    label = format_row("a, b", orders, ledger.name, clock)', "a comma and a space inside a string"),
    ("    rows = combine(left_rows, merge(a, b), right_rows, total)", "a comma and a space in a nested call"),
    ("    low, high = split_at(orders.first, orders.middle, orders.last)", "a second comma and space outside"),
    ("    notify(orders.owner, ledger.name)", "one break only"),
    ("    notify(orders.owner,ledger.name, clock.now(), 1)", "a comma with no space after it"),
    ("    notify(orders.owner, ledger.name, clock.now(),)", "a trailing comma"),
    ("    (alpha_value, beta_value, gamma_value) = unpack_all_of(orders)", "a long tail after the bracket"),
    ("    blank = ['   ', ' _ ', '| |', '|_|', '   ', '   ']", "items with nothing to read"),
    ("    notify(orders.owner, ledger.name, clock.now()", "an unclosed bracket"),
])
def test_group_leaves_these_lines_alone(line, why):
    assert splits._group(line) is None, why


def test_group_finds_the_bracket_and_its_commas():
    opener, commas = splits._group(UNDER)
    assert UNDER[opener] == "(" and [UNDER[c:c + 2] for c in commas] == [", ", ", "]


def test_fixture_makes_one_draft_from_the_only_line_worth_wrapping():
    drafts = list(splits.split_line(_window(SETTLE), "x.subst", LANG))
    assert [d.lines[d.cursor[0] - 1] for d in drafts] == [UNDER]


# The drill ========================================================================================


def test_short_indent_lines_up_under_the_first_item(runner):
    draft = _one(UNDER)
    ex, problem, _ = _evaluate(draft)
    assert ex is not None, problem
    assert ex["kind"] == "ex" and ex["par"]["keys"] == ":s/, /,\\r" + " " * 11 + "/g<CR>"
    assert ex["expect"]["lines"][1:4] == [
        "    notify(orders.owner,",
        "           ledger.name,",
        "           clock.now())",
    ]
    assert "lined up under `orders.owner` (11 spaces)" in ex["task"]


def test_deep_bracket_is_indented_one_level_instead(runner):
    draft = _one(DEEPER)
    ex, problem, _ = _evaluate(draft)
    assert ex is not None, problem
    assert ex["par"]["keys"] == ":s/, /,\\r" + " " * 8 + "/g<CR>"
    assert ex["expect"]["lines"][1:4] == [
        "    total = ledger.record(orders,",
        "        clock.now(),",
        "        ledger.currency)",
    ]
    assert "indented one level deeper (8 spaces)" in ex["task"]


def test_the_g_flag_and_the_line_break_are_both_needed(runner):
    ex = _one(UNDER).exercise("python")
    pad = " " * 11
    assert oracle.verify(ex, f":s/, /,\\r{pad}/g<CR>", runner).passed
    assert not oracle.verify(ex, f":s/, /,\\r{pad}/<CR>", runner).passed  # the first comma only
    assert not oracle.verify(ex, f":s/, /,\\n{pad}/g<CR>", runner).passed  # \n is a null byte here
    assert not oracle.verify(ex, f"f,lr<CR>i{pad[:7]}<Esc>", runner).passed  # not an Ex command, and one break


# Every language ===================================================================================


def test_every_language_runs_the_split_template():
    for name, spec in build.LANGS.items():
        assert "x.subst" in spec.skills, name
        assert set(splits.USES) <= set(spec.lang.line_templates), name


@pytest.mark.parametrize("name", sorted(BRACES))
def test_template_works_without_python_syntax(name, runner):
    spec = build.LANGS[name]
    win = _window(BRACES[name], {"cpp": cpp, "lua": lua}[name].parse)
    drafts = [d for d in spec.generate(win, spec.lang) if d.template == "split_line"]
    assert len(drafts) == 1
    ex, problem, _ = _evaluate(drafts[0], spec.lang)
    assert ex is not None, problem
    assert [ln.strip() for ln in ex["expect"]["lines"][1:4]] == ["ledger.transfer(amount,", "ledger.source(),", "ledger.target());" if name == "cpp" else "ledger.target())"]
