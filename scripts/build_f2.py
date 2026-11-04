"""Builds tests/benchmark/group1_frozen2.json (F2). Run once, then the output is frozen and hashed."""
import json
import pathlib

B = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8"}
valid = [
    ("G01", "Please run a transfer sweep on the SKY130 NFET (NMOS): width 1.5 um, length 0.35 um, 60 degrees C, VDS held at 0.5 V, VGS from 0.2 V to 1.4 V in 0.1 V steps. Extract transconductance and threshold voltage. Limit: 25 points.",
     {**B, "width_um": 1.5, "length_um": 0.35, "temperature_c": 60.0, "analysis": "idvg", "sweep": {"start": 0.2, "stop": 1.4, "step": 0.1}, "vds_v": 0.5, "measurements": ["GM", "VTH"], "budget": {"max_points": 25}}),
    ("G02", "NMOS SKY130 NFET, L=0.8 um, W=6 um, 27 degrees C. Output characteristic: gate fixed at 1.5 V; sweep the drain from 0 to 1.8 V using 19 points. Measure drain current and output conductance. At most 30 points; time limit 90 s.",
     {**B, "width_um": 6.0, "length_um": 0.8, "temperature_c": 27.0, "analysis": "idvd", "sweep": {"start": 0.0, "stop": 1.8, "points": 19}, "vgs_v": 1.5, "measurements": ["ID", "GDS"], "budget": {"max_points": 30, "max_runtime_s": 90.0}}),
    ("G03", "Characterize an NMOS (SKY130 NFET) at 125 C with W 0.84 um and L 0.15 um. Id-Vg, drain bias 1.8 V, gate sweep 0 to 1.8 V, step 30 mV. I want the subthreshold swing, the on-current at VGS = 1.8 V and the off-current at VGS = 0 V. Max 70 points.",
     {**B, "width_um": 0.84, "length_um": 0.15, "temperature_c": 125.0, "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.8, "step": 0.03}, "vds_v": 1.8, "measurements": ["SS", "ION", "IOFF"], "ion_vgs_v": 1.8, "ioff_vgs_v": 0.0, "budget": {"max_points": 70}}),
    ("G04", "We need output curves for the SKY130 NFET NMOS, width 20 um, length 2 um, temperature -40 C. Hold VGS at 0.9 V and sweep VDS from 0 to 1.8 V in 0.1 V steps. Only the drain current curve. Cap at 25 points.",
     {**B, "width_um": 20.0, "length_um": 2.0, "temperature_c": -40.0, "analysis": "idvd", "sweep": {"start": 0.0, "stop": 1.8, "step": 0.1}, "vgs_v": 0.9, "measurements": ["ID"], "budget": {"max_points": 25}}),
    ("G05", "Notes from the 3 pm meeting (attendees: 12): supply rails are 3.3 V and 1.2 V but irrelevant. The task: SKY130 NFET, NMOS, W = 1 um, L = 0.18 um, 27 C, Id-Vg, VDS = 1.0 V, VGS from 0 to 1.2 V in 0.05 V steps, report threshold voltage. Use at most 50 points.",
     {**B, "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0, "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.2, "step": 0.05}, "vds_v": 1.0, "measurements": ["VTH"], "budget": {"max_points": 50}}),
    ("G06", "SKY130 NFET NMOS; W = 750 nm; L = 0.2 um; 40 °C; Id-Vg; VDS = 0.9 V; VGS 0→1.2 V; 25 mV steps; threshold voltage and transconductance; ≤ 60 points.",
     {**B, "width_um": 0.75, "length_um": 0.2, "temperature_c": 40.0, "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.2, "step": 0.025}, "vds_v": 0.9, "measurements": ["VTH", "GM"], "budget": {"max_points": 60}}),
    ("G07", "NMOS SKY130 NFET with channel width 5 um and channel length 0.6 um at 70 °C. Id-Vg: drain at 1.2 V, gate from 0 to 1.2 V with 25 points. Measure off-current at VGS = 0 V and the subthreshold swing. Budget 40 points.",
     {**B, "width_um": 5.0, "length_um": 0.6, "temperature_c": 70.0, "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.2, "points": 25}, "vds_v": 1.2, "measurements": ["IOFF", "SS"], "ioff_vgs_v": 0.0, "budget": {"max_points": 40}}),
    ("G08", "SKY130 NFET NMOS W=2.5 um L=0.3 um 27 C. Output curve Id-Vd with the gate fixed at 1.2 V, drain 0 to 1.8 V, 0.2 V steps. Measure drain current. Allow 12 points, at most 3 tool calls and 2 retries.",
     {**B, "width_um": 2.5, "length_um": 0.3, "temperature_c": 27.0, "analysis": "idvd", "sweep": {"start": 0.0, "stop": 1.8, "step": 0.2}, "vgs_v": 1.2, "measurements": ["ID"], "budget": {"max_points": 12, "max_tool_calls": 3, "max_retries": 2}}),
]
OR = dict(device_type="nmos", model_name="sky130_fd_pr__nfet_01v8", width_um=2.0, length_um=0.3, temperature_c=27.0, analysis="idvg",
          sweep_start=0.0, sweep_stop=1.8, sweep_step=0.1, vds_v=1.8, measurements=["VTH"], max_points=30)


def o(**k):
    d = dict(OR)
    for key, v in k.items():
        if v is None:
            d.pop(key, None)
        else:
            d[key] = v
    return d


rej = [
    ("R01", "NMOS SKY130 NFET at 27 C, width 4 um, standard length. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Threshold voltage. At most 30 points.", o(width_um=4.0, length_um=None), ["length_um"]),
    ("R02", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Threshold voltage. At most 30 points.", o(temperature_c=None), ["temperature_c"]),
    ("R03", "NMOS SKY130 NFET, L = 0.5 um, 27 C. Id-Vg, VDS = 1.0 V, VGS 0 to 1.8 V in 0.05 V steps. Measure the threshold voltage. At most 50 points.", o(width_um=None, length_um=0.5, vds_v=1.0, sweep_step=0.05, max_points=50), ["width_um"]),
    ("R04", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Sweep 0 to 1.8 V in 0.05 V steps with a 1.8 V bias on the other terminal. Measure threshold voltage. At most 50 points.", o(analysis=None, sweep_step=0.05, max_points=50), ["analysis"]),
    ("R05", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.2 V, gate swept from 0 to 1.2 V. Measure threshold voltage. At most 30 points.", o(sweep_step=None, sweep_stop=1.2, vds_v=1.2), ["step", "points"]),
    ("R06", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg transfer curve, VGS 0 to 1.8 V in 0.1 V steps. Measure threshold voltage. At most 30 points.", o(vds_v=None), ["vds_v"]),
    ("R07", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vd output curve, drain from 0 to 1.8 V in 0.1 V steps. Measure the drain current. At most 30 points.", o(analysis="idvd", vds_v=None, measurements=["ID"]), ["vgs_v"]),
    ("R08", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Report the on-current. At most 30 points.", o(measurements=["ION"]), ["ion_vgs_v"]),
    ("R09", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Measure the threshold voltage and run it.", o(max_points=None), ["budget"]),
    ("R10", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Measure the output conductance. At most 30 points.", o(measurements=["GDS"]), ["cannot be extracted"]),
    ("R11", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg with VDS = 1.8 V and the gate fixed at 1.2 V, then sweep VGS 0 to 1.8 V in 0.1 V steps. Threshold voltage. At most 30 points.", o(vgs_v=1.2), ["must not be set"]),
    ("R12", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.05 V steps (that is 37 points). Threshold voltage. At most 40 points.", o(sweep_step=0.05, sweep_points=37, max_points=40), ["exactly one"]),
    ("R13", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.25 V steps. Threshold voltage. At most 30 points.", o(sweep_step=0.25), ["evenly divide"]),
    ("R14", "Run a quick check on a MOSFET and make sure it works.", {}, ["device_type"]),
    ("R15", "NMOS SKY130 NFET, W = 2 um, L = 0.3 um, 27 C. Id-Vg, VDS 1.8 V, VGS 0 to 1.8 V in 0.1 V steps. Measure the off-current. At most 30 points.", o(measurements=["IOFF"]), ["ioff_vgs_v"]),
]
tasks = [{"id": i, "expect": "valid", "text": t, "gold": gd} for i, t, gd in valid]
tasks += [{"id": i, "expect": "reject", "reject_match": m, "text": t, "oracle": orc} for i, t, orc, m in rej]
doc = {"_note": "Group-1 FROZEN test set F2. Written AFTER the grounding design, BEFORE any model was run on it. NEVER tune against it. 'oracle' = what a perfect extractor outputs (non-null fields only), used only to prove each reject task is genuinely rejectable.", "tasks": tasks}
pathlib.Path("tests/benchmark/group1_frozen2.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print(len(tasks))
