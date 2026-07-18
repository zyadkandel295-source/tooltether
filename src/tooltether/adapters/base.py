"""Adapter contract and shared result normalization."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, cast

from pydantic import BaseModel

from ..models import SerializableModel, ToolResult


class AdapterCapabilities(SerializableModel):
    import_tools: bool = False
    export_tools: bool = True
    sync_execution: bool = True
    async_execution: bool = True
    streaming: bool = False
    strict_schema: bool = True


class BaseAdapter(ABC):
    adapter_name = "base"
    adapter_version = "1"
    framework_name = "framework-neutral"
    supported_framework_versions = "n/a"
    stability = "stable"

    @abstractmethod
    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any:
        raise NotImplementedError

    def import_tool(self, value: Any) -> Any:
        raise NotImplementedError(f"{self.adapter_name} tool import is not supported")

    async def execute_call(self, runtime: Any, tool: Any, arguments: dict[str, Any]) -> ToolResult:
        return cast(ToolResult, await runtime.arun(tool, arguments))

    def normalize_result(self, result: ToolResult) -> Any:
        value = result.value
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        return value

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities()

    def compatibility_check(self) -> tuple[bool, str]:
        return True, self.supported_framework_versions
