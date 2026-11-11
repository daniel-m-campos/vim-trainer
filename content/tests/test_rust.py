"""Rust support: windowing, node -> skill mapping, templates and the Neovim oracle."""

import json
import pathlib
import re
import shutil
import tomllib

import pytest

from vimtrainer_content import gates, oracle, registers, snippets, sources, templates
from vimtrainer_content.lang import rust

REPO = pathlib.Path(__file__).resolve().parents[2]
SOURCE = {"repo": "fixture/inventory-rs", "path": "src/lib.rs", "commit": None, "license": "MIT"}
NVIM = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")

INVENTORY = """\
use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone)]
pub struct Inventory<'a> {
    pub names: Vec<&'a str>,
    pub counts: HashMap<String, usize>,
    pub ready: bool,
}

impl<'a> Inventory<'a> {
    pub fn new(names: Vec<&str>) -> Self {
        let counts = HashMap::with_capacity(names.len());
        let ready = !names.is_empty();
        Inventory { names, counts, ready }
    }

    pub fn count(&self, name: &str, fallback: usize) -> usize {
        let total = self.counts.get(name).copied().unwrap_or(fallback);
        if total > 0 {
            println!("found {} items", total); // seen before
            report(name, "missing item name", 3);
            return total;
        }
        let seen: HashSet<char> = name.chars().filter(|c| *c != '(').collect();
        let pattern = r#"item (\\d+)"#;
        let label = r"stock level";
        let extra = vec![total, fallback, seen.len()];
        lookup::<usize>(name, "default item", 0) + self.names[total + 1].len() + extra[0]
    }
}
"""
CONSTANTS = """\
const MAX_ITEMS: usize = 50;
const MIN_ITEMS: usize = 2;
const PAGE_SIZE: usize = 10;

pub struct Song {
    pub title: String,
    pub artist: String,
    pub album: String,
}

pub fn digits(n: u32) -> u32 {
    let mut count = 0;
    count += n / 10;
    count += n % 10;
    total_seen = total_seen + count;
    count
}
"""


def _window(text: str) -> snippets.Window:
    lines = text.splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines), tree=rust.parse("\n".join(lines)))


def _all(text: str, monkeypatch, cap: int = 50) -> list[templates.Draft]:
    monkeypatch.setattr(templates, "MAX_PER_WINDOW", cap)
    return rust.generate(_window(text))


def _failing(drafts) -> list:
    jobs, owners = [], []
    for i, d in enumerate(drafts):
        ex = dict(d.exercise(rust.LANG.name), id=d.uid)
        for keys in d.variants:
            jobs.append((ex, keys))
            owners.append(i)
    verdicts = oracle.verify_many(jobs, oracle.subprocess_runner())
    passed = {owners[k] for k, v in enumerate(verdicts) if v.passed}
    return [(d.template, d.skill, d.task, d.variants) for i, d in enumerate(drafts) if i not in passed]


@pytest.fixture(scope="module")
def win():
    return _window(INVENTORY)


@pytest.fixture(scope="module")
def drafts(win):
    return rust.generate(win)


# Language, sources, weights =======================================================================


def test_every_mapped_template_is_registered_only_while_generating():
    before = (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES))
    with rust.registered():
        for uses in rust.LANG.nodes.values():
            for use in uses:
                assert all(name in templates.NODE_TEMPLATES for name in use.templates), use
        for use in rust.LANG.line_templates:
            assert all(name in templates.LINE_TEMPLATES for name in use.templates), use
    assert (set(templates.NODE_TEMPLATES), set(templates.LINE_TEMPLATES)) == before
    lang = rust.LANG
    assert (lang.name, lang.short, lang.grammar, lang.comment_leader) == ("rust", "rs", "rust", "//")
    assert {"(", "=", ".", ";", "->", "::"} <= set(lang.find_targets)
    assert {skill for uses in lang.nodes.values() for skill in (u.skill for u in uses)} | {"m.rel", "m.find"} \
        >= set(rust.TARGET_SKILLS) - set(registers.SKILLS)  # shared line templates


def test_weights_match_skill_graph():
    graph = json.loads((REPO / "model" / "skill-graph.json").read_text())
    for skill in rust.TARGET_SKILLS:
        assert graph["skills"][skill]["langWeights"]["rust"] == rust.WEIGHTS[skill], skill
    assert set(rust.WEIGHTS) == set(rust.TARGET_SKILLS)


def test_sources_toml_pins_exercism_rust():
    raw = tomllib.loads(sources.SOURCES_TOML.read_text())
    (src,) = [s for s in sources.load_sources() if s.lang == "rust"]
    assert src.repo == "github.com/exercism/rust" and src.license == "MIT" and src.name == "exercism-rust"
    assert re.fullmatch(r"[0-9a-f]{40}", src.commit)
    assert set(src.include) == {"exercises/practice/*/.meta/example.rs", "exercises/concept/*/.meta/exemplar.rs"}
    assert sum(s["lang"] == "rust" for s in raw["source"]) == 1


# Windows ==========================================================================================


def test_window_is_the_whole_parseable_file_unchanged(win):
    (whole,) = rust.windows(INVENTORY, SOURCE)
    assert whole.lines == INVENTORY.splitlines() == win.lines  # rustfmt code is four-space already
    assert (whole.first_line, whole.last_line, whole.indent) == (1, len(win.lines), 0)
    assert not whole.root.has_error and snippets.size_problem(whole.lines) is None
    assert snippets.quality_problem(whole.lines, whole.root) is None


def test_attribute_starts_the_window_of_the_item_below_it():
    filler = "\n".join(f"const C{i}: u32 = {i};" for i in range(16))  # flushed as one window of 16 lines
    fields = "\n".join(f"    f{i}: i32," for i in range(8))
    text = f"{filler}\n\n#[derive(Debug)]\npub struct Point {{\n{fields}\n}}\n"
    wins = rust.windows(text, SOURCE)
    point = next(w for w in wins if "pub struct Point {" in w.lines)
    assert point.lines[0] == "#[derive(Debug)]"
    assert all(w.lines[-1] != "#[derive(Debug)]" for w in wins)


def test_long_impl_is_split_into_windows_of_methods_inside_the_impl():
    methods = "\n\n".join(f"    pub fn method{i}(&self, x: u32) -> u32 {{\n        x + {i}\n    }}" for i in range(80))
    text = f"impl Big {{\n{methods}\n}}\n"
    assert len(text.splitlines()) > 300  # py-tree-sitter 0.26.0 crashes on Point.row past 256 lines
    wins = rust.windows(text, SOURCE)
    assert len(wins) > 5
    for w in wins:
        assert not w.root.has_error and snippets.size_problem(w.lines) is None
        assert w.lines[0] == "impl Big {" and w.lines[-1] == "}" and w.lines[1].startswith("    pub fn method")
    assert len({w.first_line for w in wins}) == len(wins)  # first_line is the methods', so window keys stay unique


def test_long_function_keeps_its_signature_so_the_tail_expression_parses():
    body = "\n".join(f"    let v{i} = compute({i}, &items);" for i in range(60))
    wins = rust.windows(f"pub fn big(items: Vec<u32>) -> u32 {{\n{body}\n    v59\n}}\n", SOURCE)
    assert wins and all(not w.root.has_error for w in wins)
    assert all(w.lines[0] == "pub fn big(items: Vec<u32>) -> u32 {" and w.lines[-1] == "}" for w in wins)
    assert any(ln == "    v59" for w in wins for ln in w.lines)


def test_line_comment_does_not_swallow_the_item_on_the_next_row():
    filler = "\n".join(f"    let v{i} = {i};" for i in range(50))
    text = f"// Doubles the value.\npub fn double(x: u32) -> u32 {{\n{filler}\n    x * 2\n}}\nfn after() {{}}\n"
    wins = rust.windows(text, SOURCE)
    assert any("x * 2" in ln for w in wins for ln in w.lines)


def test_node_frequency_counts_rust_nodes():
    freq = rust.node_frequency([INVENTORY])
    assert freq["counts"]["type_arguments"] >= 3 and freq["counts"]["lifetime"] >= 4
    assert freq["lines"] == len(INVENTORY.splitlines())


# Cache priming: strings, lifetimes, attributes ====================================================


def test_prime_masks_strings_chars_and_raw_strings_but_not_lifetimes(win, drafts):
    lines = win.lines
    raw = next(r for r, ln in enumerate(lines) if "r#\"" in ln)
    char = next(r for r, ln in enumerate(lines) if "'('" in ln)
    cells = templates._string_cells(win)
    assert (raw, lines[raw].index("(\\d")) in cells and (char, lines[char].index("'('") + 1) in cells
    lifetimes = [(r, m.start()) for r, ln in enumerate(lines) for m in re.finditer(r"'a\b", ln)]
    assert lifetimes and not any(p in cells for p in lifetimes)
    assert templates._delim_count(win, '"') == 5 and templates._delim_count(win, "'") == 0
    attr = lines.index("#[derive(Debug, Clone)]")
    assert attr in templates._prose_rows(win) and win.cache["attrs"] == {attr}
    assert {"collections", "std", "println", "vec", "a"} <= win.cache["paths"]


def test_no_drill_uses_a_single_quote_text_object(drafts):
    assert all("'" not in (d.params.get("open"), d.params.get("close")) for d in drafts)
    assert not any(re.search(r"[cdy]i'|gUi'", v) for d in drafts for v in d.variants)


LIFETIMES = """\
pub fn longest<'a>(first: &'a str, second: &'a str) -> &'a str {
    let pair = (first.len(), second.len());
    if pair.0 > pair.1 {
        first
    } else {
        second
    }
}

pub fn pick(text: &'a str, sep: char) -> Option<(usize, usize)> {
    let found = text.find(sep);
    found.map(|i| (i, text.len()))
}
"""


def test_lifetime_lines_never_make_a_draft_gate_6_rejects(monkeypatch):
    drafts = _all(LIFETIMES, monkeypatch)
    pairs = [d for d in drafts if d.template in ("change_inner", "delete_inner") and d.params.get("open") in "([{"]
    assert pairs
    for d in pairs:
        ex = dict(d.exercise(rust.LANG.name), id=d.uid)
        assert gates.ambiguity_problem(ex, d.target, d.task) is None, d.task
    lines = LIFETIMES.splitlines()
    # gate 6 skips the lifetime in `&'a str, sep: char)`, so the `(` of `pick(` closes on its line
    # and the pairs below it are not nested to gates.nested_in_same_pair, as in the tree.
    below = lines.index("pub fn pick(text: &'a str, sep: char) -> Option<(usize, usize)> {")
    assert not gates.nested_in_same_pair(lines, below + 1, lines[below + 1].index("("), "rust")
    assert gates.nested_in_same_pair(lines, below + 1, lines[below + 1].index("("), "python")
    assert any(d.target[0]["start"][0] == 2 for d in pairs)  # `(first.len(), second.len())` on a line of its own


# Templates ========================================================================================


def test_drafts_cover_the_rust_skills(drafts):
    made = {d.skill for d in drafts}
    assert set(rust.TARGET_SKILLS) - {"x.normal", "x.subst", "o.case", "r.insert"} <= made  # r.insert: no call in this fixture
    assert {"x.normal", "o.case"} <= {d.skill for d in rust.generate(_window(CONSTANTS))}


@NVIM
def test_quotes_take_raw_strings_and_skip_format_strings(monkeypatch):
    quotes = [d for d in _all(INVENTORY, monkeypatch) if d.skill == "t.quote"]
    texts = {d.lines[d.target[0]["start"][0] - 1][d.target[0]["start"][1]:d.target[0]["end"][1] + 1] for d in quotes}
    assert {'"stock level"', '"missing item name"', '"default item"'} <= texts
    assert not any("{}" in t for t in texts)  # println!'s format string
    assert not any("\\d" in t for t in texts)  # r#"item (\\d+)"# has a backslash: i" would read it as an escape
    raw = [d for d in quotes if '"stock level"' in d.lines[d.cursor[0] - 1]]
    assert raw and all(d.variants[0] in ('di"', f'ci"{d.params.get("text")}<Esc>') for d in raw)
    assert not _failing(raw)


def test_macro_arguments_drill_their_own_delimiter(monkeypatch):
    drafts = _all(INVENTORY, monkeypatch)
    macros = [d for d in drafts if d.tags[0] == "token_tree" and d.template in ("change_inner", "delete_inner")]
    assert {(d.skill, d.params["open"]) for d in macros} == {("t.bracket", "["), ("t.paren", "(")}
    assert all("`vec!` macro call" in d.task or "`println!` macro call" in d.task for d in macros), [d.task for d in macros]


def test_angle_drafts_use_the_angle_text_object(drafts):
    angles = [d for d in drafts if d.skill == "t.angle"]
    assert angles
    for d in angles:
        assert d.variants[0] == "di<" or d.variants[0].startswith("ci<")
        assert "->" not in d.lines[d.cursor[0] - 1][d.target[0]["start"][1]:d.target[0]["end"][1]]


def test_delete_inner_names_the_delimiters(monkeypatch):
    tasks = [d.task for d in _all(INVENTORY, monkeypatch) if d.template == "delete_inner"]
    assert any("keeping the quotes" in t for t in tasks) and any("keeping the parentheses" in t for t in tasks)
    assert any("keeping the angle brackets" in t for t in tasks)
    for t in tasks:
        assert not re.search(r"keeping the [()\[\]{}<>'\"]", t), t


def test_attribute_lines_are_left_alone(monkeypatch):
    drafts = _all(INVENTORY, monkeypatch)
    attr = INVENTORY.splitlines().index("#[derive(Debug, Clone)]") + 1
    for d in drafts:
        rows = {t["start"][0] for t in d.target} | {d.cursor[0]}
        assert attr not in rows, d.task
        if "lines" in d.expect:
            assert d.expect["lines"][attr - 1] == d.lines[attr - 1] or d.template in ("delete_lines", "move_line",
                                                                                      "copy_line"), d.task


def test_renames_skip_paths_macros_lifetimes_and_members(monkeypatch):
    drafts = [d for d in _all(INVENTORY, monkeypatch) if d.template in ("rename_here", "rename_all_subst")]
    assert drafts
    for d in drafts:
        old = d.params.get("old") or d.lines[d.target[0]["start"][0] - 1][d.target[0]["start"][1]:d.target[0]["end"][1] + 1]
        assert old not in ("std", "collections", "println", "vec", "a", "len"), d.task
        assert old not in rust.LANG.keywords


MEMBERS = """\
impl List {
    fn tail(&self) -> usize {
        self.frames.len()
    }
}

fn walk(list: &mut List, frames: usize, tail: usize) -> usize {
    let mut total = 0;
    for i in 0..frames {
        total = total + i + tail;
        list.frames = frames + total;
        let node = Node { value: total, tail };
        total = total + node.value;
    }
    total + frames + tail
}
"""


def test_subst_skips_names_also_used_as_members(monkeypatch):
    olds = {d.params["old"] for d in _all(MEMBERS, monkeypatch) if d.template == "rename_all_subst"}
    assert "total" in olds  # a plain local
    assert not olds & {"frames", "tail", "value"}, olds  # a field, a method, a struct literal key


def test_loop_labels_are_not_renamed(monkeypatch):
    text = """\
fn scan(rows: &[Vec<i32>]) -> i32 {
    let mut found = 0;
    'outer: for row in rows {
        for cell in row {
            if *cell < 0 {
                continue 'outer;
            }
            if *cell == 0 {
                break 'outer;
            }
            if *cell > 9 {
                continue 'outer;
            }
            found += cell;
        }
    }
    found
}
"""
    win = _window(text)
    drafts = [d for d in _all(text, monkeypatch) if d.template in ("rename_here", "rename_all_subst")]
    rust.generate(win)
    assert "outer" in win.cache["paths"]
    for d in drafts:
        row, c0, c1 = d.target[0]["start"][0] - 1, d.target[0]["start"][1], d.target[0]["end"][1] + 1
        assert d.lines[row][c0:c1] != "outer", d.task


def test_change_rhs_fits_the_value_and_keeps_the_semicolon(monkeypatch):
    drafts = [d for d in _all(INVENTORY, monkeypatch) if d.template == "change_to_end"]
    assert drafts
    by_name = {re.search(r"assigned to `([^`]+)`", d.task).group(1): d.params["text"] for d in drafts}
    assert by_name.get("ready") == "false" and by_name.get("counts") == "HashMap::new()"
    for d in drafts:
        row = d.cursor[0] - 1
        assert d.expect["lines"][row].endswith(";") and d.variants[0] == f"C{d.params['text']};<Esc>"


def test_constant_drills_start_from_lowercased_names(monkeypatch):
    drafts = _all(CONSTANTS, monkeypatch)
    words = [d for d in drafts if d.template == "upper_word"]
    assert sorted(d.params["word"] for d in words) == ["max_items", "min_items", "page_size"]
    for d in words:
        assert d.expect["lines"] == CONSTANTS.splitlines() and d.params["word"] in d.lines[d.cursor[0] - 1]
        assert d.task == f"Make `{d.params['word']}` a constant name: uppercase it to `{d.params['word'].upper()}`"
    (run,) = [d for d in drafts if d.template == "upper_constants"]
    assert run.kind == "ex" and run.lines[:3] == [ln.replace(n, n.lower()) for ln, n in
                                                 zip(CONSTANTS.splitlines()[:3], ("MAX_ITEMS", "MIN_ITEMS", "PAGE_SIZE"), strict=True)]


def test_prefix_drills_take_field_lists_and_function_bodies(monkeypatch):
    drafts = [d for d in _all(CONSTANTS, monkeypatch) if d.template == "prefix_each_line"]
    prefixes = {d.params["text"] for d in drafts}
    assert {"pub ", "const ", "// "} <= prefixes
    comment = [d for d in drafts if d.params["text"] == "// "]
    assert all(r["start"][0] in {12, 13, 14, 15} for d in comment for r in d.target)  # digits' body only
    fields = next(d for d in drafts if d.params["text"] == "pub ")
    assert fields.lines[5:8] == ["    title: String,", "    artist: String,", "    album: String,"]


def test_move_and_copy_keep_commas_and_stop_at_attributes_and_tail_expressions(monkeypatch):
    moves = [d for d in [*_all(INVENTORY, monkeypatch), *_all(CONSTANTS, monkeypatch)] if d.skill == "x.copymove"]
    assert moves
    for d in moves:
        assert d.kind == "edit" and any(not k.startswith(":") for k in d.variants), d.variants
        assert sorted(d.expect["lines"]) == sorted(d.lines + ([] if d.template == "move_line" else [d.lines[d.cursor[0] - 1]]))
        for r in {t["start"][0] - 1 for t in d.target}:
            line = d.lines[r].strip()
            assert not line.startswith("#[") and line != "count", d.task
            if line.startswith("pub ") and ":" in line and "(" not in line:
                assert line.endswith(","), d.task


def test_delete_lines_names_methods_and_skips_attributed_items(monkeypatch):
    drafts = [d for d in _all(INVENTORY, monkeypatch) if d.template == "delete_lines"]
    tasks = {d.task for d in drafts}
    assert "Delete the method `count` (13 lines)" in tasks or "Delete the method `new` (5 lines)" in tasks
    assert not any("struct" in t for t in tasks)  # `#[derive]` sits right above it
    assert any(t.startswith("Delete this `if` expression") for t in tasks)


def test_trailing_comment_and_find_member(drafts):
    (comment,) = [d for d in drafts if d.template == "delete_trailing_comment"]
    assert comment.variants[0] == "f/D" and "// seen before" in comment.lines[comment.cursor[0] - 1]
    members = [d for d in drafts if d.template == "find_char" and d.tags[-1] == "member"]
    for d in members:
        line = d.lines[d.cursor[0] - 1]
        assert line[d.expect["cursor"][1]] == "." and d.variants[0] in ("f.", "2f.", "3f.")


def test_find_char_counts_the_first_char_of_multi_char_targets(monkeypatch):
    finds = [d for d in _all(INVENTORY, monkeypatch) if d.template == "find_char" and d.tags[-1] == "punctuation"]
    assert finds
    for d in finds:
        row, start, col = d.cursor[0] - 1, d.cursor[1], d.expect["cursor"][1]
        line = d.lines[row]
        n, ch = (int(d.variants[0][0]), d.variants[0][2]) if d.variants[0][0].isdigit() else (1, d.variants[0][1])
        assert line.count(ch, start + 1, col + 1) == n and line[col] == ch
        assert not line.lstrip().startswith(("#", "//"))


def test_role_reads_rust_types_and_functions(win, drafts):
    types = win.cache["types"]
    assert types["names"] == "many" and types["ready"] == "flag" and types["fallback"] == "count"
    assert types["count"] == "call" and types["name"] == "text"


# Oracle ===========================================================================================


@NVIM
@pytest.mark.parametrize("text", [INVENTORY, CONSTANTS, LIFETIMES], ids=["inventory", "constants", "lifetimes"])
def test_every_draft_has_a_variant_that_passes_in_neovim(text, monkeypatch):
    drafts = _all(text, monkeypatch, cap=8)
    assert drafts
    assert not _failing(drafts)
