"""Shared fixtures for the model tests."""

import pytest

from vimtrainer_model.graph import load_graph


@pytest.fixture(scope="session")
def graph():
    """The generated skill graph (model/skill-graph.json)."""
    return load_graph()


def make_record(t, skill, ok=True, ms=2000, keys=6, par=6, lang="python", ex=None, hint=False, retry=False):
    """AttemptRecord with defaults: par 6 (target 2280 ms), 2000 ms, at par."""
    return {"t": t, "ex": ex or f"py/{skill}/{t}", "skill": skill, "lang": lang, "ok": ok, "ms": ms,
            "keys": keys, "par": par, "hint": hint, "retry": retry, "undo": 0}
