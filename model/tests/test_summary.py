"""Tests for vimtrainer_model.summary."""

from conftest import make_record

from vimtrainer_model.attempt import apply_attempt
from vimtrainer_model.state import new_state
from vimtrainer_model.summary import session_summary


def test_session_summary_reports_mastery_unlock_and_tip(graph):
    state = new_state(graph)
    for t in range(8):
        state = apply_attempt(state, make_record(t, "f.hjkl"), graph)
    for t in range(100, 104):
        state = apply_attempt(state, make_record(t, "m.word", ms=2500), graph)
    summary = session_summary(state, 100, graph)
    assert summary["improved"][0]["skill"] == "m.word"
    assert summary["mastered"] == []
    assert summary["unlocked"] == []
    assert summary["tip"] == graph["tips"]["m.word"]
    earlier = session_summary(state, 0, graph)
    assert earlier["mastered"] == ["f.hjkl"]
    assert "m.word" in earlier["unlocked"]
