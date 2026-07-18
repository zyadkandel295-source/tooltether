from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, TypedDict

import pytest
from pydantic import BaseModel

from tooltether import (
    BaseTool,
    CachePolicy,
    Runtime,
    ToolDefinitionError,
    ToolValidationError,
    ensure_tool,
    tool,
)


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Details(TypedDict):
    label: str
    enabled: bool


class Output(BaseModel):
    total: int


@dataclass
class Item:
    value: int


def test_basic_tool_and_manifest_are_deterministic() -> None:
    @tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    assert Runtime().run(add, {"a": 2, "b": 3}).value == 5
    assert add.name == "add"
    assert add.manifest()["fingerprint"]["value"] == add.fingerprint.value
    assert add.spec.input_schema["additionalProperties"] is False
    assert add.spec.output_schema == {"type": "integer"}
    assert len(add.fingerprint.value) == 64


def test_validation_occurs_before_handler() -> None:
    calls = 0

    @tool
    def guarded(limit: int) -> int:
        """Return a validated limit."""
        nonlocal calls
        calls += 1
        return limit

    with pytest.raises(ToolValidationError, match='Field "limit"') as caught:
        Runtime().run(guarded, {"limit": "many"})
    assert calls == 0
    assert caught.value.code == "tool_validation_error"
    assert caught.value.execution_id


def test_output_validation() -> None:
    @tool
    def broken() -> int:
        """Return the wrong output type."""
        return "wrong"  # type: ignore[return-value]

    with pytest.raises(ToolValidationError, match="returned an invalid value"):
        Runtime().run(broken, {})


def test_nested_schema_features() -> None:
    @tool
    def summarize(
        items: list[Item], mode: Literal["fast", "safe"], color: Color, details: Details | None
    ) -> Output:
        """Summarize typed structured input."""
        return Output(total=sum(item.value for item in items))

    schema = summarize.spec.input_schema
    assert "$defs" in schema
    result = Runtime().run(
        summarize,
        {
            "items": [{"value": 2}, {"value": 4}],
            "mode": "safe",
            "color": "red",
            "details": {"label": "x", "enabled": True},
        },
    )
    assert result.value == Output(total=6)


def test_fingerprint_changes_only_with_contract() -> None:
    @tool(version="1.0.0")
    def first(value: int) -> int:
        """A stable contract."""
        return value

    @tool(name="first", version="1.0.1")
    def second(value: int) -> int:
        """A stable contract."""
        return value

    assert first.fingerprint != second.fingerprint
    assert first.fingerprint == first.fingerprint


def test_unsafe_cache_configuration_rejected() -> None:
    with pytest.raises(ToolDefinitionError, match="side effects"):

        @tool(side_effects="write", cache=True)
        def save(value: str) -> str:
            """Save a value."""
            return value


def test_missing_annotations_and_docstrings_are_actionable() -> None:
    def missing(value):
        return value

    with pytest.raises(ToolDefinitionError, match="description"):
        ensure_tool(missing)

    def untyped(value):
        """An untyped function."""
        return value

    with pytest.raises(ToolDefinitionError, match="type annotation"):
        ensure_tool(untyped)


def test_class_based_tool() -> None:
    class Multiply(BaseTool):
        name = "multiply"
        description = "Multiply two integers."

        async def execute(self, a: int, b: int) -> int:
            return a * b

    wrapped = Multiply().as_tool()
    assert Runtime().run(wrapped, {"a": 3, "b": 4}).value == 12


def test_callable_instance() -> None:
    class Increment:
        """Increment a number."""

        def __call__(self, value: int) -> int:
            return value + 1

    wrapped = ensure_tool(Increment())
    assert wrapped.spec.input_schema["properties"] == {
        "value": {"title": "Value", "type": "integer"}
    }
    assert Runtime().run(wrapped, {"value": 4}).value == 5


def test_callable_instance_without_annotations_is_rejected() -> None:
    class UntypedIncrement:
        """Increment a number without annotations."""

        def __call__(self, value):
            return value + 1

    with pytest.raises(ToolDefinitionError, match="type annotation"):
        ensure_tool(UntypedIncrement())


@pytest.mark.asyncio
async def test_async_callable_instance() -> None:
    class AsyncIncrement:
        """Increment a number asynchronously."""

        async def __call__(self, value: int) -> int:
            return value + 1

    assert (await Runtime().arun(ensure_tool(AsyncIncrement()), {"value": 4})).value == 5


def test_callable_instance_with_annotated_and_optional_inputs() -> None:
    class Normalize:
        """Normalize an optional string with metadata."""

        def __call__(self, value: Annotated[str | None, "optional display name"]) -> str:
            return value or "missing"

    wrapped = ensure_tool(Normalize())
    assert Runtime().run(wrapped, {"value": "x"}).value == "x"
    assert Runtime().run(wrapped, {"value": None}).value == "missing"
    schema = wrapped.spec.input_schema["properties"]["value"]
    assert {item["type"] for item in schema["anyOf"]} == {"string", "null"}


def test_normal_function_annotations_remain_unchanged() -> None:
    @tool
    def echo(value: Annotated[int | None, "normal function metadata"]) -> int | None:
        """Echo an optionally missing integer."""
        return value

    assert Runtime().run(echo, {"value": 7}).value == 7
    assert Runtime().run(echo, {"value": None}).value is None
    assert {item["type"] for item in echo.spec.input_schema["properties"]["value"]["anyOf"]} == {
        "integer",
        "null",
    }


def test_direct_call_and_custom_policy_models() -> None:
    @tool(cache=CachePolicy(enabled=True, ttl_seconds=5))
    def echo(value: str) -> str:
        """Echo a value."""
        return value

    assert echo("hello") == "hello"
    assert echo.spec.cache.enabled
