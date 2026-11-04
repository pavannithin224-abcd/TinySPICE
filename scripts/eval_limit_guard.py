"""Held-out check of the stated-limit guard (bug H13). Phrasings written AFTER the guard was designed, in new words; some are
expected to be missed (vocabulary) and some controls are adversarial (a safe false block is expected). Single shot: report, do not tune."""
from tinyspice.agent.grounding import omitted_limits, ungrounded_fields
from tinyspice.agent.raw import RAW_FIELDS

H = "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, 27 C. Id-Vg with VDS = 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. Measure the threshold voltage. At most 40 points. "


def R(**kw):
    base = dict(device_type="nmos", model_name="sky130_fd_pr__nfet_01v8", width_um=2.0, length_um=0.5, temperature_c=27.0,
                analysis="idvg", sweep_start=0.0, sweep_stop=1.2, sweep_step=0.05, vds_v=1.0, measurements=["VTH"], max_points=40)
    base.update({k: v for k, v in kw.items() if v is not None})
    return {k: None for k in RAW_FIELDS} | base


def blocked(raw, text):
    return bool(omitted_limits(raw, text) or ungrounded_fields(raw, text))


BLOCK = [
    ("omitted", "Allow at most 5 tool calls.", R()),
    ("omitted", "Use no more than 3 retries.", R()),
    ("omitted", "Use a time limit of 45 s.", R()),
    ("omitted", "Finish within 2 minutes.", R()),
    ("omitted", "Cap it at 8 API calls.", R()),
    ("omitted", "Set the retry limit to 1.", R()),
    ("omitted", "Give it up to 4 attempts.", R()),
    ("omitted", "A timeout of 30 seconds applies.", R()),
    ("omitted", "Budget: 6 tool-calls.", R()),
    ("omitted", "Each run is limited to 90 sec.", R()),                 # vocabulary gap: expected miss
    ("omitted", "Spend at most 12 invocations.", R()),                  # vocabulary gap: expected miss
    ("wrong-field", "Allow at most 4 tool calls.", R(max_retries=4)),
    ("wrong-field", "Use a timeout of 30 s and 3 retries.", R(max_runtime_s=3.0, max_retries=30)),
    ("wrong-value", "Allow at most 4 tool calls.", R(max_tool_calls=20)),   # the exact H13 symptom (schema default leaking in)
]
PASS = [
    ("control", "Allow at most 5 tool calls.", R(max_tool_calls=5)),
    ("control", "Use no more than 3 retries.", R(max_retries=3)),
    ("control", "Use a time limit of 45 s.", R(max_runtime_s=45.0)),
    ("control", "Finish within 2 minutes.", R(max_runtime_s=120.0)),
    ("control", "Use a time limit of 90 s, at most 6 tool calls and 2 retries.", R(max_runtime_s=90.0, max_tool_calls=6, max_retries=2)),
    ("control", "Cap it at 8 API calls.", R(max_tool_calls=8)),
    ("control", "Nothing special about limits here.", R()),
    ("control", "Please call me if it fails.", R()),
    ("control", "The VDS = 1.0 V supply has 3 decoupling caps, irrelevant.", R()),
    ("adversarial", "Last week the lab needed 3 attempts to get a clean run, unrelated to this request.", R()),   # expected SAFE false block
    ("adversarial", "Our cluster allows 20 tool calls per user per day, irrelevant here.", R()),                     # expected SAFE false block
]
cats = {}
for cat, extra, raw in BLOCK:
    hit = blocked(raw, H + extra)
    cats.setdefault(cat, [0, 0])
    cats[cat][0] += hit
    cats[cat][1] += 1
    if not hit:
        print("MISS        ", cat, "|", extra)
fp = [(c, e) for c, e, raw in PASS if blocked(raw, H + e)]
for c, e in fp:
    print("FALSE-BLOCK ", c, "|", e)
print({k: f"{a}/{b}" for k, (a, b) in cats.items()})
print(f"recall {sum(a for a, _ in cats.values())}/{sum(b for _, b in cats.values())}   false blocks {len(fp)}/{len(PASS)} "
      f"(of which adversarial {sum(1 for c, _ in fp if c == 'adversarial')}/2 - a safe false block is the documented direction)")
