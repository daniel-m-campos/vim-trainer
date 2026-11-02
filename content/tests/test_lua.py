"""Lua support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil

import pytest

from vimtrainer_content import gates, oracle, snippets, sources, templates
from vimtrainer_content.lang import lua

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = {"repo": "fixture/inventory-lua", "path": "inventory.lua", "commit": None, "license": "MIT"}
NVIM = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
# Two-space indent, as in exercism: windows re-indent it to four.
INVENTORY = """\
local util = require('util')

local max_items = 50

-- Count how often each word occurs.
local function count_words(words)
  local counts = { total = 0, seen = {} }
  for _, word in ipairs(words) do
    counts[word .. '_key'] = (counts[word] or 0) + 1 -- tally this word
    total_seen = total_seen + 1
  end
  return counts
end

function M.lookup(counts, name)
  local found = counts:find(name)
  local label = "items: " .. found
  if found == nil then
    error('missing item name')
    log_error('lookup', tostring(name), 3)
    report.failures = report.failures + 1
    return -1
  end
  return found.value + offsets[name:len() - 1]
end
"""
# A long string holds brackets, quotes and indentation that are not code.
BANNER = """\
local banner = [[
  usage: (run) [options]
    {more} 'quoted'
]]

local function show(items, s)
  local out = {}
  local open = s:find('(', 1, true)
  for i = 1, open do
    out[i] = string.format('%d: %s', i, items[i + 1])
  end
  print(banner, table.concat(out, ', '))
  return out
end
"""
CONSTANTS = """\
local area_code_length = 3
local exchange_length = 3
local extension_length = 4

local function digits(n)
    local count = 0
    count = count + n // 10
    count = count + n % 10
    total_seen = total_seen + count
    return count
end

function Frame:reset()
    self.roll = 1
    self.pins = max_pins
    self.frame = self.frame + 1
end
"""

SCORES = """\
local function grades(names)
  local scores = {
    alice = 90,
    bob = { 85, 80 },
    carol = 70,
    dave = 60,
  }
  return { scores = scores, count = #names }
end
"""
FIXTURES = {"inventory": INVENTORY, "banner": BANNER, "constants": CONSTANTS, "scores": SCORES}


@pytest.fixture(scope="module")
def window():
    (win,) = lua.windows(INVENTORY, SOURCE)
    return win


@pytest.fixture(scope="module")
def drafts(window):
    """Every draft the fixture window makes, not just MAX_PER_WINDOW per template."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(templates, "MAX_PER_WINDOW", 50)
        return lua.generate(window)


@pytest.fixture
def many(monkeypatch):
    """Every draft a template makes, not just MAX_PER_WINDOW of them."""
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)


def _window(text: str, indent: int = 0) -> snippets.Window:
    lines = text.splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                           tree=lua.parse("\n".join(lines)), indent=indent)


def _failing(drafts, keys=lambda d: d.variants) -> list:
    """Drafts none of whose ``keys`` pass in Neovim, as (template, task, keys)."""
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = dict(d.exercise(lua.LANG.name), id=d.uid)
        for k in keys(d):
            jobs.append((ex, k))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    passed = {owners[k] for k, v in enumerate(verdicts) if v.passed}
    return [(d.template, d.task, keys(d)) for i, d in enumerate(drafts) if i not in passed]


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with lua.registered():
        for uses in lua.LANG.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in lua.LANG.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    assert (lua.LANG.name, lua.LANG.short, lua.LANG.grammar, lua.LANG.comment_leader) == ("lua", "lua", "lua", "--")
    assert {"(", "=", ".", ":", ","} <= set(lua.LANG.find_targets) and "#" not in lua.LANG.find_targets


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    assert set(lua.WEIGHTS) == set(lua.TARGET_SKILLS)
    for skill in lua.TARGET_SKILLS:
        assert graph["skills"][skill]["langWeights"]["lua"] == lua.WEIGHTS[skill], skill
    mapped = {use.skill for uses in lua.LANG.nodes.values() for use in uses} | {u.skill for u in lua.LANG.line_templates}
    assert mapped == set(lua.TARGET_SKILLS)


def test_sources_toml_pins_exercism_lua():
    (src,) = [s for s in sources.load_sources() if s.lang == "lua"]
    assert src.repo == "github.com/exercism/lua" and src.license == "MIT" and src.name == "exercism-lua"
    assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
    assert "exercises/practice/*/.meta/example.lua" in src.include


# Windows ==========================================================================================


def test_window_is_whole_parseable_file_reindented_to_four_spaces(window):
    assert window.lines[0] == "local util = require('util')" and window.lines[-1] == "end"
    assert "        counts[word .. '_key'] = (counts[word] or 0) + 1 -- tally this word" in window.lines
    assert not window.root.has_error and window.root.type == "chunk"
    assert snippets.size_problem(window.lines) is None
    assert all(lua._indent(ln) % 4 == 0 for ln in window.lines)


def test_reindent_doubles_levels_and_leaves_long_strings_alone():
    lines = ["local s = [[", "  a (", " b]]", "if x then", "  y(1,", "     2)", "end"]
    assert lua.reindent(lines) == ["local s = [[", "  a (", " b]]", "if x then", "    y(1,", "         2)", "end"]
    four = ["if x then", "    y()", "end"]
    assert lua.reindent(four) == four
    (win,) = lua.windows(BANNER, SOURCE)
    assert win.lines[1:3] == ["  usage: (run) [options]", "    {more} 'quoted'"]
    assert "        out[i] = string.format('%d: %s', i, items[i + 1])" in win.lines


def test_long_function_is_split_into_statement_windows():
    body = "\n".join(f"  local v{i} = compute({i}, items)" for i in range(60))
    wins = lua.windows(f"local function big(items)\n{body}\n  return v1\nend\n", SOURCE)
    assert len(wins) >= 3
    assert all(not w.root.has_error and w.lines[0].startswith("local v") for w in wins)
    assert wins[-1].lines[-1] == "return v1"


def test_long_table_is_split_into_windows_of_fields_inside_the_table():
    fields = "\n".join(f"  name{i} = function(x)\n    return x + {i}\n  end," for i in range(40))
    wins = lua.windows(f"local handlers = {{\n{fields}\n}}\n\nreturn handlers\n", SOURCE)
    assert len(wins) > 3
    for win in wins:
        assert not win.root.has_error and snippets.size_problem(win.lines) is None
        assert win.lines[0] == "local handlers = {" and win.lines[-1] == "}"
        assert win.lines[1].startswith("    name")
    assert len({w.first_line for w in wins}) == len(wins)  # first_line is the fields', so window keys stay unique


def test_comment_lines_and_licence_headers_stay_out_of_window_edges():
    text = ("-- Copyright (c) someone, MIT licence\n" + "\n".join(f"local a{i} = f({i})" for i in range(10))
            + "\n-- trailing note\n-- about nothing\n")
    (win,) = lua.windows(text, SOURCE)
    assert win.lines[0] == "local a0 = f(0)" and win.lines[-1] == "local a9 = f(9)"


def test_node_frequency_and_quality_gate_read_lua(window):
    freq = lua.node_frequency([INVENTORY])
    assert freq["counts"]["function_declaration"] == 2 and freq["lines"] == len(INVENTORY.splitlines())
    assert snippets.quality_problem(window.lines, window.root) is None


# Templates ========================================================================================


def test_drafts_cover_every_target_skill(drafts):
    constants = lua.generate(_window(CONSTANTS))
    assert {d.skill for d in [*drafts, *constants]} == set(lua.TARGET_SKILLS)


def test_prime_masks_long_strings_and_comments():
    win = _window("\n".join(lua.reindent(BANNER.splitlines())))
    drafts = lua.generate(win)
    assert {0, 1, 2, 3} <= templates._prose_rows(win)
    assert (1, win.lines[1].index("(")) in templates._string_cells(win)
    assert templates._delim_count(win, "[") == 2  # out[i] and items[i + 1]; the [[ ]] is no bracket
    strings = templates._string_cells(win)
    for d in drafts:
        in_string = d.skill == "t.quote" or d.template == "upper_inner"  # the cursor goes inside the quotes
        assert in_string or (d.cursor[0] - 1, d.cursor[1]) not in strings, (d.template, d.task)
        assert all(not 2 <= r["start"][0] <= 4 for r in d.target), (d.template, d.task)
    # `s:find('(', 1, true)`: `%` and `ci(` would pair with the bracket inside the string.
    pairs = [d for d in drafts if d.template == "jump_match" or d.skill == "t.paren"]
    assert {d.template for d in pairs} == {"jump_match", "change_inner", "delete_inner"}
    assert not any(d.lines[d.cursor[0] - 1].lstrip().startswith("local open") for d in pairs)


def test_find_char_skips_comment_lines_and_counts_literal_characters(drafts):
    finds = [d for d in drafts if d.skill == "m.find"]
    assert finds
    for d in finds:
        row, start, col = d.cursor[0] - 1, d.cursor[1], d.expect["cursor"][1]
        line, motion = d.lines[row], d.variants[0]
        assert not line.lstrip().startswith("--")
        n, ch = (int(motion[0]), motion[2]) if motion[0].isdigit() else (1, motion[1])
        assert line.count(ch, start + 1, col + 1) == n and line[col] == ch


def test_member_finds_use_dot_and_colon(drafts):
    members = {d.task for d in drafts if d.tags == ["find", "member"]}
    assert {"Move to the `:` before `find`", "Move to the `.` before `value`"} <= members


def test_indent_block_shifts_block_bodies_by_a_count(drafts):
    blocks = [d for d in drafts if d.template == "indent_block"]
    assert blocks
    for d in blocks:
        n = d.target[0]["end"][0] - d.target[0]["start"][0] + 1
        assert d.variants[0] in (f"{n}>>", f"{n}<<") and d.expect["lines"] == d.window.lines
        closer = d.lines[d.target[0]["end"][0]].strip()
        assert closer.split()[0] in ("end", "else", "elseif", "until")


def test_trailing_comment_counts_minus_signs():
    win = _window("local function diff(a, b)\n    local d = a - b -- difference\n    local e = d * 2 -- doubled\n"
                  "    log(d, e)\n    return d - e\nend\n" + "\n".join(f"local x{i} = {i}" for i in range(4)))
    comments = {d.lines[d.cursor[0] - 1].strip(): d for d in lua.generate(win) if d.template == "delete_trailing_comment"}
    assert comments["local d = a - b -- difference"].variants[0] == "2f-D"
    assert comments["local e = d * 2 -- doubled"].variants[0] == "f-D"


def test_move_and_copy_never_move_return_lines(drafts):
    moves = [d for d in drafts if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        assert not d.lines[d.cursor[0] - 1].lstrip().startswith(("return", "break"))
        assert all(not d.lines[r["start"][0] - 1].lstrip().startswith("return") for r in d.target)
        assert sorted(d.expect["lines"]) == sorted(d.lines + ([] if d.template == "move_line" else
                                                               [d.lines[d.cursor[0] - 1]]))


def test_renames_skip_fields_methods_keys_and_called_names(drafts):
    renames = [d for d in drafts if d.template in ("rename_here", "upper_word")]
    assert renames
    for d in renames:
        row, c0, c1 = d.target[0]["start"][0] - 1, d.target[0]["start"][1], d.target[0]["end"][1] + 1
        word = d.lines[row][c0:c1]
        assert d.lines[row][c0 - 1:c0] not in (".", ":"), d.task
        called = d.lines[row][c1:].startswith("(") and not d.lines[row][:c0].endswith("function ")
        assert not called and word not in lua.LANG.keywords, d.task
        assert not re.match(r"\s*=[^=]", d.lines[row][c1:]) or d.lines[row][:c0].strip() in ("", "local"), d.task


def test_subst_skips_names_also_used_as_members(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = """\
function Set:difference(other)
  return self.items
end

local function grade_all(db, difference, grade, items)
  local count = 0
  for i = 1, grade do
    count = count + difference + i
    self.db[grade] = db[grade] + count
    db = difference - count
  end
  local out = { items = count, grade = db }
  return count + difference + items
end"""
    olds = {d.params["old"] for d in lua.generate(_window(text)) if d.template == "rename_all_subst"}
    assert "count" in olds  # a plain local
    assert not olds & {"difference", "db", "grade", "items"}, olds  # a method, a field, table keys


def test_case_drills_only_target_top_level_constants(drafts):
    cases = [d for d in drafts if d.template == "upper_word"]
    assert [d.params["word"] for d in cases] == ["max_items"]
    assert cases[0].task == "Make `max_items` a constant name: uppercase it to `MAX_ITEMS`"
    assert not [d for d in lua.generate(_window(CONSTANTS, indent=4)) if d.template == "upper_constants"]


def test_every_lua_template_makes_drafts_on_the_fixtures():
    made = dict.fromkeys([*lua.LUA_NODE_TEMPLATES, *lua.LUA_LINE_TEMPLATES], 0)
    for text in FIXTURES.values():
        for win in lua.windows(text, SOURCE):
            win.cache.clear()
            stack = [win.root]
            while stack:
                node = stack.pop()
                stack.extend(node.children)
                for use in lua.LANG.nodes.get(node.type, ()):
                    for name in use.templates:
                        made[name] += len(list(lua.LUA_NODE_TEMPLATES[name](win, node, use.skill, lua.LANG)))
            for use in lua.LANG.line_templates:
                for name in use.templates:
                    made[name] += len(list(lua.LUA_LINE_TEMPLATES[name](win, use.skill, lua.LANG)))
    assert not [name for name, n in made.items() if n == 0]


def test_multi_line_table_is_emptied_with_the_brace_object(many):
    (win,) = lua.windows(SCORES, SOURCE)
    (d,) = [d for d in lua.generate(win) if "lines" in d.tags and d.skill == "t.brace"]
    assert d.variants[:2] == ["di{", "diB"] and d.expect["lines"][1:3] == ["    local scores = {", "    }"]
    assert d.task == "Delete the 4 lines inside the braces of `local scores = {`, keeping the `{` and `}` lines"


# Wording ==========================================================================================


def test_inner_object_tasks_name_their_delimiters_and_real_replacements(many, drafts):
    inner = [d for d in [*drafts, *lua.generate(_window(BANNER))] if d.template in ("change_inner", "delete_inner")]
    assert {d.params["open"] for d in inner} >= {"(", "[", "{", "'"}
    for d in inner:
        o = d.params["open"]
        assert d.variants[0] == f"di{o}" if d.template == "delete_inner" else d.variants[0].startswith(f"ci{o}")
        assert not re.search(r"keeping the [()\[\]{}<>'\"]", d.task), d.task
        if d.template == "change_inner":
            assert d.params["text"] not in ("value", "X", "") and f"`{d.params['text']}`" in d.task
        assert gates.target_problem(d.exercise("lua"), d.target, d.task) is None, d.task


def test_noun_for_each_lua_pair(drafts):
    tasks = " ".join(d.task for d in drafts if d.template in ("change_inner", "delete_inner"))
    for noun in ("argument list", "parameter list", "parenthesised expression", "index", "table"):
        assert f"of this {noun}" in tasks, noun
    blocks = [d.task for d in drafts if d.template == "jump_block_end"]
    assert all(re.search(r"the (argument list|parameter list|parenthesised expression|table) around the cursor$", t)
               for t in blocks), blocks


def test_change_rhs_replaces_to_end_of_line(drafts):
    rhs = [d for d in drafts if d.template == "change_to_end"]
    assert rhs
    for d in rhs:
        row = d.cursor[0] - 1
        assert d.variants[0] == f"C{d.params['text']}<Esc>"
        assert d.expect["lines"][row] == d.lines[row][:d.cursor[1]] + d.params["text"]


def test_change_rhs_says_on_this_line_for_a_repeated_target(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    text = """\
local function copy(src, deep)
  local clone = {}
  for k, v in pairs(src) do
    if deep then
      clone[k] = copy_table(v, deep)
    else
      clone[k] = shallow_value(v)
    end
  end
  return clone
end"""
    tasks = [d.task for d in lua.generate(_window(text)) if d.template == "change_to_end" and "clone[k]" in d.task]
    assert tasks and all("`clone[k]` on this line with" in t for t in tasks), tasks


def test_length_operator_is_not_a_comment_to_the_gate(many):
    """gates.py cuts a Lua line at `--`, not at `#` (the length operator), so after
    `items[#items]` it sees no open `[` and the next index is drilled without "inner"."""
    text = ("local function shift(items, offsets)\n    local last = items[#items]\n    local first = offsets[start_index + step]\n"
            "    log(last, first)\n    record(last, offsets)\n    return first + last\nend\n"
            + "\n".join(f"local v{i} = {i}" for i in range(3)))
    win = _window(text)
    assert not gates.nested_in_same_pair(win.lines, 2, win.lines[2].index("["), "lua")
    assert gates.nested_in_same_pair(["x = {a, -- {", "  {b}}"], 1, 2, "lua")
    rows = {d.target[0]["start"][0] for d in lua.generate(win) if d.skill == "t.bracket"}
    assert 3 in rows


# Oracle ===========================================================================================


@NVIM
def test_percent_pairs_brackets_but_matchit_reads_lua_keywords(drafts):
    """Neovim loads matchit and the Lua ftplugin sets b:match_words, so `%` on `if` stops at a
    `return` / `else` in the body before it reaches `end`: the Lua drills only use `%` on brackets."""
    lines = ["local function f(x)", "    if x > 0 then", "        return g(x)", "    end", "end"]
    on_if = {"id": "pct", "skill": "m.match", "lang": "lua", "kind": "cursor",
             "start": {"lines": lines, "cursor": [2, 4]}, "expect": {"cursor": [4, 4]}, "par": {"keys": "%"}}
    on_paren = dict(on_if, start={"lines": lines, "cursor": [3, 16]}, expect={"cursor": [3, 18]})
    runner = oracle.subprocess_runner()
    (to_end,) = oracle.verify_many([(on_if, "%")], runner)
    assert not to_end.passed and to_end.outcome.cursor == [3, 8]  # the `return`, not the `end`
    assert oracle.verify_many([(on_paren, "%")], runner)[0].passed
    for d in drafts:
        if d.template == "jump_match":
            (r0, c0), (r1, c1) = d.cursor, d.expect["cursor"]
            assert d.lines[r0 - 1][c0] in "()[]{}" and d.lines[r1 - 1][c1] in "()[]{}"


@NVIM
def test_x_normal_drills_need_normal_over_a_range(many):
    drafts = [d for d in lua.generate(_window(CONSTANTS)) if d.skill == "x.normal"]
    assert {d.params.get("text") for d in drafts if d.template == "prefix_each_line"} == {"local ", "-- ", "self."}
    assert [d.tags[0] for d in drafts if d.template == "upper_constants"] == ["chunk"]
    for d in drafts:
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert d.kind == "ex" and len(changed) == d.params["n"] >= templates.EX_MIN_LINES, d.task
    assert not _failing(drafts, keys=lambda d: [*d.variants, *d.alternates])


@NVIM
@pytest.mark.parametrize("name", FIXTURES)
def test_every_draft_has_a_variant_that_passes_in_neovim(many, name):
    drafts = [d for w in lua.windows(FIXTURES[name], SOURCE) for d in lua.generate(w)]
    assert drafts
    assert not _failing(drafts)
