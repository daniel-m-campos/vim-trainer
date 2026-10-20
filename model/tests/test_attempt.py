"""Tests for vimtrainer_model.attempt."""

from conftest import make_record

from vimtrainer_model.attempt import apply_attempt, rebuild
from vimtrainer_model.state import new_state


def _run(graph, records):
    state = new_state(graph)
    for record in records:
        state = apply_attempt(state, record, graph)
    return state


def test_apply_attempt_does_not_mutate_input(graph):
    state = new_state(graph)
    apply_attempt(state, make_record(1, "f.hjkl"), graph)
    assert state == new_state(graph)


def test_apply_attempt_ema_alpha(graph):
    state = _run(graph, [make_record(1, "f.hjkl", ms=2000), make_record(2, "f.hjkl", ms=3000)])
    assert state["skills"]["f.hjkl"]["python"]["timeEma"] == 2100


def test_apply_attempt_masters_after_eight_and_unlocks(graph):
    state = _run(graph, [make_record(t, "f.hjkl") for t in range(8)])
    assert state["skills"]["f.hjkl"]["python"]["status"] == "mastered"
    assert state["skills"]["m.word"]["python"]["status"] == "active"


def test_apply_attempt_composite_credits_every_skill(graph):
    state = _run(graph, [make_record(1, "f.hjkl+f.modes")])
    assert state["skills"]["f.hjkl"]["python"]["n"] == 1
    assert state["skills"]["f.modes"]["python"]["n"] == 1


def test_apply_attempt_failures_only_touch_accuracy(graph):
    state = _run(graph, [make_record(1, "f.undo"), make_record(2, "f.undo", ok=False, ms=99999)])
    st = state["skills"]["f.undo"]["python"]
    assert (st["n"], st["acc"], st["timeEma"]) == (2, 0.5, 2000)


def test_rebuild_reproduces_state(graph):
    state = _run(graph, [make_record(t, "f.hjkl", ms=1800 + t) for t in range(12)])
    assert rebuild(state["log"], graph) == state
