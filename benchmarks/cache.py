"""Benchmark cache performance, hit/miss latencies, and stampede prevention."""

import asyncio
import platform
import time

from tooltether import Runtime, tool

exec_count = 0


@tool(cache=True, idempotent=True)
async def cached_calc(value: int) -> int:
    """Simulate cached computation."""
    global exec_count
    exec_count += 1
    await asyncio.sleep(0.005)
    return value * 2


async def main() -> None:
    global exec_count
    runtime = Runtime()
    print({"hardware": platform.platform(), "python": platform.python_version()})

    # Cold run
    exec_count = 0
    t0 = time.perf_counter()
    res1 = await runtime.arun(cached_calc, {"value": 10})
    cold_time = (time.perf_counter() - t0) * 1000
    cold_execs = exec_count

    # Warm run
    t0 = time.perf_counter()
    res2 = await runtime.arun(cached_calc, {"value": 10})
    warm_time = (time.perf_counter() - t0) * 1000
    warm_execs = exec_count

    # Concurrent stampede
    exec_count = 0
    t0 = time.perf_counter()
    await asyncio.gather(*(runtime.arun(cached_calc, {"value": 99}) for _ in range(50)))
    stampede_time = (time.perf_counter() - t0) * 1000
    stampede_execs = exec_count

    print(
        "Cold Call:",
        {"value": res1.value, "time_ms": round(cold_time, 4), "underlying_executions": cold_execs},
    )
    print(
        "Warm Call:",
        {
            "value": res2.value,
            "time_ms": round(warm_time, 4),
            "underlying_executions": warm_execs - cold_execs,
        },
    )
    print(
        "50 Concurrent Stampede Calls:",
        {"time_ms": round(stampede_time, 4), "underlying_executions": stampede_execs},
    )


if __name__ == "__main__":
    asyncio.run(main())
