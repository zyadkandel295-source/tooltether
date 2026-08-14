from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError

from tooltether import (
    ExecutionMode,
    ExecutionPolicy,
    ExecutionPolicyError,
    Runtime,
    ToolCapabilities,
    ToolRisk,
    tool,
)


@tool
def trusted_add(a: int, b: int) -> int:
    """Add numbers through the default trusted runtime."""
    return a + b


@pytest.mark.asyncio
async def test_default_execution_policy_is_backwards_compatible() -> None:
    assert Runtime().config.execution_policy.mode == ExecutionMode.TRUSTED
    assert (await Runtime().arun(trusted_add, {"a": 2, "b": 3})).value == 5


@pytest.mark.asyncio
async def test_restricted_policy_allows_explicit_safe_tool() -> None:
    runtime = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    assert (await runtime.arun(trusted_add, {"a": 1, "b": 4})).value == 5


@pytest.mark.asyncio
async def test_restricted_policy_rejects_raw_callable_when_disabled() -> None:
    def raw_add(a: int, b: int) -> int:
        """Add numbers without an explicit Tool wrapper."""
        return a + b

    runtime = Runtime(
        execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED, allow_raw_callables=False)
    )
    with pytest.raises(ExecutionPolicyError, match="explicit Tool"):
        await runtime.arun(raw_add, {"a": 2, "b": 3})


@pytest.mark.asyncio
async def test_restricted_policy_rejects_unsafe_declared_tool() -> None:
    @tool(side_effects="write", permissions=["records:write"])
    def mutate_record() -> str:
        """Mutate a record."""
        return "mutated"

    runtime = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    with pytest.raises(ExecutionPolicyError) as caught:
        await runtime.arun(mutate_record, {})
    assert caught.value.safe_details["reason_code"] == "restricted_side_effects"


@pytest.mark.asyncio
async def test_restricted_policy_can_explicitly_allow_side_effecting_tool() -> None:
    @tool(side_effects="write", permissions=["records:write"])
    def mutate_record() -> str:
        """Mutate a record."""
        return "mutated"

    runtime = Runtime(
        execution_policy=ExecutionPolicy(
            mode=ExecutionMode.RESTRICTED, allow_write_side_effects=True
        )
    )
    assert (await runtime.arun(mutate_record, {})).value == "mutated"


@pytest.mark.asyncio
async def test_restricted_policy_rejects_external_capability() -> None:
    @tool(capabilities=ToolCapabilities(external_access=True))
    def external_lookup() -> str:
        """Look up a remote value."""
        return "value"

    runtime = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    with pytest.raises(ExecutionPolicyError) as caught:
        await runtime.arun(external_lookup, {})
    assert caught.value.safe_details["reason_code"] == "restricted_external_access"


@pytest.mark.asyncio
async def test_restricted_policy_rejects_high_risk_tool() -> None:
    @tool(risk=ToolRisk(level="high"))
    def high_risk_action() -> str:
        """Perform a high-risk action."""
        return "done"

    runtime = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    with pytest.raises(ExecutionPolicyError) as caught:
        await runtime.arun(high_risk_action, {})
    assert caught.value.safe_details["reason_code"] == "restricted_high_risk"


@pytest.mark.asyncio
async def test_restricted_policy_applies_to_streaming_path() -> None:
    @tool(side_effects="write", permissions=["stream:write"])
    async def stream_values() -> AsyncIterator[int]:
        """Stream values after a write-like declaration."""
        yield 1

    runtime = Runtime(execution_policy=ExecutionPolicy(mode=ExecutionMode.RESTRICTED))
    with pytest.raises(ExecutionPolicyError):
        async for _ in runtime.astream(stream_values, {}):
            pass


def test_invalid_execution_policy_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutionPolicy(mode="sandboxed")
