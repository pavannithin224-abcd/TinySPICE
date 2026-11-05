"""Builds tests/benchmark/group1_f4.json (40 requests: 12 fixed-and-swept contradictions, 8 truly-unstated-analysis, 20 valid controls).
Seed 20261106. Written and frozen BEFORE the guards are changed and before any model sees it."""
import json
import pathlib
import random

rng = random.Random(20261106)
B = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8"}
DEV = ["NMOS SKY130 NFET", "an NMOS from the SKY130 NFET model", "SKY130 NFET (NMOS, 1.8 V)"]
PRE = ["", "", "Hello, ", "Request: "]
WS, LS = [0.42, 0.65, 1.0, 2.0, 3.5, 6.0], [0.15, 0.25, 0.4, 0.8, 1.5]
TS = [-20.0, 27.0, 50.0, 85.0, 110.0]
SW = [(0.05, 24, 1.2), (0.04, 30, 1.2), (0.05, 36, 1.8), (0.1, 18, 1.8), (0.03, 40, 1.2)]
f = lambda x: f"{x:g}"   # noqa: E731
tasks = []


def head():
    w, l, T = rng.choice(WS), rng.choice(LS), rng.choice(TS)
    g = rng.choice([f"W = {f(w)} um, L = {f(l)} um", f"width {f(w)} um and length {f(l)} um", f"{f(w)} um wide and {f(l)} um long"])
    t = f"at {f(T)} C" if rng.random() < 0.5 else f"temperature {f(T)} C"
    return w, l, T, f"{rng.choice(PRE)}{rng.choice(DEV)}, {g}, {t}."


# ---- 12 contradictions: a bias is both fixed AND swept (8 Id-Vg, 4 Id-Vd), varied phrasing
IDVG = ["Id-Vg with VDS = 1.2 V, VGS from 0 to {S} V in {st} V steps while VGS is also held at {G} V.",
        "Id-Vg, VDS = 1.2 V: sweep VGS from 0 to {S} V in {st} V steps, and keep VGS constant at {G} V.",
        "The gate voltage is fixed at {G} V and also swept from 0 to {S} V in {st} V steps, with VDS = 1.2 V (Id-Vg).",
        "Hold the gate at {G} V and sweep the gate from 0 to {S} V in {st} V steps; VDS stays at 1.2 V.",
        "Id-Vg with VDS = 1.2 V; VGS sweeps 0 to {S} V in {st} V steps, fixed gate bias {G} V throughout.",
        "Transfer curve at VDS = 1.2 V, VGS 0 to {S} V in {st} V steps, with the gate bias pinned at {G} V."]
IDVD = ["Id-Vd with VGS = 1.2 V, VDS from 0 to {S} V in {st} V steps while VDS is also held at {G} V.",
        "Output curve at VGS = 1.2 V: sweep VDS 0 to {S} V in {st} V steps and keep VDS constant at {G} V.",
        "The drain voltage is fixed at {G} V and also swept from 0 to {S} V in {st} V steps, VGS = 1.2 V (Id-Vd)."]
for i in range(12):
    w, l, T, h = head()
    st, n, S = rng.choice(SW)
    G = rng.choice([0.5, 0.7, 0.9])
    if i < 8:
        tpl, an, fixed_k, bad_k = IDVG[i % len(IDVG)], "idvg", "vds_v", "vgs_v"
    else:
        tpl, an, fixed_k, bad_k = IDVD[(i - 8) % len(IDVD)], "idvd", "vgs_v", "vds_v"
    txt = f"{h} {tpl.format(S=f(S), st=f(st), G=f(G))} Measure the threshold voltage. At most {n + 3} points." if an == "idvg" else \
          f"{h} {tpl.format(S=f(S), st=f(st), G=f(G))} Measure the drain current. At most {n + 3} points."
    oracle = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": an, "sweep_start": 0.0, "sweep_stop": S, "sweep_step": st,
              "measurements": ["VTH" if an == "idvg" else "ID"], "max_points": n + 3, fixed_k: 1.2, bad_k: G}
    tasks.append({"id": f"C{i + 1:02d}", "cat": "contra_fixed_swept", "expect": "reject", "reject_match": [], "text": txt, "oracle": oracle})

# ---- 8 truly unstated analysis (which terminal is swept is never said)
UN = ["Sweep one terminal from 0 to {S} V in {st} V steps with the other terminal at 1.2 V.",
      "Do a voltage sweep from 0 to {S} V in {st} V steps, 1.2 V on the other electrode.",
      "Run a DC sweep from 0 to {S} V in {st} V steps with a constant 0.9 V on the remaining terminal.",
      "Characterize it with a sweep 0 to {S} V, step {st} V, fixed bias 1.2 V."]
for i in range(8):
    w, l, T, h = head()
    st, n, S = rng.choice(SW)
    txt = f"{h} {UN[i % 4].format(S=f(S), st=f(st))} Measure the drain current. At most {n + 3} points."
    oracle = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": None, "sweep_start": 0.0, "sweep_stop": S, "sweep_step": st,
              "measurements": ["ID"], "max_points": n + 3}
    tasks.append({"id": f"U{i + 1:02d}", "cat": "unstated_analysis", "expect": "reject", "reject_match": ["analysis"], "text": txt, "oracle": oracle})

# ---- 20 valid controls, including legitimate "held/fixed/also/constant" wording that must NOT be blocked
VG = ["Id-Vg with VDS = {D} V (held constant), VGS from 0 to {S} V in {st} V steps.",
      "Id-Vg: the drain is fixed at {D} V, and the gate sweeps 0 to {S} V in {st} V steps.",
      "Transfer curve, VGS from 0 to {S} V in {st} V steps, with VDS kept at {D} V throughout.",
      "Id-Vg, VDS = {D} V, VGS 0 to {S} V in {st} V steps; the drain bias is also stated as {D} V in the lab sheet.",
      "Sweep VGS from 0 to {S} V in {st} V steps at a constant drain bias of {D} V (Id-Vg)."]
VD = ["Id-Vd with VGS = {D} V (held constant), VDS from 0 to {S} V in {st} V steps.",
      "Output curve: the gate is fixed at {D} V and the drain sweeps 0 to {S} V in {st} V steps.",
      "Id-Vd, VGS kept at {D} V throughout, VDS from 0 to {S} V in {st} V steps."]
for i in range(20):
    w, l, T, h = head()
    st, n, S = rng.choice(SW)
    D = rng.choice([0.6, 0.9, 1.2, 1.8])
    if i < 13:
        an, tpl = "idvg", VG[i % len(VG)]
        ms = rng.choice([["VTH"], ["VTH", "GM"], ["VTH", "SS"]])
    else:
        an, tpl = "idvd", VD[(i - 13) % len(VD)]
        ms = rng.choice([["ID"], ["GDS"], ["ID", "GDS"]])
    mp = n + 1 + rng.choice([0, 3, 8])
    gold = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": an, "sweep": {"start": 0.0, "stop": S, "step": st},
            "measurements": ms, "budget": {"max_points": mp}}
    gold["vds_v" if an == "idvg" else "vgs_v"] = D
    names = {"VTH": "the threshold voltage", "GM": "the transconductance", "SS": "the subthreshold swing", "ID": "the drain current curve", "GDS": "the output conductance"}
    mt = [names[m] for m in ms]
    mtxt = "Measure " + (mt[0] if len(mt) == 1 else " and ".join(mt)) + "."
    tasks.append({"id": f"K{i + 1:02d}", "cat": "valid_control_" + an, "expect": "valid", "text": f"{h} {tpl.format(S=f(S), st=f(st), D=f(D))} {mtxt} At most {mp} points.", "gold": gold})

assert len(tasks) == 40
doc = {"_note": "Stage 7a fresh set F4: 12 fixed-and-swept contradictions, 8 truly-unstated-analysis, 20 valid controls with legitimate fixed/held wording. FROZEN by sha256 before the guards change.", "tasks": tasks}
pathlib.Path("tests/benchmark/group1_f4.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print("wrote", len(tasks))
