"""The judge — given the goal and two ideas, decide which is better.

The judging criteria are the heart of whether Elo scores mean anything. The
default rubric weighs novelty, feasibility and relevance to the goal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import llm
from .models import Idea, MatchResult
from .rubric import DEFAULT_RUBRIC, Rubric
from .usage import UsageTracker

JUDGE_SYSTEM = (
    "You are a rigorous, impartial research reviewer. You compare two ideas and "
    "pick the stronger one. You are not swayed by which is presented first."
)

JUDGE_TEMPLATE = """Research goal:
{goal}

Compare the two candidate ideas below and decide which better serves the goal.
Score each idea from 1 to 10 on every criterion:
{criteria}

Idea A:
{idea_a}

Idea B:
{idea_b}

Return ONLY a JSON object of the form:
{{
  "scores_a": {{{score_example}}},
  "scores_b": {{{score_example}}},
  "confidence": 0.8,
  "reasoning": "one or two sentences comparing the ideas"
}}
Use exactly the criterion keys shown above. Do not return a winner; the program
will calculate it from the versioned rubric and weights.
"""


class _RawEvaluation(BaseModel):
    scores_a: dict[str, float]
    scores_b: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)


def judge_match(
    goal: str,
    idea_a: Idea,
    idea_b: Idea,
    model: str,
    rubric: Rubric = DEFAULT_RUBRIC,
    usage_tracker: UsageTracker | None = None,
) -> MatchResult:
    """Judge a single match between two ideas."""
    criteria = "\n".join(
        f"- {item.name} (weight {item.weight:g}): {item.description}"
        for item in rubric.criteria
    )
    score_example = ", ".join(f'"{item.name}": 1' for item in rubric.criteria)
    prompt = JUDGE_TEMPLATE.format(
        goal=goal,
        idea_a=idea_a.content,
        idea_b=idea_b.content,
        criteria=criteria,
        score_example=score_example,
    )
    data = llm.complete_json(
        model, prompt, system=JUDGE_SYSTEM, usage_tracker=usage_tracker
    )
    try:
        raw = _RawEvaluation.model_validate(data)
        total_a = rubric.weighted_total(raw.scores_a)
        total_b = rubric.weighted_total(raw.scores_b)
    except Exception as exc:
        raise llm.LLMError(f"Judge returned malformed result: {data!r} ({exc})") from exc
    difference = total_a - total_b
    winner = "draw" if abs(difference) <= rubric.tie_margin else ("A" if difference > 0 else "B")
    return MatchResult(
        winner=winner,
        reasoning=raw.reasoning,
        scores_a=raw.scores_a,
        scores_b=raw.scores_b,
        confidence=raw.confidence,
    )
