"""Built-in adapters. Provider and framework imports remain lazy."""

from __future__ import annotations

from ..registry import AdapterRegistry
from .anthropic import AnthropicAdapter
from .autogen import AutoGenAdapter
from .base import AdapterCapabilities, AdapterInfo, AdapterMaturity, BaseAdapter
from .crewai import CrewAIAdapter
from .langchain import LangChainAdapter
from .mcp import MCPAdapter
from .openai import OpenAIAdapter
from .smolagents import SmolagentsAdapter

adapter_registry: AdapterRegistry[BaseAdapter] = AdapterRegistry()
for _name, _adapter in (
    ("openai", OpenAIAdapter()),
    ("anthropic", AnthropicAdapter()),
    ("mcp", MCPAdapter()),
    ("langchain", LangChainAdapter()),
    ("langgraph", LangChainAdapter(adapter_name="langgraph")),
    ("crewai", CrewAIAdapter()),
    ("autogen", AutoGenAdapter()),
    ("smolagents", SmolagentsAdapter()),
):
    adapter_registry.register(_name, _adapter)

__all__ = [
    "AdapterCapabilities",
    "AdapterInfo",
    "AdapterMaturity",
    "BaseAdapter",
    "adapter_registry",
]
