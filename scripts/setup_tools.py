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


def fetch_parallel(url: str, dest: Path, expected_size: int, workers: int = 12, chunk: int = 2 << 20, max_fail: int = 10) -> None:
    """Chunked parallel Range download (the Hub throttles each connection to ~30 KB/s; throughput scales with connections).
    Resumable via <dest>.part (+ .part.json listing finished chunks). Verifies total size; caller verifies SHA-256."""
    import queue
    import threading
    import time
    import urllib.error
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    meta = tmp.with_suffix(tmp.suffix + ".json")
    n = -(-expected_size // chunk)
    done: set[int] = set()
    if meta.exists():
        try:
            d = json.loads(meta.read_text())
            if d.get("size") == expected_size and d.get("chunk") == chunk:
                done = set(d["done"])
        except (ValueError, KeyError):
            done = set()
    elif tmp.exists() and tmp.stat().st_size < expected_size:   # legacy sequential prefix: whole chunks of it are valid
        done = set(range(min(n, tmp.stat().st_size // chunk)))
    if not tmp.exists():
        tmp.touch()
    with tmp.open("r+b") as f:
        f.truncate(expected_size)
    meta.write_text(json.dumps({"size": expected_size, "chunk": chunk, "done": sorted(done)}))  # persist BEFORE any new write
    lock, q = threading.Lock(), queue.Queue()
    for i in range(n):
        if i not in done:
            q.put(i)
    stop, errors = threading.Event(), []
    t_start, base = time.monotonic(), len(done) * chunk

    def save_meta() -> None:
        meta.write_text(json.dumps({"size": expected_size, "chunk": chunk, "done": sorted(done)}))

    def one(i: int, fh) -> None:
        start, end = i * chunk, min((i + 1) * chunk, expected_size) - 1
        got, fails = 0, 0
        while start + got <= end and not stop.is_set():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tinyspice-setup/0.1", "Range": f"bytes={start + got}-{end}"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    if getattr(r, "status", 206) != 206:
                        raise RuntimeError(f"server ignored Range (HTTP {r.status})")
                    while blk := r.read(128 * 1024):
                        with lock:
                            fh.seek(start + got)
                            fh.write(blk)
                        got += len(blk)
                        fails = 0
                if start + got <= end:
                    raise RuntimeError(f"short chunk {i}: {got} of {end - start + 1}")
            except (OSError, urllib.error.URLError, RuntimeError) as e:
                fails += 1
                if fails >= max_fail:
                    raise RuntimeError(f"chunk {i} failed {fails}x: {e}")
                time.sleep(min(2 * fails, 15))
        if start + got > end:
            with lock:
                done.add(i)
                save_meta()

    def worker(fh) -> None:
        while not stop.is_set():
            try:
                i = q.get_nowait()
            except queue.Empty:
                return
            try:
                one(i, fh)
            except Exception as e:   # noqa: BLE001 - surfaced after join
                errors.append(e)
                stop.set()
                return

    with tmp.open("r+b") as fh:
        ths = [threading.Thread(target=worker, args=(fh,), daemon=True) for _ in range(min(workers, max(1, q.qsize())))]
        [t.start() for t in ths]
        last_print = 0.0
        while any(t.is_alive() for t in ths):
            time.sleep(1)
            if time.monotonic() - last_print > 15:
                last_print = time.monotonic()
                with lock:
                    got_now = len(done) * chunk
                rate = (got_now - base) / max(1e-6, time.monotonic() - t_start) / 1024
                print(f"  {min(got_now, expected_size) / 2**20:,.0f}/{expected_size / 2**20:,.0f} MiB ({rate:,.0f} KB/s, {workers} conns)", flush=True)
        [t.join() for t in ths]
    if errors:
        raise RuntimeError(f"parallel download failed: {errors[0]}")
    if len(done) != n or tmp.stat().st_size != expected_size:
        raise RuntimeError(f"incomplete: {len(done)}/{n} chunks, {tmp.stat().st_size} of {expected_size} bytes")
    tmp.replace(dest)
    meta.unlink(missing_ok=True)


def fetch(url: str, dest: Path, retries: int = 12, expected_size: int | None = None) -> None:
    """Download with retry + HTTP Range resume (large GGUF files / flaky CDNs). Partial data lives in <dest>.part.
    A response that ends early (clean close, wrong length) is treated as a failure and resumed, never accepted."""
    import re
    import time
    import urllib.error
    if expected_size and expected_size > (16 << 20):
        return fetch_parallel(url, dest, expected_size)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    stalls = 0                      # consecutive attempts that made NO progress; progress resets it
    attempt = 0
    while stalls < retries:
        attempt += 1
        have = tmp.stat().st_size if tmp.exists() else 0
        if expected_size is not None and have == expected_size:
            tmp.replace(dest)
            return
        headers = {"User-Agent": "tinyspice-setup/0.1"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                status = getattr(r, "status", 200)
                mode = "ab" if (have and status == 206) else "wb"
                total = expected_size
                if total is None:
                    cr = r.headers.get("Content-Range")
                    if cr and (mm := re.search(r"/(\d+)$", cr)):
                        total = int(mm.group(1))
                    elif r.headers.get("Content-Length"):
                        total = int(r.headers["Content-Length"]) + (have if status == 206 else 0)
                with tmp.open(mode) as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
            size = tmp.stat().st_size
            if total is None or size == total:
                tmp.replace(dest)
                return
            last = RuntimeError(f"short read: {size:,} of {total:,} bytes")
        except urllib.error.HTTPError as e:
            if e.code == 416 and have:  # already complete
                tmp.replace(dest)
                return
            last = e
        except (OSError, urllib.error.URLError) as e:
            last = e
        now = tmp.stat().st_size if tmp.exists() else 0
        stalls = 0 if now > have else stalls + 1
        print(f"  attempt {attempt} ({type(last).__name__}: {last}); at {now:,} bytes, stalls {stalls}/{retries}")
        time.sleep(1 if now > have else min(2 * stalls, 20))
    raise RuntimeError(f"download stalled: {retries} consecutive attempts without progress: {last}")


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"entries": {}}


def record(m: dict, key: str, url: str, path: Path) -> None:
    m["entries"][key] = {"url": url, "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                         "bytes": path.stat().st_size, "sha256": sha256(path),
                         "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    MANIFEST.write_text(json.dumps(m, indent=2))


def ensure(m: dict, key: str, url: str, path: Path, magic: bytes | None = None, expected_size: int | None = None) -> Path:
    e = m["entries"].get(key)
    if path.exists() and e and sha256(path) == e["sha256"]:
        print(f"  ok (cached) {key}")
        return path
    print(f"  downloading {key} ...")
    fetch(url, path, expected_size=expected_size)
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
