"""Simulated learners for validating the adaptive model.

Four learners: a fast sloppy one, a slow precise one, a plateaued expert and
a quitter who returns after 60 days. Each practises daily sessions driven by the model
(choose_focus -> choose_exercise -> apply_attempt) and the script prints, per session,
which skills the model focused on and why the weakest one is not mastered yet.

Example
-------
    uv run --project model python model/simulate.py            # all four learners
    uv run --project model python model/simulate.py quitter    # one learner
    uv run --project model python model/simulate.py picks plateaued_expert 40 5
        # the 40 focus picks of one session after 5 days, and their distribution
"""

from __future__ import annotations

import math
import random
import sys
from collections import Counter
from dataclasses import dataclass, field, replace

from vimtrainer_model import (
    apply_attempt,
    apply_placement,
    choose_exercise,
    choose_focus,
    diagnose,
    load_graph,
    new_state,
    session_summary,
)
from vimtrainer_model.graph import skill_ids, target_ms

LANG = "python"
DAY = 86400
T0 = 1760000000
PAR_MIN = 6
PAR_SPAN = 9


@dataclass
class Learner:
    """Latent ability of a simulated user. Multipliers are relative to target time / par."""

    name: str
    description: str
    seed: int
    speed_start: float
    speed_floor: float
    tau: float
    eff_start: float
    eff_floor: float
    error_rate: float
    days: int
    per_session: int
    plateau: dict[str, tuple[float, float]] = field(default_factory=dict)
    placement_tiers: int = 0
    gap_after_day: int | None = None
    gap_days: int = 0
    forget: float = 1.0


LEARNERS = {
    "fast_sloppy": Learner(
        "fast_sloppy", "fast hands, spams keys (2x par, slowly improving), 12% give-ups", 1,
        speed_start=0.8, speed_floor=0.6, tau=40, eff_start=2.2, eff_floor=1.1, error_rate=0.12,
        days=14, per_session=30,
    ),
    "slow_precise": Learner(
        "slow_precise", "at par, rarely wrong, but slow to start", 2,
        speed_start=2.2, speed_floor=0.85, tau=12, eff_start=1.05, eff_floor=1.0, error_rate=0.02,
        days=14, per_session=30,
    ),
    "plateaued_expert": Learner(
        "plateaued_expert", "passes placement through tier 7; stuck on dot, macros and :g", 3,
        speed_start=0.9, speed_floor=0.7, tau=5, eff_start=1.1, eff_floor=1.0, error_rate=0.03,
        days=10, per_session=30,
        plateau={"o.dot": (1.0, 1.7), "a.dot": (1.3, 1.8), "a.macro": (1.6, 1.4), "x.global": (1.5, 1.5),
                 "x.lastsearch": (1.4, 1.6)},
        placement_tiers=7,
    ),
    "quitter": Learner(
        "quitter", "learns for 10 days, stops for 60, comes back rusty", 4,
        speed_start=1.6, speed_floor=0.8, tau=10, eff_start=1.3, eff_floor=1.0, error_rate=0.04,
        days=16, per_session=30, gap_after_day=10, gap_days=60, forget=0.05,
    ),
}


# Public Functions =================================================================================

def make_index(graph: dict, lang: str = LANG, per_skill: int = 30, composites: int = 2) -> dict:
    """Synthetic exercise index: per skill ``per_skill`` single-skill ids plus composites
    tagged with the skill and its first prerequisite."""
    prefix = lang[:2]
    by_skill = {}
    for skill_id in skill_ids(graph):
        ids: list = [f"{prefix}/{skill_id}/{i:04d}" for i in range(1, per_skill + 1)]
        prereqs = graph["skills"][skill_id]["prereqs"]
        if prereqs:
            pair = [skill_id, prereqs[0]]
            ids += [{"id": f"{prefix}/{'+'.join(pair)}/{i:04d}", "skills": pair} for i in range(1, composites + 1)]
        by_skill[skill_id] = {"ids": ids}
    return {"langs": {lang: by_skill}}


def par_of(exercise_id: str) -> int:
    """Deterministic par for a synthetic exercise id."""
    return PAR_MIN + int(exercise_id[-4:]) % PAR_SPAN


def make_record(learner: Learner, rng: random.Random, exposures: Counter, graph: dict,
                exercise_id: str, skill: str, t: float) -> dict:
    """One simulated attempt by the learner."""
    skills = skill.split("+")
    par = par_of(exercise_id)
    speed_mult = max(_ability(learner, exposures, s)[0] for s in skills)
    eff_mult = max(_ability(learner, exposures, s)[1] for s in skills)
    ms = target_ms(graph, skills[0], par) * speed_mult * math.exp(rng.gauss(0, 0.15))
    keys = max(par, round(par * eff_mult * math.exp(rng.gauss(0, 0.08))))
    ok = rng.random() >= learner.error_rate
    for s in skills:
        exposures[s] += 1
    return {"t": t, "ex": exercise_id, "skill": skill, "lang": LANG, "ok": ok, "ms": round(ms),
            "keys": keys, "par": par, "hint": False, "retry": False, "undo": 0}


def placement_records(learner: Learner, rng: random.Random, exposures: Counter, graph: dict, t: float) -> list[dict]:
    """Twelve placement attempts: one per tier 1-9 plus three from tiers 3-4.

    Tiers up to ``placement_tiers`` are passed at good speed; higher tiers are given up.
    """
    picks = []
    for tier in range(1, 10):
        picks.append(_placement_skill(graph, tier, 0))
    picks += [_placement_skill(graph, 3, 1), _placement_skill(graph, 4, 1), _placement_skill(graph, 4, 2)]
    records = []
    for position, skill in enumerate(picks):
        exercise_id = f"{LANG[:2]}/{skill}/{position + 1:04d}"
        record = make_record(learner, rng, exposures, graph, exercise_id, skill, t + position * 20)
        if graph["skills"][skill]["tier"] > learner.placement_tiers:
            record = {**record, "ok": False}
        records.append(record)
    return records


def run_learner(learner: Learner, graph: dict, index: dict, quiet: bool = False) -> tuple[dict, list[dict]]:
    """Simulate the learner's sessions; return the final state and per-session reports."""
    rng = random.Random(learner.seed)
    exposures: Counter = Counter()
    state = new_state(graph)
    reports = []
    if learner.placement_tiers:
        state = apply_placement(state, placement_records(learner, rng, exposures, graph, T0 - 3600), graph)
    for day in range(learner.days):
        if learner.gap_after_day is not None and day == learner.gap_after_day:
            for skill in exposures:
                exposures[skill] = int(exposures[skill] * learner.forget)
        offset = learner.gap_days if learner.gap_after_day is not None and day >= learner.gap_after_day else 0
        start = T0 + (day + offset) * DAY
        state, report = _session(learner, rng, exposures, graph, index, state, start, day + offset)
        reports.append(report)
        if not quiet:
            print(_format_report(report))
    return state, reports


def pick_sequence(learner: Learner, graph: dict, index: dict, picks: int, after_days: int) -> list[str]:
    """The focus picks of one ``picks``-attempt session after ``after_days`` days of practice."""
    state, _ = run_learner(replace(learner, days=after_days), graph, index, quiet=True)
    rng = random.Random(learner.seed + 1000)
    exposures: Counter = Counter()
    t = float(T0 + after_days * DAY)
    sequence = []
    for _ in range(picks):
        focus = choose_focus(state, LANG, graph, t)
        if focus is None:
            break
        exercise_id = choose_exercise(state, focus, LANG, index, int(t) ^ len(state["log"]), graph)
        skill = "+".join(_exercise_skills(index, focus, exercise_id))
        state = apply_attempt(state, make_record(learner, rng, exposures, graph, exercise_id, skill, t), graph)
        sequence.append(focus)
        t += 10
    return sequence


def main(argv: list[str]):
    """Run the named learners (all by default) and print their diagnosis over time."""
    graph = load_graph()
    index = make_index(graph)
    if argv and argv[0] == "picks":
        name = argv[1] if len(argv) > 1 else "plateaued_expert"
        count = int(argv[2]) if len(argv) > 2 else 40
        after = int(argv[3]) if len(argv) > 3 else 5
        sequence = pick_sequence(LEARNERS[name], graph, index, count, after)
        print(f"== {name}: {len(sequence)} picks after {after} days")
        for start in range(0, len(sequence), 10):
            print("   " + " ".join(sequence[start:start + 10]))
        for skill, n in Counter(sequence).most_common():
            print(f"   {skill:<14} {n:3d}  {100 * n / len(sequence):5.1f}%")
        return
    names = argv or list(LEARNERS)
    for name in names:
        learner = LEARNERS[name]
        print(f"\n== {learner.name}: {learner.description}")
        state, _ = run_learner(learner, graph, index)
        print(_format_final(state, graph))


# Private Functions ================================================================================

def _ability(learner: Learner, exposures: Counter, skill: str) -> tuple[float, float]:
    """Current (speed multiplier, keys/par multiplier) for a skill after its exposures."""
    speed_floor, eff_floor = learner.plateau.get(skill, (learner.speed_floor, learner.eff_floor))
    decay = math.exp(-exposures[skill] / learner.tau)
    speed_start = max(learner.speed_start, speed_floor)
    eff_start = max(learner.eff_start, eff_floor)
    return speed_floor + (speed_start - speed_floor) * decay, eff_floor + (eff_start - eff_floor) * decay


def _placement_skill(graph: dict, tier: int, nth: int) -> str:
    """The nth skill of a tier that is enabled and drilled in Python."""
    skills = [s for s in skill_ids(graph) if graph["skills"][s]["tier"] == tier
              and graph["skills"][s]["enabled"] and graph["skills"][s]["langWeights"].get(LANG, 1.0) > 0]
    return skills[nth % len(skills)]


def _session(learner, rng, exposures, graph, index, state, start, day) -> tuple[dict, dict]:
    """One practice session of ``per_session`` attempts."""
    t = float(start)
    focuses: Counter = Counter()
    reviews: Counter = Counter()
    for _ in range(learner.per_session):
        focus = choose_focus(state, LANG, graph, t)
        if focus is None:
            break
        exercise_id = choose_exercise(state, focus, LANG, index, int(t) ^ len(state["log"]), graph)
        skill = "+".join(_exercise_skills(index, focus, exercise_id))
        record = make_record(learner, rng, exposures, graph, exercise_id, skill, t)
        was_review = _is_due(state, focus, t)
        state = apply_attempt(state, record, graph)
        if was_review:
            reviews["passed" if state["skills"][focus][LANG]["status"] == "mastered" else "failed"] += 1
        focuses[focus] += 1
        t += record["ms"] / 1000 + 4
    weakest = choose_focus(state, LANG, graph, t, seed=999)
    summary = session_summary(state, start, graph)
    report = {
        "day": day,
        "focuses": focuses.most_common(4),
        "weakest": weakest,
        "diagnosis": diagnose(state, weakest, LANG, graph) if weakest else None,
        "mastered": summary["mastered"],
        "unlocked": summary["unlocked"],
        "tip": summary["tip"],
        "reviews": dict(reviews),
    }
    return state, report


def _exercise_skills(index: dict, focus: str, exercise_id: str) -> list[str]:
    for item in index["langs"][LANG][focus]["ids"]:
        if isinstance(item, dict) and item["id"] == exercise_id:
            return item["skills"]
    return [focus]


def _is_due(state: dict, skill: str, t: float) -> bool:
    """Whether an attempt on the skill at time t is graded as a review."""
    st = state["skills"].get(skill, {}).get(LANG)
    if st is None:
        return False
    if st["status"] == "review":
        return True
    return st["status"] == "mastered" and st["nextReview"] is not None and st["nextReview"] <= t


def _format_report(report: dict) -> str:
    focus = ", ".join(f"{skill} x{count}" for skill, count in report["focuses"])
    diag = report["diagnosis"]
    why = "-"
    if diag:
        eff = "n/a" if diag["efficiency"] is None else f"{diag['efficiency']:.2f}"
        why = (f"{report['weakest']} [{'/'.join(diag['failing']) or 'ok'}] "
               f"speed {diag['speed']:.2f} eff {eff} acc {diag['acc']:.2f} n {diag['n']}")
    line = f"day {report['day']:3d} | focus {focus:<52} | next: {why}"
    if report["reviews"]:
        line += f"\n        reviews: {report['reviews'].get('passed', 0)} passed, {report['reviews'].get('failed', 0)} failed"
    if report["mastered"]:
        line += f"\n        mastered: {', '.join(report['mastered'])}"
    if report["unlocked"]:
        line += f"\n        unlocked: {', '.join(report['unlocked'])}"
    return line


def _format_final(state: dict, graph: dict) -> str:
    statuses = Counter(st["status"] for langs in state["skills"].values() for lang, st in langs.items() if lang == LANG)
    gates = Counter(g for sid in skill_ids(graph)
                    for g in diagnose(state, sid, LANG, graph)["failing"]
                    if state["skills"].get(sid, {}).get(LANG, {}).get("status") in ("active", "introduced"))
    return (f"   final: {dict(sorted(statuses.items()))}; failing gates among active skills: "
            f"{dict(gates.most_common())}")


if __name__ == "__main__":
    main(sys.argv[1:])
