"""Provider-independent LLM interface. A provider turns (system, user, json-schema) into JSON text, nothing else.

It never executes commands, never touches the simulator, and is never trusted: every output is validated downstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderUnavailable(Exception):
    """Model/runtime missing or failed to start. Always surfaced, never silently replaced by another provider."""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None


class LLMProvider(Protocol):
    name: str

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 700, seed: int = 0) -> LLMResponse: ...
