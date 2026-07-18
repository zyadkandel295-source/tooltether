"""Explainable ordered policy evaluation and approval handlers."""

from __future__ import annotations

import fnmatch
import inspect
import ipaddress
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from .models import (
    ExecutionContext,
    PermissionDecision,
    PermissionDecisionType,
    PermissionRequest,
    PolicyRule,
    SideEffects,
)
from .security import is_public_network_target, normalize_resource
from .tool import Tool


class ApprovalHandler(Protocol):
    async def __call__(self, request: PermissionRequest) -> PermissionDecision: ...


class NonInteractiveApprovalHandler:
    def __init__(self, allow: bool = False) -> None:
        self.allow = allow

    async def __call__(self, request: PermissionRequest) -> PermissionDecision:
        return PermissionDecision(
            decision=PermissionDecisionType.ALLOW_ONCE
            if self.allow
            else PermissionDecisionType.DENY,
            reason_code="non_interactive_allow" if self.allow else "non_interactive_deny",
        )


class CallableApprovalHandler:
    def __init__(
        self,
        callback: Callable[[PermissionRequest], PermissionDecision | Awaitable[PermissionDecision]],
    ) -> None:
        self.callback = callback

    async def __call__(self, request: PermissionRequest) -> PermissionDecision:
        result = self.callback(request)
        if inspect.isawaitable(result):
            return await result
        return result


class Policy:
    """Priority-ordered matching; deny wins ties and dangerous undeclared access is denied."""

    def __init__(self, *, default: PermissionDecisionType = PermissionDecisionType.ALLOW) -> None:
        self.default = default
        self._rules: list[PolicyRule] = []
        self._counter = 0

    @property
    def rules(self) -> tuple[PolicyRule, ...]:
        return tuple(self._rules)

    def add(self, rule: PolicyRule) -> PolicyRule:
        if any(existing.rule_id == rule.rule_id for existing in self._rules):
            raise ValueError(f"Duplicate policy rule id: {rule.rule_id}")
        self._rules.append(rule)
        return rule

    def _add(self, decision: PermissionDecisionType, **conditions: object) -> PolicyRule:
        self._counter += 1
        rule_id = str(conditions.pop("rule_id", f"rule-{self._counter}"))
        return self.add(PolicyRule(rule_id=rule_id, decision=decision, **conditions))

    def allow(self, **conditions: object) -> PolicyRule:
        return self._add(PermissionDecisionType.ALLOW, **conditions)

    def deny(self, **conditions: object) -> PolicyRule:
        return self._add(PermissionDecisionType.DENY, **conditions)

    def require_approval(self, **conditions: object) -> PolicyRule:
        return self._add(PermissionDecisionType.REQUIRE_APPROVAL, **conditions)

    def limit(self, *, max_calls: int, window: str, **conditions: object) -> PolicyRule:
        conditions["constraints"] = {"max_calls": max_calls, "window": window}
        return self._add(PermissionDecisionType.ALLOW_WITH_CONSTRAINTS, **conditions)

    def evaluate(
        self,
        tool: Tool[..., object],
        context: ExecutionContext,
        *,
        resource: str | None = None,
        hostname: str | None = None,
        method: str | None = None,
    ) -> PermissionDecision:
        matches = [
            rule
            for rule in self._rules
            if self._matches(
                rule, tool, context, resource=resource, hostname=hostname, method=method
            )
        ]
        if matches:
            rank = {
                PermissionDecisionType.DENY: 5,
                PermissionDecisionType.REQUIRE_APPROVAL: 4,
                PermissionDecisionType.ALLOW_WITH_CONSTRAINTS: 3,
                PermissionDecisionType.ALLOW_ONCE: 2,
                PermissionDecisionType.ALLOW: 1,
            }
            selected = max(matches, key=lambda item: (item.priority, rank[item.decision]))
            return PermissionDecision(
                decision=selected.decision,
                reason_code="matched_policy_rule",
                matched_rule_ids=tuple(rule.rule_id for rule in matches),
                constraints=selected.constraints,
            )
        if tool.spec.risk.approval_required:
            return PermissionDecision(
                decision=PermissionDecisionType.REQUIRE_APPROVAL,
                reason_code="tool_declares_approval_required",
            )
        dangerous = tool.spec.risk.side_effects in {
            SideEffects.WRITE,
            SideEffects.DESTRUCTIVE,
            SideEffects.EXTERNAL,
            SideEffects.FINANCIAL,
        }
        if dangerous and not tool.spec.capabilities.capabilities:
            return PermissionDecision(
                decision=PermissionDecisionType.DENY,
                reason_code="undeclared_dangerous_capability",
            )
        return PermissionDecision(decision=self.default, reason_code="default_policy")

    def simulate(self, *args: object, **kwargs: object) -> PermissionDecision:
        return self.evaluate(*args, **kwargs)  # type: ignore[arg-type]

    def _matches(
        self,
        rule: PolicyRule,
        tool: Tool[..., object],
        context: ExecutionContext,
        *,
        resource: str | None,
        hostname: str | None,
        method: str | None,
    ) -> bool:
        identity = context.identity
        checks = (
            not rule.tool or fnmatch.fnmatchcase(tool.name, rule.tool),
            not rule.version or fnmatch.fnmatchcase(tool.version, rule.version),
            not rule.capability or rule.capability in tool.spec.capabilities.capabilities,
            not rule.principal or identity.principal == rule.principal,
            not rule.agent_id or identity.agent_id == rule.agent_id,
            not rule.user_id or identity.user_id == rule.user_id,
            not rule.workspace or identity.workspace == rule.workspace,
            not rule.environment or context.environment.name == rule.environment,
            rule.side_effects is None or tool.spec.risk.side_effects == rule.side_effects,
            not rule.risk_levels or tool.spec.risk.level in rule.risk_levels,
            not rule.tags or bool(rule.tags.intersection(tool.spec.metadata.tags)),
            not rule.methods
            or bool(method and method.upper() in {item.upper() for item in rule.methods}),
        )
        if not all(checks):
            return False
        if rule.resources:
            if resource is None:
                return False
            try:
                normalized = normalize_resource(resource, identity.workspace)
                base = Path(identity.workspace or Path.cwd()).resolve(strict=False)
                relative = normalized.relative_to(base).as_posix()
            except ValueError:
                return rule.decision == PermissionDecisionType.DENY
            if not any(
                fnmatch.fnmatchcase(relative, pattern.lstrip("./")) for pattern in rule.resources
            ):
                return False
        if rule.hostnames:
            if hostname is None:
                return False
            if not _host_matches(hostname, rule.hostnames):
                return False
        return True


def _host_matches(hostname: str, patterns: tuple[str, ...]) -> bool:
    if not is_public_network_target(hostname):
        return False
    host = hostname.lower().rstrip(".")
    for pattern in patterns:
        candidate = pattern.lower().rstrip(".")
        if "/" in candidate:
            try:
                if ipaddress.ip_address(host) in ipaddress.ip_network(candidate, strict=False):
                    return True
            except ValueError:
                continue
        elif fnmatch.fnmatchcase(host, candidate):
            return True
    return False
