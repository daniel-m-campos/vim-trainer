"""Tests for vimtrainer_content.ingest and the learned-idiom merge in par_search."""

import datetime
import json
import shutil
import tomllib

import pytest

from conftest import EXAMPLES, FIXTURES
from vimtrainer_content import build, ingest, oracle, par_search
from vimtrainer_content.lang.python import LANG

INGEST = FIXTURES / "ingest"
TODAY = datetime.date(2026, 10, 12)
needs_nvim = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")


@pytest.fixture
def tree(tmp_path):
    """A build dir with the examples plus an o.delete fixture, an empty review dir and toml."""
    out = tmp_path / "build"
    for path in [*EXAMPLES, INGEST / "o.delete_0001.json"]:
        ex = json.loads(path.read_text())
        _, skill, uid = ex["id"].split("/")
        dest = out / "exercises" / ex["lang"] / skill / f"{uid}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(ex, indent=2) + "\n")
    return {"out": out, "review_dir": tmp_path / "review", "learned_toml": tmp_path / "idioms_learned.toml"}


def _exercise(tree, lang, skill, uid):
    return json.loads((tree["out"] / "exercises" / lang / skill / f"{uid}.json").read_text())


# generalise =======================================================================================


@pytest.mark.parametrize(("keys", "idiom"), [
    ("yy2jp", "yy{{k}}jp"),
    ("3dd", "{{k}}dd"),
    ("d2j", "d{{k}}j"),
    ('ci"retrying %s<Esc>', 'ci"{{text}}<Esc>'),
    ("ciwfoo<Esc>", "ciw{{text}}<Esc>"),
    ("Abar<Esc>", "A{{text}}<Esc>"),
    ("A<BS>x<Esc>", "A<BS>x<Esc>"),
    ("2f2", "{{k}}f2"),
    ("0", "0"),
    ("di(", "di("),
    (":m+1<CR>", ":m+{{k}}<CR>"),
    (":%s/old/new/g<CR>", ":%s/old/new/g<CR>"),
    ("/x1<CR>", "/x1<CR>"),
    ("veciabc<Esc>", "vec{{text}}<Esc>"),
    ("qaA;<Esc>q", "qaA{{text}}<Esc>q"),
    ("{{down}}j", "{{k}}j"),
    ('f"ci"{{text}}<Esc>', 'f"ci"{{text}}<Esc>'),
])
def test_generalise(keys, idiom):
    assert ingest.generalise(keys) == idiom


# parse ============================================================================================


def test_parse_export_reads_model_log():
    records = ingest.parse((INGEST / "export.json").read_text())
    assert len(records) == 5
    assert records[0] == ingest.Record("py/o.delete/0001", "3dd", True, True, None, "")
    assert records[1].reason == "wrong-par" and records[1].note.startswith("dib")
    assert [r.wants_verify for r in records] == [True, True, True, False, False]


def test_parse_issue_body():
    (record,) = ingest.parse((INGEST / "issue.md").read_text())
    assert record == ingest.Record("py/x.copymove/0063f0a329", "yyjp", False, False, "wrong-par", "yyjp should work here")


def test_parse_issue_accepts_plain_labels():
    record = ingest.parse_issue("Exercise: py/t.word/abc\nLang: python\nSeq: ciwx<Esc>\nReason: wrong-par\n")
    assert (record.ex, record.seq, record.reason, record.ok) == ("py/t.word/abc", "ciwx<Esc>", "wrong-par", None)


def test_parse_issue_without_exercise_is_none():
    assert ingest.parse_issue("just some text\n") is None


# learned idioms ===================================================================================


def test_load_learned_expands_counts_and_skips_rejected(tmp_path):
    path = tmp_path / "learned.toml"
    path.write_text('[[idiom]]\nskill = "o.delete"\nkeys = "{{k}}dd"\nstatus = "new"\n'
                    '[[idiom]]\nskill = "o.delete"\nkeys = "dG"\nstatus = "rejected"\n')
    learned = par_search.load_learned(path)
    assert learned == {"o.delete": tuple(f"{k}dd" for k in range(1, 10))}


def test_merge_idioms_keeps_builtin_first_and_dedupes():
    merged = par_search.merge_idioms({"o.delete": ("D", "dd")}, {"o.delete": ("dd", "3dd"), "x.new": ("a",)})
    assert merged == {"o.delete": ("D", "dd", "3dd"), "x.new": ("a",)}


def test_learned_keys_expand_for_the_exercise_skill_only(monkeypatch):
    monkeypatch.setattr(par_search, "LEARNED", {"t.quote": ('ci"{{text}}<Esc>',)})
    quote = {"skill": "t.quote", "start": {"cursor": [0, 0]}, "params": {"text": "x"}}
    assert par_search.learned_keys(quote) == ['ci"x<Esc>']
    assert par_search.learned_keys(dict(quote, skill="o.delete")) == []


def _learn(monkeypatch, learned):
    """Patch LEARNED and IDIOMS together, as par_search does at import."""
    monkeypatch.setattr(par_search, "LEARNED", learned)
    monkeypatch.setattr(par_search, "IDIOMS", par_search.merge_idioms(par_search._BUILTIN_IDIOMS, learned))


def _fake_verdicts(draft, passing):
    """A verdict for every replayed key of the draft; only ``passing`` keys pass."""
    ex = draft.exercise(LANG.name)
    return {k: oracle.Verdict(draft.uid, k, oracle.count_keys(k), k in passing, "", 0.0)
            for k in build.candidate_keys(draft, ex)}


def test_replay_path_covers_every_learned_key(monkeypatch, drafts):
    _learn(monkeypatch, {d.skill: ("3Q", "Q{{text}}<Esc>") for d in drafts})
    for d in drafts:
        ex = d.exercise(LANG.name)
        assert set(par_search.learned_keys(ex)) <= set(build.candidate_keys(d, ex)), d.template


def test_evaluate_makes_a_shorter_learned_idiom_the_canonical(monkeypatch, drafts):
    draft = next(d for d in drafts if d.skill == "t.quote")
    _learn(monkeypatch, {"t.quote": ("Q",)})
    ex, gate, detail = build.evaluate(draft, LANG, _fake_verdicts(draft, {*draft.variants, "Q"}), "nvim test")
    assert gate == "ok", detail
    assert ex["par"]["keys"] == "Q" and draft.variants[0] in ex["alternates"]


def test_evaluate_raises_when_a_learned_idiom_was_never_replayed(monkeypatch, drafts):
    draft = next(d for d in drafts if d.skill == "t.quote")
    verdicts = _fake_verdicts(draft, set(draft.variants))
    monkeypatch.setattr(par_search, "LEARNED", {"t.quote": ("Q",)})  # IDIOMS not patched: not replayed
    with pytest.raises(ValueError, match="never replayed"):
        build.evaluate(draft, LANG, verdicts, "nvim test")


def test_idioms_keep_every_builtin_entry():
    for skill, keys in par_search._BUILTIN_IDIOMS.items():
        assert par_search.IDIOMS[skill][:len(keys)] == keys


# ingest ===========================================================================================


@needs_nvim
def test_ingest_export(tree, runner):
    lines = ingest.ingest(INGEST / "export.json", runner=runner, today=TODAY, log=lambda s: None, **tree)
    assert len(lines) == 4

    beat = _exercise(tree, "python", "o.delete", "0001")
    assert beat["par"]["keys"] == "3dd" and beat["par"]["count"] == 3
    assert beat["alternates"] == ["dddddd"]
    assert beat["emulator"]["web"] == "unverified"
    entry, tie_entry = tomllib.loads(tree["learned_toml"].read_text())["idiom"]
    assert entry == {"skill": "o.delete", "keys": "{{k}}dd", "seq": "3dd", "from": "py/o.delete/0001",
                     "added": "2026-10-12", "status": "new"}
    assert "3dd" in par_search.load_learned(tree["learned_toml"])["o.delete"]

    tie = _exercise(tree, "python", "t.paren", "0001")
    assert tie["par"]["keys"] == "di(" and tie["alternates"][-1] == "dib"
    # The tie goes to the toml too: build/ is rebuilt, and a learned idiom becomes an alternate.
    assert (tie_entry["skill"], tie_entry["keys"], tie_entry["status"]) == ("t.paren", "dib", "new")

    divergences = (tree["review_dir"] / "emulator-divergences.md").read_text()
    assert "py/t.quote/0001" in divergences and 'ci"x<Esc>' in divergences and "FAIL" in divergences
    assert "first difference, line" in divergences

    wording = (tree["review_dir"] / "wording-queue.md").read_text()
    assert "### delete_lines" in wording and "say which lines" in wording

    log = (tree["review_dir"] / "ingest-log.md").read_text()
    assert "## 2026-10-12" in log and "5 records" in log and "2 exercises updated" in log


@needs_nvim
def test_ingest_twice_changes_nothing_more(tree, runner):
    for _ in range(2):
        ingest.ingest(INGEST / "export.json", runner=runner, today=TODAY, log=lambda s: None, **tree)
    assert len(tomllib.loads(tree["learned_toml"].read_text())["idiom"]) == 2
    assert _exercise(tree, "python", "t.paren", "0001")["alternates"].count("dib") == 1
    assert (tree["review_dir"] / "emulator-divergences.md").read_text().count("py/t.quote/0001") == 1
    assert (tree["review_dir"] / "wording-queue.md").read_text().count("say which lines") == 1
    assert (tree["review_dir"] / "ingest-log.md").read_text().count("## 2026-10-12") == 2


@needs_nvim
def test_ingest_rejected_idiom_is_not_appended_again(tree, runner, tmp_path):
    rejected = '\n[[idiom]]\nskill = "o.delete"\nkeys = "{{k}}dd"\nstatus = "rejected"\n'
    tree["learned_toml"].write_text(rejected)
    export = tmp_path / "export.json"
    export.write_text(json.dumps([{"ex": "py/o.delete/0001", "ok": True, "seq": "3dd", "beatPar": True}]))
    (line,) = ingest.ingest(export, runner=runner, today=TODAY, log=lambda s: None, **tree)
    assert "already known" in line
    assert _exercise(tree, "python", "o.delete", "0001")["par"]["keys"] == "3dd"
    assert tree["learned_toml"].read_text() == rejected


def test_ingest_wording_only_needs_no_nvim(tree, tmp_path):
    export = tmp_path / "export.json"
    export.write_text(json.dumps([{"ex": "py/o.delete/0001", "ok": True, "seq": "dddddd",
                                   "flag": {"reason": "wording", "note": "unclear"}}]))
    lines = ingest.ingest(export, runner=lambda jobs: pytest.fail("no replay expected"), today=TODAY,
                          log=lambda s: None, **tree)
    assert lines == ["- `py/o.delete/0001`: wording flag -> wording-queue.md"]
    assert "unclear" in (tree["review_dir"] / "wording-queue.md").read_text()
