"""The judge — given the goal and two ideas, decide which is better.

The judging criteria are the heart of whether Elo scores mean anything. The
default rubric weighs novelty, feasibility and relevance to the goal.
"""

from __future__ import annotations

from . import llm
from .models import Idea, MatchResult

JUDGE_SYSTEM = (
    "You are a rigorous, impartial research reviewer. You compare two ideas and "
    "pick the stronger one. You are not swayed by which is presented first."
)

JUDGE_TEMPLATE = """Research goal:
{goal}

Compare the two candidate ideas below and decide which better serves the goal.
Judge on three criteria, weighted equally:
- Novelty: how original / non-obvious is it?
- Feasibility: can it realistically be carried out?
- Relevance: how directly does it advance the stated goal?

Idea A:
{idea_a}

Idea B:
{idea_b}

Return ONLY a JSON object of the form:
{{"winner": "A", "reasoning": "one or two sentences explaining the verdict"}}
where "winner" is exactly "A" or "B".
"""


def judge_match(goal: str, idea_a: Idea, idea_b: Idea, model: str) -> MatchResult:
    """Judge a single match between two ideas."""
    prompt = JUDGE_TEMPLATE.format(goal=goal, idea_a=idea_a.content, idea_b=idea_b.content)
    data = llm.complete_json(model, prompt, system=JUDGE_SYSTEM)
    try:
        return MatchResult.model_validate(data)
    except Exception as exc:
        raise llm.LLMError(f"Judge returned malformed result: {data!r} ({exc})") from exc
