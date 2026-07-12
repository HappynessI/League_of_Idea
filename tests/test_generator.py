import pytest

from league_of_idea import generator, llm


def test_generate_ideas_rejects_duplicates(monkeypatch):
    monkeypatch.setattr(
        generator.llm,
        "complete_json",
        lambda *args, **kwargs: ["Same idea", "  same   idea  "],
    )

    with pytest.raises(llm.LLMError, match="distinct ideas"):
        generator.generate_ideas("goal", 2, "openai:test")


def test_generate_ideas_requires_strings(monkeypatch):
    monkeypatch.setattr(
        generator.llm,
        "complete_json",
        lambda *args, **kwargs: ["valid", {"content": "not valid"}],
    )

    with pytest.raises(llm.LLMError, match="must be a string"):
        generator.generate_ideas("goal", 2, "openai:test")


def test_generate_ideas_replenishes_near_duplicates(monkeypatch):
    responses = iter(
        [
            [
                "Deploy solar-powered pumps in flood zones.",
                "Deploy solar powered pumps in flood zones!",
            ],
            ["Create wetland parks to absorb storm water."],
        ]
    )
    calls = 0

    def complete(*args, **kwargs):
        nonlocal calls
        calls += 1
        return next(responses)

    monkeypatch.setattr(generator.llm, "complete_json", complete)

    ideas = generator.generate_ideas("goal", 2, "openai:test")

    assert calls == 2
    assert len(ideas) == 2
    assert ideas[1].content.startswith("Create wetland")


def test_evolve_retries_a_close_paraphrase(monkeypatch):
    parent = generator.Idea(content="Use solar pumps to reduce urban flooding.")
    responses = iter(
        [
            "Use solar pumps to reduce urban flooding!",
            "Convert parking lots into sensor-controlled retention basins.",
        ]
    )
    monkeypatch.setattr(
        generator.llm, "complete_json", lambda *args, **kwargs: next(responses)
    )

    child = generator.evolve_idea("goal", parent, "openai:test")

    assert child.content.startswith("Convert parking")
