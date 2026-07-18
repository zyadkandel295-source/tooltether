"""OpenAI-compatible function tool schema and call mapping."""

from __future__ import annotations

import json
from typing import Any

from ..errors import AdapterError
from ..schema import openai_strict_schema
from .base import BaseAdapter


class OpenAIAdapter(BaseAdapter):
    adapter_name = "openai"
    framework_name = "OpenAI API"
    supported_framework_versions = "schema contract; SDK >=2.8 optional"

    def export_tool(self, tool: Any, runtime: Any | None = None) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.spec.description,
                "parameters": openai_strict_schema(tool.spec.input_schema),
                "strict": True,
            },
        }

    def export_responses_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.spec.description,
            "parameters": openai_strict_schema(tool.spec.input_schema),
            "strict": True,
        }

    async def execute_tool_call(self, runtime: Any, tool: Any, call: Any) -> dict[str, Any]:
        call_id = _get(call, "id") or _get(call, "call_id")
        function = _get(call, "function") or call
        name = _get(function, "name")
        if name != tool.name:
            raise AdapterError(f"Tool call requested '{name}', expected '{tool.name}'")
        raw_arguments = _get(function, "arguments") or "{}"
        try:
            arguments = (
                json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            )
        except json.JSONDecodeError as exc:
            raise AdapterError("OpenAI tool-call arguments are not valid JSON") from exc
        result = await runtime.arun(tool, arguments, correlation_id=call_id)
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(self.normalize_result(result), default=str, separators=(",", ":")),
        }


def _get(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
