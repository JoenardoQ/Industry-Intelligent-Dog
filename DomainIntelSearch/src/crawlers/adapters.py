"""Explicit source-adapter contracts and normalized collection outcomes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Generic, TypeVar


T = TypeVar("T")
SOURCE_STATES = frozenset(
    {"fresh", "stale", "degraded", "manual", "unconfigured", "failed"})


@dataclass(frozen=True)
class CollectionResult(Generic[T]):
    adapter: str
    status: str
    items: tuple[T, ...] = ()
    error_code: str = ""
    error_message: str = ""
    retry_after: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in SOURCE_STATES:
            raise ValueError(f"unknown collection status: {self.status}")
        if self.status == "fresh" and self.error_code:
            raise ValueError("fresh result cannot carry an error")


def bounded_backoff(failures: int, *, base_seconds: int = 60,
                    ceiling_seconds: int = 21_600) -> int:
    """Exponential retry delay capped at six hours by default."""
    return min(ceiling_seconds, base_seconds * (2 ** max(0, failures - 1)))


def retry_timestamp(failures: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(seconds=bounded_backoff(failures))).isoformat()


class SourceAdapter:
    name = "unconfigured"

    def collect(self, source: dict, fetch: Callable[[dict], list[T]]) -> CollectionResult[T]:
        return CollectionResult(adapter=self.name, status="unconfigured",
                                error_code="adapter_unconfigured")


class FeedAdapter(SourceAdapter):
    name = "feed"

    def collect(self, source: dict, fetch: Callable[[dict], list[T]]) -> CollectionResult[T]:
        try:
            return CollectionResult(adapter=self.name, status="fresh",
                                    items=tuple(fetch(source)))
        except Exception as exc:  # boundary normalizes collector-specific errors
            failures = int((source.get("health") or {}).get("consecutive_failures") or 0) + 1
            return CollectionResult(
                adapter=self.name, status="failed",
                error_code=type(exc).__name__.lower(),
                error_message=str(exc)[:240], retry_after=retry_timestamp(failures))


class ApiAdapter(FeedAdapter):
    name = "api"


class ManualAdapter(SourceAdapter):
    name = "manual"

    def collect(self, source: dict, fetch: Callable[[dict], list[T]]) -> CollectionResult[T]:
        return CollectionResult(adapter=self.name, status="manual",
                                error_code="manual_collection_required")


class AdapterRegistry:
    """Select from structured fields only; never infer capability from prose."""

    def __init__(self) -> None:
        self._adapters = {
            "feed": FeedAdapter(), "rss": FeedAdapter(), "atom": FeedAdapter(),
            "api": ApiAdapter(), "manual": ManualAdapter(),
            "unconfigured": SourceAdapter(),
        }

    def select(self, source: dict) -> SourceAdapter:
        monitoring = str(source.get("monitoring_status") or "").casefold()
        if monitoring in {"recommended_manual", "manual", "reserve", "quarantined"}:
            return self._adapters["manual"]
        access = str(source.get("access") or "").casefold()
        if access in self._adapters:
            return self._adapters[access]
        if source.get("rss_url") or source.get("feed_url"):
            return self._adapters["feed"]
        return self._adapters["unconfigured"]


DEFAULT_ADAPTERS = AdapterRegistry()
