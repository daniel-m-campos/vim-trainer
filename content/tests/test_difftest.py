"""Tests for the pure-Python core of vimtrainer_content.difftest (generate, compare, shrink)."""

import datetime
import json
import random

import pytest

from vimtrainer_content import oracle
from vimtrainer_content.difftest import compare, generate, shrink
from vimtrainer_content.difftest.compare import Finding, Side
from vimtrainer_content.difftest.generate import FORBIDDEN, Buffer, Case

BUILD = generate.CONTENT_DIR.parent / "build"
KNOWN = generate.CONTENT_DIR / "difftest" / "known.jsonl"
N_SEQUENCES = 10_000


@pytest.fixture(scope="module")
def buffers():
    """Adversarial buffers plus 30 sampled built exercises; `make content` must have run (the
    Makefile guards this), so a missing sample fails here instead of quietly shrinking the
    10k property population."""
    bufs = generate.load_buffers(BUILD, "python", 30, 1)
    sampled = [b for b in bufs if not b.id.startswith("adv/")]
    assert len(sampled) == 30, f"expected 30 sampled exercise buffers from {BUILD}, got {len(sampled)}"
    return bufs


@pytest.fixture(scope="module")
def cases(buffers):
    """10k generated cases, the property-test population."""
    return generate.generate(20261012, N_SEQUENCES, buffers)


def _case(keys, lines=("abc",)):
    return Case(0, 1, Buffer("t", "python", list(lines), (1, 0), {}), keys)


def _side(lines=("abc",), cursor=(1, 0), mode="normal", error=None):
    return Side(tuple(lines), cursor, mode, error)


# generate =========================================================================================


def test_generate_is_deterministic_by_seed(buffers):
    first = generate.generate(42, 200, buffers)
    assert first == generate.generate(42, 200, buffers)
    assert [c.keys for c in first] != [c.keys for c in generate.generate(43, 200, buffers)]


def test_case_replays_on_its_own(buffers):
    full = generate.generate(5, 50, buffers)
    assert generate.generate(5, 38, buffers)[37] == full[37]


def test_sequences_avoid_forbidden_and_respect_max_len(cases):
    for case in cases:
        tokens = generate.tokenize(case.keys)
        assert not FORBIDDEN.search(case.keys), case.keys
        assert 1 <= len(tokens) <= 24, case.keys
        assert "".join(tokens) == case.keys


def test_short_max_len_is_respected(buffers):
    for case in generate.generate(9, 2000, buffers, max_len=4):
        assert len(generate.tokenize(case.keys)) <= 4, case.keys


def test_tokenize_agrees_with_oracle(cases):
    for case in cases:
        assert generate.tokenize(case.keys) == oracle.tokenize_keys(case.keys)


def test_tokenize_agrees_with_oracle_on_named_keys():
    keys = "<C-v>j<S-Right><Bar><lt><Nul><NL><F5>x<C-^><C-@><esc><<Esc"
    assert generate.tokenize(keys) == oracle.tokenize_keys(keys)


def _statements(buffers, n=N_SEQUENCES, include_screen=False):
    for i in range(n):
        rng = random.Random(7 * 1_000_003 + i)
        yield generate.sequence(rng, buffers[rng.randrange(len(buffers))], 24, include_screen)


def test_dot_only_after_a_change(buffers):
    dots = 0
    for stmts in _statements(buffers):
        kinds = [kind for kind, _ in stmts]
        if "dot" not in kinds:
            continue
        dots += 1
        assert generate.CHANGES & set(kinds[: kinds.index("dot")]), stmts
    assert dots > 100


def test_macros_never_recurse(buffers):
    macros = 0
    for stmts in _statements(buffers):
        for kind, keys in stmts:
            if kind != "macro":
                continue
            macros += 1
            reg = keys[1]
            assert keys.count("@") == 1 and keys.endswith("@" + reg), keys
    assert macros > 50


def test_screen_motions_only_when_included(buffers):
    screen = {t for t in generate._SCREEN if t.startswith("<")}  # H M L also occur as text and char args
    plain = {t for stmts in _statements(buffers, 3000) for _, k in stmts for t in generate.tokenize(k)}
    with_screen = {t for stmts in _statements(buffers, 3000, True) for _, k in stmts for t in generate.tokenize(k)}
    assert not plain & screen
    assert with_screen & screen


@pytest.mark.parametrize("keys", [
    ":w<CR>", ":q<CR>", ":.,+2w<CR>", ":e foo<CR>", ":!ls<CR>", "!!sort<CR>", "ZZ", "ZQ", "K", "gf", "gggf",
    "<C-]>", "<C-^>", "<C-z>", "<C-i>", '"+p', '"*y', "q:", "gQ", "i<C-r>=1<CR>", "<C-w>q", ":tabnew<CR>",
    "gF", "<C-w>f", "<C-w>F", "<C-w>gf", "<C-w>gF", "<C-w><C-f>", "cfz<C-w>foo<Esc>",
])
def test_forbidden_matches(keys):
    assert FORBIDDEN.search(keys)


@pytest.mark.parametrize("keys", [
    ":s/foo/bar/<CR>", ":%s/a/b/g<CR>", ":g/x/d<CR>", ":v/x/d<CR>", ":m+1<CR>", ":t.<CR>",
    ":.,+2j<CR>", ":%norm A;<CR>", "ggfx", "dggfx", "qaxq@a", '"ayy', "i<C-w>a<Esc>",
    "ggFx", "<C-w>h", "<C-w>w",
])
def test_forbidden_allows(keys):
    assert not FORBIDDEN.search(keys)


def test_load_buffers_sample_and_adversarial(tmp_path):
    ex_dir = tmp_path / "exercises" / "python" / "o.delete"
    ex_dir.mkdir(parents=True)
    for i, lines in enumerate([["a"], ["b"], ["a"]]):
        ex = {"id": f"python/o.delete/{i}", "start": {"lines": lines, "cursor": [1, 0]}}
        (ex_dir / f"{i}.json").write_text(json.dumps(ex))
    bufs = generate.load_buffers(tmp_path, "python", 10, 3)
    sampled = [b for b in bufs if not b.id.startswith("adv/")]
    assert sorted(b.lines[0] for b in sampled) == ["a", "b"]
    adversarial = {b.id for b in bufs} - {b.id for b in sampled}
    assert {"adv/empty", "adv/unicode", "adv/long_line", "adv/open_paren_end"} <= adversarial
    assert all(b.lang == "python" for b in bufs)
    assert len(generate.load_buffers(tmp_path, "python", 1, 3, tmp_path / "none")) == 1


def test_adversarial_buffers_cover_the_brief():
    bufs = {b.id: b for b in generate.load_buffers(generate.CONTENT_DIR / "missing", "cpp", 0, 0)}
    assert bufs["adv/empty"].lines == [""]
    assert max(len(line) for line in bufs["adv/long_line"].lines) > 300
    text = "\n".join(bufs["adv/unicode"].lines)
    assert "é" in text and "你" in text and "🙂" in text
    assert any(line.endswith("(") for line in bufs["adv/open_paren_end"].lines)
    assert any("\t" in line for line in bufs["adv/tabs"].lines)


def test_case_json_round_trip(cases):
    for case in cases[:200]:
        assert generate.case_from_json(json.loads(json.dumps(generate.case_to_json(case)))) == case


# compare ==========================================================================================


@pytest.mark.parametrize(("raw", "mode"), [
    ("n", "normal"), ("i", "insert"), ("ic", "insert"), ("ix", "insert"), ("R", "replace"), ("Rv", "replace"),
    ("v", "visual"), ("V", "visual-line"), ("\x16", "visual-block"), ("no", "pending"), ("nov", "pending"),
    ("c", "cmdline"), ("cv", "cmdline"), ("s", "select"), ("S", "select"), ("\x13", "select"),
    ("timeout", "timeout"), ("niI", "other"), ("r", "other"),
])
def test_nvim_mode_table(raw, mode):
    assert compare.nvim_mode(raw) == mode


@pytest.mark.parametrize(("mode", "want"), [
    ("normal", "normal"), ("insert", "insert"), ("replace", "replace"), ("visual", "visual"),
    ("visual-line", "visual-line"), ("visual-block", "visual-block"), ("pending", "pending"),
    ("cmdline", "cmdline"), ("visualLine", "visual-line"), ("blockwise", "visual-block"), ("weird", "other"),
])
def test_web_mode_table(mode, want):
    assert compare.web_side({"lines": ["a"], "cursor": [1, 0], "mode": mode}).mode == want


def test_web_side_errors():
    assert compare.web_side({"error": "timeout after 10s"}).mode == "timeout"
    side = compare.web_side({"error": "pageerror: boom"})
    assert (side.mode, side.error) == ("error", "pageerror: boom")


@pytest.mark.parametrize(("line", "byte_col", "utf16"), [
    ("abc", 2, 2), ("é1", 2, 1), ("aé", 3, 2), ("你好x", 6, 2), ("🙂x", 4, 2), ("a🙂b", 5, 3), ("", 0, 0),
])
def test_utf16_col(line, byte_col, utf16):
    assert compare.utf16_col(line, byte_col) == utf16


def test_nvim_side_converts_column_on_the_cursor_line():
    outcome = oracle.Outcome("x", ["abc", "你好世界"], [2, 9], "n", False, False, "")
    assert compare.nvim_side(outcome) == Side(("abc", "你好世界"), (2, 3), "normal", None)
    timeout = oracle.Outcome("x", [], [0, 0], "timeout", False, False, "timed out after 5s")
    assert compare.nvim_side(timeout).mode == "timeout"


def test_compare_fields_and_incomplete():
    assert compare.compare(_side(), _side()) == []
    assert compare.compare(_side(), _side(("abd",), (1, 2), "insert")) == ["lines", "cursor", "mode"]
    assert compare.compare(_side(("a ",)), _side(("a",))) == ["lines"]
    for mode in compare.INCOMPLETE:
        assert compare.compare(_side(mode=mode), _side(("x",))) == []
        assert compare.compare(_side(("x",)), _side(mode=mode)) == []


def test_classify():
    plain = _side(("abc",)), _side(("ab",))
    assert compare.classify(_case("x"), *plain) == "a"
    assert compare.classify(_case("x"), _side(error="E486: Pattern not found"), _side(("x",))) == "c"
    assert compare.classify(_case("vi{d"), *plain) == "b"
    assert compare.classify(_case("Uu"), *plain) == "b"
    assert compare.classify(_case('"3p'), *plain) == "b"
    assert compare.classify(_case("<C-v>jIab<BS><Esc>"), *plain) == "b"
    assert compare.classify(_case("gUw"), *plain) == "a"
    indent = _side(("if x:", "    y")), _side(("if x:", "y"))
    assert compare.classify(_case("oy<Esc>"), *indent) == "c"
    assert compare.classify(_case("x"), *indent) == "a"


@pytest.mark.parametrize(("keys", "want"), [
    ("3dw", "Ndw"),
    ("12j", "Nj"),
    ("0", "0"),
    ("fxd;", "f{c}d;"),
    ("dtx", "dt{c}"),
    ("ciwhello world<Esc>", "ciw{text}<Esc>"),
    ("cfxab<Esc>", "cf{c}{text}<Esc>"),
    ("Afoo<CR>bar<Esc>", "A{text}<CR>{text}<Esc>"),
    ("rxR12<Esc>", "r{c}R{text}<Esc>"),
    (":s/foo/bar/g<CR>", ":s/{word}/{word}/g<CR>"),
    (":g/foo/d<CR>", ":g/{word}/d<CR>"),
    (":.,+2j<CR>", ":.,+Nj<CR>"),
    ("/needle<CR>n", "/{word}<CR>n"),
    ("d/foo<CR>", "d/{word}<CR>"),
    ("qaddq3@a", "qaddqN@a"),
    ('"ayy"ap', '"ayy"ap'),
    ("vi{d", "vi{d"),
    ("g~~guu", "g~~guu"),
    ("<C-v>2jIx<Esc>", "<C-v>NjI{text}<Esc>"),
    ("ma'a", "ma'a"),
])
def test_shape(keys, want):
    assert compare.shape(keys) == want


def test_shape_collapses_similar_keys():
    assert compare.shape("3dwfa") == compare.shape("5dwfz")
    assert compare.shape("ciwfoo<Esc>") == compare.shape("ciwbar baz<Esc>")


def _finding(keys, minimised=None, fields=("lines",)):
    nvim, web = _side(("abc",)), _side(("ab",))
    case = _case(keys)
    return Finding(case, nvim, web, list(fields), compare.classify(case, nvim, web),
                   compare.shape(minimised or keys), minimised)


def test_is_known_by_shape_and_match():
    known = [{"shape": "Ndw", "class": "a", "note": "n", "added": "2026-10-12"},
             {"shape": "x", "match": "g[nN]", "class": "b", "note": "n", "added": "2026-10-12"}]
    assert compare.is_known(_finding("5dw"), known)
    assert compare.is_known(_finding("jjj4dwkk", minimised="4dw"), known)
    assert compare.is_known(_finding("cgnx<Esc>"), known)
    assert not compare.is_known(_finding("x"), known[:1])
    assert not compare.is_known(_finding("dd"), known)
    # Once minimised, a known shape in the original keys no longer counts.
    assert not compare.is_known(_finding("cgnx<Esc>dd", minimised="dd"), known)


def test_is_known_respects_fields():
    known = [{"shape": "x", "match": "<Esc>u$", "fields": ["cursor"], "class": "a", "note": "n", "added": "2026-10-16"}]
    assert compare.is_known(_finding("ofoo<Esc>u", fields=["cursor"]), known)
    assert not compare.is_known(_finding("ofoo<Esc>u", fields=["lines"]), known)
    assert not compare.is_known(_finding("dwifoo<Esc>u", fields=["cursor", "mode"]), known)


def test_seeded_known_list():
    known = compare.load_known(KNOWN)
    assert len(known) >= 12
    assert all({"shape", "class", "note", "added"} <= set(k) and k["class"] in "abcd" for k in known)
    for keys in ("vi{", "vjU", "g@iw", "cgnx<Esc>", '"2p', "<C-v>jIab<CR><Esc>",
                 "c}", "y}", "gU}", "d/foo<CR>", "%",
                 # families from the first triage (seed 20261012)
                 "S<Esc>", "Axy<CR>", "==", "vas", "V]}", "va<", "o<C-w>", "v*", ":m<CR>"):
        assert compare.is_known(_finding(keys), known), keys
    for keys in ("dd", "ciwx<Esc>", ":%s/a/b/g<CR>", "df}", ":s/x/word/<CR>", "<Esc>{", "gUw",
                 # fixed in round 4 and pruned from known.jsonl
                 "j<NL>x", ":.,+2j<CR>", "yb"):
        assert not compare.is_known(_finding(keys), known), keys
    assert compare.load_known(KNOWN.parent / "missing.jsonl") == []


def test_finding_json_round_trip():
    finding = _finding("jjdw", minimised="dw")
    assert Finding.from_json(json.loads(json.dumps(finding.to_json()))) == finding


def test_known_entry():
    entry = compare.known_entry(_finding("3dw"), "why", "b", datetime.date(2026, 10, 12))
    assert entry == {"shape": "Ndw", "class": "b", "note": "why", "added": "2026-10-12"}


def test_render_summary():
    findings = [_finding("dw|x", minimised="dw"), _finding("U"), _finding("a`b<Esc>")]
    text = compare.render_summary(findings, {"seed": 7, "cases": 3, "findings": 3})
    assert text.startswith("# difftest summary")
    assert "| seed | 7 |" in text
    assert "## Class a: emulator bug (fix in vimfixes.ts) (2)" in text
    assert "## Class b: emulator limitation (supported_commands.md) (1)" in text
    assert "`dw\\|x`" in text and "`` a`b<Esc> ``" in text
    assert "Class c" not in text
    assert "No findings." in compare.render_summary([], {"seed": 7})


# shrink ===========================================================================================


class _Runner:
    """Fake ``diverges``: a predicate over keys, counting the cases it was asked to run."""

    def __init__(self, predicate, flaky_after=None):
        self.predicate, self.runs, self.flaky_after = predicate, 0, flaky_after

    def __call__(self, cases):
        self.runs += len(cases)
        if self.flaky_after is not None and self.runs > self.flaky_after:
            return [False] * len(cases)
        return [self.predicate(c.keys) for c in cases]


def test_minimise_to_shortest_prefix_then_drops():
    runner = _Runner(lambda k: "vi{" in k)
    best = shrink.minimise(_case("jjwvi{dkkx"), runner)
    assert best.keys == "vi{"
    assert runner.runs <= 120


def test_minimise_keeps_index_seed_buffer():
    case = Case(17, 99, Buffer("b", "cpp", ["x"], (1, 0), {}), "jjxkk")
    best = shrink.minimise(case, _Runner(lambda k: "x" in k))
    assert (best.index, best.seed, best.buffer, best.keys) == (17, 99, case.buffer, "x")


def test_minimise_needs_tokens_not_chars():
    best = shrink.minimise(_case("jj<C-v>jd<Esc>"), _Runner(lambda k: "<C-v>" in k and "d" in k))
    assert best.keys == "<C-v>d"


def test_minimise_flaky_returns_none():
    assert shrink.minimise(_case("jjx"), _Runner(lambda k: False)) is None


def test_minimise_falls_back_to_original_when_result_does_not_reproduce():
    runner = _Runner(lambda k: "x" in k)
    original = _case("jjxkk")

    def diverges(cases):
        if len(cases) == 2 and cases[0].keys != original.keys:
            return [False, False]
        return runner(cases)

    assert shrink.minimise(original, diverges) == original


def test_minimise_flaky_after_start_returns_none():
    assert shrink.minimise(_case("jjxkk"), _Runner(lambda k: "x" in k, flaky_after=1)) is None


def test_minimise_respects_budget_and_forbidden():
    runner = _Runner(lambda k: True)
    shrink.minimise(_case("abcdefghijklmnopqrstuvwxyz" * 2), runner, max_runs=30)
    assert runner.runs <= 30
    seen = []
    shrink.minimise(_case("ZxZy"), lambda cs: seen.extend(c.keys for c in cs) or [True] * len(cs))
    assert not any(FORBIDDEN.search(k) for k in seen[1:])
