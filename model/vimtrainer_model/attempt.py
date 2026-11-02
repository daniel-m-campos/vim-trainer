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

from vimtrainer_model.constants import (
    DAY,
    FOCUS_HISTORY_MAX,
    IN_ROTATION,
    REVIEW_FAIL_FACTOR,
    REVIEW_KEYS,
    Status,
)
from vimtrainer_model.graph import record_skills
from vimtrainer_model.placement import apply_placement
from vimtrainer_model.state import (
    clone_state,
    confidence,
    efficiency_factor,
    ensure_skill,
    interval_days,
    is_counted,
    log_record,
    mark_mastered,
    new_state,
    passes_mastery_gate,
    prepare,
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
        every named skill is credited. The app also writes three optional fields that the
        model ignores and logs unchanged: ``seq`` (str, the player's normalised keys),
        ``beatPar`` (bool, ok and keys < par) and ``flag`` (dict with ``reason`` and an
        optional ``note``, set when the player reports the exercise). ``vectors.digest``
        does not read record contents, so these fields never change the vectors.
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
    """Recompute a state from its log (placement records are those flagged ``placement``).

    Consecutive placement records form one ``apply_placement`` batch; a change of language
    closes the batch, because the app runs one placement test per language.
    """
    state = new_state(graph)
    batch: list[dict] = []
    for record in log:
        if batch and (not record.get("placement") or record["lang"] != batch[0]["lang"]):
            state, batch = apply_placement(state, batch, graph), []
        if record.get("placement"):
            batch.append(record)
            continue
        state = apply_attempt(state, record, graph)
    if batch:
        state = apply_placement(state, batch, graph)
    return state


def review_passed(graph: dict, skill_id: str, record: dict) -> bool:
    """A review passes when ok and keys <= 1.5 x par (time is not graded)."""
    return bool(record["ok"]) and record["keys"] <= REVIEW_KEYS * record["par"]


# Private Functions ================================================================================

def _credit(state: dict, graph: dict, skill_id: str, record: dict):
    """Update one skill's statistics and status from a counted attempt."""
    st = ensure_skill(state, graph, skill_id, record["lang"])
    if st["status"] == Status.LOCKED:
        # Only a skill the user forced from the stats screen is drilled while locked;
        # forcing a skill makes it active.
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
    """Scale confidence by 0.8 by inflating the efficiency EMA, so the drop persists.

    The efficiency factor is clamped at 0.5, so a skill already at the floor drops less.
    """
    if st["effEma"] is None or st["confidence"] <= 0:
        return
    st["effEma"] = 1.0 / (REVIEW_FAIL_FACTOR * efficiency_factor(st))
    st["confidence"] = confidence(graph, skill_id, st)
