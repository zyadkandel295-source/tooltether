# Compatibility matrix

Verified on 2026-07-17 with CPython 3.14.4 in the local workspace.

| Surface | Declared range | Verification | Status |
|---|---|---|---|
| Python | 3.11–3.14 | 3.14.4: full suite | Supported range pending CI matrix |
| Pydantic | >=2.12,<3 | 2.13.4 | Pass |
| OpenAI schema | current function tool shape | contract tests | Pass |
| Anthropic schema | current client-tool shape | contract tests | Pass |
| MCP Python SDK | >=1.25,<2 | 1.28.1 installed server/schema smoke | Pass |
| langchain-core | >=1.1,<2 | 1.4.9 sync/async StructuredTool smoke | Pass |
| CrewAI | >=1.7,<2 | boundary test | Experimental |
| autogen-core | >=0.7,<1 | boundary test | Experimental |
| smolagents | >=1.24,<2 | boundary test | Experimental |

The scheduled compatibility workflow installs optional extras and must pass before a release may upgrade “boundary test” to a tested SDK version.
