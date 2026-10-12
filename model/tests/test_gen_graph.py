"""Tests for model/gen_graph.py and the generated skill-graph.json."""

import json
import sys
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODEL_DIR))

import gen_graph  # noqa: E402


def test_build_graph_matches_committed_file():
    built = gen_graph.build_graph(gen_graph.DOC.read_text(), json.loads(gen_graph.TIPS.read_text()))
    assert json.loads((MODEL_DIR / "skill-graph.json").read_text()) == json.loads(json.dumps(built))


def test_app_copy_is_identical():
    app_copy = MODEL_DIR.parent / "app" / "src" / "model" / "skill-graph.json"
    assert app_copy.read_text() == (MODEL_DIR / "skill-graph.json").read_text()


def test_graph_shape(graph):
    skills = graph["skills"]
    assert len(skills) == 93
    assert skills["o.delete"]["prereqs"] == ["m.word", "m.line"]
    assert skills["x.lastsearch"]["prereqs"] == ["x.subst", "o.dot"]
    assert set(skills["t.compose"]["prereqs"]) == {s for s, n in skills.items() if n["tier"] == 4} - {"t.compose"}
    assert all(n["targetBase"] == 1200 and n["perKey"] == 180 for n in skills.values())


def test_emulator_flags(graph):
    skills = graph["skills"]
    assert skills["o.filter"]["emulator"]["vscodevim"] == "none"
    assert skills["o.filter"]["emulator"]["ideavim"] == "verify"
    assert skills["x.global"]["emulator"]["vscodevim"] == "partial"
    assert skills["x.global"]["emulator"]["ideavim"] == "full"
    assert skills["nv.lsp"]["emulator"]["vscodevim"] == "none"


def test_lang_weights(graph):
    skills = graph["skills"]
    assert skills["t.angle"]["langWeights"]["python"] == 0
    assert skills["t.angle"]["langWeights"]["typescript"] == 1.0
    assert skills["m.match"]["langWeights"]["markdown"] == 0.2
    assert skills["o.indent"]["langWeights"]["go"] == 0.5
    assert skills["nv.comment"]["langWeights"]["markdown"] == 0
    assert skills["f.hjkl"]["langWeights"]["cpp"] == 1.0


def test_tips_cover_at_least_fifteen_skills(graph):
    assert len(graph["tips"]) >= 15
    assert set(graph["tips"]) <= set(graph["skills"])
