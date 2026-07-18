"""Local event, metric, and optional OpenTelemetry facilities."""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .models import RuntimeEvent, RuntimeHook


class EventBus:
    def __init__(self, hooks: Iterable[RuntimeHook] = ()) -> None:
        self._hooks = list(hooks)
        self.events: list[RuntimeEvent] = []

    def subscribe(self, hook: RuntimeHook) -> None:
        self._hooks.append(hook)

    async def emit(self, event: RuntimeEvent) -> None:
        self.events.append(event)
        if self._hooks:
            await asyncio.gather(*(hook(event) for hook in self._hooks), return_exceptions=True)


@dataclass(slots=True)
class LocalMetrics:
    counters: Counter[str] = field(default_factory=Counter)
    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def record(
        self, tool_name: str, outcome: str, latency: float, attempts: int, cache_hit: bool
    ) -> None:
        self.counters["calls"] += 1
        self.counters[f"outcome.{outcome}"] += 1
        self.counters["retries"] += max(0, attempts - 1)
        if cache_hit:
            self.counters["cache_hits"] += 1
        self.latencies[tool_name].append(latency)

    def summary(self) -> dict[str, Any]:
        calls = self.counters["calls"]
        success = self.counters["outcome.succeeded"]
        return {
            "counters": dict(self.counters),
            "success_rate": success / calls if calls else 0.0,
            "latency": {
                name: {
                    "count": len(values),
                    "mean": sum(values) / len(values),
                    "max": max(values),
                }
                for name, values in self.latencies.items()
                if values
            },
        }


class OpenTelemetryHook:
    """Optional API-only integration; never configures a global provider or exporter."""

    def __init__(self, tracer: Any) -> None:
        self.tracer = tracer

    async def __call__(self, event: RuntimeEvent) -> None:
        span = self.tracer.get_current_span() if hasattr(self.tracer, "get_current_span") else None
        if span is not None and hasattr(span, "add_event"):
            span.add_event(event.name, attributes=event.attributes)
