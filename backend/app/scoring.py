from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreComponents(BaseModel):
    """Weighted points, not raw 0-1 ratings.

    Risk is deliberately named as a favorability score: more points mean lower,
    better-controlled risk. The six maxima sum to 100.
    """

    expected_roi: float = Field(ge=0, le=25)
    evidence_quality: float = Field(ge=0, le=20)
    capital_efficiency: float = Field(ge=0, le=15)
    ai_leverage: float = Field(ge=0, le=15)
    strategic_value: float = Field(ge=0, le=15)
    risk: float = Field(ge=0, le=10)


SCORE_WEIGHTS = {
    "expected_roi": 25,
    "evidence_quality": 20,
    "capital_efficiency": 15,
    "ai_leverage": 15,
    "strategic_value": 15,
    "risk": 10,
}


def calculate_bcop_score(components: ScoreComponents) -> float:
    """Return the weighted BCOP Opportunity Score on a 0-100 scale."""

    total = sum(getattr(components, name) for name in SCORE_WEIGHTS)
    return round(total, 2)
