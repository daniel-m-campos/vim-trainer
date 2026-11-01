"""vim-trainer adaptive model, Python mirror of app/src/model/model.ts.

Interface (snake_case here, camelCase in TypeScript):

- ``new_state(graph)``
- ``apply_attempt(state, record, graph) -> state``
- ``apply_placement(state, records, graph) -> state``
- ``choose_focus(state, lang, graph, now, seed=None) -> skill_id``
- ``choose_exercise(state, skill_id, lang, index, rng_seed, graph=None) -> exercise_id``
- ``projection(state, skill_id, lang, graph=None) -> {fit, attemptsToTarget, r2}``
- ``session_summary(state, since_t, graph) -> {improved, mastered, unlocked, tip}``

Nothing reads the clock or global randomness: time and seeds are arguments.

Example
-------
>>> from vimtrainer_model import load_graph, new_state, choose_focus
>>> graph = load_graph()
>>> choose_focus(new_state(graph), "python", graph, 1760200000) in ("f.modes", "f.hjkl", "f.undo")
True
"""

from vimtrainer_model.attempt import apply_attempt, rebuild
from vimtrainer_model.graph import apply_profile, load_graph
from vimtrainer_model.placement import apply_placement
from vimtrainer_model.projection import projection
from vimtrainer_model.rng import Mulberry32, derive_seed
from vimtrainer_model.selection import choose_exercise, choose_focus, choose_warmup, exercise_pool
from vimtrainer_model.state import diagnose, new_state
from vimtrainer_model.summary import session_summary

__all__ = [
    "Mulberry32",
    "apply_attempt",
    "apply_placement",
    "apply_profile",
    "choose_exercise",
    "choose_focus",
    "choose_warmup",
    "derive_seed",
    "diagnose",
    "exercise_pool",
    "load_graph",
    "new_state",
    "projection",
    "rebuild",
    "session_summary",
]
