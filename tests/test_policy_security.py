from __future__ import annotations

from pathlib import Path

import pytest

from tooltether import ExecutionContext, ExecutionIdentity, Policy, tool
from tooltether.models import PermissionDecisionType
from tooltether.security import is_public_network_target, normalize_resource, payload_hash, redact


def context(workspace: str | None = None) -> ExecutionContext:
    return ExecutionContext(
        execution_id="execution",
        correlation_id="correlation",
        tool_name="read_file",
        tool_version="1.0.0",
        tool_fingerprint="a" * 64,
        identity=ExecutionIdentity(principal="alice", workspace=workspace),
    )


def test_policy_precedence_and_explanation() -> None:
    @tool(permissions=["filesystem:read"])
    def read_file(path: str) -> str:
        """Read a file marker."""
        return path

    policy = Policy(default=PermissionDecisionType.DENY)
    policy.allow(capability="filesystem:read", principal="alice", priority=1, rule_id="allow")
    policy.deny(tool="read_file", priority=1, rule_id="deny")
    decision = policy.evaluate(read_file, context(), resource="safe.txt")
    assert decision.decision == PermissionDecisionType.DENY
    assert set(decision.matched_rule_ids) == {"allow", "deny"}
    assert "matched" in decision.explain()


def test_resource_allowlist_and_traversal(tmp_path: Path) -> None:
    @tool(permissions=["filesystem:read"])
    def read_file(path: str) -> str:
        """Read a file marker."""
        return path

    policy = Policy(default=PermissionDecisionType.DENY)
    policy.allow(tool="read_file", resources=("documents/**",), priority=1, rule_id="documents")
    allowed = policy.evaluate(read_file, context(str(tmp_path)), resource="documents/report.txt")
    denied = policy.evaluate(read_file, context(str(tmp_path)), resource="../secret.txt")
    assert allowed.decision == PermissionDecisionType.ALLOW
    assert denied.decision == PermissionDecisionType.DENY
    with pytest.raises(ValueError, match="escapes workspace"):
        normalize_resource("../secret.txt", tmp_path)


def test_network_target_checks() -> None:
    assert is_public_network_target("https://8.8.8.8/path")
    assert is_public_network_target("https://example.com")
    assert not is_public_network_target("http://127.0.0.1")
    assert not is_public_network_target("http://169.254.169.254/latest/meta-data")
    assert not is_public_network_target("localhost")


def test_network_policy_allowlist_rejects_private_hosts() -> None:
    @tool(permissions=["network:http"], external_access=True)
    def fetch(url: str) -> str:
        """Return a URL."""
        return url

    policy = Policy(default=PermissionDecisionType.DENY)
    policy.allow(tool="fetch", hostnames=("*.example.com",), rule_id="public-example")
    assert (
        policy.evaluate(fetch, context(), hostname="api.example.com").decision
        == PermissionDecisionType.ALLOW
    )
    assert (
        policy.evaluate(fetch, context(), hostname="127.0.0.1").decision
        == PermissionDecisionType.DENY
    )


def test_redaction_log_injection_and_hashing() -> None:
    value = {
        "api_key": "sk-abcdefghijklmnopqrst",
        "message": "first\nsecond",
        "nested": {"password": "secret"},
    }
    safe = redact(value)
    assert safe["api_key"] == "[REDACTED]"
    assert safe["nested"]["password"] == "[REDACTED]"
    assert safe["message"] == "first\\nsecond"
    assert payload_hash({"b": 2, "a": 1}) == payload_hash({"a": 1, "b": 2})
