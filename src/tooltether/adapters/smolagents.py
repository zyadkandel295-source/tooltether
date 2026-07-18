"""Experimental Hugging Face smolagents Tool adapter."""

from __future__ import annotations

from typing import Any

from ..errors import MissingExtraError
from .base import AdapterCapabilities, BaseAdapter

_JSON_TO_SMOL = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


class SmolagentsAdapter(BaseAdapter):
    adapter_name = "smolagents"
    framework_name = "Hugging Face smolagents"
    supported_framework_versions = "smolagents >=1.24,<2"
    stability = "experimental"

    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any:
        if runtime is None:
            raise ValueError("smolagents export requires runtime=")
        try:
            from smolagents import Tool as SmolTool  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MissingExtraError("smolagents", "smolagents") from exc
        properties = tool.spec.input_schema.get("properties", {})
        tool_inputs = {
            key: {
                "type": _JSON_TO_SMOL.get(schema.get("type", "object"), "object"),
                "description": schema.get("description", key),
                "nullable": key not in tool.spec.input_schema.get("required", []),
            }
            for key, schema in properties.items()
        }
        tool_output_type = _JSON_TO_SMOL.get(
            tool.spec.output_schema.get("type", "object"), "object"
        )

        bound_runtime = runtime

        class RuntimeSmolTool(SmolTool):  # type: ignore[misc]
            name = tool.name
            description = tool.spec.description
            inputs = tool_inputs
            output_type = tool_output_type

            def forward(self, **arguments: Any) -> Any:
                return bound_runtime.run(tool, arguments).value

        return RuntimeSmolTool()

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(async_execution=False, streaming=False)
