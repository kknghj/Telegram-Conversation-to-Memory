"""회고 카드 사용자 평가 observation log 모델."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Accuracy(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    WRONG = "wrong"


class EvidenceQuality(StrEnum):
    SUFFICIENT = "sufficient"
    WEAK = "weak"
    WRONG = "wrong"


class FailureType(StrEnum):
    SEARCH_FAILURE = "SEARCH_FAILURE"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    INTERPRETATION_FAILURE = "INTERPRETATION_FAILURE"
    OVER_GENERALIZATION = "OVER_GENERALIZATION"
    OBVIOUS_INSIGHT = "OBVIOUS_INSIGHT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    DUPLICATED_CARD = "DUPLICATED_CARD"
    EVIDENCE_WEAK = "EVIDENCE_WEAK"
    EVIDENCE_WRONG = "EVIDENCE_WRONG"


class Action(StrEnum):
    KEEP = "keep"
    REVISE = "revise"
    DISCARD = "discard"


class CardValue(BaseModel):
    interesting: bool
    revisit: bool


class CardEvaluation(BaseModel):
    """카드 1개에 대한 사용자 평가 — 학습 데이터가 아닌 관찰 로그."""

    evaluation_id: str = Field(default_factory=lambda: str(uuid4()))
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    memory_count: int = Field(ge=0)
    card_id: str
    card_type: str
    accuracy: Accuracy
    value: CardValue
    evidence: EvidenceQuality
    failure_type: FailureType | None = None
    user_comment: str = ""
    action: Action | None = None

    @model_validator(mode="after")
    def _derive_action(self) -> CardEvaluation:
        """action은 accuracy / evidence / failure_type 규칙에서 항상 파생한다."""
        object.__setattr__(self, "action", derive_action(self))
        return self


def derive_action(evaluation: CardEvaluation) -> Action:
    """accuracy / evidence / failure_type 규칙으로 action을 결정한다."""
    if evaluation.accuracy == Accuracy.WRONG:
        return Action.DISCARD
    if evaluation.evidence == EvidenceQuality.WEAK:
        return Action.REVISE
    if evaluation.failure_type is not None:
        return Action.REVISE
    return Action.KEEP


EvaluationStats = dict[
    Literal[
        "total_cards",
        "acceptance_rate",
        "value_rate",
        "interesting_rate",
        "revisit_rate",
        "evidence_sufficient_rate",
        "failure_distribution",
    ],
    float | int | dict[str, int],
]
