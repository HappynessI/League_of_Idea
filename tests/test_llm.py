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


def test_complete_passes_timeout_and_retries_transient_failure(monkeypatch):
    attempts = []
    response = {"choices": [{"message": {"content": "ok"}}]}

    def fake_completion(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise TimeoutError("slow")
        return response

    monkeypatch.setattr(llm, "_load_any_llm", lambda: fake_completion)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    from league_of_idea.runtime import RuntimeConfig, RuntimeController

    runtime = RuntimeController(RuntimeConfig(request_timeout_seconds=12, max_retries=1))
    assert llm.complete("openai:test", "hello", runtime=runtime) == "ok"
    assert len(attempts) == 2
    assert attempts[0]["timeout"] == 12


def test_complete_does_not_retry_invalid_request(monkeypatch):
    calls = 0

    class InvalidRequestError(Exception):
        pass

    def fake_completion(**kwargs):
        nonlocal calls
        calls += 1
        raise InvalidRequestError("bad input")

    monkeypatch.setattr(llm, "_load_any_llm", lambda: fake_completion)
    with pytest.raises(llm.LLMError, match="1 attempt"):
        llm.complete("openai:test", "hello")
    assert calls == 1
