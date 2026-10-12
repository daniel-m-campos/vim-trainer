"""Tests for vimtrainer_model.placement."""

from conftest import make_record

from vimtrainer_model.placement import apply_placement, transitive_prereqs
from vimtrainer_model.state import new_state


def test_transitive_prereqs(graph):
    assert transitive_prereqs(graph, "o.change") == ["o.delete", "m.word", "m.line", "f.hjkl"]


def test_apply_placement_pass_propagates(graph):
    state = apply_placement(new_state(graph), [make_record(0, "t.quote", ms=3000, keys=12, par=12)], graph)
    skills = state["skills"]
    assert skills["t.quote"]["python"]["n"] == 1
    assert skills["t.quote"]["python"]["status"] == "active"
    for prereq in ("o.change", "o.delete", "m.word", "m.line", "f.hjkl", "f.modes"):
        assert skills[prereq]["python"]["status"] == "mastered"
        assert skills[prereq]["python"]["n"] == 8
    assert state["log"][0]["placement"] is True


def test_apply_placement_failed_prereq_not_inferred(graph):
    records = [make_record(0, "m.line", ok=False), make_record(1, "o.delete", ms=2500, keys=3, par=3)]
    state = apply_placement(new_state(graph), records, graph)
    assert state["skills"]["m.line"]["python"]["status"] != "mastered"
    assert state["skills"]["f.hjkl"]["python"]["status"] == "mastered"


def test_apply_placement_unsampled_open_at_half(graph):
    state = apply_placement(new_state(graph), [make_record(0, "m.word", ms=1500, keys=3, par=3)], graph)
    assert state["skills"]["m.line"]["python"]["status"] == "active"
    assert state["skills"]["m.line"]["python"]["confidence"] == 0.5
