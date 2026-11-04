"""Measurement extractors. Pure functions of (x, y[, conditions]); no simulator, LLM or I/O involved.

Conventions
- x = swept voltage (V), strictly increasing. y = drain current INTO the drain (A).
- Id-Vg: x = VGS.  Id-Vd: x = VDS.
- Every extractor either returns a value with diagnostics or raises MeasurementError(code, detail).
  Nothing is ever defaulted, clipped or guessed.

Definitions (documented so results are reproducible and comparable)
- ID   : the validated drain-current curve itself.
- GM   : maximum of dId/dVGS over the sweep (np.gradient, 2nd-order accurate incl. edges, non-uniform grids OK).
         Reports the VGS of the maximum and flags a maximum sitting on the sweep edge (not a true peak).
- GDS  : dId/dVDS at the LAST point of the Id-Vd sweep (output conductance at the end bias), 2nd-order edge.
- VTH  : constant-current method. VGS where Id = ic * W/L (ic default 100 nA), first upward crossing,
         linear interpolation of log(Id) between the bracketing points.
- SS   : subthreshold swing = 1/slope of a least-squares line of log10(Id) vs VGS over the window
         ic*W/L / 10^decades <= Id <= ic*W/L (stays below the VTH current). Reports mV/decade, R^2, window.
         Refuses on too few points, too narrow a window, non-contiguous window, or R^2 below r2_min.
- ION / IOFF : Id at an EXPLICIT VGS (log-linear interpolation when all currents are positive, else linear).
"""
from __future__ import annotations

import numpy as np

from tinyspice.measurements.result import MeasurementError


def prepare(x, y) -> tuple[np.ndarray, np.ndarray]:
    try:
        xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    except (TypeError, ValueError) as e:
        raise MeasurementError("INVALID_DATA", f"not numeric: {e}")
    if xa.ndim != 1 or ya.shape != xa.shape:
        raise MeasurementError("INVALID_DATA", f"bad shapes x{xa.shape} y{ya.shape}")
    if len(xa) < 3:
        raise MeasurementError("INVALID_DATA", f"need >= 3 points, got {len(xa)}")
    if not (np.isfinite(xa).all() and np.isfinite(ya).all()):
        raise MeasurementError("INVALID_DATA", "non-finite values")
    if not (np.diff(xa) > 0).all():
        raise MeasurementError("INVALID_DATA", "sweep axis not strictly increasing")
    return xa, ya


def id_at(x, y, v: float, tol: float = 1e-9) -> tuple[float, dict]:
    xa, ya = prepare(x, y)
    if v < xa[0] - tol or v > xa[-1] + tol:
        raise MeasurementError("OUT_OF_RANGE", f"bias {v} V outside sweep [{xa[0]}, {xa[-1]}]")
    v = min(max(v, xa[0]), xa[-1])
    if (ya > 0).all():
        val = float(10 ** np.interp(v, xa, np.log10(ya)))
        return val, {"interpolation": "log-linear"}
    return float(np.interp(v, xa, ya)), {"interpolation": "linear"}


def gm_max(x, y) -> tuple[float, dict]:
    xa, ya = prepare(x, y)
    g = np.gradient(ya, xa, edge_order=2)
    i = int(np.argmax(g))
    return float(g[i]), {"vgs_at_max_v": float(xa[i]), "max_on_sweep_edge": i in (0, len(xa) - 1),
                         "n_points": int(len(xa))}


def gds_end(x, y) -> tuple[float, dict]:
    xa, ya = prepare(x, y)
    g = np.gradient(ya, xa, edge_order=2)
    return float(g[-1]), {"vds_v": float(xa[-1]), "gds_max_s": float(g.max()), "n_points": int(len(xa))}


def vth_constant_current(x, y, width_um: float, length_um: float, ic_a: float = 1e-7) -> tuple[float, dict]:
    xa, ya = prepare(x, y)
    target = ic_a * width_um / length_um
    above = np.nonzero(ya >= target)[0]
    if len(above) == 0:
        raise MeasurementError("NOT_CROSSED", f"Id never reaches {target:.3e} A (max {ya.max():.3e} A)")
    i = int(above[0])
    if i == 0:
        raise MeasurementError("ALREADY_ABOVE", f"Id at first point ({ya[0]:.3e} A) already >= {target:.3e} A; cannot bracket")
    y0, y1 = ya[i - 1], ya[i]
    if y0 > 0 and y1 > 0:
        frac = (np.log(target) - np.log(y0)) / (np.log(y1) - np.log(y0))
        interp = "log-linear"
    else:
        frac = (target - y0) / (y1 - y0)
        interp = "linear"
    vth = float(xa[i - 1] + frac * (xa[i] - xa[i - 1]))
    return vth, {"target_current_a": float(target), "bracket_vgs_v": [float(xa[i - 1]), float(xa[i])],
                 "interpolation": interp, "recrosses_below_target": bool((ya[i:] < target).any())}


def ss_fit(x, y, width_um: float, length_um: float, ic_a: float = 1e-7, decades: float = 3.0,
           min_points: int = 4, min_span_decades: float = 1.0, r2_min: float = 0.995) -> tuple[float, dict]:
    xa, ya = prepare(x, y)
    i_hi = ic_a * width_um / length_um
    i_lo = i_hi / 10**decades
    idx = np.nonzero((ya >= i_lo) & (ya <= i_hi) & (ya > 0))[0]
    if len(idx) < min_points:
        raise MeasurementError("INSUFFICIENT_POINTS",
                               f"{len(idx)} points in window [{i_lo:.2e}, {i_hi:.2e}] A; need >= {min_points}")
    if not (np.diff(idx) == 1).all():
        raise MeasurementError("NON_CONTIGUOUS_WINDOW", "subthreshold window is not one contiguous run of points")
    lx, ly = xa[idx], np.log10(ya[idx])
    span = float(ly.max() - ly.min())
    if span < min_span_decades:
        raise MeasurementError("WINDOW_TOO_NARROW", f"window spans {span:.2f} decades; need >= {min_span_decades}")
    slope, icpt = np.polyfit(lx, ly, 1)
    if slope <= 0:
        raise MeasurementError("NON_POSITIVE_SLOPE", f"log10(Id) vs VGS slope {slope:.3g} <= 0")
    pred = slope * lx + icpt
    ss_res, ss_tot = float(((ly - pred) ** 2).sum()), float(((ly - ly.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    if r2 < r2_min:
        raise MeasurementError("POOR_FIT", f"R^2 = {r2:.4f} < {r2_min}; subthreshold region is not exponential enough")
    return float(1000.0 / slope), {"r2": float(r2), "n_points": int(len(idx)), "span_decades": span,
                                   "window_vgs_v": [float(lx[0]), float(lx[-1])],
                                   "window_current_a": [float(i_lo), float(i_hi)]}
