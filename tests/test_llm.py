import pytest

from league_of_idea import llm
from league_of_idea.usage import BudgetConfig, UsageStats, UsageTracker


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("openai:gpt-4o-mini", ("openai", "gpt-4o-mini")),
        ("anthropic/claude-sonnet", ("anthropic", "claude-sonnet")),
    ],
)
def test_split_model_ref_accepts_current_and_legacy_formats(value, expected):
    assert llm._split_model_ref(value) == expected


def test_split_model_ref_requires_provider():
    with pytest.raises(llm.LLMError, match="must include a provider"):
        llm._split_model_ref("gpt-4o-mini")


def test_parse_json_tolerates_fenced_output():
    assert llm._parse_json('```json\n{"winner": "A"}\n```') == {"winner": "A"}


def test_complete_passes_provider_and_model_separately(monkeypatch):
    captured = {}

    class Message:
        content = "ok"

    class Choice:
        message = Message()

    class Response:
        choices = [Choice()]

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(llm, "_load_any_llm", lambda: fake_completion)

    assert llm.complete("openai/gpt-4o-mini", "hello") == "ok"
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-4o-mini"


def test_complete_records_provider_usage(monkeypatch):
    response = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }
    monkeypatch.setattr(llm, "_load_any_llm", lambda: lambda **kwargs: response)
    stats = UsageStats()

    llm.complete(
        "openai:test",
        "hello",
        usage_tracker=UsageTracker(BudgetConfig(), stats),
    )

    assert stats.calls == 1
    assert stats.prompt_tokens == 11
    assert stats.completion_tokens == 7
    assert stats.total_tokens == 18
