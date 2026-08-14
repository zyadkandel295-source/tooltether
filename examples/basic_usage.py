"""Minimal ToolTether usage with the public API."""

from tooltether import Runtime, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


if __name__ == "__main__":
    result = Runtime().run(add, {"a": 2, "b": 3})
    assert result.value == 5
    print(result.value)
