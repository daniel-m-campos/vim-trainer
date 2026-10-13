"""Tests that the app-only AttemptRecord fields (seq, beatPar, flag) pass through the model."""

from conftest import make_record

from vimtrainer_model.attempt import apply_attempt
from vimtrainer_model.state import new_state
from vimtrainer_model.vectors import digest


def test_app_fields_are_logged_unchanged_and_ignored(graph):
    plain = make_record(1, "f.hjkl", keys=4)
    extra = {"seq": "jjll", "beatPar": True, "flag": {"reason": "wrong-par", "note": "4 keys is enough"}}
    record = {**plain, **extra}
    state = apply_attempt(new_state(graph), record, graph)
    assert state["log"][-1] == record
    assert {key: state["log"][-1][key] for key in extra} == extra
    assert digest(state) == digest(apply_attempt(new_state(graph), plain, graph))
