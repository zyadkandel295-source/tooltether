"""Benchmark sustained load execution stability and memory overhead."""

import asyncio
import platform
import statistics
import time

from tooltether import Runtime, tool


@tool
def add(a: int, b: int) -> int:
    """Add integers."""
    return a + b


async def main() -> None:
    runtime = Runtime()
    iterations = 2000
    print(
        {
            "hardware": platform.platform(),
            "python": platform.python_version(),
            "iterations": iterations,
        }
    )

    latencies = []
    t_start = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter()
        await runtime.arun(add, {"a": i, "b": i + 1})
        latencies.append((time.perf_counter() - t0) * 1000)
    total_time = time.perf_counter() - t_start

    ordered = sorted(latencies)
    n = len(ordered)
    print(
        {
            "total_requests": n,
            "total_seconds": round(total_time, 2),
            "req_per_sec": round(n / total_time, 1),
            "median_ms": round(statistics.median(ordered), 4),
            "p95_ms": round(ordered[int(0.95 * (n - 1))], 4),
            "p99_ms": round(ordered[int(0.99 * (n - 1))], 4),
            "max_ms": round(max(ordered), 4),
            "stdev_ms": round(statistics.pstdev(ordered), 4),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
