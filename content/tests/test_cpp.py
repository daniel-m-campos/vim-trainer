"""C++ language support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil
import tomllib

import pytest

from vimtrainer_content import oracle, snippets, sources, templates
from vimtrainer_content.lang import cpp

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = {"repo": "fixture/inventory-cpp", "path": "src/inventory.cpp", "commit": None, "license": "MIT"}
INVENTORY = """\
#include <map>
#include <string>
#include <vector>

using std::string;
using std::vector;

namespace inventory {

// Count how often each word occurs.
std::map<std::string, int> count_words(const std::vector<std::string>& words) {
    std::map<std::string, int> counts;
    for (const auto& word : words) {
        counts[word + "_key"] += 1;  // tally this word
        total_seen = total_seen + 1;
    }
    return counts;
}

int lookup(const std::map<std::string, int>& counts, const string& name) {
    auto it = counts.find(name);
    if (it == counts.end()) {
        throw std::invalid_argument("missing item name");
        log_error("lookup", name, 3);
        report->failures.push_back(name);
        return -1;
    }
    return it->second + offsets[name.size() - 1];
}

}  // namespace inventory
"""


@pytest.fixture(scope="module")
def window():
    (win,) = cpp.windows(INVENTORY, SOURCE)
    return win


@pytest.fixture(scope="module")
def drafts(window):
    return cpp.generate(window)


def _long_file(functions: int) -> str:
    body = "\n\n".join(f"int f{i}(int x) {{\n    return x + {i};\n}}" for i in range(functions))
    return f"#include <string>\n\nnamespace big {{\n\n{body}\n\n}}  // namespace big\n"


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with cpp.registered():
        for uses in cpp.LANG.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in cpp.LANG.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    assert cpp.LANG.comment_leader == "//"
    assert {"->", "::", ";", "<", ">"} <= set(cpp.LANG.find_targets)


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    for skill in cpp.TARGET_SKILLS:
        assert skill in graph["skills"], skill
        assert graph["skills"][skill]["langWeights"]["cpp"] == cpp.WEIGHTS[skill], skill


def test_sources_toml_pins_exercism_cpp():
    (src,) = [s for s in sources.load_sources() if s.lang == "cpp"]
    assert src.repo == "github.com/exercism/cpp" and src.license == "MIT"
    assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
    assert set(src.include) == {
        "exercises/practice/*/.meta/example.cpp", "exercises/practice/*/.meta/example.h",
        "exercises/concept/*/.meta/exemplar.cpp",
    }
    raw = tomllib.loads((sources.SOURCES_TOML).read_text())
    assert sum(s["lang"] == "cpp" for s in raw["source"]) == 1


# Windows ==========================================================================================


def test_window_is_whole_parseable_file(window):
    assert window.lines[0] == "#include <map>" and window.lines[-1] == "}  // namespace inventory"
    assert not window.root.has_error
    assert snippets.size_problem(window.lines) is None


def test_long_namespace_is_split_into_parseable_windows():
    text = _long_file(80)  # > 256 lines: py-tree-sitter 0.26.0 crashes on Point.row there
    assert len(text.splitlines()) > 300
    wins = cpp.windows(text, SOURCE)
    assert len(wins) > 5
    for win in wins:
        assert not win.root.has_error
        assert snippets.size_problem(win.lines) is None
        assert win.lines[0] != "}" and "// namespace big" not in win.lines[-1]


def test_node_frequency_counts_cpp_nodes():
    freq = cpp.node_frequency([INVENTORY])
    assert freq["counts"]["template_argument_list"] >= 4 and freq["lines"] == len(INVENTORY.splitlines())


# Templates ========================================================================================


def test_drafts_cover_the_cpp_skills(drafts):
    skills = {d.skill for d in drafts}
    assert {"t.quote", "t.paren", "t.brace", "t.bracket", "t.angle", "t.word", "m.find", "m.match", "m.rel", "n.unmatched",
            "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove"} <= skills


def test_prime_feeds_the_shared_helpers(window, drafts):
    comment_row = window.lines.index("// Count how often each word occurs.")
    assert comment_row in templates._prose_rows(window)
    row = next(r for r, ln in enumerate(window.lines) if "missing item name" in ln)
    col = window.lines[row].index("missing")
    assert (row, col) in templates._string_cells(window)
    assert templates._delim_count(window, "<") >= 2


def test_angle_drafts_use_the_angle_text_object(drafts):
    angles = [d for d in drafts if d.skill == "t.angle"]
    assert angles
    for d in angles:
        assert d.variants[0] in ("di<",) or d.variants[0].startswith("ci<")
        row = d.cursor[0] - 1
        assert d.lines[row].rfind("<", 0, d.cursor[1]) >= 0


def test_indent_block_prefers_the_brace_object(drafts):
    blocks = [d for d in drafts if d.template == "indent_block"]
    assert blocks
    for d in blocks:
        assert d.variants[0] in (">i{", "<i{")
        assert d.expect["lines"] == d.window.lines and d.lines != d.window.lines


def test_trailing_comment_skips_bare_closing_brace(drafts):
    comments = [d for d in drafts if d.template == "delete_trailing_comment"]
    assert [d.lines[d.cursor[0] - 1].strip() for d in comments] == ['counts[word + "_key"] += 1;  // tally this word']
    assert comments[0].variants[0] == "f/D"


MID_LINE_COMMENT = """\
int sum_items(const std::vector<int>& items, int limit) {
    int total = compute_total(/* fast */ items, limit);
    int extra = compute_total(items, limit);  /* trailing note */
    report->failures.push_back(total);
    if (total > limit) {
        log_warning("over the limit", total);
    }
    auto label = std::string("items");
    return total + extra + label.size();
}
"""


@pytest.fixture(scope="module")
def mid_line():
    (win,) = cpp.windows(MID_LINE_COMMENT, SOURCE)
    return win


def test_trailing_comment_needs_nothing_after_it(mid_line):
    comments = [d for d in cpp.generate(mid_line) if d.template == "delete_trailing_comment"]
    assert [d.lines[d.cursor[0] - 1].strip() for d in comments] == [
        "int extra = compute_total(items, limit);  /* trailing note */"]


def test_delete_inner_names_the_delimiters(drafts, mid_line):
    tasks = [d.task for d in [*drafts, *cpp.generate(mid_line)] if d.template == "delete_inner"]
    assert any("keeping the quotes" in t for t in tasks) and any("keeping the parentheses" in t for t in tasks)
    for t in tasks:
        assert not re.search(r"keeping the [()\[\]{}<>'\"]", t), t


def test_role_reads_cpp_functions_and_members(mid_line):
    found = {}
    stack = [mid_line.root]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type in ("identifier", "field_identifier"):
            found[templates._text(n)] = (templates._role(n, templates._text(n)), templates._is_member(n))
    assert found["sum_items"] == ("call", False)  # function_declarator
    assert found["log_warning"] == ("call", False)  # call_expression
    assert found["size"] == ("call", True)  # method call through field_expression
    assert found["failures"][1] and not found["report"][1]


def test_find_char_counts_the_first_char_of_multi_char_targets(drafts):
    finds = [d for d in drafts if d.skill == "m.find"]
    assert finds
    for d in finds:
        row, start, col = d.cursor[0] - 1, d.cursor[1], d.expect["cursor"][1]
        line = d.lines[row]
        motion = d.variants[0]
        n, ch = (int(motion[0]), motion[2]) if motion[0].isdigit() else (1, motion[1])
        assert line.count(ch, start + 1, col + 1) == n and line[col] == ch


def test_move_and_copy_only_touch_whole_one_line_items(drafts):
    moves = [d for d in drafts if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        assert sorted(d.expect["lines"]) == sorted(d.lines + ([] if d.template == "move_line" else
                                                               [d.lines[d.cursor[0] - 1]]))


def test_change_rhs_fits_the_value_and_keeps_the_semicolon(drafts):
    for d in (d for d in drafts if d.template == "change_to_end"):
        row = d.cursor[0] - 1
        assert d.expect["lines"][row].endswith(";")
        assert d.params["text"] not in ("value", "X")


# Oracle ===========================================================================================


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_every_draft_has_a_variant_that_passes_in_neovim(drafts):
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = d.exercise(cpp.LANG.name)
        ex["id"] = d.uid
        for keys in d.variants:
            jobs.append((ex, keys))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    passed = {owners[k] for k, v in enumerate(verdicts) if v.passed}
    failing = [(d.template, d.skill, d.task, d.variants) for i, d in enumerate(drafts) if i not in passed]
    assert not failing
