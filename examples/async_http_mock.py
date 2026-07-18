import asyncio

from tooltether import Runtime, tool


@tool(timeout=1, retries=1, cache=True, idempotent=True)
async def mock_http_get(url: str) -> dict[str, str]:
    """Simulate a read-only HTTP request without network access."""
    await asyncio.sleep(0.01)
    return {"url": url, "status": "ok"}


async def main() -> None:
    runtime = Runtime()
    print((await runtime.arun(mock_http_get, {"url": "https://example.com"})).value)


if __name__ == "__main__":
    asyncio.run(main())
