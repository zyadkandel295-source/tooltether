"""Explicit tool and adapter registries with opt-in plugin loading."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Generic, TypeVar

from .errors import ToolDefinitionError
from .tool import BaseTool, Tool, ensure_tool

T = TypeVar("T")


class AdapterRegistry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, name: str, adapter: T) -> None:
        if name in self._items:
            raise ValueError(f"Adapter '{name}' is already registered")
        self._items[name] = adapter

    def get(self, name: str) -> T:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown adapter '{name}'. Available: {', '.join(sorted(self._items))}"
            ) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[tuple[str, str], Tool[..., Any]] = {}
        self._aliases: dict[str, tuple[str, str]] = {}
        self._disabled: set[tuple[str, str]] = set()

    def register(self, candidate: Tool[..., Any] | BaseTool) -> Tool[..., Any]:
        tool = ensure_tool(candidate)
        key = (tool.name, tool.version)
        if key in self._tools:
            raise ToolDefinitionError(f"Duplicate tool registration: {tool.name}@{tool.version}")
        self._tools[key] = tool
        for alias in tool.spec.metadata.aliases:
            if alias in self._aliases:
                raise ToolDefinitionError(f"Duplicate tool alias: {alias}")
            self._aliases[alias] = key
        return tool

    def get(self, name: str, version: str | None = None) -> Tool[..., Any]:
        if version is None and name in self._aliases:
            key = self._aliases[name]
        elif version is None:
            candidates = [key for key in self._tools if key[0] == name]
            if not candidates:
                raise KeyError(name)
            key = sorted(candidates, key=lambda item: item[1])[-1]
        else:
            key = (name, version)
        if key in self._disabled:
            raise KeyError(f"Tool '{key[0]}@{key[1]}' is disabled")
        return self._tools[key]

    def disable(self, name: str, version: str | None = None) -> None:
        tool = self.get(name, version)
        self._disabled.add((tool.name, tool.version))

    def enable(self, name: str, version: str) -> None:
        self._disabled.discard((name, version))

    def search(
        self, *, tag: str | None = None, capability: str | None = None
    ) -> tuple[Tool[..., Any], ...]:
        return tuple(
            tool
            for key, tool in sorted(self._tools.items())
            if key not in self._disabled
            and (tag is None or tag in tool.spec.metadata.tags)
            and (capability is None or capability in tool.spec.capabilities.capabilities)
        )

    def manifest(self) -> list[dict[str, Any]]:
        return [tool.manifest() for tool in self.search()]

    def load_plugins(self, group: str = "tooltether.tools") -> tuple[str, ...]:
        loaded: list[str] = []
        for point in entry_points(group=group):
            plugin = point.load()
            result = plugin(self) if callable(plugin) else None
            if isinstance(result, (Tool, BaseTool)):
                self.register(result)
            loaded.append(point.name)
        return tuple(loaded)
