"""Shared vectors, generated into a temporary directory: they replay cleanly, and generation is deterministic.

The vectors' ``expect`` values come from this same Python model, so replaying them here is a
self-consistency smoke check, not a drift check. The real cross-check is the TypeScript
mirror (app/src/model/model.test.ts), which replays the copy ``make vectors`` writes.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vimtrainer_model.graph import load_graph
from vimtrainer_model.vectors import compare, run_vector

MODEL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODEL_DIR))
import gen_vectors  # noqa: E402

SCENARIO_NAMES = sorted(gen_vectors.scenarios(load_graph()))


def test_vectors_at_least_twelve(vector_dir):
    assert len(list(vector_dir.glob("*.json"))) >= 12


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_vector_replays_self_consistently(name, vector_dir, graph):
    """Smoke check: each generated vector loads, replays and compares against its own ``expect``."""
    vector = json.loads((vector_dir / f"{name}.json").read_text())
    outputs = run_vector(vector, graph)
    problems = []
    for position, (op, output) in enumerate(zip(vector["ops"], outputs)):
        if "expect" in op:
            problems += compare(op["expect"], output, f"ops[{position}].{op['op']}")
    assert not problems, "\n".join(problems[:20])


def test_generation_is_deterministic(vector_dir, tmp_path):
    """A second generation in a fresh process, with another hash seed, writes identical bytes."""
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    subprocess.run([sys.executable, "gen_vectors.py", "--out", str(tmp_path)], cwd=MODEL_DIR, env=env,
                   check=True, capture_output=True)
    first = {p.name: p.read_bytes() for p in sorted(vector_dir.glob("*.json"))}
    second = {p.name: p.read_bytes() for p in sorted(tmp_path.glob("*.json"))}
    assert first.keys() == second.keys()
    differing = [name for name in first if first[name] != second[name]]
    assert not differing, f"two runs of gen_vectors.py differ in {differing}"
