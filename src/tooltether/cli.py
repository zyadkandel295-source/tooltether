"""Dependency-free command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, cast

from .adapters import adapter_registry
from .constants import PROJECT_DISPLAY_NAME, PROJECT_VERSION
from .errors import ToolTetherError
from .registry import ToolRegistry
from .runtime import Runtime
from .tool import Tool, ensure_tool


def _load(reference: str) -> Any:
    try:
        module_name, attribute = reference.split(":", 1)
    except ValueError as exc:
        raise ValueError("Object references must use module:attribute syntax") from exc
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


def _json_input(value: str) -> dict[str, Any]:
    source = Path(value)
    text = source.read_text(encoding="utf-8") if source.is_file() else value
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Tool input must be a JSON object")
    return parsed


def _render(value: Any, json_output: bool) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    if json_output or isinstance(value, (dict, list)):
        print(json.dumps(value, indent=None if json_output else 2, default=str, sort_keys=True))
    else:
        print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tooltether", description="Define once. Execute consistently. Improve safely."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version", help="Show the package version")
    sub.add_parser("doctor", help="Inspect the local installation")
    sub.add_parser("init", help="Create a safe local configuration")
    inspect_cmd = sub.add_parser("inspect", help="Inspect a tool contract")
    inspect_cmd.add_argument("reference")
    validate = sub.add_parser("validate", help="Validate a tool or registry")
    validate.add_argument("reference")
    run = sub.add_parser("run", help="Run a tool through the runtime")
    run.add_argument("reference")
    run.add_argument("--input", required=True)
    export = sub.add_parser("export", help="Export a framework tool schema")
    export.add_argument("reference")
    export.add_argument("--format", choices=adapter_registry.names(), required=True)
    policy = sub.add_parser("policy-check", help="Simulate the default policy")
    policy.add_argument("reference")
    policy.add_argument("--input", default="{}")
    serve = sub.add_parser("serve-mcp", help="Serve a ToolRegistry over MCP stdio")
    serve.add_argument("reference")
    audit = sub.add_parser("audit-list", help="List local audit records")
    audit.add_argument("--limit", type=int, default=20)
    sub.add_parser("telemetry-summary", help="Show in-process runtime metrics")
    optimize = sub.add_parser("optimize-recommend", help="Generate bounded recommendations")
    optimize.add_argument("reference")
    benchmark = sub.add_parser("benchmark", help="Measure direct and runtime overhead")
    benchmark.add_argument("reference")
    benchmark.add_argument("--input", required=True)
    benchmark.add_argument("--iterations", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    json_output = bool(args.json)
    try:
        if args.command == "version":
            _render({"name": PROJECT_DISPLAY_NAME, "version": PROJECT_VERSION}, json_output)
        elif args.command == "doctor":
            _render(
                {
                    "name": PROJECT_DISPLAY_NAME,
                    "version": PROJECT_VERSION,
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "adapters": adapter_registry.names(),
                },
                json_output,
            )
        elif args.command == "init":
            destination = Path("tooltether.toml")
            if destination.exists():
                raise FileExistsError(f"Refusing to overwrite {destination}")
            destination.write_text(
                '[runtime]\nenvironment = "development"\nstorage_path = ".tooltether/runtime.db"\n',
                encoding="utf-8",
            )
            _render({"created": str(destination)}, json_output)
        elif args.command in {"inspect", "validate"}:
            value = _load(args.reference)
            rendered: Any
            if isinstance(value, ToolRegistry):
                rendered = value.manifest()
            else:
                rendered = ensure_tool(value).manifest()
            _render(rendered, json_output)
        elif args.command == "run":
            runtime = Runtime()
            result = runtime.run(ensure_tool(_load(args.reference)), _json_input(args.input))
            _render(result, json_output)
        elif args.command == "export":
            tool = ensure_tool(_load(args.reference))
            runtime = Runtime()
            _render(tool.export(args.format, runtime=runtime), json_output)
        elif args.command == "policy-check":
            tool = ensure_tool(_load(args.reference))
            runtime = Runtime()
            result = runtime.run(tool, _json_input(args.input))
            _render({"decision": "allow", "execution_id": result.execution_id}, json_output)
        elif args.command == "serve-mcp":
            registry = _load(args.reference)
            if not isinstance(registry, ToolRegistry):
                raise TypeError("serve-mcp requires a ToolRegistry")
            asyncio.run(_serve_mcp(registry))
        elif args.command == "audit-list":
            runtime = Runtime()
            _render(asyncio.run(runtime.storage.list_audit(args.limit)), json_output)
        elif args.command == "telemetry-summary":
            _render(Runtime().metrics.summary(), json_output)
        elif args.command == "optimize-recommend":
            runtime = Runtime()
            recommendations = asyncio.run(
                runtime.optimizer.recommend(ensure_tool(_load(args.reference)))
            )
            _render(recommendations, json_output)
        elif args.command == "benchmark":
            _render(
                _benchmark(
                    ensure_tool(_load(args.reference)), _json_input(args.input), args.iterations
                ),
                json_output,
            )
        return 0
    except (
        ToolTetherError,
        ValueError,
        TypeError,
        KeyError,
        FileNotFoundError,
        FileExistsError,
    ) as exc:
        error = (
            exc.to_dict()
            if isinstance(exc, ToolTetherError)
            else {
                "code": type(exc).__name__,
                "message": str(exc),
            }
        )
        if json_output:
            print(json.dumps({"error": error}, sort_keys=True))
        else:
            print(f"error: {error['message']}", file=sys.stderr)
        return 2


async def _serve_mcp(registry: ToolRegistry) -> None:
    from mcp.server.stdio import stdio_server

    runtime = Runtime()
    adapter = adapter_registry.get("mcp")
    server = cast(Any, adapter).create_server(registry, runtime)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _benchmark(tool: Tool[..., Any], arguments: dict[str, Any], iterations: int) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    runtime = Runtime()
    started = time.perf_counter()
    for _ in range(iterations):
        tool.function(**arguments)
    direct = time.perf_counter() - started
    started = time.perf_counter()
    for _ in range(iterations):
        runtime.run(tool, arguments)
    managed = time.perf_counter() - started
    return {
        "iterations": iterations,
        "direct_seconds": direct,
        "runtime_seconds": managed,
        "overhead_seconds_per_call": (managed - direct) / iterations,
        "python": platform.python_version(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
