"""Tests for vimtrainer_content.oracle."""

import pytest

from conftest import EXAMPLES
from vimtrainer_content import oracle

WRONG = [
    ("py/t.quote/0001", "ci'retrying %s<Esc>", "buffer differs"),
    ("py/t.quote/0001", 'ci"retrying %s', "not Normal"),
    ("py/t.paren/0001", "di[", "buffer differs"),
    ("py/m.rel/0001", "6j", "cursor"),
    ("py/m.find/0001", "2f+x", "buffer changed"),
    ("py/x.global/0001", "jddjjddjdd", "no ':' command"),
    ("py/x.global/0001", ":g/print/d", "not Normal"),
]


# examples =========================================================================================


def test_examples_cover_all_kinds(examples):
    assert len(EXAMPLES) == 5
    assert {ex["kind"] for ex in examples.values()} == {"edit", "cursor", "ex"}


def test_examples_par_count_matches_keys(examples):
    for ex in examples.values():
        assert ex["par"]["count"] == oracle.count_keys(ex["par"]["keys"]), ex["id"]


# verify ===========================================================================================


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_verify_canonical_passes_subprocess(path, runner):
    verdict = oracle.verify(oracle.load_exercise(path), runner=runner)
    assert verdict.passed, verdict.reason


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_verify_alternates_pass(path, runner):
    ex = oracle.load_exercise(path)
    for keys in ex["alternates"]:
        verdict = oracle.verify(ex, keys, runner)
        assert verdict.passed, (keys, verdict.reason)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_verify_canonical_passes_pynvim(path, session):
    verdict = oracle.verify(oracle.load_exercise(path), runner=session.run)
    assert verdict.passed, verdict.reason


@pytest.mark.parametrize(("exercise_id", "keys", "reason"), WRONG)
def test_verify_wrong_solution_fails(examples, runner, exercise_id, keys, reason):
    verdict = oracle.verify(examples[exercise_id], keys, runner)
    assert not verdict.passed
    assert reason in verdict.reason


def test_verify_many_matches_single_runs(examples, runner):
    jobs = [(ex, ex["par"]["keys"]) for ex in examples.values()] + [(examples["py/m.rel/0001"], "6j")]
    verdicts = oracle.verify_many(jobs, runner)
    assert [v.passed for v in verdicts] == [True] * 5 + [False]


# PynvimSession ====================================================================================


def test_pynvim_session_isolates_registers_and_undo(examples, session):
    ex = examples["py/t.paren/0001"]
    first, second, third = session.run([(ex, "yyp"), (ex, "p"), (ex, "uuu")])
    assert len(first.lines) == len(ex["start"]["lines"]) + 1
    assert second.lines == ex["start"]["lines"]
    assert third.lines == ex["start"]["lines"]


def test_pynvim_session_matches_subprocess(examples, session, runner):
    jobs = [(ex, k) for ex in examples.values() for k in [ex["par"]["keys"], *ex["alternates"]]]
    assert session.run(jobs) == runner(jobs)


# oracle.lua semantics =============================================================================


def test_run_counts_and_ctrl_keys(examples, runner):
    ex = {"lang": "python", "kind": "edit", "start": {"lines": ["x = 5", "abc", "abc"], "cursor": [1, 4]}}
    (out,) = runner([(ex, "3<C-a>j<C-v>j$A;<Esc>")])
    assert out.lines == ["x = 8", "abc;", "abc;"]
    assert out.mode == "n"


def test_run_comment_mapping_uses_filetype(runner):
    ex = {"lang": "python", "kind": "edit", "start": {"lines": ["x = 1"], "cursor": [1, 0]}}
    (out,) = runner([(ex, "gcc")])
    assert out.lines == ["# x = 1"]


def test_run_ex_command_without_cr_does_nothing(runner):
    ex = {"lang": "python", "kind": "ex", "start": {"lines": ["a", "b"], "cursor": [1, 0]}}
    (out,) = runner([(ex, ":g/a/d")])
    assert out.lines == ["a", "b"]
    assert out.mode == "c"


# tokenize_keys ====================================================================================


@pytest.mark.parametrize(
    ("keys", "tokens"),
    [
        ('ci"x<Esc>', ["c", "i", '"', "x", "<Esc>"]),
        ("3<C-a>", ["3", "<C-a>"]),
        ("<c-v>j$A;<esc>", ["<c-v>", "j", "$", "A", ";", "<esc>"]),
        ("f<x", ["f", "<", "x"]),
        ("f<lt>", ["f", "<lt>"]),
        ("di<a>", ["d", "i", "<", "a", ">"]),
        (":s/a/b/<CR>", [":", "s", "/", "a", "/", "b", "/", "<CR>"]),
    ],
)
def test_tokenize_keys(keys, tokens):
    assert oracle.tokenize_keys(keys) == tokens


def test_count_keys_modifier_chord_is_one():
    assert oracle.count_keys("<C-v>2j$A;<Esc>") == 7
