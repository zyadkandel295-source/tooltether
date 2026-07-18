"""Anthropic client-tool schema and tool-use/result mapping."""

from __future__ import annotations

from typing import Any

from ..errors import AdapterError, ToolTetherError
from .base import BaseAdapter


class AnthropicAdapter(BaseAdapter):
    adapter_name = "anthropic"
    framework_name = "Anthropic Messages API"
    supported_framework_versions = "schema contract; SDK >=0.75 optional"

    def export_tool(self, tool: Any, runtime: Any | None = None) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.spec.description,
            "input_schema": tool.spec.input_schema,
        }

    async def execute_tool_use(self, runtime: Any, tool: Any, block: Any) -> dict[str, Any]:
        block_id = _get(block, "id")
        name = _get(block, "name")
        if name != tool.name:
            raise AdapterError(f"Tool use requested '{name}', expected '{tool.name}'")
        arguments = _get(block, "input") or {}
        try:
            result = await runtime.arun(tool, arguments, correlation_id=block_id)
            return {
                "type": "tool_result",
                "tool_use_id": block_id,
                "content": str(self.normalize_result(result)),
            }
        except ToolTetherError as exc:
            return {
                "type": "tool_result",
                "tool_use_id": block_id,
                "content": exc.message,
                "is_error": True,
            }


def _get(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
