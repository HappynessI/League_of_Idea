from league_of_idea.runtime import RuntimeConfig, RuntimeController


def test_rate_limiter_spaces_requests_per_provider(monkeypatch):
    times = iter([10.0, 10.0, 10.0])
    sleeps = []
    monkeypatch.setattr("league_of_idea.runtime.time.monotonic", lambda: next(times))
    monkeypatch.setattr("league_of_idea.runtime.time.sleep", sleeps.append)
    runtime = RuntimeController(RuntimeConfig(requests_per_second=2))

    runtime.wait("openai")
    runtime.wait("openai")
    runtime.wait("anthropic")

    assert sleeps == [0.5]
