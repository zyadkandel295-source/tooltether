"""Typed parameters, defaults, and schema export."""

from tooltether import Runtime, tool


@tool
def calculate_total(price: float, quantity: int, discount: float = 0.0) -> float:
    """Calculate a discounted line total."""
    return price * quantity * (1 - discount)


if __name__ == "__main__":
    runtime = Runtime()
    assert runtime.run(calculate_total, {"price": 10.0, "quantity": 3}).value == 30.0
    assert (
        runtime.run(
            calculate_total,
            {"price": 10.0, "quantity": 3, "discount": 0.1},
        ).value
        == 27.0
    )
    schema = calculate_total.export("openai")
    assert schema["type"] == "function"
    assert "discount" in schema["function"]["parameters"]["properties"]
    print("typed tool ok")
