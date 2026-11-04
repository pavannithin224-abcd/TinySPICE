"""Local llama.cpp provider. Starts a llama-server child bound to 127.0.0.1 ONLY, using an explicit argv list.

No network access beyond loopback, no shell, always cleaned up (context manager). Model + runtime come from
./.tools (installed by scripts/setup_llm.py); nothing is read from outside the project.
"""
from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from tinyspice.providers.base import LLMResponse, ProviderUnavailable
from tinyspice.simulator.tools import ToolPaths, find_tools


class LlamaCppProvider:
    def __init__(self, model_key: str, tools: ToolPaths | None = None, threads: int = 4, ctx: int = 4096,
                 startup_timeout_s: float = 240.0, request_timeout_s: float = 300.0, enable_thinking: bool = False, temperature: float = 0.0):
        self.tools = tools or find_tools()
        man = self.tools.manifest
        try:
            self.exe = self.tools.root / man["llama_cpp"]["exes"]["llama-server.exe"]
            self.model_path = self.tools.root / man["models"][model_key]["file"]
        except KeyError as e:
            raise ProviderUnavailable(f"'{model_key}' or the llama.cpp runtime is not installed (scripts/setup_llm.py): {e}")
        if not self.exe.exists() or not self.model_path.exists():
            raise ProviderUnavailable(f"missing file: {self.exe if not self.exe.exists() else self.model_path}")
        self.name = f"llamacpp:{model_key}"
        self.model_key, self.threads, self.ctx, self.temperature = model_key, threads, ctx, temperature
        self.startup_timeout_s, self.request_timeout_s, self.enable_thinking = startup_timeout_s, request_timeout_s, enable_thinking
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.startup_s = 0.0
        self._log = None

    # ---- lifecycle ----
    def start(self) -> None:
        if self.proc is not None:
            return
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        logdir = self.tools.root / ".tools" / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        self._log = open(logdir / f"llama-server-{self.model_key}.log", "wb")
        argv = [str(self.exe), "-m", str(self.model_path), "--host", "127.0.0.1", "--port", str(self.port),
                "-c", str(self.ctx), "-t", str(self.threads), "-np", "1"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        t0 = time.monotonic()
        self.proc = subprocess.Popen(argv, stdout=self._log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     shell=False, creationflags=flags)
        while time.monotonic() - t0 < self.startup_timeout_s:
            if self.proc.poll() is not None:
                self.stop()
                raise ProviderUnavailable(f"llama-server exited early (see .tools/logs/llama-server-{self.model_key}.log)")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        self.startup_s = time.monotonic() - t0
                        return
            except (urllib.error.URLError, OSError, ValueError):
                pass
            time.sleep(0.5)
        self.stop()
        raise ProviderUnavailable(f"llama-server not healthy after {self.startup_timeout_s}s")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
            self.proc = None
        if self._log:
            self._log.close()
            self._log = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    # ---- inference ----
    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 700, seed: int = 0) -> LLMResponse:
        if self.proc is None:
            self.start()
        body = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature, "seed": seed, "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "spec", "strict": True, "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
        }
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout_s) as r:
                d = json.load(r)
            msg = d["choices"][0]["message"]
            u = d.get("usage", {})
            return LLMResponse(text=msg.get("content") or "", model=self.name, latency_s=time.monotonic() - t0,
                               prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"))
        except (urllib.error.URLError, OSError, KeyError, ValueError, TimeoutError) as e:
            return LLMResponse(text="", model=self.name, latency_s=time.monotonic() - t0, error=f"{type(e).__name__}: {e}")
