from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from tooltether import (
    FeedbackStore,
    ModelCandidate,
    NonInteractiveApprovalHandler,
    OptimizationMode,
    OptimizationPolicy,
    OptimizationRecommendation,
    PermissionDecisionType,
    Policy,
    Runtime,
    RuntimeConfig,
    RuntimeEvent,
    TelemetryRecord,
    ToolDefinitionError,
    ToolResult,
    ToolTetherError,
    ToolValidationError,
    UnsafeOperationError,
    tool,
)
from tooltether.adapters import adapter_registry
from tooltether.adapters.base import BaseAdapter
from tooltether.cli import main
from tooltether.errors import AdapterError
from tooltether.models import ExecutionContext, Outcome
from tooltether.observability import EventBus, LocalMetrics, OpenTelemetryHook
from tooltether.registry import AdapterRegistry, ToolRegistry
from tooltether.schema import openai_strict_schema


@tool(aliases=["sum"])
def add(a: int, b: int) -> int:
    """Add values for additional paths."""
    return a + b


def _module(name: str, **attributes: object) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def test_feedback_metrics_and_event_bus() -> None:
    feedback = FeedbackStore()
    record = feedback.record(execution_id="x", quality=0.8, accepted=True)
    assert feedback.for_execution("x") == (record,)
    assert feedback.for_execution("missing") == ()

    metrics = LocalMetrics()
    metrics.record("add", "succeeded", 0.1, 2, True)
    summary = metrics.summary()
    assert summary["success_rate"] == 1
    assert summary["counters"]["retries"] == 1


@pytest.mark.asyncio
async def test_event_bus_and_otel_hook() -> None:
    received: list[str] = []

    async def hook(event: RuntimeEvent) -> None:
        received.append(event.name)

    bus = EventBus()
    bus.subscribe(hook)
    await bus.emit(RuntimeEvent(name="event", execution_id="x"))
    assert received == ["event"]

    class Span:
        def __init__(self) -> None:
            self.events: list[str] = []

        def add_event(self, name, attributes):
            self.events.append(name)

    span = Span()
    await OpenTelemetryHook(SimpleNamespace(get_current_span=lambda: span))(
        RuntimeEvent(name="otel", execution_id="x")
    )
    assert span.events == ["otel"]


def test_registry_aliases_and_adapter_registry() -> None:
    registry = ToolRegistry()
    registry.register(add)
    assert registry.get("sum") is add
    assert registry.search(tag="missing") == ()
    adapters: AdapterRegistry[object] = AdapterRegistry()
    adapters.register("x", object())
    assert adapters.names() == ("x",)
    with pytest.raises(ValueError, match="already registered"):
        adapters.register("x", object())


def test_schema_definition_error_paths() -> None:
    def variadic(*values: int) -> int:
        """Use unsupported variadic input."""
        return sum(values)

    with pytest.raises(ToolDefinitionError, match="unsupported signature"):
        tool(variadic)

    def missing_output(value: int):
        """Miss an output annotation."""
        return value

    with pytest.raises(ToolDefinitionError, match="return type annotation"):
        tool(missing_output)

    schema = {"type": "object", "properties": {"nested": {"type": "object"}}}
    assert openai_strict_schema(schema)["properties"]["nested"]["additionalProperties"] is False


@pytest.mark.asyncio
async def test_bound_tool_context_manager_and_non_stream_fallback() -> None:
    runtime = Runtime()
    assert (await runtime.bind(add).arun(a=2, b=3)).value == 5
    streamed = [item async for item in runtime.astream(add, {"a": 3, "b": 4})]
    assert streamed == [7]
    await runtime.close()

    async with Runtime() as managed:
        assert (await managed.arun(add, {"a": 1, "b": 1})).value == 2


def test_bound_tool_sync_call() -> None:
    assert Runtime().bind(add)(a=1, b=2).value == 3


def test_runtime_config_json_and_secret_repr(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"storage_path": "db.sqlite"}), encoding="utf-8")
    config = RuntimeConfig.from_file(path)
    assert config.storage_path == "db.sqlite"
    assert "secret_value" not in RuntimeConfig(secret_value="hidden").model_dump()


@pytest.mark.asyncio
async def test_policy_builders_and_default_approval() -> None:
    policy = Policy(default=PermissionDecisionType.DENY)
    policy.require_approval(tool="add", rule_id="approval")
    policy.limit(tool="add", max_calls=2, window="1h", rule_id="limit", priority=-1)
    context = ExecutionContext(
        execution_id="x",
        correlation_id="x",
        tool_name="add",
        tool_version="1.0.0",
        tool_fingerprint=add.fingerprint.value,
    )
    decision = policy.simulate(add, context)
    assert decision.decision == PermissionDecisionType.REQUIRE_APPROVAL
    allowed = await NonInteractiveApprovalHandler(allow=True)(
        SimpleNamespace(context=context, reason="test")
    )
    assert allowed.decision == PermissionDecisionType.ALLOW_ONCE


@pytest.mark.asyncio
async def test_base_adapter_paths() -> None:
    class Dummy(BaseAdapter):
        def export_tool(self, tool, runtime=None):
            return {"name": tool.name}

    adapter = Dummy()
    runtime = Runtime()
    result = await adapter.execute_call(runtime, add, {"a": 5, "b": 6})
    assert result.value == 11
    assert adapter.normalize_result(result) == 11
    assert adapter.capabilities().strict_schema
    assert adapter.compatibility_check()[0]
    with pytest.raises(NotImplementedError):
        adapter.import_tool({})


def test_optional_framework_adapter_shapes(monkeypatch) -> None:
    class StructuredTool:
        @classmethod
        def from_function(cls, **kwargs):
            return SimpleNamespace(**kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_core.tools",
        _module("langchain_core.tools", StructuredTool=StructuredTool),
    )
    exported = add.export("langchain", runtime=Runtime())
    assert exported.name == "add"
    assert exported.func(a=2, b=3) == 5

    class CrewBaseTool:
        def __init__(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "crewai.tools", _module("crewai.tools", BaseTool=CrewBaseTool))
    crew = add.export("crewai", runtime=Runtime())
    assert crew._run(a=3, b=4) == 7

    class FunctionTool:
        def __init__(self, function, description, name):
            self.function = function
            self.name = name

    monkeypatch.setitem(
        sys.modules, "autogen_core.tools", _module("autogen_core.tools", FunctionTool=FunctionTool)
    )
    autogen = add.export("autogen", runtime=Runtime())
    assert autogen.name == "add"

    class SmolTool:
        def __init__(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "smolagents", _module("smolagents", Tool=SmolTool))
    smol = add.export("smolagents", runtime=Runtime())
    assert smol.forward(a=4, b=5) == 9
    assert smol.inputs["a"]["type"] == "integer"


def test_mcp_server_shape_with_sdk_contract_fake(monkeypatch) -> None:
    class Server:
        def __init__(self, name):
            self.name = name
            self.list_handler = None
            self.call_handler = None

        def list_tools(self):
            def decorator(function):
                self.list_handler = function
                return function

            return decorator

        def call_tool(self):
            def decorator(function):
                self.call_handler = function
                return function

            return decorator

    class MCPTool:
        @classmethod
        def model_validate(cls, value):
            return value

    class TextContent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class CallToolResult:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(
        sys.modules, "mcp.server.lowlevel", _module("mcp.server.lowlevel", Server=Server)
    )
    monkeypatch.setitem(
        sys.modules,
        "mcp.types",
        _module(
            "mcp.types",
            MCPTool=MCPTool,
            Tool=MCPTool,
            TextContent=TextContent,
            CallToolResult=CallToolResult,
        ),
    )
    registry = ToolRegistry()
    registry.register(add)
    server = adapter_registry.get("mcp").create_server(registry, Runtime())
    assert asyncio.run(server.list_handler())[0]["name"] == "add"
    response = asyncio.run(server.call_handler("add", {"a": 1, "b": 2}))
    assert response.isError is False


def test_cli_remaining_read_only_commands(capsys) -> None:
    reference = "test_additional_paths:add"
    assert main(["--json", "validate", reference]) == 0
    capsys.readouterr()
    assert main(["--json", "policy-check", reference, "--input", '{"a":1,"b":2}']) == 0
    capsys.readouterr()
    assert main(["--json", "telemetry-summary"]) == 0
    capsys.readouterr()
    assert main(["--json", "audit-list", "--limit", "1"]) == 0
    capsys.readouterr()
    assert main(["--json", "optimize-recommend", reference]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_errors_and_serialization() -> None:
    error = ToolTetherError("safe", safe_details={"api_key": "hidden"})
    assert error.to_dict()["details"]["api_key"] == "[REDACTED]"
    result = ToolResult(
        execution_id="x",
        tool_name="add",
        tool_version="1",
        duration_seconds=0,
        outcome=Outcome.SUCCEEDED,
    )
    assert '"execution_id":"x"' in result.to_json()
    with pytest.raises(ToolValidationError):
        Runtime().run(add, {"a": 1, "b": 2, "extra": 3})


def test_optimizer_off_mode() -> None:
    runtime = Runtime(RuntimeConfig(optimization=OptimizationPolicy(mode=OptimizationMode.OFF)))
    assert asyncio.run(runtime.optimizer.recommend(add)) == []


@pytest.mark.asyncio
async def test_adapter_invalid_call_paths() -> None:
    openai = adapter_registry.get("openai")
    with pytest.raises(AdapterError, match="expected"):
        await openai.execute_tool_call(
            Runtime(), add, {"id": "x", "function": {"name": "other", "arguments": "{}"}}
        )
    with pytest.raises(AdapterError, match="valid JSON"):
        await openai.execute_tool_call(
            Runtime(), add, {"id": "x", "function": {"name": "add", "arguments": "{"}}
        )
    anthropic = adapter_registry.get("anthropic")
    with pytest.raises(AdapterError, match="expected"):
        await anthropic.execute_tool_use(Runtime(), add, {"id": "x", "name": "other", "input": {}})


@pytest.mark.asyncio
async def test_optimizer_cache_and_safety_paths() -> None:
    runtime = Runtime(RuntimeConfig(optimization=OptimizationPolicy(min_samples=5)))
    for index in range(5):
        await runtime.storage.add_telemetry(
            TelemetryRecord(
                execution_id=str(index),
                tool_fingerprint=add.fingerprint.value,
                environment="development",
                latency_seconds=0.1,
                outcome=Outcome.SUCCEEDED,
                attempts=1,
                cache_hit=index < 2,
            )
        )
    recommendations = await runtime.optimizer.recommend(add)
    assert {item.setting for item in recommendations} == {"timeout", "cache"}
    assert "Observed" in await runtime.optimizer.explain(add)
    wrong = recommendations[0].model_copy(update={"tool_fingerprint": "b" * 64})
    with pytest.raises(UnsafeOperationError, match="fingerprint"):
        await runtime.optimizer.apply(add, wrong)

    @tool(side_effects="write", permissions=["records:write"])
    def mutate() -> str:
        """Mutate a record."""
        return "done"

    unsafe = OptimizationRecommendation(
        recommendation_id="unsafe",
        tool_fingerprint=mutate.fingerprint.value,
        setting="cache",
        current_value=False,
        recommended_value=True,
        reason="test",
        sample_size=10,
        confidence=0.8,
    )
    with pytest.raises(UnsafeOperationError, match="side-effecting"):
        await runtime.optimizer.apply(mutate, unsafe)


def test_model_selection_additional_objectives() -> None:
    candidates = [
        ModelCandidate(
            provider="a", model="slow", estimated_cost=1, estimated_latency=5, quality=0.9
        ),
        ModelCandidate(
            provider="b", model="fast", estimated_cost=2, estimated_latency=1, quality=0.7
        ),
    ]
    from tooltether import select_model

    assert select_model(candidates, objective="minimize_latency").candidate.model == "fast"
    assert select_model(candidates, objective="maximize_quality").candidate.model == "slow"
    assert select_model(candidates, objective="balanced").explanation.startswith("Selected")
