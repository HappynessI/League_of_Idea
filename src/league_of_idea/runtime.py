"""Runtime controls shared by all provider calls in a tournament."""

from __future__ import annotations

import threading
import time

from pydantic import BaseModel, Field


class RuntimeConfig(BaseModel):
    """Network reliability and provider pacing settings."""

    request_timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=2, ge=0)
    requests_per_second: float | None = Field(default=None, gt=0)


class RuntimeController:
    """Thread-safe provider rate limiter attached to one tournament run."""

    def __init__(self, config: RuntimeConfig):
        self.config = config
        self._lock = threading.Lock()
        self._next_allowed: dict[str, float] = {}

    def wait(self, provider: str) -> None:
        rate = self.config.requests_per_second
        if rate is None:
            return
        interval = 1.0 / rate
        with self._lock:
            now = time.monotonic()
            allowed = max(now, self._next_allowed.get(provider, now))
            self._next_allowed[provider] = allowed + interval
        delay = allowed - now
        if delay > 0:
            time.sleep(delay)
