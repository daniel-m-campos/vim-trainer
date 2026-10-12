"""Shared fixtures: the hand-written example exercises."""

import pathlib

import pytest

from vimtrainer_content import oracle

EXAMPLES = sorted((pathlib.Path(__file__).parent.parent / "examples").glob("*.json"))


@pytest.fixture(scope="session")
def examples():
    """Example exercises keyed by id."""
    return {ex["id"]: ex for ex in map(oracle.load_exercise, EXAMPLES)}


@pytest.fixture(scope="session")
def runner():
    """Subprocess runner (one nvim per call)."""
    return oracle.subprocess_runner()


@pytest.fixture(scope="session")
def session():
    """Long-lived pynvim session."""
    with oracle.PynvimSession() as s:
        yield s


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def window():
    """The single snippet window cut from tests/fixtures/src/inventory.py."""
    from vimtrainer_content import snippets

    text = (FIXTURES / "src" / "inventory.py").read_text()
    (win,) = snippets.windows(text, {"repo": "fixture/inventory", "path": "src/inventory.py", "commit": None,
                                     "license": "MIT"})
    return win


@pytest.fixture(scope="session")
def drafts(window):
    """Every draft the Python mapping cuts from the fixture window."""
    from vimtrainer_content import templates
    from vimtrainer_content.lang.python import LANG

    return templates.generate(window, LANG)
