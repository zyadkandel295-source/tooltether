"""Small non-gating benchmark smoke for release reviews.

This records rough local timings only. It intentionally does not enforce pass/fail
thresholds because developer machines and CI runners vary too much for stable
microbenchmark gates.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable

from tooltether import Runtime, ToolRegistry, tool


@tool
def increment(value: int) -> int:
    """Increment an integer."""
    return value + 1


@tool
async def async_increment(value: int) -> int:
    """Increment an integer asynchronously."""
    await asyncio.sleep(0)
    return value + 1


def main() -> None:
    runtime = Runtime()
    samples = 100
    results = {
        "direct_ms": _measure(lambda: increment.function(1), samples),
        "runtime_ms": _measure(lambda: runtime.run(increment, {"value": 1}), samples),
        "serialize_schema_ms": _measure(lambda: json.dumps(increment.manifest()), samples),
        "register_1_ms": _measure(lambda: _register_many(1), 10),
        "register_10_ms": _measure(lambda: _register_many(10), 10),
        "register_100_ms": _measure(lambda: _register_many(100), 3),
        "async_runtime_ms": asyncio.run(_measure_async(runtime, samples)),
    }
    print(json.dumps(results, indent=2, sort_keys=True))


def _measure(function: Callable[[], object], samples: int) -> float:
    started = time.perf_counter()
    for _ in range(samples):
        function()
    return round((time.perf_counter() - started) * 1000 / samples, 4)


async def _measure_async(runtime: Runtime, samples: int) -> float:
    started = time.perf_counter()
    for _ in range(samples):
        await runtime.arun(async_increment, {"value": 1})
    return round((time.perf_counter() - started) * 1000 / samples, 4)


def _register_many(count: int) -> ToolRegistry:
    registry = ToolRegistry()
    for index in range(count):

        @tool(name=f"tool_{index}")
        def generated(value: int, offset: int = index) -> int:
            """Generated benchmark tool."""
            return value + offset

        registry.register(generated)
    return registry


if __name__ == "__main__":
    main()
