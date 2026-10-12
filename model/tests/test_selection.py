"""Tests for vimtrainer_model.selection."""

from conftest import make_record

from vimtrainer_model.attempt import apply_attempt
from vimtrainer_model.selection import choose_exercise, choose_focus, exercise_pool
from vimtrainer_model.state import new_state


def test_choose_focus_lowest_confidence(graph):
    state = new_state(graph)
    for t, skill in enumerate(("f.modes", "f.hjkl", "f.undo", "f.save")):
        state = apply_attempt(state, make_record(t, skill), graph)
    assert choose_focus(state, "python", graph, 10, seed=1) == "f.xdd"


def test_choose_focus_interleaves_after_three(graph):
    state = new_state(graph)
    for t in range(3):
        state = apply_attempt(state, make_record(t, "f.modes", ms=9000), graph)
    for t, skill in enumerate(("f.hjkl", "f.undo", "f.xdd", "f.save")):
        state = apply_attempt(state, make_record(10 + t, skill), graph)
    for t in range(3):
        state = apply_attempt(state, make_record(20 + t, "f.modes", ms=9000), graph)
    assert choose_focus(state, "python", graph, 30, seed=1) != "f.modes"


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
