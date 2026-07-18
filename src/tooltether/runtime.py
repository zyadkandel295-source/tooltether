"""Async-first controlled tool execution runtime."""

from __future__ import annotations

import asyncio
import contextvars
import random
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from .cache import MemoryCache
from .errors import (
    StorageError,
    ToolApprovalError,
    ToolExecutionError,
    ToolPermissionError,
    ToolRateLimitError,
    ToolRetryExhaustedError,
    ToolTetherError,
    ToolTimeoutError,
    ToolValidationError,
    UnsafeOperationError,
)
from .models import (
    AuditRecord,
    ExecutionContext,
    ExecutionEnvironment,
    ExecutionIdentity,
    Outcome,
    PermissionDecision,
    PermissionDecisionType,
    PermissionRequest,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeHook,
    RuntimeMiddleware,
    TelemetryRecord,
    ToolResult,
)
from .observability import EventBus, LocalMetrics
from .optimizer import Optimizer
from .policy import ApprovalHandler, NonInteractiveApprovalHandler, Policy
from .schema import validate_input, validate_output
from .security import payload_hash, redact
from .storage import SQLiteStorage
from .tool import BaseTool, Tool, ensure_tool

current_execution: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar(
    "tooltether_current_execution", default=None
)


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float
    lock: asyncio.Lock


class _TokenBuckets:
    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def consume(self, key: str, calls: int, period: float, burst: int | None) -> bool:
        capacity = float(burst or calls)
        rate = calls / period
        async with self._lock:
            bucket = self._buckets.setdefault(
                key, _Bucket(tokens=capacity, updated_at=time.monotonic(), lock=asyncio.Lock())
            )
        async with bucket.lock:
            now = time.monotonic()
            bucket.tokens = min(capacity, bucket.tokens + (now - bucket.updated_at) * rate)
            bucket.updated_at = now
            if bucket.tokens < 1:
                return False
            bucket.tokens -= 1
            return True


class RuntimeBoundTool:
    def __init__(self, runtime: Runtime, tool: Tool[..., Any]) -> None:
        self.runtime = runtime
        self.tool = tool
        self.__name__ = tool.name
        self.__doc__ = tool.spec.description

    def __call__(self, **arguments: Any) -> ToolResult:
        return self.runtime.run(self.tool, arguments)

    async def arun(self, **arguments: Any) -> ToolResult:
        return await self.runtime.arun(self.tool, arguments)


class Runtime:
    """Coordinates the same validation and safety lifecycle for every adapter."""

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        *,
        policy: Policy | None = None,
        approval_handler: ApprovalHandler | None = None,
        cache: MemoryCache | None = None,
        storage: SQLiteStorage | None = None,
        hooks: tuple[RuntimeHook, ...] = (),
        middleware: tuple[RuntimeMiddleware, ...] = (),
    ) -> None:
        self.config = config or RuntimeConfig()
        self.policy = policy or Policy()
        self.approval_handler = approval_handler or NonInteractiveApprovalHandler()
        self.cache = cache or MemoryCache()
        self.storage = storage or SQLiteStorage(self.config.storage_path)
        self.events = EventBus(hooks)
        self.metrics = LocalMetrics()
        self.middleware = list(middleware)
        self.optimizer = Optimizer(
            self.storage, self.config.optimization, self.config.environment.name
        )
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._semaphore_lock = asyncio.Lock()
        self._buckets = _TokenBuckets()
        self._idempotency_locks: dict[str, asyncio.Lock] = {}
        self._idempotency_guard = asyncio.Lock()

    def bind(self, candidate: Tool[..., Any] | BaseTool | Callable[..., Any]) -> RuntimeBoundTool:
        return RuntimeBoundTool(self, ensure_tool(candidate))

    def add_middleware(self, middleware: RuntimeMiddleware) -> None:
        self.middleware.append(middleware)

    def add_hook(self, hook: RuntimeHook) -> None:
        self.events.subscribe(hook)

    def run(
        self,
        candidate: Tool[..., Any] | BaseTool | Callable[..., Any],
        arguments: Mapping[str, Any],
        **options: Any,
    ) -> ToolResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(candidate, arguments, **options))
        raise RuntimeError("Runtime.run() cannot be used inside an active event loop; await arun()")

    async def arun(
        self,
        candidate: Tool[..., Any] | BaseTool | Callable[..., Any],
        arguments: Mapping[str, Any],
        *,
        identity: ExecutionIdentity | None = None,
        environment: ExecutionEnvironment | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ToolResult:
        tool = ensure_tool(candidate)
        execution_id = str(uuid.uuid4())
        effective_timeout = min(
            tool.spec.timeout.seconds,
            tool.spec.timeout.hard_max_seconds,
            self.config.hard_max_timeout,
        )
        context = ExecutionContext(
            execution_id=execution_id,
            correlation_id=correlation_id or execution_id,
            tool_name=tool.name,
            tool_version=tool.version,
            tool_fingerprint=tool.fingerprint.value,
            identity=identity or ExecutionIdentity(),
            environment=environment or self.config.environment,
            deadline=datetime.now(UTC) + timedelta(seconds=effective_timeout),
            metadata=dict(metadata or {}),
        )
        token = current_execution.set(context)
        started = time.perf_counter()
        decision = PermissionDecision(
            decision=PermissionDecisionType.DENY, reason_code="not_evaluated"
        )
        result: ToolResult | None = None
        failure: BaseException | None = None
        await self._emit("tool.call.started", context, {"tool_fingerprint": tool.fingerprint.value})
        try:
            try:
                normalized = validate_input(
                    tool.input_model,
                    dict(arguments),
                    tool_name=tool.name,
                    tool_version=tool.version,
                )
            except ToolValidationError as exc:
                exc.execution_id = execution_id
                await self._emit("tool.validation.failed", context, {"error_code": exc.code})
                raise
            await self._emit("tool.validation.succeeded", context)
            decision = self.policy.evaluate(
                tool,
                context,
                resource=_argument(normalized, "path", "file_path", "resource"),
                hostname=_argument(normalized, "url", "hostname", "host"),
                method=_argument(normalized, "method", "http_method"),
            )
            await self._emit(
                f"tool.permission.{decision.decision}",
                context,
                {"reason_code": decision.reason_code, "rule_ids": decision.matched_rule_ids},
            )
            if decision.decision == PermissionDecisionType.DENY:
                raise ToolPermissionError(
                    f"Policy denied '{tool.name}': {decision.explain()}",
                    tool_name=tool.name,
                    tool_version=tool.version,
                    execution_id=execution_id,
                    safe_details={"reason_code": decision.reason_code},
                )
            if decision.decision == PermissionDecisionType.REQUIRE_APPROVAL:
                await self._emit("tool.approval.requested", context)
                approval = await self.approval_handler(
                    PermissionRequest(context=context, reason=decision.reason_code)
                )
                if approval.decision not in {
                    PermissionDecisionType.ALLOW,
                    PermissionDecisionType.ALLOW_ONCE,
                    PermissionDecisionType.ALLOW_WITH_CONSTRAINTS,
                }:
                    raise ToolApprovalError(
                        f"Approval denied for '{tool.name}'",
                        tool_name=tool.name,
                        tool_version=tool.version,
                        execution_id=execution_id,
                        safe_details={"reason_code": approval.reason_code},
                    )
                await self._emit("tool.approval.allowed", context)
            await self._check_rate_limit(tool, context)
            lock: asyncio.Lock | None = None
            if idempotency_key is not None:
                if not tool.spec.idempotent:
                    raise UnsafeOperationError(
                        f"Tool '{tool.name}' does not declare idempotency support",
                        tool_name=tool.name,
                        tool_version=tool.version,
                        execution_id=execution_id,
                    )
                lock_key = payload_hash(
                    [tool.fingerprint.value, context.identity.cache_scope, idempotency_key]
                )
                async with self._idempotency_guard:
                    lock = self._idempotency_locks.setdefault(lock_key, asyncio.Lock())
                await lock.acquire()
            try:
                if idempotency_key is not None:
                    replay = await self.storage.get_idempotent(
                        tool.fingerprint.value, context.identity.cache_scope, idempotency_key
                    )
                    if replay is not None:
                        result = ToolResult.model_validate(replay).model_copy(
                            update={
                                "execution_id": execution_id,
                                "duration_seconds": time.perf_counter() - started,
                                "idempotency_replay": True,
                                "attempts": 0,
                            }
                        )
                        await self._emit("tool.idempotency.replayed", context)
                        return result
                result = await self._run_with_cache(tool, normalized, context, started)
                if idempotency_key is not None:
                    await self.storage.save_idempotent(
                        tool.fingerprint.value,
                        context.identity.cache_scope,
                        idempotency_key,
                        result.model_dump(mode="json"),
                    )
                return result
            finally:
                if lock is not None:
                    lock.release()
        except asyncio.CancelledError:
            failure = asyncio.CancelledError()
            await self._emit("tool.execution.cancelled", context)
            raise
        except ToolTetherError as exc:
            failure = exc
            if exc.execution_id is None:
                exc.execution_id = execution_id
            await self._emit("tool.execution.failed", context, {"error_code": exc.code})
            raise
        except Exception as exc:
            failure = exc
            wrapped = ToolExecutionError(
                f"Tool '{tool.name}' failed",
                tool_name=tool.name,
                tool_version=tool.version,
                execution_id=execution_id,
                safe_details={"exception_type": type(exc).__name__},
            )
            await self._emit("tool.execution.failed", context, {"error_code": wrapped.code})
            raise wrapped from exc
        finally:
            duration = time.perf_counter() - started
            outcome = result.outcome if result else _failure_outcome(failure)
            attempts = result.attempts if result else int(context.metadata.get("attempts", 0))
            cache_hit = bool(result and result.cache_hit)
            self.metrics.record(tool.name, str(outcome), duration, attempts, cache_hit)
            telemetry = TelemetryRecord(
                execution_id=execution_id,
                tool_fingerprint=tool.fingerprint.value,
                environment=context.environment.name,
                latency_seconds=duration,
                outcome=outcome,
                attempts=attempts,
                cache_hit=cache_hit,
                error_code=failure.code if isinstance(failure, ToolTetherError) else None,
            )
            audit = AuditRecord(
                execution_id=execution_id,
                correlation_id=context.correlation_id,
                tool_name=tool.name,
                tool_version=tool.version,
                tool_fingerprint=tool.fingerprint.value,
                principal=context.identity.principal,
                decision=str(decision.decision),
                policy_rule_ids=decision.matched_rule_ids,
                started_at=context.started_at,
                duration_seconds=duration,
                outcome=outcome,
                attempts=attempts,
                cache_hit=cache_hit,
            )
            try:
                await self.storage.add_telemetry(telemetry)
                await self.storage.append_audit(audit, hash_chain=self.config.audit_hash_chain)
            except StorageError:
                if self.config.strict_audit:
                    raise
            await self._emit("tool.call.completed", context, {"outcome": str(outcome)})
            current_execution.reset(token)

    async def _run_with_cache(
        self,
        tool: Tool[..., Any],
        arguments: dict[str, Any],
        context: ExecutionContext,
        started: float,
    ) -> ToolResult:
        policy = tool.spec.cache
        excluded = {
            key: value for key, value in arguments.items() if key not in policy.excluded_fields
        }
        cache_key = payload_hash(
            [policy.namespace, tool.fingerprint.value, context.identity.cache_scope, excluded]
        )
        if policy.enabled:
            cached = await self.cache.get(cache_key)
            if cached is not None:
                await self._emit("tool.cache.hit", context)
                return ToolResult(
                    value=cached,
                    execution_id=context.execution_id,
                    tool_name=tool.name,
                    tool_version=tool.version,
                    duration_seconds=time.perf_counter() - started,
                    attempts=0,
                    cache_hit=True,
                )
            await self._emit("tool.cache.miss", context)
        value, attempts = await self._execute_limited(tool, arguments, context)
        result = ToolResult(
            value=value,
            execution_id=context.execution_id,
            tool_name=tool.name,
            tool_version=tool.version,
            duration_seconds=time.perf_counter() - started,
            attempts=attempts,
        )
        if policy.enabled:
            safe_value = redact(value, tool.spec.metadata.secret_fields)
            if safe_value != value and not policy.sensitive:
                await self._emit("tool.cache.skipped_sensitive", context)
            else:
                await self.cache.set(
                    cache_key,
                    value,
                    policy.ttl_seconds,
                    tags=tool.spec.metadata.tags,
                    tool_fingerprint=tool.fingerprint.value,
                )
        return result

    async def _execute_limited(
        self, tool: Tool[..., Any], arguments: dict[str, Any], context: ExecutionContext
    ) -> tuple[Any, int]:
        async with self._semaphore_lock:
            semaphore = self._semaphores.setdefault(
                tool.fingerprint.value,
                asyncio.Semaphore(tool.spec.concurrency.max_concurrent),
            )
        wait_started = time.perf_counter()
        try:
            await asyncio.wait_for(
                semaphore.acquire(), timeout=tool.spec.concurrency.queue_timeout_seconds
            )
        except TimeoutError as exc:
            raise ToolRateLimitError(
                f"Concurrency queue timed out for '{tool.name}'",
                tool_name=tool.name,
                tool_version=tool.version,
                execution_id=context.execution_id,
                safe_details={"limit": tool.spec.concurrency.max_concurrent},
            ) from exc
        context.metadata["concurrency_wait_seconds"] = time.perf_counter() - wait_started
        try:
            return await self._apply_middleware(tool, arguments, context)
        finally:
            semaphore.release()

    async def _apply_middleware(
        self, tool: Tool[..., Any], arguments: dict[str, Any], context: ExecutionContext
    ) -> tuple[Any, int]:
        async def terminal(_: ExecutionContext) -> ToolResult:
            value, attempts = await self._execute_retries(tool, arguments, context)
            return ToolResult(
                value=value,
                execution_id=context.execution_id,
                tool_name=tool.name,
                tool_version=tool.version,
                duration_seconds=0,
                attempts=attempts,
            )

        next_call: Callable[[ExecutionContext], Awaitable[ToolResult]] = terminal
        for middleware in reversed(self.middleware):
            downstream = next_call

            async def invoke(
                ctx: ExecutionContext,
                *,
                layer: RuntimeMiddleware = middleware,
                call_next: Callable[[ExecutionContext], Any] = downstream,
            ) -> ToolResult:
                return await layer(ctx, call_next)

            next_call = invoke
        result = await next_call(context)
        return result.value, result.attempts

    async def _execute_retries(
        self, tool: Tool[..., Any], arguments: dict[str, Any], context: ExecutionContext
    ) -> tuple[Any, int]:
        policy = tool.spec.retry
        safe_retry = tool.spec.idempotent or tool.spec.risk.side_effects == "none"
        attempts_allowed = policy.max_attempts if safe_retry else 1
        retry_started = time.monotonic()
        last_error: BaseException | None = None
        for attempt in range(1, attempts_allowed + 1):
            context.metadata["attempts"] = attempt
            try:
                await self._emit("tool.execution.started", context, {"attempt": attempt})
                value = await self._invoke(tool, arguments, context)
                value = validate_output(
                    tool.output_adapter,
                    value,
                    tool_name=tool.name,
                    tool_version=tool.version,
                )
                await self._emit("tool.execution.succeeded", context, {"attempt": attempt})
                return value, attempt
            except asyncio.CancelledError:
                raise
            except ToolTimeoutError as exc:
                last_error = exc
            except policy.retry_on as exc:
                last_error = exc
            except ToolTetherError:
                raise
            except Exception as exc:
                raise ToolExecutionError(
                    f"Tool '{tool.name}' raised {type(exc).__name__}",
                    tool_name=tool.name,
                    tool_version=tool.version,
                    execution_id=context.execution_id,
                    safe_details={"exception_type": type(exc).__name__},
                ) from exc
            if attempt >= attempts_allowed:
                break
            delay = policy.base_delay * (
                2 ** (attempt - 1) if policy.backoff == "exponential" else 1
            )
            delay = min(delay, policy.max_delay)
            if policy.jitter:
                # Retry jitter is timing noise, never a security or identity value.
                delay = random.uniform(0, delay)  # nosec B311  # noqa: S311
            if (
                policy.retry_budget_seconds is not None
                and time.monotonic() - retry_started + delay > policy.retry_budget_seconds
            ):
                break
            await self._emit(
                "tool.retry.started", context, {"attempt": attempt + 1, "delay": delay}
            )
            await asyncio.sleep(delay)
        if attempts_allowed == 1 and isinstance(last_error, ToolTimeoutError):
            raise last_error
        raise ToolRetryExhaustedError(
            f"Tool '{tool.name}' exhausted {int(context.metadata.get('attempts', 0))} attempts",
            tool_name=tool.name,
            tool_version=tool.version,
            execution_id=context.execution_id,
            retryable=False,
            safe_details={"last_error_type": type(last_error).__name__},
        ) from last_error

    async def _invoke(
        self, tool: Tool[..., Any], arguments: dict[str, Any], context: ExecutionContext
    ) -> Any:
        if context.deadline is None:
            remaining = tool.spec.timeout.seconds
        else:
            remaining = (context.deadline - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            raise ToolTimeoutError(
                f"Tool '{tool.name}' exceeded its total timeout",
                tool_name=tool.name,
                tool_version=tool.version,
                execution_id=context.execution_id,
            )
        try:
            async with asyncio.timeout(remaining):
                if tool.is_async_generator:
                    return [item async for item in tool.function(**arguments)]
                if tool.is_async:
                    return await tool.function(**arguments)
                return await asyncio.to_thread(partial(tool.function, **arguments))
        except TimeoutError as exc:
            unknown_state = tool.spec.risk.side_effects != "none"
            await self._emit(
                "tool.execution.timed_out", context, {"unknown_completion_state": unknown_state}
            )
            raise ToolTimeoutError(
                f"Tool '{tool.name}' timed out after {remaining:.3f}s",
                tool_name=tool.name,
                tool_version=tool.version,
                execution_id=context.execution_id,
                safe_details={"unknown_completion_state": unknown_state},
            ) from exc

    async def astream(
        self,
        candidate: Tool[..., Any],
        arguments: Mapping[str, Any],
        *,
        identity: ExecutionIdentity | None = None,
    ) -> AsyncIterator[Any]:
        tool = ensure_tool(candidate)
        if not tool.is_async_generator:
            yield (await self.arun(tool, arguments, identity=identity)).value
            return
        normalized = validate_input(
            tool.input_model, dict(arguments), tool_name=tool.name, tool_version=tool.version
        )
        context = ExecutionContext(
            execution_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            tool_name=tool.name,
            tool_version=tool.version,
            tool_fingerprint=tool.fingerprint.value,
            identity=identity or ExecutionIdentity(),
            environment=self.config.environment,
        )
        decision = self.policy.evaluate(tool, context)
        if decision.decision == PermissionDecisionType.DENY:
            raise ToolPermissionError(f"Policy denied '{tool.name}': {decision.explain()}")
        try:
            async with asyncio.timeout(tool.spec.timeout.seconds):
                async for item in tool.function(**normalized):
                    yield validate_output(
                        tool.output_adapter,
                        item,
                        tool_name=tool.name,
                        tool_version=tool.version,
                    )
        except TimeoutError as exc:
            raise ToolTimeoutError(f"Streaming tool '{tool.name}' timed out") from exc

    async def _check_rate_limit(self, tool: Tool[..., Any], context: ExecutionContext) -> None:
        policy = tool.spec.rate_limit
        if policy is None:
            return
        key = f"{tool.fingerprint.value}:{context.identity.cache_scope}"
        if not await self._buckets.consume(key, policy.calls, policy.period_seconds, policy.burst):
            await self._emit("tool.rate_limit.rejected", context)
            raise ToolRateLimitError(
                f"Rate limit exceeded for '{tool.name}'",
                tool_name=tool.name,
                tool_version=tool.version,
                execution_id=context.execution_id,
                safe_details={"calls": policy.calls, "period_seconds": policy.period_seconds},
            )

    async def _emit(
        self, name: str, context: ExecutionContext, attributes: Mapping[str, Any] | None = None
    ) -> None:
        await self.events.emit(
            RuntimeEvent(
                name=name,
                execution_id=context.execution_id,
                attributes=redact(dict(attributes or {})),
            )
        )

    async def close(self) -> None:
        await self.storage.close()

    async def __aenter__(self) -> Runtime:
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()


def _argument(arguments: Mapping[str, Any], *names: str) -> str | None:
    for name in names:
        value = arguments.get(name)
        if isinstance(value, str):
            return value
    return None


def _failure_outcome(failure: BaseException | None) -> Outcome:
    if failure is None:
        return Outcome.FAILED
    if isinstance(failure, ToolTimeoutError):
        return Outcome.TIMED_OUT
    if isinstance(failure, ToolPermissionError):
        return Outcome.DENIED
    if isinstance(failure, asyncio.CancelledError):
        return Outcome.CANCELLED
    return Outcome.FAILED
