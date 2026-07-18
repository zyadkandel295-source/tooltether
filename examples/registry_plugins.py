from tooltether import ToolRegistry, tool


@tool(tags=["math"])
def square(value: int) -> int:
    """Square an integer."""
    return value * value


if __name__ == "__main__":
    registry = ToolRegistry()
    registry.register(square)
    print(registry.manifest())
