from __future__ import annotations

import json
from pathlib import Path

import pytest

from tooltether import MissingExtraError, Runtime, ToolDefinitionError, ToolRegistry, tool
from tooltether.adapters import adapter_registry
from tooltether.cli import main


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def test_schema_adapters() -> None:
    openai = add.export("openai")
    assert openai["function"]["strict"] is True
    assert openai["function"]["parameters"]["additionalProperties"] is False
    anthropic = add.export("anthropic")
    assert anthropic["input_schema"]["type"] == "object"
    mcp = add.export("mcp")
    assert mcp["annotations"]["readOnlyHint"] is True
    assert mcp["inputSchema"] == add.spec.input_schema


@pytest.mark.asyncio
async def test_openai_call_mapping_preserves_id() -> None:
    adapter = adapter_registry.get("openai")
    output = await adapter.execute_tool_call(
        Runtime(),
        add,
        {"id": "call-1", "function": {"name": "add", "arguments": '{"a":2,"b":5}'}},
    )
    assert output["call_id"] == "call-1"
    assert output["output"] == "7"


@pytest.mark.asyncio
async def test_anthropic_call_mapping_and_error() -> None:
    adapter = adapter_registry.get("anthropic")
    output = await adapter.execute_tool_use(
        Runtime(), add, {"id": "toolu-1", "name": "add", "input": {"a": 2, "b": 6}}
    )
    assert output["tool_use_id"] == "toolu-1"
    assert output["content"] == "8"
    error = await adapter.execute_tool_use(
        Runtime(), add, {"id": "toolu-2", "name": "add", "input": {"a": "bad", "b": 6}}
    )
    assert error["is_error"] is True


def test_missing_framework_extras_are_helpful() -> None:
    runtime = Runtime()
    for name in ("crewai", "autogen", "smolagents"):
        with pytest.raises(MissingExtraError, match="pip install"):
            add.export(name, runtime=runtime)


def test_registry_versions_duplicates_disable_and_search() -> None:
    registry = ToolRegistry()
    registry.register(add)
    assert registry.get("add") is add
    assert registry.search(capability="missing") == ()
    assert registry.manifest()[0]["name"] == "add"
    with pytest.raises(ToolDefinitionError, match="Duplicate"):
        registry.register(add)
    registry.disable("add")
    with pytest.raises(KeyError, match="disabled"):
        registry.get("add")
    registry.enable("add", "1.0.0")
    assert registry.get("add") is add


def test_cli_version_doctor_inspect_and_run(capsys) -> None:
    assert main(["--json", "version"]) == 0
    assert json.loads(capsys.readouterr().out)["version"] == "0.1.0"
    assert main(["--json", "doctor"]) == 0
    assert "openai" in json.loads(capsys.readouterr().out)["adapters"]
    assert main(["--json", "inspect", "test_adapters_registry_cli:add"]) == 0
    assert json.loads(capsys.readouterr().out)["name"] == "add"
    assert (
        main(
            [
                "--json",
                "run",
                "test_adapters_registry_cli:add",
                "--input",
                '{"a":3,"b":4}',
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["value"] == 7


def test_cli_init_and_errors(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["--json", "init"]) == 0
    assert (tmp_path / "tooltether.toml").exists()
    assert main(["--json", "init"]) == 2
    assert "error" in json.loads(capsys.readouterr().out.splitlines()[-1])
    assert main(["--json", "run", "bad-reference", "--input", "{}"]) == 2


def test_cli_export_and_benchmark(capsys) -> None:
    assert (
        main(
            [
                "--json",
                "export",
                "test_adapters_registry_cli:add",
                "--format",
                "openai",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["type"] == "function"
    assert (
        main(
            [
                "--json",
                "benchmark",
                "test_adapters_registry_cli:add",
                "--input",
                '{"a":1,"b":2}',
                "--iterations",
                "2",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["iterations"] == 2


def test_adapter_registry_unknown() -> None:
    with pytest.raises(KeyError, match="Available"):
        adapter_registry.get("unknown")
