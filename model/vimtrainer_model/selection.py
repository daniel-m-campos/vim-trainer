"""Choosing the focus skill, the warm-up skill and the next exercise.

Focus: with probability 0.2 a due review skill. Otherwise a low-weight skill (language
weight <= 0.3) absent from the last 11 picks is picked outright (starvation guard). Otherwise
the in-rotation skills are filtered (no 4th pick in a row; no skill with 4 of the last 9
picks, so none exceeds 4 of any 10) and one of the 3 weakest by language-weighted confidence
is drawn with weight ``(max priority of the three - priority) + 0.1``, so the weakest is the
most likely pick but not a certain one. Each filter is skipped when it would leave nothing.
Exercise: from the focus skill's pool, 1 in 5 draws is a composite (an exercise tagging the
focus skill plus other unlocked skills) when 2+ unlocked skills are above 0.8 confidence;
other draws use single-skill exercises. Exercises among the last 50 are avoided, and the
draw is weighted by the tagged skills' language weights.

Index shape accepted by ``choose_exercise`` (build/index.json)::

    {"langs": {"python": {"t.quote": {"ids": ["py/t.quote/0001",
                                               {"id": "py/x/0007", "skills": ["t.quote", "m.find"]}]}}}}

``index[lang][skill]`` (without ``langs``) and a bare list instead of ``{"ids": [...]}``
are accepted too; ``exercises`` is an alias of ``ids``.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> from vimtrainer_model.state import new_state
>>> graph = load_graph()
>>> choose_focus(new_state(graph), "python", graph, 0)
'f.modes'
"""

from vimtrainer_model.constants import (
    COMPOSITE_CONF,
    COMPOSITE_P,
    FOCUS_CANDIDATES,
    FOCUS_FLOOR,
    IN_ROTATION,
    LOW_WEIGHT,
    MAX_STREAK,
    REVIEW_P,
    SHARE_MAX,
    SHARE_WINDOW,
    STARVE_WINDOW,
    Status,
)
from vimtrainer_model.graph import lang_weight, order_of, skill_ids
from vimtrainer_model.rng import Mulberry32, derive_seed
from vimtrainer_model.state import clone_state, is_eligible, prepare

# Public Functions =================================================================================

def choose_focus(state: dict, lang: str, graph: dict, now: float, seed: int | None = None) -> str | None:
    """Pick the skill to drill next.

    Parameters
    ----------
    state : dict
        ModelState (not modified; unlocks and due reviews are evaluated on a copy).
    lang : str
        Current language.
    graph : dict
        Skill graph.
    now : float
        Current time in seconds.
    seed : int | None
        RNG seed (first draw: review roll; second draw: the weighted pick among the
        weakest); defaults to ``derive_seed(len(log), now)``.

    Returns
    -------
    str | None
        Skill id, or None when no skill is eligible.
    """
    view = clone_state(state)
    prepare(view, graph, lang, now)
    rng = Mulberry32(derive_seed(len(state["log"]), now) if seed is None else seed)
    roll = rng.next()
    eligible = [sid for sid in skill_ids(graph) if is_eligible(graph, sid, lang)]
    due = _due_reviews(view, graph, lang, eligible)
    if due and roll < REVIEW_P:
        return due[0]
    rotation = [sid for sid in eligible if view["skills"][sid][lang]["status"] in IN_ROTATION]
    if rotation:
        return _pick_rotation(view, graph, lang, rotation, rng.next())
    if due:
        return due[0]
    mastered = [sid for sid in eligible if view["skills"][sid][lang]["status"] == Status.MASTERED]
    if not mastered:
        return None
    return min(mastered, key=lambda sid: (view["skills"][sid][lang]["confidence"], order_of(graph, sid)))


def choose_warmup(state: dict, lang: str, graph: dict) -> str | None:
    """Mastered skill with the highest confidence in this language (warm-ups are not counted)."""
    mastered = [
        sid
        for sid in skill_ids(graph)
        if is_eligible(graph, sid, lang)
        and state["skills"].get(sid, {}).get(lang, {}).get("status") == Status.MASTERED
    ]
    if not mastered:
        return None
    return min(mastered, key=lambda sid: (-state["skills"][sid][lang]["confidence"], order_of(graph, sid)))


def choose_exercise(
    state: dict, skill_id: str, lang: str, index: dict, rng_seed: int, graph: dict | None = None
) -> str | None:
    """Pick an exercise id from the focus skill's pool.

    Parameters
    ----------
    state : dict
        ModelState (read only).
    skill_id : str
        Focus skill.
    lang : str
        Current language.
    index : dict
        Exercise index (see module docstring).
    rng_seed : int
        Seed for the composite roll and the weighted draw.
    graph : dict | None
        Skill graph; when given, candidates are weighted by the product of their tagged
        skills' language weights.

    Returns
    -------
    str | None
        Exercise id, or None when the pool is empty.
    """
    pool = exercise_pool(index, lang, skill_id)
    if not pool:
        return None
    rng = Mulberry32(rng_seed)
    composite_roll = rng.next()
    singles = [entry for entry in pool if len(entry["skills"]) == 1]
    composites = _composites(state, pool, skill_id, lang)
    if composites and composite_roll < COMPOSITE_P and _composite_ready(state, lang):
        pool = composites
    else:
        pool = singles or composites or pool
    candidates = _fresh(pool, state["recent"])
    weights = [_exercise_weight(graph, entry, lang) for entry in candidates]
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(candidates)
        total = float(len(candidates))
    draw = rng.next() * total
    running = 0.0
    for entry, weight in zip(candidates, weights):
        running += weight
        if draw < running:
            return entry["id"]
    return candidates[-1]["id"]


def exercise_pool(index: dict, lang: str, skill_id: str) -> list[dict]:
    """Normalised ``[{"id", "skills"}]`` pool for (lang, skill) from an index."""
    by_lang = index.get("langs", index).get(lang) or {}
    if isinstance(by_lang.get("skills"), dict):
        by_lang = by_lang["skills"]  # build/index.json: {langs: {lang: {skills: {skill: {...}}}}}
    raw = by_lang.get(skill_id) or []
    if isinstance(raw, dict):
        raw = raw.get("ids", raw.get("exercises", []))
    pool = []
    for item in raw:
        if isinstance(item, str):
            pool.append({"id": item, "skills": [skill_id]})
            continue
        skills = list(item.get("skills") or [skill_id])
        if skill_id not in skills:
            skills.insert(0, skill_id)
        pool.append({"id": item["id"], "skills": skills})
    return pool


# Private Functions ================================================================================

def _pick_rotation(state: dict, graph: dict, lang: str, rotation: list[str], draw: float) -> str:
    """Starvation guard, then streak and share-cap filters, then a weighted draw among the weakest."""
    history = state["focusHistory"]
    starved = _starved(graph, lang, rotation, history)
    if starved:
        return min(starved, key=lambda sid: order_of(graph, sid))
    candidates = _without(rotation, {_streak_skill(history)})
    candidates = _without(candidates, _capped(history))
    ranked = sorted(candidates, key=lambda sid: (_priority(state, graph, sid, lang), order_of(graph, sid)))
    ranked = ranked[:FOCUS_CANDIDATES]
    priorities = [_priority(state, graph, sid, lang) for sid in ranked]
    top = max(priorities)
    weights = [top - p + FOCUS_FLOOR for p in priorities]
    total = 0.0
    for weight in weights:
        total += weight
    target = draw * total
    running = 0.0
    for sid, weight in zip(ranked, weights):
        running += weight
        if target < running:
            return sid
    return ranked[-1]


def _starved(graph: dict, lang: str, rotation: list[str], history: list[str]) -> list[str]:
    """Low-weight rotation skills not picked in the last ``STARVE_WINDOW - 1`` picks."""
    if len(history) < STARVE_WINDOW - 1:
        return []
    recent = set(history[-(STARVE_WINDOW - 1):])
    return [sid for sid in rotation if lang_weight(graph, sid, lang) <= LOW_WEIGHT and sid not in recent]


def _capped(history: list[str]) -> set[str]:
    """Skills that would exceed ``SHARE_MAX`` of the last ``SHARE_WINDOW`` picks if picked again."""
    tail = history[-(SHARE_WINDOW - 1):]
    return {sid for sid in set(tail) if tail.count(sid) >= SHARE_MAX}


def _without(items: list[str], drop: set) -> list[str]:
    """Items not in ``drop``, or all items when that would leave none."""
    kept = [sid for sid in items if sid not in drop]
    return kept or items


def _priority(state: dict, graph: dict, skill_id: str, lang: str) -> float:
    """Confidence deficit scaled by language weight: ``1 - (1 - confidence) * weight``."""
    conf = state["skills"][skill_id][lang]["confidence"]
    return 1.0 - (1.0 - conf) * lang_weight(graph, skill_id, lang)


def _due_reviews(state: dict, graph: dict, lang: str, eligible: list[str]) -> list[str]:
    """Review-status skills, most overdue first."""
    due = [sid for sid in eligible if state["skills"][sid][lang]["status"] == Status.REVIEW]
    return sorted(due, key=lambda sid: (state["skills"][sid][lang]["nextReview"] or 0, order_of(graph, sid)))


def _streak_skill(history: list[str]) -> str | None:
    """The skill picked in each of the last 3 attempts, if any."""
    tail = history[-MAX_STREAK:]
    if len(tail) < MAX_STREAK or len(set(tail)) != 1:
        return None
    return tail[0]


def _unlocked(state: dict, skill_id: str, lang: str) -> dict | None:
    st = state["skills"].get(skill_id, {}).get(lang)
    if st is None or st["status"] == Status.LOCKED:
        return None
    return st


def _composite_ready(state: dict, lang: str) -> bool:
    """Two or more unlocked skills above 0.8 confidence in this language."""
    count = 0
    for skill_id in state["skills"]:
        st = _unlocked(state, skill_id, lang)
        if st is not None and st["confidence"] > COMPOSITE_CONF:
            count += 1
    return count >= 2


def _composites(state: dict, pool: list[dict], skill_id: str, lang: str) -> list[dict]:
    """Multi-skill exercises whose other skills are all unlocked."""
    return [
        entry
        for entry in pool
        if len(entry["skills"]) >= 2
        and all(_unlocked(state, other, lang) is not None for other in entry["skills"] if other != skill_id)
    ]


def _fresh(pool: list[dict], recent: list[str]) -> list[dict]:
    """Entries not in the recent list; if none, the one seen longest ago."""
    seen = set(recent)
    fresh = [entry for entry in pool if entry["id"] not in seen]
    if fresh:
        return fresh
    last_seen = {ex_id: position for position, ex_id in enumerate(recent)}
    return [min(pool, key=lambda entry: last_seen[entry["id"]])]


def _exercise_weight(graph: dict | None, entry: dict, lang: str) -> float:
    """Product of the tagged skills' language weights."""
    weight = 1.0
    for skill_id in entry["skills"]:
        weight *= lang_weight(graph, skill_id, lang)
    return weight
