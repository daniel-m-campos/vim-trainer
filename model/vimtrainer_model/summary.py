"""Session summary: improved skills, new mastery, new unlocks and the editor tip.

The state before the session is recomputed by replaying the log up to ``since_t``, so the
summary needs the graph (and takes the tips from ``graph["tips"]``).

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> from vimtrainer_model.state import new_state
>>> graph = load_graph()
>>> session_summary(new_state(graph), 0, graph)
{'improved': [], 'mastered': [], 'unlocked': [], 'tip': None}
"""

from __future__ import annotations

from vimtrainer_model.attempt import rebuild
from vimtrainer_model.constants import IMPROVED_DELTA, IN_ROTATION, MASTERED_LIKE, Status
from vimtrainer_model.graph import order_of, skill_ids
from vimtrainer_model.state import ensure_lang, is_mastered_anywhere, is_unlocked_anywhere

_EPSILON = 1e-12


# Public Functions =================================================================================

def session_summary(state: dict, since_t: float, graph: dict) -> dict:
    """Summarise what changed since ``since_t``.

    Parameters
    ----------
    state : dict
        ModelState at the end of the session.
    since_t : float
        Session start in seconds; records with ``t >= since_t`` belong to the session.
    graph : dict
        Skill graph (with ``tips``).

    Returns
    -------
    dict
        ``{"improved": [{"skill", "delta"}], "mastered": [...], "unlocked": [...], "tip": str | None}``.
        ``improved`` holds confidence gains of at least 0.1, largest first.
    """
    session = [record for record in state["log"] if record["t"] >= since_t]
    langs = list(dict.fromkeys(record["lang"] for record in session))
    before = rebuild([record for record in state["log"] if record["t"] < since_t], graph)
    for lang in langs:
        ensure_lang(before, graph, lang)  # a language new this session starts as ensure_skill makes it
    gains: dict[str, float] = {}
    mastered: list[str] = []
    unlocked: list[str] = []
    for skill_id in skill_ids(graph):
        for lang in langs:
            old, new = _view(before, graph, skill_id, lang), _view(state, graph, skill_id, lang)
            delta = new["confidence"] - old["confidence"]
            if delta > gains.get(skill_id, 0.0):
                gains[skill_id] = delta
            if new["status"] in MASTERED_LIKE and old["status"] not in MASTERED_LIKE and skill_id not in mastered:
                mastered.append(skill_id)
            if new["status"] in IN_ROTATION and old["status"] == Status.LOCKED and skill_id not in unlocked:
                unlocked.append(skill_id)
    ranked = sorted(gains, key=lambda sid: (-gains[sid], order_of(graph, sid)))
    improved = [{"skill": sid, "delta": gains[sid]} for sid in ranked if gains[sid] >= IMPROVED_DELTA - _EPSILON]
    return {"improved": improved, "mastered": mastered, "unlocked": unlocked, "tip": _tip(graph, ranked, mastered)}


# Private Functions ================================================================================

def _view(state: dict, graph: dict, skill_id: str, lang: str) -> dict:
    """Status and confidence of (skill, lang); when absent, the status ``ensure_skill`` would give."""
    st = state["skills"].get(skill_id, {}).get(lang)
    if st is not None:
        return {"status": st["status"], "confidence": st["confidence"]}
    if is_mastered_anywhere(state, skill_id):
        return {"status": Status.MASTERED, "confidence": 0.0}
    tier_zero = graph["skills"][skill_id]["tier"] == 0
    opened = tier_zero or is_unlocked_anywhere(state, skill_id)
    return {"status": Status.ACTIVE if opened else Status.LOCKED, "confidence": 0.0}


def _tip(graph: dict, ranked: list[str], mastered: list[str]) -> str | None:
    """Tip of the skill with the largest confidence gain that has one; new masteries next."""
    tips = graph.get("tips", {})
    for skill_id in ranked + mastered:
        if skill_id in tips:
            return tips[skill_id]
    return None
