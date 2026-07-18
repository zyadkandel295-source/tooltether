from __future__ import annotations

import typing
from typing import Annotated, TypedDict, get_args, get_origin

import pytest

from tooltether import schema as schema_module
from tooltether import tool


class LegacyDetails(TypedDict):
    label: str
    enabled: bool


def test_stdlib_typeddict_compat_conversion_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_module, "_NEEDS_TYPED_DICT_COMPAT", True)
    schema_module._TYPED_DICT_CACHE.clear()

    assert schema_module._is_stdlib_typed_dict_class(LegacyDetails)
    assert not schema_module._is_stdlib_typed_dict_class(dict)

    converted = schema_module._normalize_annotation(LegacyDetails)
    assert converted is schema_module._normalize_annotation(LegacyDetails)
    assert converted is not LegacyDetails
    assert type(converted).__module__ != "typing"
    assert converted.__annotations__ == LegacyDetails.__annotations__


def test_stdlib_typeddict_compat_nested_annotations(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(schema_module, "_NEEDS_TYPED_DICT_COMPAT", True)
    schema_module._TYPED_DICT_CACHE.clear()

    annotated = schema_module._normalize_annotation(
        Annotated[LegacyDetails | None, "legacy payload"]
    )
    union_arg = get_args(annotated)[0]
    assert get_origin(annotated) is Annotated
    assert get_args(union_arg)[1] is type(None)
    assert get_args(union_arg)[0] is not LegacyDetails

    list_annotation = schema_module._normalize_annotation(list[LegacyDetails])
    assert get_origin(list_annotation) is list
    assert get_args(list_annotation)[0] is not LegacyDetails

    typing_list_annotation = schema_module._normalize_annotation(typing.List[LegacyDetails])  # noqa: UP006
    assert get_origin(typing_list_annotation) is list
    assert get_args(typing_list_annotation)[0] is not LegacyDetails


def test_stdlib_typeddict_compat_path_builds_tool_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(schema_module, "_NEEDS_TYPED_DICT_COMPAT", True)
    schema_module._TYPED_DICT_CACHE.clear()

    @tool
    def render(details: LegacyDetails | None) -> str:
        """Render legacy typed dictionary details."""
        return details["label"] if details is not None else "missing"

    assert render({"label": "x", "enabled": True}) == "x"
    assert render.spec.input_schema["properties"]["details"]["anyOf"][0]["$ref"] == (
        "#/$defs/LegacyDetails"
    )
