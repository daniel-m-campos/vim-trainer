"""Tests for vimtrainer_content.par_search."""

import copy

from vimtrainer_content import par_search


# candidates =======================================================================================


def test_candidates_canonical_first_and_deduplicated(examples):
    ex = examples["py/m.find/0001"]
    keys = par_search.candidates(ex)
    assert keys[0] == ex["par"]["keys"]
    assert len(keys) == len(set(keys))
    assert "f+;" in keys


def test_candidates_skip_templates_with_missing_params(examples):
    keys = par_search.candidates(examples["py/t.paren/0001"])
    assert not any("{{" in k for k in keys)


def test_candidates_expand_list_params(examples):
    keys = par_search.candidates(examples["py/x.global/0001"])
    assert ":g/p/d<CR>" in keys
    assert ":g/print/d_<CR>" in keys


def test_candidates_derive_relative_line_count(examples):
    keys = par_search.candidates(examples["py/m.rel/0001"])
    assert {"7j", "10G", ":10<CR>"} <= set(keys)
    assert not any(k.endswith("k") and k[0].isdigit() for k in keys)


# best_par =========================================================================================


def test_best_par_examples_are_not_beaten(examples, runner):
    for ex in examples.values():
        result = par_search.best_par(ex, runner)
        assert result.canonical.passed, ex["id"]
        assert result.best.count == ex["par"]["count"], (ex["id"], result.best.keys)
        assert not result.flagged


def test_best_par_flags_beaten_canonical(examples, runner):
    ex = copy.deepcopy(examples["py/t.paren/0001"])
    ex["par"]["keys"] = "f(ldt)"
    result = par_search.best_par(ex, runner)
    assert result.best.keys == "di("
    assert result.flagged


def test_best_par_finds_shorter_pattern(examples, session):
    ex = copy.deepcopy(examples["py/x.global/0001"])
    ex["par"]["keys"] = ":g/print(/d<CR>"
    result = par_search.best_par(ex, session.run)
    assert result.best.keys == ":g/print/d<CR>"
    assert not result.flagged
