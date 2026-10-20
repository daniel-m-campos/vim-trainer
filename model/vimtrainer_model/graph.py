"""Skill graph access: loading, ordering, language weights, targets and profiles.

The graph is the JSON produced by model/gen_graph.py. Skills are stored as an ordered
object keyed by id; every node carries ``order``, ``tier``, ``prereqs``, ``targetBase``,
``perKey``, ``enabled``, ``emulator`` and ``langWeights``.

Example
-------
>>> graph = load_graph()
>>> target_ms(graph, "t.quote", 12)
3360
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Final

from vimtrainer_model.constants import DEFAULT_PER_KEY, DEFAULT_TARGET_BASE

GRAPH_PATH: Final = Path(__file__).resolve().parent.parent / "skill-graph.json"
COMPOSITE_SEP: Final = "+"


# Public Functions =================================================================================

def load_graph(path: str | Path | None = None) -> dict:
    """Load the skill graph JSON (defaults to model/skill-graph.json)."""
    return json.loads(Path(path or GRAPH_PATH).read_text())


def skill_ids(graph: dict) -> list[str]:
    """Skill ids sorted by (tier, document order)."""
    skills = graph["skills"]
    return sorted(skills, key=lambda sid: (skills[sid]["tier"], skills[sid]["order"]))


def order_of(graph: dict, skill_id: str) -> int:
    """Document order of a skill, used to break ties deterministically."""
    return graph["skills"][skill_id]["order"]


def is_enabled(graph: dict, skill_id: str) -> bool:
    """Whether the skill may ever become active under the current profile."""
    return bool(graph["skills"][skill_id].get("enabled", True))


def lang_weight(graph: dict | None, skill_id: str, lang: str) -> float:
    """Per-language weight of a skill; 1.0 when unknown."""
    if graph is None:
        return 1.0
    node = graph["skills"].get(skill_id)
    if node is None:
        return 1.0
    return float(node.get("langWeights", {}).get(lang, 1.0))


def target_ms(graph: dict | None, skill_id: str, par: float | None) -> float:
    """Target time for a skill at a given par: ``targetBase + perKey * par``."""
    node = (graph or {}).get("skills", {}).get(skill_id, {})
    base = node.get("targetBase", DEFAULT_TARGET_BASE)
    per_key = node.get("perKey", DEFAULT_PER_KEY)
    return base + per_key * (par or 0)


def record_skills(graph: dict, record: dict) -> list[str]:
    """Skills credited by a record: ``skill`` split on '+', unknown ids dropped."""
    seen: list[str] = []
    for skill_id in record["skill"].split(COMPOSITE_SEP):
        if skill_id in graph["skills"] and skill_id not in seen:
            seen.append(skill_id)
    return seen


def apply_profile(graph: dict, profile: str = "neovim", extra_tiers: tuple[int, ...] = ()) -> dict:
    """Return a copy of the graph with ``enabled`` set for an editor profile.

    Parameters
    ----------
    graph : dict
        Skill graph.
    profile : str
        "neovim", "vscodevim" or "ideavim". Skills flagged ``none`` for the profile are
        disabled; ``partial`` skills stay enabled.
    extra_tiers : tuple[int, ...]
        Tiers above 10 the user turned on (11 = buffers/windows, 12 = Neovim-native).
        Tier 12 is only ever enabled for the neovim profile.

    Returns
    -------
    dict
        A new graph; the input is not modified.
    """
    result = copy.deepcopy(graph)
    for node in result["skills"].values():
        tier_on = node["tier"] <= 10 or node["tier"] in extra_tiers
        supported = node["emulator"].get(profile, "full") != "none"
        node["enabled"] = tier_on and supported
    return result
