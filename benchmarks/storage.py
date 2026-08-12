"""Benchmark SQLite storage modes, WAL throughput, and audit chain verification."""

import asyncio
import contextlib
import platform
import statistics
import time
from pathlib import Path
from typing import Any

from tooltether import Runtime, SQLiteStorage, tool


@tool
def sample_op(x: int) -> int:
    """Sample operation."""
    return x * 2


async def measure_storage(storage: SQLiteStorage, samples: int = 100) -> dict[str, Any]:
    runtime = Runtime(storage=storage)
    latencies = []
    for i in range(samples):
        t0 = time.perf_counter()
        await runtime.arun(sample_op, {"x": i})
        latencies.append((time.perf_counter() - t0) * 1000)

    audit_valid = await storage.verify_audit_chain()
    audit_count = len(await storage.list_audit(limit=10000))
    ordered = sorted(latencies)
    n = len(ordered)
    return {
        "audit_count": audit_count,
        "hash_chain_valid": audit_valid,
        "median_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[int(0.95 * (n - 1))], 4),
        "p99_ms": round(ordered[int(0.99 * (n - 1))], 4),
        "max_ms": round(max(ordered), 4),
    }


def _cleanup_db(db_file: Path) -> None:
    if db_file.exists():
        with contextlib.suppress(Exception):
            db_file.unlink()


async def main() -> None:
    db_file = Path("benchmark_storage.db")
    _cleanup_db(db_file)

    print({"hardware": platform.platform(), "python": platform.python_version()})

    memory_storage = SQLiteStorage(":memory:")
    mem_res = await measure_storage(memory_storage)
    print("Memory Storage:", mem_res)

    disk_storage = SQLiteStorage(db_file)
    disk_res = await measure_storage(disk_storage)
    print("Disk Storage (WAL+NORMAL):", disk_res)

    await disk_storage.close()
    _cleanup_db(db_file)


if __name__ == "__main__":
    asyncio.run(main())
