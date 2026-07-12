import pytest

from league_of_idea import tournament
from league_of_idea.pricing import ModelPrice, PricingTable
from league_of_idea.usage import BudgetConfig, BudgetExceeded, UsageStats, UsageTracker


def test_pricing_calculates_input_and_output_cost():
    pricing = PricingTable(
        version="test",
        models={
            "openai:test": ModelPrice(
                input_per_million_usd=2,
                output_per_million_usd=4,
            )
        },
    )

    assert pricing.cost("openai/test", 1_000_000, 500_000) == pytest.approx(4.0)


def test_cost_budget_stops_before_the_next_call():
    pricing = PricingTable(
        version="test",
        models={
            "openai:test": ModelPrice(
                input_per_million_usd=1,
                output_per_million_usd=1,
            )
        },
    )
    stats = UsageStats()
    tracker = UsageTracker(BudgetConfig(max_cost_usd=1), stats, pricing)

    tracker.record(600_000, 400_000, model="openai:test")

    assert stats.estimated_cost_usd == pytest.approx(1.0)
    with pytest.raises(BudgetExceeded, match="Cost budget"):
        tracker.before_call()


def test_cost_budget_requires_prices_for_all_tournament_models():
    pricing = PricingTable(
        version="test",
        models={
            "openai:generator": ModelPrice(
                input_per_million_usd=1,
                output_per_million_usd=1,
            )
        },
    )

    with pytest.raises(ValueError, match="openai:judge"):
        tournament.run_tournament(
            "goal",
            num_ideas=2,
            rounds=1,
            judge_model="openai:judge",
            generator_model="openai:generator",
            budget=BudgetConfig(max_cost_usd=1),
            pricing=pricing,
        )
