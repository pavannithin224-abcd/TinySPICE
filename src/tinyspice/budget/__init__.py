"""Budget ledger. Charges BEFORE each action, so a limit can be reached but never exceeded.

Units (pre-registered in tests/benchmark/stage5_injection_expected.json):
- tool calls : a simulation attempt = 2 (generate_netlist + run_ngspice), a two-phase attempt = 4; persist = 1, RESERVED
               up front so persistence is never blocked by the budget.
- retries    : each recovery action is one retry.
- points     : size of the FINAL retained dataset (failed attempts cost tool calls / retries / time, not points).
- wall-clock : budget.max_runtime_s is the TOTAL deadline for the whole run, retries included.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

FIRST_TIMEOUT_FRACTION = 0.4
TIMEOUT_GROWTH = 2.0
PERSIST_RESERVE = 1


class BudgetExceeded(Exception):
    """Raised BEFORE an action that would push a dimension over its limit."""

    def __init__(self, dimension: str, detail: str):
        super().__init__(f"{dimension}: {detail}")
        self.dimension, self.detail = dimension, detail


@dataclass
class BudgetLedger:
    max_points: int
    max_runtime_s: float
    max_tool_calls: int
    max_retries: int
    clock: Callable[[], float] = time.monotonic
    tool_calls: int = 0
    retries: int = 0
    points: int = 0
    _start: float = field(default=0.0)
    _persisted: bool = False

    def __post_init__(self) -> None:
        self._start = self.clock()

    @classmethod
    def from_spec(cls, spec, clock: Callable[[], float] = time.monotonic) -> "BudgetLedger":
        b = spec.budget
        return cls(b.max_points, b.max_runtime_s, b.max_tool_calls, b.max_retries, clock=clock)

    # ---- wall-clock ----
    def elapsed_s(self) -> float:
        return self.clock() - self._start

    def remaining_s(self) -> float:
        return max(0.0, self.max_runtime_s - self.elapsed_s())

    def check_deadline(self) -> None:
        if self.remaining_s() <= 0.0:
            raise BudgetExceeded("runtime", f"deadline {self.max_runtime_s}s reached")

    def attempt_timeout(self, previous: float | None) -> float:
        """First process timeout = min(remaining, 0.4 x total); each timeout-retry doubles the previous, capped at remaining."""
        self.check_deadline()
        want = FIRST_TIMEOUT_FRACTION * self.max_runtime_s if previous is None else previous * TIMEOUT_GROWTH
        return min(self.remaining_s(), want)

    # ---- tool calls ----
    def charge_calls(self, n: int) -> None:
        if self.tool_calls + n > self.max_tool_calls - (0 if self._persisted else PERSIST_RESERVE):
            raise BudgetExceeded("tool_calls", f"{n} more would exceed {self.max_tool_calls} (1 reserved for persistence)")
        self.tool_calls += n

    def charge_persist(self) -> None:
        if not self._persisted:
            self.tool_calls += PERSIST_RESERVE
            self._persisted = True

    # ---- retries ----
    def retries_left(self) -> int:
        return self.max_retries - self.retries

    def charge_retry(self) -> None:
        if self.retries >= self.max_retries:
            raise BudgetExceeded("retries", f"retry limit {self.max_retries} reached")
        self.retries += 1

    # ---- points ----
    def set_points(self, n: int) -> None:
        if n > self.max_points:
            raise BudgetExceeded("points", f"{n} points would exceed {self.max_points}")
        self.points = n

    def points_left(self) -> int:
        return max(0, self.max_points - self.points)

    def snapshot(self) -> dict:
        return {"tool_calls": {"used": self.tool_calls, "limit": self.max_tool_calls},
                "retries": {"used": self.retries, "limit": self.max_retries},
                "points": {"used": self.points, "limit": self.max_points},
                "wallclock_s": {"used": round(self.elapsed_s(), 4), "limit": self.max_runtime_s}}

    def within_limits(self) -> bool:
        s = self.snapshot()
        return all(v["used"] <= v["limit"] for v in s.values())
