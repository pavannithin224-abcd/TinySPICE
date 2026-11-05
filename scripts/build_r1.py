"""Builds the Stage 6b fresh set tests/benchmark/group1_r1.json (28 valid + 12 bad). Seed 20261105; no text shared with dev/F1-F3/bench tasks
by construction (new seed, new templates). Written and frozen BEFORE any model sees it or any arm exists."""
import json
import pathlib
import random

rng = random.Random(20261105)
B = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8"}
DEV = ["NMOS SKY130 NFET", "an NMOS device from the SKY130 NFET model", "SKY130 NFET (NMOS, 1.8 V)", "the SKY130 1.8 V NFET, NMOS"]
PRE = ["", "", "Hello, ", "For the characterization log: ", "Short ask (the 5 V rail is irrelevant here): "]
WS, LS = [0.42, 0.65, 1.0, 1.8, 2.5, 4.0, 6.0, 8.0], [0.15, 0.2, 0.3, 0.5, 0.9, 1.5, 2.5]
TS = [-30.0, 0.0, 27.0, 40.0, 70.0, 105.0, 125.0]
SW = [(0.03, 40, 1.2), (0.04, 30, 1.2), (0.05, 24, 1.2), (0.05, 36, 1.8), (0.06, 30, 1.8), (0.1, 18, 1.8), (0.02, 30, 0.6), (0.025, 48, 1.2)]
f = lambda x: f"{x:g}"   # noqa: E731


def geom(w, l):
    k = rng.choice(["wl", "words", "nm", "wide"])
    return {"wl": f"W = {f(w)} um, L = {f(l)} um", "words": f"width {f(w)} um and length {f(l)} um",
            "nm": f"W = {f(round(w * 1000))} nm, L = {f(round(l * 1000))} nm", "wide": f"{f(w)} um wide and {f(l)} um long"}[k]


def temp(T):
    if T == 27.0 and rng.random() < 0.5:
        return "at room temperature"
    return rng.choice([f"at {f(T)} C", f"at {f(T)} degrees Celsius", f"temperature {f(T)} C"])


def meas_text(ms, ion, ioff):
    d = {"VTH": "the threshold voltage", "GM": "the transconductance", "SS": "the subthreshold swing", "ID": "the drain current curve",
         "GDS": "the output conductance", "ION": f"the on-current at VGS = {f(ion)} V", "IOFF": f"the off-current at VGS = {f(ioff)} V"}
    parts = [d[m] for m in ms]
    return "Measure " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + "."


tasks = []


def valid(i, kind):
    w, l, T = rng.choice(WS), rng.choice(LS), rng.choice(TS)
    mode = "points" if kind == "points" else "step"
    if kind == "idvd":
        step, n, stop = rng.choice([(0.05, 24, 1.2), (0.05, 36, 1.8), (0.1, 18, 1.8)])
        an, ms, fixed = "idvd", rng.choice([["ID"], ["GDS"], ["ID", "GDS"]]), round(rng.choice([0.6, 0.9, 1.2, 1.8]), 2)
    else:
        step, n, stop = rng.choice(SW)
        an, fixed = "idvg", rng.choice([0.1, 0.5, 1.0, 1.2, 1.8])
        ms = {"tempt_vth": ["VTH"], "tempt_ion": ["ION"], "tempt_ioff": ["IOFF"], "tempt_mix": rng.choice([["VTH", "ION"], ["VTH", "IOFF"], ["GM", "VTH", "ION"]]),
              "plain": rng.choice([["VTH", "GM"], ["VTH", "SS"], ["VTH", "GM", "SS"]]), "points": ["VTH", "SS"]}[kind]
    ion, ioff = stop, 0.0
    sweep = {"start": 0.0, "stop": stop, **({"points": 20} if mode == "points" else {"step": step})}
    npts = 20 if mode == "points" else n + 1
    mp = npts + rng.choice([0, 2, 5, 10]) if mode != "points" else 20
    bud = {"max_points": mp}
    gold = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": an, "sweep": sweep, "measurements": ms, "budget": bud}
    if an == "idvg":
        gold["vds_v"] = fixed
        swp = f"Id-Vg with VDS = {f(fixed)} V, VGS from 0 to {f(stop)} V " + ("with 20 points" if mode == "points" else f"in {f(step)} V steps")
    else:
        gold["vgs_v"] = fixed
        swp = f"Id-Vd output curve with VGS = {f(fixed)} V, VDS from 0 to {f(stop)} V in {f(step)} V steps"
    if "ION" in ms:
        gold["ion_vgs_v"] = ion
    if "IOFF" in ms:
        gold["ioff_vgs_v"] = ioff
    extra = ""
    if rng.random() < 0.3:
        c = rng.choice([3, 4, 6])
        bud["max_tool_calls"] = c
        extra = f" and at most {c} tool calls"
    txt = f"{rng.choice(PRE)}{rng.choice(DEV)}, {geom(w, l)}, {temp(T)}. {swp}. {meas_text(ms, ion, ioff)} At most {mp} points{extra}."
    tasks.append({"id": f"V{i:02d}", "cat": kind, "expect": "valid", "text": txt[0].upper() + txt[1:] if txt[0].islower() else txt, "gold": gold})


kinds = ["tempt_vth"] * 3 + ["tempt_ion"] * 3 + ["tempt_ioff"] * 2 + ["tempt_mix"] * 3 + ["idvd"] * 4 + ["plain"] * 8 + ["points"] * 5   # 28; 11 tempt + 4 idvd(VGS stated)
assert len(kinds) == 28
rng.shuffle(kinds)
for i, k in enumerate(kinds, 1):
    valid(i, k)


def bad(i, cat, drop, match, tweak=None):
    w, l, T = rng.choice(WS), rng.choice(LS), rng.choice(TS)
    step, n, stop = rng.choice(SW)
    oracle = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": "idvg", "sweep_start": 0.0, "sweep_stop": stop, "sweep_step": step,
              "vds_v": 1.2, "measurements": ["VTH"], "max_points": n + 3}
    parts = {"geom": geom(w, l), "temp": temp(T), "sweep": f"Id-Vg with VDS = 1.2 V, VGS from 0 to {f(stop)} V in {f(step)} V steps", "meas": "Measure the threshold voltage.", "bud": f"At most {n + 3} points."}
    if tweak:
        oracle, parts = tweak(oracle, parts, w, l, T, stop, step, n)
    for k in drop:
        if k == "length":
            oracle.pop("length_um"); parts["geom"] = f"width {f(w)} um with the standard length"
        elif k == "width":
            oracle.pop("width_um"); parts["geom"] = f"length {f(l)} um, width as usual"
        elif k == "temperature":
            oracle.pop("temperature_c"); parts["temp"] = "at the usual lab temperature"
        elif k == "vds":
            oracle.pop("vds_v"); parts["sweep"] = f"Id-Vg, VGS from 0 to {f(stop)} V in {f(step)} V steps"
        elif k == "budget":
            oracle.pop("max_points"); parts["bud"] = ""
        elif k == "analysis":
            oracle["analysis"] = None; parts["sweep"] = f"A sweep, VGS from 0 to {f(stop)} V in {f(step)} V steps with VDS = 1.2 V"
    txt = f"{rng.choice(PRE)}{rng.choice(DEV)}, {parts['geom']}, {parts['temp']}. {parts['sweep']}. {parts['meas']} {parts['bud']}".strip()
    tasks.append({"id": f"B{i:02d}", "cat": cat, "expect": "reject", "reject_match": match, "text": txt, "oracle": oracle})


def ion_nobias(o, p, w, l, T, stop, step, n):
    o["measurements"] = ["ION"]
    p["meas"] = "Measure the on-current."
    return o, p


def contra_fixed(o, p, w, l, T, stop, step, n):
    o["vgs_v"] = 0.7
    p["sweep"] += " while VGS is also held at 0.7 V"
    return o, p


def contra_both(o, p, w, l, T, stop, step, n):
    o["sweep_points"] = 25
    p["sweep"] += " and exactly 25 points"
    return o, p


def nodiv(o, p, w, l, T, stop, step, n):
    s = rng.choice([0.07, 0.35, 0.45])
    o["sweep_stop"], o["sweep_step"], o["sweep_start"] = 1.0, s, 0.0
    p["sweep"] = f"Id-Vg with VDS = 1.2 V, VGS from 0 to 1 V in {f(s)} V steps"
    return o, p


def gds_idvg(o, p, w, l, T, stop, step, n):
    o["measurements"] = ["GDS"]
    p["meas"] = "Measure the output conductance."
    return o, p


def ioff_nobias(o, p, w, l, T, stop, step, n):
    o["measurements"] = ["IOFF"]
    p["meas"] = "Measure the off-current."
    return o, p


spec = [("length", ["length"], ["length_um"], None), ("width", ["width"], ["width_um"], None), ("temperature", ["temperature"], ["temperature_c"], None),
        ("vds", ["vds"], ["vds_v"], None), ("analysis", ["analysis"], ["analysis"], None), ("budget", ["budget"], ["budget"], None),
        ("ion_nobias", [], ["ion_vgs_v"], ion_nobias), ("contra_fixed", [], ["must not be set"], contra_fixed), ("contra_both", [], ["exactly one"], contra_both),
        ("nodiv", [], ["evenly divide"], nodiv), ("gds_idvg", [], ["cannot be extracted"], gds_idvg), ("ioff_nobias", [], ["ioff_vgs_v"], ioff_nobias)]
for i, (cat, drop, match, tw) in enumerate(spec, 1):
    bad(i, cat, drop, match, tw)

assert len(tasks) == 40 and sum(t["expect"] == "valid" for t in tasks) == 28
doc = {"_note": "Stage 6b fresh set R1 (28 valid + 12 bad). FROZEN by sha256 before any arm runs; see docs/STAGE6B_PREREG.md.", "tasks": tasks}
pathlib.Path("tests/benchmark/group1_r1.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print("wrote", len(tasks))
