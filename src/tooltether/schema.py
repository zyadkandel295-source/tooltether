"""Deterministic schema generation and validation from Python type hints."""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from typing import Any, cast, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, create_model

from .errors import ToolDefinitionError, ToolValidationError


def _model_name(tool_name: str) -> str:
    return "".join(part.capitalize() for part in tool_name.replace("-", "_").split("_")) + "Input"


def _annotation_target(function: Callable[..., Any]) -> Any:
    if inspect.isroutine(function) or inspect.isclass(function) or inspect.ismodule(function):
        return function
    if callable(function):
        return type(function).__call__
    return function


def _type_hints(function: Callable[..., Any], tool_name: str) -> dict[str, Any]:
    try:
        return get_type_hints(_annotation_target(function), include_extras=True)
    except (TypeError, ValueError, NameError) as exc:
        raise ToolDefinitionError(f"Cannot inspect callable for tool '{tool_name}': {exc}") from exc


def create_input_model(function: Callable[..., Any], tool_name: str) -> type[BaseModel]:
    try:
        signature = inspect.signature(function)
        hints = _type_hints(function, tool_name)
    except ToolDefinitionError:
        raise
    except (TypeError, ValueError) as exc:
        raise ToolDefinitionError(f"Cannot inspect callable for tool '{tool_name}': {exc}") from exc
    fields: dict[str, tuple[Any, Any]] = {}
    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        if parameter.kind in (
            parameter.VAR_POSITIONAL,
            parameter.VAR_KEYWORD,
            parameter.POSITIONAL_ONLY,
        ):
            raise ToolDefinitionError(
                f"Tool '{tool_name}' parameter '{name}' uses an unsupported signature kind"
            )
        annotation = hints.get(name, parameter.annotation)
        if annotation is inspect.Signature.empty:
            raise ToolDefinitionError(
                f"Tool '{tool_name}' parameter '{name}' must have a type annotation"
            )
        default = parameter.default if parameter.default is not inspect.Signature.empty else ...
        fields[name] = (annotation, default)
    try:
        return cast(
            type[BaseModel],
            create_model(  # type: ignore[call-overload]
                _model_name(tool_name),
                # JSON representations of enums and dataclasses must remain parseable.
                # Pydantic still rejects incompatible primitives and unexpected fields.
                __config__=ConfigDict(extra="forbid", strict=False),
                **fields,
            ),
        )
    except Exception as exc:
        raise ToolDefinitionError(f"Cannot build input schema for '{tool_name}': {exc}") from exc


def create_output_adapter(function: Callable[..., Any], tool_name: str) -> TypeAdapter[Any]:
    try:
        hints = _type_hints(function, tool_name)
        annotation = hints.get("return", inspect.signature(function).return_annotation)
    except ToolDefinitionError:
        raise
    except (TypeError, ValueError) as exc:
        raise ToolDefinitionError(f"Cannot inspect output type for '{tool_name}': {exc}") from exc
    if annotation in (inspect.Signature.empty, None):
        raise ToolDefinitionError(f"Tool '{tool_name}' must have a return type annotation")
    if get_origin(annotation) in {AsyncIterator, AsyncGenerator}:
        annotation = get_args(annotation)[0]
    try:
        return TypeAdapter(annotation)
    except Exception as exc:
        raise ToolDefinitionError(f"Cannot build output schema for '{tool_name}': {exc}") from exc


def validate_input(
    model: type[BaseModel], arguments: dict[str, Any], *, tool_name: str, tool_version: str
) -> dict[str, Any]:
    try:
        validated = model.model_validate(arguments)
        return {name: getattr(validated, name) for name in model.model_fields}
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        field = ".".join(str(part) for part in first.get("loc", ())) or "input"
        message = first.get("msg", "is invalid")
        received = first.get("input")
        raise ToolValidationError(
            f'Field "{field}" {message}. Received: {received!r}. Tool: {tool_name}@{tool_version}',
            tool_name=tool_name,
            tool_version=tool_version,
            safe_details={"field": field, "error_type": first.get("type")},
        ) from exc


def validate_output(
    adapter: TypeAdapter[Any], value: Any, *, tool_name: str, tool_version: str
) -> Any:
    try:
        return adapter.validate_python(value, strict=True)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        raise ToolValidationError(
            f"Tool '{tool_name}@{tool_version}' returned an invalid value: {first['msg']}",
            tool_name=tool_name,
            tool_version=tool_version,
            safe_details={"error_type": first.get("type")},
        ) from exc


def deterministic_schema(model_or_adapter: type[BaseModel] | TypeAdapter[Any]) -> dict[str, Any]:
    schema = (
        model_or_adapter.model_json_schema(mode="validation")
        if isinstance(model_or_adapter, type) and issubclass(model_or_adapter, BaseModel)
        else model_or_adapter.json_schema(mode="validation")
    )
    schema.pop("title", None)
    return cast(dict[str, Any], _sort_schema(schema))


def _sort_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sort_schema(item) for item in value]
    return value


def openai_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize an object schema to the strict function-tool subset."""
    normalized = _sort_schema(schema)

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object" or "properties" in node:
            node["additionalProperties"] = False
            properties = node.get("properties", {})
            if isinstance(properties, dict):
                for child in properties.values():
                    visit(child)
        for key in ("items", "anyOf", "oneOf", "allOf", "$defs"):
            child = node.get(key)
            if isinstance(child, dict):
                for nested in child.values():
                    visit(nested)
            elif isinstance(child, list):
                for nested in child:
                    visit(nested)

    visit(normalized)
    return cast(dict[str, Any], normalized)
