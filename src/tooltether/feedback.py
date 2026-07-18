"""Validated application-supplied outcome feedback."""

from __future__ import annotations

from typing import Any

from .models import FeedbackRecord


class FeedbackStore:
    def __init__(self) -> None:
        self._records: dict[str, list[FeedbackRecord]] = {}

    def record(
        self,
        *,
        execution_id: str,
        quality: float | None = None,
        accepted: bool | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "application",
    ) -> FeedbackRecord:
        record = FeedbackRecord(
            execution_id=execution_id,
            quality=quality,
            accepted=accepted,
            metadata=metadata or {},
            source=source,
        )
        self._records.setdefault(execution_id, []).append(record)
        return record

    def for_execution(self, execution_id: str) -> tuple[FeedbackRecord, ...]:
        return tuple(self._records.get(execution_id, ()))
