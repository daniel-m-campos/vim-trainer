"""Tests for vimtrainer_model.state."""

import pytest

from vimtrainer_model.state import (
    confidence,
    interval_days,
    new_skill_state,
    new_state,
    passes_mastery_gate,
    prepare,
)


def _st(**fields):
    st = new_skill_state("active")
    st.update(fields)
    return st


def test_confidence_speed_capped_and_efficiency_clamped(graph):
    assert confidence(graph, "t.quote", _st(timeEma=1000.0, effEma=1.0, parEma=6.0)) == 1.0
    assert confidence(graph, "t.quote", _st(timeEma=4560.0, effEma=1.0, parEma=6.0)) == pytest.approx(0.5)
    assert confidence(graph, "t.quote", _st(timeEma=1000.0, effEma=4.0, parEma=6.0)) == 0.5
    assert confidence(graph, "t.quote", _st()) == 0.0


def test_mastery_gate_needs_all_four(graph):
    good = dict(timeEma=2000.0, effEma=1.2, parEma=6.0, acc=0.9, n=8)
    assert passes_mastery_gate(graph, "t.quote", _st(**good))
    for override in ({"n": 7}, {"acc": 0.85}, {"effEma": 1.3}, {"timeEma": 2300.0}):
        assert not passes_mastery_gate(graph, "t.quote", _st(**{**good, **override}))


def test_interval_days_doubles_to_sixty():
    assert [interval_days(r) for r in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]


def test_prepare_activates_tier_zero_only(graph):
    state = new_state(graph)
    prepare(state, graph, "python", 0)
    active = {s for s, langs in state["skills"].items() if langs.get("python", {}).get("status") == "active"}
    assert active == {"f.modes", "f.hjkl", "f.undo", "f.xdd", "f.save"}
