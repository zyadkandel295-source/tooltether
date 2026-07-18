"""Canonical tool definition and decorator."""

from __future__ import annotations

import hashlib
import inspect
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Generic, ParamSpec, TypeVar, cast, overload

from pydantic import BaseModel, TypeAdapter

from .errors import ToolDefinitionError
from .models import (
    CachePolicy,
    ConcurrencyPolicy,
    RateLimitPolicy,
    RetryPolicy,
    RiskLevel,
    SideEffects,
    TimeoutPolicy,
    ToolCapabilities,
    ToolFingerprint,
    ToolMetadata,
    ToolRisk,
    ToolSpec,
)
from .schema import create_input_model, create_output_adapter, deterministic_schema

P = ParamSpec("P")
R = TypeVar("R")


def _callable_implementation(function: Callable[..., Any]) -> Callable[..., Any]:
    if inspect.isroutine(function) or inspect.isclass(function) or inspect.ismodule(function):
        return function
    return type(function).__call__ if callable(function) else function


class Tool(Generic[P, R]):
    """A callable plus its framework-neutral execution contract."""

    def __init__(
        self,
        function: Callable[P, R],
        spec: ToolSpec,
        input_model: type[BaseModel],
        output_adapter: TypeAdapter[Any],
    ) -> None:
        self.function = function
        self.spec = spec
        self.input_model = input_model
        self.output_adapter = output_adapter
        self.__name__ = spec.name
        self.__doc__ = spec.description

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def version(self) -> str:
        return self.spec.version

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(_callable_implementation(self.function))

    @property
    def is_async_generator(self) -> bool:
        return inspect.isasyncgenfunction(_callable_implementation(self.function))

    @property
    def fingerprint(self) -> ToolFingerprint:
        contract = self.spec.model_dump(mode="json", exclude_none=True)
        encoded = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        return ToolFingerprint(value=hashlib.sha256(encoded).hexdigest())

    def manifest(self) -> dict[str, Any]:
        data = self.spec.model_dump(mode="json", exclude_none=True)
        data["fingerprint"] = self.fingerprint.to_dict()
        return data

    def export(self, adapter: str, *, runtime: Any | None = None) -> Any:
        from .adapters import adapter_registry

        return adapter_registry.get(adapter).export_tool(self, runtime)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Direct calls remain possible; applications must enforce runtime-only access."""
        return self.function(*args, **kwargs)


class BaseTool(ABC):
    """Class-based definition for tools needing explicit lifecycle or owned resources."""

    name: str
    description: str
    version: str = "1.0.0"
    capabilities = ToolCapabilities()
    risk = ToolRisk()
    timeout = TimeoutPolicy()
    retry = RetryPolicy()
    cache = CachePolicy()
    idempotent = False

    @abstractmethod
    async def execute(self, **arguments: Any) -> Any:
        raise NotImplementedError

    def as_tool(self) -> Tool[..., Any]:
        async def invoke(**arguments: Any) -> Any:
            return await self.execute(**arguments)

        invoke.__name__ = self.name
        invoke.__doc__ = self.description
        signature = inspect.signature(self.execute)
        invoke.__signature__ = signature  # type: ignore[attr-defined]
        invoke.__annotations__ = dict(getattr(self.execute, "__annotations__", {}))
        return _build_tool(
            invoke,
            name=self.name,
            description=self.description,
            version=self.version,
            capabilities=self.capabilities,
            risk=self.risk,
            timeout=self.timeout,
            retries=self.retry,
            cache=self.cache,
            idempotent=self.idempotent,
        )


def _build_tool(
    function: Callable[..., Any],
    *,
    name: str | None = None,
    description: str | None = None,
    version: str = "1.0.0",
    timeout: float | TimeoutPolicy = 30.0,
    retries: int | RetryPolicy = 0,
    cache: bool | CachePolicy = False,
    cache_ttl: float = 300.0,
    permissions: list[str] | tuple[str, ...] | None = None,
    side_effects: SideEffects | str = SideEffects.NONE,
    idempotent: bool = False,
    approval_required: bool = False,
    destructive: bool = False,
    external_access: bool = False,
    secret_fields: list[str] | tuple[str, ...] | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    aliases: list[str] | tuple[str, ...] | None = None,
    capabilities: ToolCapabilities | None = None,
    risk: ToolRisk | None = None,
    rate_limit: RateLimitPolicy | None = None,
    concurrency: ConcurrencyPolicy | None = None,
) -> Tool[..., Any]:
    tool_name = str(name or getattr(function, "__name__", function.__class__.__name__))
    tool_description = description or inspect.getdoc(function)
    if not tool_description:
        raise ToolDefinitionError(f"Tool '{tool_name}' requires a description or docstring")
    input_model = create_input_model(function, tool_name)
    output_adapter = create_output_adapter(function, tool_name)
    implementation = _callable_implementation(function)
    side_effect_value = SideEffects(side_effects)
    capability_model = capabilities or ToolCapabilities(
        capabilities=frozenset(permissions or ()),
        external_access=external_access,
        streaming=inspect.isasyncgenfunction(implementation),
    )
    risk_model = risk or ToolRisk(
        level=RiskLevel.HIGH
        if destructive or side_effect_value.value in {"financial", "destructive"}
        else RiskLevel.LOW,
        side_effects=side_effect_value,
        destructive=destructive,
        approval_required=approval_required,
        irreversible=side_effect_value.value == "financial",
    )
    timeout_policy = (
        timeout if isinstance(timeout, TimeoutPolicy) else TimeoutPolicy(seconds=timeout)
    )
    retry_policy = (
        retries if isinstance(retries, RetryPolicy) else RetryPolicy(max_attempts=retries + 1)
    )
    cache_policy = (
        cache
        if isinstance(cache, CachePolicy)
        else CachePolicy(enabled=cache, ttl_seconds=cache_ttl)
    )
    if retry_policy.max_attempts > 1 and not idempotent and side_effect_value != SideEffects.NONE:
        retry_policy = retry_policy.model_copy(update={"max_attempts": 1})
    if cache_policy.enabled and side_effect_value != SideEffects.NONE:
        raise ToolDefinitionError(
            f"Tool '{tool_name}' has side effects and cannot enable caching "
            "without a custom safety layer"
        )
    spec = ToolSpec(
        name=tool_name,
        version=version,
        description=tool_description,
        input_schema=deterministic_schema(input_model),
        output_schema=deterministic_schema(output_adapter),
        capabilities=capability_model,
        risk=risk_model,
        metadata=ToolMetadata(
            tags=frozenset(tags or ()),
            aliases=frozenset(aliases or ()),
            secret_fields=frozenset(secret_fields or ()),
        ),
        timeout=timeout_policy,
        retry=retry_policy,
        cache=cache_policy,
        rate_limit=rate_limit,
        concurrency=concurrency or ConcurrencyPolicy(),
        idempotent=idempotent,
    )
    return Tool(function, spec, input_model, output_adapter)


@overload
def tool(function: Callable[P, R], /) -> Tool[P, R]: ...


@overload
def tool(
    function: None = None,
    /,
    **configuration: Any,
) -> Callable[[Callable[P, R]], Tool[P, R]]: ...


def tool(
    function: Callable[P, R] | None = None,
    /,
    **configuration: Any,
) -> Tool[P, R] | Callable[[Callable[P, R]], Tool[P, R]]:
    """Define a canonical tool with or without configuration arguments."""

    def decorate(target: Callable[P, R]) -> Tool[P, R]:
        return cast(Tool[P, R], _build_tool(target, **configuration))

    return decorate(function) if function is not None else decorate


def ensure_tool(candidate: Tool[..., Any] | BaseTool | Callable[..., Any]) -> Tool[..., Any]:
    if isinstance(candidate, Tool):
        return candidate
    if isinstance(candidate, BaseTool):
        return candidate.as_tool()
    if callable(candidate):
        return _build_tool(candidate)
    raise ToolDefinitionError(f"Object {candidate!r} is not a supported tool definition")
