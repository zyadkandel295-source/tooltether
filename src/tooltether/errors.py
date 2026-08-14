"""Stable, secret-safe exception hierarchy."""

from __future__ import annotations

from typing import Any


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(token in str(key).lower() for token in ("secret", "token", "password", "key"))
            else _safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    return value


class ToolTetherError(Exception):
    """Root error with stable serialization fields."""

    code = "tooltether_error"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        tool_version: str | None = None,
        execution_id: str | None = None,
        safe_details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.tool_version = tool_version
        self.execution_id = execution_id
        self.safe_details = _safe(safe_details or {})
        self.retryable = self.retryable if retryable is None else retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "execution_id": self.execution_id,
            "retryable": self.retryable,
            "details": self.safe_details,
        }


class ToolDefinitionError(ToolTetherError):
    code = "tool_definition_error"


class ToolValidationError(ToolTetherError):
    code = "tool_validation_error"


class ToolPermissionError(ToolTetherError):
    code = "tool_permission_denied"


class ToolApprovalError(ToolPermissionError):
    code = "tool_approval_denied"


class ToolExecutionError(ToolTetherError):
    code = "tool_execution_error"


class ToolTimeoutError(ToolExecutionError):
    code = "tool_timeout"
    retryable = True


class ToolRateLimitError(ToolTetherError):
    code = "tool_rate_limited"
    retryable = True


class ToolRetryExhaustedError(ToolExecutionError):
    code = "tool_retry_exhausted"


class UnsafeOperationError(ToolTetherError):
    code = "unsafe_operation"


class ExecutionPolicyError(UnsafeOperationError):
    code = "execution_policy_violation"


class AdapterError(ToolTetherError):
    code = "adapter_error"


class MissingExtraError(AdapterError, ImportError):
    code = "missing_optional_extra"

    def __init__(self, extra: str, adapter: str) -> None:
        super().__init__(
            f"The {adapter} adapter requires the optional '{extra}' extra. "
            f'Install it with: pip install "tooltether[{extra}]"',
            safe_details={"extra": extra, "adapter": adapter},
        )


class StorageError(ToolTetherError):
    code = "storage_error"
