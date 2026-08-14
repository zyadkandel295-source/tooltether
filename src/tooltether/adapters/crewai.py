"""Experimental CrewAI BaseTool adapter."""

from __future__ import annotations

from typing import Any

from ..errors import MissingExtraError
from .base import AdapterMaturity, BaseAdapter


class CrewAIAdapter(BaseAdapter):
    adapter_name = "crewai"
    framework_name = "CrewAI"
    supported_framework_versions = "crewai >=1.7,<2"
    maturity = AdapterMaturity.EXPERIMENTAL
    recommended = False
    limitations = ("Upstream custom-tool lifecycle APIs may change.",)

    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any:
        if runtime is None:
            raise ValueError("CrewAI export requires runtime=")
        try:
            from crewai.tools import BaseTool as CrewBaseTool  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MissingExtraError("crewai", "CrewAI") from exc

        bound_runtime = runtime

        class RuntimeCrewTool(CrewBaseTool):  # type: ignore[misc]
            name: str = tool.name
            description: str = tool.spec.description
            args_schema: type = tool.input_model

            def _run(self, **arguments: Any) -> Any:
                return bound_runtime.run(tool, arguments).value

            async def _arun(self, **arguments: Any) -> Any:
                return (await bound_runtime.arun(tool, arguments)).value

        return RuntimeCrewTool()
