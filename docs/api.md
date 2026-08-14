# Public API

The package root exports stable core names: `tool`, `Tool`, `BaseTool`, `Runtime`, `RuntimeConfig`, `ExecutionPolicy`, `ExecutionMode`, `ToolRegistry`, `Policy`, reliability policies, canonical models, structured errors, `SQLiteStorage`, `Optimizer`, `select_model`, and approval handlers.

Framework-specific objects remain in `tooltether.adapters`. Adapter maturity and capability metadata are available through `adapter_registry.get(name).info()`.

Objects not exported through `tooltether.__all__` or documented adapter modules are internal or provisional.
