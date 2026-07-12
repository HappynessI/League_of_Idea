"""Provider-agnostic usage accounting and hard budget guardrails."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Protocol

from pydantic import BaseModel, Field

from .pricing import PricingTable


class BudgetConfig(BaseModel):
    max_calls: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    max_cost_usd: float | None = Field(default=None, gt=0)


class UsageStats(BaseModel):
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    unpriced_calls: int = 0


class BudgetExceeded(RuntimeError):
    pass


class UsageRecorder(Protocol):
    def before_call(self) -> None: ...
    def ensure_calls_available(self, count: int) -> None: ...
    def record(
        self, prompt_tokens: int, completion_tokens: int, model: str | None = None
    ) -> None: ...


class UsageTracker:
    def __init__(
        self,
        budget: BudgetConfig,
        stats: UsageStats,
        pricing: PricingTable | None = None,
    ) -> None:
        self.budget = budget
        self.stats = stats
        self.pricing = pricing or PricingTable()
        self._lock = threading.RLock()
        self._reserved_calls = 0

    def before_call(self) -> None:
        with self._lock:
            self._check_non_call_budgets()
            if (
                self.budget.max_calls is not None
                and self.stats.calls + self._reserved_calls >= self.budget.max_calls
            ):
                raise BudgetExceeded(
                    f"LLM call budget of {self.budget.max_calls} reached."
                )

    def ensure_calls_available(self, count: int) -> None:
        """Ensure an atomic multi-call operation fits in the call budget."""
        with self._lock:
            self._check_non_call_budgets()
            if (
                self.budget.max_calls is not None
                and self.stats.calls + self._reserved_calls + count
                > self.budget.max_calls
            ):
                remaining = (
                    self.budget.max_calls - self.stats.calls - self._reserved_calls
                )
                raise BudgetExceeded(
                    f"Need {count} LLM calls, but only {remaining} remain in the call budget."
                )

    def reserve_calls(self, count: int) -> "UsageReservation":
        with self._lock:
            self.ensure_calls_available(count)
            self._reserved_calls += count
        return UsageReservation(self, count)

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._lock:
            yield

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str | None = None,
    ) -> None:
        with self._lock:
            self._record_unlocked(prompt_tokens, completion_tokens, model)

    def _record_unlocked(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str | None,
    ) -> None:
        safe_prompt = max(0, prompt_tokens)
        safe_completion = max(0, completion_tokens)
        self.stats.calls += 1
        self.stats.prompt_tokens += safe_prompt
        self.stats.completion_tokens += safe_completion
        self.stats.total_tokens += safe_prompt + safe_completion
        cost = self.pricing.cost(model, safe_prompt, safe_completion) if model else None
        if cost is None:
            self.stats.unpriced_calls += 1
        else:
            self.stats.estimated_cost_usd += cost

    def _check_non_call_budgets(self) -> None:
        if (
            self.budget.max_tokens is not None
            and self.stats.total_tokens >= self.budget.max_tokens
        ):
            raise BudgetExceeded(f"Token budget of {self.budget.max_tokens} reached.")
        if (
            self.budget.max_cost_usd is not None
            and self.stats.estimated_cost_usd >= self.budget.max_cost_usd
        ):
            raise BudgetExceeded(
                f"Cost budget of ${self.budget.max_cost_usd:.4f} reached."
            )


class UsageReservation:
    """A call-budget reservation owned by one concurrent judge task."""

    def __init__(self, tracker: UsageTracker, calls: int) -> None:
        self.tracker = tracker
        self.remaining = calls
        self._closed = False

    def before_call(self) -> None:
        with self.tracker._lock:
            self.tracker._check_non_call_budgets()
            if self.remaining < 1:
                raise BudgetExceeded("This task has no reserved LLM calls remaining.")

    def ensure_calls_available(self, count: int) -> None:
        with self.tracker._lock:
            self.tracker._check_non_call_budgets()
            if self.remaining < count:
                raise BudgetExceeded(
                    f"This task needs {count} calls but reserved only {self.remaining}."
                )

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str | None = None,
    ) -> None:
        with self.tracker._lock:
            if self.remaining < 1:
                raise RuntimeError("Usage reservation was already exhausted.")
            self.remaining -= 1
            self.tracker._reserved_calls -= 1
            self.tracker._record_unlocked(prompt_tokens, completion_tokens, model)

    def release(self) -> None:
        with self.tracker._lock:
            if not self._closed:
                self.tracker._reserved_calls -= self.remaining
                self.remaining = 0
                self._closed = True
