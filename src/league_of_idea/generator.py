"""Generate candidate ideas from a research goal.

All generation prompts live here so they are easy to tune in one place.
"""

from __future__ import annotations

from . import llm
from .models import Idea

GENERATE_SYSTEM = (
    "You are a creative research strategist. You produce concrete, distinct, "
    "non-overlapping ideas. Each idea must be self-contained and specific."
)

GENERATE_TEMPLATE = """Research goal:
{goal}

Generate exactly {n} distinct candidate ideas that address this goal.
Each idea should be one or two sentences, concrete and actionable, and clearly
different from the others (different angle, mechanism or assumption).

Return ONLY a JSON array of {n} strings, e.g.:
["idea one ...", "idea two ...", ...]
"""

EVOLVE_SYSTEM = (
    "You are a research strategist who improves existing ideas. You keep the "
    "strongest core and fix weaknesses, producing a sharper variant."
)

EVOLVE_TEMPLATE = """Research goal:
{goal}

Here is a strong idea that ranked highly in a competition:
"{content}"

Produce ONE improved variant: keep what makes it strong, address a likely
weakness, and make it more specific or more feasible. Do not just rephrase.

Return ONLY the improved idea as a single JSON string, e.g.:
"improved idea ..."
"""


def generate_ideas(goal: str, n: int, model: str) -> list[Idea]:
    """Generate ``n`` first-generation ideas for ``goal``."""
    prompt = GENERATE_TEMPLATE.format(goal=goal, n=n)
    data = llm.complete_json(model, prompt, system=GENERATE_SYSTEM)
    if not isinstance(data, list):
        raise llm.LLMError(f"Expected a JSON array of ideas, got: {data!r}")
    ideas = [
        Idea(content=str(item).strip(), generation=0, created_by=model)
        for item in data
        if str(item).strip()
    ]
    return ideas[:n]


def evolve_idea(goal: str, parent: Idea, model: str) -> Idea:
    """Produce one improved child idea from ``parent``."""
    prompt = EVOLVE_TEMPLATE.format(goal=goal, content=parent.content)
    data = llm.complete_json(model, prompt, system=EVOLVE_SYSTEM)
    content = data if isinstance(data, str) else str(data)
    return Idea(
        content=content.strip(),
        generation=parent.generation + 1,
        parent_id=parent.id,
        created_by=model,
    )
