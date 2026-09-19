from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from app.scoring import ScoreComponents
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator


class EvidenceLevel(StrEnum):
    SAMPLE = "sample"
    FACT = "fact"
    PROJECT_CLAIM = "project_claim"
    ESTIMATE = "estimate"
    INFERENCE = "inference"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Opportunity(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(min_length=1)
    project_id: str | None = None
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_url: AnyHttpUrl
    source_type: str = Field(min_length=1)
    evidence_level: EvidenceLevel
    capital_required_usd: float = Field(ge=0)
    estimated_human_minutes: int = Field(ge=0)
    reward_type: str = Field(min_length=1)
    reward_certainty: str = Field(min_length=1)
    deadline: date | None = None
    risk_level: RiskLevel
    score_components: ScoreComponents
    bcop_score: float = Field(ge=0, le=100)
    recommended_action: str = Field(min_length=1)
    fetched_at: datetime
    is_sample: bool = True
    summary: str = Field(min_length=1)

    @field_validator("bcop_score")
    @classmethod
    def score_must_be_rounded(cls, value: float) -> float:
        return round(value, 2)
