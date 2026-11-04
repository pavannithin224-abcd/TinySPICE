"""Proves a benchmark set is sound: gold specs validate, reject tasks are rejected for the stated reason by a PERFECT
extractor (oracle), and grounding never blocks a perfect extraction. Usage: python scripts/verify_set.py <json>"""
import json
import sys

from tinyspice.agent.grounding import ungrounded_fields
from tinyspice.agent.raw import RAW_FIELDS, raw_to_spec_dict
from tinyspice.schemas import ExperimentSpec

T = json.load(open(sys.argv[1], encoding="utf-8"))["tasks"]
bad = 0
for t in T:
    if t["expect"] == "valid":
        g = t["gold"]
        try:
            ExperimentSpec.model_validate(g)
        except Exception as e:
            bad += 1
            print("GOLD INVALID", t["id"], str(e)[:160])
        raw = {k: None for k in RAW_FIELDS} | {k: v for k, v in g.items() if k not in ("sweep", "budget")}
        for k, v in g["sweep"].items():
            raw["sweep_" + k] = v
        for k, v in g["budget"].items():
            raw[k] = v
    else:
        raw = {k: None for k in RAW_FIELDS} | t["oracle"]
        try:
            ExperimentSpec.model_validate(raw_to_spec_dict(t["oracle"]))
            bad += 1
            print("ORACLE ACCEPTED (task not rejectable)", t["id"])
        except Exception as e:
            blob = str(e).lower()
            if not all(m.lower() in blob for m in t["reject_match"]):
                bad += 1
                print("REASON MISMATCH", t["id"], t["reject_match"], blob[:240].replace("\n", " "))
    ug = ungrounded_fields(raw, t["text"])
    if ug:
        bad += 1
        print("PERFECT EXTRACTION BLOCKED BY GROUNDING", t["id"], ug)
print("tasks", len(T), "valid", sum(t["expect"] == "valid" for t in T), "reject", sum(t["expect"] == "reject" for t in T), "problems", bad)
sys.exit(1 if bad else 0)
