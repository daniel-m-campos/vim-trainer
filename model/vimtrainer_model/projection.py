"""Projection for the stats chart: polynomial fit of recent attempt times.

A least-squares polynomial (linear below 15 points, quadratic from 15) is fit over the
last 30 counted correct attempts' ``ms``. The line is shown only when R^2 >= 0.5, and the
caption reports how many more attempts until the fit crosses ``target_ms``, looking up to
30 attempts ahead.

Example
-------
>>> from vimtrainer_model.graph import load_graph
>>> from vimtrainer_model.state import new_state
>>> projection(new_state(load_graph()), "t.quote", "python")
{'fit': 'none', 'attemptsToTarget': None, 'r2': 0.0}
"""

from __future__ import annotations

from vimtrainer_model.constants import (
    PROJECTION_AHEAD,
    PROJECTION_MIN_N,
    PROJECTION_MIN_R2,
    PROJECTION_QUADRATIC_N,
    PROJECTION_WINDOW,
)
from vimtrainer_model.graph import record_skills, target_ms
from vimtrainer_model.state import is_counted

_NONE = {"fit": "none", "attemptsToTarget": None, "r2": 0.0}


# Public Functions =================================================================================

def projection(state: dict, skill_id: str, lang: str, graph: dict | None = None) -> dict:
    """Fit recent times and estimate attempts to reach the target.

    Parameters
    ----------
    state : dict
        ModelState.
    skill_id, lang : str
        The (skill, language) to project.
    graph : dict | None
        Skill graph, for per-skill target constants and composite tags; defaults to
        1200 + 180 * par and single-skill records.

    Returns
    -------
    dict
        ``{"fit": "none" | "linear" | "quadratic", "attemptsToTarget": int | None, "r2": float}``.
    """
    ys = recent_times(state, skill_id, lang, graph)
    if len(ys) < PROJECTION_MIN_N:
        return dict(_NONE)
    degree = 2 if len(ys) >= PROJECTION_QUADRATIC_N else 1
    coeffs = fit_polynomial(ys, degree)
    r2 = r_squared(ys, coeffs)
    if r2 < PROJECTION_MIN_R2:
        return {"fit": "none", "attemptsToTarget": None, "r2": r2}
    fit = "quadratic" if degree == 2 else "linear"
    st = state["skills"].get(skill_id, {}).get(lang)
    if st is None or st["parEma"] is None:
        return {"fit": fit, "attemptsToTarget": None, "r2": r2}
    target = target_ms(graph, skill_id, st["parEma"])
    return {"fit": fit, "attemptsToTarget": _attempts_to_target(coeffs, len(ys), target), "r2": r2}


def recent_times(state: dict, skill_id: str, lang: str, graph: dict | None = None) -> list[float]:
    """``ms`` of the last 30 counted, correct attempts of (skill, lang), oldest first."""
    times: list[float] = []
    for record in reversed(state["log"]):
        if len(times) >= PROJECTION_WINDOW:
            break
        if record["lang"] != lang or not record["ok"] or not is_counted(record):
            continue
        skills = record_skills(graph, record) if graph is not None else record["skill"].split("+")
        if skill_id not in skills:
            continue
        times.append(record["ms"])
    times.reverse()
    return times


def fit_polynomial(ys: list[float], degree: int) -> list[float]:
    """Least-squares coefficients ``[c0, c1, (c2)]`` for x = 0..n-1 via normal equations."""
    size = degree + 1
    matrix = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for i, y in enumerate(ys):
        powers = _powers(float(i), 2 * degree)
        for row in range(size):
            rhs[row] += powers[row] * y
            for col in range(size):
                matrix[row][col] += powers[row + col]
    return _solve(matrix, rhs)


def evaluate(coeffs: list[float], x: float) -> float:
    """Value of the polynomial at x."""
    total = 0.0
    power = 1.0
    for coeff in coeffs:
        total += coeff * power
        power = power * x
    return total


def r_squared(ys: list[float], coeffs: list[float]) -> float:
    """Coefficient of determination; 0 when the data has no variance."""
    mean = 0.0
    for y in ys:
        mean += y
    mean = mean / len(ys)
    ss_tot = 0.0
    ss_res = 0.0
    for i, y in enumerate(ys):
        residual = y - evaluate(coeffs, float(i))
        ss_res += residual * residual
        ss_tot += (y - mean) * (y - mean)
    if ss_tot <= 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


# Private Functions ================================================================================

def _powers(x: float, highest: int) -> list[float]:
    powers = [1.0]
    for _ in range(highest):
        powers.append(powers[-1] * x)
    return powers


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (same operation order as the TS mirror)."""
    size = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(size):
        pivot = col
        for row in range(col + 1, size):
            if abs(a[row][col]) > abs(a[pivot][col]):
                pivot = row
        a[col], a[pivot] = a[pivot], a[col]
        if a[col][col] == 0:
            return [0.0] * size
        for row in range(col + 1, size):
            factor = a[row][col] / a[col][col]
            for k in range(col, size + 1):
                a[row][k] -= factor * a[col][k]
    coeffs = [0.0] * size
    for row in range(size - 1, -1, -1):
        total = a[row][size]
        for k in range(row + 1, size):
            total -= a[row][k] * coeffs[k]
        coeffs[row] = total / a[row][row]
    return coeffs


def _attempts_to_target(coeffs: list[float], n: int, target: float) -> int | None:
    """0 if the fit is already at target, else the first step ahead (<= 30) that reaches it."""
    last = float(n - 1)
    if evaluate(coeffs, last) <= target:
        return 0
    for step in range(1, PROJECTION_AHEAD + 1):
        if evaluate(coeffs, last + step) <= target:
            return step
    return None
