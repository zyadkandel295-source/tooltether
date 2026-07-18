from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tooltether import (
    AuditRecord,
    ModelCandidate,
    OptimizationPolicy,
    Outcome,
    RuntimeConfig,
    SQLiteStorage,
    TelemetryRecord,
    UnsafeOperationError,
    select_model,
    tool,
)
from tooltether.cache import MemoryCache
from tooltether.optimizer import Optimizer


@pytest.mark.asyncio
async def test_memory_cache_ttl_lru_and_invalidation() -> None:
    cache = MemoryCache(max_entries=2)
    await cache.set("a", 1, 10, tags=frozenset({"x"}), tool_fingerprint="f1")
    await cache.set("b", 2, 10, tags=frozenset({"y"}), tool_fingerprint="f2")
    assert await cache.get("a") == 1
    await cache.set("c", 3, 10)
    assert await cache.get("b") is None
    assert await cache.invalidate(tag="x") == 1
    await cache.set("short", 4, 0)
    assert await cache.get("short") is None


@pytest.mark.asyncio
async def test_cache_stampede_protection() -> None:
    cache = MemoryCache()
    calls = 0

    async def factory() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return 42

    values = await asyncio.gather(*(cache.get_or_compute("key", factory, 10) for _ in range(5)))
    assert {item[0] for item in values} == {42}
    assert calls == 1
    assert sum(item[1] for item in values) == 4


def audit(execution_id: str) -> AuditRecord:
    return AuditRecord(
        execution_id=execution_id,
        correlation_id=execution_id,
        tool_name="tool",
        tool_version="1",
        tool_fingerprint="a" * 64,
        principal="test",
        decision="allow",
        started_at=datetime.now(UTC),
        duration_seconds=0.1,
        outcome=Outcome.SUCCEEDED,
        attempts=1,
        cache_hit=False,
    )


@pytest.mark.asyncio
async def test_sqlite_audit_telemetry_and_idempotency(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "runtime.db")
    first = await storage.append_audit(audit("one"))
    second = await storage.append_audit(audit("two"))
    assert first.sequence == 1
    assert second.previous_hash == first.record_hash
    assert await storage.verify_audit_chain()
    assert len(await storage.list_audit()) == 2

    record = TelemetryRecord(
        execution_id="one",
        tool_fingerprint="a" * 64,
        environment="test",
        latency_seconds=0.2,
        outcome=Outcome.SUCCEEDED,
        attempts=1,
    )
    await storage.add_telemetry(record)
    assert (await storage.telemetry_for("a" * 64, "test"))[0] == record
    await storage.save_idempotent("a" * 64, "alice", "key", {"value": 1})
    assert await storage.get_idempotent("a" * 64, "alice", "key") == {"value": 1}
    await storage.close()


@pytest.mark.asyncio
async def test_audit_chain_detects_tampering() -> None:
    storage = SQLiteStorage()
    await storage.append_audit(audit("one"))
    with storage._lock, storage._connection:
        storage._connection.execute("UPDATE audit SET record_hash='bad' WHERE sequence=1")
    assert not await storage.verify_audit_chain()


@pytest.mark.asyncio
async def test_timeout_recommendation_apply_and_rollback() -> None:
    @tool(timeout=10)
    def measured(value: int) -> int:
        """Return a measured value."""
        return value

    storage = SQLiteStorage()
    for index in range(20):
        await storage.add_telemetry(
            TelemetryRecord(
                execution_id=str(index),
                tool_fingerprint=measured.fingerprint.value,
                environment="test",
                latency_seconds=0.1 + index / 1000,
                outcome=Outcome.SUCCEEDED,
                attempts=1,
            )
        )
    optimizer = Optimizer(
        storage,
        OptimizationPolicy(min_samples=20, min_timeout=0.05, max_timeout=2),
        "test",
    )
    recommendations = await optimizer.recommend(measured)
    assert recommendations[0].setting == "timeout"
    assert recommendations[0].sample_size == 20
    profile = await optimizer.apply(measured, recommendations[0])
    assert "timeout" in profile.settings
    rolled = await optimizer.rollback(measured)
    assert rolled is not None
    assert rolled.settings == profile.previous_settings


@pytest.mark.asyncio
async def test_optimizer_rejects_out_of_bounds() -> None:
    @tool
    def measured() -> int:
        """Return one."""
        return 1

    optimizer = Optimizer(SQLiteStorage(), OptimizationPolicy(max_timeout=1), "test")
    from tooltether import OptimizationRecommendation

    recommendation = OptimizationRecommendation(
        recommendation_id="bad",
        tool_fingerprint=measured.fingerprint.value,
        setting="timeout",
        current_value=30,
        recommended_value=100,
        reason="bad",
        sample_size=20,
        confidence=0.9,
    )
    with pytest.raises(UnsafeOperationError):
        await optimizer.apply(measured, recommendation)


def test_model_selection_constraints_and_objectives() -> None:
    candidates = [
        ModelCandidate(
            provider="a",
            model="cheap",
            estimated_cost=1,
            estimated_latency=2,
            quality=0.7,
            capabilities=frozenset({"tools"}),
            context_limit=1000,
        ),
        ModelCandidate(
            provider="b",
            model="quality",
            estimated_cost=5,
            estimated_latency=1,
            quality=0.95,
            capabilities=frozenset({"tools", "vision"}),
            context_limit=2000,
        ),
    ]
    assert select_model(candidates, objective="minimize_cost").candidate.model == "cheap"
    assert (
        select_model(candidates, required_capabilities=frozenset({"vision"})).candidate.model
        == "quality"
    )
    with pytest.raises(ValueError, match="No model"):
        select_model(candidates, max_cost=0.1)


def test_runtime_config_env_and_toml(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TOOLTETHER_ENVIRONMENT", "production")
    monkeypatch.setenv("TOOLTETHER_DEFAULT_TIMEOUT", "12")
    config = RuntimeConfig.from_env()
    assert config.environment.name == "production"
    assert config.default_timeout.seconds == 12
    path = tmp_path / "config.toml"
    path.write_text('[runtime]\nstorage_path = "runtime.db"\n', encoding="utf-8")
    assert RuntimeConfig.from_file(path).storage_path == "runtime.db"
    with pytest.raises(ValueError, match="JSON and TOML"):
        RuntimeConfig.from_file(tmp_path / "config.yaml")
