"""Shared test-vector runner: the TypeScript test runs the same ops and compares results.

A vector is ``{"name", "description", "graph"?, "profile"?, "index"?, "ops": [...]}``.
Each op has an ``op`` name (camelCase, as in TypeScript) and inputs; ops that produce
output carry the expected value in ``expect``. ``graph`` replaces model/skill-graph.json
for that vector; ``profile`` is ``{"profile", "extraTiers"}`` passed to ``apply_profile``.

Ops: applyAttempt{record}, applyPlacement{records}, chooseFocus{lang, now, seed?},
chooseWarmup{lang}, chooseExercise{skill, lang, seed, useGraph?}, projection{skill, lang},
sessionSummary{since}, diagnose{skill, lang}, digest{}, rebuildMatches{}, rng{seed, count},
deriveSeed{n, now}.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> run_vector({"ops": [{"op": "deriveSeed", "n": 0, "now": 5}]}, load_graph())
[5]
"""

from __future__ import annotations

import math

from vimtrainer_model.attempt import apply_attempt, rebuild
from vimtrainer_model.graph import apply_profile
from vimtrainer_model.placement import apply_placement
from vimtrainer_model.projection import projection
from vimtrainer_model.rng import Mulberry32, derive_seed
from vimtrainer_model.selection import choose_exercise, choose_focus, choose_warmup
from vimtrainer_model.state import diagnose, new_state
from vimtrainer_model.summary import session_summary

DIGEST_TAIL = 5
REL_TOL = 1e-9


# Public Functions =================================================================================

def vector_graph(vector: dict, default_graph: dict) -> dict:
    """The graph a vector runs against."""
    graph = vector.get("graph") or default_graph
    profile = vector.get("profile")
    if profile:
        graph = apply_profile(graph, profile.get("profile", "neovim"), tuple(profile.get("extraTiers", [])))
    return graph


def run_vector(vector: dict, default_graph: dict) -> list:
    """Run every op; return one output per op (None for state-changing ops)."""
    graph = vector_graph(vector, default_graph)
    index = vector.get("index") or {}
    state = new_state(graph)
    outputs: list = []
    for op in vector["ops"]:
        state, output = _run_op(op, state, graph, index)
        outputs.append(output)
    return outputs


def digest(state: dict) -> dict:
    """Comparable summary of a state: every touched skill state plus list tails."""
    skills = {}
    for skill_id, langs in state["skills"].items():
        kept = {lang: dict(st) for lang, st in langs.items() if st["status"] != "locked" or st["n"] > 0}
        if kept:
            skills[skill_id] = kept
    return {
        "skills": skills,
        "logLen": len(state["log"]),
        "recentLen": len(state["recent"]),
        "recentTail": state["recent"][-DIGEST_TAIL:],
        "focusTail": state["focusHistory"][-DIGEST_TAIL:],
    }


def compare(expected, actual, path: str = "$") -> list[str]:
    """Structural comparison with a relative float tolerance; returns mismatch messages."""
    if isinstance(expected, bool) or isinstance(actual, bool) or expected is None or actual is None:
        return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        scale = max(1.0, abs(expected), abs(actual))
        return [] if math.isclose(expected, actual, rel_tol=0, abs_tol=REL_TOL * scale) else [
            f"{path}: expected {expected!r}, got {actual!r}"
        ]
    if isinstance(expected, dict) and isinstance(actual, dict):
        problems = [f"{path}: key sets differ {sorted(set(expected) ^ set(actual))}"] if set(expected) != set(actual) else []
        for key in expected.keys() & actual.keys():
            problems += compare(expected[key], actual[key], f"{path}.{key}")
        return problems
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: length {len(expected)} != {len(actual)}"]
        problems = []
        for position, (left, right) in enumerate(zip(expected, actual)):
            problems += compare(left, right, f"{path}[{position}]")
        return problems
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


# Private Functions ================================================================================

def _run_op(op: dict, state: dict, graph: dict, index: dict) -> tuple[dict, object]:
    """Execute one op; return the (possibly new) state and the op's output."""
    kind = op["op"]
    if kind == "applyAttempt":
        return apply_attempt(state, op["record"], graph), None
    if kind == "applyPlacement":
        return apply_placement(state, op["records"], graph), None
    if kind == "chooseFocus":
        return state, choose_focus(state, op["lang"], graph, op["now"], op.get("seed"))
    if kind == "chooseWarmup":
        return state, choose_warmup(state, op["lang"], graph)
    if kind == "chooseExercise":
        use_graph = graph if op.get("useGraph", True) else None
        return state, choose_exercise(state, op["skill"], op["lang"], index, op["seed"], use_graph)
    if kind == "projection":
        return state, projection(state, op["skill"], op["lang"], graph)
    if kind == "sessionSummary":
        return state, session_summary(state, op["since"], graph)
    if kind == "diagnose":
        return state, diagnose(state, op["skill"], op["lang"], graph)
    if kind == "digest":
        return state, digest(state)
    if kind == "rebuildMatches":
        return state, not compare(digest(state), digest(rebuild(state["log"], graph)))
    if kind == "rng":
        rng = Mulberry32(op["seed"])
        return state, [rng.next() for _ in range(op["count"])]
    if kind == "deriveSeed":
        return state, derive_seed(op["n"], op["now"])
    raise ValueError(f"unknown op {kind!r}")
