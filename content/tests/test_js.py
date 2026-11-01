"""JavaScript and TypeScript support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil
import tomllib

import pytest

from vimtrainer_content import gates, oracle, snippets, sources, templates
from vimtrainer_content.lang import js

REPO = pathlib.Path(__file__).resolve().parents[2]
JS_SOURCE = {"repo": "fixture/inventory-js", "path": "src/inventory.js", "commit": None, "license": "MIT"}
TS_SOURCE = {"repo": "fixture/inventory-ts", "path": "src/inventory.ts", "commit": None, "license": "MIT"}
# Two-space indent, as in exercism: windows re-indent it to four.
INVENTORY_JS = """\
import { gcd } from './math';

const max_items = 50;

// Count how often each word occurs.
export const countWords = (words) => {
  const counts = { total: 0, seen: [] };
  for (const word of words) {
    counts[word + '_key'] = (counts[word] || 0) + 1; // tally this word
    totalSeen = totalSeen + 1;
  }
  return counts;
};

export function lookup(counts, name) {
  const found = counts.find(name);
  const label = `items: ${found}`;
  if (found === undefined) {
    throw new Error('missing item name');
    logError('lookup', name, 3);
    report.failures.push(name);
    return -1;
  }
  return found.value + offsets[name.length - 1];
}
"""
INVENTORY_TS = """\
export class Inventory<T> {
  private items: Map<string, number>
  private names: string[]
  private ready: boolean

  constructor(names: string[]) {
    this.items = new Map<string, number>()
    this.names = names
    this.ready = names.length > 0
  }

  public count(name: string, fallback: number): number {
    const total = this.items.get(name) ?? fallback
    if (total > 0) {
      log('found item', name, total) // seen before
      return total
    }
    return lookup<number>(name, 'default', 0)
  }
}
"""


@pytest.fixture(scope="module")
def js_window():
    (win,) = js.windows_js(INVENTORY_JS, JS_SOURCE)
    return win


@pytest.fixture(scope="module")
def ts_window():
    (win,) = js.windows_ts(INVENTORY_TS, TS_SOURCE)
    return win


@pytest.fixture(scope="module")
def js_drafts(js_window):
    return js.generate(js_window, js.LANG_JS)


@pytest.fixture(scope="module")
def ts_drafts(ts_window):
    return js.generate(ts_window, js.LANG_TS)


def _window(text: str, source=JS_SOURCE, grammar: str = "javascript") -> snippets.Window:
    lines = text.splitlines()
    return snippets.Window(lines=lines, source=source, first_line=1, last_line=len(lines),
                           tree=js.parse("\n".join(lines), grammar))


def _long_class(methods: int) -> str:
    body = "\n\n".join(f"  method{i}(x) {{\n    return x + {i};\n  }}" for i in range(methods))
    return f"export class Big {{\n{body}\n}}\n"


def _passes(draft, lang) -> bool:
    ex = dict(draft.exercise(lang.name), id=draft.uid)
    return any(v.passed for v in oracle.verify_many([(ex, k) for k in draft.variants], oracle.subprocess_runner()))


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with js.registered():
        for uses in js.LANG_JS.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in js.LANG_JS.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    for lang in (js.LANG_JS, js.LANG_TS):
        assert lang.comment_leader == "//" and lang.nodes is js.LANG_JS.nodes
        assert {"(", "=", ".", ";", "=>"} <= set(lang.find_targets)
    assert (js.LANG_JS.name, js.LANG_JS.short, js.LANG_TS.name, js.LANG_TS.short) == ("javascript", "js", "typescript", "ts")


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    for lang, skills in (("javascript", js.JS_TARGET_SKILLS), ("typescript", js.TS_TARGET_SKILLS)):
        for skill in skills:
            assert skill in graph["skills"], skill
            assert graph["skills"][skill]["langWeights"][lang] == js.WEIGHTS[skill], (lang, skill)
    assert set(js.TS_TARGET_SKILLS) - set(js.JS_TARGET_SKILLS) == {"t.angle"}


def test_sources_toml_pins_exercism_javascript_and_typescript():
    raw = tomllib.loads((sources.SOURCES_TOML).read_text())
    for lang, ext in (("javascript", "js"), ("typescript", "ts")):
        (src,) = [s for s in sources.load_sources() if s.lang == lang]
        assert src.repo == f"github.com/exercism/{lang}" and src.license == "MIT" and src.name == f"exercism-{lang}"
        assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
        assert set(src.include) == {f"exercises/practice/*/.meta/proof.ci.{ext}", f"exercises/concept/*/.meta/exemplar.{ext}"}
        assert sum(s["lang"] == lang for s in raw["source"]) == 1


# Windows ==========================================================================================


def test_window_is_whole_parseable_file_reindented_to_four_spaces(js_window, ts_window):
    assert js_window.lines[0] == "import { gcd } from './math';" and js_window.lines[-1] == "}"
    assert "        counts[word + '_key'] = (counts[word] || 0) + 1; // tally this word" in js_window.lines
    for win in (js_window, ts_window):
        assert not win.root.has_error
        assert snippets.size_problem(win.lines) is None
        assert all((len(ln) - len(ln.lstrip())) % 4 == 0 for ln in win.lines)


def test_reindent_leaves_template_strings_and_doubles_comment_levels():
    lines = ["function f() {", "  const s = `a", "  b`;", "  /**", "   * doc", "   */", "  return s;", "}"]
    assert js.reindent(lines) == [
        "function f() {", "    const s = `a", "  b`;", "    /**", "     * doc", "     */", "    return s;", "}"]
    four = ["function f() {", "    return 1;", "}"]
    assert js.reindent(four) == four


def test_long_class_is_split_into_windows_of_members_inside_the_class():
    text = _long_class(80)  # > 256 lines: py-tree-sitter 0.26.0 crashes on Point.row there
    assert len(text.splitlines()) > 300
    wins = js.windows_js(text, JS_SOURCE)
    assert len(wins) > 5
    starts = set()
    for win in wins:
        assert not win.root.has_error
        assert snippets.size_problem(win.lines) is None
        assert win.lines[0] == "export class Big {" and win.lines[-1] == "}"
        assert win.lines[1].startswith("    method")
        starts.add(win.first_line)
    assert len(starts) == len(wins)  # first_line is the members', so window keys stay unique


def test_long_function_is_split_into_statement_windows():
    body = "\n".join(f"  const v{i} = compute({i}, items);" for i in range(60))
    wins = js.windows_ts(f"export function big(items: number[]): void {{\n{body}\n}}\n", TS_SOURCE)
    assert wins and all(not w.root.has_error and w.lines[0].startswith("const v") for w in wins)


def test_node_frequency_counts_js_and_ts_nodes():
    freq = js.node_frequency_ts([INVENTORY_TS])
    assert freq["counts"]["type_arguments"] >= 2 and freq["lines"] == len(INVENTORY_TS.splitlines())
    assert "type_arguments" not in js.node_frequency_js([INVENTORY_JS])["counts"]


def test_quality_gate_reads_js_windows(js_window):
    assert snippets.quality_problem(js_window.lines, js_window.root) is None
    stub = _window("export const twoFer = () => {\n  throw new Error('Remove this statement and implement this function');\n};\n"
                   "// TODO: implement\nexport const a = 1;\nexport const b = 2;\nexport const c = 3;\nexport const d = 4;")
    assert snippets.quality_problem(stub.lines, stub.root) == "scaffold"


# Templates ========================================================================================


def test_drafts_cover_the_js_and_ts_skills(js_drafts, ts_drafts):
    assert {"t.quote", "t.paren", "t.brace", "t.bracket", "t.word", "m.find", "m.match", "m.rel", "n.unmatched",
            "o.delete", "o.change", "o.indent", "o.case", "x.subst", "x.copymove"} <= {d.skill for d in js_drafts}
    assert {"t.angle", "t.quote", "t.paren", "o.change", "x.copymove"} <= {d.skill for d in ts_drafts}
    assert "t.angle" not in {d.skill for d in js_drafts}


def test_prime_feeds_the_shared_helpers(js_window, js_drafts):
    comment_row = js_window.lines.index("// Count how often each word occurs.")
    assert comment_row in templates._prose_rows(js_window)
    row = next(r for r, ln in enumerate(js_window.lines) if "missing item name" in ln)
    assert (row, js_window.lines[row].index("missing")) in templates._string_cells(js_window)
    assert templates._delim_count(js_window, "'") >= 2 and templates._delim_count(js_window, "{") >= 2


BACKTICKS = """\
export function describe(name, count) {
    const title = `report for ${name}`;
    const summary = `total items: ${count}`;
    if (count === 0) {
        return 'nothing to report';
    }
    log(title, summary, 'done');
    return title + summary;
}
"""


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_quotes_use_their_own_text_object(js_drafts, monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    quotes = [d for d in [*js_drafts, *js.generate(_window(BACKTICKS))] if d.skill == "t.quote"]
    assert {d.params["open"] for d in quotes} == {"'", "`"}  # the fixtures have no double-quoted strings
    for d in quotes:
        o = d.params["open"]
        assert d.variants[0] == f"di{o}" if d.template == "delete_inner" else d.variants[0].startswith(f"ci{o}")
    ticks = [d for d in quotes if d.params["open"] == "`"]
    assert {d.template for d in ticks} == {"change_inner", "delete_inner"}
    assert all("inside the backticks" in d.task for d in ticks), [d.task for d in ticks]
    assert all(_passes(d, js.LANG_JS) for d in ticks)


TWIN_TEMPLATES = """\
export function show(name) {
    const a = `item: ${name}`;
    const b = `item: ${name}`;
    log(a, b);
    return a + b;
}
"""


def test_repeated_template_literals_are_singled_out_by_the_cursor(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    drafts = [d for d in js.generate(_window(TWIN_TEMPLATES))
              if d.template in ("change_inner", "delete_inner") and d.params.get("open") == "`"]
    assert drafts
    for d in drafts:
        assert "under the cursor" in d.task, d.task
    cursors = {}
    for d in js.generate(_window(TWIN_TEMPLATES)):
        if d.template in ("change_inner", "delete_inner"):
            cursors.setdefault(d.task, set()).add(tuple(d.cursor))
    ambiguous = [t for t, cs in cursors.items() if len(cs) > 1 and "under the cursor" not in t]
    assert not ambiguous


def test_angle_drafts_use_the_angle_text_object(ts_drafts):
    angles = [d for d in ts_drafts if d.skill == "t.angle"]
    assert angles
    for d in angles:
        assert d.variants[0] == "di<" or d.variants[0].startswith("ci<")
        assert d.lines[d.cursor[0] - 1].rfind("<", 0, d.cursor[1]) >= 0


def test_indent_block_prefers_the_brace_object(js_drafts, ts_drafts):
    blocks = [d for d in [*js_drafts, *ts_drafts] if d.template == "indent_block"]
    assert blocks
    for d in blocks:
        assert d.variants[0] in (">i{", "<i{")
        assert d.expect["lines"] == d.window.lines and d.lines != d.window.lines


def test_trailing_comment_skips_bare_closing_brace(js_drafts, ts_drafts):
    comments = [d for d in [*js_drafts, *ts_drafts] if d.template == "delete_trailing_comment"]
    assert sorted(d.lines[d.cursor[0] - 1].strip() for d in comments) == [
        "counts[word + '_key'] = (counts[word] || 0) + 1; // tally this word",
        "log('found item', name, total) // seen before",
    ]
    assert {d.variants[0] for d in comments} == {"f/D"}


def test_change_rhs_keeps_whatever_ends_the_line(js_drafts, ts_drafts):
    drafts = [d for d in [*js_drafts, *ts_drafts] if d.template == "change_to_end"]
    assert drafts
    for d in drafts:
        row = d.cursor[0] - 1
        assert d.expect["lines"][row].endswith(";") is d.lines[row].endswith(";"), d.task
        assert d.variants[0] == f"C{d.params['text']}{';' if d.lines[row].endswith(';') else ''}<Esc>"
        assert d.params["text"] not in ("value", "X")


def test_find_char_counts_the_first_char_of_multi_char_targets(js_drafts):
    finds = [d for d in js_drafts if d.skill == "m.find"]
    assert finds
    for d in finds:
        row, start, col = d.cursor[0] - 1, d.cursor[1], d.expect["cursor"][1]
        line = d.lines[row]
        motion = d.variants[0]
        n, ch = (int(motion[0]), motion[2]) if motion[0].isdigit() else (1, motion[1])
        assert line.count(ch, start + 1, col + 1) == n and line[col] == ch


def test_move_and_copy_only_touch_whole_one_line_items(js_drafts, ts_drafts):
    moves = [d for d in [*js_drafts, *ts_drafts] if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        assert d.kind == "edit" and any(not k.startswith(":") for k in d.variants), d.variants
        assert sorted(d.expect["lines"]) == sorted(d.lines + ([] if d.template == "move_line" else
                                                               [d.lines[d.cursor[0] - 1]]))


def test_delete_inner_names_the_delimiters(js_drafts, ts_drafts):
    tasks = [d.task for d in [*js_drafts, *ts_drafts] if d.template == "delete_inner"]
    assert any("keeping the quotes" in t for t in tasks) and any("keeping the parentheses" in t for t in tasks)
    for t in tasks:
        assert not re.search(r"keeping the [()\[\]{}<>'\"]", t), t


def test_role_reads_js_functions_members_and_ts_types(js_window, ts_window):
    found = {}
    for win in (js_window, ts_window):
        js.generate(win, js.LANG_JS if win is js_window else js.LANG_TS)  # primes the cache
        stack = [win.root]
        while stack:
            n = stack.pop()
            stack.extend(n.children)
            if n.type in ("identifier", "property_identifier"):
                found[templates._text(n)] = (templates._role(n, templates._text(n), win), templates._is_member(n))
    assert found["lookup"] == ("call", False)  # function_declaration
    assert found["countWords"] == ("call", False)  # const f = (...) => ...
    assert found["logError"] == ("call", False)  # call_expression
    assert found["push"] == ("call", True)  # method call through member_expression
    assert found["failures"][1] and not found["report"][1]
    assert ts_window.cache["types"]["names"] == "many" and ts_window.cache["types"]["ready"] == "flag"
    assert ts_window.cache["types"]["fallback"] == "count"


def test_renames_skip_members_strings_and_keywords(js_drafts, ts_drafts):
    renames = [d for d in [*js_drafts, *ts_drafts] if d.template in ("rename_here", "upper_word")]
    assert renames
    for d in renames:
        row, col = d.target[0]["start"][0] - 1, d.target[0]["start"][1]
        assert d.lines[row][col - 1:col] != ".", d.task  # never `this.x` / `a.b`
        word = d.params.get("word") or d.lines[row][col:d.target[0]["end"][1] + 1]
        assert word not in js.LANG_JS.keywords
    named = [d for d in js.generate(_window(GREET)) if d.template in ("rename_here", "rename_all_subst")]
    assert named
    banner = GREET.splitlines()[1]
    for d in named:
        assert all(not (r["start"][0] == 2 and r["start"][1] > banner.index("'")) for r in d.target), d.task
    assert not any(d.template == "rename_all_subst" and d.params["old"] == "person" for d in named)


GREET = """\
export function greet(person) {
    const banner = 'hello person';
    log(banner, person);
    return person;
}
"""

TALLY = """\
export class Counter {
    constructor() {
        this.tally = 0;
    }

    add(n) {
        this.tally = this.tally + n;
        log('added', n);
        return this.tally;
    }

    reset() {
        this.tally = 0;
    }
}
"""


def test_rename_all_subst_counts_and_renames_every_member_hit(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 50)
    (d,) = [d for d in js.generate(_window(TALLY)) if d.template == "rename_all_subst"]
    assert d.params["old"] == "tally" and "(5 occurrences)" in d.task
    lines = TALLY.splitlines()
    hits = [(r + 1, c) for r, ln in enumerate(lines) for c in range(len(ln)) if ln.startswith("tally", c)]
    assert [tuple(r["start"]) for r in d.target] == hits
    assert d.expect["lines"] == [ln.replace("this.tally", f"this.{d.params['new']}") for ln in lines]


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_case_drills_only_target_top_level_constants(js_drafts):
    cases = [d for d in js_drafts if d.template == "upper_word"]
    assert [d.params["word"] for d in cases] == ["max_items"]  # top-level const literal, used once
    assert cases[0].task == "Make `max_items` a constant name: uppercase it to `MAX_ITEMS`"
    assert _passes(cases[0], js.LANG_JS)


def test_nested_pair_check_strips_slash_comments():
    assert not gates.nested_in_same_pair(["// note (", "f(x);"], 1, 1, "javascript")
    assert gates.nested_in_same_pair(["g(", "f(x);"], 1, 1, "typescript")


CONSTANTS = """\
const area_code_length = 3;
const exchange_length = 3;
const extension_length = 4;

export class Song {
    title;
    artist;
    album;
}

export function digits(n) {
    let count = 0;
    count += n / 10;
    count += n % 10;
    totalSeen = totalSeen + count;
    return count;
}

export class Frame {
    reset() {
        this.roll = 1;
        this.pins = maxPins;
        this.frame = this.frame + 1;
    }
}
"""


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
def test_x_normal_prefix_and_upper_constants_need_normal_over_a_range(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    win = _window(CONSTANTS)
    drafts = [d for d in js.generate(win) if d.skill == "x.normal"]
    prefixes = {d.params["text"] for d in drafts if d.template == "prefix_each_line"}
    assert prefixes == {"const ", "// ", "this."}  # never the class fields: they share no prefix
    assert [d.tags[0] for d in drafts if d.template == "upper_constants"] == ["program"]
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        changed = [r for r, (a, b) in enumerate(zip(d.lines, d.expect["lines"])) if a != b]
        assert d.kind == "ex" and len(changed) == d.params["n"] >= templates.EX_MIN_LINES, d.task
        assert ":norm " in d.variants[0]
        ex = d.exercise(js.LANG_JS.name)
        ex["id"] = d.uid
        for keys in d.variants + d.alternates:
            jobs.append((ex, keys))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    failing = [(drafts[owners[k]].task, v.keys, v.reason) for k, v in enumerate(verdicts) if not v.passed]
    assert not failing


def test_comment_out_drills_only_take_statements_in_function_bodies(monkeypatch):
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", 8)
    drafts = [d for d in js.generate(_window(CONSTANTS)) if d.template == "prefix_each_line" and d.params["text"] == "// "]
    rows = {r["start"][0] for d in drafts for r in d.target}
    assert drafts and rows <= {12, 13, 14, 15}, rows  # digits' body, never the constants or class fields


# Oracle ===========================================================================================


@pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
@pytest.mark.parametrize("which", ["js", "ts"])
def test_every_draft_has_a_variant_that_passes_in_neovim(which, js_drafts, ts_drafts):
    drafts, lang = (js_drafts, js.LANG_JS) if which == "js" else (ts_drafts, js.LANG_TS)
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = d.exercise(lang.name)
        ex["id"] = d.uid
        for keys in d.variants:
            jobs.append((ex, keys))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    passed = {owners[k] for k, v in enumerate(verdicts) if v.passed}
    failing = [(d.template, d.skill, d.task, d.variants) for i, d in enumerate(drafts) if i not in passed]
    assert not failing
