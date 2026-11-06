"""Figures for the report, generated ONLY from committed raw results (no ngspice, no LLM).  python scripts/make_figures.py  ->  results/figures/*.png
Needs the optional extra:  pip install -e .[figures]"""
import json
import re
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
COL = {"A": "#c0504d", "B": "#e0a030", "C": "#2e7d5b"}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return max(0.0, c - h), min(1.0, c + h)


# ---- Fig 1: false success / completion by configuration and row (TinySPICEBench, frozen run)
rows = json.loads((ROOT / "results" / "bench" / "run.json").read_text())["rows"]
labels = {"qwen3.5-2b": "Qwen3.5-2B", "qwen3.5-0.8b": "Qwen3.5-0.8B", "oracle": "perfect parser (oracle)"}
fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True)
for ax, metric, title in ((axes[0], "false_success", "False success (claimed success that fails the independent check)"),
                          (axes[1], "completion", "Completion (final status = expected status)")):
    for gi, row in enumerate(labels):
        for ci, cfg in enumerate("ABC"):
            R = [r for r in rows if r["row"] == row and r["config"] == cfg]
            k, n = sum(bool(r[metric]) for r in R), len(R)
            lo, hi = wilson(k, n)
            x = gi + (ci - 1) * 0.26
            ax.bar(x, k / n, 0.24, color=COL[cfg], label={"A": "A direct LLM-to-tool", "B": "B structured agent", "C": "C full TinySPICE"}[cfg] if gi == 0 else None)
            ax.errorbar(x, k / n, yerr=[[k / n - lo], [hi - k / n]], color="black", lw=1, capsize=2)
            ax.text(x, hi + 0.02, f"{k}/{n}", ha="center", fontsize=7)
    ax.set_xticks(range(3), [labels[r] for r in labels], fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.set_ylim(0, 1.15)
axes[0].set_ylabel("rate (95 % Wilson interval)")
axes[0].legend(fontsize=7, loc="upper left")
fig.suptitle("TinySPICEBench, one frozen run (24 tasks; 3 seeds per task, mostly pseudo-replicates - see report)", fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "fig1_benchmark.png", dpi=160)
plt.close(fig)

# ---- Fig 2: SS extraction success vs point count (Stage 4 confirmatory, held-out)
d = json.loads((ROOT / "results" / "stage4_confirm" / "confirm_result.json").read_text())["ss_success_by_N"]
Ns = sorted(int(n) for n in d)
fig, ax = plt.subplots(figsize=(5.2, 3.6))
ax.plot(Ns, [d[str(n)]["uniform_pwl"] for n in Ns], "o-", color=COL["A"], label="uniform sampling")
ax.plot(Ns, [d[str(n)]["window"] for n in Ns], "s-", color=COL["C"], label="measurement-aware (window) sampling")
ax.set_xlabel("simulation points N")
ax.set_ylabel("subthreshold-swing extraction success")
ax.set_ylim(-0.03, 1.05)
ax.legend(fontsize=8)
ax.set_title("SS success at small N (12 held-out conditions; 24/24 vs 4/24 at N=16,20)", fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "fig2_sampling.png", dpi=160)
plt.close(fig)

# ---- Fig 3: parser safety vs recall, raw vs guarded (Stage 3, F3 untainted set) from the saved raw model runs
out = subprocess.run([sys.executable, str(ROOT / "scripts" / "replay_policies.py"), "frozen3"], capture_output=True, text=True, cwd=ROOT,
                     env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}).stdout
data = {}
for m in re.finditer(r"^(\S+)\s+frozen3\s+(raw|ground)\s+\|\s+(\d+)/20\s+(\d+)\s+(\d+)/21", out, flags=re.M):
    data[(m[1], m[2])] = (int(m[3]), int(m[4]), int(m[5]))
models = ["smollm2-135m", "smollm2-360m", "qwen3.5-0.8b", "qwen3.5-2b"]
fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
for ax, idx, title, n in ((axes[0], 2, "bad requests wrongly accepted (of 21)", 21), (axes[1], 0, "valid requests extracted exactly (of 20)", 20)):
    for i, mk in enumerate(models):
        for j, pol in enumerate(("raw", "ground")):
            v = data[(mk, pol)][idx]
            ax.bar(i + (j - 0.5) * 0.36, v, 0.34, color="#999999" if pol == "raw" else COL["C"], label=("no guardrails" if pol == "raw" else "with guardrails") if i == 0 else None)
            ax.text(i + (j - 0.5) * 0.36, v + 0.2, str(v), ha="center", fontsize=8)
    ax.set_xticks(range(4), ["135M", "360M", "0.8B", "2B"])
    ax.set_title(title, fontsize=9)
axes[0].legend(fontsize=8)
fig.suptitle("English -> spec on a fresh 41-request set: guardrails remove unsafe acceptances without losing correct extractions", fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "fig3_parser.png", dpi=160)
plt.close(fig)
print("wrote", sorted(p.name for p in OUT.glob("fig*.png")), "| fig3 data points:", len(data))
