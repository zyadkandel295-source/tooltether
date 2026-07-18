from tooltether import tool


@tool
def weather(city: str) -> str:
    """Return fake weather for a city."""
    return f"Clear in {city}"


if __name__ == "__main__":
    print(weather.export("openai"))
    print(weather.export("anthropic"))
