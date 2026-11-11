"""Register drills: preloaded registers, register-graded tasks and the plain-route gate.

Drafts are replayed in Neovim, so what a register holds at the end is Neovim's answer.
"""

import pytest

from vimtrainer_content import build, gates, oracle, registers, snippets, templates
from vimtrainer_content.lang import cpp, lua
from vimtrainer_content.lang.python import LANG

SOURCE = {"repo": "fixture/registers", "path": "registers.py", "commit": None, "license": "MIT"}
SETTLE = '''
import collections


def settle(orders, ledger, clock):
    pending = collections.deque(orders)
    settled_total = 0
    started = clock.now()
    while pending:
        order = pending.popleft()
        amount = order.price * order.count
        ledger.record(order, amount)
        settled_total = settled_total + amount
        clock.advance(amount, started)
    elapsed = clock.now() - started
    ledger.close(elapsed)
    summary = max(settled_total, elapsed)
    return summary
'''
BRACES = {
    "cpp": '''
int settle(Ledger& ledger, int amount, int started) {
    int settled_total = 0;
    int elapsed = started + amount;
    ledger.record(amount, started);
    settled_total = settled_total + amount;
    ledger.advance(amount, elapsed);
    int summary = max(settled_total, elapsed);
    ledger.close(elapsed);
    return summary;
}
''',
    "lua": '''
local function settle(ledger, amount, started)
    local settled_total = 0
    local elapsed = started + amount
    ledger.record(amount, started)
    settled_total = settled_total + amount
    ledger.advance(amount, elapsed)
    local summary = math.max(settled_total, elapsed)
    ledger.close(elapsed)
    return summary
end
''',
}


def _window(text: str) -> snippets.Window:
    lines = text.strip("\n").splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines), tree=snippets.parse("\n".join(lines)))


def _drafts(name: str) -> list[templates.Draft]:
    return [d for d in templates.generate(_window(SETTLE), LANG) if d.template == name]


def _evaluate(draft):
    verdicts = build._replay([draft], LANG, workers=1, report=build.Report())
    return build.evaluate(draft, LANG, verdicts[id(draft)], "nvim test")


def _accepted(name: str) -> list[dict]:
    """Exercises the gates accept from one template; the test fails when there is none."""
    kept = [ex for ex, _, _ in map(_evaluate, _drafts(name)) if ex is not None]
    assert kept, (name, [_evaluate(d)[1:] for d in _drafts(name)])
    return kept


def _verdict(keys, passed=True):
    return oracle.Verdict("x", keys, oracle.count_keys(keys), passed, "ok" if passed else "no", 0.0)


# Format: start.registers and expect.registers =====================================================


def _exercise(start_registers, expect_registers, expect_lines=None):
    lines = ["alpha = 1", "beta = 2", "gamma = 3"]
    return {"lang": "python", "kind": "edit", "start": {"lines": lines, "cursor": [1, 0], "registers": start_registers},
            "expect": {"lines": expect_lines or lines, "registers": expect_registers}}


def test_oracle_loads_start_registers(runner):
    held = {'"': "cut = 0\n", "1": "cut = 0\n", "0": "yank = 9\n", "a": "word"}
    below = lambda text: ["alpha = 1", text, "beta = 2", "gamma = 3"]  # noqa: E731
    assert oracle.verify(_exercise(held, {}, below("cut = 0")), "p", runner).passed
    assert oracle.verify(_exercise(held, {}, below("yank = 9")), '"0p', runner).passed
    assert oracle.verify(_exercise(held, {}, ["awordlpha = 1", "beta = 2", "gamma = 3"]), '"ap', runner).passed


def test_oracle_grades_expect_registers(runner):
    held = {'"': "cut = 0\n", "1": "cut = 0\n"}
    after = ["beta = 2", "gamma = 3"]
    kept = oracle.verify(_exercise(held, {'"': "cut = 0\n"}, after), '"_dd', runner)
    lost = oracle.verify(_exercise(held, {'"': "cut = 0\n"}, after), "dd", runner)
    assert kept.passed
    assert not lost.passed and "register" in lost.reason
    assert oracle.verify(_exercise({}, {"a": "alpha = 1\nbeta = 2\n"}), '"ayyj"Ayy', runner).passed
    assert not oracle.verify(_exercise({}, {"a": "alpha = 1\nbeta = 2\n"}), '"ayyj"ayy', runner).passed


def test_registers_are_part_of_the_exercise_only_when_set():
    plain = next(d for d in templates.generate(_window(SETTLE), LANG) if not d.registers)
    loaded = _drafts("put_yanked_line")[0]
    assert "registers" not in plain.exercise("python")["start"]
    assert loaded.exercise("python")["start"]["registers"] == loaded.registers
    before = loaded.uid
    loaded.registers = {**loaded.registers, "0": "something else\n"}
    assert loaded.uid != before


# Gates ============================================================================================


def test_plain_problem_rejects_a_plain_route_that_ties_or_wins():
    par = _verdict('"0p')
    assert gates.plain_problem(par, []) is None
    assert gates.plain_problem(par, [_verdict(":12t.<CR>")]) is None
    assert gates.plain_problem(par, [_verdict("yyp", passed=False)]) is None
    assert "ties or beats" in gates.plain_problem(par, [_verdict(":3t.<CR>"), _verdict("3Gp")])
    assert "ties or beats" in gates.plain_problem(par, [_verdict("p")])


def test_register_only_exercise_needs_no_changed_line():
    ex = _accepted("collect_lines")
    untouched = [e for e in ex if e["expect"]["lines"] == e["start"]["lines"]]
    assert untouched
    for e in untouched:
        assert e["expect"]["registers"]["a"].count("\n") == 3
        assert gates.target_problem(e, e["target"]) is None
        bare = {**e, "expect": {"lines": e["expect"]["lines"]}}
        assert gates.target_problem(bare, e["target"]) is not None


# Templates ========================================================================================


@pytest.mark.parametrize("name", sorted(registers.TEMPLATES))
def test_every_template_yields_an_accepted_exercise(name):
    for ex in _accepted(name):
        assert ex["par"]["count"] == oracle.count_keys(ex["par"]["keys"])
        assert "`" in ex["task"]


def test_put_yanked_line_is_not_solved_by_p(runner):
    for ex in _accepted("put_yanked_line"):
        assert ex["par"]["keys"] in ('"0p', '"0P')
        assert ex["start"]["registers"]['"'] != ex["start"]["registers"]["0"]
        assert not oracle.verify(ex, ex["par"]["keys"].replace('"0', ""), runner).passed


def test_put_yanked_word_backs_the_unnamed_register(runner):
    for ex in _accepted("put_yanked_word"):
        held = ex["start"]["registers"]
        assert held['"'] == held["-"] != held["0"]
        assert ex["par"]["keys"] == 'viw"0p'
        assert not oracle.verify(ex, "viwp", runner).passed
        assert oracle.verify(ex, "ciw<C-r>0<Esc>", runner).passed


def test_swap_words_swaps_across_a_comma_or_operator(runner):
    for ex in _accepted("swap_words"):
        row = ex["start"]["cursor"][0] - 1
        assert ex["par"]["keys"].startswith("diw") and "viwp" in ex["par"]["keys"]
        assert ex["start"]["lines"][row] != ex["expect"]["lines"][row]
        assert len(ex["start"]["lines"][row]) == len(ex["expect"]["lines"][row])
        assert " = " not in ex["task"]


def test_delete_keep_register_is_graded_on_the_unnamed_register(runner):
    for ex in _accepted("delete_keep_register"):
        cut = ex["start"]["registers"]['"']
        assert ex["expect"]["registers"] == {'"': cut}
        assert ex["par"]["keys"].startswith('"_') or ex["par"]["keys"][1:].startswith('"_')
        plain = oracle.verify(ex, ex["par"]["keys"].replace('"_', ""), runner)
        assert not plain.passed and "register" in plain.reason


def test_put_two_registers_names_both_registers(runner):
    for ex in _accepted("put_two_registers"):
        assert set(ex["start"]["registers"]) == {"a", "b"}
        assert '"a' in ex["par"]["keys"] and '"b' in ex["par"]["keys"]
        assert len(ex["expect"]["lines"]) == len(ex["start"]["lines"]) + 2


def test_collect_lines_needs_the_append(runner):
    for ex in _accepted("collect_lines"):
        assert ex["par"]["keys"].count('"A') == 2
        overwrite = oracle.verify(ex, ex["par"]["keys"].replace('"A', '"a'), runner)
        assert not overwrite.passed and "register" in overwrite.reason


def test_insert_register_arg_pastes_in_insert_mode(runner):
    for ex in _accepted("insert_register_arg"):
        row = ex["start"]["cursor"][0] - 1
        name = ex["start"]["registers"]["a"]
        assert "<C-r>a" in ex["par"]["keys"]
        assert not ex["start"]["lines"][row].lstrip().startswith("def ")
        assert ex["expect"]["lines"][row] == ex["start"]["lines"][row].replace(")", f", {name})")


# Every language ===================================================================================


def test_every_language_runs_the_register_templates():
    for name, spec in build.LANGS.items():
        assert set(registers.SKILLS) <= set(spec.skills), name
        assert set(registers.USES) <= set(spec.lang.line_templates), name


@pytest.mark.parametrize("name", sorted(BRACES))
def test_templates_work_without_python_syntax(name):
    spec = build.LANGS[name]
    lines = BRACES[name].strip("\n").splitlines()
    win = snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                          tree={"cpp": cpp, "lua": lua}[name].parse("\n".join(lines)))
    made = {d.template for d in spec.generate(win, spec.lang) if d.template in registers.TEMPLATES}
    assert made == set(registers.TEMPLATES)
