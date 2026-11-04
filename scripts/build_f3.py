"""Builds F3 (tests/benchmark/group1_frozen3.json: 20 valid + 20 reject) and the synonym probe set
(tests/benchmark/group1_probe.json). Seeded; phrasing varies by template. Written BEFORE any model sees it."""
import json
import pathlib
import random

rng = random.Random(20261104)
B = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8"}
DEV = ["NMOS SKY130 NFET", "SKY130 1.8 V NFET (NMOS)", "an NMOS from the SKY130 NFET model", "SKY130 NFET, NMOS"]
PREFIX = ["", "", "", "Hi team, ", "Quick request from the lab (12 people on this thread, rails 3.3 V and 5 V are irrelevant): ", "Please "]
WS = [0.42, 0.6, 0.84, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
LS = [0.15, 0.18, 0.25, 0.35, 0.5, 0.8, 1.0, 2.0]
TS = [-40.0, -20.0, 0.0, 27.0, 50.0, 85.0, 100.0, 125.0]
STEPS = [0.02, 0.025, 0.05, 0.1]


def fnum(x):
    return f"{x:g}"


def geom(w, l):
    t = rng.choice(["wl", "words", "nm", "wide"])
    if t == "wl":
        return f"W = {fnum(w)} um, L = {fnum(l)} um"
    if t == "words":
        return f"width {fnum(w)} um and length {fnum(l)} um"
    if t == "nm":
        return f"W = {fnum(round(w * 1000))} nm, L = {fnum(round(l * 1000))} nm"
    return f"{fnum(w)} um wide and {fnum(l)} um long"


def temp(T):
    if T == 27.0 and rng.random() < 0.5:
        return "at room temperature"
    return rng.choice([f"at {fnum(T)} °C", f"temperature {fnum(T)} C", f"at {fnum(T)} degrees Celsius"])


def budget(mp, extra):
    s = rng.choice([f"At most {mp} points", f"Maximum {mp} simulation points", f"Limit of {mp} points", f"Cap the run at {mp} points"])
    bd = {"max_points": mp}
    if extra == "rt":
        r = rng.choice([60, 90, 120])
        s += f" and a time limit of {r} s"
        bd["max_runtime_s"] = float(r)
    elif extra == "tc":
        c = rng.choice([3, 4, 6])
        s += f" and at most {c} tool calls"
        bd["max_tool_calls"] = c
    return s + ".", bd


def make_valid(i):
    w, l, T = rng.choice(WS), rng.choice(LS), rng.choice(TS)
    analysis = rng.choice(["idvg", "idvg", "idvd"])
    step = rng.choice(STEPS)
    n_int = rng.choice([12, 16, 24, 36])
    start = 0.0
    stop = round(step * n_int, 6)
    use_points = rng.random() < 0.3
    bias = rng.choice([0.5, 0.9, 1.2, 1.8])
    if analysis == "idvg":
        pool = ["VTH", "GM", "SS", "ION", "IOFF", "ID"]
    else:
        pool = ["ID", "GDS"]
    k = rng.choice([1, 2, 2, 3]) if analysis == "idvg" else rng.choice([1, 2])
    meas = rng.sample(pool, min(k, len(pool)))
    ion = stop if "ION" in meas else None
    ioff = start if "IOFF" in meas else None
    names = {"VTH": rng.choice(["threshold voltage", "Vth"]), "GM": "transconductance", "SS": "subthreshold swing",
             "GDS": "output conductance", "ID": "the drain current curve", "ION": f"on-current at VGS = {fnum(stop)} V",
             "IOFF": f"off-current at VGS = {fnum(start)} V"}
    mtxt = "Measure " + " and ".join(names[m] for m in meas) + "."
    if analysis == "idvg":
        sw = f"Id-Vg with VDS = {fnum(bias)} V, VGS from {fnum(start)} to {fnum(stop)} V " + (f"using {n_int + 1} points" if use_points else f"in {fnum(step)} V steps")
    else:
        sw = f"Id-Vd output curve with VGS = {fnum(bias)} V, VDS from {fnum(start)} to {fnum(stop)} V " + (f"using {n_int + 1} points" if use_points else f"in {fnum(step)} V steps")
    mp = n_int + 1 + rng.choice([0, 5, 20])
    btxt, bd = budget(mp, rng.choice([None, None, "rt", "tc"]))
    text = f"{rng.choice(PREFIX)}{rng.choice(DEV)}, {geom(w, l)}, {temp(T)}. {sw}. {mtxt} {btxt}"
    sweep = {"start": start, "stop": stop, ("points" if use_points else "step"): (n_int + 1 if use_points else step)}
    gold = {**B, "width_um": w, "length_um": l, "temperature_c": T, "analysis": analysis, "sweep": sweep,
            ("vds_v" if analysis == "idvg" else "vgs_v"): bias, "measurements": meas, "budget": bd}
    if ion is not None:
        gold["ion_vgs_v"] = ion
    if ioff is not None:
        gold["ioff_vgs_v"] = ioff
    return {"id": f"H{i:02d}", "expect": "valid", "text": text, "gold": gold}


def base_parts():
    w, l, T = rng.choice(WS), rng.choice(LS), rng.choice(TS)
    step = rng.choice([0.05, 0.1])
    stop = round(step * rng.choice([12, 18, 24]), 6)
    return dict(w=w, l=l, T=T, step=step, stop=stop, bias=rng.choice([0.9, 1.2, 1.8]), mp=int(round(stop / step)) + 1 + 10)


def text_of(p, *, dev=None, g=True, t=True, analysis="idvg", sweepmode="step", bias=True, meas="Measure the threshold voltage.", bud=True, w_only=None, l_only=None, extra=""):
    parts = [rng.choice(PREFIX) + (dev or rng.choice(DEV))]
    if g:
        if w_only == "L":
            parts.append(f"L = {fnum(p['l'])} um")
        elif w_only == "W":
            parts.append(f"W = {fnum(p['w'])} um")
        elif w_only == "Wstd":
            parts.append(f"width {fnum(p['w'])} um, standard length")
        else:
            parts.append(geom(p["w"], p["l"]))
    if t:
        parts.append(temp(p["T"]))
    head = ", ".join(parts) + ". "
    if analysis == "idvg":
        s = "Id-Vg"
        if bias:
            s += f" with VDS = {fnum(p['bias'])} V"
    elif analysis == "idvd":
        s = "Id-Vd output curve"
        if bias:
            s += f" with VGS = {fnum(p['bias'])} V"
    else:
        s = "A sweep"
    rng_txt = f"{'VGS' if analysis != 'idvd' else 'VDS'} from 0 to {fnum(p['stop'])} V"
    if sweepmode == "step":
        s += f", {rng_txt} in {fnum(p['step'])} V steps"
    elif sweepmode == "none":
        s += f", {rng_txt}"
    s += "." + extra
    b = f" At most {p['mp']} points." if bud else ""
    return head + s + " " + meas + b


def oracle(p, *, analysis="idvg", **drop):
    o = dict(B, width_um=p["w"], length_um=p["l"], temperature_c=p["T"], analysis=analysis, sweep_start=0.0, sweep_stop=p["stop"],
             sweep_step=p["step"], measurements=["VTH"], max_points=p["mp"])
    o["vds_v" if analysis == "idvg" else "vgs_v"] = p["bias"]
    for k, v in drop.items():
        if v is None:
            o.pop(k, None)
        else:
            o[k] = v
    return o


def make_rejects():
    out = []
    cats = []
    for rep in range(2):
        p = base_parts(); cats.append(("length_um", ["length_um"], text_of(p, w_only="Wstd"), oracle(p, length_um=None)))
        p = base_parts(); cats.append(("temperature_c", ["temperature_c"], text_of(p, t=False), oracle(p, temperature_c=None)))
        p = base_parts(); cats.append(("width_um", ["width_um"], text_of(p, w_only="L"), oracle(p, width_um=None)))
        p = base_parts(); cats.append(("vds_v", ["vds_v"], text_of(p, bias=False), oracle(p, vds_v=None)))
    p = base_parts(); cats.append(("analysis", ["analysis"], text_of(p, analysis="none", bias=False), oracle(p, analysis=None, vds_v=None, vgs_v=None)))
    p = base_parts(); cats.append(("step", ["step", "points"], text_of(p, sweepmode="none"), oracle(p, sweep_step=None)))
    p = base_parts(); cats.append(("vgs_v", ["vgs_v"], text_of(p, analysis="idvd", bias=False, meas="Measure the drain current."), oracle(p, analysis="idvd", vgs_v=None, measurements=["ID"])))
    p = base_parts(); cats.append(("ion", ["ion_vgs_v"], text_of(p, meas="Measure the on-current."), oracle(p, measurements=["ION"])))
    p = base_parts(); cats.append(("ioff", ["ioff_vgs_v"], text_of(p, meas="Measure the off-current."), oracle(p, measurements=["IOFF"])))
    p = base_parts(); cats.append(("ion2", ["ion_vgs_v"], text_of(p, meas="Report Ion and the threshold voltage."), oracle(p, measurements=["ION", "VTH"])))
    p = base_parts(); cats.append(("budget", ["budget"], text_of(p, bud=False), oracle(p, max_points=None)))
    p = base_parts(); cats.append(("gds", ["cannot be extracted"], text_of(p, meas="Measure the output conductance."), oracle(p, measurements=["GDS"])))
    p = base_parts(); cats.append(("nodiv", ["evenly divide"], text_of(p).replace(f"in {fnum(p['step'])} V steps", "in 0.35 V steps"), oracle(p, sweep_step=0.35)))
    p = base_parts(); cats.append(("contra_fixed", ["must not be set"], text_of(p, extra=" The gate is also held fixed at 0.6 V."), oracle(p, vgs_v=0.6)))
    p = base_parts(); n = int(round(p["stop"] / p["step"])) + 1
    cats.append(("contra_both", ["exactly one"], text_of(p).replace(f"V steps", f"V steps ({n} points)"), oracle(p, sweep_points=n)))
    p = base_parts(); cats.append(("vague", ["device_type"], "Please run a quick check on one of those devices and tell me if it is fine.", {}))
    p = base_parts(); cats.append(("vague2", ["device_type"], "Run a MOSFET simulation with some reasonable settings.", {}))
    for j, (cat, m, text, orc) in enumerate(cats):
        out.append({"id": f"X{j + 1:02d}", "cat": cat, "expect": "reject", "reject_match": m, "text": text, "oracle": orc})
    return out


valid = [make_valid(i + 1) for i in range(20)]
rejects = make_rejects()
doc = {"_note": "Group-1 FROZEN test set F3 (seeded 20261104). Written after the prune+coverage design, BEFORE any model ran on it. NEVER tune against it.", "tasks": valid + rejects}
pathlib.Path("tests/benchmark/group1_frozen3.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")

# synonym probe: correct requests phrased with measurement words the keyword list does NOT know (measures false blocking)
P = {**B, "width_um": 2.0, "length_um": 0.5, "temperature_c": 27.0, "analysis": "idvg", "vds_v": 1.8}
probe = [
    {"id": "S01", "expect": "valid", "text": "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, at room temperature. Id-Vg with VDS = 1.8 V, VGS from 0 to 1.8 V in 0.1 V steps. Measure the subthreshold slope. At most 40 points.",
     "gold": {**P, "sweep": {"start": 0.0, "stop": 1.8, "step": 0.1}, "measurements": ["SS"], "budget": {"max_points": 40}}},
    {"id": "S02", "expect": "valid", "text": "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, at 27 C. Id-Vg with VDS = 1.8 V, VGS from 0 to 1.8 V in 0.1 V steps. Measure the saturation drive current at VGS = 1.8 V. At most 40 points.",
     "gold": {**P, "sweep": {"start": 0.0, "stop": 1.8, "step": 0.1}, "measurements": ["ION"], "ion_vgs_v": 1.8, "budget": {"max_points": 40}}},
    {"id": "S03", "expect": "valid", "text": "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, at 27 C. Id-Vg with VDS = 1.8 V, VGS from 0 to 1.8 V in 0.1 V steps. Measure the standby current at VGS = 0 V. At most 40 points.",
     "gold": {**P, "sweep": {"start": 0.0, "stop": 1.8, "step": 0.1}, "measurements": ["IOFF"], "ioff_vgs_v": 0.0, "budget": {"max_points": 40}}},
    {"id": "S04", "expect": "valid", "text": "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, at 27 C. Id-Vg with VDS = 1.8 V, VGS from 0 to 1.8 V in 0.1 V steps. Measure the turn-on voltage. At most 40 points.",
     "gold": {**P, "sweep": {"start": 0.0, "stop": 1.8, "step": 0.1}, "measurements": ["VTH"], "budget": {"max_points": 40}}},
]
pathlib.Path("tests/benchmark/group1_probe.json").write_text(json.dumps({"_note": "Synonym probe: measures grounding false-blocks. Perfect extractions are EXPECTED to be blocked for some of these.", "tasks": probe}, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
print(len(valid), len(rejects))
