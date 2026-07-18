from tooltether import Runtime, tool


@tool
def calculate_total(price: float, quantity: int) -> float:
    """Calculate a line-item total."""
    return price * quantity


if __name__ == "__main__":
    print(Runtime().run(calculate_total, {"price": 2.5, "quantity": 4}).value)
