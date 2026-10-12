"""Applying attempts to the model, spaced review grading, and rebuilding from a log.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> from vimtrainer_model.state import new_state
>>> graph = load_graph()
>>> record = {"t": 1000, "ex": "py/f.hjkl/0001", "skill": "f.hjkl", "lang": "python",
...           "ok": True, "ms": 2500, "keys": 6, "par": 6, "hint": False, "retry": False, "undo": 0}
>>> apply_attempt(new_state(graph), record, graph)["skills"]["f.hjkl"]["python"]["n"]
1
"""

from __future__ import annotations

from vimtrainer_model.constants import (
    DAY,
    FOCUS_HISTORY_MAX,
    IN_ROTATION,
    REVIEW_FAIL_FACTOR,
    REVIEW_KEYS,
    REVIEW_TIME,
    Status,
)
from vimtrainer_model.graph import record_skills, target_ms
from vimtrainer_model.placement import apply_placement
from vimtrainer_model.state import (
    clone_state,
    confidence,
    ensure_skill,
    interval_days,
    is_counted,
    log_record,
    mark_mastered,
    new_state,
    passes_mastery_gate,
    prepare,
    speed,
    update_stats,
    update_unlocks,
)


# Public Functions =================================================================================

def apply_attempt(state: dict, record: dict, graph: dict) -> dict:
    """Return a new state with one attempt applied.

    Parameters
    ----------
    state : dict
        Current ModelState (not modified).
    record : dict
        AttemptRecord. ``skill`` may name several skills joined by '+' (composites);
        every named skill is credited.
    graph : dict
        Skill graph.

    Returns
    -------
    dict
        The new ModelState.
    """
    result = clone_state(state)
    skills = record_skills(graph, record)
    log_record(result, record)
    if not record.get("retry"):
        # A retry repeats the exercise just shown; it is not another pick of the skill,
        # so it must not count toward the 3-in-a-row interleave limit.
        primary = skills[0] if skills else record["skill"]
        result["focusHistory"] = (result["focusHistory"] + [primary])[-FOCUS_HISTORY_MAX:]
    prepare(result, graph, record["lang"], record["t"])
    if not is_counted(record):
        return result
    for skill_id in skills:
        _credit(result, graph, skill_id, record)
    update_unlocks(result, graph, record["lang"])
    return result


def rebuild(log: list[dict], graph: dict) -> dict:
    """Recompute a state from its log (placement records are those flagged ``placement``)."""
    state = new_state(graph)
    batch: list[dict] = []
    for record in log:
        if record.get("placement"):
            batch.append(record)
            continue
        if batch:
            state, batch = apply_placement(state, batch, graph), []
        state = apply_attempt(state, record, graph)
    if batch:
        state = apply_placement(state, batch, graph)
    return state


def review_passed(graph: dict, skill_id: str, record: dict) -> bool:
    """A review passes when ok, keys <= 1.5 x par and ms <= 1.3 x target time."""
    if not record["ok"]:
        return False
    if record["keys"] > REVIEW_KEYS * record["par"]:
        return False
    return record["ms"] <= REVIEW_TIME * target_ms(graph, skill_id, record["par"])


# Private Functions ================================================================================

def _credit(state: dict, graph: dict, skill_id: str, record: dict):
    """Update one skill's statistics and status from a counted attempt."""
    st = ensure_skill(state, graph, skill_id, record["lang"])
    if st["status"] == Status.LOCKED:
        # Only a skill the user forced from the stats screen is drilled while locked;
        # forcing a skill makes it active (04, Unlocking).
        st["status"] = Status.ACTIVE
    was_review = st["status"] == Status.REVIEW
    update_stats(state, graph, skill_id, record, st)
    if was_review:
        _grade_review(graph, skill_id, st, record)
        return
    if st["status"] in IN_ROTATION and passes_mastery_gate(graph, skill_id, st):
        mark_mastered(st, record["t"])


def _grade_review(graph: dict, skill_id: str, st: dict, record: dict):
    """Pass doubles the interval; fail resets it to 1 day and drops confidence by 20%."""
    if review_passed(graph, skill_id, record):
        st["reviewsPassed"] += 1
        st["status"] = Status.MASTERED
        st["nextReview"] = record["t"] + interval_days(st["reviewsPassed"]) * DAY
        return
    st["reviewsPassed"] = 0
    st["nextReview"] = None
    st["status"] = Status.ACTIVE
    _drop_confidence(graph, skill_id, st)


def _drop_confidence(graph: dict, skill_id: str, st: dict):
    """Scale confidence by 0.8 by slowing the time EMA, so the drop persists."""
    if st["timeEma"] is None or st["confidence"] <= 0:
        return
    capped_speed = REVIEW_FAIL_FACTOR * min(speed(graph, skill_id, st), 1.0)
    st["timeEma"] = target_ms(graph, skill_id, st["parEma"]) / capped_speed
    st["confidence"] = confidence(graph, skill_id, st)
