#!/usr/bin/env python
"""Install the local LLM runtime (llama.cpp, pinned build) and chosen GGUF models INSIDE ./.tools (git-ignored).

Usage:  python scripts/setup_llm.py runtime            # llama.cpp CPU build only (~24 MB)
        python scripts/setup_llm.py model qwen3.5-2b   # one model (sizes are printed before download)
Models: qwen3.5-2b, qwen3.5-4b, phi-4-mini, smollm3-3b  (all Q4_K_M, revision-pinned, SHA-256 recorded).
Stdlib only; reuses the verified-download helpers of setup_tools.py. Never downloads anything not named on the CLI.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import setup_tools as st  # noqa: E402

LLAMA_TAG = "b12102"
LLAMA_ASSET = f"llama-{LLAMA_TAG}-bin-win-cpu-x64.zip"
LLAMA_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/{LLAMA_ASSET}"
LLAMA_DIR = st.TOOLS / "llama.cpp"
MODELS = {  # key -> HF repo (Q4_K_M file is looked up in the repo listing). All files land in ./.tools/models only.
    "smollm2-135m": "bartowski/SmolLM2-135M-Instruct-GGUF",
    "smollm2-360m": "bartowski/SmolLM2-360M-Instruct-GGUF",
    "qwen3.5-0.8b": "unsloth/Qwen3.5-0.8B-GGUF",
    "qwen3.5-2b": "unsloth/Qwen3.5-2B-GGUF",
    "qwen3.5-4b": "unsloth/Qwen3.5-4B-GGUF",
    "phi-4-mini": "unsloth/Phi-4-mini-instruct-GGUF",
    "smollm3-3b": "ggml-org/SmolLM3-3B-GGUF",
}


def hf(repo: str, tries: int = 8) -> dict:
    import time
    import urllib.error
    last: Exception | None = None
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(f"https://huggingface.co/api/models/{repo}?blobs=true", headers={"User-Agent": "tinyspice-setup/0.1"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last = e
            print(f"  hub metadata attempt {i}/{tries} failed ({type(e).__name__}: {e}); retrying")
            time.sleep(min(3 * i, 30))
    raise RuntimeError(f"Hugging Face metadata unreachable after {tries} attempts: {last}")


def runtime() -> int:
    m = st.load_manifest()
    arc = st.ensure(m, f"llama.cpp-{LLAMA_TAG}", LLAMA_URL, st.DL / LLAMA_ASSET, magic=b"PK")
    if not list(LLAMA_DIR.rglob("llama-server.exe")):
        LLAMA_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(arc) as z:
            z.extractall(LLAMA_DIR)
    exes = {p.name: str(p.relative_to(st.ROOT)).replace("\\", "/") for p in LLAMA_DIR.rglob("*.exe")}
    for need in ("llama-server.exe", "llama-bench.exe"):
        if need not in exes:
            sys.exit(f"ERROR: {need} not found after extraction")
    m["llama_cpp"] = {"tag": LLAMA_TAG, "exes": {k: exes[k] for k in ("llama-server.exe", "llama-bench.exe", "llama-cli.exe") if k in exes}}
    st.MANIFEST.write_text(json.dumps(m, indent=2))
    print("llama.cpp", LLAMA_TAG, "->", m["llama_cpp"]["exes"])
    return 0


def model(key: str) -> int:
    if key not in MODELS:
        sys.exit(f"unknown model '{key}'; choose from {sorted(MODELS)}")
    repo = MODELS[key]
    info = hf(repo)
    cands = [s for s in info["siblings"] if s["rfilename"].endswith("Q4_K_M.gguf") and "/" not in s["rfilename"]]
    if len(cands) != 1:
        sys.exit(f"ERROR: expected exactly one top-level Q4_K_M gguf in {repo}, found {[c['rfilename'] for c in cands]}")
    f, rev = cands[0], info["sha"]
    print(f"{repo} @ {rev[:10]}: {f['rfilename']} ({f['size'] / 2**30:.2f} GB), license: {info.get('cardData', {}).get('license')}")
    m = st.load_manifest()
    url = f"https://huggingface.co/{repo}/resolve/{rev}/{f['rfilename']}"
    dest = st.TOOLS / "models" / f["rfilename"]
    st.ensure(m, f"model:{key}", url, dest, magic=b"GGUF", expected_size=f["size"])
    want = (f.get("lfs") or {}).get("sha256")  # independent integrity check against the Hub's own recorded hash
    if want:
        got = st.sha256(dest)
        if got != want:
            dest.unlink()
            m["entries"].pop(f"model:{key}", None)
            st.MANIFEST.write_text(json.dumps(m, indent=2))
            sys.exit(f"ERROR: SHA-256 mismatch for {f['rfilename']}: expected {want}, got {got}; file deleted")
        print("  sha256 verified against Hugging Face LFS record")
    else:
        print("  WARNING: no LFS sha256 available from the Hub; integrity not independently verified")
    m.setdefault("models", {})[key] = {"repo": repo, "revision": rev, "file": str(dest.relative_to(st.ROOT)).replace("\\", "/"),
                                       "license": info.get("cardData", {}).get("license")}
    st.MANIFEST.write_text(json.dumps(m, indent=2))
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "runtime":
        raise SystemExit(runtime())
    if len(sys.argv) == 3 and sys.argv[1] == "model":
        raise SystemExit(model(sys.argv[2]))
    sys.exit(__doc__)
