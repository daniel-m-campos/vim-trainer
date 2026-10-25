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
    assert all(w.indent == 4 for w in wins)  # and remember it: their top level is not the file's


def test_top_level_window_has_no_indent(window):
    assert window.indent == 0


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


# Snippet quality gate (QA #12) ====================================================================

CPP_HEADER = """\
#pragma once

#include <string>

namespace affine_cipher {

std::string encode(const std::string& input, int a, int b);
std::string decode(const std::string& input, int a, int b);

}  // namespace affine_cipher
"""

CPP_STUB = """\
#include "list_ops.h"

namespace list_ops {

int length(const std::vector<int>& items) {
    // TODO: add your solution here
    throw std::logic_error("Waiting to be implemented");
}

}  // namespace list_ops
"""

CPP_CLASS = """\
namespace complex_numbers {
class Complex {
   public:
    Complex(double, double);
    Complex operator+(const Complex& other) const;
    Complex operator-(const Complex& other) const;
    Complex operator*(const Complex& other) const;
    double abs() const;
    double real() const;
    double imag() const;
   private:
    double re, im;
};
}  // namespace complex_numbers
"""

CPP_CODE = """\
namespace darts {

int score(float x, float y) {
    auto distance = std::hypot(x, y);
    if (distance <= 1.0) {
        return 10;
    } else if (distance <= 5.0) {
        return 5;
    }
    return 0;
}

}  // namespace darts
"""


def _cpp_problem(text):
    from vimtrainer_content.lang import cpp

    lines = text.splitlines()
    return snippets.quality_problem(lines, cpp.parse("\n".join(lines)).root_node)


def _py_problem(text):
    lines = text.splitlines()
    return snippets.quality_problem(lines, snippets.parse("\n".join(lines)).root_node)


def test_quality_gate_rejects_cpp_prototype_headers_and_scaffold():
    assert _cpp_problem(CPP_HEADER).startswith("declaration-only")
    assert _cpp_problem(CPP_STUB) == "scaffold"
    assert _cpp_problem(CPP_CODE) is None
    assert _cpp_problem(CPP_CLASS) is None  # a class declaration holds enough code to drill


def test_quality_gate_on_python_rejects_scaffold_and_thin_but_not_compact_code():
    stub = "def solve(puzzle):\n    raise NotImplementedError('fill me in')\n" + "\n" * 6
    thin = "def drinks_water():\n    answer, _ = solution()\n    return answer\n\n\ndef owns_zebra():\n" \
           "    _, answer = solution()\n    return answer\n"
    compact = ("def find_anagrams(word, candidates):\n    return [candidate\n            for candidate in candidates\n"
               "            if _letters(candidate) == _letters(word)\n            if candidate.lower() != word.lower()]\n\n\n"
               "def _letters(word):\n    return sorted(word.lower())\n")
    assert _py_problem(stub) == "scaffold"
    assert _py_problem(thin).startswith("thin")
    assert _py_problem(compact) is None  # two statements are fine: Python has no prototypes


def test_quality_gate_does_not_take_a_lowercase_todo_identifier_for_scaffold():
    code = ("todo = []\n\n\ndef add_todo(todo):\n    todo = todo.strip()\n    if todo not in TODO_LIST:\n"
            "        todo_list.append(todo)\n    return len(todo_list)\n")
    assert _py_problem(code) != "scaffold"


def test_trim_comment_edges_drops_a_dangling_comment_and_a_comment_tail():
    lines = ["// lost returns true if Pac-Man loses.", "// It is true when Pac-Man touches a ghost and",
             "// does not have a power pellet.", "bool lost(bool a, bool b) {", "    return a && !b;", "}",
             "", "// won returns true if Pac-Man wins.", "// It is true when"]
    assert snippets.trim_comment_edges(lines, 2, 8) == (3, 5)
    assert snippets.trim_comment_edges(lines, 0, 5) == (0, 5)  # a comment block that starts here stays
    assert snippets.trim_comment_edges(["#include <x>", "int f();"], 0, 1) == (0, 1)  # directives are code


def test_python_windows_never_end_on_a_comment():
    text = "\n".join(f"x{i} = compute({i}, {i + 1})" for i in range(10)) + "\n# describes code below\n# more\n"
    (win,) = snippets.windows(text, {"repo": "r", "path": "p"})
    assert win.lines[-1] == "x9 = compute(9, 10)"
