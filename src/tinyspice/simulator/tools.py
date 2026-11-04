"""Locate project-local tools (installed by scripts/setup_tools.py into ./.tools). Never searches other projects."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("TINYSPICE_HOME")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "pyproject.toml").exists() and (p / "src" / "tinyspice").exists():
            return p
    return Path.cwd()


@dataclass(frozen=True)
class ToolPaths:
    root: Path
    ngspice_exe: Path | None
    sky130_root: Path | None
    manifest: dict = field(default_factory=dict)


def find_tools(root: Path | None = None) -> ToolPaths:
    root = (root or project_root()).resolve()
    mpath = root / ".tools" / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    exe: Path | None = None
    env = os.environ.get("TINYSPICE_NGSPICE_PATH")
    if env:
        exe = Path(env)
    elif manifest.get("ngspice_exe"):
        exe = root / manifest["ngspice_exe"]
    if exe is not None and not exe.exists():
        exe = None
    sky = root / ".tools" / "sky130"
    return ToolPaths(root=root, ngspice_exe=exe, sky130_root=sky if sky.exists() else None, manifest=manifest)


@lru_cache(maxsize=64)
def _sha(path: str, mtime_ns: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sha256(p: Path) -> str:
    return _sha(str(p), p.stat().st_mtime_ns)
