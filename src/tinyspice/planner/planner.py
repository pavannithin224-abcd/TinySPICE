"""Deterministic experiment planner. No LLM involvement: given a validated spec and device limits,
it either returns an ExecutionPlan or raises PlanRejected with a machine-readable code.

An LLM may *propose* a plan later (Phase 4); that proposal must pass the same checks.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel

from tinyspice.errors import PlanRejected
from tinyspice.schemas.device import DeviceLimits
from tinyspice.schemas.spec import AnalysisType, ExperimentSpec, Measurement
from tinyspice.schemas.status import ExperimentStatus

SUPPORTED_STRATEGIES = {"uniform", "curvature", "window"}
MIN_CURVATURE_POINTS = 12


class PlanStep(BaseModel):
    order: int
    action: Literal["generate_netlist", "run_ngspice", "validate_output", "extract_measurements", "persist_provenance"]
    detail: str
    uses_tool_call: bool


class ExecutionPlan(BaseModel):
    spec_sha256: str
    strategy: str
    estimated_points: int
    budget_max_points: int
    estimated_tool_calls: int
    budget_max_tool_calls: int
    resolved_conditions: dict[str, float | str]
    steps: list[PlanStep]
    rationale: list[str]


def spec_hash(spec: ExperimentSpec) -> str:
    canon = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def _reject(code: str, msg: str, status: ExperimentStatus = ExperimentStatus.REJECTED_INVALID) -> PlanRejected:
    return PlanRejected(code, msg, status)


def _check_device(spec: ExperimentSpec, lim: DeviceLimits) -> None:
    if spec.model_name != lim.model_name or spec.device_type != lim.device_type:
        raise _reject("DEVICE_MODEL_MISMATCH",
                      f"spec requests {spec.device_type.value}/{spec.model_name}; limits are for "
                      f"{lim.device_type.value}/{lim.model_name}")
    if not lim.w_min_um <= spec.width_um <= lim.w_max_um:
        raise _reject("GEOMETRY_OUT_OF_RANGE", f"W={spec.width_um} um outside [{lim.w_min_um}, {lim.w_max_um}]")
    if not lim.l_min_um <= spec.length_um <= lim.l_max_um:
        raise _reject("GEOMETRY_OUT_OF_RANGE", f"L={spec.length_um} um outside [{lim.l_min_um}, {lim.l_max_um}]")
    if not lim.temp_min_c <= spec.temperature_c <= lim.temp_max_c:
        raise _reject("TEMPERATURE_OUT_OF_RANGE",
                      f"T={spec.temperature_c} C outside [{lim.temp_min_c}, {lim.temp_max_c}]")
    volts = {"sweep.start": spec.sweep.start, "sweep.stop": spec.sweep.stop}
    for name, v in (("vds_v", spec.vds_v), ("vgs_v", spec.vgs_v)):
        if v is not None:
            volts[name] = v
    for name, v in volts.items():
        if not lim.v_min <= v <= lim.v_max:
            raise _reject("VOLTAGE_OUT_OF_RANGE", f"{name}={v} V outside supported [{lim.v_min}, {lim.v_max}] V")


def build_plan(spec: ExperimentSpec, limits: DeviceLimits, strategy: str = "uniform") -> ExecutionPlan:
    if strategy not in SUPPORTED_STRATEGIES:
        raise _reject("UNSUPPORTED_STRATEGY", f"strategy '{strategy}' not implemented; supported: {sorted(SUPPORTED_STRATEGIES)}")
    _check_device(spec, limits)

    n = spec.sweep.n_points
    if strategy in ("curvature", "window"):
        if spec.analysis is not AnalysisType.IDVG:
            raise _reject("UNSUPPORTED_STRATEGY", "curvature sampling is implemented for Id-Vg only")
        if n < MIN_CURVATURE_POINTS:
            raise _reject("UNSUPPORTED_STRATEGY", f"curvature sampling needs >= {MIN_CURVATURE_POINTS} points (requested {n}); use uniform")
    if n > spec.budget.max_points:
        raise _reject("BUDGET_EXCEEDED_POINTS",
                      f"plan needs {n} points; budget allows {spec.budget.max_points}. "
                      "Refusing to silently coarsen the sweep.", ExperimentStatus.STOPPED_BUDGET)

    extra = "extract_measurements"
    steps = [
        PlanStep(order=1, action="generate_netlist", uses_tool_call=True,
                 detail=f"{spec.analysis.value} netlist for {spec.model_name} W={spec.width_um}um L={spec.length_um}um T={spec.temperature_c}C"),
        PlanStep(order=2, action="run_ngspice", uses_tool_call=True,
                 detail=f"{n} points, timeout {spec.budget.max_runtime_s}s, explicit-argv subprocess"),
        PlanStep(order=3, action="validate_output", uses_tool_call=False,
                 detail="row count == planned points; all values finite; ngspice exit code 0"),
        PlanStep(order=4, action=extra, uses_tool_call=False,
                 detail=", ".join(m.value for m in spec.measurements)),
        PlanStep(order=5, action="persist_provenance", uses_tool_call=True,
                 detail="spec, plan, netlist, model hash, ngspice version, raw output, measurements"),
    ]
    if strategy in ("curvature", "window"):
        steps[1] = PlanStep(order=2, action="run_ngspice", uses_tool_call=True,
                            detail="pilot: coarse uniform points + forced ION/IOFF bias points (explicit-point sweep)")
        steps.insert(2, PlanStep(order=3, action="run_ngspice", uses_tool_call=True,
                                 detail=f"refine: remaining points placed by log10(Id) curvature of the pilot; total simulated points == {n}"))
        for i, s in enumerate(steps, 1):
            s.order = i
    tool_calls = sum(s.uses_tool_call for s in steps)
    if tool_calls > spec.budget.max_tool_calls:
        raise _reject("BUDGET_EXCEEDED_TOOL_CALLS",
                      f"plan needs {tool_calls} tool calls; budget allows {spec.budget.max_tool_calls}",
                      ExperimentStatus.STOPPED_BUDGET)

    resolved: dict[str, float | str] = {"vbs_v": spec.vbs_v, "output_format": spec.output_format}
    rationale = [
        f"{spec.analysis.value.upper()} chosen because the request sweeps "
        f"{'VGS' if spec.analysis is AnalysisType.IDVG else 'VDS'} and all requested measurements are extractable from it.",
        f"Strategy '{strategy}': {n} {'evenly spaced' if strategy == 'uniform' else ('curvature-placed' if strategy == 'curvature' else 'window+curvature-placed') + ' (pilot + refinement, same count)'} points; {spec.budget.max_points - n} budget points unused.",
        f"vbs_v={spec.vbs_v} V (documented default: bulk tied to source)" if spec.vbs_v == 0.0 else f"vbs_v={spec.vbs_v} V (explicit)",
    ]
    if Measurement.VTH in spec.measurements:
        resolved["vth_ic_a_at_unit_wl"] = spec.vth_ic_a
        rationale.append(f"VTH by constant-current method, Ic = {spec.vth_ic_a:g} A x W/L.")
    if not limits.limits_verified:
        rationale.append("WARNING: device limits are conservative and NOT yet verified against the model-card bin table.")

    return ExecutionPlan(
        spec_sha256=spec_hash(spec), strategy=strategy, estimated_points=n,
        budget_max_points=spec.budget.max_points, estimated_tool_calls=tool_calls,
        budget_max_tool_calls=spec.budget.max_tool_calls, resolved_conditions=resolved,
        steps=steps, rationale=rationale,
    )
