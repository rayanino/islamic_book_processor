from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


@dataclass(slots=True)
class DecisionRecord:
    artifact: str
    item_id: str
    decision: DecisionAction
    reviewer: str
    timestamp: str
    reason: str
    edited_value: dict[str, Any] | None = None

    @classmethod
    def new(
        cls,
        *,
        artifact: str,
        item_id: str,
        decision: DecisionAction,
        reviewer: str,
        reason: str,
        edited_value: dict[str, Any] | None = None,
    ) -> "DecisionRecord":
        return cls(
            artifact=artifact,
            item_id=item_id,
            decision=decision,
            reviewer=reviewer,
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
            edited_value=edited_value,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "artifact": self.artifact,
            "item_id": self.item_id,
            "decision": self.decision.value,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }
        if self.edited_value is not None:
            data["edited_value"] = self.edited_value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionRecord":
        decision = DecisionAction(str(data["decision"]))
        return cls(
            artifact=str(data["artifact"]),
            item_id=str(data["item_id"]),
            decision=decision,
            reviewer=str(data["reviewer"]),
            timestamp=str(data["timestamp"]),
            reason=str(data["reason"]),
            edited_value=data.get("edited_value"),
        )


@dataclass(slots=True)
class ReviewSummary:
    run_id: str
    book_id: str
    resolved: int = 0
    blocked: int = 0
    approved: int = 0
    edited: int = 0
    rejected: int = 0
    blocked_items: list[str] = field(default_factory=list)

    @property
    def downstream_apply_permitted(self) -> bool:
        return self.blocked == 0


EXERCISE_FAMILY_KEYWORDS: tuple[str, ...] = (
    "أسئلة",
    "تمرين",
    "تطبيق",
    "تدريبات",
    "مسائل للتدريب",
)
