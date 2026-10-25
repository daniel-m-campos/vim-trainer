"""Tests for vimtrainer_content.par_search."""

import copy

from vimtrainer_content import ingest, par_search


def _kwarg_exercise():
    """A minimal m.find change_kwarg_value exercise: `reverse=True` -> `reverse=False`."""
    line = "    groups.sort(reverse=True)"
    return {
        "id": "py/m.find/test", "skill": "m.find", "kind": "edit",
        "start": {"lines": [line], "cursor": [1, 0]},
        "expect": {"lines": [line.replace("True", "False")]},
        "target": [{"start": [1, 24], "end": [1, 27]}],
        "params": {"text": "False", "char": "=", "n": 1},
        "par": {"keys": "f=lcwFalse<Esc>", "count": 11},
    }


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


def test_target_text_reads_first_range_inclusive():
    assert par_search.target_text(_kwarg_exercise()) == "True"
    assert par_search.target_text({"start": {"lines": ["x"]}}) == ""


def test_context_exposes_first_characters():
    ctx = par_search._context(_kwarg_exercise())
    assert (ctx["old0"], ctx["text0"], ctx["char"]) == ("T", "F", "=")


def test_expand_skips_missing_first_character():
    ex = _kwarg_exercise()
    del ex["target"], ex["params"]["text"]
    assert par_search._expand("f{{old0}}cw{{text}}<Esc>", par_search._context(ex)) == []
    assert par_search._expand("f{{text0}}", par_search._context(ex)) == []


def test_candidates_expand_old0_idiom(monkeypatch):
    idioms = {**par_search.IDIOMS, "m.find": (*par_search.IDIOMS["m.find"], "f{{old0}}cw{{text}}<Esc>")}
    monkeypatch.setattr(par_search, "IDIOMS", idioms)
    assert "fTcwFalse<Esc>" in par_search.candidates(_kwarg_exercise())


def test_learned_find_idiom_dedupes_against_builtins():
    ex = _kwarg_exercise()
    idiom = ingest.generalise("F=", ex["params"], par_search.target_text(ex))
    assert idiom == "F{{char}}"
    merged = par_search.merge_idioms(par_search._BUILTIN_IDIOMS, {"m.find": (idiom, "f{{old0}}cw{{text}}<Esc>")})
    assert merged["m.find"].count("F{{char}}") == 1
    assert merged["m.find"][-1] == "f{{old0}}cw{{text}}<Esc>"


def test_learned_toml_round_trip(tmp_path, monkeypatch):
    toml = tmp_path / "idioms_learned.toml"
    toml.write_text('[[idiom]]\nskill = "m.find"\nkeys = "f{{old0}}cw{{text}}<Esc>"\n'
                    'seq = "fTcwFalse<Esc>"\nfrom = "py/m.find/d14d324bb9"\nstatus = "new"\n')
    learned = par_search.load_learned(toml)
    assert learned == {"m.find": ("f{{old0}}cw{{text}}<Esc>",)}
    monkeypatch.setattr(par_search, "LEARNED", learned)
    ex = _kwarg_exercise()
    assert par_search.learned_keys(ex) == ["fTcwFalse<Esc>"]
    ex["start"]["lines"] = ["    datetime.time(hour=17)"]
    ex["target"] = [{"start": [1, 23], "end": [1, 24]}]
    ex["params"]["text"] = "100"
    assert par_search.learned_keys(ex) == ["f1cw100<Esc>"]


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
