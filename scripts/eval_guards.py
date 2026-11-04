"""Held-out evaluation of the request-side guards (no model involved). Phrasings written AFTER the guards were designed,
in different words from every benchmark set. Single shot: report, do not tune. Usage: python scripts/eval_guards.py"""
from tinyspice.agent.grounding import omitted_biases, request_conflicts, uncovered_measurements, ungrounded_fields
from tinyspice.agent.raw import RAW_FIELDS

H = "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, 27 C. "


def R(**kw):
    base = dict(device_type="nmos", model_name="sky130_fd_pr__nfet_01v8", width_um=2.0, length_um=0.5, temperature_c=27.0,
                analysis="idvg", sweep_start=0.0, sweep_stop=1.2, sweep_step=0.05, vds_v=1.0, measurements=["VTH"], max_points=40)
    for k, v in kw.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return {k: None for k in RAW_FIELDS} | base


def blocked(raw, text):
    return bool(ungrounded_fields(raw, text) or uncovered_measurements(raw, text) or request_conflicts(text) or omitted_biases(raw, text))


BLOCK = [  # (category, text, raw as a typical model would emit it)
    ("step+points", H + "Id-Vg at VDS = 1.0 V, sweep VGS 0 to 1.2 V with 0.05 V increments, i.e. 25 samples. Measure threshold voltage. At most 40 points.", R()),
    ("step+points", H + "Id-Vg at VDS = 1.0 V, gate from 0 to 1.8 V, spacing 0.1 V, total of 19 points. Measure threshold voltage. At most 40 points.", R(sweep_stop=1.8, sweep_step=0.1)),
    ("step+points", H + "Id-Vg at VDS = 1.0 V, VGS 0 to 2 V in 0.2 V steps (10 sweep points). Measure threshold voltage. At most 40 points.", R(sweep_stop=2.0, sweep_step=0.2)),
    ("step+points", H + "Id-Vg at VDS = 1.0 V, VGS 0 to 1.2 V, step size 25 mV, 49 data points. Measure threshold voltage. At most 60 points.", R(sweep_step=0.025, max_points=60)),
    ("step+points", H + "Id-Vg at VDS = 1.0 V, VGS 0 to 1.8 V stepping 0.05 V; 37 points. Measure threshold voltage. At most 40 points.", R(sweep_stop=1.8)),
    ("step+points", H + "Id-Vg at VDS = 1.0 V, VGS 0 to 1.8 V in increments of 0.1 V, 19 points. Measure threshold voltage. At most 40 points.", R(sweep_stop=1.8, sweep_step=0.1)),
    ("omitted bias", H + "Id-Vg with the drain tied to 1.2 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R(vds_v=None)),
    ("omitted bias", H + "Id-Vg with drain voltage fixed at 0.6 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R(vds_v=None)),
    ("omitted bias", H + "Id-Vd output curve while the gate stays at 1.1 V, VDS 0 to 1.2 V in 0.05 V steps. Measure the drain current. At most 40 points.", R(analysis="idvd", vds_v=None, measurements=["ID"])),
    ("omitted bias", H + "Id-Vg with VDS biased at 1.8 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R(vds_v=None)),
    ("omitted bias", H + "Id-Vd output curve with VGS clamped to 0.9 V, VDS 0 to 1.2 V in 0.05 V steps. Measure the drain current. At most 40 points.", R(analysis="idvd", vds_v=None, measurements=["ID"])),
    ("omitted bias", H + "Id-Vg where the drain voltage is 0.9 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R(vds_v=None)),
    ("fixed+swept", H + "Id-Vg with VDS = 1.0 V, the gate fixed at 0.5 V and also swept 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R()),
    ("cross-field", H + "Id-Vd output curve, gate at 0.9 V, VDS from 0 to 1.8 V in 0.1 V steps. Measure the drain current. At most 40 points.", R(analysis="idvd", vds_v=None, vgs_v=1.8, sweep_stop=1.8, sweep_step=0.1, measurements=["ID"])),
    ("cross-field", H + "Id-Vg with VDS = 1.0 V, VGS from 0 to 1.8 V in 0.1 V steps. Measure threshold voltage. At most 40 points.", R(vds_v=1.8, sweep_stop=1.8, sweep_step=0.1)),
]
PASS = [
    ("control", H + "Id-Vg with the drain at 1.0 V, gate from 0 to 1.2 V with 25 points. Measure threshold voltage. Budget 40 points.", R(sweep_step=None, sweep_points=25)),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure Ion at 1.2 V and Ioff at 0 V. At most 40 points.", R(measurements=["ION", "IOFF"], ion_vgs_v=1.2, ioff_vgs_v=0.0)),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Report on-current at VGS = 1.2 V and off-current at VGS = 0 V. No more than 40 points.", R(measurements=["ION", "IOFF"], ion_vgs_v=1.2, ioff_vgs_v=0.0)),
    ("control", H + "Id-Vd output curve with gate bias 0.9 V, drain sweep 0 to 1.2 V in 0.05 V steps. Measure the drain current. At most 40 points.", R(analysis="idvd", vds_v=None, vgs_v=0.9, measurements=["ID"])),
    ("control", H + "Id-Vg with VDS = 1.0 V and the bulk at 0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R(vbs_v=0.0)),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. Cap the run at 40 points.", R()),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. Up to 40 simulation points.", R()),
    ("control", H + "Id-Vg with a drain bias of 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R()),
    ("control", H + "Id-Vg with VDS held at 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure threshold voltage. At most 40 points.", R()),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V, 0.05 V step. Measure threshold voltage. Limited to 40 points.", R()),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V using 25 points. Measure threshold voltage. (budget: 40 points)", R(sweep_step=None, sweep_points=25)),
    ("control", H + "Id-Vd output curve with VGS = 0.9 V, VDS 0 to 1.2 V using 25 points. Measure output conductance. Max 40 points.", R(analysis="idvd", vds_v=None, vgs_v=0.9, sweep_step=None, sweep_points=25, measurements=["GDS"])),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure the subthreshold swing. Max 40 points.", R(measurements=["SS"])),
    ("control", H + "Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure the threshold voltage and transconductance. At most 40 points and a time limit of 60 s.", R(measurements=["VTH", "GM"], max_runtime_s=60.0)),
]
cats = {}
for cat, text, raw in BLOCK:
    hit = blocked(raw, text)
    cats.setdefault(cat, [0, 0])
    cats[cat][0] += hit
    cats[cat][1] += 1
    if not hit:
        print("MISS  ", cat, "|", text[len(H):len(H) + 110])
fp = [text[len(H):len(H) + 110] for _, text, raw in PASS if blocked(raw, text)]
for f in fp:
    print("FALSE-BLOCK |", f)
print({k: f"{a}/{b}" for k, (a, b) in cats.items()})
print(f"recall {sum(a for a, _ in cats.values())}/{sum(b for _, b in cats.values())}   false-blocks on controls {len(fp)}/{len(PASS)}")
