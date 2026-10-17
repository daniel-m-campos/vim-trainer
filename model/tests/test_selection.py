"""Tests for vimtrainer_model.selection."""

import json
from collections import Counter
from pathlib import Path

from conftest import make_record

from vimtrainer_model.attempt import apply_attempt
from vimtrainer_model.selection import choose_exercise, choose_focus, exercise_pool
from vimtrainer_model.state import new_state


def test_choose_focus_prefers_lowest_confidence(graph):
    state = new_state(graph)
    for t, skill in enumerate(("f.modes", "f.hjkl", "f.undo", "f.save")):
        state = apply_attempt(state, make_record(t, skill), graph)
    picks = Counter(choose_focus(state, "python", graph, 10, seed=s) for s in range(200))
    assert picks.most_common(1)[0][0] == "f.xdd"
    assert 100 < picks["f.xdd"] < 200
    assert len(picks) == 3


def test_choose_focus_spreads_two_weak_skills(graph):
    """The e2e regression: two weak skills used to take 13 of 15 picks."""
    state = new_state(graph)
    for t, skill in enumerate(("f.modes", "f.hjkl", "f.undo")):
        state = apply_attempt(state, make_record(t, skill), graph)
    picks = []
    for pick in range(40):
        focus = choose_focus(state, "python", graph, 100 + pick * 30, seed=pick)
        picks.append(focus)
        weak = focus in ("f.xdd", "f.save")
        record = make_record(100 + pick * 30, focus, ms=6000 if weak else 2000, keys=13 if weak else 6)
        state = apply_attempt(state, record, graph)
    counts = Counter(picks)
    assert counts["f.xdd"] + counts["f.save"] <= 0.8 * len(picks)
    assert len(counts) >= 4
    assert _max_window_share(picks, 10) <= 4


def test_share_cap_vector_holds(vector_dir):
    picks = _vector_picks(vector_dir, "24_share_cap")
    assert _max_window_share(picks, 10) <= 4
    assert Counter(picks).most_common(1)[0][0] == "f.xdd"


def test_starvation_guard_vector_holds(vector_dir):
    picks = _vector_picks(vector_dir, "25_starvation_guard")
    assert all("d0" in picks[start:start + 12] for start in range(0, len(picks) - 11))


def test_share_cap_relaxed_for_a_single_skill():
    mini = {"version": 1, "tips": {}, "skills": {"a0": {
        "id": "a0", "tier": 0, "prereqs": [], "order": 0, "targetBase": 1200, "perKey": 180,
        "enabled": True, "emulator": {}, "langWeights": {}}}}
    state = new_state(mini)
    for t in range(6):
        state = apply_attempt(state, make_record(t, "a0", ms=6000), mini)
    assert choose_focus(state, "python", mini, 100, seed=1) == "a0"


def test_choose_focus_interleaves_after_three(graph):
    state = new_state(graph)
    for t in range(3):
        state = apply_attempt(state, make_record(t, "f.modes", ms=9000), graph)
    for t, skill in enumerate(("f.hjkl", "f.undo", "f.xdd", "f.save")):
        state = apply_attempt(state, make_record(10 + t, skill), graph)
    for t in range(3):
        state = apply_attempt(state, make_record(20 + t, "f.modes", ms=9000), graph)
    assert choose_focus(state, "python", graph, 30, seed=1) != "f.modes"


def _vector_picks(vector_dir: Path, name: str) -> list[str]:
    vector = json.loads((vector_dir / f"{name}.json").read_text())
    return [op["expect"] for op in vector["ops"] if op["op"] == "chooseFocus"]


def _max_window_share(picks: list[str], window: int) -> int:
    return max(max(Counter(picks[i:i + window]).values()) for i in range(len(picks) - window + 1))


def test_choose_focus_is_pure(graph):
    state = new_state(graph)
    choose_focus(state, "python", graph, 0)
    assert state == new_state(graph)


def test_exercise_pool_shapes():
    flat = {"python": {"t.quote": ["a", {"id": "b", "skills": ["m.find"]}]}}
    nested = {"langs": {"python": {"t.quote": {"ids": ["a"]}}}}
    assert exercise_pool(flat, "python", "t.quote") == [
        {"id": "a", "skills": ["t.quote"]}, {"id": "b", "skills": ["t.quote", "m.find"]}]
    assert exercise_pool(nested, "python", "t.quote") == [{"id": "a", "skills": ["t.quote"]}]
    assert exercise_pool(nested, "cpp", "t.quote") == []
    build = {"version": 1, "langs": {"python": {"skills": {"t.quote": {"ids": ["a"], "count": 1}}}}}
    assert exercise_pool(build, "python", "t.quote") == [{"id": "a", "skills": ["t.quote"]}]


def test_choose_exercise_avoids_recent(graph):
    index = {"python": {"f.hjkl": ["a", "b", "c"]}}
    state = new_state(graph)
    for t, ex in enumerate(("a", "b")):
        state = apply_attempt(state, make_record(t, "f.hjkl", ex=ex), graph)
    assert {choose_exercise(state, "f.hjkl", "python", index, s, graph) for s in range(20)} == {"c"}
    state = apply_attempt(state, make_record(5, "f.hjkl", ex="c"), graph)
    assert choose_exercise(state, "f.hjkl", "python", index, 0, graph) == "a"
