"""Provider-agnostic usage accounting and hard budget guardrails."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BudgetConfig(BaseModel):
    max_calls: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)


class UsageStats(BaseModel):
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class BudgetExceeded(RuntimeError):
    pass


class UsageTracker:
    def __init__(self, budget: BudgetConfig, stats: UsageStats) -> None:
        self.budget = budget
        self.stats = stats

    def before_call(self) -> None:
        if self.budget.max_calls is not None and self.stats.calls >= self.budget.max_calls:
            raise BudgetExceeded(f"LLM call budget of {self.budget.max_calls} reached.")
        if (
            self.budget.max_tokens is not None
            and self.stats.total_tokens >= self.budget.max_tokens
        ):
            raise BudgetExceeded(f"Token budget of {self.budget.max_tokens} reached.")

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.stats.calls += 1
        self.stats.prompt_tokens += max(0, prompt_tokens)
        self.stats.completion_tokens += max(0, completion_tokens)
        self.stats.total_tokens += max(0, prompt_tokens + completion_tokens)
