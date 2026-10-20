"""Tests for vimtrainer_model.placement."""

from conftest import make_record

from vimtrainer_model.attempt import rebuild
from vimtrainer_model.placement import apply_placement, transitive_prereqs
from vimtrainer_model.state import new_state
from vimtrainer_model.vectors import digest


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


def _two_placements(graph):
    """A Python placement, then a C++ placement with no attempt between; both states."""
    python_records = [make_record(i * 20, skill, ms=3000, keys=12, par=12) for i, skill in
                      enumerate(("t.quote", "o.change", "m.match"))]
    cpp_records = [make_record(300, "m.word", ok=False, keys=3, par=3, lang="cpp"),
                   make_record(320, "o.delete", ms=1500, keys=3, par=3, lang="cpp")]
    after_python = apply_placement(new_state(graph), python_records, graph)
    return after_python, apply_placement(after_python, cpp_records, graph)


def test_second_language_placement_leaves_python_untouched(graph):
    after_python, after_cpp = _two_placements(graph)
    for skill_id, langs in after_python["skills"].items():
        if "python" in langs:
            assert after_cpp["skills"][skill_id]["python"] == langs["python"], skill_id


def test_rebuild_splits_placement_batches_by_lang(graph):
    _, state = _two_placements(graph)
    assert digest(rebuild(state["log"], graph)) == digest(state)
    one_batch = apply_placement(new_state(graph), state["log"], graph)
    assert digest(one_batch) != digest(state)


def test_second_language_placement_carries_mastery(graph):
    _, state = _two_placements(graph)
    for skill_id, langs in state["skills"].items():
        if langs.get("python", {}).get("status") == "mastered" and "cpp" in langs:
            assert langs["cpp"]["status"] == "mastered", skill_id
    carried = state["skills"]["o.change"]["cpp"]
    assert (carried["n"], carried["nextReview"]) == (0, 0)
    failed = state["skills"]["m.word"]["cpp"]
    assert (failed["status"], failed["n"], failed["nextReview"]) == ("mastered", 1, 0)
