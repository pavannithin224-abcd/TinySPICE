#!/usr/bin/env python
"""Install TinySPICE's third-party tools INSIDE the project (./.tools, git-ignored).

Installs: ngspice 47 (64-bit Windows build), 7-Zip's standalone 7zr.exe (to unpack the .7z),
and the SKY130 NFET model files (pinned to a specific upstream commit).
Stdlib only. Safe to re-run: verified files are skipped. Records url/size/sha256 in .tools/manifest.json.

Usage:  python scripts/setup_tools.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools"
DL = TOOLS / "downloads"
MANIFEST = TOOLS / "manifest.json"

NGSPICE_URL = "https://sourceforge.net/projects/ngspice/files/ng-spice-rework/47/ngspice-47_64.7z/download"
NGSPICE_ARCHIVE = DL / "ngspice-47_64.7z"
SEVENZR_URL = "https://www.7-zip.org/a/7zr.exe"
SEVENZR = TOOLS / "7zr.exe"

PDK_REPO = "google/skywater-pdk-libs-sky130_fd_pr"
PDK_FILES = {  # repo path -> local path under .tools/sky130
    "models/parameters/invariant.spice": "parameters/invariant.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.corner.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.corner.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ss.corner.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ss.corner.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ff.corner.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ff.corner.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__fs.corner.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__fs.corner.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__sf.corner.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__sf.corner.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.pm3.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.pm3.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ss.pm3.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ss.pm3.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ff.pm3.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__ff.pm3.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__fs.pm3.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__fs.pm3.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__sf.pm3.spice": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__sf.pm3.spice",
    "cells/nfet_01v8/sky130_fd_pr__nfet_01v8.bins.csv": "cells/nfet_01v8/sky130_fd_pr__nfet_01v8.bins.csv",
    "LICENSE": "LICENSE",
}
# Pinned so every machine gets the same model text (upstream tip of main at install time is recorded).
PDK_COMMIT = "9e08415b20a813ba7038177da5f18aaaaea0b56b"  # last commit touching models/ (2020-11-10)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, retries: int = 6) -> None:
    """Download with retry + HTTP Range resume (large GGUF files / flaky CDNs). Partial data lives in <dest>.part."""
    import time
    import urllib.error
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        headers = {"User-Agent": "tinyspice-setup/0.1"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                mode = "ab" if (have and getattr(r, "status", 200) == 206) else "wb"
                with tmp.open(mode) as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            return
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # already complete
                tmp.replace(dest)
                return
            last = e
        except (OSError, urllib.error.URLError) as e:
            last = e
        print(f"  attempt {attempt}/{retries} failed ({type(last).__name__}); resuming from {tmp.stat().st_size if tmp.exists() else 0:,} bytes")
        time.sleep(2 * attempt)
    raise RuntimeError(f"download failed after {retries} attempts: {last}")


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"entries": {}}


def record(m: dict, key: str, url: str, path: Path) -> None:
    m["entries"][key] = {"url": url, "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                         "bytes": path.stat().st_size, "sha256": sha256(path),
                         "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    MANIFEST.write_text(json.dumps(m, indent=2))


def ensure(m: dict, key: str, url: str, path: Path, magic: bytes | None = None) -> Path:
    e = m["entries"].get(key)
    if path.exists() and e and sha256(path) == e["sha256"]:
        print(f"  ok (cached) {key}")
        return path
    print(f"  downloading {key} ...")
    fetch(url, path)
    if magic and not path.read_bytes()[: len(magic)] == magic:
        path.unlink()
        sys.exit(f"ERROR: {key}: downloaded file is not the expected format (got HTML interstitial?). Aborting.")
    record(m, key, url, path)
    print(f"  fetched {key}: {path.stat().st_size:,} bytes")
    return path


def find_ngspice() -> Path | None:
    for name in ("ngspice_con.exe", "ngspice.exe"):  # console build preferred for batch use
        hits = sorted((TOOLS / "ngspice").rglob(name))
        if hits:
            return hits[0]
    return None


def main() -> int:
    TOOLS.mkdir(exist_ok=True)
    m = load_manifest()
    print("[1/3] 7zr.exe")
    ensure(m, "7zr", SEVENZR_URL, SEVENZR, magic=b"MZ")
    print("[2/3] ngspice 47")
    arc = ensure(m, "ngspice-47_64.7z", NGSPICE_URL, NGSPICE_ARCHIVE, magic=b"7z\xbc\xaf\x27\x1c")
    exe = find_ngspice()
    if exe is None:
        print("  extracting ...")
        r = subprocess.run([str(SEVENZR), "x", str(arc), f"-o{TOOLS / 'ngspice'}", "-y"], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"ERROR: extraction failed (exit {r.returncode}):\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
        exe = find_ngspice()
    if exe is None:
        sys.exit("ERROR: extracted archive but found no ngspice(_con).exe")
    m["ngspice_exe"] = str(exe.relative_to(ROOT)).replace("\\", "/")
    print(f"  ngspice executable: {m['ngspice_exe']}")
    print("[3/3] SKY130 NFET model files (pinned commit " + PDK_COMMIT[:10] + ")")
    for src, dst in PDK_FILES.items():
        url = f"https://raw.githubusercontent.com/{PDK_REPO}/{PDK_COMMIT}/{src}"
        ensure(m, f"sky130:{src}", url, TOOLS / "sky130" / dst)
    m["sky130_commit"] = PDK_COMMIT
    MANIFEST.write_text(json.dumps(m, indent=2))
    print("done. manifest:", MANIFEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
