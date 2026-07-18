"""Evidence-based, bounded recommendations and provider-neutral model selection."""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from typing import Literal

from .errors import UnsafeOperationError
from .models import (
    ModelCandidate,
    ModelSelection,
    OptimizationPolicy,
    OptimizationProfile,
    OptimizationRecommendation,
    RiskLevel,
)
from .storage import SQLiteStorage
from .tool import Tool


class Optimizer:
    def __init__(
        self, storage: SQLiteStorage, policy: OptimizationPolicy, environment: str
    ) -> None:
        self.storage = storage
        self.policy = policy
        self.environment = environment

    async def recommend(self, tool: Tool[..., object]) -> list[OptimizationRecommendation]:
        if str(self.policy.mode) == "off":
            return []
        records = await self.storage.telemetry_for(tool.fingerprint.value, self.environment)
        if len(records) < self.policy.min_samples:
            return []
        successful = sorted(
            record.latency_seconds for record in records if str(record.outcome) == "succeeded"
        )
        if len(successful) < self.policy.min_samples:
            return []
        percentile = _percentile(successful, self.policy.timeout_percentile)
        recommended = min(
            self.policy.max_timeout,
            max(self.policy.min_timeout, percentile * self.policy.timeout_margin),
        )
        confidence = min(0.99, 1 - 1 / math.sqrt(len(successful)))
        result = [
            OptimizationRecommendation(
                recommendation_id=str(uuid.uuid4()),
                tool_fingerprint=tool.fingerprint.value,
                setting="timeout",
                current_value=tool.spec.timeout.seconds,
                recommended_value=round(recommended, 6),
                reason=(
                    f"Observed p{int(self.policy.timeout_percentile * 100)} latency "
                    f"{percentile:.4f}s with {self.policy.timeout_margin:.2f}x margin"
                ),
                sample_size=len(successful),
                confidence=confidence,
                estimated_effect={"percentile_seconds": percentile},
                risk=RiskLevel.LOW,
                rollback_value=tool.spec.timeout.seconds,
            )
        ]
        repeated = sum(1 for record in records if record.cache_hit)
        if tool.spec.risk.side_effects == "none" and repeated / len(records) >= 0.2:
            result.append(
                OptimizationRecommendation(
                    recommendation_id=str(uuid.uuid4()),
                    tool_fingerprint=tool.fingerprint.value,
                    setting="cache",
                    current_value=tool.spec.cache.enabled,
                    recommended_value={"enabled": True, "ttl_seconds": tool.spec.cache.ttl_seconds},
                    reason="Equivalent calls produced a material observed cache opportunity",
                    sample_size=len(records),
                    confidence=min(0.9, repeated / len(records) + 0.4),
                    estimated_effect={"observed_hit_rate": repeated / len(records)},
                    risk=RiskLevel.MEDIUM,
                    rollback_value=tool.spec.cache.enabled,
                )
            )
        return result

    async def apply(
        self, tool: Tool[..., object], recommendation: OptimizationRecommendation
    ) -> OptimizationProfile:
        if recommendation.tool_fingerprint != tool.fingerprint.value:
            raise UnsafeOperationError(
                "Recommendation fingerprint does not match the tool contract"
            )
        if recommendation.setting == "timeout":
            value = float(recommendation.recommended_value)
            if not self.policy.min_timeout <= value <= self.policy.max_timeout:
                raise UnsafeOperationError("Recommended timeout is outside configured safe bounds")
        elif recommendation.setting in {"retry", "cache"} and tool.spec.risk.side_effects != "none":
            raise UnsafeOperationError(
                "Automatic reliability changes are disabled for side-effecting tools"
            )
        current = await self.storage.get_profile(tool.fingerprint.value, self.environment)
        previous = current.settings if current else {}
        settings = dict(previous)
        settings[recommendation.setting] = recommendation.recommended_value
        profile = OptimizationProfile(
            tool_fingerprint=tool.fingerprint.value,
            environment=self.environment,
            version=str(int(current.version) + 1 if current else 1),
            settings=settings,
            previous_settings=previous,
        )
        await self.storage.save_profile(profile)
        return profile

    async def rollback(self, tool: Tool[..., object]) -> OptimizationProfile | None:
        current = await self.storage.get_profile(tool.fingerprint.value, self.environment)
        if current is None:
            return None
        rolled = current.model_copy(
            update={
                "version": str(int(current.version) + 1),
                "settings": current.previous_settings,
                "previous_settings": current.settings,
            }
        )
        await self.storage.save_profile(rolled)
        return rolled

    async def explain(self, tool: Tool[..., object]) -> str:
        recommendations = await self.recommend(tool)
        if not recommendations:
            return f"No recommendation: fewer than {self.policy.min_samples} usable observations"
        return "\n".join(item.reason for item in recommendations)


def select_model(
    candidates: Iterable[ModelCandidate],
    *,
    objective: Literal[
        "minimize_cost", "minimize_latency", "maximize_quality", "balanced"
    ] = "balanced",
    required_capabilities: frozenset[str] = frozenset(),
    allowed_providers: frozenset[str] = frozenset(),
    max_cost: float | None = None,
    max_latency: float | None = None,
    min_quality: float = 0,
    min_context: int = 0,
) -> ModelSelection:
    eligible = [
        item
        for item in candidates
        if required_capabilities.issubset(item.capabilities)
        and (not allowed_providers or item.provider in allowed_providers)
        and (max_cost is None or item.estimated_cost <= max_cost)
        and (max_latency is None or item.estimated_latency <= max_latency)
        and item.quality >= min_quality
        and item.context_limit >= min_context
    ]
    if not eligible:
        raise ValueError("No model candidate satisfies all hard constraints")
    max_candidate_cost = max(item.estimated_cost for item in eligible) or 1
    max_candidate_latency = max(item.estimated_latency for item in eligible) or 1

    def score(item: ModelCandidate) -> float:
        cost_score = 1 - item.estimated_cost / max_candidate_cost
        latency_score = 1 - item.estimated_latency / max_candidate_latency
        if objective == "minimize_cost":
            return cost_score
        if objective == "minimize_latency":
            return latency_score
        if objective == "maximize_quality":
            return item.quality
        return 0.35 * cost_score + 0.25 * latency_score + 0.4 * item.quality

    selected = max(eligible, key=lambda item: (score(item), item.provider, item.model))
    final_score = score(selected)
    return ModelSelection(
        candidate=selected,
        score=final_score,
        objective=objective,
        explanation=(
            f"Selected {selected.provider}/{selected.model} from "
            f"{len(eligible)} eligible candidates; "
            f"score={final_score:.4f} after enforcing hard constraints"
        ),
    )


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("Cannot calculate a percentile of an empty series")
    index = (len(values) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    return values[lower] * (upper - index) + values[upper] * (index - lower)
