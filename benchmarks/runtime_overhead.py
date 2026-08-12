"""Benchmark pure runtime execution overhead compared to direct Python calls."""

import platform
import statistics
import time
from typing import Any

from tooltether import Runtime, tool


@tool
def increment(value: int) -> int:
    """Increment an integer."""
    return value + 1


def measure(function: Any, samples: int = 100) -> dict[str, float]:
    for _ in range(10):
        function()
    values = []
    t_start = time.perf_counter()
    for _ in range(samples):
        started = time.perf_counter_ns()
        function()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    t_total = time.perf_counter() - t_start
    ordered = sorted(values)
    n = len(ordered)
    return {
        "median_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[int(0.95 * (n - 1))], 4),
        "p99_ms": round(ordered[int(0.99 * (n - 1))], 4),
        "max_ms": round(max(ordered), 4),
        "stdev_ms": round(statistics.pstdev(ordered), 4),
        "req_per_sec": round(samples / t_total, 1),
    }


def main() -> None:
    runtime = Runtime()
    print({"hardware": platform.platform(), "python": platform.python_version(), "samples": 100})
    print("direct", measure(lambda: increment.function(1)))
    print("runtime", measure(lambda: runtime.run(increment, {"value": 1})))


if __name__ == "__main__":
    main()
