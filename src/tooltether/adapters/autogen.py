"""Experimental Microsoft AutoGen FunctionTool adapter."""

from __future__ import annotations

from typing import Any

from ..errors import MissingExtraError
from .base import AdapterMaturity, BaseAdapter


class AutoGenAdapter(BaseAdapter):
    adapter_name = "autogen"
    framework_name = "Microsoft AutoGen"
    supported_framework_versions = "autogen-core >=0.7,<1"
    maturity = AdapterMaturity.EXPERIMENTAL
    recommended = False
    limitations = ("Cancellation and lifecycle behavior depend on the caller integration.",)

    def export_tool(self, tool: Any, runtime: Any | None = None) -> Any:
        if runtime is None:
            raise ValueError("AutoGen export requires runtime=")
        try:
            from autogen_core.tools import FunctionTool  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MissingExtraError("autogen", "AutoGen") from exc

        async def handler(**arguments: Any) -> Any:
            return (await runtime.arun(tool, arguments)).value

        handler.__name__ = tool.name
        handler.__doc__ = tool.spec.description
        handler.__signature__ = __import__("inspect").signature(tool.function)  # type: ignore[attr-defined]
        handler.__annotations__ = dict(getattr(tool.function, "__annotations__", {}))
        return FunctionTool(handler, description=tool.spec.description, name=tool.name)
