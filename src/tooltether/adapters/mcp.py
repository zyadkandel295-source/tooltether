"""MCP schema export and optional official-SDK server construction."""

from __future__ import annotations

import json
from typing import Any

from ..errors import MissingExtraError, ToolTetherError
from .base import AdapterCapabilities, BaseAdapter


class MCPAdapter(BaseAdapter):
    adapter_name = "mcp"
    framework_name = "Model Context Protocol"
    supported_framework_versions = "mcp >=1.25,<2"
    limitations = (
        "Transport authorization and process isolation are host-application responsibilities.",
    )

    def export_tool(self, tool: Any, runtime: Any | None = None) -> dict[str, Any]:
        risk = tool.spec.risk
        return {
            "name": tool.name,
            "title": tool.name.replace("_", " ").title(),
            "description": tool.spec.description,
            "inputSchema": tool.spec.input_schema,
            "outputSchema": tool.spec.output_schema,
            "annotations": {
                "readOnlyHint": risk.side_effects in {"none", "read"},
                "destructiveHint": risk.destructive,
                "idempotentHint": tool.spec.idempotent,
                "openWorldHint": tool.spec.capabilities.external_access,
            },
        }

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(streaming=True)

    def create_server(self, registry: Any, runtime: Any, name: str = "ToolTether") -> Any:
        try:
            from mcp.server.lowlevel import Server
            from mcp.types import CallToolResult, TextContent
            from mcp.types import Tool as MCPTool
        except ImportError as exc:
            raise MissingExtraError("mcp", "MCP") from exc
        server = Server(name)

        @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[Any]:
            return [MCPTool.model_validate(self.export_tool(tool)) for tool in registry.search()]

        @server.call_tool()  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
            tool = registry.get(name)
            try:
                result = await runtime.arun(tool, arguments)
                normalized = self.normalize_result(result)
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(normalized, default=str))],
                    structuredContent=normalized if isinstance(normalized, dict) else None,
                    isError=False,
                )
            except ToolTetherError as exc:
                return CallToolResult(
                    content=[TextContent(type="text", text=exc.message)], isError=True
                )

        return server
