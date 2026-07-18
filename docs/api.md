# Public API

The package root exports stable core names: `tool`, `Tool`, `BaseTool`, `Runtime`, `RuntimeConfig`, `ToolRegistry`, `Policy`, reliability policies, canonical models, structured errors, `SQLiteStorage`, `Optimizer`, `select_model`, and approval handlers.

Framework-specific objects remain in `tooltether.adapters` and are not part of the core interface. Objects not exported through `tooltether.__all__` are internal or provisional.

