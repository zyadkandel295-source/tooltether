# Changelog

All notable changes follow Keep a Changelog and semantic versioning.

## [0.1.0] - 2026-08-12

### Added
- Canonical typed tools, schemas, manifests, deterministic fingerprints, and registry.
- Async-first runtime with validation, policy/approval, limits, timeout, safe retries, cache, idempotency, events, telemetry, and hash-chained audit logging.
- Explainable bounded timeout/cache recommendations and provider-neutral model scoring.
- OpenAI, Anthropic, MCP, LangChain/LangGraph, CrewAI, AutoGen, and smolagents framework adapters.
- Official repository benchmark suite in `benchmarks/` (`runtime_overhead.py`, `payload_scaling.py`, `concurrency.py`, `sustained_load.py`, `cache.py`, `storage.py`).
- TestPyPI release workflow (`.github/workflows/testpypi.yml`).

### Fixed
- Resolved Python 3.14 + Windows + `pytest-asyncio` fixture scope incompatibility by declaring `asyncio_default_fixture_loop_scope = "function"` and setting `--basetemp=.pytest_tmp`.

### Performance & Security Hardening
- Implemented high-performance WAL (Write-Ahead Logging) mode and `PRAGMA synchronous = NORMAL` for SQLite storage.
- Consolidated telemetry logging and hash-chained audit logging into a single thread-pool dispatch and single transaction (`SQLiteStorage.write_telemetry_and_audit`).
- Reduced runtime median latency by 86.0% (from 31.67 ms to 4.44 ms memory / 5.29 ms disk).
- Reduced P95 tail latency by 92.7% (from 105.89 ms to 7.73 ms) and maximum latency by 98.0% (from 463.22 ms to 9.18 ms).
