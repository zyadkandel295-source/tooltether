"""Async ToolTether execution with the public API."""

from __future__ import annotations

import asyncio

from tooltether import Runtime, tool


@tool
async def lookup(query: str) -> list[str]:
    """Return a fake async lookup result."""
    await asyncio.sleep(0)
    return [query]


async def main() -> None:
    result = await Runtime().arun(lookup, {"query": "safety"})
    assert result.value == ["safety"]
    print(result.value)


if __name__ == "__main__":
    asyncio.run(main())
