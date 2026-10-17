"""Tests for vimtrainer_content.templates: every template's expect must match real Neovim."""

import collections

import pytest

from vimtrainer_content import build, oracle, templates
from vimtrainer_content.lang.python import LANG

ALL_TEMPLATES = sorted({*templates.NODE_TEMPLATES, *templates.LINE_TEMPLATES})


def _by_template(drafts):
    groups = collections.defaultdict(list)
    for d in drafts:
        groups[d.template].append(d)
    return groups


def _replay(draft, keys, runner):
    return oracle.verify(draft.exercise("python"), keys, runner)


# generation =======================================================================================


def test_every_mapped_template_fires_on_fixture(drafts):
    fired = {d.template for d in drafts}
    # fixture strings are not all lower-case words; the tier 5-8 templates that need repeated
    # structure (4+ sibling assignments, one-item-per-line collections) are covered by
    # test_templates_tiers.py with their own snippets. The fixture defines no constant, so
    # upper_word is covered by test_templates_wording.py.
    missing = set(ALL_TEMPLATES) - fired - {"upper_inner", "append_each_line", "prefix_each_line", "record_macro",
                                            "upper_constants", "upper_word"}
    assert not missing


def test_generation_is_deterministic(window, drafts):
    again = templates.generate(window, LANG)
    assert [d.uid for d in again] == [d.uid for d in drafts]


def test_at_most_max_per_window_per_template_and_skill(drafts):
    counts = collections.Counter((d.template, d.skill) for d in drafts)
    assert max(counts.values()) <= templates.MAX_PER_WINDOW + 1  # find_char allows one extra


def test_drafts_have_target_hints_and_ascii_tasks(drafts):
    for d in drafts:
        assert d.target and d.variants and d.hints, d.template
        assert d.task.isascii()
        assert any(h["trigger"] is None for h in d.hints), d.template


@pytest.mark.parametrize("template", ALL_TEMPLATES)
def test_some_variant_reaches_expect_in_neovim(template, drafts, runner):
    group = _by_template(drafts).get(template, [])
    if not group:
        pytest.skip(f"{template} does not fire on the fixture")
    for d in group:
        verdicts = [_replay(d, k, runner) for k in d.variants]
        assert any(v.passed for v in verdicts), (d.task, [(v.keys, v.reason) for v in verdicts])


# specific templates ===============================================================================


def test_change_inner_string(drafts):
    (d, *_) = [d for d in drafts if d.template == "change_inner" and d.skill == "t.quote"]
    row = d.cursor[0] - 1
    assert d.variants[0].startswith('ci"') and d.variants[0].endswith("<Esc>")
    assert d.expect["lines"][row] != d.lines[row]
    assert d.typed == len(d.params["text"])


def test_move_line_expect_matches_ex_move(drafts, runner):
    for d in [d for d in drafts if d.template == "move_line"]:
        for keys in d.variants:
            assert _replay(d, keys, runner).passed, (d.task, keys)


def test_indent_block_start_is_misindented_and_expect_is_source(window, drafts):
    for d in [d for d in drafts if d.template == "indent_block"]:
        assert d.expect["lines"] == window.lines
        assert d.lines != window.lines


def test_rename_all_subst_is_ex_above_subst_edit_max_and_a_variant_passes(drafts, runner):
    d = next(d for d in drafts if d.template == "rename_all_subst")
    assert len(d.target) > templates.SUBST_EDIT_MAX
    assert d.kind == "ex"
    ok = [_replay(d, k, runner) for k in d.variants]
    assert any(v.passed for v in ok)


def test_find_char_targets_nth_occurrence(drafts):
    for d in [d for d in drafts if d.template == "find_char"]:
        row, col = d.expect["cursor"]
        line = d.lines[row - 1]
        assert line[col] == d.params["char"]
        start = d.cursor[1]
        assert line[start + 1:col + 1].count(d.params["char"]) == d.params["n"]


def test_jump_block_end_shortcut_is_listed(drafts):
    for d in [d for d in drafts if d.template == "jump_block_end"]:
        assert d.forbid and d.forbid[0][0] in "fF"


# evaluate (gates on oracle verdicts) ==============================================================


def test_evaluate_accepts_most_fixture_drafts(drafts):
    report = build.Report()
    verdicts = build._replay(drafts, LANG, workers=2, report=report)
    results = [build.evaluate(d, LANG, verdicts[id(d)], "nvim test") for d in drafts]
    accepted = [ex for ex, _, _ in results if ex is not None]
    assert len(accepted) >= len(drafts) // 3
    for ex in accepted:
        assert ex["par"]["count"] == oracle.count_keys(ex["par"]["keys"])
        assert ex["id"].startswith(f"py/{ex['skill']}/")
        assert ex["par"]["keys"] not in ex["alternates"]
        if ex["kind"] == "cursor":
            assert "best" not in ex["par"]  # cursor drills allow no shorter candidate at all
