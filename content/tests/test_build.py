"""End-to-end build on the fixture source, plus the review CLI."""

import json
import re
import shutil

import pytest

from conftest import FIXTURES
from vimtrainer_content import build, review


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("b") / "build"
    report = build.build(out=out, cap=3, workers=2, sources_toml=FIXTURES / "sources.toml", log=lambda *_: None)
    return out, report


@pytest.fixture(scope="module")
def built_js(tmp_path_factory):
    """A cap-3 build of the JavaScript and TypeScript fixtures in test_js.py, as local sources."""
    from test_js import INVENTORY_JS, INVENTORY_TS

    root = tmp_path_factory.mktemp("js")
    (root / "src").mkdir()
    shutil.copy(FIXTURES / "LICENSE", root / "LICENSE")
    (root / "src" / "inventory.js").write_text(INVENTORY_JS)
    (root / "src" / "inventory.ts").write_text(INVENTORY_TS)
    toml = root / "sources.toml"
    toml.write_text("".join(
        f'[[source]]\nname = "fixture-{ext}"\nlang = "{lang}"\nrepo = "fixture/inventory-{ext}"\n'
        f'license = "MIT"\nlocal = "."\ninclude = ["src/*.{ext}"]\n\n'
        for lang, ext in (("javascript", "js"), ("typescript", "ts"))))
    out = root / "build"
    report = build.build(out=out, cap=3, workers=2, sources_toml=toml, log=lambda *_: None)
    return out, report


def test_build_layout(built):
    out, _ = built
    for rel in ("index.json", "ATTRIBUTION.md", "supported_commands.md", "stats/node_frequency.json",
                "stats/gates.json"):
        assert (out / rel).is_file(), rel
    assert list((out / "exercises" / "python").glob("*/*.json"))


def test_index_matches_files(built):
    out, report = built
    index = json.loads((out / "index.json").read_text())
    skills = index["langs"]["python"]["skills"]
    for skill, entry in skills.items():
        assert entry["count"] == len(entry["ids"]) == report.counts["python"][skill]
        assert entry["thin"] is (entry["count"] < 20)
        for ex_id in entry["ids"]:
            path = out / "exercises" / "python" / skill / f"{ex_id.rsplit('/', 1)[1]}.json"
            ex = json.loads(path.read_text())
            assert ex["id"] == ex_id
            assert ex["par"]["verified"].startswith("nvim ")
            assert ex["source"]["license"] == "MIT"


def test_exercise_schema(built):
    out, _ = built
    for path in (out / "exercises").glob("*/*/*.json"):
        ex = json.loads(path.read_text())
        assert {"id", "skill", "lang", "kind", "task", "start", "expect", "par", "alternates", "hints", "tags",
                "source", "emulator", "target", "template"} <= set(ex)
        assert ("cursor" in ex["expect"]) is (ex["kind"] == "cursor")
        for hint in ex["hints"]:
            assert set(hint) == {"trigger", "text"}
            assert not hint["trigger"] or not re.search(hint["trigger"], ex["par"]["keys"])  # at par: no hint


def test_attribution_and_frequency(built):
    out, _ = built
    text = (out / "ATTRIBUTION.md").read_text()
    assert "fixture/inventory" in text and "Permission is hereby granted" in text
    freq = json.loads((out / "stats" / "node_frequency.json").read_text())
    assert freq["python"]["mapped"]["string"] > 0


def test_build_refuses_to_wipe_non_build_dir(tmp_path):
    (tmp_path / "precious.txt").write_text("x")
    with pytest.raises(RuntimeError, match="refusing"):
        build.build(out=tmp_path, sources_toml=FIXTURES / "sources.toml", log=lambda *_: None)


def test_review_accept_reject_quit(built, tmp_path):
    out, _ = built
    answers = iter(["a", "r", "q"])
    shown = []
    reviewed, rejected = tmp_path / "reviewed.txt", tmp_path / "rejected.txt"
    acc, rej = review.review(out, ask=lambda _: next(answers), echo=shown.append,
                             reviewed_txt=reviewed, rejected_txt=rejected)
    assert (acc, rej) == (1, 1)
    assert len(reviewed.read_text().split()) == 1 and len(rejected.read_text().split()) == 1
    assert any("-- canonical:" in s for s in shown)


def test_render_shows_cursor_and_target(built):
    out, _ = built
    ex = next(review.iter_exercises(out))
    text = review.render(ex)
    assert "^" in text and ex["par"]["keys"] in text


@pytest.mark.parametrize("which", ["built", "built_js"])
def test_hint_triggers_compile_in_python_and_javascript(which, request):
    import subprocess

    out, _ = request.getfixturevalue(which)
    triggers = sorted({h["trigger"] for p in (out / "exercises").glob("*/*/*.json")
                       for h in json.loads(p.read_text())["hints"] if h["trigger"]})
    assert triggers
    for t in triggers:
        re.compile(t)
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not installed")
    script = "const ts = JSON.parse(require('fs').readFileSync(0, 'utf8')); for (const t of ts) new RegExp(t, 'u');"
    subprocess.run([node, "-e", script], input=json.dumps(triggers), text=True, check=True)


def test_cpp_is_wired_into_the_build():
    from vimtrainer_content.lang import cpp

    spec = build.LANGS["cpp"]
    assert spec.lang is cpp.LANG
    assert (spec.windows, spec.frequency, spec.generate) == (cpp.windows, cpp.node_frequency, cpp.generate)
    assert spec.skills == cpp.TARGET_SKILLS
    assert "t.angle" not in build.LANGS["python"].skills


def test_js_is_wired_into_the_build():
    from vimtrainer_content.lang import js

    js_spec, ts_spec = build.LANGS["javascript"], build.LANGS["typescript"]
    assert js_spec.lang is js.LANG_JS and ts_spec.lang is js.LANG_TS
    assert (js_spec.windows, js_spec.frequency, js_spec.generate) == (js.windows_js, js.node_frequency_js, js.generate)
    assert (ts_spec.windows, ts_spec.frequency, ts_spec.generate) == (js.windows_ts, js.node_frequency_ts, js.generate)
    assert js_spec.skills == js.JS_TARGET_SKILLS and ts_spec.skills == js.TS_TARGET_SKILLS
    assert "t.angle" not in js_spec.skills and "t.angle" in ts_spec.skills


def test_js_and_ts_fixtures_build_end_to_end(built_js):
    out, report = built_js
    index = json.loads((out / "index.json").read_text())
    for lang, short in (("javascript", "js"), ("typescript", "ts")):
        skills = index["langs"][lang]["skills"]
        assert sum(e["count"] for e in skills.values()) == sum(report.counts[lang].values()) > 0
        for path in (out / "exercises" / lang).glob("*/*.json"):
            ex = json.loads(path.read_text())
            assert ex["lang"] == lang and ex["id"].startswith(f"{short}/")
    assert "fixture/inventory-ts" in (out / "ATTRIBUTION.md").read_text()


def test_quality_gate_counts_rejected_windows_and_their_drafts_per_skill():
    from test_snippets import CPP_CODE, CPP_HEADER

    from vimtrainer_content.lang import cpp

    source = {"repo": "fixture/q", "path": "q.h", "commit": None, "license": "MIT"}
    spec = build.LANGS["cpp"]
    wins = [w for text in (CPP_HEADER, CPP_CODE) for w in cpp.windows(text, source)]
    report = build.Report()
    kept = build._quality_windows(wins, spec, spec.skills, report)
    assert [w.lines[0] for w in kept] == ["namespace darts {"]
    assert report.rejections[("snippet-window", "-", "declaration-only")] == 1
    lost = {k: n for k, n in report.rejections.items() if k[0] == "snippet"}
    expected = {}
    for d in cpp.generate(wins[0]):
        expected[("snippet", d.skill, d.template)] = expected.get(("snippet", d.skill, d.template), 0) + 1
    assert lost == expected and lost
