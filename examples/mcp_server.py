from tooltether import Runtime, ToolRegistry, tool
from tooltether.adapters import adapter_registry


@tool
def ping(message: str) -> str:
    """Echo an MCP ping."""
    return message


registry = ToolRegistry()
registry.register(ping)

if __name__ == "__main__":
    server = adapter_registry.get("mcp").create_server(registry, Runtime())
    print(server)
