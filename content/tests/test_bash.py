"""Bash support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil

import pytest

from vimtrainer_content import build, gates, oracle, registers, snippets, sources, splits, templates
from vimtrainer_content.lang import bash

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = {"repo": "fixture/inventory-bash", "path": "inventory.sh", "commit": None, "license": "MIT"}
NVIM = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
# Two-space indent: windows re-indent it to four.
INVENTORY = """\
#!/usr/bin/env bash

max_items=50
declare -a names=(alice bob "carol ann" dave)

# Count how often each word occurs.
count_words() {
  local -i total=0 index
  local label="items: none"
  for (( index = 0; index < ${#names[@]}; index++ )); do
    (( total += index ))
    echo "${names[index]} is number $total" # tally this word
  done
  if (( total > max_items )); then
    echo "too many items" >&2
    log_error "$total" "$label"
    return 1
  fi
  result=$(printf '%s items' "$total")
  width=$((total * 2 + index))
  echo "$result" | tr 'a-z' 'A-Z' | sort -u | head -n "$width"
}
"""
LOOKUP = """\
lookup() {
    local found=${names[$1]} key=$2
    local -A prices=([apple]=3 [pear]=4)
    local description_text="${found} is sold at ${prices[$found]} each"
    case $key in
        first) echo "$found" ;;
        *) echo "unknown key" ;;
    esac
    while read -r line; do
        seen+=("$line")
        echo "${prices[$line]}" # the price
    done < "$inventory_file"
    if [[ -z $found ]]; then
        echo "nothing was found here" >&2
        echo "$description_text"
    else
        echo "${found} was found by ${key}"
        report_item "$found" "$key"
    fi
    echo "${prices[apple_and_pear]}"
}

report_item() {
    printf '%s: %s' "$1" "$2"
    printf 'done with %s' "$1"
}
"""
FIXTURES = {"inventory": INVENTORY, "lookup": LOOKUP}


@pytest.fixture(scope="module")
def drafts():
    """Every draft the fixtures make, not just MAX_PER_WINDOW per template."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(templates, "MAX_PER_WINDOW", 50)
        return [d for text in FIXTURES.values() for w in bash.windows(text, SOURCE) for d in bash.generate(w)]


@pytest.fixture
def many(monkeypatch):
    """Every draft a template makes, not just MAX_PER_WINDOW of them."""
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)


def _window(text: str, indent: int = 0) -> snippets.Window:
    lines = text.splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                           tree=bash.parse("\n".join(lines)), indent=indent)


def _failing(drafts, keys=lambda d: d.variants) -> list:
    """Drafts none of whose ``keys`` pass in Neovim, as (template, task, keys)."""
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = dict(d.exercise(bash.LANG.name), id=d.uid)
        for k in keys(d):
            jobs.append((ex, k))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    passed = {owners[k] for k, v in enumerate(verdicts) if v.passed}
    return [(d.template, d.task, keys(d)) for i, d in enumerate(drafts) if i not in passed]


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with bash.registered():
        for uses in bash.LANG.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in bash.LANG.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    assert (bash.LANG.name, bash.LANG.short, bash.LANG.grammar, bash.LANG.comment_leader) == ("bash", "sh", "bash", "#")
    assert {"(", "=", "$", ";", '"'} <= set(bash.LANG.find_targets) and "#" not in bash.LANG.find_targets
    assert build.LANGS["bash"].lang is bash.LANG and build.LANGS["bash"].skills == bash.TARGET_SKILLS


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    assert set(bash.WEIGHTS) == set(bash.TARGET_SKILLS)
    assert not {"t.angle", "o.case", "x.normal"} & set(bash.TARGET_SKILLS)
    for skill in bash.TARGET_SKILLS:
        assert graph["skills"][skill]["langWeights"]["bash"] == bash.WEIGHTS[skill], skill
    mapped = {use.skill for uses in bash.LANG.nodes.values() for use in uses} | {u.skill for u in bash.LANG.line_templates}
    assert mapped == set(bash.TARGET_SKILLS)


def test_sources_toml_pins_exercism_bash():
    (src,) = [s for s in sources.load_sources() if s.lang == "bash"]
    assert src.repo == "github.com/exercism/bash" and src.license == "MIT" and src.name == "exercism-bash"
    assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
    assert "exercises/practice/*/.meta/example.sh" in src.include


# Windows ==========================================================================================


def test_windows_are_parseable_and_reindented_to_four_spaces():
    wins = bash.windows(INVENTORY, SOURCE)
    lines = [ln for w in wins for ln in w.lines]
    assert wins[0].lines[0] == "#!/usr/bin/env bash" and lines[-1] == "}"
    assert '        echo "${names[index]} is number $total" # tally this word' in lines
    for win in wins:
        assert not win.root.has_error and win.root.type == "program"
        assert snippets.size_problem(win.lines) is None
        assert all(bash._indent(ln) % 4 == 0 for ln in win.lines)


def test_reindent_doubles_two_space_levels_and_turns_tabs_into_spaces():
    lines = ["if x; then", "  y 1 \\", "     2", "fi"]
    assert bash.reindent(lines) == ["if x; then", "    y 1 \\", "         2", "fi"]
    four = ["colors=(", "  red green", ")", "f() {", "    a", "    b", "    if c; then", "        d", "    fi", "}"]
    assert bash.reindent(four) == four  # one line aligned by hand does not make a two-space file
    assert bash.reindent(["f() {", "\tif x; then", "\t\ty", "\tfi", "}"]) == ["f() {", "    if x; then", "        y", "    fi", "}"]
    text = ['x="first', "  second", '\tthird"', "if y; then", "  z", "fi"]
    assert bash.reindent(text) == ['x="first', "  second", '\tthird"', "if y; then", "    z", "fi"]  # string content stays


def test_file_that_does_not_parse_and_window_with_heredoc_are_left_out():
    body = "\n".join(f"echo line {i}" for i in range(10))
    assert bash.windows(body + "\nif then fi (\n", SOURCE) == []
    heredoc = "f() {\n    cat <<EOF\nusage: f\nEOF\n}\n"
    assert bash.windows(heredoc + body + "\n", SOURCE) == []
    assert len(bash.windows(body + "\n", SOURCE)) == 1


def test_long_function_is_split_into_statement_windows():
    body = "\n".join(f"  local v{i}=$(compute {i} \"$1\")" for i in range(60))
    wins = bash.windows(f"big() {{\n{body}\n  echo \"$v1\"\n}}\n", SOURCE)
    assert len(wins) >= 3
    assert all(not w.root.has_error and w.lines[0].startswith("local v") for w in wins)
    assert wins[-1].lines[-1] == 'echo "$v1"'


def test_comment_lines_and_licence_headers_stay_out_of_window_edges():
    text = ("# Copyright (c) someone, MIT licence\n" + "\n".join(f"a{i}=$(f {i})" for i in range(10))
            + "\n# trailing note\n# about nothing\n")
    (win,) = bash.windows(text, SOURCE)
    assert win.lines[0] == "a0=$(f 0)" and win.lines[-1] == "a9=$(f 9)"


def test_node_frequency_and_quality_gate_read_bash():
    freq = bash.node_frequency([INVENTORY])
    assert freq["counts"]["function_definition"] == 1 and freq["lines"] == len(INVENTORY.splitlines())
    for win in bash.windows(INVENTORY, SOURCE):
        assert snippets.quality_problem(win.lines, win.root) is None


# Facts ============================================================================================


def test_prime_tells_code_from_text_inside_double_quotes():
    win = _window(LOOKUP)
    bash.generate(win)
    names, _ = templates._code_names(win)
    row = win.lines.index('        echo "${found} was found by ${key}"')
    assert (row, win.lines[row].index("found")) in names["found"]  # `${found}` inside quotes is code
    strings = templates._string_cells(win)
    assert (row, win.lines[row].index("was")) in strings and (row, win.lines[row].index("found")) not in strings
    assert "found" in names and "key" in names and "line" in names  # `read -r line` names a variable
    assert names["report_item"] == [(17, 8), (22, 0)]  # a call and the definition
    assert "apple" not in names and "first" not in names
    assert templates._prose_rows(win) == set()
    assert templates._delim_count(win, "{") >= 5 and templates._delim_count(win, "'") == 2


def test_rows_that_are_not_statements_are_prose_to_the_register_drills():
    win = _window(LOOKUP)
    bash.generate(win)
    prose, idents = registers._facts(win)
    at = {ln.strip(): r for r, ln in enumerate(win.lines)}
    for text in ('first) echo "$found" ;;', "esac", 'done < "$inventory_file"', "else", "fi", "}"):
        assert at[text] in prose, text
    assert at['report_item "$found" "$key"'] not in prose and at["if [[ -z $found ]]; then"] not in prose
    assert {name for _, _, name in idents} >= {"found", "key", "prices"}
    assert "report_item" not in {name for _, _, name in idents}  # a function name is no variable to swap


def test_gate_cuts_a_bash_line_at_a_comment_hash_only():
    """`$#`, `${#names[@]}` and `${name#x}` are code: after them the gate still sees the brackets."""
    lines = ["for (( i = 0; i < ${#names[@]}; i++ )); do", "    echo ${names[i]} $# ${1#x} (", "done # {"]
    assert not gates.nested_in_same_pair(lines, 1, lines[1].index("{"), "bash")
    assert gates.nested_in_same_pair(["x=( # (", "  $(f) )"], 1, 3, "bash")
    assert gates._code_chars("echo $# ${#a} # note (", "bash") == "echo $# ${#a} "
    assert gates._code_chars("a; #b", "bash") == "a; " and gates._code_chars("# all", "bash") == ""
    assert gates._code_chars("x = y # z", "python") == "x = y "  # other languages as before


# Templates ========================================================================================


def test_drafts_cover_every_target_skill(drafts):
    # The register drills are shared templates with their own tests (test_registers.py).
    shared = set(registers.SKILLS)
    assert {d.skill for d in drafts} - shared == set(bash.TARGET_SKILLS) - shared


def test_every_bash_template_makes_drafts_on_the_fixtures():
    made = dict.fromkeys([*bash.BASH_NODE_TEMPLATES, *bash.BASH_LINE_TEMPLATES], 0)
    for text in FIXTURES.values():
        for win in bash.windows(text, SOURCE):
            win.cache.clear()
            stack = [win.root]
            while stack:
                node = stack.pop()
                stack.extend(node.children)
                for use in bash.LANG.nodes.get(node.type, ()):
                    for name in use.templates:
                        made[name] += len(list(bash.BASH_NODE_TEMPLATES[name](win, node, use.skill, bash.LANG)))
            for use in bash.LANG.line_templates:
                for name in use.templates:
                    if name in registers.TEMPLATES or name in splits.TEMPLATES:
                        continue  # shared, not Bash's own
                    made[name] += len(list(bash.BASH_LINE_TEMPLATES[name](win, use.skill, bash.LANG)))
    assert not [name for name, n in made.items() if n == 0]


def test_inner_object_tasks_name_their_delimiters_and_fitting_replacements(drafts):
    inner = [d for d in drafts if d.template in ("change_inner", "delete_inner")]
    assert {d.params["open"] for d in inner} >= {"(", "[", "{", "'", '"'}
    nouns = " ".join(d.task for d in inner)
    for noun in ("expansion", "command substitution", "arithmetic expansion", "array", "subscript"):
        assert f"of this {noun}" in nouns, noun
    for d in inner:
        o = d.params["open"]
        assert d.variants[0] == f"di{o}" if d.template == "delete_inner" else d.variants[0].startswith(f"ci{o}")
        assert gates.target_problem(d.exercise("bash"), d.target, d.task) is None, d.task
        if d.template == "change_inner":
            assert ")" not in d.params["text"] and f"`{d.params['text']}`" in d.task
    # `${}` and `name[]` are errors in Bash: an expansion or a subscript is changed, never emptied.
    assert not [d for d in inner if d.template == "delete_inner" and d.params["open"] in "{["]
    texts = {d.lines[d.cursor[0] - 1].strip(): d.params["text"] for d in inner if d.template == "change_inner"}
    assert texts['echo "too many items" >&2'] in bash.MESSAGE_TEXTS  # words for words
    assert texts["local -A prices=([apple]=3 [pear]=4)"] in bash.KEYED_TEXTS  # keys for a keyed array
    assert texts['echo "${prices[apple_and_pear]}"'] in (*bash.KEY_TEXTS, *bash.ELEMENT_TEXTS)
    # A printf format is emptied but not replaced with prose.
    formats = [d for d in inner if "'%s: %s'" in d.lines[d.cursor[0] - 1] and d.params["open"] == "'"]
    assert formats and {d.template for d in formats} == {"delete_inner"}


def test_bracket_drills_never_start_inside_a_nested_quoted_string(drafts):
    for d in drafts:
        if d.template in ("change_inner", "delete_inner") and d.params["open"] == "(":
            row, col = d.cursor[0] - 1, d.cursor[1]
            inside = d.lines[row][d.target[0]["start"][1] + 1:col]
            assert inside.count('"') % 2 == 0 and inside.count("'") % 2 == 0, d.task


def test_change_rhs_replaces_to_end_of_line(drafts):
    rhs = {d.lines[d.cursor[0] - 1].strip(): d for d in drafts if d.template == "change_to_end"}
    assert rhs['local label="items: none"'].params["text"].strip('"') in bash.MESSAGE_TEXTS
    assert rhs["result=$(printf '%s items' \"$total\")"].params["text"] == '"$1"'
    assert rhs["width=$((total * 2 + index))"].params["text"] == "0"
    for d in rhs.values():
        row = d.cursor[0] - 1
        assert d.variants[0] == f"C{d.params['text']}<Esc>"
        assert d.expect["lines"][row] == d.lines[row][:d.cursor[1]] + d.params["text"]


def test_indent_block_uses_braces_for_a_function_and_a_count_for_keyword_bodies(drafts):
    blocks = [d for d in drafts if d.template == "indent_block"]
    closers = set()
    for d in blocks:
        n = d.target[0]["end"][0] - d.target[0]["start"][0] + 1
        closer = d.lines[d.target[0]["end"][0]].strip().split()[0]
        closers.add(closer)
        assert d.expect["lines"] == d.window.lines
        assert d.variants[0] in ((">i{", "<i{") if closer == "}" else (f"{n}>>", f"{n}<<")), d.task
    assert closers >= {"}", "done", "fi", "else"}


def test_trailing_comment_counts_hashes_and_keeps_directives():
    win = _window("f() {\n    echo $# args # how many\n    echo ${#1} $# # lengths\n    run \"$1\" # shellcheck disable=SC2086\n"
                  "    log \"$1\" \"$2\"\n    return 0\n}\n" + "\n".join(f"x{i}={i}" for i in range(4)))
    comments = {d.lines[d.cursor[0] - 1].strip(): d for d in bash.generate(win) if d.template == "delete_trailing_comment"}
    assert comments["echo $# args # how many"].variants[0] == "2f#D"
    assert comments["echo ${#1} $# # lengths"].variants[0] == "3f#D"
    assert len(comments) == 2  # the shellcheck directive stays


def test_move_and_copy_keep_return_exit_and_shift_in_place(drafts):
    moves = [d for d in drafts if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        involved = [d.lines[r["start"][0] - 1].split()[0] for r in d.target]
        assert not {"return", "exit", "break", "continue", "shift"} & set(involved), d.task
        assert sorted(d.expect["lines"]) == sorted(d.lines + ([] if d.template == "move_line" else
                                                               [d.lines[d.cursor[0] - 1]]))


def test_delete_lines_leaves_no_empty_block_and_no_broken_pipeline(many):
    text = """\
run() {
    if [[ -n $1 ]]; then
        echo "one"
        echo "two"
        echo "three"
    fi
}
list_items | while read -r item; do
    echo "$item"
    echo "next"
    echo "last"
done
for item in "$@"; do
    echo "$item"
    echo "again"
    echo "done"
done
setup "$@"
finish "$@" """
    tasks = sorted(d.task for d in bash.generate(_window(text)) if d.template == "delete_lines")
    assert tasks == ["Delete the function `run` (7 lines)", "Delete this `for` loop (5 lines)"]


def test_subst_renames_variables_and_functions_but_not_text_or_keys(many):
    text = """\
tally() {
    local count=0 size=$1 label=$2 color=$3
    for (( i = 0; i < size; i++ )); do
        (( count += size ))
        echo "size is $size, count is $count"
    done
    echo "${prices[label]} $label ${label} ${#label}"
    echo "$color" "${color}" "${color:-red}" color
    echo "$count $count"
}
tally "$@"
tally 1 2
tally 3 4"""
    olds = {d.params["old"]: d for d in bash.generate(_window(text)) if d.template == "rename_all_subst"}
    assert set(olds) == {"tally"}  # `count` and `size` are words in a string, `label` a key, `color` an argument
    assert olds["tally"].params["new"] in ("process", "compute", "update")
    assert len(olds["tally"].target) == 4
    clean = text.replace('echo "size is $size, count is $count"', 'echo "$size $count"')
    assert {d.params["old"] for d in bash.generate(_window(clean)) if d.template == "rename_all_subst"} == {"tally", "count", "size"}


def test_register_drafts_leave_no_empty_block_and_swap_only_inside_arithmetic(many):
    text = """\
adjust() {
    local numerator=$1 denominator=$2 verbose=$3 prefix=""
    if (( denominator < 0 )); then
        (( numerator *= -1 ))
    fi
    $verbose && prefix+="$numerator"
    (( numerator + denominator ))
    echo "$numerator/$denominator"
    echo "$prefix adjusted values"
    echo "finished the adjustment"
    return 0
}"""
    win = _window(text)
    made = bash.generate(win)
    swaps = [d.task for d in made if d.template == "swap_words"]
    assert swaps == ["Swap `numerator` and `denominator` on this line"]  # not `$verbose && prefix`
    for d in made:
        if d.template in registers.TEMPLATES:
            for lines in (d.lines, d.expect.get("lines", d.lines)):
                assert "    if (( denominator < 0 )); then\n    fi" not in "\n".join(lines), d.task
    assert bash._hollow(bash.parse("f() {\n}").root_node) and bash._hollow(bash.parse("if x; then\n    # y\nfi").root_node)
    assert not bash._hollow(bash.parse("\n".join(win.lines)).root_node)


# Split drill ======================================================================================


@pytest.mark.parametrize(("line", "why"), [
    ('    echo "$input" | sort', "one break only"),
    ('    echo "a | b" | sort | uniq -c', "a pipe and spaces inside a string"),
    ("    list_items | sort || fail | cat", "a second pipeline"),
    ("    list_items |sort | uniq -c", "a pipe with no space before the next command"),
    ("    list_items | sort | uniq -c # count them", "a trailing comment"),
    ("                list_items | sort | uniq -c", "an indent that is too deep to type"),
])
def test_split_pipeline_leaves_these_lines_alone(line, why):
    assert bash._pipelines(_window(f"f() {{\n{line}\n}}")) == {}, why


@NVIM
def test_split_pipeline_breaks_after_each_pipe(runner):
    line = "    count=$(echo \"$input\" | tr -d '[:space:]' | sort -u | wc -l)"
    win = _window(f"f() {{\n{line}\n    echo \"$count\"\n}}")
    (draft,) = [d for d in bash.generate(win) if d.template == "split_pipeline"]
    keys = ":s/ | / |\\r" + " " * 8 + "/g<CR>"
    assert draft.variants == [keys] and draft.kind == "ex" and draft.skill == "x.subst" and draft.typed == 8
    assert draft.expect["lines"][1:5] == [
        '    count=$(echo "$input" |',
        "        tr -d '[:space:]' |",
        "        sort -u |",
        "        wc -l)",
    ]
    assert "the 4 commands go one per line" in draft.task and "(8 spaces)" in draft.task
    ex = draft.exercise("bash")
    assert oracle.verify(ex, keys, runner).passed  # a literal `|` works as typed in the pattern and the replacement
    assert not oracle.verify(ex, keys.replace("/g", "/"), runner).passed  # the first pipe only
    assert not oracle.verify(ex, keys.replace("\\r", "\\n"), runner).passed  # \n is a null byte here
    verdicts = build._replay([draft], bash.LANG, workers=1, report=build.Report())
    shipped, problem, _ = build.evaluate(draft, bash.LANG, verdicts[id(draft)], "nvim test")
    assert shipped is not None, problem


# Oracle ===========================================================================================


@NVIM
def test_filetype_bash_loads_the_sh_plugins_and_percent_reads_keywords(drafts):
    """`filetype=bash` loads Neovim's sh ftplugin: matchit makes `%` on `if` stop at `else`, so
    the Bash drills only use `%` on brackets."""
    lines = ["f() {", "    if x; then", "        echo ${a[1]}", "    else", "        b", "    fi", "}"]
    on_if = {"id": "pct", "skill": "m.match", "lang": "bash", "kind": "cursor",
             "start": {"lines": lines, "cursor": [2, 4]}, "expect": {"cursor": [6, 4]}, "par": {"keys": "%"}}
    on_brace = dict(on_if, start={"lines": lines, "cursor": [3, 14]}, expect={"cursor": [3, 19]})
    runner = oracle.subprocess_runner()
    (to_end,) = oracle.verify_many([(on_if, "%")], runner)
    assert not to_end.passed and to_end.outcome.cursor == [4, 4]  # the `else`, not the `fi`
    assert oracle.verify_many([(on_brace, "%")], runner)[0].passed
    for d in drafts:
        if d.template == "jump_match":
            (r0, c0), (r1, c1) = d.cursor, d.expect["cursor"]
            assert d.lines[r0 - 1][c0] in "()[]{}" and d.lines[r1 - 1][c1] in "()[]{}"


@NVIM
@pytest.mark.parametrize("name", FIXTURES)
def test_every_draft_has_a_variant_that_passes_in_neovim(many, name):
    drafts = [d for w in bash.windows(FIXTURES[name], SOURCE) for d in bash.generate(w)]
    assert drafts
    assert not _failing(drafts)
