"""Safe ngspice runner: explicit argv list, no shell, stdin closed, hard timeout, exit-code and output checks."""
from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import numpy as np

from tinyspice.schemas.spec import ExperimentSpec
from tinyspice.simulator.base import SimResult, wrap_arrays
from tinyspice.simulator.models import ModelProfile, get_profile
from tinyspice.simulator.netlist import RAW_NAME, build_netlist
from tinyspice.simulator.tools import ToolPaths, file_sha256, find_tools
from tinyspice.simulator.validate import classify_ngspice_error, has_error_lines

NETLIST_NAME = "netlist.cir"


class NgspiceSimulator:
    name = "ngspice"

    def __init__(self, exe: Path | None = None, tools: ToolPaths | None = None):
        self.tools = tools or find_tools()
        self.exe = Path(exe) if exe else self.tools.ngspice_exe
        if self.exe is None or not Path(self.exe).exists():
            raise FileNotFoundError("ngspice not found; run scripts/setup_tools.py (or set TINYSPICE_NGSPICE_PATH)")
        self._version: str | None = None

    def version(self) -> str:
        if self._version is None:
            r = subprocess.run([str(self.exe), "--version"], capture_output=True, text=True, timeout=30,
                               stdin=subprocess.DEVNULL)
            m = re.search(r"ngspice-(\d+(?:\.\d+)*)", r.stdout + r.stderr)
            self._version = f"ngspice-{m.group(1)}" if m else "unknown"
        return self._version

    def run(self, spec: ExperimentSpec, run_dir: Path, profile: ModelProfile | None = None) -> SimResult:
        profile = profile or get_profile(spec.model_name, self.tools)
        run_dir = Path(run_dir)
        netlist_path = run_dir / NETLIST_NAME
        if netlist_path.exists():
            raise FileExistsError(f"refusing to overwrite existing run: {netlist_path}")
        run_dir.mkdir(parents=True, exist_ok=True)
        netlist_path.write_text(build_netlist(spec, profile), encoding="utf-8", newline="\n")
        raw_path = run_dir / RAW_NAME
        meta = {"model": profile.name, "corner": profile.corner, "educational_model": profile.educational,
                "solver_options": profile.solver_options,
                "model_files_sha256": {p.name: file_sha256(p) for p in profile.model_files}}
        common = dict(simulator_version=self.version(), netlist_path=netlist_path, raw_path=raw_path, meta=meta)

        t0 = time.monotonic()
        try:
            proc = subprocess.run([str(self.exe), "-b", NETLIST_NAME], cwd=run_dir, capture_output=True, text=True,
                                  timeout=spec.budget.max_runtime_s, stdin=subprocess.DEVNULL, shell=False)
        except subprocess.TimeoutExpired as e:
            return SimResult(ok=False, error_code="TIMEOUT", runtime_s=time.monotonic() - t0,
                             error_detail=f"exceeded {spec.budget.max_runtime_s}s",
                             stdout=_s(e.stdout), stderr=_s(e.stderr), **common)
        dt = time.monotonic() - t0
        (run_dir / "ngspice.stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (run_dir / "ngspice.stderr.txt").write_text(proc.stderr, encoding="utf-8")
        text = proc.stdout + "\n" + proc.stderr
        fail = dict(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, runtime_s=dt, **common)

        if proc.returncode != 0:
            return SimResult(ok=False, error_code=classify_ngspice_error(text) or "NONZERO_EXIT",
                             error_detail=f"ngspice exit code {proc.returncode}", **fail)
        if has_error_lines(text):  # exit 0 but simulator reported an error: never call that success
            return SimResult(ok=False, error_code=classify_ngspice_error(text) or "ERROR_IN_OUTPUT",
                             error_detail="ngspice reported an error despite exit code 0", **fail)
        if not raw_path.exists():
            return SimResult(ok=False, error_code="NO_OUTPUT", error_detail=f"{RAW_NAME} was not produced", **fail)
        try:
            data = np.loadtxt(raw_path, ndmin=2)
            x, y = data[:, 0], data[:, 1]
        except (ValueError, IndexError) as e:
            return SimResult(ok=False, error_code="PARSE_ERROR", error_detail=str(e), **fail)
        return wrap_arrays(spec, x, y, **fail)


def _s(b) -> str:
    return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
