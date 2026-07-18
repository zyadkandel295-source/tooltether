# Contributing

Contributions require Python 3.11 or newer. Create an environment, install `.[dev]`, and run the complete local gates before opening a pull request.

```bash
python -m pytest --cov=tooltether
ruff check .
ruff format --check .
mypy src
mkdocs build --strict
python -m build
python -m twine check dist/*
```

Behavior changes need tests. Security-sensitive policy changes need negative and traversal/identity tests. Adapter claims need an installed official-SDK compatibility test. Do not add network telemetry, credentials, import-time plugin execution, hidden global registries, or broad warning/type suppressions.

Contributions are submitted under Apache-2.0. Use focused commits and explain compatibility, security, and migration impact in the pull request.

