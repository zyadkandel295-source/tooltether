# ADR 0001: Canonical contract and async-first pipeline

Status: accepted for 0.1.0 alpha.

ToolTether uses a Pydantic-backed canonical `ToolSpec`, a deterministic SHA-256 contract fingerprint, an asyncio-first runtime, lazy adapters, and transactional SQLite local storage. The design keeps provider SDKs out of core, routes adapter calls back through one safety pipeline, makes evidence environment/fingerprint scoped, and treats tool metadata as policy input rather than a security guarantee.

