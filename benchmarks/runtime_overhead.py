import platform
import statistics
import time

from tooltether import Runtime, tool


@tool
def increment(value: int) -> int:
    """Increment an integer."""
    return value + 1


def measure(function, samples: int = 100) -> dict[str, float]:
    for _ in range(10):
        function()
    values = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        function()
        values.append((time.perf_counter_ns() - started) / 1_000_000)
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[int(0.95 * (len(ordered) - 1))],
        "max_ms": max(ordered),
        "stdev_ms": statistics.pstdev(ordered),
    }


if __name__ == "__main__":
    runtime = Runtime()
    print({"hardware": platform.platform(), "python": platform.python_version(), "samples": 100})
    print("direct", measure(lambda: increment.function(1)))
    print("runtime", measure(lambda: runtime.run(increment, {"value": 1})))
