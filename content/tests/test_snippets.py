"""Tests for vimtrainer_content.snippets (windowing, size and secret gates)."""

from conftest import FIXTURES
from vimtrainer_content import snippets


def test_window_is_dedented_parseable_and_bounded(window):
    assert snippets.MIN_LINES <= len(window.lines) <= snippets.MAX_LINES
    assert not window.root.has_error
    assert window.first_line == 1
    assert snippets.size_problem(window.lines) is None


def test_docstrings_are_shortened_to_summary():
    lines = ['def f():', '    """Summary line.', '', '    More text.', '    """', '    return 1']
    out, origin = snippets.shorten_docstrings(lines)
    assert out == ['def f():', '    """Summary line."""', '    return 1']
    assert origin == [1, 2, 6]


def test_window_records_original_line_numbers(window):
    text = (FIXTURES / "src" / "inventory.py").read_text().splitlines()
    assert window.last_line == len(text)
    assert window.lines[-1] == text[-1]


def test_big_definitions_are_split_into_body_windows():
    body = "\n".join(f"    x{i} = {i}" for i in range(60))
    text = f"def big():\n{body}\n    return x1\n"
    wins = snippets.windows(text, {"repo": "r", "path": "p"})
    assert wins and all(len(w.lines) <= snippets.MAX_LINES for w in wins)
    assert all(not w.lines[0].startswith(" ") for w in wins)  # body windows are dedented


def test_size_problem_rejects_short_wide_tab_and_non_ascii():
    ok = ["x = 1"] * 8
    assert snippets.size_problem(ok) is None
    assert "lines" in snippets.size_problem(["x"] * 7)
    assert "lines" in snippets.size_problem(["x"] * 41)
    assert "wider" in snippets.size_problem(ok[:-1] + ["x" * 101])
    assert "tab" in snippets.size_problem(ok[:-1] + ["\tx"])
    assert "ASCII" in snippets.size_problem(ok[:-1] + ["s = 'café'"])


def test_secret_scan():
    assert snippets.secret_findings(["contact = 'someone@example.com'"]) == ["email"]
    assert "aws-key" in snippets.secret_findings(["key = AKIAABCDEFGHIJKLMNOP"])
    assert "assigned-secret" in snippets.secret_findings(["password = 'hunter2hunter2'"])
    assert snippets.secret_findings(["x = compute(a, b)"]) == []


def test_header_comments_never_enter_a_window():
    text = "# Copyright (c) 2020 Someone\n# Licensed under MIT\n" + "\n".join(f"x{i} = {i}" for i in range(12))
    (win,) = snippets.windows(text, {"repo": "r", "path": "p"})
    assert not any("Copyright" in ln or "Licensed" in ln for ln in win.lines)


def test_node_frequency_counts_per_100_lines():
    freq = snippets.node_frequency(["x = 'a'\ny = 'b'\n", "z = 1\n"])
    assert freq["lines"] == 3
    assert freq["counts"]["string"] == 2
    assert abs(freq["per100Lines"]["string"] - 66.667) < 0.01


def test_pick_is_deterministic():
    assert snippets.pick("abcdef", "k", 1) == snippets.pick("abcdef", "k", 1)
