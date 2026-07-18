from tooltether import Runtime, tool


@tool
def double(value: int) -> int:
    """Double an integer."""
    return value * 2


if __name__ == "__main__":
    runtime = Runtime()
    exported = double.export("langchain", runtime=runtime)
    print(exported.invoke({"value": 3}))
