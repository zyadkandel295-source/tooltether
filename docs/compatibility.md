# Compatibility matrix

Verified on 2026-08-15 with local CPython 3.14.4 and 3.11.9 environments, plus GitHub Actions CI history for the supported Python/OS matrix.

| Surface | Declared range | Verification | Status |
|---|---|---|---|
| Python | 3.11-3.14 | Local 3.11.9 and 3.14.4 suites; CI matrix for Ubuntu, Windows, and macOS | Pass |
| Pydantic | >=2.12,<3 | 2.13.4 | Pass |
| OpenAI schema | current function tool shape | contract tests | Pass |
| Anthropic schema | current client-tool shape | contract tests | Pass |
| MCP Python SDK | >=1.25,<2 | installed server/schema smoke | Pass |
| langchain-core | >=1.1,<2 | sync/async StructuredTool smoke | Pass |
| CrewAI | >=1.7,<2 | boundary test | Experimental |
| autogen-core | >=0.7,<1 | boundary test | Experimental |
| smolagents | >=1.24,<2 | boundary test | Experimental |

The scheduled optional-compatibility workflow installs optional extras. Experimental adapters remain supported only at the ToolTether boundary until upstream APIs stabilize and installed-SDK matrices are consistently green.

Adapter maturity is also exposed programmatically through `adapter_registry.get(name).info()`. Stable adapters are recommended for normal alpha users; beta adapters are usable with integration caution; experimental adapters are available for early feedback and may need faster follow-up changes as upstream APIs move.
