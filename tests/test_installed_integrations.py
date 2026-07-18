from __future__ import annotations

import pytest
from langchain_core.tools import StructuredTool
from mcp.server.lowlevel import Server
from mcp.types import Tool as MCPTool

from tooltether import Runtime, ToolRegistry, tool
from tooltether.adapters import adapter_registry


@tool
def add(a: int, b: int) -> int:
    """Add through installed SDK adapters."""
    return a + b


def test_installed_langchain_sync_contract() -> None:
    exported = add.export("langchain", runtime=Runtime())
    assert isinstance(exported, StructuredTool)
    assert exported.invoke({"a": 2, "b": 5}) == 7
    assert exported.args_schema.model_json_schema()["additionalProperties"] is False


@pytest.mark.asyncio
async def test_installed_langchain_async_contract() -> None:
    exported = add.export("langchain", runtime=Runtime())
    assert await exported.ainvoke({"a": 3, "b": 6}) == 9


def test_installed_mcp_server_and_schema_contract() -> None:
    registry = ToolRegistry()
    registry.register(add)
    adapter = adapter_registry.get("mcp")
    server = adapter.create_server(registry, Runtime())
    assert isinstance(server, Server)
    assert server.request_handlers
    schema = adapter.export_tool(add)
    parsed = MCPTool.model_validate(schema)
    assert parsed.name == "add"
    assert parsed.inputSchema["additionalProperties"] is False
