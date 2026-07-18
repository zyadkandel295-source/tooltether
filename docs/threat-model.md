# Threat model

## Assets and trust boundaries

Tool arguments, credentials, local files, databases, remote services, audit integrity, tenant separation, and framework call IDs are protected assets. Model output, tool arguments, third-party plugins, remote MCP servers, and arbitrary tool code may be hostile.

## Threats and controls

- **Malicious tools:** the runtime validates calls but cannot sandbox the handler. Use a process/container/VM boundary.
- **Prompt-injected or over-permissioned calls:** explicit policy and approval decisions execute before handlers.
- **Path traversal and symlinks:** paths are resolved under a configured workspace; applications must define symlink policy and OS permissions for high assurance.
- **SSRF:** direct private, loopback, link-local, metadata, multicast, reserved, and unspecified IP targets are rejected when host policies are used. DNS rebinding still requires a network-layer egress proxy.
- **Secret leakage:** key/value pattern redaction is defense in depth; payload logging is off. Keep credentials out of arguments where possible.
- **Duplicate effects and unsafe retries:** retry is zero by default; side effects require declared idempotency, and identity/fingerprint-scoped keys prevent replay.
- **Cache cross-tenant leakage:** identity scope and tool fingerprint are part of hashed keys. Distributed backends must preserve that invariant.
- **Log injection:** newline escaping and secret redaction are applied to event attributes.
- **Malicious plugins:** discovery is explicit. Loading an entry point executes installed Python and therefore requires package trust.
- **Supply chain:** optional SDKs are extras, CI audits dependencies, releases use OIDC, and no long-lived PyPI token is stored.
- **Adapter bypass:** shipped execution adapters bind back to the runtime. Direct handler calls remain possible unless the application prevents them.
- **Telemetry leakage:** core stores metadata only and exports nothing remotely by default.
- **Audit tampering:** optional hash chaining detects modification but does not stop deletion or a privileged attacker from replacing the database.

## Limitations

A Python library cannot fully sandbox arbitrary malicious Python in-process. Permission annotations and tool descriptions are not security boundaries. ToolTether governs only calls routed through it. Strong isolation and authorization remain application/platform responsibilities.

