from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from tooltether import (
    CallableApprovalHandler,
    ConcurrencyPolicy,
    ExecutionIdentity,
    NonInteractiveApprovalHandler,
    PermissionDecision,
    PermissionDecisionType,
    Policy,
    RateLimitPolicy,
    Runtime,
    ToolApprovalError,
    ToolPermissionError,
    ToolRateLimitError,
    ToolTetherError,
    ToolTimeoutError,
    UnsafeOperationError,
    tool,
)
from tooltether.models import RuntimeEvent


@pytest.mark.asyncio
async def test_native_async_execution() -> None:
    @tool
    async def add(a: int, b: int) -> int:
        """Add asynchronously."""
        await asyncio.sleep(0)
        return a + b

    assert (await Runtime().arun(add, {"a": 4, "b": 5})).value == 9


@pytest.mark.asyncio
async def test_timeout_is_structured() -> None:
    cleaned = asyncio.Event()

    @tool(timeout=0.02)
    async def slow() -> str:
        """Wait too long."""
        try:
            await asyncio.sleep(1)
        finally:
            cleaned.set()
        return "late"

    with pytest.raises(ToolTimeoutError) as caught:
        await Runtime().arun(slow, {})
    assert caught.value.code == "tool_timeout"
    assert await asyncio.wait_for(cleaned.wait(), 0.2)


@pytest.mark.asyncio
async def test_retry_recovers_for_idempotent_tool() -> None:
    calls = 0

    @tool(idempotent=True, retries=2)
    async def flaky() -> str:
        """Recover after transient failures."""
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("temporary")
        return "ok"

    result = await Runtime().arun(flaky, {})
    assert result.value == "ok"
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_non_idempotent_side_effect_never_retries() -> None:
    calls = 0

    @tool(side_effects="write", permissions=["records:write"], retries=4)
    async def mutate() -> str:
        """Mutate a record."""
        nonlocal calls
        calls += 1
        raise ConnectionError("failed")

    assert mutate.spec.retry.max_attempts == 1
    with pytest.raises(ToolTetherError):
        await Runtime().arun(mutate, {})
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_hit() -> None:
    calls = 0

    @tool(cache=True)
    async def lookup(value: int) -> int:
        """Look up a deterministic value."""
        nonlocal calls
        calls += 1
        return value * 2

    runtime = Runtime()
    first = await runtime.arun(lookup, {"value": 4})
    second = await runtime.arun(lookup, {"value": 4})
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.attempts == 0
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_is_scoped_by_identity() -> None:
    calls = 0

    @tool(cache=True)
    async def whoami() -> int:
        """Count executions."""
        nonlocal calls
        calls += 1
        return calls

    runtime = Runtime()
    alice = ExecutionIdentity(principal="alice")
    bob = ExecutionIdentity(principal="bob")
    assert (await runtime.arun(whoami, {}, identity=alice)).value == 1
    assert (await runtime.arun(whoami, {}, identity=bob)).value == 2


@pytest.mark.asyncio
async def test_idempotency_prevents_duplicate_effect() -> None:
    calls = 0

    @tool(side_effects="write", permissions=["mail:send"], idempotent=True)
    async def send(subject: str) -> str:
        """Send a fake message."""
        nonlocal calls
        calls += 1
        return f"sent:{subject}"

    runtime = Runtime()
    first = await runtime.arun(send, {"subject": "weekly"}, idempotency_key="week-1")
    replay = await runtime.arun(send, {"subject": "weekly"}, idempotency_key="week-1")
    assert first.value == replay.value
    assert replay.idempotency_replay
    assert calls == 1


@pytest.mark.asyncio
async def test_idempotency_requires_contract() -> None:
    @tool
    def read() -> str:
        """Read a value."""
        return "x"

    with pytest.raises(UnsafeOperationError):
        await Runtime().arun(read, {}, idempotency_key="x")


@pytest.mark.asyncio
async def test_policy_denial_never_executes() -> None:
    calls = 0

    @tool
    def secret() -> str:
        """Return a secret marker."""
        nonlocal calls
        calls += 1
        return "secret"

    policy = Policy()
    policy.deny(tool="secret", rule_id="deny-secret")
    with pytest.raises(ToolPermissionError, match="deny-secret"):
        await Runtime(policy=policy).arun(secret, {})
    assert calls == 0


@pytest.mark.asyncio
async def test_approval_handlers() -> None:
    @tool(approval_required=True)
    def action() -> str:
        """Perform an approved action."""
        return "done"

    with pytest.raises(ToolApprovalError):
        await Runtime(approval_handler=NonInteractiveApprovalHandler()).arun(action, {})

    async def approve(request):
        return PermissionDecision(
            decision=PermissionDecisionType.ALLOW_ONCE, reason_code="test_approved"
        )

    result = await Runtime(approval_handler=CallableApprovalHandler(approve)).arun(action, {})
    assert result.value == "done"


@pytest.mark.asyncio
async def test_rate_limit() -> None:
    @tool(rate_limit=RateLimitPolicy(calls=1, period_seconds=10))
    async def limited() -> str:
        """Allow one call."""
        return "ok"

    runtime = Runtime()
    await runtime.arun(limited, {})
    with pytest.raises(ToolRateLimitError):
        await runtime.arun(limited, {})


@pytest.mark.asyncio
async def test_concurrency_limit_releases_semaphore() -> None:
    active = 0
    maximum = 0

    @tool(concurrency=ConcurrencyPolicy(max_concurrent=1, queue_timeout_seconds=1))
    async def serialized(value: int) -> int:
        """Serialize concurrent calls."""
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    runtime = Runtime()
    values = await asyncio.gather(*(runtime.arun(serialized, {"value": i}) for i in range(3)))
    assert [item.value for item in values] == [0, 1, 2]
    assert maximum == 1


@pytest.mark.asyncio
async def test_cancellation_propagates() -> None:
    started = asyncio.Event()
    cleaned = asyncio.Event()

    @tool(timeout=5)
    async def cancellable() -> str:
        """Wait until cancelled."""
        started.set()
        try:
            await asyncio.sleep(5)
        finally:
            cleaned.set()
        return "late"

    task = asyncio.create_task(Runtime().arun(cancellable, {}))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_hooks_and_middleware() -> None:
    events: list[str] = []

    async def hook(event: RuntimeEvent) -> None:
        events.append(event.name)

    class MetadataMiddleware:
        async def __call__(self, context, call_next):
            context.metadata["middleware"] = True
            return await call_next(context)

    @tool
    async def okay() -> str:
        """Return okay."""
        return "okay"

    runtime = Runtime(hooks=(hook,), middleware=(MetadataMiddleware(),))
    assert (await runtime.arun(okay, {})).value == "okay"
    assert "tool.call.started" in events
    assert "tool.call.completed" in events


@pytest.mark.asyncio
async def test_streaming() -> None:
    @tool
    async def numbers(count: int) -> AsyncIterator[int]:
        """Yield a sequence."""
        for value in range(count):
            yield value

    values = [value async for value in Runtime().astream(numbers, {"count": 3})]
    assert values == [0, 1, 2]


@pytest.mark.asyncio
async def test_sync_wrapper_rejects_nested_loop() -> None:
    @tool
    def one() -> int:
        """Return one."""
        return 1

    with pytest.raises(RuntimeError, match="active event loop"):
        Runtime().run(one, {})
