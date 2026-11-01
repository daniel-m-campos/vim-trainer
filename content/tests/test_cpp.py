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


CONSTANTS = """\
namespace phone {

const int area_code_length = 3;
const int exchange_length = 3;
const int extension_length = 4;

enum class plant {
    grass,
    clover,
    radishes,
};

struct Song {
    std::string title;
    std::string artist;
    std::string album;
};

int digits(int n) {
    int count = 0;
    count += n / 10;
    count += n % 10;
    total_seen = total_seen + count;
    return count;
}

}  // namespace phone
"""


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_x_normal_prefix_and_upper_constants_need_normal_over_a_range(monkeypatch):
    # The fixture has three prefix runs; lift the per-window cap so all of them are drafted.
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    (win,) = cpp.windows(CONSTANTS, SOURCE)
    drafts = [d for d in cpp.generate(win) if d.skill == "x.normal"]
    prefixes = {d.params["text"] for d in drafts if d.template == "prefix_each_line"}
    assert prefixes == {"const ", "// "}  # never `std::`: cinkeys re-indents `std:` as a label
    assert {d.tags[0] for d in drafts if d.template == "upper_constants"} == {"enumerator_list", "declaration_list"}
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert d.kind == "ex" and len(changed) == d.params["n"] >= templates.EX_MIN_LINES, d.task
        assert ":norm " in d.variants[0]
        ex = d.exercise(cpp.LANG.name)
        ex["id"] = d.uid
        for keys in d.variants + d.alternates:
            jobs.append((ex, keys))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    failing = [(drafts[owners[k]].task, v.keys, v.reason) for k, v in enumerate(verdicts) if not v.passed]
    assert not failing


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


def test_move_and_copy_are_edit_kind_with_a_normal_mode_variant(drafts):
    for d in (d for d in drafts if d.skill == "x.copymove"):
        assert d.kind == "edit"
        assert any(not k.startswith(":") for k in d.variants), d.variants


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


# Round 4 template rules (QA #7, #13, #23, #27, #28, #54); the Python side is test_templates_wording.py

RULES = """\
#include "scoring.h"
#include <vector>

namespace scoring {

constexpr int max_bonus = 50;

int score(const std::vector<int>& coins, bool has_priority, Node* head) {
    Node* next = head->next_node;
    int points = 0;
    int bonus = 0;
    for (int coin : coins) {
        points += coin;
        bonus = bonus + 1;
    }
    log("missing points", points);  // points so far
    if (has_priority) {
        points = points * 2 + bonus;
    }
    return points + bonus;
}

}  // namespace scoring
"""


@pytest.fixture(scope="module")
def rules():
    lines = RULES.splitlines()
    win = snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                          tree=cpp.parse("\n".join(lines)))
    return win, cpp.generate(win)


def _passes(draft) -> bool:
    ex = dict(draft.exercise(cpp.LANG.name), id=draft.uid)
    return any(v.passed for v in oracle.verify_many([(ex, k) for k in draft.variants], oracle.subprocess_runner()))


def test_include_paths_are_never_string_targets(rules):
    _, drafts = rules
    inner = [d for d in drafts if d.template in ("change_inner", "delete_inner", "upper_inner")]
    assert any(d.skill == "t.quote" for d in inner)  # the other string still drills t.quote
    assert not [d for d in inner if d.target[0]["start"][0] == 1], "row 1 is the #include"


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_renames_skip_names_in_strings_comments_and_namespaces(rules):
    _, drafts = rules
    renames = [d for d in drafts if d.template in ("rename_here", "rename_all_subst", "upper_word")]
    olds = {d.params.get("old") for d in renames}
    assert "points" not in olds and "scoring" not in olds  # `points` is also in a string and a comment
    (subst,) = [d for d in renames if d.template == "rename_all_subst"]
    assert subst.params["old"] == "bonus" and subst.kind == "ex"
    assert "as a whole word" in subst.task and "`max_bonus` stays" in subst.task  # QA #13
    assert not [d for d in renames if d.lines[d.target[0]["start"][0] - 1].startswith("namespace")]
    assert _passes(subst)  # Neovim's :%s gives the identifier-only buffer


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_case_drills_only_target_constants_cpp(rules):
    _, drafts = rules
    cases = [d for d in drafts if d.template == "upper_word"]
    assert [d.params["word"] for d in cases] == ["max_bonus"]  # constexpr and used once; locals never
    assert cases[0].task == "Make `max_bonus` a constant name: uppercase it to `MAX_BONUS`"
    assert _passes(cases[0])


def test_change_to_end_names_the_declared_variable(rules):
    _, drafts = rules
    tasks = [d.task for d in drafts if d.template == "change_to_end"]
    assert any("`next`" in t for t in tasks), tasks
    assert not any("`*" in t or "`&" in t for t in tasks), tasks  # QA #54: not "`* next`"


def test_type_roles_pick_names_that_fit(rules):
    win, _ = rules
    types = win.cache["types"]
    assert (types["coins"], types["has_priority"], types["head"], types["points"]) == ("many", "flag", "ptr", "count")
    found = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type == "identifier" and templates._text(n) in ("coins", "head"):
            found[templates._text(n)] = templates._new_name(win, templates._text(n), n, "k")
    assert found["coins"] in cpp.ROLE_NAMES["many"] and found["head"] in cpp.ROLE_NAMES["ptr"]



# snippet quality and task wording ========================================================================

MEMBERS = """\
namespace bank {

class Account {
   public:
    void open();
    void deposit(int amount);
    int balance();
   private:
    int balance_{0};
    bool open_{false};
};

int settle(Account& account, int amount) {
    account.deposit(amount);
    int fee = amount / 100;
    log_fee(fee);
    return account.balance() - fee;
}

}  // namespace bank
"""


def test_comment_out_drills_only_take_statements_in_function_bodies(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    lines = MEMBERS.splitlines()
    win = snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                          tree=cpp.parse("\n".join(lines)))
    drafts = [d for d in cpp.generate(win) if d.template == "prefix_each_line" and d.params["text"] == "// "]
    rows = {r["start"][0] for d in drafts for r in d.target}
    assert drafts and rows <= {14, 15, 16, 17}, rows  # settle's body, never the class members


def test_cpp_angle_pairs_nested_by_the_tree_say_inner(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 20)
    text = "int f(std::map<int, std::vector<std::string>> const& m, int n) {\n    return n < 3 ? 1 : 2;\n}\n"
    lines = text.splitlines()
    win = snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines), tree=cpp.parse(text))
    tasks = [d.task for d in cpp.generate(win) if d.skill == "t.angle"]
    assert any("`std::string` inside the inner angle brackets" in t for t in tasks), tasks
    assert not any("inner" in t and "int, std::vector" in t for t in tasks), tasks


def test_cpp_indent_task_counts_lines_without_blanks(drafts):
    for d in (d for d in drafts if d.template == "indent_block"):
        (rng,) = d.target
        n = rng["end"][0] - rng["start"][0] + 1
        assert f"these {n} lines one level" in d.task
        assert all(d.lines[r].strip() for r in range(rng["start"][0] - 1, rng["end"][0]))
