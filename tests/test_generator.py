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
