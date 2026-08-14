# Security policy

Report security issues privately through GitHub Security Advisories / private vulnerability reporting for this repository. If that channel is unavailable, contact the repository owner before opening a public issue.

Do not disclose suspected credential leakage, policy bypass, cross-tenant cache access, unsafe retry, path traversal, SSRF, plugin execution, or audit-integrity defects in a public issue. Include affected version, minimal reproduction, impact, and proposed embargo window.

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x alpha | Security reports accepted; fixes are best-effort until the public release process is established |

## Execution threat model

ToolTether validates inputs, applies policy decisions, approval checks, rate/concurrency limits, timeout handling, telemetry, audit logging, and the explicit `ExecutionPolicy` gate for calls routed through `Runtime`.

ToolTether does not provide an OS, process, container, VM, filesystem, network, or Python bytecode sandbox. Treat untrusted Python tools as untrusted code and isolate them outside ToolTether.

## Dependency vulnerability policy

Runtime dependencies are intentionally minimal and optional framework SDKs remain extras. Release candidates should pass `pip-audit`, `bandit -q -r src`, `python -m pip check`, package-content validation, and fresh installed-package smoke tests before tagging.

ToolTether does not sandbox Python handlers. Reports whose only premise is that directly invoked arbitrary Python can access its process are outside the intended boundary unless a documented runtime control is bypassed.
