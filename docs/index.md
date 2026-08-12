# ToolTether guide

ToolTether defines a canonical typed contract and routes supported framework calls through one controlled execution lifecycle. It does not sandbox arbitrary Python or replace provider authorization.

## Installation

Install `tooltether` for core functionality or an explicit extra such as `tooltether[mcp]`.

## Five-minute quickstart

```python
from tooltether import Runtime, tool


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


assert Runtime().run(add, {"a": 2, "b": 3}).value == 5
```

## Core concepts

`ToolSpec` is the portable contract. `ToolFingerprint` changes with execution-relevant schema, version, risk, and reliability configuration. `Runtime` owns validation, policy, limits, execution, observability, and optimization evidence.

## Defining tools

Use `@tool`, configured `@tool(...)`, callable objects, or `BaseTool`. Type annotations and a description are mandatory. Dataclasses, Pydantic models, TypedDict, enums, literals, optionals, collections, and nested structures are supported through Pydantic JSON Schema.

## Runtime execution

The runtime validates input before policy and before side effects, resolves approval, enforces per-identity rate and concurrency limits, checks idempotency and cache, executes with a total timeout and safe retry rule, validates output, then records local telemetry and audit data.

## Sync and async usage

`Runtime.arun` is native asyncio. Sync handlers run in a worker thread so they do not block the loop. `Runtime.run` creates a fresh event loop only when no loop is active. Async generators are supported through `Runtime.astream`.

## Permissions and policies

Rules match tool/version, capability, identity, workspace, environment, resource, hostname, method, side effect, risk, and tags. Deny wins equal-priority ties. `decision.explain()` identifies matched rules. Resource paths are resolved under the workspace and public-host checks reject direct private, loopback, link-local, metadata, multicast, and reserved IPs.

## Approvals

Approval is asynchronous. `NonInteractiveApprovalHandler` denies by default for server environments; applications can wrap their own handler with `CallableApprovalHandler`.

## Retries and idempotency

Retries default to zero. Non-idempotent side-effecting tools are clamped to one attempt. Idempotency records are keyed by tool fingerprint, identity scope, and application key.

## Timeouts

Per-tool, runtime hard maximum, cancellation, structured errors, and unknown-completion-state metadata are implemented. Python cannot forcibly stop a running sync thread, so sync side-effecting tools require process isolation for hard termination.

## Caching

The memory backend is async-safe LRU with TTL, tag/fingerprint invalidation, hashed keys, identity isolation, and stampede protection. Side-effecting tools cannot enable the built-in cache.

## Tracing and metrics

`RuntimeEvent` hooks and in-process metrics work without a backend. The optional OpenTelemetry hook uses an application-provided tracer and never configures a provider or exporter globally. Payloads are not emitted by default.

## Audit logs

SQLite audit records include identity, fingerprint, policy rules, outcome, retry/cache facts, and correlation ID. Optional SHA-256 hash chaining detects later modification; it is not a legal compliance claim.

## Adaptive optimization

Modes are `off`, `recommend`, and `auto_safe`. Timeout recommendations require a minimum sample count, high percentile, margin, confidence, and bounds. Profiles are environment/fingerprint scoped and support rollback.

## Model-backed tools

`select_model` applies hard provider/capability/cost/latency/quality/context constraints before transparent cost, latency, quality, or balanced scoring. It performs no exploration and makes no provider call.

## MCP integration

Schema export is core-only. Install `tooltether[mcp]` to construct a low-level official-SDK server; the CLI uses stdio. Transport authorization remains the host application's responsibility.

## OpenAI integration

The adapter exports strict Chat Completions-style function tools and a Responses-style helper, validates JSON arguments locally, preserves call IDs, executes through the runtime, and returns a function-call output. No model is hard-coded.

## Anthropic integration

The adapter exports `name`, `description`, and `input_schema`, preserves `tool_use` IDs, and maps failures to `tool_result` blocks with `is_error`.

## LangChain and LangGraph integration

Install the extra and export with `runtime=`. The `StructuredTool` sync and async handlers call the runtime. LangGraph support is through its accepted LangChain tool abstraction.

## CrewAI, AutoGen, and smolagents

These adapters are experimental and lazy. Their wrappers preserve runtime execution, but upstream lifecycle and cancellation behavior varies. smolagents code-agent sandboxing is separate from ToolTether permissions.

## CLI reference

Run `tooltether --help`. Commands include `init`, `doctor`, `inspect`, `validate`, `run`, `export`, `serve-mcp`, `policy-check`, audit/telemetry inspection, optimization recommendation, benchmark, and version.

## Configuration reference

Programmatic Pydantic configuration has precedence. `RuntimeConfig.from_env()` reads `TOOLTETHER_` values, and `from_file()` supports safe JSON and TOML. Secrets are excluded from dumps and repr.

## Plugin development

Register `tooltether.tools` or `tooltether.adapters` entry points. Loading is always explicit through `ToolRegistry.load_plugins`; installed plugins are never executed at core import time.

## Adapter development

Subclass `BaseAdapter`; report framework/version/stability, export a canonical tool, and ensure every execution path calls `Runtime.arun` or `Runtime.run`.

## Security and privacy model

See the [threat model](threat-model.md). Telemetry stores metadata, not arguments/results. Cache keys hash arguments and include identity. Applications own file, process, network, database, provider, and transport isolation.

## Compatibility matrix

See [compatibility.md](compatibility.md). Claims are limited to automated results.

## Migration and deprecation policy

Tool contracts, runtime configuration, and storage migrations have explicit versions. Public removals require a deprecation warning and a semantic-versioned release.

## Troubleshooting

- Missing adapter SDK: install the named extra from `MissingExtraError`.
- Nested event loop: use `await runtime.arun(...)`.
- Policy denial: inspect `decision.explain()` and declared capability metadata.
- Stale profile: contract fingerprint changes intentionally invalidate it.

## Performance and benchmarks

Run `python benchmarks/runtime_overhead.py`. Results are machine-specific microbenchmarks; direct calls remain the baseline and unfavorable overhead is reported.

## Contributing and release process

See `CONTRIBUTING.md` and `docs/release.md`. Documentation examples are exercised by tests or artifact smoke checks.

## API reference

See [api.md](api.md) and package-root `__all__` for the supported public API.

