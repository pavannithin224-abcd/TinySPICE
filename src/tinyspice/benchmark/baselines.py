"""Baseline configurations A (direct LLM-to-tool) and B (structured agent), exactly as defined in docs/BENCH_PREREG.md."""
from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import ValidationError

from tinyspice.agent import interpret_request
from tinyspice.benchmark.bench import Outcome, make_sim
from tinyspice.executor import _solver_floor, execute
from tinyspice.measurements import extract_all
from tinyspice.schemas import ExperimentSpec

IDVG_OK = ("VTH", "GM", "SS", "ION", "IOFF", "ID")
IDVD_OK = ("ID", "GDS")
DEFAULT_MODEL = "sky130_fd_pr__nfet_01v8"


def parse_first_json(texts) -> dict | None:
    """A uses the model's FIRST response only (no repair call). Malformed -> None."""
    if not texts:
        return None
    try:
        d = json.loads(texts[0])
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) else None


def lenient_spec(raw: dict) -> ExperimentSpec | None:
    """A's tool wrapper. Fixed defaults for anything unstated; contradictions resolved silently; stated budget limits ignored."""
    r = {k: v for k, v in raw.items() if v is not None}
    analysis = r.get("analysis") if r.get("analysis") in ("idvg", "idvd") else "idvg"
    try:
        start, stop = float(r.get("sweep_start", 0.0)), float(r.get("sweep_stop", 1.8))
        if stop <= start:
            stop = start + 1.8
        step, pts = r.get("sweep_step"), r.get("sweep_points")
        if step is not None and pts is not None:
            pts = None                                         # step wins over points
        if step is None and pts is None:
            step = 0.02
        if step is not None:
            step = float(step) if float(step) > 0 else 0.02
            n = max(1, int((stop - start) / step + 1e-9))      # a step that does not divide the range is truncated to the nearest multiple
            stop = round(start + n * step, 9)
            sweep = {"start": start, "stop": stop, "step": step}
            n_points = n + 1
        else:
            n_points = max(2, int(pts))
            sweep = {"start": start, "stop": stop, "points": n_points}
        ok_set = IDVG_OK if analysis == "idvg" else IDVD_OK
        meas = [m for m in dict.fromkeys(r.get("measurements") or []) if m in ok_set] or [("VTH" if analysis == "idvg" else "ID")]
        d = {"device_type": "nmos", "model_name": DEFAULT_MODEL, "width_um": float(r.get("width_um", 1.0)) or 1.0,
             "length_um": float(r.get("length_um", 0.18)) or 0.18, "temperature_c": float(r.get("temperature_c", 27.0)),
             "analysis": analysis, "sweep": sweep, "measurements": meas, "budget": {"max_points": n_points}}
        echo = {k: r[k] for k in ("max_points", "max_runtime_s", "max_tool_calls", "max_retries") if k in r}   # echoed, NEVER enforced (see run_config_a)
        if analysis == "idvg":
            d["vds_v"] = float(r.get("vds_v", 1.8))            # a fixed VGS on an Id-Vg sweep is silently dropped
        else:
            d["vgs_v"] = float(r.get("vgs_v", 0.9))
        clamp = lambda v: min(max(float(v), start), stop)      # noqa: E731
        if "ION" in meas:
            d["ion_vgs_v"] = clamp(r.get("ion_vgs_v", stop))
        if "IOFF" in meas:
            d["ioff_vgs_v"] = clamp(r.get("ioff_vgs_v", start))
        try:
            return ExperimentSpec.model_validate({**d, "budget": {**d["budget"], **echo}})
        except ValidationError:
            return ExperimentSpec.model_validate(d)            # an unusable stated limit is dropped, not enforced
    except (ValueError, TypeError, ValidationError):
        return None


def _values(meas) -> dict:
    return {k: {"ok": m.ok, "value": m.value, "code": m.error_code} for k, m in (meas or {}).items()}


def run_config_a(task: dict, texts, workdir: Path) -> Outcome:
    raw = parse_first_json(texts)
    if raw is None:
        return Outcome("A", "failed", notes="malformed tool call")
    spec = lenient_spec(raw)
    if spec is None:
        return Outcome("A", "failed", notes="tool call could not be turned into a runnable request")
    sim = make_sim(task)
    t0 = time.monotonic()
    res = sim.run(spec, Path(workdir) / "sim", timeout_s=300.0)   # one call; stated limits are echoed in the spec but NOT enforced (explicit timeout)
    dt = time.monotonic() - t0
    if not res.ok:
        return Outcome("A", "failed", spec=spec.model_dump(mode="json"), wallclock_s=dt, sim_calls=sim.calls, notes=str(res.error_code))
    meas = extract_all(spec, res.x, res.y, floor_a=_solver_floor(spec, res))
    return Outcome("A", "successful", spec=spec.model_dump(mode="json"), values=_values(meas), points=int(len(res.x)),
                   wallclock_s=dt, sim_calls=sim.calls, notes="naive: simulator returned data")


def run_config_b(task: dict, provider, limits, workdir: Path) -> Outcome:
    r = interpret_request(task["text"], provider, ground=False)
    if not r.ok:
        return Outcome("B", "rejected_invalid_input", notes="; ".join(f"{e['loc']}: {e['msg']}" for e in r.errors)[:300])
    sim = make_sim(task)
    t0 = time.monotonic()
    rec = execute(r.spec, limits, sim, Path(workdir), strategy="uniform")
    dt = time.monotonic() - t0
    pts = int(len(rec.sim.x)) if (rec.sim is not None and rec.sim.ok and rec.sim.x is not None) else 0
    return Outcome("B", rec.status.value, spec=r.spec.model_dump(mode="json"), values=_values(rec.measurements), points=pts,
                   wallclock_s=dt, sim_calls=sim.calls, run_dir=str(rec.run_dir) if rec.run_dir else None, notes=rec.message[:200])
