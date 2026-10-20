"""Placement test: seed skills from a dozen attempts and propagate through prerequisites.

Each placement record seeds its skill (n = 1, EMAs from the attempt). A pass marks every
transitive prerequisite mastered (confidence 1.0, n = 8) unless that prerequisite was
itself sampled and failed. Sampled skills scoring above 0.6 become active; unsampled
skills whose prerequisites are all satisfied start active at confidence 0.5.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> from vimtrainer_model.state import new_state
>>> graph = load_graph()
>>> rec = {"t": 0, "ex": "py/t.quote/0001", "skill": "t.quote", "lang": "python", "ok": True,
...        "ms": 3000, "keys": 12, "par": 12, "hint": False, "retry": False, "undo": 0}
>>> apply_placement(new_state(graph), [rec], graph)["skills"]["o.change"]["python"]["status"]
'mastered'
"""

from __future__ import annotations

from vimtrainer_model.constants import (
    DAY,
    MASTER_N,
    MASTERED_LIKE,
    MAX_ACTIVE,
    PLACEMENT_ACTIVE_CONF,
    PLACEMENT_FOUNDATION_TIER,
    PLACEMENT_INFERRED_CONF,
    PLACEMENT_INFERRED_REVIEWS,
    Status,
)
from vimtrainer_model.graph import record_skills, skill_ids
from vimtrainer_model.state import (
    active_count,
    clone_state,
    ensure_lang,
    ensure_skill,
    interval_days,
    is_counted,
    is_eligible,
    log_record,
    prereqs_satisfied,
    update_stats,
    update_unlocks,
)


# Public Functions =================================================================================

def apply_placement(state: dict, records: list[dict], graph: dict) -> dict:
    """Return a new state seeded from placement-test records.

    Parameters
    ----------
    state : dict
        ModelState, normally fresh from ``new_state``.
    records : list[dict]
        Placement AttemptRecords. They are appended to the log flagged ``placement: true``
        so ``rebuild`` can replay them.
    graph : dict
        Skill graph.

    Returns
    -------
    dict
        The seeded ModelState.
    """
    result = clone_state(state)
    if not records:
        return result
    langs = list(dict.fromkeys(record["lang"] for record in records))
    t_end = max(record["t"] for record in records)
    for lang in langs:
        ensure_lang(result, graph, lang)
    sampled = _seed(result, graph, records)
    inferred = _propagate(result, graph, sampled, t_end)
    for lang in langs:
        _settle(result, graph, lang, sampled, inferred)
        update_unlocks(result, graph, lang)
    return result


def transitive_prereqs(graph: dict, skill_id: str) -> list[str]:
    """All prerequisites of a skill, nearest first, without duplicates."""
    found: list[str] = []
    queue = list(graph["skills"][skill_id]["prereqs"])
    while queue:
        prereq = queue.pop(0)
        if prereq in found:
            continue
        found.append(prereq)
        queue += graph["skills"][prereq]["prereqs"]
    return found


def inferred_from_pass(graph: dict, skill_id: str) -> list[str]:
    """Skills a placement pass proves: transitive prerequisites, plus all of tier 0 when
    the passed skill is tier 3 or higher (tier 0 is "assumed; placement test confirms")."""
    found = transitive_prereqs(graph, skill_id)
    if graph["skills"][skill_id]["tier"] < PLACEMENT_FOUNDATION_TIER:
        return found
    return found + [sid for sid in skill_ids(graph) if graph["skills"][sid]["tier"] == 0 and sid not in found]


# Private Functions ================================================================================

def _seed(state: dict, graph: dict, records: list[dict]) -> dict[tuple[str, str], bool]:
    """Log every record and count the counted ones; return whether each sampled (skill,
    lang) passed. A hinted or retried record is logged only, and is never a pass, so it
    cannot propagate mastery to prerequisites."""
    sampled: dict[tuple[str, str], bool] = {}
    for record in records:
        flagged = {**record, "placement": True}
        log_record(state, flagged)
        counted = is_counted(flagged)
        for skill_id in record_skills(graph, flagged):
            st = ensure_skill(state, graph, skill_id, flagged["lang"])
            key = (skill_id, flagged["lang"])
            if not counted:
                sampled[key] = sampled.get(key, False)
                continue
            update_stats(state, graph, skill_id, flagged, st)
            sampled[key] = sampled.get(key, False) or bool(flagged["ok"])
    return sampled


def _propagate(state: dict, graph: dict, sampled: dict[tuple[str, str], bool], now: float) -> set[tuple[str, str]]:
    """Mark prerequisites of passed skills mastered; a directly failed skill is skipped."""
    inferred: set[tuple[str, str]] = set()
    for (skill_id, lang), passed in sampled.items():
        if not passed:
            continue
        for prereq in inferred_from_pass(graph, skill_id):
            if sampled.get((prereq, lang)) is False:
                continue
            _infer_mastered(ensure_skill(state, graph, prereq, lang), now)
            inferred.add((prereq, lang))
    return inferred


def _infer_mastered(st: dict, now: float):
    """Inferred mastery: confidence 1.0, n >= 8, first review after two passed intervals."""
    st["status"] = Status.MASTERED
    st["confidence"] = 1.0
    st["n"] = max(st["n"], MASTER_N)
    st["acc"] = 1.0
    st["reviewsPassed"] = PLACEMENT_INFERRED_REVIEWS
    st["nextReview"] = now + interval_days(PLACEMENT_INFERRED_REVIEWS) * DAY


def _settle(state: dict, graph: dict, lang: str, sampled: dict, inferred: set):
    """Set statuses of sampled skills, then open unsampled skills whose prerequisites hold."""
    for (skill_id, sampled_lang) in sampled:
        if sampled_lang != lang or (skill_id, lang) in inferred:
            continue
        st = state["skills"][skill_id][lang]
        if st["status"] in MASTERED_LIKE:
            continue
        opens = st["confidence"] > PLACEMENT_ACTIVE_CONF or prereqs_satisfied(state, graph, skill_id, lang)
        st["status"] = Status.ACTIVE if opens else Status.LOCKED
    count = active_count(state, graph, lang)
    for skill_id in skill_ids(graph):
        if count >= MAX_ACTIVE:
            break
        if (skill_id, lang) in sampled or (skill_id, lang) in inferred or not is_eligible(graph, skill_id, lang):
            continue
        st = ensure_skill(state, graph, skill_id, lang)
        if st["status"] != Status.LOCKED or not graph["skills"][skill_id]["prereqs"]:
            continue
        if not prereqs_satisfied(state, graph, skill_id, lang):
            continue
        st["status"] = Status.ACTIVE
        if st["n"] == 0:
            st["confidence"] = PLACEMENT_INFERRED_CONF
        count += 1
