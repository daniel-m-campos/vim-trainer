"""Model state: creation, per-skill statistics, confidence, gates and unlocking.

State is a JSON-compatible dict shaped exactly like the TypeScript ``ModelState``:
``{"skills": {skill: {lang: SkillState}}, "log": [...], "recent": [...], "focusHistory": [...]}``.
Public functions in other modules never mutate their input; helpers here mutate the
state they are given and are only called on a fresh clone.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> graph = load_graph()
>>> state = new_state(graph)
>>> prepare(state, graph, "python", 0)
>>> state["skills"]["f.hjkl"]["python"]["status"]
'active'
"""

from __future__ import annotations

import math

from vimtrainer_model.constants import (
    ACC_WINDOW,
    ALPHA,
    DAY,
    EFF_FLOOR,
    IN_ROTATION,
    MASTER_ACC,
    MASTER_EFF,
    MASTER_N,
    MASTERED_LIKE,
    MAX_ACTIVE,
    MAX_INTERVAL_DAYS,
    MIN_ACTIVE,
    RECENT_MAX,
    Status,
)
from vimtrainer_model.graph import is_enabled, lang_weight, record_skills, skill_ids, target_ms


# Public Functions =================================================================================

def new_state(graph: dict) -> dict:
    """Empty model state with one (empty) per-language map per skill."""
    return {"skills": {sid: {} for sid in skill_ids(graph)}, "log": [], "recent": [], "focusHistory": []}


def new_skill_state(status: str) -> dict:
    """A SkillState with no data."""
    return {
        "timeEma": None,
        "effEma": None,
        "parEma": None,
        "acc": 0.0,
        "n": 0,
        "confidence": 0.0,
        "lastSeen": 0,
        "status": status,
        "reviewsPassed": 0,
        "nextReview": None,
    }


def clone_state(state: dict) -> dict:
    """Copy a state; skill states are copied, log records are shared (treated as immutable)."""
    return {
        "skills": {sid: {lang: dict(st) for lang, st in langs.items()} for sid, langs in state["skills"].items()},
        "log": list(state["log"]),
        "recent": list(state["recent"]),
        "focusHistory": list(state["focusHistory"]),
    }


def ensure_skill(state: dict, graph: dict, skill_id: str, lang: str) -> dict:
    """Return the (skill, lang) state, creating it with its initial status if missing.

    Unlocking uses the max across languages (adaptive-model.md), so a new entry starts:

    - mastered, with its first review due at once, when the skill is mastered in another
      language: it is not re-locked and does not crowd the 4-7 active skills, and spaced
      review confirms it in this language;
    - active for tier 0;
    - active when the skill is unlocked in another language and fewer than MAX_ACTIVE
      skills are in rotation for this language;
    - locked otherwise (``update_unlocks`` opens it once a slot frees up).
    """
    langs = state["skills"].setdefault(skill_id, {})
    if lang in langs:
        return langs[lang]
    if is_mastered_anywhere(state, skill_id):
        langs[lang] = new_skill_state(Status.MASTERED)
        langs[lang]["nextReview"] = 0
        return langs[lang]
    tier_zero = graph["skills"][skill_id]["tier"] == 0
    carried = is_unlocked_anywhere(state, skill_id) and active_count(state, graph, lang) < MAX_ACTIVE
    langs[lang] = new_skill_state(Status.ACTIVE if tier_zero or carried else Status.LOCKED)
    return langs[lang]


def is_unlocked_anywhere(state: dict, skill_id: str) -> bool:
    """Whether the skill is not locked in at least one language."""
    return any(st["status"] != Status.LOCKED for st in state["skills"].get(skill_id, {}).values())


def is_mastered_anywhere(state: dict, skill_id: str) -> bool:
    """Whether the skill is mastered (or mastered and due for review) in any language."""
    return any(st["status"] in MASTERED_LIKE for st in state["skills"].get(skill_id, {}).values())


def is_eligible(graph: dict, skill_id: str, lang: str) -> bool:
    """Enabled for the profile and drilled in this language (weight > 0)."""
    return is_enabled(graph, skill_id) and lang_weight(graph, skill_id, lang) > 0


def prereq_satisfied(state: dict, graph: dict, prereq: str, lang: str) -> bool:
    """A prerequisite counts when mastered anywhere, disabled, or weight 0 in this language."""
    return is_mastered_anywhere(state, prereq) or not is_eligible(graph, prereq, lang)


def prereqs_satisfied(state: dict, graph: dict, skill_id: str, lang: str) -> bool:
    """Whether every prerequisite of the skill is satisfied for this language."""
    return all(prereq_satisfied(state, graph, p, lang) for p in graph["skills"][skill_id]["prereqs"])


def speed(graph: dict, skill_id: str, st: dict) -> float:
    """``target_ms / time_ema``; 0 without data, infinite for a zero time."""
    if st["timeEma"] is None:
        return 0.0
    if st["timeEma"] <= 0:
        return math.inf
    return target_ms(graph, skill_id, st["parEma"]) / st["timeEma"]


def efficiency_factor(st: dict) -> float:
    """``clamp(1 / eff_ema, 0.5, 1.0)``; 0.5 without data."""
    if st["effEma"] is None:
        return EFF_FLOOR
    if st["effEma"] <= 0:
        return 1.0
    return min(max(1.0 / st["effEma"], EFF_FLOOR), 1.0)


def confidence(graph: dict, skill_id: str, st: dict) -> float:
    """``min(speed, 1) * clamp(1 / eff_ema, 0.5, 1)``."""
    if st["timeEma"] is None:
        return 0.0
    return min(speed(graph, skill_id, st), 1.0) * efficiency_factor(st)


def failing_gates(graph: dict, skill_id: str, st: dict | None) -> list[str]:
    """Mastery gates the skill does not meet yet, in the order samples, accuracy, efficiency, speed."""
    if st is None:
        return ["samples", "accuracy", "efficiency", "speed"]
    failing = []
    if st["n"] < MASTER_N:
        failing.append("samples")
    if st["acc"] < MASTER_ACC:
        failing.append("accuracy")
    if st["effEma"] is None or st["effEma"] > MASTER_EFF:
        failing.append("efficiency")
    if speed(graph, skill_id, st) < 1.0:
        failing.append("speed")
    return failing


def diagnose(state: dict, skill_id: str, lang: str, graph: dict) -> dict:
    """Why a skill is not mastered yet, for the stats screen and the simulators.

    Returns
    -------
    dict
        ``{"status", "failing": [gate, ...], "speed", "efficiency", "acc", "n"}`` where
        ``efficiency`` is ``1 / eff_ema`` (None without data) and ``speed`` is capped at 10.
    """
    st = state["skills"].get(skill_id, {}).get(lang)
    if st is None:
        return {"status": None, "failing": failing_gates(graph, skill_id, None), "speed": 0.0,
                "efficiency": None, "acc": 0.0, "n": 0}
    eff = None if st["effEma"] is None or st["effEma"] <= 0 else 1.0 / st["effEma"]
    return {
        "status": st["status"],
        "failing": failing_gates(graph, skill_id, st),
        "speed": min(speed(graph, skill_id, st), 10.0),
        "efficiency": eff,
        "acc": st["acc"],
        "n": st["n"],
    }


def passes_mastery_gate(graph: dict, skill_id: str, st: dict) -> bool:
    """``speed >= 1 and eff_ema <= 1.25 and acc >= 0.9 and n >= 8``."""
    return not failing_gates(graph, skill_id, st)


def interval_days(reviews_passed: int) -> int:
    """``min(2 ** reviews_passed, 60)``."""
    if reviews_passed >= 6:
        return MAX_INTERVAL_DAYS
    return min(1 << reviews_passed, MAX_INTERVAL_DAYS)


def is_counted(record: dict) -> bool:
    """Retries and hinted attempts are logged but never update the model."""
    return not record.get("retry") and not record.get("hint")


def recent_accuracy(state: dict, graph: dict, skill_id: str, lang: str) -> float:
    """Correct / attempts over the last 20 counted attempts of (skill, lang)."""
    total = 0
    correct = 0
    for record in reversed(state["log"]):
        if total >= ACC_WINDOW:
            break
        if record["lang"] != lang or not is_counted(record):
            continue
        if skill_id not in record_skills(graph, record):
            continue
        total += 1
        correct += 1 if record["ok"] else 0
    return correct / total if total else 0.0


def log_record(state: dict, record: dict):
    """Append a record to the log and its exercise id to the recent list."""
    state["log"].append(record)
    state["recent"] = (state["recent"] + [record["ex"]])[-RECENT_MAX:]


def update_stats(state: dict, graph: dict, skill_id: str, record: dict, st: dict):
    """Count one attempt: n, last seen, EMAs on correct attempts, accuracy, confidence."""
    st["n"] += 1
    st["lastSeen"] = record["t"]
    if record["ok"]:
        par = record["par"]
        st["timeEma"] = _ema(st["timeEma"], record["ms"])
        st["effEma"] = _ema(st["effEma"], record["keys"] / par if par > 0 else 1.0)
        st["parEma"] = _ema(st["parEma"], par)
    st["acc"] = recent_accuracy(state, graph, skill_id, record["lang"])
    st["confidence"] = confidence(graph, skill_id, st)


def mark_mastered(st: dict, now: float):
    """Promote to mastered with the first (1-day) review interval."""
    st["status"] = Status.MASTERED
    st["reviewsPassed"] = 0
    st["nextReview"] = now + interval_days(0) * DAY


def mark_due_reviews(state: dict, now: float):
    """Mastered skills whose review time has come move to review status."""
    for langs in state["skills"].values():
        for st in langs.values():
            if st["status"] != Status.MASTERED or st["nextReview"] is None:
                continue
            if st["nextReview"] <= now:
                st["status"] = Status.REVIEW


def ensure_lang(state: dict, graph: dict, lang: str):
    """Create the state for every enabled skill in this language."""
    for sid in skill_ids(graph):
        if is_enabled(graph, sid):
            ensure_skill(state, graph, sid, lang)


def prepare(state: dict, graph: dict, lang: str, now: float):
    """Bring a state up to date for a language at a time: ensure, due reviews, unlocks."""
    ensure_lang(state, graph, lang)
    mark_due_reviews(state, now)
    update_unlocks(state, graph, lang)


def active_count(state: dict, graph: dict, lang: str) -> int:
    """Number of eligible skills in rotation (active or introduced) for the language."""
    return sum(
        1
        for sid in skill_ids(graph)
        if is_eligible(graph, sid, lang) and _status(state, sid, lang) in IN_ROTATION
    )


def update_unlocks(state: dict, graph: dict, lang: str):
    """Unlock skills whose prerequisites are mastered (up to 7 active), then pull in
    ``introduced`` skills while fewer than 4 are active.
    """
    candidates = [sid for sid in skill_ids(graph) if is_eligible(graph, sid, lang)]
    count = active_count(state, graph, lang)
    for sid in candidates:
        if count >= MAX_ACTIVE:
            break
        st = ensure_skill(state, graph, sid, lang)
        if st["status"] != Status.LOCKED or not prereqs_satisfied(state, graph, sid, lang):
            continue
        st["status"] = Status.ACTIVE
        count += 1
    while count < MIN_ACTIVE:
        sid = _introduce_candidate(state, graph, lang, candidates)
        if sid is None:
            break
        state["skills"][sid][lang]["status"] = Status.INTRODUCED
        count += 1


# Private Functions ================================================================================

def _ema(previous: float | None, value: float) -> float:
    """EMA with alpha 0.1, seeded by the first sample."""
    if previous is None:
        return value
    return previous + ALPHA * (value - previous)


def _status(state: dict, skill_id: str, lang: str) -> str | None:
    st = state["skills"].get(skill_id, {}).get(lang)
    return None if st is None else st["status"]


def _introduce_candidate(state: dict, graph: dict, lang: str, candidates: list[str]) -> str | None:
    """Lowest tier's locked skill with the fewest unmet (then total) prerequisites."""
    locked = [sid for sid in candidates if ensure_skill(state, graph, sid, lang)["status"] == Status.LOCKED]
    if not locked:
        return None
    tier = min(graph["skills"][sid]["tier"] for sid in locked)

    def key(sid: str) -> tuple[int, int, int]:
        prereqs = graph["skills"][sid]["prereqs"]
        unmet = sum(1 for p in prereqs if not prereq_satisfied(state, graph, p, lang))
        return unmet, len(prereqs), graph["skills"][sid]["order"]

    return min((sid for sid in locked if graph["skills"][sid]["tier"] == tier), key=key)
