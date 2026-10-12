"""Tests for vimtrainer_content.gates."""

import pytest

from vimtrainer_content import gates, oracle


def _verdict(keys, passed=True):
    return oracle.Verdict("x", keys, oracle.count_keys(keys), passed, "ok" if passed else "no", 0.0)


def _edit(lines, cursor, expect):
    return {"kind": "edit", "start": {"lines": lines, "cursor": cursor}, "expect": {"lines": expect}}


# naive_cost / anti-shortcut =======================================================================


def test_naive_cost_cursor_is_manhattan_distance():
    ex = {"kind": "cursor", "start": {"lines": ["a"] * 20, "cursor": [2, 0]}, "expect": {"cursor": [12, 0]}}
    assert gates.naive_cost(ex) == 10


def test_naive_cost_edit_prefers_cheaper_strategy():
    # Deleting 6 lines: line strategy (dd x6 = 12) beats x-ing every character.
    lines = [f"line number {i}" for i in range(10)]
    ex = _edit(lines, [3, 0], lines[:2] + lines[8:])
    assert gates.naive_cost(ex) == 12


def test_anti_shortcut_rejects_short_relative_jump_and_accepts_long_one():
    near = {"kind": "cursor", "start": {"lines": ["a"] * 20, "cursor": [1, 0]}, "expect": {"cursor": [5, 0]}}
    far = {"kind": "cursor", "start": {"lines": ["a"] * 20, "cursor": [1, 0]}, "expect": {"cursor": [10, 0]}}
    assert gates.anti_shortcut_problem(near, 2, 0) is not None  # 4j: jjjj is as good
    assert gates.anti_shortcut_problem(far, 2, 0) is None


def test_anti_shortcut_subtracts_typed_text():
    line = '    logger.warning("a much longer message here", count, total)'
    ex = _edit([line], [1, 12], [line.replace("a much longer message here", "retry")])
    assert gates.anti_shortcut_problem(ex, oracle.count_keys('ci"retry<Esc>'), typed=5) is None
    tiny = _edit(['f("abc")'], [1, 3], ['f("x")'])
    assert gates.anti_shortcut_problem(tiny, oracle.count_keys('ci"x<Esc>'), typed=1) is not None


# target ===========================================================================================


def test_target_problem_requires_highlight_covering_the_change():
    ex = _edit(["a = 1", "b = 2"], [1, 0], ["a = 1", "b = 3"])
    assert gates.target_problem(ex, []) == "no target highlight"
    assert gates.target_problem(ex, [{"start": [2, 4], "end": [2, 4]}]) is None
    assert "outside" in gates.target_problem(ex, [{"start": [1, 0], "end": [1, 4]}])
    assert "bounds" in gates.target_problem(ex, [{"start": [3, 0], "end": [3, 0]}])


def test_target_problem_cursor_must_be_in_highlight():
    ex = {"kind": "cursor", "start": {"lines": ["abc", "def"], "cursor": [1, 0]}, "expect": {"cursor": [2, 1]}}
    assert gates.target_problem(ex, [{"start": [2, 1], "end": [2, 1]}]) is None
    assert gates.target_problem(ex, [{"start": [2, 2], "end": [2, 2]}]) is not None


# judge_par ========================================================================================


def test_judge_par_picks_shortest_passing_variant():
    verdicts = {k: _verdict(k) for k in ("6dd", "d}", "dap")}
    canonical, best, problem = gates.judge_par(["6dd", "d}", "dap"], verdicts)
    assert canonical.keys == "d}" and best.keys == "d}" and problem is None


def test_judge_par_flags_canonical_beaten_by_more_than_margin():
    verdicts = {"4f,": _verdict("4f,"), "$": _verdict("$")}  # 3 keys vs 1 key
    assert "beaten" in gates.judge_par(["4f,"], verdicts)[2]
    verdicts = {"f,": _verdict("f,"), "w": _verdict("w")}  # beaten by 1: fine at margin 1, not at 0
    assert gates.judge_par(["f,"], verdicts)[2] is None
    assert gates.judge_par(["f,"], verdicts, margin=0)[2] is not None


def test_judge_par_rejects_forbidden_shortcut_and_failing_canonical():
    verdicts = {"])": _verdict("])"), "f)": _verdict("f)")}
    assert "shortcut" in gates.judge_par(["])"], verdicts, forbid=["f)"])[2]
    failing = {"di(": _verdict("di(", passed=False)}
    canonical, _, problem = gates.judge_par(["di("], failing)
    assert canonical is None and "no canonical" in problem


@pytest.mark.parametrize(("count", "thin"), [(19, True), (20, False)])
def test_is_thin(count, thin):
    assert gates.is_thin(count) is thin


# cursor probes ====================================================================================


def _cursor(lines, cursor, target, skill):
    return {"kind": "cursor", "skill": skill, "start": {"lines": lines, "cursor": cursor}, "expect": {"cursor": target}}


def test_cursor_probes_cover_pairs_counts_and_find_chars():
    ex = _cursor(["a < b"], [1, 0], [1, 4], "m.find")
    probes = dict(gates.cursor_probes(ex))
    assert probes["$"] == 1 and probes["G-"] == 2 and probes["9j"] == 2 and probes["gg"] == 2
    assert probes["f<lt>"] == 2 and probes["tb"] == 2


def test_cursor_probe_problem_rejects_shorter_and_moot_ties():
    ex = _cursor(["return ''.join(chars)"], [1, 14], [1, 20], "m.match")
    probes = [("$", 1), ("%", 1), ("ww", 2)]
    target, elsewhere = [1, 20], [1, 15]
    assert "ties" in gates.cursor_probe_problem(ex, 1, probes, [target, target, None])
    assert gates.cursor_probe_problem(ex, 1, probes, [elsewhere, target, target]) is None
    rel = _cursor(["x"] * 20, [12, 0], [3, 0], "m.rel")
    assert "beats" in gates.cursor_probe_problem(rel, 2, [("(", 1)], [[3, 0]])
    # same-skill and known-candidate ties pass; a coincidental 2-key tie passes too
    assert gates.cursor_probe_problem(rel, 2, [("9+", 2), ("Mj", 2)], [[3, 0], [3, 0]]) is None
    assert gates.cursor_probe_problem(rel, 2, [("M", 2)], [[3, 0]], allowed={"M"}) is None
    # f/t/F/T + char ties a non-find skill: the drill no longer needs its skill
    unmatched = _cursor(["f(a.b)"], [1, 2], [1, 3], "n.unmatched")
    assert "ties" in gates.cursor_probe_problem(unmatched, 2, [("t.", 2)], [[1, 3]])
    assert gates.cursor_probe_problem(unmatched, 2, [("])", 2)], [[1, 3]]) is None


def test_cursor_probes_land_in_nvim():
    ex = _cursor(["    return ''.join(chars)", "x = 1"], [1, 18], [1, 24], "m.match")
    keys = ["%", "$", "w", "x", "i", "fz"]
    (landed,) = oracle.probe_cursors([(ex, keys)])
    assert landed == [[1, 24], [1, 24], [1, 19], None, None, [1, 18]]


# destination ======================================================================================


def test_target_problem_rejects_ambiguous_destination():
    lines = ["def f():", "    total = 1", "    return inventory", "x = 2", "    return inventory"]
    ex = _edit(lines, [2, 4], lines[:3] + ["    total = 1"] + lines[3:])
    rng = [{"start": [2, 0], "end": [2, 12]}, {"start": [4, 0], "end": [4, 4]}]
    assert "matches 2 lines" in gates.target_problem(ex, rng, "Copy this line to just below `return inventory`")
    assert gates.target_problem(ex, rng, "Copy this line to just below `x = 2`") is None
    assert gates.target_problem(ex, rng, "Copy this line to just below `x = ...`") is None
    assert "matches 2 lines" in gates.target_problem(ex, rng, "Move this line above `return inv...`")
