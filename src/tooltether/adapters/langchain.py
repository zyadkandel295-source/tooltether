"""LangChain StructuredTool adapter; also accepted by supported LangGraph tool nodes."""

from __future__ import annotations

from typing import Any

from ..errors import MissingExtraError
from .base import AdapterMaturity, BaseAdapter


class LangChainAdapter(BaseAdapter):
    framework_name = "LangChain / LangGraph"
    supported_framework_versions = "langchain-core >=1.1,<2"
    maturity = AdapterMaturity.BETA
    limitations = (
        "Requires runtime= so sync and async handlers preserve ToolTether validation and policy.",
        "LangGraph support is through LangChain StructuredTool compatibility.",
    )

    def __init__(self, adapter_name: str = "langchain") -> None:
        self.adapter_name = adapter_name

    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any:
        if runtime is None:
            raise ValueError("LangChain export requires runtime= to preserve the safety pipeline")
        try:
            from langchain_core.tools import StructuredTool
        except ImportError as exc:
            raise MissingExtraError("langchain", "LangChain") from exc

        def sync_handler(**arguments: Any) -> Any:
            return runtime.run(tool, arguments).value

        async def async_handler(**arguments: Any) -> Any:
            return (await runtime.arun(tool, arguments)).value

        return StructuredTool.from_function(
            func=sync_handler,
            coroutine=async_handler,
            name=tool.name,
            description=tool.spec.description,
            args_schema=tool.input_model,
            infer_schema=False,
        )
