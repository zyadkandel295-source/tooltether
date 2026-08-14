"""Adapter contract and shared result normalization."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
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


class AdapterMaturity(StrEnum):
    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"


class AdapterInfo(SerializableModel):
    name: str
    framework: str
    supported_versions: str
    maturity: AdapterMaturity
    recommended: bool
    capabilities: AdapterCapabilities
    limitations: tuple[str, ...] = ()


class BaseAdapter(ABC):
    adapter_name = "base"
    adapter_version = "1"
    framework_name = "framework-neutral"
    supported_framework_versions = "n/a"
    maturity = AdapterMaturity.STABLE
    limitations: tuple[str, ...] = ()
    recommended = True

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

    def info(self) -> AdapterInfo:
        return AdapterInfo(
            name=self.adapter_name,
            framework=self.framework_name,
            supported_versions=self.supported_framework_versions,
            maturity=self.maturity,
            recommended=self.recommended,
            capabilities=self.capabilities(),
            limitations=self.limitations,
        )

    def compatibility_check(self) -> tuple[bool, str]:
        return True, self.supported_framework_versions
