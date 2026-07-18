import asyncio

from tooltether import OptimizationPolicy, Runtime, RuntimeConfig, tool


@tool
async def controlled_latency(value: int) -> int:
    """Return after controlled local latency."""
    await asyncio.sleep(0.001)
    return value


async def main() -> None:
    runtime = Runtime(RuntimeConfig(optimization=OptimizationPolicy(min_samples=5)))
    for value in range(5):
        await runtime.arun(controlled_latency, {"value": value})
    print(await runtime.optimizer.recommend(controlled_latency))


if __name__ == "__main__":
    asyncio.run(main())
