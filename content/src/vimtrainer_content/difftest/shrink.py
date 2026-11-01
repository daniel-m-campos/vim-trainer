"""Minimise a diverging case to the fewest keys that still diverge.

``diverges`` takes a batch of cases and says, per case, whether Neovim and the browser
still disagree (``run.py`` runs both sides). Steps, all within ``max_runs`` case runs:

1. confirm the original diverges (else it was flaky: return None);
2. shortest diverging prefix, every prefix in one batch;
3. greedy single-token deletion, one batch per pass, until no deletion diverges;
4. confirm the result twice; if that fails, fall back to the original (confirmed twice too).

Candidates that match ``generate.FORBIDDEN`` are never run.

Examples
--------
>>> from vimtrainer_content.difftest.generate import Buffer, Case
>>> case = Case(0, 1, Buffer("b", "python", ["x"], (1, 0), {}), "jjUkk")
>>> minimise(case, lambda cases: ["U" in c.keys for c in cases]).keys
'U'
"""

import dataclasses
from collections.abc import Callable

from vimtrainer_content.difftest.generate import FORBIDDEN, Case, tokenize

type Diverges = Callable[[list[Case]], list[bool]]

_CONFIRMATIONS = 2


# Public Functions =================================================================================


def minimise(case: Case, diverges: Diverges, max_runs: int = 120) -> Case | None:
    """Shortest variant of ``case`` that still diverges, or None if the case no longer diverges.

    Parameters
    ----------
    case
        A case whose sides differed.
    diverges
        Batch predicate: one bool per case, True when the sides still differ.
    max_runs
        Budget of case runs across all ``diverges`` calls (confirmation reserved).

    Returns
    -------
    Case | None
        The minimised case (same index, seed and buffer), the original if the minimised
        one does not reproduce, or None when the original does not reproduce (flaky).
    """
    budget = _Budget(max_runs - 1 - 2 * _CONFIRMATIONS)
    if not diverges([case])[0]:
        return None
    tokens = tokenize(case.keys)
    tokens = _shortest_prefix(case, tokens, diverges, budget)
    tokens = _drop_tokens(case, tokens, diverges, budget)
    best = _with_keys(case, tokens)
    if best.keys != case.keys and all(diverges([best] * _CONFIRMATIONS)):
        return best
    return case if all(diverges([case] * _CONFIRMATIONS)) else None


# Private Functions ================================================================================


@dataclasses.dataclass
class _Budget:
    left: int

    def take(self, wanted: list[Case]) -> list[Case]:
        """As many of ``wanted`` as the budget allows, charged."""
        granted = wanted[: max(self.left, 0)]
        self.left -= len(granted)
        return granted


def _with_keys(case: Case, tokens: list[str]) -> Case:
    return dataclasses.replace(case, keys="".join(tokens))


def _allowed(tokens: list[str]) -> bool:
    return bool(tokens) and not FORBIDDEN.search("".join(tokens))


def _shortest_prefix(case: Case, tokens: list[str], diverges: Diverges, budget: _Budget) -> list[str]:
    prefixes = [tokens[:k] for k in range(1, len(tokens)) if _allowed(tokens[:k])]
    batch = budget.take([_with_keys(case, p) for p in prefixes])
    if not batch:
        return tokens
    for prefix, hit in zip(prefixes, diverges(batch)):
        if hit:
            return prefix
    return tokens


def _drop_tokens(case: Case, tokens: list[str], diverges: Diverges, budget: _Budget) -> list[str]:
    while len(tokens) > 1:
        candidates = [tokens[:i] + tokens[i + 1:] for i in range(len(tokens))]
        candidates = [c for c in candidates if _allowed(c)]
        batch = budget.take([_with_keys(case, c) for c in candidates])
        if not batch:
            return tokens
        hits = [c for c, hit in zip(candidates, diverges(batch)) if hit]
        if not hits:
            return tokens
        tokens = hits[0]
    return tokens
