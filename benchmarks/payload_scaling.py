"""Benchmark payload scaling performance across 1KB, 100KB, and 1MB objects."""

import asyncio
import platform
import statistics
import time
from typing import Any

from pydantic import BaseModel

from tooltether import Runtime, tool


class SmallData(BaseModel):
    payload: str = "x" * 1024


class MediumData(BaseModel):
    payload: str = "x" * (100 * 1024)


class LargeData(BaseModel):
    payload: str = "x" * (1024 * 1024)


@tool
def process_small(data: SmallData) -> int:
    """Process small payload."""
    return len(data.payload)


@tool
def process_medium(data: MediumData) -> int:
    """Process medium payload."""
    return len(data.payload)


@tool
def process_large(data: LargeData) -> int:
    """Process large payload."""
    return len(data.payload)


async def async_measure(fn: Any, samples: int = 50) -> dict[str, float]:
    for _ in range(5):
        await fn()
    values = []
    t_start = time.perf_counter()
    for _ in range(samples):
        started = time.perf_counter_ns()
        await fn()
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


async def main() -> None:
    runtime = Runtime()
    small_obj = SmallData()
    medium_obj = MediumData()
    large_obj = LargeData()

    print({"hardware": platform.platform(), "python": platform.python_version()})
    print(
        "1 KB Payload",
        await async_measure(lambda: runtime.arun(process_small, {"data": small_obj})),
    )
    print(
        "100 KB Payload",
        await async_measure(lambda: runtime.arun(process_medium, {"data": medium_obj})),
    )
    print(
        "1 MB Payload",
        await async_measure(lambda: runtime.arun(process_large, {"data": large_obj})),
    )


if __name__ == "__main__":
    asyncio.run(main())
