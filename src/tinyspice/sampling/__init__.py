"""Sweep-point selection. Pure functions of numbers; no simulator, no LLM, no I/O.

uniform_grid : N evenly spaced points (the baseline).
pilot_grid   : a coarse uniform grid plus FORCED points (the bias points ION/IOFF must be evaluated at exactly).
refine_points: given a pilot curve, choose `n_new` extra points by greedy bisection of the interval with the largest
               linear-interpolation error indicator  h^2 * max|f''|, where f = log10(Id) is modelled by a cubic spline
               through the pilot data. log10 because Id spans ~10 decades: curvature of linear Id would be blind to the
               subthreshold knee. Deterministic: ties broken by position.
"""
from __future__ import annotations

import heapq

import numpy as np
from scipy.interpolate import CubicSpline

_ROUND = 9


def uniform_grid(start: float, stop: float, n: int) -> np.ndarray:
    if n < 2:
        raise ValueError("need at least 2 points")
    return np.round(np.linspace(start, stop, n), _ROUND)


def _merge(base: np.ndarray, extra, tol: float) -> np.ndarray:
    pts = list(base)
    for v in extra:
        if all(abs(v - p) > tol for p in pts):
            pts.append(float(v))
    return np.round(np.array(sorted(pts)), _ROUND)


def pilot_grid(start: float, stop: float, n_pilot: int, forced=(), tol: float = 1e-6) -> np.ndarray:
    """Uniform pilot of n_pilot points; forced points inside [start, stop] are added unless one is already within tol."""
    base = uniform_grid(start, stop, n_pilot)
    inside = [f for f in forced if start - tol <= f <= stop + tol]
    return _merge(base, inside, tol)


def pilot_base(n: int, n_forced: int, frac: float = 0.3, minimum: int = 8) -> int:
    """Uniform pilot size so that pilot + forced <= n, leaving 0 or >= 2 points to refine (a 1-point PWL run is not defined)."""
    base = max(minimum, round(frac * n))
    base = min(base, n - n_forced)
    return base


def window_points(x, y, i_hi: float, *, decades: float = 3.0, target: int = 6, margin: float = 0.1,
                  max_new: int | None = None, floor: float = 1e-18) -> np.ndarray:
    """Measurement-aware placement for the SS extractor: its window is the set of points with Id in [i_hi/10^decades, i_hi]
    (i_hi = vth_ic_a * W/L) and it needs >= 4 of them over >= 1 decade. Estimate that VGS window from the pilot (monotone
    envelope of log10 Id) and add points inside its central (1-2*margin) part until `target` pilot+new points lie there,
    each placed in the middle of the currently largest gap. Returns [] if the pilot does not bracket i_hi."""
    x = np.asarray(x, float)
    f = np.maximum.accumulate(np.log10(np.maximum(np.abs(np.asarray(y, float)), floor)))
    hi_t = float(np.log10(i_hi))
    lo_t = hi_t - decades
    if len(x) < 2 or f[-1] < hi_t or f[0] >= hi_t:
        return np.array([])
    v_hi = float(np.interp(hi_t, f, x))
    v_lo = float(x[0]) if f[0] >= lo_t else float(np.interp(lo_t, f, x))
    w = v_hi - v_lo
    if w <= 0:
        return np.array([])
    a, b = v_lo + margin * w, v_hi - margin * w
    have = [float(v) for v in x if a <= v <= b]
    need = max(0, target - len(have))
    if max_new is not None:
        need = min(need, max_new)
    pts = sorted(set([a, b] + have))
    new: list[float] = []
    for _ in range(need):
        gaps = [(pts[i + 1] - pts[i], -i) for i in range(len(pts) - 1)]
        g, neg_i = max(gaps)
        if g < 2e-4:
            break
        m = 0.5 * (pts[-neg_i] + pts[-neg_i + 1])
        new.append(round(m, _ROUND))
        pts = sorted(pts + [m])
    return np.array(sorted(new))


def refine_points(x, y, n_new: int, *, floor: float = 1e-18, min_gap: float = 1e-4, extra=()) -> np.ndarray:
    """Choose n_new points to add to the pilot data (x strictly increasing, y = Id > 0). Returns sorted new points,
    all distinct from the pilot points. May return fewer than n_new only if every interval is already below min_gap."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if n_new <= 0:
        return np.array([])
    if len(x) < 4 or not (np.diff(x) > 0).all() or not np.isfinite(y).all():
        raise ValueError("pilot data unusable for curvature refinement (need >= 4 strictly increasing finite points)")
    f = np.log10(np.maximum(np.abs(y), floor))
    d2 = CubicSpline(x, f).derivative(2)
    bp = np.array(sorted(set(np.round(np.concatenate([x, np.asarray(extra, float)]), _ROUND))))   # `extra` = points already decided

    def indicator(a: float, b: float) -> float:
        if b - a < 2 * min_gap:
            return 0.0
        m = 0.5 * (a + b)
        return (b - a) ** 2 * max(abs(float(d2(a))), abs(float(d2(m))), abs(float(d2(b))))

    heap = [(-indicator(a, b), a, b) for a, b in zip(bp[:-1], bp[1:])]
    heapq.heapify(heap)
    new: list[float] = []
    while len(new) < n_new and heap:
        neg, a, b = heapq.heappop(heap)
        if neg == 0.0:
            break                                   # nothing left that is worth (or able to be) split
        m = 0.5 * (a + b)
        new.append(round(m, _ROUND))
        heapq.heappush(heap, (-indicator(a, m), a, m))
        heapq.heappush(heap, (-indicator(m, b), m, b))
    return np.array(sorted(new))
