from __future__ import annotations

import json

import pytest

from tooltether import AdapterError, Runtime, ToolValidationError, tool
from tooltether.adapters import AdapterMaturity, adapter_registry


@tool
def add(a: int, b: int) -> int:
    """Add two integers for adapter contracts."""
    return a + b


def test_builtin_adapters_report_maturity_and_capabilities() -> None:
    info = {name: adapter_registry.get(name).info() for name in adapter_registry.names()}
    assert info["openai"].maturity == AdapterMaturity.STABLE
    assert info["anthropic"].maturity == AdapterMaturity.STABLE
    assert info["mcp"].maturity == AdapterMaturity.STABLE
    assert info["langchain"].maturity == AdapterMaturity.BETA
    assert info["langgraph"].maturity == AdapterMaturity.BETA
    for name in ("crewai", "autogen", "smolagents"):
        assert info[name].maturity == AdapterMaturity.EXPERIMENTAL
        assert info[name].recommended is False
    assert info["smolagents"].capabilities.async_execution is False


@pytest.mark.parametrize("name", ("openai", "anthropic", "mcp"))
def test_schema_export_contract_preserves_metadata(name: str) -> None:
    exported = add.export(name)
    rendered = json.dumps(exported, sort_keys=True)
    assert "add" in rendered
    assert "Add two integers" in rendered
    assert "a" in rendered
    assert "b" in rendered


@pytest.mark.asyncio
async def test_openai_adapter_contract_valid_invalid_and_malformed_calls() -> None:
    adapter = adapter_registry.get("openai")
    runtime = Runtime()
    valid = await adapter.execute_tool_call(
        runtime,
        add,
        {"id": "call-1", "function": {"name": "add", "arguments": '{"a":2,"b":3}'}},
    )
    assert valid == {"type": "function_call_output", "call_id": "call-1", "output": "5"}

    with pytest.raises(AdapterError, match="not valid JSON"):
        await adapter.execute_tool_call(
            runtime,
            add,
            {"id": "call-2", "function": {"name": "add", "arguments": "{"}},
        )

    with pytest.raises(AdapterError, match="expected 'add'"):
        await adapter.execute_tool_call(
            runtime,
            add,
            {"id": "call-3", "function": {"name": "other", "arguments": "{}"}},
        )

    with pytest.raises(ToolValidationError):
        await adapter.execute_tool_call(
            runtime,
            add,
            {"id": "call-4", "function": {"name": "add", "arguments": '{"a":"x"}'}},
        )


@pytest.mark.asyncio
async def test_anthropic_adapter_contract_valid_and_error_result() -> None:
    adapter = adapter_registry.get("anthropic")
    runtime = Runtime()
    valid = await adapter.execute_tool_use(
        runtime, add, {"id": "toolu-1", "name": "add", "input": {"a": 4, "b": 5}}
    )
    assert valid == {"type": "tool_result", "tool_use_id": "toolu-1", "content": "9"}

    error = await adapter.execute_tool_use(
        runtime, add, {"id": "toolu-2", "name": "add", "input": {"a": "bad"}}
    )
    assert error["type"] == "tool_result"
    assert error["tool_use_id"] == "toolu-2"
    assert error["is_error"] is True


@pytest.mark.asyncio
async def test_adapter_timeout_surfaces_tooltether_error() -> None:
    @tool(timeout=0.01)
    async def slow() -> str:
        """Timeout through adapter execution."""
        import asyncio

        await asyncio.sleep(1)
        return "late"

    adapter = adapter_registry.get("anthropic")
    error = await adapter.execute_tool_use(
        Runtime(), slow, {"id": "toolu-timeout", "name": "slow", "input": {}}
    )
    assert error["is_error"] is True
    assert "timeout" in error["content"] or "timed out" in error["content"]
