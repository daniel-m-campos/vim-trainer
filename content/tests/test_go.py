"""Go support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil
import tomllib

import pytest

from vimtrainer_content import build, gates, oracle, snippets, sources, templates
from vimtrainer_content.lang import go

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = {"repo": "fixture/inventory-go", "path": "inventory.go", "commit": None, "license": "MIT"}
NVIM = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
# gofmt style: tab indent, spaces for alignment. Windows re-indent the tabs to four spaces.
INVENTORY_GO = """\
package inventory

const max_items = 50

// Item is one line of the inventory.
type Item struct {
\tName  string
\tCount int // units on hand
}

// countWords tallies how often each word occurs.
func countWords(words []string) map[string]int {
\tcounts := map[string]int{"total": 0, "seen": 1}
\tfor _, word := range words {
\t\tcounts[word+"_key"] = counts[word] + 1 // tally this word
\t\ttotalSeen = totalSeen + 1
\t}
\treturn counts
}

func Lookup(counts map[string]int, name string) (Item, error) {
\tfound, ok := counts[name]
\tlabel := `items: (raw) [x]`
\theader := `name and count`
\tif !ok {
\t\tlogError("lookup", name, 3)
\t\treport.failures = append(report.failures, name)
\t\treturn Item{}, errors.New("missing item name")
\t}
\treturn Item{Name: label + header, Count: found + offsets[len(name)-1]}, nil
}
"""
WRITER = """\
func render(rows []Row, w io.Writer) error {
\tvar sb strings.Builder
\tsb.WriteString("header")
\tsb.WriteString(separator)
\tsb.WriteString("footer")

\ttotal := 0
\tcount := len(rows)
\tlimit := count * 2
\tfmt.Fprintln(w, sb.String(), total, limit)
\treturn nil
}
"""


def _windows(text: str) -> list[snippets.Window]:
    return go.windows(text, SOURCE)


def _window(text: str) -> snippets.Window:
    (win,) = _windows(text)
    return win


def _drafts(text: str) -> list[templates.Draft]:
    return [d for w in _windows(text) for d in go.generate(w)]


@pytest.fixture(scope="module")
def drafts():
    return _drafts(INVENTORY_GO) + _drafts(WRITER)


def _replay(drafts, keys_of=lambda d: d.variants):
    """Per draft, the keys that pass in Neovim."""
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = dict(d.exercise(go.LANG.name), id=d.uid)
        for keys in keys_of(d):
            jobs.append((ex, keys))
            owners.append(i)
    passed: dict[int, list[str]] = {i: [] for i in range(len(drafts))}
    for k, v in enumerate(oracle.verify_many(jobs, oracle.subprocess_runner())):
        if v.passed:
            passed[owners[k]].append(v.keys)
    return passed


def _accepted(draft) -> dict:
    """The exercise the build would ship for ``draft`` (every gate, par search included)."""
    report = build.Report()
    verdicts = build._replay([draft], go.LANG, workers=1, report=report)
    ex, gate, detail = build.evaluate(draft, go.LANG, verdicts[id(draft)], "nvim test")
    assert ex is not None, (draft.task, gate, detail)
    return ex


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with go.registered():
        for uses in go.LANG.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in go.LANG.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    assert (go.LANG.name, go.LANG.short, go.LANG.grammar, go.LANG.comment_leader) == ("go", "go", "go", "//")
    assert {"(", "=", ".", ",", ":="} <= set(go.LANG.find_targets)


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    for skill in go.TARGET_SKILLS:
        assert graph["skills"][skill]["langWeights"]["go"] == go.WEIGHTS[skill], skill
    assert set(go.WEIGHTS) == set(go.TARGET_SKILLS) and "t.angle" not in go.TARGET_SKILLS


def test_sources_toml_pins_exercism_go():
    raw = tomllib.loads(sources.SOURCES_TOML.read_text())
    (src,) = [s for s in sources.load_sources() if s.lang == "go"]
    assert src.repo == "github.com/exercism/go" and src.license == "MIT" and src.name == "exercism-go"
    assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
    assert set(src.include) == {"exercises/practice/*/.meta/example.go", "exercises/concept/*/.meta/exemplar.go"}
    assert sum(s["lang"] == "go" for s in raw["source"]) == 1


# Windows ==========================================================================================


def test_windows_are_parseable_and_reindented_to_four_spaces():
    wins = _windows(INVENTORY_GO)
    assert wins and wins[0].lines[0] == "package inventory"
    lines = [ln for w in wins for ln in w.lines]
    assert "        counts[word+\"_key\"] = counts[word] + 1 // tally this word" in lines
    assert "    Name  string" in lines  # alignment spaces after the indent are kept
    for win in wins:
        assert not win.root.has_error
        assert snippets.size_problem(win.lines) is None
        assert all((len(ln) - len(ln.lstrip())) % 4 == 0 for ln in win.lines)


def test_reindent_turns_leading_tabs_into_four_spaces_and_leaves_raw_strings():
    lines = ["func f() string {", "\ts := `a", "\tb`", "\t\t  x := 1", "\treturn s\t// tab", "}"]
    assert go.reindent(lines) == [
        "func f() string {", "    s := `a", "\tb`", "        " + "  x := 1", "    return s\t// tab", "}"]
    four = ["func f() int {", "    return 1", "}"]
    assert go.reindent(four) == four


def test_a_tab_left_in_a_raw_string_drops_the_window():
    body = "\n".join(f"\tv{i} := compute({i})" for i in range(8))
    text = f"func usage() string {{\n{body}\n\treturn `name:\n\tthe tool`\n}}\n"
    assert _windows(text) == []
    assert _windows(text.replace("\tthe tool", "the tool"))  # without the tab it ships


def test_long_struct_is_split_into_windows_of_fields_inside_the_struct():
    fields = "\n".join(f"\tfield{i} int // value {i}" for i in range(300))  # > 256 lines: see js._spans
    wins = _windows(f"type Big struct {{\n{fields}\n}}\n")
    assert len(wins) > 5
    for win in wins:
        assert not win.root.has_error
        assert win.lines[0] == "type Big struct {" and win.lines[-1] == "}"
        assert win.lines[1].startswith("    field")
    assert len({w.first_line for w in wins}) == len(wins)  # first_line is the fields', so window keys stay unique


def test_long_function_and_const_group_are_split():
    body = "\n".join(f"\tv{i} := compute({i}, items)" for i in range(60))
    wins = _windows(f"func big(items []int) {{\n{body}\n}}\n")
    assert wins and all(not w.root.has_error and w.lines[0].startswith("v") for w in wins)
    consts = "\n".join(f"\tcode{i} = {i}" for i in range(60))
    wins = _windows(f"const (\n{consts}\n)\n")
    assert len(wins) > 1 and all(w.lines[0] == "const (" and w.lines[-1] == ")" for w in wins)


def test_node_frequency_counts_go_nodes():
    freq = go.node_frequency([INVENTORY_GO])
    assert freq["counts"]["raw_string_literal"] == 2 and freq["counts"]["composite_literal"] >= 2
    assert freq["lines"] == len(INVENTORY_GO.splitlines())


def test_quality_gate_reads_go_windows():
    for win in _windows(INVENTORY_GO):
        assert snippets.quality_problem(win.lines, win.root) is None
    stub = "func TwoFer(name string) string {\n\t// TODO: implement\n\tpanic(\"implement me\")\n}\n" + "\n".join(
        f"const c{i} = {i}" for i in range(6))
    (win,) = _windows(stub)
    assert snippets.quality_problem(win.lines, win.root) == "scaffold"


# Templates ========================================================================================


def test_drafts_cover_every_target_skill(drafts):
    assert {d.skill for d in drafts} == set(go.TARGET_SKILLS)


def test_prime_feeds_the_shared_helpers():
    win = _windows(INVENTORY_GO)[0]
    go.generate(win)
    comment_row = win.lines.index("// Item is one line of the inventory.")
    assert comment_row in templates._prose_rows(win)
    assert templates._delim_count(win, '"') >= 2 and templates._delim_count(win, "{") >= 2


def test_every_task_singles_out_its_target(drafts):
    """Gate 6's wording rules: a quoted target names one place, the old items are not reordered."""
    for d in drafts:
        ex = d.exercise(go.LANG.name)
        assert gates.ambiguity_problem(ex, d.target, d.task) is None, d.task
        assert gates.permutation_problem(d.task) is None, d.task
        assert "``" not in d.task and d.params.get("text") not in ("value", "X"), d.task


def test_raw_strings_are_masked_and_drilled_with_backticks(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    win = _windows(INVENTORY_GO)[-1]
    drafts = go.generate(win)
    row = next(r for r, ln in enumerate(win.lines) if "`items" in ln)
    raw = range(win.lines[row].index("`"), win.lines[row].rindex("`") + 1)
    assert all((row, c) in win.cache["strings"] for c in raw)
    ticks = [d for d in drafts if d.skill == "t.quote" and d.params["open"] == "`"]
    assert {d.template for d in ticks} == {"change_inner", "delete_inner"}
    assert all("inside the backticks" in d.task and d.variants[0][:3] in ("ci`", "di`") for d in ticks)
    looked = 0
    for d in drafts:  # no motion, bracket or rename drill starts, lands or renames inside the raw string
        if d.template in ("find_char", "jump_match", "jump_block_end") or d.skill in ("t.paren", "t.bracket", "t.word", "x.subst"):
            spots = [tuple(d.cursor), *([tuple(d.expect["cursor"])] if "cursor" in d.expect else [])]
            spots += [tuple(r["start"]) for r in d.target]
            assert not any(line == row + 1 and col in raw for line, col in spots), (d.template, d.task)
            looked += 1
    assert looked > 10


def test_struct_literals_are_brace_text_objects(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    braces = [d for d in _drafts(INVENTORY_GO) if d.skill == "t.brace" and d.params.get("open") == "{"
              and d.tags[0] == "literal_value"]
    assert {d.template for d in braces} == {"change_inner", "delete_inner"}
    assert all("composite literal" in d.task for d in braces), [d.task for d in braces]


def test_func_literal_body_is_named_a_function_literal(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = """\
func order(xs []int, n int) int {
\ttotal := 0
\tcount := len(xs)
\tsort.Slice(xs, func(i, j int) bool { return xs[i] < xs[j] })
\tfor i := 0; i < n; i++ {
\t\ttotal = total + xs[i]
\t}
\treturn total + count
}
"""
    tasks = [d.task for d in _drafts(text) if d.skill == "t.brace" and "return xs[i]" in d.lines[d.cursor[0] - 1]]
    assert tasks and all("this function literal" in t and "this block" not in t for t in tasks), tasks


def test_conditions_have_no_paren_drills(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = """\
func sum(xs []int, n int) int {
\ttotal := 0
\tfor i := 0; i < n; i++ {
\t\tx := xs[i]
\t\tif x > 0 {
\t\t\ttotal = total + (x * 2)
\t\t\tlog(total, x)
\t\t}
\t}
\treturn total
}
"""
    drills = [d for d in _drafts(text) if d.skill in ("t.paren", "m.match")]
    assert drills
    for d in drills:
        for t in d.target:
            line = d.lines[t["start"][0] - 1]
            head = re.match(r"\s*(?:if|for) ", line)
            if head:  # an `if`/`for` header: nothing between the keyword and its `{`
                assert not head.end() <= t["start"][1] < line.rindex("{"), (d.template, d.task)


def test_indent_block_prefers_the_brace_object(drafts):
    blocks = [d for d in drafts if d.template == "indent_block"]
    assert blocks
    for d in blocks:
        assert d.variants[0] in (">i{", "<i{")
        assert d.expect["lines"] == d.window.lines and d.lines != d.window.lines


def test_trailing_comment_skips_bare_closing_brace(drafts):
    comments = [d for d in drafts if d.template == "delete_trailing_comment"]
    assert sorted(d.lines[d.cursor[0] - 1].strip() for d in comments) == [
        "Count int // units on hand",
        'counts[word+"_key"] = counts[word] + 1 // tally this word',
    ]
    assert {d.variants[0] for d in comments} == {"f/D"}


def test_change_rhs_never_assigns_nil_and_fits_the_value(drafts):
    rhs = [d for d in drafts if d.template == "change_to_end"]
    assert rhs
    for d in rhs:
        assert d.variants[0] == f"C{d.params['text']}<Esc>" and d.params["text"] not in ("nil", "value", "X")


def test_format_calls_get_a_string_not_a_number(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = 'func fail(n int) error {\n' + "\n".join(f"\tlog{i}(n)" for i in range(6)) + (
        '\n\treturn fmt.Errorf("bad count %d", n)\n}\n')
    calls = [d for d in _drafts(text) if d.template == "change_inner" and "Errorf" in d.lines[d.cursor[0] - 1]]
    assert calls and all(d.params["text"].startswith('"') for d in calls)


def test_find_char_counts_the_first_char_of_multi_char_targets(drafts):
    finds = [d for d in drafts if d.skill == "m.find"]
    assert finds
    for d in finds:
        row, start, col = d.cursor[0] - 1, d.cursor[1], d.expect["cursor"][1]
        motion = d.variants[0]
        n, ch = (int(motion[0]), motion[2]) if motion[0].isdigit() else (1, motion[1])
        assert d.lines[row].count(ch, start + 1, col + 1) == n and d.lines[row][col] == ch


def test_move_and_copy_only_touch_whole_one_line_items(drafts):
    moves = [d for d in drafts if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        assert d.kind == "edit" and any(not k.startswith(":") for k in d.variants), d.variants
        extra = [] if d.template == "move_line" else [d.lines[d.cursor[0] - 1]]
        assert sorted(d.expect["lines"]) == sorted(d.lines + extra)


def test_delete_inner_names_the_delimiters(drafts):
    tasks = [d.task for d in drafts if d.template == "delete_inner"]
    assert any("keeping the quotes" in t for t in tasks) and any("keeping the parentheses" in t for t in tasks)
    for t in tasks:
        assert not re.search(r"keeping the [()\[\]{}'\"]", t), t


def test_renames_skip_members_literal_keys_strings_and_keywords(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    renames = [d for d in _drafts(INVENTORY_GO) if d.template == "rename_here"]
    assert renames
    for d in renames:
        row, col = d.target[0]["start"][0] - 1, d.target[0]["start"][1]
        line = d.lines[row]
        assert line[col - 1:col] != ".", d.task  # never `report.failures`
        assert not line[d.target[0]["end"][1] + 1:].startswith(":"), d.task  # never the key in `Item{Name: ...}`
        assert line[col:d.target[0]["end"][1] + 1] not in go.LANG.keywords
    exported = [d for d in _drafts(INVENTORY_GO) if d.template in ("rename_here", "rename_all_subst")
                and d.lines[d.target[0]["start"][0] - 1][d.target[0]["start"][1]].isupper()]
    assert exported and all(d.params["text"] not in ("Record", "Item", "Handler") for d in exported)


def test_subst_skips_names_also_used_as_members(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = """\
package list

func (s *Set) size() int {
\treturn len(s.items)
}

func walk(ll *List, tail *Node, size int) int {
\tcount := 0
\tfor tail != nil {
\t\tcount = count + tail.value + size
\t\tll.tail = tail
\t\ttail = tail.next
\t\tsize = size - 1
\t}
\tn := Node{value: count, next: tail}
\tvalue := count
\tvalue = value + 1
\treturn count + value + n.next.value
}
"""
    olds = {d.params["old"] for d in _drafts(text) if d.template == "rename_all_subst"}
    assert "count" in olds  # a plain local
    assert not olds & {"tail", "value", "size", "next"}, olds  # a selector field, a literal key, a method


def test_role_reads_go_declarations():
    win = _windows(INVENTORY_GO)[-1]
    go.generate(win)
    assert win.cache["types"]["name"] == "text" and win.cache["types"]["counts"] == "many"
    names = {}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type == "identifier":
            names[templates._text(n)] = templates._role(n, templates._text(n), win)
    assert names["logError"] == "call" and names["Lookup"] == "call"


def test_toggle_export_only_takes_names_defined_once(drafts):
    toggles = [d for d in drafts if d.template == "toggle_case"]
    assert [d.params["word"] for d in toggles] == ["render"]  # countWords is in its doc comment, lookup in a string
    for d in toggles:
        word = d.params["word"]
        assert sum(ln.count(word) for ln in d.lines) == 1
        assert d.variants[0] == "b~" and d.cursor[1] >= d.target[0]["start"][1] + 3
        assert d.task.startswith("Export" if word[0].islower() else "Unexport")


# Oracle ===========================================================================================


@NVIM
def test_every_draft_has_a_variant_that_passes_in_neovim(drafts):
    passed = _replay(drafts)
    failing = [(d.template, d.skill, d.task, d.variants) for i, d in enumerate(drafts) if not passed[i]]
    assert not failing


@NVIM
def test_x_normal_prefix_and_comment_out_need_normal_over_a_range(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    drafts = [d for d in _drafts(WRITER) if d.skill == "x.normal"]
    assert {d.params["text"] for d in drafts} == {"sb.", "// "}
    for d in drafts:
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert d.kind == "ex" and len(changed) == d.params["n"] >= templates.EX_MIN_LINES, d.task
        assert ":norm " in d.variants[0]
    passed = _replay(drafts, lambda d: d.variants + d.alternates)
    assert all(len(passed[i]) == len(d.variants) + len(d.alternates) for i, d in enumerate(drafts))


@NVIM
def test_shipped_exercises_for_the_go_only_templates():
    """The build accepts a struct literal ci{ (typing `:` must not re-indent the line), a raw
    string ci`, and the export toggle, with the drilled keys as par."""
    drafts = _drafts(INVENTORY_GO) + _drafts(WRITER)
    picks = {
        "literal": next(d for d in drafts if d.template == "change_inner" and d.tags[0] == "literal_value"
                        and ":" in d.params["text"]),
        "raw": next(d for d in drafts if d.template == "change_inner" and d.params.get("open") == "`"),
        "export": next(d for d in drafts if d.template == "toggle_case"),
    }
    assert _accepted(picks["literal"])["par"]["keys"].startswith("ci{")
    assert _accepted(picks["raw"])["par"]["keys"].startswith("ci`")
    assert _accepted(picks["export"])["par"]["keys"] == "b~"
