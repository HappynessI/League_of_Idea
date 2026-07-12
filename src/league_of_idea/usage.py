"""Provider-agnostic usage accounting and hard budget guardrails."""

from __future__ import annotations

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

    def before_call(self) -> None:
        if self.budget.max_calls is not None and self.stats.calls >= self.budget.max_calls:
            raise BudgetExceeded(f"LLM call budget of {self.budget.max_calls} reached.")
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

    def ensure_calls_available(self, count: int) -> None:
        """Ensure an atomic multi-call operation fits in the call budget."""
        if (
            self.budget.max_calls is not None
            and self.stats.calls + count > self.budget.max_calls
        ):
            raise BudgetExceeded(
                f"Need {count} LLM calls, but only "
                f"{self.budget.max_calls - self.stats.calls} remain in the call budget."
            )
        self.before_call()

    def record(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        model: str | None = None,
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
