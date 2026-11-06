"""Renders terminal-style screenshots and an animated GIF from the REAL demo transcript (docs/DEMO.md, itself captured from real runs by
scripts/make_demo.py). These are RENDERINGS of captured output, not a live screen recording; each image carries a footer saying so.
  python scripts/make_media.py  ->  docs/media/*.png, docs/media/demo.gif          (needs Pillow, installed with matplotlib)"""
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
OUT.mkdir(parents=True, exist_ok=True)
FONT = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 17)
BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 17)
CW, LH, PAD = 10, 24, 18
COLS = 112
BG, FG, DIM = (22, 24, 29), (214, 218, 224), (120, 128, 140)
GREEN, RED, YEL, CYAN = (110, 200, 140), (235, 110, 100), (230, 190, 90), (110, 190, 235)
FOOT = "rendered from the real transcript docs/DEMO.md (captured from real ngspice runs) - not a live screen recording"


def short(t):
    t = t.split(' (')[0]
    return t if len(t) <= 62 else t[:59] + '...'


def parse():
    doc = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
    steps = []
    for m in re.finditer(r"### (\d)\. (.+?)\n(.*?)```\n(.*?)\n```\n\(exit code (\d+)\)", doc, flags=re.S):
        body = m.group(4).split("\n")
        steps.append({"n": m.group(1), "title": m.group(2), "lines": body, "exit": m.group(5)})
    return steps


def compact(lines):
    out, i = [], 0
    while i < len(lines):
        if lines[i] == "{":                                   # collapse the echoed spec JSON, say so explicitly
            j = i
            while lines[j] != "}":
                j += 1
            out.append(f"  {{ ... typed spec JSON, {j - i + 1} lines, full text in docs/DEMO.md ... }}")
            i = j + 1
            continue
        if lines[i].startswith("  \"") or lines[i].startswith("    ") and out and out[-1].startswith("  {"):
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def wrap(lines):
    res = []
    for ln in lines:
        while len(ln) > COLS:
            cut = ln.rfind(" ", 0, COLS)
            cut = cut if cut > 20 else COLS
            res.append(ln[:cut])
            ln = "      " + ln[cut:].lstrip()
        res.append(ln)
    return res


def colour(ln):
    if ln.startswith("$ "):
        return CYAN
    low = ln.lower()
    if "status   : successful" in low or "verified" in low or '"matched": true' in low or " pass" in low:
        return GREEN
    if "rejected" in low or "out_of_range" in low or "required" in low:
        return RED
    if "nothing was simulated" in low:
        return YEL
    return FG


def frame(title, lines, shown=None):
    shown = len(lines) if shown is None else shown
    h = PAD * 2 + 34 + LH * max(len(lines), 6) + 30
    im = Image.new("RGB", (COLS * CW + PAD * 2, h), BG)
    d = ImageDraw.Draw(im)
    for k, c in enumerate(((235, 95, 87), (240, 190, 70), (90, 200, 90))):
        d.ellipse((PAD + k * 22, PAD, PAD + 14 + k * 22, PAD + 14), fill=c)
    d.text((PAD + 80, PAD - 3), title, font=BOLD, fill=DIM)
    y = PAD + 34
    for ln in lines[:shown]:
        d.text((PAD, y), ln, font=FONT, fill=colour(ln))
        y += LH
    d.text((PAD, h - 26), FOOT, font=ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 12), fill=DIM)
    return im


steps = parse()
assert len(steps) == 6, len(steps)
files = {"1": "01_ask_run.png", "2": "02_verify.png", "4": "03_refused_incomplete.png", "5": "04_planner_refuses_300C.png"}
frames = []
for s in steps:
    lines = wrap(compact(s["lines"]))
    if s["n"] == "3":
        lines = [l for l in lines if l.startswith("$ ") or '"matched"' in l or '"n_compared"' in l or '"max_rel_err"' in l] or lines[:12]
        s["lines"] = lines
    if s["n"] in files:
        frame(f"TinySPICE demo - step {s['n']}: {short(s['title'])}", lines).save(OUT / files[s["n"]], optimize=True)
    if s["n"] in ("1", "2", "4", "5"):
        for k in range(1, len(lines) + 1, 2 if len(lines) > 14 else 1):
            frames.append(frame(f"TinySPICE demo - step {s['n']}: {short(s['title'])}", lines, k))
        frames.extend([frame(f"TinySPICE demo - step {s['n']}: {short(s['title'])}", lines)] * 6)
W = max(f.width for f in frames)
H = max(f.height for f in frames)
norm = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=64) if (f.width, f.height) == (W, H) else
        Image.new("RGB", (W, H), BG).convert("P", palette=Image.Palette.ADAPTIVE, colors=64) for f in frames]
canvas = []
for f in frames:
    c = Image.new("RGB", (W, H), BG)
    c.paste(f, (0, 0))
    canvas.append(c.convert("P", palette=Image.Palette.ADAPTIVE, colors=64))
canvas[0].save(OUT / "demo.gif", save_all=True, append_images=canvas[1:], duration=140, loop=0, optimize=True)
print("wrote", sorted(p.name for p in OUT.iterdir()), "| frames", len(canvas), "| gif KB", (OUT / "demo.gif").stat().st_size // 1024)
