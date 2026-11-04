"""Run the extractors requested by an ExperimentSpec. Each measurement succeeds or fails independently."""
from __future__ import annotations

from tinyspice.measurements import extractors as ex
from tinyspice.measurements.result import MeasurementError, MeasurementResult
from tinyspice.schemas.spec import ExperimentSpec, Measurement


def _run(name, unit, method, conditions, fn) -> MeasurementResult:
    try:
        value, diag = fn()
    except MeasurementError as e:
        return MeasurementResult(name, False, None, unit, method, conditions, {}, e.code, e.detail)
    return MeasurementResult(name, True, value, unit, method, conditions, diag)


def extract_all(spec: ExperimentSpec, x, y, floor_a: float | None = None) -> dict[str, MeasurementResult]:
    """floor_a: solver current floor (gmin*|VDS|) if known; IOFF within 10x of it is flagged, not hidden."""
    out: dict[str, MeasurementResult] = {}
    w, l, ic = spec.width_um, spec.length_um, spec.vth_ic_a
    base = {"temperature_c": spec.temperature_c, "width_um": w, "length_um": l, "vbs_v": spec.vbs_v}
    for m in spec.measurements:
        if m is Measurement.ID:
            try:
                xa, ya = ex.prepare(x, y)
                out["ID"] = MeasurementResult("ID", True, None, "A", "validated simulator curve", base, {"n_points": int(len(xa))},
                                              series={"x_v": xa.tolist(), "id_a": ya.tolist()})
            except MeasurementError as e:
                out["ID"] = MeasurementResult("ID", False, None, "A", "validated simulator curve", base, {}, e.code, e.detail)
        elif m is Measurement.GM:
            out["GM"] = _run("GM", "S", "max dId/dVGS (np.gradient, edge_order=2)", {**base, "vds_v": spec.vds_v},
                             lambda: ex.gm_max(x, y))
        elif m is Measurement.GDS:
            out["GDS"] = _run("GDS", "S", "dId/dVDS at last sweep point (np.gradient, edge_order=2)", {**base, "vgs_v": spec.vgs_v},
                              lambda: ex.gds_end(x, y))
        elif m is Measurement.VTH:
            out["VTH"] = _run("VTH", "V", "constant current, Ic = ic*W/L, log-linear interpolation",
                              {**base, "vds_v": spec.vds_v, "ic_a_at_unit_wl": ic}, lambda: ex.vth_constant_current(x, y, w, l, ic))
        elif m is Measurement.SS:
            out["SS"] = _run("SS", "mV/dec", "least-squares slope of log10(Id) vs VGS, window Ic/1e3..Ic",
                             {**base, "vds_v": spec.vds_v, "ic_a_at_unit_wl": ic}, lambda: ex.ss_fit(x, y, w, l, ic))
        elif m is Measurement.ION:
            out["ION"] = _run("ION", "A", "Id at explicit VGS", {**base, "vds_v": spec.vds_v, "vgs_v": spec.ion_vgs_v},
                              lambda: ex.id_at(x, y, spec.ion_vgs_v))
        elif m is Measurement.IOFF:
            def f():
                v, d = ex.id_at(x, y, spec.ioff_vgs_v)
                if floor_a is not None:
                    d = {**d, "solver_floor_a": floor_a, "near_solver_floor": bool(v < 10 * floor_a)}
                return v, d
            out["IOFF"] = _run("IOFF", "A", "Id at explicit VGS", {**base, "vds_v": spec.vds_v, "vgs_v": spec.ioff_vgs_v}, f)
    return out
