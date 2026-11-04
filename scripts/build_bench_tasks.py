"""Builds tests/benchmark/bench_tasks.json: the 24 TinySPICEBench tasks (4 groups x 6).
Each task: natural-language request, gold flat extraction (what a PERFECT parser emits; null/absent = not stated), the expected FINAL STATUS an ideal
system reports, and an optional fault injection (applied identically to every configuration). Expected statuses are pre-registered: if a task
does not realise its scenario, its PARAMETERS may be adjusted with a logged reason; its expected STATUS may not."""
import json
import pathlib

B = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8"}
S = "NMOS SKY130 NFET"


def raw(**k):
    return {**B, **k}


T = []


def add(id, group, name, text, gold, expected, inject=None, note=""):
    T.append({"id": id, "group": group, "name": name, "text": text, "gold_raw": gold, "expected_status": expected, "inject": inject, "note": note})


STD = f"{S}, W = 2 um, L = 0.5 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points."
STD_RAW = raw(width_um=2.0, length_um=0.5, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50)

# ---------------- G1 understanding ----------------
add("T01", "G1", "valid request", "Characterize an NMOS SKY130 NFET with W = 2 um and L = 0.5 um at 27 C. Id-Vg with VDS fixed at 1.8 V, VGS from 0 to 1.8 V in 0.04 V steps. Measure the threshold voltage, transconductance and subthreshold swing. At most 60 points.",
    raw(width_um=2.0, length_um=0.5, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.04, vds_v=1.8, measurements=["VTH", "GM", "SS"], max_points=60), "successful")
add("T02", "G1", "missing parameter (length)", f"{S}, W = 2 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points.",
    raw(width_um=2.0, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50), "rejected_invalid_input")
add("T03", "G1", "contradiction (VGS fixed and swept)", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg with VDS = 1.8 V and VGS held at 0.9 V while VGS is swept 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, vgs_v=0.9, measurements=["VTH"], max_points=50), "rejected_invalid_input")
add("T04", "G1", "unit conversion + distractors", "Hi team, quick one (12 people on the thread, rails of 3.3 V are irrelevant). SKY130 NFET NMOS with W = 750 nm and L = 0.2 um at room temperature. Id-Vg, VDS = 1.0 V, VGS from 0 to 1.2 V in 0.03 V steps; measure the threshold voltage and the on-current at VGS = 1.2 V. At most 50 points.",
    raw(width_um=0.75, length_um=0.2, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.2, sweep_step=0.03, vds_v=1.0, measurements=["VTH", "ION"], ion_vgs_v=1.2, max_points=50), "successful")
add("T05", "G1", "stated constraints preserved", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points, at most 6 tool calls, a time limit of 120 s and 2 retries.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50, max_tool_calls=6, max_runtime_s=120.0, max_retries=2), "successful")
add("T06", "G1", "no invented condition (temperature missing)", f"{S}, W = 1 um, L = 0.18 um. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points.",
    raw(width_um=1.0, length_um=0.18, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50), "rejected_invalid_input")

# ---------------- G2 planning / simulation ----------------
add("T07", "G2", "valid plan, mid-size sweep", f"{S}, width 5 um, length 1 um, at 85 C. Transfer curve: VDS 1.2 V, VGS 0 to 1.8 V in 0.05 V steps. Measure threshold voltage and off-current at VGS = 0 V. At most 50 points.",
    raw(width_um=5.0, length_um=1.0, temperature_c=85.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.2, measurements=["VTH", "IOFF"], ioff_vgs_v=0.0, max_points=50), "successful")
add("T08", "G2", "Id-Vd output curve", f"{S}, W = 4 um, L = 0.5 um, 27 C. Id-Vd output curve with VGS = 1.2 V, VDS from 0 to 1.8 V in 0.05 V steps. Measure the drain current and the output conductance. At most 40 points.",
    raw(width_um=4.0, length_um=0.5, temperature_c=27.0, analysis="idvd", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vgs_v=1.2, measurements=["ID", "GDS"], max_points=40), "successful")
add("T09", "G2", "point limit respected (sweep needs 181 points, limit 50)", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.01 V steps. Measure the threshold voltage. At most 50 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.01, vds_v=1.8, measurements=["VTH"], max_points=50), "stopped_budget_limit")
add("T10", "G2", "physically invalid temperature (300 C)", f"{S}, W = 2 um, L = 0.5 um at 300 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points.",
    raw(width_um=2.0, length_um=0.5, temperature_c=300.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50), "rejected_invalid_input",
    note="ngspice itself happily simulates 300 C; only the planner's device limits refuse it")
add("T11", "G2", "simulator error detected (model include missing)", STD, STD_RAW, "failed", {"type": "missing_include", "mode": "persistent"})
add("T12", "G2", "invalid output never accepted (NaN every attempt)", STD, STD_RAW, "stopped_budget_limit", {"type": "nan", "mode": "persistent"},
    note="retries are exhausted by the persistent fault; configurations without recovery report failed")

# ---------------- G3 measurement / sampling ----------------
add("T13", "G3", "all five measurements", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.04 V steps. Measure threshold voltage, transconductance, subthreshold swing, on-current at VGS = 1.8 V and off-current at VGS = 0 V. At most 60 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.04, vds_v=1.8, measurements=["VTH", "GM", "SS", "ION", "IOFF"], ion_vgs_v=1.8, ioff_vgs_v=0.0, max_points=60), "successful")
add("T14", "G3", "incomplete data detected (sweep ends below threshold)", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 0.3 V in 0.02 V steps. Measure the threshold voltage. At most 40 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=0.3, sweep_step=0.02, vds_v=1.8, measurements=["VTH"], max_points=40), "failed")
add("T15", "G3", "partial result (one measurement refused)", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 0.3 V in 0.02 V steps. Measure the threshold voltage and the on-current at VGS = 0.3 V. At most 40 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=0.3, sweep_step=0.02, vds_v=1.8, measurements=["VTH", "ION"], ion_vgs_v=0.3, max_points=40), "partially_completed")
add("T16", "G3", "subthreshold swing with only 16 points", f"{S}, W = 1 um, L = 0.18 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V with 16 points. Measure threshold voltage and subthreshold swing. At most 16 points.",
    raw(width_um=1.0, length_um=0.18, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_points=16, vds_v=1.8, measurements=["VTH", "SS"], max_points=16), "successful",
    note="needs measurement-aware (window) sampling; uniform sampling cannot extract SS here")
add("T17", "G3", "subthreshold swing with 20 points", f"{S}, W = 2 um, L = 0.5 um, 85 C. Id-Vg, VDS = 1.2 V, VGS 0 to 1.8 V with 20 points. Measure threshold voltage, transconductance and subthreshold swing. At most 20 points.",
    raw(width_um=2.0, length_um=0.5, temperature_c=85.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_points=20, vds_v=1.2, measurements=["VTH", "GM", "SS"], max_points=20), "successful")
add("T18", "G3", "numerical edge: cold, short, narrow device", f"{S}, W = 0.42 um, L = 0.15 um, -40 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.04 V steps. Measure threshold voltage, subthreshold swing and off-current at VGS = 0 V. At most 60 points.",
    raw(width_um=0.42, length_um=0.15, temperature_c=-40.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.04, vds_v=1.8, measurements=["VTH", "SS", "IOFF"], ioff_vgs_v=0.0, max_points=60), "successful")

# ---------------- G4 reliability ----------------
add("T19", "G4", "recover from a recognised fault (timeout once)", STD, STD_RAW, "recovered_after_failure", {"type": "timeout", "mode": "transient"})
add("T20", "G4", "recover from a recognised fault (NaN once)", STD, STD_RAW, "recovered_after_failure", {"type": "nan", "mode": "transient"})
add("T21", "G4", "stop at the retry limit (truncated output every attempt)", STD, STD_RAW, "stopped_budget_limit", {"type": "truncated", "mode": "persistent"})
add("T22", "G4", "respect the time budget (limit 0.3 s)", f"{S}, W = 2 um, L = 0.5 um, 27 C. Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points and a time limit of 0.3 s.",
    raw(width_um=2.0, length_um=0.5, temperature_c=27.0, analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50, max_runtime_s=0.3), "stopped_budget_limit",
    note="one real ngspice run takes >= 0.7 s, so any configuration that ignores the stated limit violates it")
add("T23", "G4", "provenance preserved and run reproducible", STD, STD_RAW, "successful", None,
    note="reproducibility is measured by replaying the stored run; configurations without a stored record cannot be replayed")
add("T24", "G4", "no false success (unrecognised fault every attempt)", STD, STD_RAW, "failed", {"type": "unknown_code", "mode": "persistent"})

assert len(T) == 24 and len({t["id"] for t in T}) == 24
for g in ("G1", "G2", "G3", "G4"):
    assert sum(t["group"] == g for t in T) == 6, g
doc = {"_note": "TinySPICEBench tasks. FROZEN once committed with its sha256; expected statuses are pre-registered (see header of scripts/build_bench_tasks.py).", "tasks": T}
pathlib.Path("tests/benchmark/bench_tasks.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print("wrote", len(T), "tasks")
