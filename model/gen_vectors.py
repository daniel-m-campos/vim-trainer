"""Generate model/vectors/*.json: shared scenarios whose expected outputs come from Python.

Each scenario lists ops (see vimtrainer_model.vectors); this script runs them through the
Python model and stores every output as ``expect``. pytest re-runs the ops and compares;
app/src/model/model.test.ts runs the same ops through the TypeScript mirror.

Example
-------
    uv run --project model python model/gen_vectors.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Final

from vimtrainer_model import Mulberry32, apply_attempt, choose_exercise, choose_focus, load_graph, new_state
from vimtrainer_model.vectors import run_vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate  # noqa: E402

OUT_DIR: Final = Path(__file__).resolve().parent / "vectors"
T0: Final = 1760200000
DAY: Final = 86400
PY: Final = "python"


# Public Functions =================================================================================

def rec(t: float, skill: str, ok: bool = True, ms: float = 2000, keys: int = 6, par: int = 6,
        ex: str | None = None, lang: str = PY, hint: bool = False, retry: bool = False, undo: int = 0) -> dict:
    """An AttemptRecord with sensible defaults (6-key par, 2000 ms is under the 2280 ms target)."""
    return {"t": t, "ex": ex or f"{lang[:2]}/{skill}/{int(t) % 10000:04d}", "skill": skill, "lang": lang,
            "ok": ok, "ms": ms, "keys": keys, "par": par, "hint": hint, "retry": retry, "undo": undo}


def attempts(skill: str, count: int, start: float, step: float = 30, **fields) -> list[dict]:
    """``count`` applyAttempt ops on one skill, ``step`` seconds apart."""
    return [{"op": "applyAttempt", "record": rec(start + i * step, skill, **fields)} for i in range(count)]


def seed_with_roll(below: bool, start: int = 0) -> int:
    """First seed whose first Mulberry32 draw is below (or not below) 0.2."""
    seed = start
    while (Mulberry32(seed).next() < 0.2) != below:
        seed += 1
    return seed


def scenarios(graph: dict) -> dict[str, dict]:
    """All scenarios by file name."""
    builders = [
        _rng_and_seeds, _fresh_state, _mastery_and_unlock, _interleave_streak, _fast_sloppy_gate,
        _accuracy_gate, _slow_precise_gate, _retry_hint_not_counted, _review_pass_cycle, _review_fail_drop,
        _introduced_pull_in, _placement_advanced, _placement_switcher, _composite_credit_and_choice,
        _exercise_recent_and_weights, _projection_fits, _cross_language, _profile_vscodevim,
        _simulated_fast_sloppy, _simulated_quitter, _forced_locked_skill, _placement_hinted,
        _cross_language_after_placement, _share_cap, _starvation_guard,
    ]
    result = {}
    for position, build in enumerate(builders, start=1):
        vector = build(graph)
        name = build.__name__.lstrip("_")
        result[f"{position:02d}_{name}"] = {"name": name, **vector}
    return result


def main():
    """Write every scenario with its expected outputs."""
    graph = load_graph()
    OUT_DIR.mkdir(exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()
    for file_name, vector in scenarios(graph).items():
        outputs = run_vector(vector, graph)
        for op, output in zip(vector["ops"], outputs):
            if output is not None or _has_output(op):
                op["expect"] = output
        (OUT_DIR / f"{file_name}.json").write_text(json.dumps(vector, indent=1, ensure_ascii=True) + "\n")
        print(f"wrote vectors/{file_name}.json ({len(vector['ops'])} ops)", file=sys.stderr)


# Scenarios ========================================================================================

def _rng_and_seeds(graph: dict) -> dict:
    ops = [{"op": "rng", "seed": seed, "count": 6} for seed in (0, 1, 42, 2**31, 2**32 - 1)]
    ops += [{"op": "deriveSeed", "n": n, "now": now} for n, now in
            ((0, 0), (7, T0), (123456, T0 + 0.75), (10**7, 5), (2**31, 2**32 + 9))]
    return {"description": "Mulberry32 draws and derived seeds are bit-identical.", "ops": ops}


def _fresh_state(graph: dict) -> dict:
    ops = [{"op": "chooseFocus", "lang": PY, "now": T0, "seed": s} for s in (None, 0, 1, 2)]
    ops += [
        {"op": "chooseWarmup", "lang": PY},
        {"op": "projection", "skill": "f.hjkl", "lang": PY},
        {"op": "sessionSummary", "since": 0},
        {"op": "diagnose", "skill": "t.quote", "lang": PY},
        {"op": "digest"},
    ]
    return {"description": "New state: tier 0 active (lazily), focus is the first tier-0 skill.", "ops": ops}


def _mastery_and_unlock(graph: dict) -> dict:
    ops = attempts("f.hjkl", 7, T0)
    ops += [{"op": "digest"}, {"op": "diagnose", "skill": "f.hjkl", "lang": PY}]
    ops += attempts("f.hjkl", 3, T0 + 300)
    ops += [
        {"op": "digest"},
        {"op": "diagnose", "skill": "f.hjkl", "lang": PY},
        {"op": "chooseFocus", "lang": PY, "now": T0 + 400, "seed": 5},
        {"op": "chooseWarmup", "lang": PY},
        {"op": "sessionSummary", "since": T0},
        {"op": "rebuildMatches"},
    ]
    return {"description": "8 at-target attempts master f.hjkl (n gate), unlocking m.word, m.line, m.file.", "ops": ops}


def _interleave_streak(graph: dict) -> dict:
    ops = []
    for position, skill in enumerate(("f.hjkl", "f.undo", "f.xdd", "f.save")):
        ops += attempts(skill, 1, T0 + position * 30, ms=3000, keys=6, par=6)
    ops += attempts("f.modes", 3, T0 + 200, ms=6000)
    ops.append({"op": "chooseFocus", "lang": PY, "now": T0 + 300, "seed": 7})
    ops += attempts("f.hjkl", 1, T0 + 320, ms=3000)
    ops.append({"op": "chooseFocus", "lang": PY, "now": T0 + 400, "seed": 7})
    ops.append({"op": "digest"})
    return {"description": "Same skill 3 times in a row is skipped on the 4th pick.", "ops": ops}


def _fast_sloppy_gate(graph: dict) -> dict:
    ops = attempts("f.xdd", 12, T0, ms=1500, keys=13, par=6)
    ops += [{"op": "diagnose", "skill": "f.xdd", "lang": PY}, {"op": "digest"}]
    return {"description": "Fast but 2x par: confidence halves, efficiency gate blocks mastery.", "ops": ops}


def _accuracy_gate(graph: dict) -> dict:
    ops = []
    for i in range(12):
        ops += attempts("f.undo", 1, T0 + i * 30, ok=i % 4 != 3, ms=1800, keys=4, par=4)
    ops += [{"op": "diagnose", "skill": "f.undo", "lang": PY}, {"op": "digest"}]
    return {"description": "Fast and at par but 3/12 give-ups: accuracy gate blocks mastery.", "ops": ops}


def _slow_precise_gate(graph: dict) -> dict:
    ops = attempts("f.save", 10, T0, ms=5000, keys=4, par=4)
    ops += [{"op": "diagnose", "skill": "f.save", "lang": PY}, {"op": "projection", "skill": "f.save", "lang": PY},
            {"op": "digest"}]
    return {"description": "At par, never wrong, but twice the target time: speed gate.", "ops": ops}


def _retry_hint_not_counted(graph: dict) -> dict:
    ops = attempts("f.modes", 2, T0)
    ops += attempts("f.modes", 2, T0 + 100, retry=True, ms=500)
    ops += attempts("f.modes", 2, T0 + 200, hint=True, ok=False)
    ops += [{"op": "digest"}, {"op": "rebuildMatches"}]
    return {"description": "Retries and hinted attempts are logged but leave the skill unchanged.", "ops": ops}


def _review_pass_cycle(graph: dict) -> dict:
    review_seed = seed_with_roll(True)
    normal_seed = seed_with_roll(False)
    ops = attempts("f.save", 8, T0, keys=4, par=4, ms=1500)
    ops.append({"op": "digest"})
    t = T0 + DAY + 600
    ops += [{"op": "chooseFocus", "lang": PY, "now": t, "seed": review_seed},
            {"op": "chooseFocus", "lang": PY, "now": t, "seed": normal_seed}]
    ops += attempts("f.save", 1, t, keys=4, par=4, ms=1500)
    ops.append({"op": "digest"})
    t += 2 * DAY + 600
    ops.append({"op": "chooseFocus", "lang": PY, "now": t, "seed": review_seed})
    ops += attempts("f.save", 1, t, keys=5, par=4, ms=2400)
    ops += [{"op": "digest"}, {"op": "sessionSummary", "since": T0 + DAY}, {"op": "rebuildMatches"}]
    return {"description": "Due review wins the 0.2 slot; passes double the interval (1, 2, 4 days).", "ops": ops}


def _review_fail_drop(graph: dict) -> dict:
    ops = attempts("f.save", 8, T0, keys=4, par=4, ms=1500)
    t = T0 + DAY + 600
    ops += attempts("f.save", 1, t, keys=4, par=4, ms=4000)
    ops += [{"op": "digest"}, {"op": "diagnose", "skill": "f.save", "lang": PY},
            {"op": "chooseFocus", "lang": PY, "now": t + 60, "seed": seed_with_roll(False)}]
    ops += attempts("f.save", 6, t + 120, keys=4, par=4, ms=1500)
    ops += [{"op": "digest"}, {"op": "rebuildMatches"}]
    return {"description": "A slow review fails: back to active, interval reset, confidence x0.8.", "ops": ops}


def _introduced_pull_in(graph: dict) -> dict:
    mini = _mini_graph({
        "a0": (0, []), "b1": (1, ["a0"]), "c1": (1, ["a0"]), "d1": (1, ["b1"]), "e1": (1, ["b1", "c1"]),
        "f2": (2, ["e1"]), "g2": (2, ["a0"]),
    })
    ops = [{"op": "chooseFocus", "lang": PY, "now": T0, "seed": 1}]
    ops += attempts("a0", 1, T0)
    ops.append({"op": "digest"})
    ops += attempts("b1", 9, T0 + 100)
    ops += [{"op": "digest"}, {"op": "chooseFocus", "lang": PY, "now": T0 + 1000, "seed": 1},
            {"op": "sessionSummary", "since": T0 + 100}]
    return {"description": "Fewer than 4 active and nothing unlockable: lowest-prerequisite skills are introduced.",
            "graph": mini, "ops": ops}


def _placement_advanced(graph: dict) -> dict:
    learner = simulate.LEARNERS["plateaued_expert"]
    records = simulate.placement_records(learner, random.Random(11), Counter(), graph, T0)
    ops = [{"op": "applyPlacement", "records": records}, {"op": "digest"}]
    ops += [{"op": "chooseFocus", "lang": PY, "now": T0 + 600, "seed": s} for s in range(4)]
    ops += [{"op": "sessionSummary", "since": T0}, {"op": "rebuildMatches"}]
    return {"description": "Advanced placement: passes through tier 7 infer prerequisites and tier 0 mastered.",
            "ops": ops}


def _placement_switcher(graph: dict) -> dict:
    learner = simulate.Learner("switcher", "", 5, 1.3, 1.0, 10, 1.2, 1.0, 0.0, 1, 1, placement_tiers=1)
    records = simulate.placement_records(learner, random.Random(12), Counter(), graph, T0)
    ops = [{"op": "applyPlacement", "records": records}, {"op": "digest"},
           {"op": "chooseFocus", "lang": PY, "now": T0 + 600, "seed": 3}]
    ops += attempts("m.word", 3, T0 + 700, keys=3, par=3, ms=1600)
    ops += [{"op": "digest"}, {"op": "rebuildMatches"}]
    return {"description": "Switcher placement: tier 1 passes, everything else failed.", "ops": ops}


def _composite_credit_and_choice(graph: dict) -> dict:
    index = {"langs": {PY: {"m.word": {"ids": [
        "py/m.word/0001", "py/m.word/0002", "py/m.word/0003",
        {"id": "py/comp/0001", "skills": ["m.word", "f.hjkl"]},
        {"id": "py/comp/0002", "skills": ["m.word", "f.modes"]},
        {"id": "py/comp/0003", "skills": ["m.word", "t.quote"]},
    ]}}}}
    ops = attempts("f.hjkl", 8, T0) + attempts("f.modes", 8, T0 + 300)
    ops += [{"op": "chooseExercise", "skill": "m.word", "lang": PY, "seed": s} for s in range(16)]
    ops.append({"op": "applyAttempt", "record": rec(T0 + 900, "m.word+f.hjkl", ex="py/comp/0001", keys=8, par=7)})
    ops += [{"op": "digest"}, {"op": "projection", "skill": "f.hjkl", "lang": PY}, {"op": "rebuildMatches"}]
    return {"description": "Composites are drawn ~1 in 5 once 2 skills exceed 0.8, and credit every tagged skill.",
            "index": index, "ops": ops}


def _exercise_recent_and_weights(graph: dict) -> dict:
    ids = [f"py/t.paren/{i:04d}" for i in range(1, 6)]
    index = {PY: {"t.paren": ids + [{"id": "py/t.paren+t.angle/0001", "skills": ["t.paren", "t.angle"]}]}}
    ops = [{"op": "chooseExercise", "skill": "t.paren", "lang": PY, "seed": s} for s in range(6)]
    ops += [{"op": "chooseExercise", "skill": "t.paren", "lang": PY, "seed": s, "useGraph": False} for s in range(6)]
    for i, ex in enumerate(ids[:4]):
        ops.append({"op": "applyAttempt", "record": rec(T0 + i * 30, "t.paren", ex=ex)})
    ops += [{"op": "chooseExercise", "skill": "t.paren", "lang": PY, "seed": s} for s in range(3)]
    ops.append({"op": "applyAttempt", "record": rec(T0 + 200, "t.paren", ex=ids[4])})
    ops += [{"op": "chooseExercise", "skill": "t.paren", "lang": PY, "seed": s} for s in range(3)]
    ops += [{"op": "chooseExercise", "skill": "t.paren", "lang": "lua", "seed": 1},
            {"op": "chooseExercise", "skill": "t.quote", "lang": PY, "seed": 1}]
    return {"description": "Recent ids are avoided, weight-0 tags (t.angle in Python) are never drawn, "
                           "and an exhausted pool returns the least recently seen.", "index": index, "ops": ops}


def _projection_fits(graph: dict) -> dict:
    ops = []
    for i in range(10):
        ops += attempts("f.undo", 1, T0 + i * 30, ms=6000 - 250 * i, keys=4, par=4)
    ops.append({"op": "projection", "skill": "f.undo", "lang": PY})
    noisy = [3000, 5200, 2800, 5100, 3100, 4900]
    for i, ms in enumerate(noisy):
        ops += attempts("f.xdd", 1, T0 + 1000 + i * 30, ms=ms, keys=3, par=3)
    ops.append({"op": "projection", "skill": "f.xdd", "lang": PY})
    for i in range(20):
        ops += attempts("f.modes", 1, T0 + 2000 + i * 30, ms=5000 - 160 * i + i * i, keys=3, par=3)
    ops += [{"op": "projection", "skill": "f.modes", "lang": PY}, {"op": "digest"}]
    return {"description": "Linear fit with a crossing, noisy data hidden (R^2 < 0.5), quadratic at n >= 15.",
            "ops": ops}


def _cross_language(graph: dict) -> dict:
    ops = attempts("f.hjkl", 8, T0)
    ops += [{"op": "chooseFocus", "lang": "cpp", "now": T0 + 600, "seed": 2},
            {"op": "applyAttempt", "record": rec(T0 + 700, "m.word", lang="cpp", ms=3000)},
            {"op": "digest"}, {"op": "sessionSummary", "since": T0 + 650}]
    return {"description": "Unlocking uses the max across languages; confidence is per language.", "ops": ops}


def _forced_locked_skill(graph: dict) -> dict:
    ops = attempts("o.change", 15, T0, ms=1500)
    ops += [{"op": "digest"}, {"op": "chooseFocus", "lang": PY, "now": T0 + 900, "seed": 3},
            {"op": "rebuildMatches"}]
    return {"description": "A locked skill forced from the stats screen becomes active on its first counted "
                           "attempt and can be mastered.", "ops": ops}


def _placement_hinted(graph: dict) -> dict:
    records = [rec(T0, "t.quote", keys=12, par=12, ms=3000, hint=True),
               rec(T0 + 60, "m.word", keys=3, par=3, ms=1500),
               rec(T0 + 120, "o.delete", keys=3, par=3, ms=1500, retry=True)]
    ops = [{"op": "applyPlacement", "records": records}, {"op": "digest"}, {"op": "rebuildMatches"}]
    return {"description": "Hinted and retried placement records are logged only: no stats, no pass, "
                           "no propagation to prerequisites.", "ops": ops}


def _cross_language_after_placement(graph: dict) -> dict:
    learner = simulate.LEARNERS["plateaued_expert"]
    records = simulate.placement_records(learner, random.Random(11), Counter(), graph, T0)
    ops = [{"op": "applyPlacement", "records": records},
           {"op": "applyAttempt", "record": rec(T0 + 700, "f.hjkl", lang="cpp", ms=1500)},
           {"op": "digest"}, {"op": "sessionSummary", "since": T0 + 650}]
    ops += [{"op": "chooseFocus", "lang": "cpp", "now": T0 + 800, "seed": s} for s in range(4)]
    return {"description": "A new language: skills mastered elsewhere start mastered with a review due, and "
                           "carried-over active skills respect the 4-7 active target.", "ops": ops}


def _share_cap(graph: dict) -> dict:
    setup = []
    for position, skill in enumerate(("f.modes", "f.hjkl", "f.undo", "f.save")):
        setup += attempts(skill, 1, T0 + position * 30)
    setup += attempts("f.xdd", 1, T0 + 150, ms=6000, keys=13, par=6)
    ops = _driven(graph, setup, 30, T0 + 300, lambda skill, t: rec(t, skill, ms=6000, keys=13, par=6)
                   if skill == "f.xdd" else rec(t, skill))
    ops.append({"op": "digest"})
    return {"description": "f.xdd stays far weaker than the rest, yet takes at most 4 of any 10 consecutive "
                           "picks (share cap); the other picks spread over the next-weakest skills.",
            "ops": ops}


def _starvation_guard(graph: dict) -> dict:
    mini = _mini_graph({"a0": (0, []), "b0": (0, []), "c0": (0, []), "d0": (0, [])}, {"d0": {PY: 0.2}})
    ops = _driven(mini, [], 36, T0, lambda skill, t: rec(t, skill, ms=6000))
    ops.append({"op": "digest"})
    return {"description": "d0 has Python weight 0.2, so its weighted confidence is never among the 3 weakest; "
                           "the starvation guard still picks it at least once in every 12 picks.",
            "graph": mini, "ops": ops}


def _profile_vscodevim(graph: dict) -> dict:
    ops = attempts("f.save", 8, T0, keys=4, par=4, ms=1500)
    ops.append({"op": "digest"})
    ops += attempts("f.modes", 8, T0 + 300)
    ops += [{"op": "digest"}, {"op": "chooseFocus", "lang": PY, "now": T0 + 900, "seed": 4}]
    return {"description": "VSCodeVim profile with tier 11 on: w.split unlocks from f.save, w.args stays disabled.",
            "profile": {"profile": "vscodevim", "extraTiers": [11]}, "ops": ops}


def _simulated_fast_sloppy(graph: dict) -> dict:
    return _simulated(graph, simulate.LEARNERS["fast_sloppy"], days=3, per_session=25)


def _simulated_quitter(graph: dict) -> dict:
    learner = simulate.LEARNERS["quitter"]
    return _simulated(graph, learner, days=5, per_session=25, gap_after_day=3, gap_days=60)


# Private Functions ================================================================================

def _has_output(op: dict) -> bool:
    return op["op"] not in ("applyAttempt", "applyPlacement")


def _mini_graph(spec: dict[str, tuple[int, list[str]]], weights: dict[str, dict] | None = None) -> dict:
    skills = {}
    for order, (skill_id, (tier, prereqs)) in enumerate(spec.items()):
        skills[skill_id] = {"id": skill_id, "tier": tier, "prereqs": prereqs, "order": order, "targetBase": 1200,
                            "perKey": 180, "enabled": True, "emulator": {},
                            "langWeights": dict((weights or {}).get(skill_id, {}))}
    return {"version": 1, "skills": skills, "tips": {"b1": "Tip for b1."}}


def _driven(graph: dict, setup: list[dict], picks: int, start: float, make) -> list[dict]:
    """The setup ops, then ``picks`` rounds of chooseFocus (seed = round) and an attempt
    ``make(focus, t)`` on each pick."""
    state = new_state(graph)
    for op in setup:
        state = apply_attempt(state, op["record"], graph)
    ops: list[dict] = list(setup)
    t = start
    for pick in range(picks):
        focus = choose_focus(state, PY, graph, t, seed=pick)
        ops.append({"op": "chooseFocus", "lang": PY, "now": t, "seed": pick})
        record = make(focus, t)
        state = apply_attempt(state, record, graph)
        ops.append({"op": "applyAttempt", "record": record})
        t += 30
    return ops


def _simulated(graph: dict, learner: simulate.Learner, days: int, per_session: int,
               gap_after_day: int | None = None, gap_days: int = 0) -> dict:
    """Drive a simulated learner through the Python model and record every decision as an op."""
    index = simulate.make_index(graph, per_skill=6, composites=1)
    rng = random.Random(learner.seed)
    exposures: Counter = Counter()
    state = new_state(graph)
    ops: list[dict] = []
    for day in range(days):
        if gap_after_day is not None and day == gap_after_day:
            for skill in exposures:
                exposures[skill] = int(exposures[skill] * learner.forget)
        offset = gap_days if gap_after_day is not None and day >= gap_after_day else 0
        start = T0 + (day + offset) * DAY
        t = float(start)
        for _ in range(per_session):
            focus = choose_focus(state, PY, graph, t)
            ops.append({"op": "chooseFocus", "lang": PY, "now": t})
            seed = int(t) ^ len(state["log"])
            exercise_id = choose_exercise(state, focus, PY, index, seed, graph)
            ops.append({"op": "chooseExercise", "skill": focus, "lang": PY, "seed": seed})
            skill = "+".join(simulate._exercise_skills(index, focus, exercise_id))
            record = simulate.make_record(learner, rng, exposures, graph, exercise_id, skill, t)
            state = apply_attempt(state, record, graph)
            ops.append({"op": "applyAttempt", "record": record})
            t += record["ms"] / 1000 + 4
        ops += [{"op": "digest"}, {"op": "sessionSummary", "since": start}]
        weakest = choose_focus(state, PY, graph, t, seed=999)
        ops += [{"op": "projection", "skill": weakest, "lang": PY}, {"op": "diagnose", "skill": weakest, "lang": PY}]
    ops.append({"op": "rebuildMatches"})
    return {"description": f"Simulated {learner.name} ({learner.description}): every focus, exercise and "
                           "attempt the model produced.", "index": index, "ops": ops}


if __name__ == "__main__":
    main()
