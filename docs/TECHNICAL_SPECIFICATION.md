# Technical Specification

## ExperimentSpec (`tinyspice.schemas.spec`) — IMPLEMENTED
Required: device_type, model_name, width_um, length_um, temperature_c, analysis (idvg|idvd), sweep (start, stop, exactly one of step|points), measurements (>=1), budget.max_points.
Conditional: idvg requires vds_v and forbids vgs_v; idvd the reverse. ION/IOFF require explicit ion_vgs_v/ioff_vgs_v inside the sweep and ion > ioff; supplying a bias for an unrequested measurement is an error.
Defaults (all echoed by the planner): vbs_v=0 (bulk to source), vth_ic_a=1e-7 A at W/L=1, budget max_runtime_s=300, max_tool_calls=20, max_retries=2, output_format=csv.
Rejected: unknown fields, duplicate measurements, non-ascending sweeps, steps that do not divide the range, GM/VTH/SS/ION/IOFF on Id-Vd, GDS on Id-Vg.

## Planner (`tinyspice.planner`) — IMPLEMENTED
`build_plan(spec, limits, strategy)` -> ExecutionPlan or `PlanRejected(code, status)`. Codes: DEVICE_MODEL_MISMATCH, GEOMETRY_OUT_OF_RANGE, TEMPERATURE_OUT_OF_RANGE, VOLTAGE_OUT_OF_RANGE, BUDGET_EXCEEDED_POINTS, BUDGET_EXCEEDED_TOOL_CALLS, UNSUPPORTED_STRATEGY. Never coarsens a sweep to fit a budget. Plan carries a SHA-256 of the canonical spec.
Device limits are in `configs/devices/*.json`; the SKY130 NFET bounds are **provisional and unverified** (`limits_verified=false`) until checked against the model card.

## Measurements — IMPLEMENTED (Stage 2). Authoritative definitions: docstring of `src/tinyspice/measurements/extractors.py`
GM = max dId/dVGS (np.gradient, edge_order=2, non-uniform grids OK; flags a maximum on the sweep edge); GDS = dId/dVDS at the last Id-Vd point; VTH = constant current Ic = ic*W/L (first upward crossing, log-linear interpolation; fails NOT_CROSSED / ALREADY_ABOVE; flags re-crossing); SS = 1/slope of least-squares log10(Id) vs VGS over Ic/1e3..Ic (needs >=4 contiguous points, >=1 decade, R^2 >= 0.995, else POOR_FIT / INSUFFICIENT_POINTS / WINDOW_TOO_NARROW / NON_CONTIGUOUS_WINDOW); ION/IOFF = Id at explicit VGS (log-linear interpolation, OUT_OF_RANGE if outside the sweep; IOFF flagged if within 10x of the solver floor gmin*VDS). Invalid data (NaN/Inf, non-monotonic axis, <3 points, shape mismatch) -> INVALID_DATA. No smoothing/denoising is applied.
Original plan text follows for history:
## Measurements (planned definitions)
- ID: simulator drain current, sign convention documented per device.
- GM = dID/dVGS, GDS = dID/dVDS: central differences on the sampled grid.
- VTH: constant-current, VGS where ID = vth_ic_a * W/L, linear interpolation in log(ID); fails if never crossed.
- SS = dVGS / dlog10(ID) fitted over a documented subthreshold window; fit R^2 reported; refuses below a threshold.
- ION/IOFF: ID at explicit VGS. Each result carries method, conditions, validity flag.

## Simulation safety — planned
subprocess with explicit argv list, cwd inside run dir, timeout, exit-code check, output size/row validation; netlists generated from validated numeric fields only.

## Provenance — planned
SQLite (metadata, status, budget use) + per-run directory (netlist, logs, raw output, figures). Run IDs are unique; runs are never overwritten.
