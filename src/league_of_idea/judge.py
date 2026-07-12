"""The judge — given the goal and two ideas, decide which is better.

The judging criteria are the heart of whether Elo scores mean anything. The
default rubric weighs novelty, feasibility and relevance to the goal.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import llm
from .models import Idea, MatchResult
from .rubric import DEFAULT_RUBRIC, Rubric
from .usage import UsageRecorder
from .runtime import RuntimeController

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
    usage_tracker: UsageRecorder | None = None,
    bidirectional: bool = False,
    runtime: RuntimeController | None = None,
) -> MatchResult:
    """Judge a match once or in both A/B orientations."""
    if bidirectional and usage_tracker is not None:
        usage_tracker.ensure_calls_available(2)
    forward = _evaluate_once(goal, idea_a, idea_b, model, rubric, usage_tracker, runtime)
    if not bidirectional:
        return forward

    reverse = _evaluate_once(goal, idea_b, idea_a, model, rubric, usage_tracker, runtime)
    reverse_in_original_order = MatchResult(
        winner={"A": "B", "B": "A", "draw": "draw"}[reverse.winner],
        reasoning=reverse.reasoning,
        scores_a=reverse.scores_b,
        scores_b=reverse.scores_a,
        confidence=reverse.confidence,
    )
    disputed = forward.winner != reverse_in_original_order.winner
    scores_a = _average_scores(forward.scores_a, reverse_in_original_order.scores_a)
    scores_b = _average_scores(forward.scores_b, reverse_in_original_order.scores_b)
    winner = "draw" if disputed else _winner_from_scores(rubric, scores_a, scores_b)
    confidences = [
        value
        for value in (forward.confidence, reverse_in_original_order.confidence)
        if value is not None
    ]
    return MatchResult(
        winner=winner,
        reasoning=(
            f"Forward: {forward.reasoning} Reverse: {reverse.reasoning}"
        ),
        scores_a=scores_a,
        scores_b=scores_b,
        confidence=sum(confidences) / len(confidences) if confidences else None,
        disputed=disputed,
        evaluations=2,
    )


def _evaluate_once(
    goal: str,
    idea_a: Idea,
    idea_b: Idea,
    model: str,
    rubric: Rubric,
    usage_tracker: UsageRecorder | None,
    runtime: RuntimeController | None = None,
) -> MatchResult:
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
        model, prompt, system=JUDGE_SYSTEM, usage_tracker=usage_tracker,
        runtime=runtime,
    )
    try:
        raw = _RawEvaluation.model_validate(data)
        winner = _winner_from_scores(rubric, raw.scores_a, raw.scores_b)
    except Exception as exc:
        raise llm.LLMError(f"Judge returned malformed result: {data!r} ({exc})") from exc
    return MatchResult(
        winner=winner,
        reasoning=raw.reasoning,
        scores_a=raw.scores_a,
        scores_b=raw.scores_b,
        confidence=raw.confidence,
    )


def _winner_from_scores(
    rubric: Rubric,
    scores_a: dict[str, float],
    scores_b: dict[str, float],
) -> str:
    difference = rubric.weighted_total(scores_a) - rubric.weighted_total(scores_b)
    if abs(difference) <= rubric.tie_margin:
        return "draw"
    return "A" if difference > 0 else "B"


def _average_scores(
    first: dict[str, float], second: dict[str, float]
) -> dict[str, float]:
    return {name: (value + second[name]) / 2 for name, value in first.items()}
