"""Shared vectors in model/vectors/*.json: outputs must match, and the files must be current."""

import json
import sys
from pathlib import Path

import pytest

from vimtrainer_model.vectors import compare, run_vector

MODEL_DIR = Path(__file__).resolve().parent.parent
VECTOR_FILES = sorted((MODEL_DIR / "vectors").glob("*.json"))


def test_vectors_at_least_twelve():
    assert len(VECTOR_FILES) >= 12


@pytest.mark.parametrize("path", VECTOR_FILES, ids=lambda p: p.stem)
def test_run_vector_matches_expectations(path, graph):
    vector = json.loads(path.read_text())
    outputs = run_vector(vector, graph)
    problems = []
    for position, (op, output) in enumerate(zip(vector["ops"], outputs)):
        if "expect" in op:
            problems += compare(op["expect"], output, f"ops[{position}].{op['op']}")
    assert not problems, "\n".join(problems[:20])


def test_vectors_are_up_to_date(graph):
    sys.path.insert(0, str(MODEL_DIR))
    import gen_vectors

    for name, vector in gen_vectors.scenarios(graph).items():
        stored = json.loads((MODEL_DIR / "vectors" / f"{name}.json").read_text())
        expected_ops = [{k: v for k, v in op.items() if k != "expect"} for op in stored["ops"]]
        assert json.loads(json.dumps(vector["ops"])) == expected_ops, f"{name}: rerun model/gen_vectors.py"
