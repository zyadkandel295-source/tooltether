"""Canonical domain models shared by the runtime and adapters."""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic.json_schema import SkipJsonSchema

from .constants import RUNTIME_CONFIG_VERSION, TOOL_CONTRACT_VERSION


class SerializableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class SideEffects(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    EXTERNAL = "external"
    FINANCIAL = "financial"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DataSensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PermissionDecisionType(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    ALLOW_ONCE = "allow_once"
    ALLOW_WITH_CONSTRAINTS = "allow_with_constraints"


class OptimizationMode(StrEnum):
    OFF = "off"
    RECOMMEND = "recommend"
    AUTO_SAFE = "auto_safe"


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    DENIED = "denied"


class ToolCapabilities(SerializableModel):
    capabilities: frozenset[str] = frozenset()
    resources: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    external_access: bool = False
    filesystem_access: bool = False
    database_access: bool = False
    required_secrets: frozenset[str] = frozenset()
    streaming: bool = False
    cancellation: bool = True
    concurrency_safe: bool = True


class ToolRisk(SerializableModel):
    level: RiskLevel = RiskLevel.LOW
    side_effects: SideEffects = SideEffects.NONE
    destructive: bool = False
    approval_required: bool = False
    data_sensitivity: DataSensitivity = DataSensitivity.INTERNAL
    irreversible: bool = False


class RetryPolicy(SerializableModel):
    max_attempts: int = Field(default=1, ge=1, le=20)
    backoff: Literal["fixed", "exponential"] = "exponential"
    base_delay: float = Field(default=0.25, ge=0, le=60)
    max_delay: float = Field(default=5.0, ge=0, le=300)
    jitter: bool = True
    retry_budget_seconds: float | None = Field(default=None, gt=0)
    retry_on: SkipJsonSchema[tuple[type[BaseException], ...]] = Field(
        default=(TimeoutError, ConnectionError), exclude=True
    )


class TimeoutPolicy(SerializableModel):
    seconds: float = Field(default=30.0, gt=0)
    hard_max_seconds: float = Field(default=300.0, gt=0)
    connect_seconds: float | None = Field(default=None, gt=0)

    @field_validator("hard_max_seconds")
    @classmethod
    def hard_max_is_positive(cls, value: float) -> float:
        return value


class CachePolicy(SerializableModel):
    enabled: bool = False
    ttl_seconds: float = Field(default=300.0, gt=0)
    namespace: str = "default"
    max_entries: int = Field(default=1024, ge=1)
    sensitive: bool = False
    excluded_fields: frozenset[str] = frozenset()


class RateLimitPolicy(SerializableModel):
    calls: int = Field(default=100, ge=1)
    period_seconds: float = Field(default=60.0, gt=0)
    burst: int | None = Field(default=None, ge=1)


class ConcurrencyPolicy(SerializableModel):
    max_concurrent: int = Field(default=16, ge=1)
    queue_timeout_seconds: float = Field(default=30.0, gt=0)


class OptimizationPolicy(SerializableModel):
    mode: OptimizationMode = OptimizationMode.RECOMMEND
    min_samples: int = Field(default=20, ge=5)
    timeout_percentile: float = Field(default=0.95, gt=0.5, lt=1)
    timeout_margin: float = Field(default=1.25, ge=1)
    min_timeout: float = Field(default=0.05, gt=0)
    max_timeout: float = Field(default=300, gt=0)


class ToolMetadata(SerializableModel):
    tags: frozenset[str] = frozenset()
    aliases: frozenset[str] = frozenset()
    expected_latency: Literal["instant", "short", "medium", "long"] = "short"
    expected_cost: Literal["none", "low", "medium", "high"] = "none"
    secret_fields: frozenset[str] = frozenset()
    deprecated: bool = False


class ToolSpec(SerializableModel):
    contract_version: str = TOOL_CONTRACT_VERSION
    name: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    version: str = "1.0.0"
    description: str = Field(min_length=1, max_length=2048)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: ToolCapabilities = Field(default_factory=ToolCapabilities)
    risk: ToolRisk = Field(default_factory=ToolRisk)
    metadata: ToolMetadata = Field(default_factory=ToolMetadata)
    timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    cache: CachePolicy = Field(default_factory=CachePolicy)
    rate_limit: RateLimitPolicy | None = None
    concurrency: ConcurrencyPolicy = Field(default_factory=ConcurrencyPolicy)
    idempotent: bool = False


class ToolInput(SerializableModel):
    arguments: dict[str, Any]


class ToolOutput(SerializableModel):
    value: Any


class ToolCall(SerializableModel):
    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None = None
    idempotency_key: str | None = None


class ToolError(SerializableModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionIdentity(SerializableModel):
    principal: str = "anonymous"
    user_id: str | None = None
    agent_id: str | None = None
    workspace: str | None = None
    roles: frozenset[str] = frozenset()

    @property
    def cache_scope(self) -> str:
        return "|".join(filter(None, (self.principal, self.user_id, self.agent_id, self.workspace)))


class ExecutionEnvironment(SerializableModel):
    name: str = "development"
    region: str | None = None
    tags: frozenset[str] = frozenset()


class ExecutionContext(SerializableModel):
    execution_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    tool_fingerprint: str
    identity: ExecutionIdentity = Field(default_factory=ExecutionIdentity)
    environment: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    deadline: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(SerializableModel):
    value: Any = None
    execution_id: str
    tool_name: str
    tool_version: str
    outcome: Outcome = Outcome.SUCCEEDED
    duration_seconds: float = Field(ge=0)
    attempts: int = Field(default=1, ge=0)
    cache_hit: bool = False
    idempotency_replay: bool = False
    error: ToolError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeEvent(SerializableModel):
    name: str
    execution_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class RuntimeHook(Protocol):
    async def __call__(self, event: RuntimeEvent) -> None: ...


NextMiddleware = Callable[[ExecutionContext], Awaitable[ToolResult]]


@runtime_checkable
class RuntimeMiddleware(Protocol):
    async def __call__(
        self, context: ExecutionContext, call_next: NextMiddleware
    ) -> ToolResult: ...


class PermissionRequest(SerializableModel):
    context: ExecutionContext
    capability: str | None = None
    reason: str


class PermissionDecision(SerializableModel):
    decision: PermissionDecisionType
    reason_code: str
    matched_rule_ids: tuple[str, ...] = ()
    constraints: dict[str, Any] = Field(default_factory=dict)

    def explain(self) -> str:
        rules = ", ".join(self.matched_rule_ids) or "no explicit rule"
        return f"{self.decision}: {self.reason_code}; matched {rules}"


class PolicyRule(SerializableModel):
    rule_id: str
    decision: PermissionDecisionType
    tool: str | None = None
    version: str | None = None
    capability: str | None = None
    principal: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    workspace: str | None = None
    environment: str | None = None
    resources: tuple[str, ...] = ()
    hostnames: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    side_effects: SideEffects | None = None
    risk_levels: frozenset[RiskLevel] = frozenset()
    tags: frozenset[str] = frozenset()
    constraints: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0


class TelemetryRecord(SerializableModel):
    execution_id: str
    tool_fingerprint: str
    environment: str
    latency_seconds: float = Field(ge=0)
    outcome: Outcome
    attempts: int = Field(ge=0)
    cache_hit: bool = False
    error_code: str | None = None
    cost: float | None = Field(default=None, ge=0)
    model: str | None = None
    quality: float | None = Field(default=None, ge=0, le=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditRecord(SerializableModel):
    sequence: int | None = None
    execution_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    tool_fingerprint: str
    principal: str
    decision: str
    policy_rule_ids: tuple[str, ...] = ()
    started_at: datetime
    duration_seconds: float = Field(ge=0)
    outcome: Outcome
    attempts: int = Field(ge=0)
    cache_hit: bool
    redacted: bool = True
    config_version: str = RUNTIME_CONFIG_VERSION
    profile_version: str | None = None
    previous_hash: str | None = None
    record_hash: str | None = None


class ToolFingerprint(SerializableModel):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_version: str = TOOL_CONTRACT_VERSION


class OptimizationRecommendation(SerializableModel):
    recommendation_id: str
    tool_fingerprint: str
    setting: Literal["timeout", "retry", "cache", "concurrency", "rate_limit", "model"]
    current_value: Any
    recommended_value: Any
    reason: str
    sample_size: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    estimated_effect: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = RiskLevel.LOW
    profile_version: str = "1"
    rollback_value: Any = None


class OptimizationProfile(SerializableModel):
    tool_fingerprint: str
    environment: str
    version: str = "1"
    settings: dict[str, Any] = Field(default_factory=dict)
    previous_settings: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelCandidate(SerializableModel):
    provider: str
    model: str
    estimated_cost: float = Field(ge=0)
    estimated_latency: float = Field(ge=0)
    quality: float = Field(ge=0, le=1)
    capabilities: frozenset[str] = frozenset()
    context_limit: int = Field(default=0, ge=0)
    privacy: frozenset[str] = frozenset()
    regions: frozenset[str] = frozenset()


class ModelSelection(SerializableModel):
    candidate: ModelCandidate
    score: float
    objective: str
    explanation: str


class FeedbackRecord(SerializableModel):
    execution_id: str
    quality: float | None = Field(default=None, ge=0, le=1)
    accepted: bool | None = None
    source: str = "application"
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Plugin(SerializableModel):
    name: str
    version: str
    entry_point: str
    kind: Literal["tool", "adapter"]


class Adapter(Protocol):
    adapter_name: str
    adapter_version: str
    framework_name: str
    supported_framework_versions: str

    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any: ...


class RuntimeConfig(SerializableModel):
    version: str = RUNTIME_CONFIG_VERSION
    environment: ExecutionEnvironment = Field(default_factory=ExecutionEnvironment)
    default_timeout: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    hard_max_timeout: float = Field(default=300.0, gt=0)
    strict_validation: bool = True
    deny_undeclared_dangerous: bool = True
    log_payloads: bool = False
    audit_hash_chain: bool = True
    strict_audit: bool = False
    storage_path: str = ":memory:"
    optimization: OptimizationPolicy = Field(default_factory=OptimizationPolicy)
    secret_value: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @classmethod
    def from_env(cls, prefix: str = "TOOLTETHER_") -> RuntimeConfig:
        values: dict[str, Any] = {}
        if environment := os.getenv(f"{prefix}ENVIRONMENT"):
            values["environment"] = {"name": environment}
        if timeout := os.getenv(f"{prefix}DEFAULT_TIMEOUT"):
            values["default_timeout"] = {"seconds": float(timeout)}
        if hard_max := os.getenv(f"{prefix}HARD_MAX_TIMEOUT"):
            values["hard_max_timeout"] = float(hard_max)
        if storage := os.getenv(f"{prefix}STORAGE_PATH"):
            values["storage_path"] = storage
        return cls.model_validate(values)

    @classmethod
    def from_file(cls, path: str | Path) -> RuntimeConfig:
        source = Path(path)
        if source.suffix.lower() == ".json":
            data = json.loads(source.read_text(encoding="utf-8"))
        elif source.suffix.lower() == ".toml":
            data = tomllib.loads(source.read_text(encoding="utf-8"))
        else:
            raise ValueError("RuntimeConfig supports only JSON and TOML files in core")
        if "runtime" in data and isinstance(data["runtime"], Mapping):
            data = dict(data["runtime"])
        return cls.model_validate(data)
