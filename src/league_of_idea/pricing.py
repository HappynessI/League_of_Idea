"""Versioned, user-supplied model pricing for reproducible cost estimates."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator


def normalize_model_ref(model: str) -> str:
    return model.replace("/", ":", 1) if ":" not in model and "/" in model else model


class ModelPrice(BaseModel):
    input_per_million_usd: float = Field(ge=0)
    output_per_million_usd: float = Field(ge=0)

    @model_validator(mode="after")
    def at_least_one_nonzero_rate(self) -> "ModelPrice":
        if self.input_per_million_usd == 0 and self.output_per_million_usd == 0:
            raise ValueError("At least one model price must be greater than zero.")
        return self


class PricingTable(BaseModel):
    version: str = "unpriced"
    models: dict[str, ModelPrice] = Field(default_factory=dict)

    def price_for(self, model: str) -> ModelPrice | None:
        return self.models.get(normalize_model_ref(model)) or self.models.get(model)

    def cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
        price = self.price_for(model)
        if price is None:
            return None
        return (
            prompt_tokens * price.input_per_million_usd
            + completion_tokens * price.output_per_million_usd
        ) / 1_000_000


def load_pricing(path: Path | None = None) -> PricingTable:
    if path is None:
        return PricingTable()
    return PricingTable.model_validate_json(path.read_text(encoding="utf-8"))
