"""Benchmark concurrency scaling from 1 to 500 tasks."""

import asyncio
import platform
import statistics
import time
from typing import Any

from tooltether import Runtime, tool


@tool
def add(a: int, b: int) -> int:
    """Add integers."""
    return a + b


def calc_stats(latencies_ms: list[float], total_time: float) -> dict[str, Any]:
    n = len(latencies_ms)
    ordered = sorted(latencies_ms)
    return {
        "req_per_sec": round(n / total_time, 1) if total_time > 0 else 0,
        "median_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[int(0.95 * (n - 1))], 4),
        "p99_ms": round(ordered[int(0.99 * (n - 1))], 4),
        "max_ms": round(max(ordered), 4),
        "stdev_ms": round(statistics.pstdev(ordered), 4),
    }


async def run_concurrency(runtime: Runtime, level: int) -> dict[str, Any]:
    iterations_per_task = max(2, 500 // level)
    latencies: list[float] = []

    async def worker() -> None:
        for i in range(iterations_per_task):
            t0 = time.perf_counter()
            await runtime.arun(add, {"a": i, "b": i + 1})
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)

    start_t = time.perf_counter()
    tasks = [asyncio.create_task(worker()) for _ in range(level)]
    await asyncio.gather(*tasks, return_exceptions=True)
    total_t = time.perf_counter() - start_t
    return calc_stats(latencies, total_t)


async def main() -> None:
    runtime = Runtime()
    print({"hardware": platform.platform(), "python": platform.python_version()})
    for level in (1, 2, 5, 10, 25, 50, 100, 250, 500):
        res = await run_concurrency(runtime, level)
        print(f"Concurrency {level:3d}: {res}")


if __name__ == "__main__":
    asyncio.run(main())
