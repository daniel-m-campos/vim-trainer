"""Tests for vimtrainer_model.attempt."""

import pytest
from conftest import make_record

from vimtrainer_model.attempt import apply_attempt, rebuild
from vimtrainer_model.constants import DAY
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


def test_slow_review_passes_and_sloppy_review_fails(graph):
    mastered = _run(graph, [make_record(t, "f.save", keys=4, par=4) for t in range(8)])
    assert mastered["skills"]["f.save"]["python"]["status"] == "mastered"
    later = 2 * DAY
    slow = apply_attempt(mastered, make_record(later, "f.save", keys=4, par=4, ms=60000), graph)
    assert slow["skills"]["f.save"]["python"]["status"] == "mastered"
    assert slow["skills"]["f.save"]["python"]["reviewsPassed"] == 1
    sloppy = apply_attempt(mastered, make_record(later, "f.save", keys=7, par=4, ms=1000), graph)
    st = sloppy["skills"]["f.save"]["python"]
    assert (st["status"], st["reviewsPassed"]) == ("active", 0)
    # The attempt moves effEma to 1.075 (factor 0.930); the failed review then scales that by 0.8.
    assert st["confidence"] == pytest.approx(0.8 / 1.075)


def test_rebuild_reproduces_state(graph):
    state = _run(graph, [make_record(t, "f.hjkl", ms=1800 + t) for t in range(12)])
    assert rebuild(state["log"], graph) == state
